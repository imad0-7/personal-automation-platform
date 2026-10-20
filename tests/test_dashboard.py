from automation_platform.core.database.sqlite import SQLiteRepository
from automation_platform.core.models import Listing
from automations.cashconverters.dashboard import build_html


def test_dashboard_escapes_remote_content(tmp_path):
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    repo.save_listings([Listing(source='cashconverters', external_id='1',
        title='<script>alert(1)</script>', url='https://example.test/?a=1&b=2', price_cents=50000)])
    page = build_html(repo)
    assert '<script>alert(1)</script>' not in page
    assert '&lt;script&gt;' in page
    assert '500.00 €' in page
    assert 'Vue d’ensemble' in page
    assert 'À clarifier' in page
    assert 'Nouveautés aujourd’hui' in page
    assert 'Activité du catalogue' in page
    assert 'Dernière nouveauté détectée' in page


def test_dashboard_formats_scan_time_in_brussels_timezone(tmp_path):
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    repo.set_state('cashconverters-v2', 'last_status', {
        'status': 'SUCCESS', 'finished_at': '2026-09-12T20:57:17.942109+00:00',
    })
    page = build_html(repo)
    assert '12 septembre 2026 à 22:57' in page
    assert '2026-09-12T20:57:17.942109+00:00' not in page


def test_dashboard_uses_catalog_rank_not_insertion_order(tmp_path):
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    items = []
    for external_id, rank in [('old', 3), ('newest', 1), ('middle', 2)]:
        item = Listing(source='cashconverters', external_id=external_id,
                       title=external_id, url='https://example.test/' + external_id)
        item.attributes['catalog_rank'] = rank
        items.append(item)
    repo.save_listings(items)
    ordered = repo.recent_listings('cashconverters')
    assert [x.external_id for x in ordered] == ['newest', 'middle', 'old']
    page = build_html(repo)
    assert page.index('>newest</h3>') < page.index('>middle</h3>') < page.index('>old</h3>')


def test_dashboard_excludes_initial_catalogue_from_discoveries(tmp_path):
    from automation_platform.core.models import RunStatus, RunSummary, utc_now

    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    repo.save_listings([Listing(source='cashconverters', external_id='baseline',
        title='Initial', url='https://example.test/initial')])
    run_id = repo.begin_run('cashconverters')
    summary = RunSummary(automation='cashconverters', started_at=utc_now(),
                         finished_at=utc_now(), status=RunStatus.SUCCESS)
    repo.finish_run(run_id, summary)
    assert repo.listing_discoveries('cashconverters', 'cashconverters') == []


def test_dashboard_includes_explicit_discovery(tmp_path):
    from automation_platform.core.models import utc_now

    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    item = Listing(source='cashconverters', external_id='new', title='Nouveau PC',
                   url='https://example.test/new')
    item.attributes['discovered_at'] = utc_now().isoformat()
    repo.save_listings([item])
    page = build_html(repo)
    assert 'Nouveautés aujourd’hui <b>1</b>' in page
    assert 'Détecté à' in page


def test_dashboard_offers_have_independent_filters(tmp_path):
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    item = Listing(source='cashconverters', external_id='deal', title='Ryzen Deal',
                   url='https://example.test/deal', price_cents=40000)
    item.attributes.update({
        'offer_reasons': ['AM4 sous le plafond'],
        'reservable': True,
        'hardware': {'fields': {'platform': {'value': 'AM4'},
                                'cpu': {'value': 'Ryzen 5 5600'},
                                'gpu': {'value': 'RTX 3060'}}},
    })
    repo.save_listings([item])
    page = build_html(repo)
    assert 'id="offers-grid"' in page
    assert 'id="offer-search"' in page
    assert 'id="offer-availability"' in page
    assert 'id="offer-platform"' in page
    assert "setupFilters('#offers-grid'" in page


def test_dashboard_activity_view_uses_scan_activity(tmp_path):
    from datetime import UTC, datetime

    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    repo.record_scan_activity(
        1, 'cashconverters', datetime(2026, 10, 20, 18, 15, tzinfo=UTC),
        356, {'new-a', 'new-b'}, {'old-a'},
    )
    page = build_html(repo)
    assert 'Activité du catalogue' in page
    assert 'Heatmap jour × heure' in page
    assert '"added":2' in page
    assert '"removed":1' in page
    assert '15 min' in page
    assert '30 min' in page
    assert '60 min' in page


def test_dashboard_month_thirds_activity_trend(tmp_path):
    from datetime import UTC, datetime

    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    repo.record_scan_activity(1, 'cashconverters', datetime(2026, 10, 5, 12, 0, tzinfo=UTC), 350, {'a'}, set())
    repo.record_scan_activity(2, 'cashconverters', datetime(2026, 10, 15, 12, 0, tzinfo=UTC), 351, {'b', 'c'}, {'x'})
    repo.record_scan_activity(3, 'cashconverters', datetime(2026, 10, 25, 12, 0, tzinfo=UTC), 352, {'d'}, {'y', 'z'})
    page = build_html(repo)
    assert 'Tendance dans le mois' in page
    assert '1er tiers' in page
    assert '2e tiers' in page
    assert '3e tiers' in page
    assert 'changements / jour observé' in page
