import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
from googleapiclient.errors import HttpError

from jobmatch.config import home, initialize, settings


def doctor():
    root = home()
    result = {
        "data_directory": str(root),
        "oauth_client": (root / "credentials.json").exists(),
        "oauth_token": (root / "token.dpapi").exists(),
        "cv": bool((root / "cv.txt").read_text("utf-8").strip()),
        "preferences": bool((root / "preferences.txt").read_text("utf-8").strip()),
    }
    try:
        cfg = settings()
        result["configured_model"] = cfg.model
        result["ollama_url"] = cfg.ollama_url
        with httpx.Client(trust_env=False, timeout=5, follow_redirects=False) as client:
            response = client.get(f"{cfg.ollama_url}/api/tags")
            response.raise_for_status()
            result["ollama_models"] = [m["name"] for m in response.json()["models"]]
            result["configured_model_available"] = cfg.model in result["ollama_models"]
    except Exception as exc:
        result["ollama_error"] = type(exc).__name__
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Private local job matching")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument(
        "--max-analyses",
        type=int,
        choices=range(1, 5001),
        metavar="1-5000",
        help="Override the analysis batch size for this sync only",
    )
    parser.add_argument(
        "command",
        choices=[
            "init",
            "doctor",
            "authorize",
            "sync",
            "dashboard",
            "install-task",
            "remove-task",
        ],
    )
    args = parser.parse_args()
    if args.data_dir:
        os.environ["JOBMATCH_HOME"] = str(args.data_dir.resolve())
    try:
        initialize()
        if args.command == "init":
            print(home())
        elif args.command == "doctor":
            doctor()
        elif args.command == "authorize":
            from jobmatch.gmail import authorize

            authorize()
            print("Gmail read-only authorization saved with Windows DPAPI.")
        elif args.command == "sync":
            from jobmatch.sync import sync

            result = sync(max_analyses=args.max_analyses)
            print(json.dumps(result))
            return 1 if result["errors"] else 0
        elif args.command == "dashboard":
            app = Path(__file__).with_name("dashboard.py")
            return subprocess.call(
                [
                    sys.executable,
                    "-m",
                    "streamlit",
                    "run",
                    str(app),
                    "--server.address=127.0.0.1",
                    "--browser.gatherUsageStats=false",
                    "--server.headless=true",
                ]
            )
        else:
            from jobmatch import scheduler

            scheduler.install() if args.command == "install-task" else scheduler.remove()
            print("Scheduled task updated.")
    except Exception as exc:
        detail = (
            str(exc)
            if isinstance(exc, RuntimeError)
            else "Run doctor and consult README.md."
        )
        if isinstance(exc, HttpError):
            detail = f"Gmail API returned HTTP {exc.resp.status}. Saved offers are preserved; retry synchronization."
        print(f"Operation failed ({type(exc).__name__}): {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
