from __future__ import annotations

import json
import re
import time
from math import ceil
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from automation_platform.core.http import HttpClient
from automation_platform.core.models import Listing

from .config import CashConvertersConfig
from .parser import ParserFailure, enrich_from_detail, parse_catalog


def with_page(url: str, page: int) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if page > 1:
        query["page"] = str(page)
    else:
        query.pop("page", None)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


class CashConvertersScraper:
    def __init__(self, http: HttpClient, config: CashConvertersConfig):
        self.http = http
        self.config = config

    def collect(self, *, full: bool = False, price_scan: bool = False,
                known_ids: set[str] | None = None) -> list[Listing]:
        by_id: dict[str, Listing] = {}
        for feed in self.config.sources:
            first = self.http.get_text(with_page(feed.url, 1))
            first_items = parse_catalog(first, feed.name)
            payload = json.loads(first) if first.lstrip().startswith('{') else {}
            soup = BeautifulSoup(first if not payload else payload.get('rendered_products', ''),
                                 'html.parser')
            count = payload.get('pagination', {}).get('total_items')
            if count is None:
                match = re.search(r'de\s+(\d+)\s+article', soup.get_text(' ', strip=True))
                if match:
                    count = int(match[1])
            if full and count is None:
                raise ParserFailure('Full baseline requires a verifiable catalogue total')
            total_pages = ceil(int(count) / len(first_items)) if count else 50
            target = total_pages if full else (5 if price_scan else self.config.pages_per_source)
            target = min(target, total_pages)
            page = 1
            while page <= target:
                if page > 50:
                    raise ParserFailure('Catalogue exceeded safety page limit')
                if page == 1:
                    items = first_items
                else:
                    time.sleep(0.3)
                    items = parse_catalog(self.http.get_text(with_page(feed.url, page)), feed.name)
                before = len(by_id)
                for listing in items:
                    current = by_id.get(listing.external_id)
                    if current is None:
                        listing.attributes["feeds"] = [feed.name]
                        by_id[listing.external_id] = listing
                    else:
                        feeds = current.attributes.setdefault("feeds", [])
                        if feed.name not in feeds:
                            feeds.append(feed.name)
                if len(by_id) == before:
                    raise ParserFailure('Pagination repeated a page; previous state preserved')
                # Catch up after downtime until reaching the known catalogue boundary.
                if (not full and page == target and known_ids is not None
                        and not any(x.external_id in known_ids for x in items)
                        and target < total_pages):
                    target += 1
                page += 1
            if full and len(by_id) != int(count):
                raise ParserFailure('Catalogue changed during baseline; retry next scan')
        return list(by_id.values())

    def enrich(self, listing: Listing) -> Listing:
        return enrich_from_detail(listing, self.http.get_text(listing.url))
