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
    assert not any(x.title == "ALERTE TECHNIQUE CASH CONVERTERS" for x in notifier.sent)
    assert repo.known_ids("cashconverters", ["1"]) == {"1"}


def test_recovery_notification_after_site_failure(tmp_path: Path):
    repo = SQLiteRepository(tmp_path / "state.db")
    repo.migrate()
    notifier = FakeNotifier()
    scraper = FakeScraper([[listing("1")], httpx.ConnectError("offline"),
                           httpx.ConnectError("offline"), [listing("1")]])
    automation = CashConvertersAutomation(repo, scraper, notifier, config())
    automation.run()
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


def test_scan_activity_tracks_additions_and_removals_even_when_total_is_stable(tmp_path: Path):
    repo = SQLiteRepository(tmp_path / "state.db")
    repo.migrate()
    first_batch = [listing(str(i)) for i in range(1, 5)]
    second_batch = [listing("1"), listing("2"), listing("5"), listing("6")]
    automation = CashConvertersAutomation(
        repo, FakeScraper([first_batch, second_batch]), FakeNotifier(), config()
    )

    assert automation.run().status == RunStatus.SUCCESS
    repo.set_state('cashconverters-v2', 'last_full_scan', 0)
    assert automation.run().status == RunStatus.SUCCESS

    activity = repo.scan_activity("cashconverters")
    assert len(activity) == 2
    assert activity[0]["added_count"] == 0
    assert activity[0]["removed_count"] == 0
    assert activity[1]["total_count"] == 4
    assert activity[1]["added_count"] == 2
    assert activity[1]["removed_count"] == 2


def test_unresolved_detail_is_retried_without_manual_input(tmp_path: Path):
    class ClarifyingScraper(FakeScraper):
        def __init__(self, batches):
            super().__init__(batches)
            self.enrich_calls = 0

        def enrich(self, item):
            self.enrich_calls += 1
            if self.enrich_calls >= 2:
                item.attributes["description"] = "Ryzen 5 7600 RTX 4070 RAM 32GB SSD 1TB"
            return item

    repo = SQLiteRepository(tmp_path / "state.db")
    repo.migrate()
    notifier = FakeNotifier()
    scraper = ClarifyingScraper([
        [listing("1", "PC gamer")],
        [listing("1", "PC gamer")],
        [listing("1", "PC gamer")],
    ])
    automation = CashConvertersAutomation(repo, scraper, notifier, config())

    automation.run()  # baseline
    automation.run()  # first detail enrichment, still unclear

    stored = repo.get_listing("cashconverters", "1")
    assert stored is not None
    stored.attributes["detail_checked_at"] = "2020-01-01T00:00:00+00:00"
    repo.save_listings([stored])

    automation.run()  # automatic clarification retry
    clarified = repo.get_listing("cashconverters", "1")
    assert clarified is not None
    fields = clarified.attributes["hardware"]["fields"]
    assert fields["cpu"]["value"] == "Ryzen 5 7600"
    assert fields["gpu"]["value"] == "RTX 4070"
    assert fields["ram_gb"]["value"] == 32


def test_optional_detail_timeout_is_silent_and_retried_later(tmp_path):
    class FailingDetails(FakeScraper):
        calls = 0

        def enrich(self, item):
            self.calls += 1
            item.title = 'damaged'
            raise httpx.ReadTimeout('slow detail')

    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    notifier = FakeNotifier()
    scraper = FailingDetails([[listing('1')], [listing('1')], [listing('1')]])
    automation = CashConvertersAutomation(repo, scraper, notifier, config())
    automation.run()
    assert automation.run().status == RunStatus.SUCCESS
    saved = repo.get_listing('cashconverters', '1')
    assert saved.title != 'damaged'
    assert saved.attributes['detail_failures'] == 1
    automation.run()
    assert scraper.calls == 1
    assert not any(n.title in {'CONTRÔLE PARTIEL', 'QUESTIONS MATÉRIEL'} for n in notifier.sent)


def test_reservation_changes_only_on_periodic_refresh(tmp_path):
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    batches = []
    for value in (True, False, False):
        item = listing('1')
        item.attributes.update(reservable=value, reservation_checked_at=str(value))
        batches.append([item])
    automation = CashConvertersAutomation(repo, FakeScraper(batches), FakeNotifier(), config())
    automation.run()
    automation.run()
    assert repo.get_listing('cashconverters', '1').attributes['reservable'] is True
    repo.set_state('cashconverters-v2', 'last_price_scan', 0)
    automation.run()
    assert repo.get_listing('cashconverters', '1').attributes['reservable'] is False


def test_partial_catalogue_does_not_remove_unvisited_listings(tmp_path):
    from automations.cashconverters.scraper import CashConvertersScraper

    class PartialScraper(CashConvertersScraper):
        def __init__(self):
            self.http = FakeHttp()
            self.flags = []

        def collect(self, *, full=False, **kwargs):
            self.flags.append(full)
            return [listing('1'), listing('2')] if full else [listing('1')]

        def enrich(self, item):
            return item

    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    scraper = PartialScraper()
    automation = CashConvertersAutomation(repo, scraper, FakeNotifier(), config())
    automation.run()
    automation.run()
    assert scraper.flags == [True, False]
    assert repo.state('cashconverters-v2', 'active_catalog') == ['1', '2']
    assert repo.scan_activity('cashconverters')[-1]['removed_count'] == 0
