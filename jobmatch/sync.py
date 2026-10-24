"""Bounded, restart-safe synchronization; each invocation exits."""

import time

from filelock import FileLock

from jobmatch import gmail
from jobmatch.analysis import analyze, fingerprint, profile
from jobmatch.config import home, settings
from jobmatch.parsing import extract
from jobmatch.storage import connect


def sync(api=None, evaluator=analyze):
    with FileLock(str(home() / "sync.lock"), timeout=0):
        cfg = settings()
        candidate = profile()
        digest = fingerprint(candidate, cfg.model)
        api = api or gmail.service()
        db = connect()
        run = db.execute("INSERT INTO runs(status) VALUES ('running')").lastrowid
        db.commit()
        counts = {"messages": 0, "analyzed": 0, "errors": 0}
        try:
            # Fixed initial boundary persists across runs: no unread backlog is lost.
            db.execute(
                "CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT)"
            )
            db.execute(
                "INSERT OR IGNORE INTO state VALUES ('since', ?)",
                (str(int(time.time()) - cfg.initial_days * 86400),),
            )
            since = db.execute("SELECT value FROM state WHERE key='since'").fetchone()[
                0
            ]
            db.commit()
            for message_id in gmail.message_ids(
                api, f"({cfg.gmail_query}) after:{since}"
            ):
                if db.execute(
                    "SELECT 1 FROM messages WHERE id=?", (message_id,)
                ).fetchone():
                    continue
                message = (
                    api.users()
                    .messages()
                    .get(userId="me", id=message_id, format="full")
                    .execute(num_retries=3)
                )
                jobs = extract(message)
                with db:
                    db.execute(
                        "INSERT INTO messages(id,received,status,job_count) VALUES (?,?,?,?)",
                        (
                            message_id,
                            int(message.get("internalDate", 0)),
                            "parsed" if jobs else "no_jobs",
                            len(jobs),
                        ),
                    )
                    for job in jobs:
                        db.execute(
                            "INSERT OR IGNORE INTO jobs(id,title,url,context) VALUES (?,?,?,?)",
                            (job.id, job.title, job.url, job.context),
                        )
                        db.execute(
                            "INSERT OR IGNORE INTO message_jobs VALUES (?,?)",
                            (message_id, job.id),
                        )
                counts["messages"] += 1
                if counts["messages"] >= cfg.max_messages:
                    break
            for row in db.execute(
                "SELECT * FROM jobs WHERE analysis IS NULL OR profile_hash != ?",
                (digest,),
            ).fetchall():
                try:
                    result = evaluator(
                        {k: row[k] for k in ("title", "context")}, candidate, cfg.model
                    )
                    with db:
                        db.execute(
                            "UPDATE jobs SET analysis=?,profile_hash=?,error=NULL WHERE id=?",
                            (result.model_dump_json(), digest, row["id"]),
                        )
                    counts["analyzed"] += 1
                except Exception as exc:
                    with db:
                        # Store a safe error category, never response bodies or secrets.
                        db.execute(
                            "UPDATE jobs SET error=? WHERE id=?",
                            (type(exc).__name__, row["id"]),
                        )
                    counts["errors"] += 1
            with db:
                db.execute(
                    "UPDATE runs SET finished=CURRENT_TIMESTAMP,status=?,messages=?,analyzed=?,errors=? WHERE id=?",
                    (
                        "partial" if counts["errors"] else "success",
                        *counts.values(),
                        run,
                    ),
                )
            return counts
        except Exception:
            with db:
                db.execute(
                    "UPDATE runs SET finished=CURRENT_TIMESTAMP,status='failed' WHERE id=?",
                    (run,),
                )
            raise
        finally:
            db.close()
