from automation_platform.core.database.sqlite import SQLiteRepository
from automation_platform.core.models import Listing
from scripts.generate_dashboard import build_html


def test_dashboard_escapes_remote_content(tmp_path):
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    repo.save_listings([Listing(source='cashconverters', external_id='1',
        title='<script>alert(1)</script>', url='https://example.test/?a=1&b=2', price_cents=50000)])
    page = build_html(repo)
    assert '<script>alert(1)</script>' not in page
    assert '&lt;script&gt;' in page
    assert '500.00 €' in page
