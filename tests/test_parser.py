from pathlib import Path

import pytest

from automations.cashconverters.parser import ParserFailure, enrich_from_detail, parse_catalog


def test_extracts_real_fields_from_catalog_fixture(fixture_dir: Path):
    item = parse_catalog((fixture_dir / "catalog.html").read_text(), "desktops")[0]
    assert item.external_id == "1234567"
    assert item.price_cents == 69900
    assert item.store == "JETTE"
    assert item.category == "ordinateurs-de-bureau"
    assert item.is_new_badge is True
    assert item.image_url.endswith("large.jpg")
    assert item.attributes["reservable"] is None


def test_enriches_from_prestashop_product_data(fixture_dir: Path):
    item = parse_catalog((fixture_dir / "catalog.html").read_text(), "desktops")[0]
    enrich_from_detail(item, (fixture_dir / "detail.html").read_text())
    assert item.title == "PC Gaming Ryzen 7 + RTX 4070"
    assert item.store == "JETTE"
    assert item.attributes["reference"] == "ABC123"
    assert item.attributes["reservable"] is False
    assert item.attributes["reservation_checked_at"]
    assert item.published_at is not None


@pytest.mark.parametrize("body", ["", "<html><div id='js-product-list'></div></html>", "<html>changed</html>"])
def test_empty_or_changed_structure_is_failure(body: str):
    with pytest.raises(ParserFailure):
        parse_catalog(body, "test")
