from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class PlatformSettings:
    environment: str
    database_url: str
    log_level: str
    notification_backend: str
    telegram_bot_token: str | None
    telegram_chat_id: str | None

    @classmethod
    def from_env(cls) -> PlatformSettings:
        return cls(
            environment=os.getenv("AUTOMATION_ENV", "development"),
            database_url=os.getenv("AUTOMATION_DB_URL", "sqlite:///storage/automation.db"),
            log_level=os.getenv("AUTOMATION_LOG_LEVEL", "INFO"),
            notification_backend=os.getenv("NOTIFICATION_BACKEND", "console"),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID") or None,
        )


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise TypeError(f"Configuration root must be an object: {path}")
    return data
