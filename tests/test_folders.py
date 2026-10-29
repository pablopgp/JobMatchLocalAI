import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from jobmatch.config import home, initialize
from jobmatch.storage import connect, create_folder, update_offer


@pytest.fixture(autouse=True)
def isolated_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBMATCH_HOME", str(tmp_path))
    initialize()


def insert_offer():
    with connect() as db:
        db.execute(
            "INSERT INTO jobs(id,title,url,context) VALUES ('123','Engineer','https://www.linkedin.com/jobs/view/123/','Evidence')"
        )


def state():
    with connect() as db:
        return tuple(
            db.execute("SELECT folder_id,viewed FROM jobs WHERE id='123'").fetchone()
        )


def test_default_and_custom_folder_viewed_rules():
    insert_offer()
    assert state() == (1, 0)
    update_offer("123", viewed=True)
    assert state() == (2, 1)
    update_offer("123", viewed=False)
    assert state() == (1, 0)
    custom = create_folder("Applications")
    update_offer("123", folder_id=custom)
    update_offer("123", viewed=True)
    assert state() == (custom, 1)
    update_offer("123", viewed=False)
    assert state() == (custom, 0)
    update_offer("123", folder_id=2)
    assert state() == (2, 1)
    update_offer("123", viewed=False)
    assert state() == (1, 0)


def test_folder_validation_and_persistence():
    identity = create_folder("  Interviews  ")
    with connect() as db:
        assert (
            db.execute("SELECT name FROM folders WHERE id=?", (identity,)).fetchone()[0]
            == "Interviews"
        )
    for invalid in ("", "  ", "offers", "VIEWED", "interviews", "x" * 81):
        with pytest.raises(ValueError):
            create_folder(invalid)
    insert_offer()
    with pytest.raises(ValueError):
        update_offer("123", folder_id=9999)
    assert state() == (1, 0)


def test_migration_moves_existing_viewed_records_once():
    db = sqlite3.connect(home() / "jobs.sqlite3")
    db.execute(
        "CREATE TABLE jobs(id TEXT PRIMARY KEY, title TEXT, url TEXT, context TEXT, first_seen TEXT, analysis TEXT, profile_hash TEXT, error TEXT, viewed INTEGER DEFAULT 0)"
    )
    db.execute(
        "INSERT INTO jobs(id,title,context,viewed) VALUES ('123','Existing','Evidence',1)"
    )
    db.commit()
    db.close()
    assert state() == (2, 1)
    custom = create_folder("Keep here")
    update_offer("123", folder_id=custom)
    assert state() == (custom, 1)


def test_ui_create_move_filter_and_viewed_transitions():
    insert_offer()
    app = AppTest.from_file(
        str(Path(__file__).parents[1] / "jobmatch" / "dashboard.py")
    ).run()
    app.checkbox[0].check().run()
    next(t for t in app.text_input if t.label == "New folder name").input(
        "Favorites"
    ).run()
    next(b for b in app.button if b.label == "Create folder").click().run()
    assert not app.exception
    with connect() as db:
        custom = db.execute("SELECT id FROM folders WHERE name='Favorites'").fetchone()[
            0
        ]
    next(s for s in app.selectbox if s.key == "destination_123").set_value(custom).run()
    next(b for b in app.button if b.label == "Move offer").click().run()
    assert app.metric[0].value == "0"
    next(r for r in app.radio if r.key == "folder_selection").set_value(custom).run()
    app.checkbox[0].uncheck().run()
    assert app.metric[0].value == "1"  # filed offers survive the recent-email view
    next(b for b in app.button if b.key == "viewed_123").click().run()
    assert state() == (custom, 1)
    assert app.metric[0].value == "1"
    next(s for s in app.selectbox if s.key == "destination_123").set_value(2).run()
    next(b for b in app.button if b.label == "Move offer").click().run()
    next(r for r in app.radio if r.key == "folder_selection").set_value(2).run()
    next(b for b in app.button if b.key == "viewed_123").click().run()
    assert state() == (1, 0)
    assert app.metric[0].value == "0"
    assert not app.exception
