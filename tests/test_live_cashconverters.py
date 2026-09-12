import pytest

from automation_platform.core.http import HttpClient, HttpPolicy
from automations.cashconverters.parser import enrich_from_detail, parse_catalog


@pytest.mark.live
def test_live_desktop_catalog_contract():
    url = "https://www.cashconverters.be/fr/164-ordinateurs-de-bureau?order=product.date_add.desc"
    with HttpClient(HttpPolicy(timeout_seconds=30, retries=2)) as http:
        listings = parse_catalog(http.get_text(url), "desktops")
        enrich_from_detail(listings[0], http.get_text(listings[0].url))
    assert len(listings) >= 5
    assert all(item.external_id.isdigit() for item in listings)
    assert all(item.url.startswith("https://www.cashconverters.be/") for item in listings)
    assert all(item.attributes["reservable"] in {True, False} for item in listings)
    assert listings[0].attributes["reference"]
    assert listings[0].attributes["reservable"] in {True, False, None}
