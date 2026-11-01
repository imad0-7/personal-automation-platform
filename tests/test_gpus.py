import json

import httpx
import pytest

from automation_platform.core.database.sqlite import SQLiteRepository
from automation_platform.core.http import HttpClient
from automation_platform.core.models import Listing
from automations.cashconverters.config import CashConvertersConfig
from automations.cashconverters.gpus import GPU_STATE, discover_gpus, gpu_model
from automations.cashconverters.parser import ParserFailure
from automations.cashconverters.watch import WATCH_STATE, refresh_watches, watch_command


def card(ident='1', title='Carte graphique MSI RTX 5070 Ti 16GB'):
    return Listing('cashconverters', ident, title,
                   f'https://www.cashconverters.be/fr/accessoires-informatique/{ident}-gpu.html',
                   price_cents=49900, store='JETTE', category='accessoires-informatique',
                   attributes={'reservable': True})


@pytest.mark.parametrize('model', CashConvertersConfig.load().gpu_models)
@pytest.mark.parametrize('suffix', ['', 'Ti', ' Super', ' Ti Super'])
def test_target_models_and_variants(model, suffix):
    assert gpu_model(card(title=f'MSI RTX{model}{suffix} 16GB'),
                     CashConvertersConfig.load().gpu_models) is not None


@pytest.mark.parametrize('title', ['PC Gamer RTX 4090', 'Portable RTX 5090',
                                  'Support carte graphique RTX 5070', 'RTX 3060 12GB',
                                  'RTX 50700', 'Câble RTX 4080', 'Boîte RTX 3090'])
def test_ignores_computers_accessories_and_other_models(title):
    assert gpu_model(card(title=title), CashConvertersConfig.load().gpu_models) is None


def test_gpu_discovery_baseline_new_dedup_and_preserves_state_on_failure(tmp_path):
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    config = CashConvertersConfig.load()
    queued = []

    class Scraper:
        def __init__(self):
            self.result = [card('1')]

        def collect(self, **kwargs):
            if isinstance(self.result, Exception):
                raise self.result
            return self.result

    scraper = Scraper()
    ns = 'subscriber:test:cashconverters'
    queue = lambda k, n: queued.append((k, n))
    discover_gpus(repo, None, config, ns, queue, scraper)
    assert not queued
    assert repo.state(ns, 'watches')['1']['silent_initial']
    scraper.result = [card('1'), card('2'), card('3', 'PC Gamer RTX 4090')]
    discover_gpus(repo, None, config, ns, queue, scraper)
    discover_gpus(repo, None, config, ns, queue, scraper)
    assert len(queued) == 1
    assert '16 Go' in queued[0][1].message
    assert len(repo.state(ns, 'watches')) == 2
    scraper.result = ParserFailure('broken category')
    with pytest.raises(ParserFailure):
        discover_gpus(repo, None, config, ns, queue, scraper)
    assert repo.state(GPU_STATE, 'baseline') is True
    assert len(repo.state(ns, 'watches')) == 2
    watch_command(repo, ns, '/arreter 2')
    scraper.result = [card('2')]
    discover_gpus(repo, None, config, ns, queue, scraper)
    assert '2' not in repo.state(ns, 'watches')
    repo.close()


def detail(price=500, reserved=False):
    product = json.dumps({'id_product': 1, 'name': 'GPU <MSI>', 'price_amount': price})
    return (f"<div id='product-details' data-product='{product}'></div>"
            '<button class="add-to-cart" data-button-action="add-to-cart" '
            + ('disabled' if reserved else '') + '>Réserver</button>')


def test_price_list_changes_both_directions_and_automatic_removal(tmp_path):
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    config = CashConvertersConfig.load()
    ns, url = 'subscriber:test', card().url
    assert 'ajouté' in watch_command(repo, ns, '/prix ' + url)
    responses = iter([detail(500), detail(450), detail(450), detail(500), 404, 404])
    queued = []

    def handler(request):
        result = next(responses)
        return httpx.Response(result) if isinstance(result, int) else httpx.Response(200, text=result)

    with HttpClient(transport=httpx.MockTransport(handler)) as client:
        for _ in range(6):
            refresh_watches(repo, client, config, ns, lambda k, n: queued.append((k, n)))
        assert refresh_watches(repo, client, config, ns, lambda k, n: queued.append((k, n))) is None
    assert len(queued) == 3
    assert '500.00 → 450.00' in queued[0][1].message
    assert '450.00 → 500.00' in queued[1][1].message
    assert '&lt;MSI&gt;' in queued[0][1].message
    assert queued[-1][1].metadata['watch_final']
    assert not repo.state(ns, 'watches')
    assert 'Aucun article' in watch_command(repo, ns, '/prix')
    repo.close()


def test_all_watches_are_removed_only_after_two_missing_checks(tmp_path):
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    config = CashConvertersConfig.load()
    ns, url = 'subscriber:test', card().url
    watch_command(repo, ns, '/suivre ' + url)
    watch_command(repo, ns, '/prix ' + url)
    statuses = iter([404, 503, 404, 404])
    queued = []
    with HttpClient(transport=httpx.MockTransport(lambda r: httpx.Response(next(statuses)))) as client:
        for _ in range(3):
            refresh_watches(repo, client, config, ns, lambda k, n: queued.append(n))
            assert repo.state(ns, 'watches')
        refresh_watches(repo, client, config, ns, lambda k, n: queued.append(n))
    assert not repo.state(ns, 'watches')
    assert len(queued) == 1
    assert queued[0].metadata['watch_final']
    repo.close()


def test_gpu_available_alert_is_single_but_can_be_pinned_for_four(tmp_path):
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    config = CashConvertersConfig.load()
    ns, url = 'subscriber:test', card().url
    repo.set_state(ns, 'watches', {'1': {'url': url, 'title': 'GPU', 'origin': 'gpu',
                   'price': True, 'reservation': True, 'burst': False, 'prefix': False}})
    responses = iter([detail(reserved=True), detail(), detail(), detail()])
    queued = []
    with HttpClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=next(responses)))) as client:
        for _ in range(3):
            refresh_watches(repo, client, config, ns, lambda k, n: queued.append(n))
        assert len(queued) == 1
        assert 'ajouté' in watch_command(repo, ns, '/suivre ' + url)
        refresh_watches(repo, client, config, ns, lambda k, n: queued.append(n))
    assert len(queued) == 5
    assert repo.state(WATCH_STATE, url)['reservable'] is True
    repo.close()


def test_gpu_in_wrong_shop_category_is_still_detected():
    item = card(title='Carteb Graphique *NEUF* Gygabite RTX4060')
    item.category = 'pda'
    assert gpu_model(item, CashConvertersConfig.load().gpu_models) == 'RTX 4060'
    item.category = 'ordinateurs-de-bureau'
    assert gpu_model(item, CashConvertersConfig.load().gpu_models) is None


def test_final_removal_notification_retries_after_registry_deletion(tmp_path):
    from test_service import FakeNotifier, FakeScraper, config, listing

    from automations.cashconverters.service import CashConvertersAutomation

    class Notifier(FakeNotifier):
        fail = True

        def notify(self, notification):
            if self.fail:
                self.fail = False
                raise RuntimeError('Telegram unavailable')
            super().notify(notification)

    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    notifier = Notifier()
    ns = 'subscriber:local:cashconverters'
    watch_command(repo, ns, '/prix ' + card().url)
    scraper = FakeScraper([[listing('9')], [listing('9')], [listing('9')]])
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(404)

    with HttpClient(transport=httpx.MockTransport(handler)) as client:
        scraper.http = client
        automation = CashConvertersAutomation(repo, scraper, notifier, config())
        automation.run()
        automation.run()
        assert not repo.state(ns, 'watches')
        assert any(n.metadata.get('watch_final') for _, n in repo.pending_notifications('cashconverters'))
        automation.run()
    assert len(requests) == 2
    assert sum(bool(n.metadata.get('watch_final')) for n in notifier.sent) == 1
    repo.close()


def test_bulk_price_urls_are_validated_before_mutating_list(tmp_path):
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    ns = 'subscriber:test'
    answer = watch_command(repo, ns, '/prix ' + card().url + ' https://evil.test/item')
    assert 'invalide' in answer
    assert not repo.state(ns, 'watches', {})
    answer = watch_command(repo, ns, '/prix ' + card('1').url + ' ' + card('2').url)
    assert 'ajouté' in answer
    assert len(repo.state(ns, 'watches')) == 2
    repo.close()
