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
    notify_min_score: int
    urgent_min_score: int
    max_price_eur: float
    category_bonus: dict[str, int]
    keywords: dict[str, int]
    exclusions: dict[str, int]
    allowed_stores: tuple[str, ...]

    @classmethod
    def load(cls, path: Path | None = None) -> CashConvertersConfig:
        path = path or Path(__file__).with_name("config.yaml")
        raw: dict[str, Any] = load_yaml(path)
        scan = raw["scan"]
        scoring = raw["scoring"]
        return cls(
            interval_minutes=int(scan["interval_minutes"]),
            pages_per_source=int(scan["pages_per_source"]),
            detail_requests_limit=int(scan["detail_requests_limit"]),
            minimum_products=int(scan["minimum_products"]),
            sudden_drop_ratio=float(scan["sudden_drop_ratio"]),
            sources=tuple(Feed(str(x["name"]), str(x["url"])) for x in raw["sources"]),
            notify_min_score=int(scoring["notify_min_score"]),
            urgent_min_score=int(scoring["urgent_min_score"]),
            max_price_eur=float(scoring["max_price_eur"]),
            category_bonus={str(k).lower(): int(v) for k, v in scoring["category_bonus"].items()},
            keywords={str(k).lower(): int(v) for k, v in scoring["keywords"].items()},
            exclusions={str(k).lower(): int(v) for k, v in scoring["exclusions"].items()},
            allowed_stores=tuple(str(x).casefold() for x in scoring.get("allowed_stores", [])),
        )
