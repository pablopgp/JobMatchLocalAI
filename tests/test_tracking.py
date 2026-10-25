import base64
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from streamlit.testing.v1 import AppTest

from jobmatch.config import home, initialize
from jobmatch.storage import connect, update_offer, empty_trash
from jobmatch.sync import sync


@pytest.fixture(autouse=True)
def private_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBMATCH_HOME", str(tmp_path))
    initialize()
    (tmp_path / "cv.txt").write_text("Python developer")
    (tmp_path / "preferences.txt").write_text("Remote roles")


def insert_offer():
    with connect() as db:
        db.execute(
            "INSERT INTO jobs(id,title,url,context) VALUES ('123','Engineer','https://www.linkedin.com/jobs/view/123/','Evidence')"
        )


def test_legacy_database_migration_preserves_existing_offer():
    db = sqlite3.connect(home() / "jobs.sqlite3")
    db.execute(
        "CREATE TABLE jobs(id TEXT PRIMARY KEY,title TEXT,url TEXT,context TEXT,first_seen TEXT,analysis TEXT,profile_hash TEXT,error TEXT)"
    )
    db.execute(
        "INSERT INTO jobs(id,title,context) VALUES ('old','Existing role','Original evidence')"
    )
    db.commit()
    db.close()
    with connect() as db:
        row = db.execute("SELECT * FROM jobs WHERE id='old'").fetchone()
        assert row["context"] == "Original evidence"
        assert row["saved"] == 0
        assert row["deleted_at"] is None


def test_tracking_persists_across_reconnections_and_restore():
    insert_offer()
    update_offer("123", saved=True, status="Interview", notes="Call on Monday")
    update_offer("123", deleted=True)
    with connect() as db:
        row = db.execute("SELECT * FROM jobs WHERE id='123'").fetchone()
        assert row["saved"] == 1 and row["tracking_status"] == "Interview"
        assert row["notes"] == "Call on Monday"
        assert row["deleted_at"]
    update_offer("123", deleted=False)
    with connect() as db:
        assert db.execute("SELECT notes,deleted_at FROM jobs").fetchone()[:] == (
            "Call on Monday",
            None,
        )
    with pytest.raises(ValueError):
        update_offer("123", status="invented")


@pytest.mark.parametrize("purge", [False, True])
def test_deleted_offer_is_not_reimported_or_analyzed(purge):
    import time

    insert_offer()
    update_offer("123", deleted=True)
    if purge:
        assert empty_trash() == 1
    payload = base64.urlsafe_b64encode(
        b'<a href="https://www.linkedin.com/jobs/view/123/">Engineer</a>'
    ).decode()
    api = MagicMock()
    api.users().messages().list().execute.return_value = {
        "messages": [{"id": "new-mail"}]
    }
    api.users().messages().get().execute.return_value = {
        "internalDate": str(int(time.time() * 1000)),
        "payload": {
            "headers": [{"name": "From", "value": "jobs-noreply@linkedin.com"}],
            "mimeType": "text/html",
            "body": {"data": payload},
        },
    }
    evaluator = MagicMock()
    result = sync(api, evaluator)
    assert result["analyzed"] == 0
    evaluator.assert_not_called()
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == (
            0 if purge else 1
        )
        if not purge:
            assert db.execute("SELECT deleted_at FROM jobs").fetchone()[0]


def test_dashboard_save_follow_up_delete_and_restore(monkeypatch):
    # An old saved offer must remain available outside the email time window.
    insert_offer()
    monkeypatch.setattr(
        "jobmatch.gmail.service", lambda: pytest.fail("Dashboard must not access Gmail")
    )
    app = AppTest.from_file(
        str(Path(__file__).parents[1] / "jobmatch" / "dashboard.py")
    ).run()
    app.checkbox[0].check().run()
    next(b for b in app.button if b.key == "save_123").click().run()
    app.checkbox[0].uncheck().run()
    assert app.metric[0].value == "1"
    next(s for s in app.selectbox if s.key == "status_123").select("Interview").run()
    app.text_area[0].input("Ask about remote policy").run()
    next(b for b in app.button if b.label == "Save follow-up").click().run()
    with connect() as db:
        assert db.execute("SELECT tracking_status,notes FROM jobs").fetchone()[:] == (
            "Interview",
            "Ask about remote policy",
        )
    app.radio[0].set_value("Saved offers").run()
    assert app.metric[0].value == "1"
    next(b for b in app.button if b.key == "delete_123").click().run()
    assert app.metric[0].value == "0"
    app.radio[0].set_value("Trash").run()
    assert app.metric[0].value == "1"
    next(b for b in app.button if b.key == "restore_123").click().run()
    app.radio[0].set_value("Saved offers").run()
    assert app.metric[0].value == "1"
    assert app.text_area[0].value == "Ask about remote policy"
    assert not app.exception


def test_empty_trash_keeps_active_offers_and_removes_notes():
    insert_offer()
    with connect() as db:
        db.execute(
            "INSERT INTO jobs(id,title,url,context) VALUES ('456','Keep','url','evidence')"
        )
        db.execute(
            "INSERT INTO messages(id,received,status) VALUES ('mail',0,'parsed')"
        )
        db.execute("INSERT INTO message_jobs VALUES ('mail','123')")
    update_offer("123", deleted=True, notes="private notes", viewed=True)
    assert empty_trash() == 1
    assert empty_trash() == 0
    with connect() as db:
        assert db.execute("SELECT id FROM jobs").fetchone()[0] == "456"
        assert db.execute("SELECT COUNT(*) FROM message_jobs").fetchone()[0] == 0
        assert db.execute("SELECT id FROM deleted_jobs").fetchone()[0] == "123"


def test_viewed_highlight_and_confirmed_empty_trash_ui():
    insert_offer()
    app = AppTest.from_file(
        str(Path(__file__).parents[1] / "jobmatch" / "dashboard.py")
    ).run()
    app.checkbox[0].check().run()
    next(b for b in app.button if b.key == "viewed_123").click().run()
    assert not app.exception
    with connect() as db:
        assert db.execute("SELECT viewed FROM jobs").fetchone()[0] == 1
    assert "#e0f2fe" in str(app.get("html")[0].proto)
    assert next(b for b in app.button if b.key == "viewed_123").label == "Viewed ✓"
    next(b for b in app.button if b.key == "delete_123").click().run()
    app.radio[0].set_value("Trash").run()
    assert next(b for b in app.button if b.label == "Empty trash permanently").disabled
    next(c for c in app.checkbox if c.key == "confirm_empty_trash").check().run()
    next(b for b in app.button if b.label == "Empty trash permanently").click().run()
    assert not app.exception
    assert app.metric[0].value == "0"
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
