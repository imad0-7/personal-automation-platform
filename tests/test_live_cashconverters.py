import pytest

from automation_platform.core.http import HttpClient, HttpPolicy
from automations.cashconverters.parser import parse_catalog


@pytest.mark.live
def test_live_desktop_catalog_contract():
    url = "https://www.cashconverters.be/fr/164-ordinateurs-de-bureau?order=product.date_add.desc"
    with HttpClient(HttpPolicy(timeout_seconds=30, retries=2)) as http:
        listings = parse_catalog(http.get_text(url), "desktops")
    assert len(listings) >= 5
    assert all(item.external_id.isdigit() for item in listings)
    assert all(item.url.startswith("https://www.cashconverters.be/") for item in listings)
