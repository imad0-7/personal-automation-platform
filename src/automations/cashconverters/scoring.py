from __future__ import annotations

import re

from automation_platform.core.models import Listing

from .config import CashConvertersConfig


def _contains(text: str, keyword: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text, flags=re.IGNORECASE) is not None


def score_listing(listing: Listing, config: CashConvertersConfig) -> Listing:
    haystack = " ".join((listing.title, str(listing.attributes.get("description", "")))).casefold()
    points = 0
    reasons: list[str] = []
    for keyword, weight in config.keywords.items():
        if _contains(haystack, keyword):
            points += weight
            reasons.append(keyword.upper())
    for keyword, penalty in config.exclusions.items():
        if _contains(haystack, keyword):
            points += penalty
            reasons.append(f"exclusion: {keyword}")
    if listing.category:
        bonus = config.category_bonus.get(listing.category.casefold(), 0)
        if bonus:
            points += bonus
            reasons.append("PC fixe")
    if listing.price_cents is not None and listing.price_cents <= config.max_price_eur * 100:
        points += 1
        reasons.append(f"prix ≤ {config.max_price_eur:g} €")
    if config.allowed_stores and (listing.store or "").casefold() not in config.allowed_stores:
        points = 0
        reasons.append("magasin hors sélection")
    listing.score = max(0, min(10, points))
    listing.score_reasons = reasons
    return listing
