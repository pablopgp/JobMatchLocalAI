import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class Settings(BaseModel):
    model: str = "qwen3:4b-instruct"
    ollama_url: Literal["http://localhost:11434", "http://127.0.0.1:11434"] = (
        "http://localhost:11434"
    )
    interval_hours: int = Field(default=3, ge=1, le=168)
    gmail_query: str = (
        "from:(jobalerts-noreply@linkedin.com OR jobs-noreply@linkedin.com)"
    )
    lookback_hours: int = Field(default=24, ge=1, le=87600)
    max_messages: int = Field(default=200, ge=1, le=5000)
    max_analyses: int = Field(default=20, ge=1, le=5000)


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
        Settings.model_validate_json(path.read_text("utf-8-sig"))
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
