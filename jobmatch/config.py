import json
import os
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    model: str = "qwen2.5:7b"
    interval_hours: int = Field(default=3, ge=1, le=168)
    gmail_query: str = (
        "from:(jobalerts-noreply@linkedin.com OR jobs-noreply@linkedin.com)"
    )
    initial_days: int = Field(default=30, ge=1, le=3650)
    max_messages: int = Field(default=200, ge=1, le=5000)


def home() -> Path:
    path = Path(
        os.environ.get(
            "JOBMATCH_HOME",
            str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "JobMatchLocalAI"),
        )
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings() -> Settings:
    path = home() / "settings.json"
    return (
        Settings.model_validate_json(path.read_text("utf-8"))
        if path.exists()
        else Settings()
    )


def initialize():
    root = home()
    defaults = {
        "settings.json": json.dumps(Settings().model_dump(), indent=2),
        "cv.txt": "",
        "preferences.txt": "",
    }
    for name, content in defaults.items():
        path = root / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    return root
