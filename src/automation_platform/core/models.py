from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARSER_FAILURE = "PARSER_FAILURE"
    SITE_FAILURE = "SITE_FAILURE"
    FAILED = "FAILED"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    URGENT = "urgent"


@dataclass(slots=True)
class Listing:
    source: str
    external_id: str
    title: str
    url: str
    price_cents: int | None = None
    store: str | None = None
    category: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    image_url: str | None = None
    is_new_badge: bool = False
    published_at: datetime | None = None
    score: int = 0
    score_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Notification:
    title: str
    message: str
    priority: Priority = Priority.NORMAL
    url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RunSummary:
    automation: str
    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus = RunStatus.RUNNING
    observed: int = 0
    discovered: int = 0
    requests_count: int = 0
    notifications_sent: int = 0
    errors: list[str] = field(default_factory=list)
