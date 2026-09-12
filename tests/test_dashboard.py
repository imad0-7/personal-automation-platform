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
