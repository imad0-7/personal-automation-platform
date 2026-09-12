from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from automation_platform.core.http import HttpClient
from automation_platform.core.models import Listing

from .config import CashConvertersConfig
from .parser import enrich_from_detail, parse_catalog


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

    def collect(self) -> list[Listing]:
        by_id: dict[str, Listing] = {}
        for feed in self.config.sources:
            for page in range(1, self.config.pages_per_source + 1):
                html = self.http.get_text(with_page(feed.url, page))
                for listing in parse_catalog(html, feed.name):
                    current = by_id.get(listing.external_id)
                    if current is None:
                        listing.attributes["feeds"] = [feed.name]
                        by_id[listing.external_id] = listing
                    else:
                        feeds = current.attributes.setdefault("feeds", [])
                        if feed.name not in feeds:
                            feeds.append(feed.name)
        return list(by_id.values())

    def enrich(self, listing: Listing) -> Listing:
        return enrich_from_detail(listing, self.http.get_text(listing.url))
