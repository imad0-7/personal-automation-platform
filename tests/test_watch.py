import json
from dataclasses import replace

import httpx

from automation_platform.core.database.sqlite import SQLiteRepository
from automation_platform.core.http import HttpClient
from automation_platform.core.models import Notification
from automation_platform.integrations.telegram import TelegramNotifier
from automations.cashconverters.config import CashConvertersConfig
from automations.cashconverters.watch import refresh_watch


def test_watch_lifecycle_and_telegram_first_line(tmp_path):
    config = CashConvertersConfig.load()
    assert '1278034-' in config.watched_url
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    statuses = iter(['reserved', 'free', 'timeout', 404, 404])
    messages, queued, requests = [], [], []

    def handler(request):
        if request.method == 'POST':
            messages.append(json.loads(request.content)['text'])
            return httpx.Response(200, json={'ok': True})
        requests.append(request.url)
        state = next(statuses)
        if state == 'timeout':
            raise httpx.ReadTimeout('timeout', request=request)
        if isinstance(state, int):
            return httpx.Response(state)
        product = json.dumps({'id_product': 1278034, 'name': 'RTX 3090 Ti'})
        disabled = 'disabled' if state == 'reserved' else ''
        return httpx.Response(200, text=(
            f"<div id='product-details' data-product='{product}'></div>"
            f'<button class="add-to-cart" data-button-action="add-to-cart" {disabled}>'
            'Réserver</button>'))

    with HttpClient(transport=httpx.MockTransport(handler)) as client:
        notifier = TelegramNotifier('fake-token', '42', client)
        for expected in ('Réservé —', 'Non réservé —', 'État non vérifié —',
                         'État non vérifié —', 'Article disparu —'):
            prefix = refresh_watch(repo, client, config, lambda k, n: queued.append(n))
            assert prefix.startswith(expected)
            notifier.notify(Notification('Rapport', 'Corps', metadata={'telegram_prefix': prefix}))
            assert messages[-1].startswith(expected)
        # Removal is persistent and stops further requests and repeated final alerts.
        assert refresh_watch(repo, client, config, lambda k, n: queued.append(n)) is None
    assert len(requests) == 5
    assert len(queued) == 5
    assert all('💰💰💰' in n.title for n in queued[:4])
    assert queued[-1].title == 'FIN DU SUIVI'
    repo.close()


def test_outages_and_unrecognized_pages_do_not_stop_watch(tmp_path):
    config = replace(CashConvertersConfig.load(), watched_title='GPU')
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    responses = iter([404, 503, 404, 200, 404])
    queued = []

    def handler(request):
        return httpx.Response(next(responses), text='<html>unrecognized page</html>')

    with HttpClient(transport=httpx.MockTransport(handler)) as client:
        for _ in range(5):
            assert refresh_watch(repo, client, config, lambda k, n: queued.append(n)).startswith(
                'État non vérifié')
    assert not queued
    repo.close()


def test_watch_prefix_applies_to_outbox_even_when_catalogue_fails(tmp_path):
    from test_service import FakeNotifier, FakeScraper, config

    from automations.cashconverters.parser import ParserFailure
    from automations.cashconverters.service import CashConvertersAutomation

    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    notifier = FakeNotifier()
    scraper = FakeScraper([ParserFailure('catalogue down')])
    watched = replace(config(), watched_url=CashConvertersConfig.load().watched_url)
    page = ("<div id='product-details' data-product='{\"id_product\":1278034}'></div>"
            '<button class="add-to-cart" data-button-action="add-to-cart" disabled></button>')
    repo.queue_event('cashconverters', 'pending-command', Notification('ALFRED', 'Reply'))
    with HttpClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=page))) as client:
        scraper.http = client
        CashConvertersAutomation(repo, scraper, notifier, watched).run()
    assert notifier.sent[0].metadata['telegram_prefix'].startswith('Réservé —')
    repo.close()


def test_four_alerts_per_availability_episode_without_scan_duplicates(tmp_path):
    config = CashConvertersConfig.load()
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    states = iter([True, True, False, True, True])
    queued = []

    def handler(request):
        disabled = '' if next(states) else 'disabled'
        return httpx.Response(200, text=(
            "<div id='product-details' data-product='{\"id_product\":1278034}'></div>"
            f'<button class="add-to-cart" data-button-action="add-to-cart" {disabled}></button>'))

    with HttpClient(transport=httpx.MockTransport(handler)) as client:
        for expected_count in [4, 4, 4, 8, 8]:
            refresh_watch(repo, client, config, lambda k, n: queued.append((k, n)))
            assert len(queued) == expected_count
    assert len({key for key, _ in queued}) == 8
    assert all('💰💰💰' in n.title for _, n in queued)
    repo.close()
