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
    assert 'Heures d’ajout' in page
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
