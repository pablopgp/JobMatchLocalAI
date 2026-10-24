"""Run privacy-preserving live acceptance checks on the current private database."""

import json
import time
from pathlib import Path

from googleapiclient.errors import HttpError
from streamlit.testing.v1 import AppTest

from jobmatch.analysis import Analysis
from jobmatch.config import settings
from jobmatch.gmail import message_ids, service
from jobmatch.storage import connect


def main():
    db = connect()
    print(
        json.dumps(
            dict(
                db.execute(
                    "SELECT COUNT(*) AS offers, SUM(analysis IS NOT NULL) AS analyzed FROM jobs"
                ).fetchone()
            )
        )
    )
    analyzed = db.execute(
        "SELECT analysis FROM jobs WHERE analysis IS NOT NULL"
    ).fetchall()
    for row in analyzed:
        Analysis.model_validate_json(row["analysis"])
    print(
        json.dumps(
            {
                "validated_saved_analyses": len(analyzed),
                "duplicate_job_ids": db.execute(
                    "SELECT COUNT(*)-COUNT(DISTINCT id) FROM jobs"
                ).fetchone()[0],
            }
        )
    )
    api = service()
    try:
        cfg = settings()
        cutoff = int(time.time()) - cfg.lookback_hours * 3600
        for identity in message_ids(api, f"({cfg.gmail_query}) after:{cutoff}"):
            if not db.execute(
                "SELECT 1 FROM messages WHERE id=?", (identity,)
            ).fetchone():
                api.users().messages().get(
                    userId="me", id=identity, format="full"
                ).execute(num_retries=1)
                print("Unprocessed Gmail message retrieval succeeded.")
                break
    except HttpError as exc:
        body = json.loads(exc.content)
        print(
            json.dumps(
                {
                    "gmail_status": exc.resp.status,
                    "reasons": [
                        e.get("reason") for e in body.get("error", {}).get("errors", [])
                    ],
                }
            )
        )
    db.close()
    app = AppTest.from_file(str(Path(__file__).with_name("dashboard.py"))).run(
        timeout=30
    )
    print(
        json.dumps(
            {
                "panel_errors": len(app.exception),
                "displayed_offers": app.metric[0].value,
                "analyzed_offer_cards": sum("/100" in e.label for e in app.expander),
            }
        )
    )


if __name__ == "__main__":
    main()
