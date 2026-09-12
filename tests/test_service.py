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


def offer_listing(external_id: str, price_cents: int = 69900) -> Listing:
    item = listing(external_id, "PC Ryzen 5 5600X RTX 5060 2x16G")
    item.price_cents = price_cents
    item.attributes["reservable"] = True
    return item


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
    assert any(x.title == "COMPTE RENDU CASH CONVERTERS" for x in notifier.sent)
    count_after_second = len(notifier.sent)

    third = automation.run()
    assert third.discovered == 0
    assert not any(x.title == "NOUVEL ORDINATEUR" for x in notifier.sent)
    # A daily clarification may be emitted after noon; no duplicate listing alert is created.
    assert len([x for x in notifier.sent
                if x.title == "COMPTE RENDU CASH CONVERTERS" and "1 nouveaux" in x.message]) == 1
    assert len(notifier.sent) >= count_after_second


def test_network_failure_preserves_previous_state(tmp_path: Path):
    repo = SQLiteRepository(tmp_path / "state.db")
    repo.migrate()
    scraper = FakeScraper([[listing("1")], httpx.ConnectError("offline")])
    notifier = FakeNotifier()
    automation = CashConvertersAutomation(repo, scraper, notifier, config())
    assert automation.run().status == RunStatus.SUCCESS
    assert automation.run().status == RunStatus.SITE_FAILURE
    assert any(x.title == "ALERTE TECHNIQUE CASH CONVERTERS" for x in notifier.sent)
    assert repo.known_ids("cashconverters", ["1"]) == {"1"}


def test_recovery_notification_after_site_failure(tmp_path: Path):
    repo = SQLiteRepository(tmp_path / "state.db")
    repo.migrate()
    notifier = FakeNotifier()
    scraper = FakeScraper([[listing("1")], httpx.ConnectError("offline"), [listing("1")]])
    automation = CashConvertersAutomation(repo, scraper, notifier, config())
    automation.run()
    automation.run()
    automation.run()
    assert len([x for x in notifier.sent if x.title == "ALERTE TECHNIQUE CASH CONVERTERS"]) == 1
    assert len([x for x in notifier.sent if x.title == "SITE RÉTABLI"]) == 1


def test_offer_is_immediate_and_not_duplicated(tmp_path: Path):
    repo = SQLiteRepository(tmp_path / "state.db")
    repo.migrate()
    notifier = FakeNotifier()
    scraper = FakeScraper([[listing("1")], [listing("1"), offer_listing("2")],
                           [listing("1"), offer_listing("2")]])
    automation = CashConvertersAutomation(repo, scraper, notifier, config())
    automation.run()
    automation.run()
    automation.run()
    offers = [x for x in notifier.sent if x.title == "OFFRE À EXAMINER"]
    assert len(offers) == 1
    assert "réservation possible" in offers[0].message


def test_price_drop_can_turn_known_pc_into_offer(tmp_path: Path):
    repo = SQLiteRepository(tmp_path / "state.db")
    repo.migrate()
    notifier = FakeNotifier()
    expensive = listing("1", "PC Ryzen 5 7600")
    expensive.price_cents = 130000
    discounted = listing("1", "PC Ryzen 5 7600")
    discounted.price_cents = 119900
    automation = CashConvertersAutomation(
        repo, FakeScraper([[expensive], [discounted]]), notifier, config()
    )
    automation.run()
    repo.set_state("cashconverters-v2", "last_price_scan", 0)
    automation.run()
    offers = [x for x in notifier.sent if x.title == "OFFRE À EXAMINER"]
    assert len(offers) == 1
    assert "AM5 à 1 200 € maximum" in offers[0].message


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
