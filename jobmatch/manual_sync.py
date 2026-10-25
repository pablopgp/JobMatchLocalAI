"""One-shot background synchronization started explicitly from the dashboard."""

import json
import os
import subprocess
import sys
from pathlib import Path

from filelock import FileLock, Timeout

from jobmatch.config import home


def write_status(value):
    path = home() / "manual-sync.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(path)


def read_status():
    path = home() / "manual-sync.json"
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def is_running():
    try:
        with FileLock(str(home() / "manual-sync.lock"), timeout=0):
            return False
    except Timeout:
        return True


_child = None


def launch():
    global _child
    with FileLock(str(home() / "manual-launch.lock"), timeout=0):
        if is_running() or (_child is not None and _child.poll() is None):
            return False
        with FileLock(str(home() / "sync.lock"), timeout=0):
            command = [sys.executable, "-m", "jobmatch.manual_sync", str(home())]
            _child = subprocess.Popen(
                command,
                cwd=str(Path(__file__).resolve().parent.parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        return True


def run():
    from jobmatch.sync import sync

    with FileLock(str(home() / "manual-sync.lock"), timeout=0):
        write_status({"status": "running"})
        try:
            result = sync(resync_all=True)
            write_status(
                {"status": "partial" if result["errors"] else "success", **result}
            )
        except BaseException as exc:
            write_status({"status": "failed", "error": type(exc).__name__})


if __name__ == "__main__":
    os.environ["JOBMATCH_HOME"] = sys.argv[1]
    run()
