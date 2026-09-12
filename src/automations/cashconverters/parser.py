from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from automation_platform.core.models import Listing


class ParserFailure(RuntimeError):
    pass


def _price_to_cents(text: str) -> int | None:
    value = text.replace("\xa0", " ").replace("€", "").strip().replace(" ", "")
    value = value.replace(".", "").replace(",", ".")
    try:
        return round(float(value) * 100)
    except ValueError:
        return None


def parse_catalog(html: str, feed_name: str) -> list[Listing]:
    wrapped_fragment = False
    if html.lstrip().startswith("{"):
        try:
            payload = json.loads(html)
            rendered = payload.get("rendered_products")
        except (json.JSONDecodeError, AttributeError) as exc:
            raise ParserFailure(f"Invalid JSON catalogue response for {feed_name}") from exc
        if not isinstance(rendered, str):
            raise ParserFailure(f"JSON catalogue has no rendered_products for {feed_name}")
        html = rendered
        wrapped_fragment = True
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one("#js-product-list")
    cards = soup.select("article.product-miniature[data-id-product]")
    if (container is None and not wrapped_fragment) or not cards:
        raise ParserFailure(f"Expected product list/cards missing for {feed_name}")

    listings: list[Listing] = []
    for card in cards:
        external_id = str(card.get("data-id-product", "")).strip()
        link = card.select_one("a.product-thumbnail[href]") or card.select_one(".product-title a[href]")
        title_node = card.select_one(".product-title a")
        if not external_id or link is None or title_node is None:
            raise ParserFailure(f"Required product fields missing in {feed_name}")
        url = str(link.get("href"))
        path_parts = [part for part in urlparse(url).path.split("/") if part]
        category = path_parts[-2] if len(path_parts) >= 2 else None
        price_node = card.select_one(".price")
        store_node = card.select_one(".magasin")
        image_node = card.select_one("img[src]")
        flags = {x.get_text(" ", strip=True).casefold() for x in card.select(".product-flag")}
        listings.append(Listing(
            source="cashconverters",
            external_id=external_id,
            title=title_node.get_text(" ", strip=True),
            url=url,
            price_cents=_price_to_cents(price_node.get_text(" ", strip=True)) if price_node else None,
            store=re.sub(r"^storefront\s*", "", store_node.get_text(" ", strip=True), flags=re.IGNORECASE) if store_node else None,
            category=category,
            attributes={"feed": feed_name},
            image_url=str(image_node.get("data-full-size-image-url") or image_node.get("src")) if image_node else None,
            is_new_badge="nouveau" in flags,
        ))
    return listings


def enrich_from_detail(listing: Listing, html: str) -> Listing:
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one("#product-details[data-product]")
    if node is None:
        raise ParserFailure(f"Product detail data missing for {listing.external_id}")
    try:
        data = json.loads(str(node["data-product"]))
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ParserFailure(f"Invalid product detail data for {listing.external_id}") from exc

    listing.title = str(data.get("name") or listing.title).strip()
    listing.price_cents = round(float(data["price_amount"]) * 100) if data.get("price_amount") is not None else listing.price_cents
    listing.category = str(data.get("category_name") or data.get("category") or listing.category)
    features = {str(x.get("name")): str(x.get("value")) for x in data.get("features", [])}
    listing.store = features.get("Magasin", listing.store)
    listing.attributes.update({
        "reference": data.get("reference"),
        "features": features,
        "description": BeautifulSoup(str(data.get("description") or ""), "html.parser").get_text(" ", strip=True),
    })
    date_added = data.get("date_add")
    if isinstance(date_added, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", date_added):
        listing.published_at = (
            datetime.fromisoformat(date_added)
            .replace(tzinfo=ZoneInfo("Europe/Brussels"))
            .astimezone(UTC)
        )
    cover = data.get("cover") or {}
    listing.image_url = cover.get("large", {}).get("url") or listing.image_url
    listing.is_new_badge = bool(data.get("new", listing.is_new_badge))
    return listing
