from pathlib import Path

import httpx

from automation_platform.core.database.sqlite import SQLiteRepository
from automation_platform.core.models import Listing, RunStatus
from automations.cashconverters.config import CashConvertersConfig
from automations.cashconverters.parser import ParserFailure
from automations.cashconverters.service import CashConvertersAutomation


def listing(external_id: str, title: str = "PC Gaming Ryzen RTX 4070") -> Listing:
    return Listing(
        source="cashconverters", external_id=external_id, title=title,
        url=f"https://example.test/{external_id}", price_cents=69900,
        store="JETTE", category="ordinateurs de bureau",
    )


class FakeHttp:
    requests_count = 1


class FakeScraper:
    def __init__(self, batches):
        self.batches = iter(batches)
        self.http = FakeHttp()

    def collect(self):
        value = next(self.batches)
        if isinstance(value, Exception):
            raise value
        return value

    def enrich(self, item):
        return item


class FakeNotifier:
    backend_name = "fake"

    def __init__(self):
        self.sent = []

    def notify(self, notification):
        self.sent.append(notification)


def config(minimum_products=1):
    base = CashConvertersConfig.load()
    return CashConvertersConfig(
        interval_minutes=base.interval_minutes, pages_per_source=base.pages_per_source,
        detail_requests_limit=base.detail_requests_limit, minimum_products=minimum_products,
        sudden_drop_ratio=base.sudden_drop_ratio, sources=base.sources,
        notify_min_score=base.notify_min_score, urgent_min_score=base.urgent_min_score,
        max_price_eur=base.max_price_eur, category_bonus=base.category_bonus,
        keywords=base.keywords, exclusions=base.exclusions, allowed_stores=base.allowed_stores,
    )


def test_bootstrap_new_item_and_no_duplicate(tmp_path: Path):
    repo = SQLiteRepository(tmp_path / "state.db")
    repo.migrate()
    notifier = FakeNotifier()
    scraper = FakeScraper([[listing("1")], [listing("1"), listing("2")], [listing("1"), listing("2")]])
    automation = CashConvertersAutomation(repo, scraper, notifier, config())

    first = automation.run()
    assert first.status == RunStatus.SUCCESS
    assert first.discovered == 0
    assert notifier.sent == []

    second = automation.run()
    assert second.discovered == 1
    assert len(notifier.sent) == 1

    third = automation.run()
    assert third.discovered == 0
    assert len(notifier.sent) == 1


def test_network_failure_preserves_previous_state(tmp_path: Path):
    repo = SQLiteRepository(tmp_path / "state.db")
    repo.migrate()
    scraper = FakeScraper([[listing("1")], httpx.ConnectError("offline")])
    automation = CashConvertersAutomation(repo, scraper, FakeNotifier(), config())
    assert automation.run().status == RunStatus.SUCCESS
    assert automation.run().status == RunStatus.SITE_FAILURE
    assert repo.known_ids("cashconverters", ["1"]) == {"1"}


def test_parser_failure_is_explicit(tmp_path: Path):
    repo = SQLiteRepository(tmp_path / "state.db")
    repo.migrate()
    automation = CashConvertersAutomation(
        repo, FakeScraper([ParserFailure("selector disappeared")]), FakeNotifier(), config()
    )
    assert automation.run().status == RunStatus.PARSER_FAILURE


def test_sudden_empty_scan_does_not_erase_state(tmp_path: Path):
    repo = SQLiteRepository(tmp_path / "state.db")
    repo.migrate()
    initial = [listing(str(i)) for i in range(20)]
    automation = CashConvertersAutomation(repo, FakeScraper([initial, [listing("1")]]), FakeNotifier(), config())
    assert automation.run().status == RunStatus.SUCCESS
    assert automation.run().status == RunStatus.SITE_FAILURE
    assert len(repo.known_ids("cashconverters", [str(i) for i in range(20)])) == 20
