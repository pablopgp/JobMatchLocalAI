import base64
import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from filelock import FileLock, Timeout
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest

from jobmatch.analysis import Analysis, analyze
from jobmatch.config import home, initialize
from jobmatch.parsing import canonical_job, extract
from jobmatch.storage import connect
from jobmatch.sync import sync


@pytest.fixture(autouse=True)
def private_home(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBMATCH_HOME", str(tmp_path))
    initialize()
    (tmp_path / "cv.txt").write_text("Python developer with SQLite experience.")
    (tmp_path / "preferences.txt").write_text("Remote Python roles in Spain.")


def mail(id="m1"):
    html = '<table><tr><td><a href="https://www.linkedin.com/jobs/view/12345/?trk=email">Python engineer</a> Remote Madrid</td></tr></table>'
    return {
        "id": id,
        "internalDate": str(int(time.time() * 1000)),
        "payload": {
            "headers": [
                {"name": "From", "value": "Jobs <jobalerts-noreply@linkedin.com>"}
            ],
            "mimeType": "text/html",
            "body": {
                "data": base64.urlsafe_b64encode(html.encode()).decode().rstrip("=")
            },
        },
    }


def api_for(messages):
    api = MagicMock()
    api.users().messages().list().execute.return_value = {
        "messages": [{"id": m["id"]} for m in messages]
    }
    api.users().messages().get().execute.side_effect = messages
    return api


def evaluation(*args):
    return Analysis(
        score=80,
        confidence="low",
        reasons=["Python matches"],
        missing_information=["Salary", "Full requirements"],
        concerns=[],
    )


def test_link_security_and_dedup():
    assert (
        canonical_job("https://www.linkedin.com/jobs/view/python-role-12345/?trk=x")
        == "12345"
    )
    assert canonical_job("https://linkedin.com.evil.test/jobs/view/12345/") is None
    assert canonical_job("http://linkedin.com/jobs/view/12345/") is None
    assert extract(mail())[0].id == "12345"
    bad = mail()
    bad["payload"]["headers"][0]["value"] = "attacker@example.com"
    assert extract(bad) == []


def test_sync_idempotency_and_profile_change():
    assert sync(api_for([mail(), mail("m2")]), evaluation) == {
        "messages": 2,
        "analyzed": 1,
        "errors": 0,
    }
    assert sync(api_for([mail(), mail("m2")]), evaluation)["analyzed"] == 0
    (home() / "preferences.txt").write_text("Only onsite roles.")
    assert sync(api_for([]), evaluation)["analyzed"] == 1
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM message_jobs").fetchone()[0] == 2


def test_analysis_failure_is_retried():
    def broken(*args):
        raise ValueError("private response")

    assert sync(api_for([mail()]), broken)["errors"] == 1
    with connect() as db:
        assert db.execute("SELECT error FROM jobs").fetchone()[0] == "ValueError"
    assert sync(api_for([]), evaluation)["analyzed"] == 1


def test_lock_prevents_overlapping_runs():
    with FileLock(str(home() / "sync.lock")):
        with pytest.raises(Timeout):
            sync(api_for([]), evaluation)


def test_schema_and_cloud_guard():
    with pytest.raises(ValidationError):
        Analysis(
            score=101,
            confidence="high",
            reasons=["x"],
            missing_information=[],
            concerns=[],
        )
    with pytest.raises(RuntimeError):
        analyze({}, {}, "model:cloud")


def test_ollama_transport(monkeypatch):
    original = httpx.Client

    def handler(request):
        assert request.url.host == "localhost"
        if request.url.path == "/api/show":
            return httpx.Response(200, json={})
        body = json.loads(request.content)
        assert body["stream"] is False
        assert body["think"] is False
        assert body["format"]["type"] == "object"
        return httpx.Response(
            200, json={"message": {"content": evaluation().model_dump_json()}}
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    assert analyze({"title": "Engineer"}, {}, "local:7b").score == 80


def test_dashboard_shows_saved_job():
    sync(api_for([mail()]), evaluation)
    app = AppTest.from_file(
        str(Path(__file__).parents[1] / "jobmatch" / "dashboard.py")
    ).run(timeout=20)
    assert not app.exception
    assert app.metric[0].value == "1"
    assert any("80/100" in exp.label for exp in app.expander)


def test_dpapi_roundtrip():
    from jobmatch.gmail import save_token
    import win32crypt

    creds = MagicMock()
    creds.to_json.return_value = '{"token":"synthetic-test-only"}'
    save_token(creds)
    blob = (home() / "token.dpapi").read_bytes()
    assert b"synthetic-test-only" not in blob
    assert (
        win32crypt.CryptUnprotectData(blob, None, None, None, 0)[1].decode()
        == creds.to_json()
    )


def test_gmail_failure_does_not_mark_processed():
    api = api_for([mail()])
    api.users().messages().get().execute.side_effect = RuntimeError("offline")
    with pytest.raises(RuntimeError):
        sync(api, evaluation)
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
        assert db.execute("SELECT status FROM runs").fetchone()[0] == "failed"


def test_gmail_pagination():
    from jobmatch.gmail import message_ids

    api = MagicMock()
    api.users().messages().list().execute.side_effect = [
        {"messages": [{"id": "1"}], "nextPageToken": "next"},
        {"messages": [{"id": "2"}]},
    ]
    assert list(message_ids(api, "query")) == ["1", "2"]


def test_missing_profile_fails_before_network():
    (home() / "cv.txt").write_text("")
    with pytest.raises(RuntimeError, match="cv.txt"):
        sync(api_for([]), evaluation)


def test_scheduler_xml(monkeypatch):
    import xml.etree.ElementTree as ET
    from jobmatch.scheduler import task_xml

    monkeypatch.setattr("subprocess.check_output", lambda *a, **kw: "MACHINE\\user")
    xml = task_xml()
    ET.fromstring(xml)
    assert "PT3H" in xml
    assert "InteractiveToken" in xml
    assert "--data-dir" in xml


def test_analysis_batch_preserves_pending_work():
    first = mail()
    second = mail("m2")
    raw = base64.urlsafe_b64decode(second["payload"]["body"]["data"] + "==").decode()
    second["payload"]["body"]["data"] = base64.urlsafe_b64encode(
        raw.replace("12345", "67890").encode()
    ).decode()
    assert sync(api_for([first, second]), evaluation, max_analyses=1)["analyzed"] == 1
    assert sync(api_for([]), evaluation, max_analyses=1)["analyzed"] == 1
    assert sync(api_for([]), evaluation, max_analyses=1)["analyzed"] == 0


def test_rolling_window_skips_old_mail_and_old_pending_analyses():
    recent = mail("recent")
    api = api_for([recent])
    assert sync(api, evaluation)["analyzed"] == 1
    query = api.users().messages().list.call_args.kwargs["q"]
    cutoff = int(query.rsplit("after:", 1)[1])
    assert abs(cutoff - (int(time.time()) - 86400)) < 2
    with connect() as db:
        db.execute("UPDATE messages SET received=?", ((cutoff - 1) * 1000,))
        db.execute("UPDATE jobs SET analysis=NULL,profile_hash=NULL")
    old = mail("old")
    old["internalDate"] = str((cutoff - 10) * 1000)
    assert sync(api_for([old]), evaluation) == {
        "messages": 0,
        "analyzed": 0,
        "errors": 0,
    }
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 1


def test_recent_recommendation_makes_existing_offer_eligible_again():
    sync(api_for([mail()]), evaluation)
    with connect() as db:
        db.execute("UPDATE messages SET received=0")
        db.execute("UPDATE jobs SET analysis=NULL,profile_hash=NULL")
    assert sync(api_for([mail("new-recommendation")]), evaluation)["analyzed"] == 1


def test_dashboard_hides_old_offers_without_deleting_them():
    sync(api_for([mail()]), evaluation)
    with connect() as db:
        db.execute("UPDATE messages SET received=0")
    app = AppTest.from_file(
        str(Path(__file__).parents[1] / "jobmatch" / "dashboard.py")
    ).run(timeout=20)
    assert not app.exception
    assert app.metric[0].value == "0"
    app.checkbox[0].check().run()
    assert not app.exception
    assert app.metric[0].value == "1"
