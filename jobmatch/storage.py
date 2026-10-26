import sqlite3

from jobmatch.config import home

TRACKING_STATUSES = (
    "Interested",
    "Applied",
    "Interview",
    "Offer",
    "Rejected",
    "Closed",
)


def connect():
    db = sqlite3.connect(home() / "jobs.sqlite3", timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript("""
    PRAGMA journal_mode=WAL;
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS messages (
      id TEXT PRIMARY KEY, received INTEGER NOT NULL, status TEXT NOT NULL,
      job_count INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
      context TEXT NOT NULL, first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      analysis TEXT, profile_hash TEXT, error TEXT);
    CREATE TABLE IF NOT EXISTS message_jobs (
      message_id TEXT REFERENCES messages(id), job_id TEXT REFERENCES jobs(id),
      PRIMARY KEY(message_id, job_id));
    CREATE TABLE IF NOT EXISTS runs (
      id INTEGER PRIMARY KEY, started TEXT DEFAULT CURRENT_TIMESTAMP,
      finished TEXT, status TEXT, messages INTEGER DEFAULT 0,
      analyzed INTEGER DEFAULT 0, errors INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS deleted_jobs (id TEXT PRIMARY KEY);
    """)
    db.execute("BEGIN IMMEDIATE")
    columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
    additions = {
        "company": "TEXT",
        "saved": "INTEGER NOT NULL DEFAULT 0",
        "tracking_status": "TEXT NOT NULL DEFAULT 'Interested'",
        "notes": "TEXT NOT NULL DEFAULT ''",
        "deleted_at": "TEXT",
        "viewed": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, definition in additions.items():
        if name not in columns:
            db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
    db.commit()
    return db


def update_offer(
    job_id, *, saved=None, status=None, notes=None, deleted=None, viewed=None
):
    """Persist user actions without touching email evidence or analysis."""
    if status is not None and status not in TRACKING_STATUSES:
        raise ValueError("Unknown tracking status")
    if notes is not None and len(notes) > 10000:
        raise ValueError("Notes must contain at most 10,000 characters")
    assignments, values = [], []
    for column, value in (
        ("saved", None if saved is None else int(saved)),
        ("tracking_status", status),
        ("notes", notes),
        ("viewed", None if viewed is None else int(viewed)),
    ):
        if value is not None:
            assignments.append(f"{column}=?")
            values.append(value)
    if deleted is not None:
        assignments.append(
            "deleted_at=CURRENT_TIMESTAMP" if deleted else "deleted_at=NULL"
        )
    if not assignments:
        return
    db = connect()
    try:
        with db:
            db.execute(
                f"UPDATE jobs SET {','.join(assignments)} WHERE id=?", (*values, job_id)
            )
    finally:
        db.close()


def empty_trash():
    """Remove trashed records and retain only IDs to prevent reimport."""
    db = connect()
    try:
        with db:
            db.execute(
                "INSERT OR IGNORE INTO deleted_jobs SELECT id FROM jobs WHERE deleted_at IS NOT NULL"
            )
            db.execute(
                "DELETE FROM message_jobs WHERE job_id IN (SELECT id FROM jobs WHERE deleted_at IS NOT NULL)"
            )
            count = db.execute("DELETE FROM jobs WHERE deleted_at IS NOT NULL").rowcount
        return count
    finally:
        db.close()
