from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from automation_platform.core.config import load_yaml


@dataclass(frozen=True, slots=True)
class Feed:
    name: str
    url: str


@dataclass(frozen=True, slots=True)
class CashConvertersConfig:
    interval_minutes: int
    pages_per_source: int
    detail_requests_limit: int
    minimum_products: int
    sudden_drop_ratio: float
    sources: tuple[Feed, ...]

    @classmethod
    def load(cls, path: Path | None = None) -> CashConvertersConfig:
        path = path or Path(__file__).with_name("config.yaml")
        raw: dict[str, Any] = load_yaml(path)
        scan = raw["scan"]
        return cls(
            interval_minutes=int(scan["interval_minutes"]),
            pages_per_source=int(scan["pages_per_source"]),
            detail_requests_limit=int(scan["detail_requests_limit"]),
            minimum_products=int(scan["minimum_products"]),
            sudden_drop_ratio=float(scan["sudden_drop_ratio"]),
            sources=tuple(Feed(str(x["name"]), str(x["url"])) for x in raw["sources"]),
        )
