from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from ..models import Listing, Notification, Priority, RunSummary

SCHEMA = """
CREATE TABLE IF NOT EXISTS automation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    automation TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    observed INTEGER NOT NULL DEFAULT 0,
    discovered INTEGER NOT NULL DEFAULT 0,
    requests_count INTEGER NOT NULL DEFAULT 0,
    notifications_sent INTEGER NOT NULL DEFAULT 0,
    errors_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_runs_automation ON automation_runs(automation, id DESC);

CREATE TABLE IF NOT EXISTS listings (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    price_cents INTEGER,
    store TEXT,
    category TEXT,
    attributes_json TEXT NOT NULL DEFAULT '{}',
    image_url TEXT,
    is_new_badge INTEGER NOT NULL DEFAULT 0,
    published_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    score INTEGER NOT NULL DEFAULT 0,
    score_reasons_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (source, external_id)
);

CREATE TABLE IF NOT EXISTS notification_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    automation TEXT NOT NULL,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    backend TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT,
    UNIQUE (automation, source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending ON notification_outbox(automation, status);
"""


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


class SQLiteRepository:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row

    def migrate(self) -> None:
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def begin_run(self, automation: str) -> int:
        cursor = self.connection.execute(
            "INSERT INTO automation_runs(automation, started_at, status) VALUES (?, ?, 'RUNNING')",
            (automation, _iso_now()),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def finish_run(self, run_id: int, summary: RunSummary) -> None:
        self.connection.execute(
            """UPDATE automation_runs SET finished_at=?, status=?, observed=?, discovered=?, requests_count=?,
               notifications_sent=?, errors_json=? WHERE id=?""",
            (
                (summary.finished_at or datetime.now(UTC)).isoformat(),
                summary.status.value,
                summary.observed,
                summary.discovered,
                summary.requests_count,
                summary.notifications_sent,
                json.dumps(summary.errors, ensure_ascii=False),
                run_id,
            ),
        )
        self.connection.commit()

    def has_successful_run(self, automation: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM automation_runs WHERE automation=? AND status='SUCCESS' LIMIT 1",
            (automation,),
        ).fetchone()
        return row is not None

    def previous_observed_count(self, automation: str) -> int | None:
        row = self.connection.execute(
            "SELECT observed FROM automation_runs WHERE automation=? AND status='SUCCESS' ORDER BY id DESC LIMIT 1",
            (automation,),
        ).fetchone()
        return int(row["observed"]) if row else None

    def known_ids(self, source: str, external_ids: Sequence[str]) -> set[str]:
        if not external_ids:
            return set()
        placeholders = ",".join("?" for _ in external_ids)
        rows = self.connection.execute(
            f"SELECT external_id FROM listings WHERE source=? AND external_id IN ({placeholders})",
            (source, *external_ids),
        ).fetchall()
        return {str(row["external_id"]) for row in rows}

    def save_listings(self, listings: Sequence[Listing]) -> None:
        now = _iso_now()
        self.connection.executemany(
            """INSERT INTO listings(
                   source, external_id, title, url, price_cents, store, category,
                   attributes_json, image_url, is_new_badge, published_at,
                   first_seen_at, last_seen_at, score, score_reasons_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(source, external_id) DO UPDATE SET
                   title=excluded.title, url=excluded.url, price_cents=excluded.price_cents,
                   store=excluded.store, category=excluded.category,
                   attributes_json=excluded.attributes_json, image_url=excluded.image_url,
                   is_new_badge=excluded.is_new_badge, published_at=excluded.published_at,
                   last_seen_at=excluded.last_seen_at, score=excluded.score,
                   score_reasons_json=excluded.score_reasons_json""",
            [
                (
                    x.source, x.external_id, x.title, x.url, x.price_cents, x.store, x.category,
                    json.dumps(x.attributes, ensure_ascii=False), x.image_url, int(x.is_new_badge),
                    x.published_at.isoformat() if x.published_at else None, now, now, x.score,
                    json.dumps(x.score_reasons, ensure_ascii=False),
                )
                for x in listings
            ],
        )
        self.connection.commit()

    def enqueue_notification(
        self, automation: str, listing: Listing, notification: Notification
    ) -> None:
        payload = {
            "title": notification.title,
            "message": notification.message,
            "priority": notification.priority.value,
            "url": notification.url,
            "metadata": notification.metadata,
        }
        self.connection.execute(
            """INSERT OR IGNORE INTO notification_outbox(
                   automation, source, external_id, payload_json, created_at
               ) VALUES (?, ?, ?, ?, ?)""",
            (automation, listing.source, listing.external_id, json.dumps(payload), _iso_now()),
        )
        self.connection.commit()

    def pending_notifications(self, automation: str) -> list[tuple[int, Notification]]:
        rows = self.connection.execute(
            "SELECT id, payload_json FROM notification_outbox WHERE automation=? AND status='pending' ORDER BY id",
            (automation,),
        ).fetchall()
        result: list[tuple[int, Notification]] = []
        for row in rows:
            data = json.loads(row["payload_json"])
            result.append((int(row["id"]), Notification(
                title=data["title"], message=data["message"],
                priority=Priority(data["priority"]), url=data.get("url"),
                metadata=data.get("metadata", {}),
            )))
        return result

    def mark_notification_sent(self, notification_id: int, backend: str) -> None:
        self.connection.execute(
            "UPDATE notification_outbox SET status='sent', backend=?, sent_at=? WHERE id=?",
            (backend, _iso_now(), notification_id),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


def repository_from_url(url: str) -> SQLiteRepository:
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise ValueError("V1 supports sqlite:/// URLs; the repository interface permits a PostgreSQL adapter later")
    return SQLiteRepository(Path(url.removeprefix(prefix)))
