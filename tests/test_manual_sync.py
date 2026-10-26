from pathlib import Path
from unittest.mock import MagicMock

import pytest
from filelock import FileLock, Timeout
from streamlit.testing.v1 import AppTest

from jobmatch import manual_sync
from jobmatch.config import home, initialize


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBMATCH_HOME", str(tmp_path))
    monkeypatch.setattr(manual_sync, "_child", None)
    initialize()


def test_launcher_uses_private_directory_and_rejects_overlap(monkeypatch):
    child = MagicMock()
    child.poll.return_value = None
    spawn = MagicMock(return_value=child)
    monkeypatch.setattr(manual_sync.subprocess, "Popen", spawn)
    assert manual_sync.launch()
    assert str(home()) == spawn.call_args.args[0][-1]
    assert "jobmatch.manual_sync" in spawn.call_args.args[0]
    assert not manual_sync.launch()
    spawn.assert_called_once()


def test_scheduled_lock_blocks_manual_launch(monkeypatch):
    spawn = MagicMock()
    monkeypatch.setattr(manual_sync.subprocess, "Popen", spawn)
    with FileLock(str(home() / "sync.lock")):
        with pytest.raises(Timeout):
            manual_sync.launch()
    spawn.assert_not_called()


def test_worker_records_safe_failure_and_success(monkeypatch):
    worker = MagicMock(side_effect=RuntimeError("private API response"))
    monkeypatch.setattr("jobmatch.sync.sync", worker)
    manual_sync.run()
    assert manual_sync.read_status() == {"status": "failed", "error": "RuntimeError"}
    worker.side_effect = None
    worker.return_value = {"messages": 2, "analyzed": 4, "errors": 0}
    manual_sync.run()
    assert manual_sync.read_status()["status"] == "success"
    worker.assert_called_with(resync_all=True)


def test_dashboard_button_starts_only_on_explicit_click(monkeypatch):
    launch = MagicMock(return_value=True)
    monkeypatch.setattr(manual_sync, "launch", launch)
    app = AppTest.from_file(
        str(Path(__file__).parents[1] / "jobmatch" / "dashboard.py")
    ).run()
    launch.assert_not_called()
    next(b for b in app.button if b.label == "Resynchronize all offers").click().run()
    launch.assert_called_once()
    assert not app.exception
    assert any("started in the background" in message.value for message in app.success)
