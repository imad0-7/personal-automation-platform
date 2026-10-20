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


def test_catalog_prefers_lazy_loaded_image_url():
    body = """
    <div id="js-product-list">
      <article class="product-miniature" data-id-product="42">
        <a class="product-thumbnail" href="https://www.cashconverters.be/fr/ordinateurs-de-bureau/42-test.html">
          <img src="data:image/gif;base64,placeholder" data-src="https://cdn.example.test/real.jpg">
        </a>
        <h2 class="product-title"><a href="https://www.cashconverters.be/fr/ordinateurs-de-bureau/42-test.html">Test PC</a></h2>
        <span class="price">499,00 €</span>
      </article>
    </div>
    """
    item = parse_catalog(body, "desktops")[0]
    assert item.image_url == "https://cdn.example.test/real.jpg"


def test_catalog_uses_largest_srcset_candidate():
    body = """
    <div id="js-product-list">
      <article class="product-miniature" data-id-product="43">
        <a class="product-thumbnail" href="https://www.cashconverters.be/fr/ordinateurs-de-bureau/43-test.html">
          <img srcset="https://cdn.example.test/small.jpg 320w, https://cdn.example.test/large.jpg 960w">
        </a>
        <h2 class="product-title"><a href="https://www.cashconverters.be/fr/ordinateurs-de-bureau/43-test.html">Test PC 2</a></h2>
        <span class="price">599,00 €</span>
      </article>
    </div>
    """
    item = parse_catalog(body, "desktops")[0]
    assert item.image_url == "https://cdn.example.test/large.jpg"


def test_catalog_normalizes_relative_product_url():
    body = """
    <div id="js-product-list">
      <article class="product-miniature" data-id-product="44">
        <a class="product-thumbnail" href="/fr/ordinateurs-de-bureau/44-test.html">
          <img src="/img/test.jpg">
        </a>
        <h2 class="product-title"><a href="/fr/ordinateurs-de-bureau/44-test.html">Test PC 3</a></h2>
        <span class="price">699,00 €</span>
      </article>
    </div>
    """
    item = parse_catalog(body, "desktops")[0]
    assert item.url == "https://www.cashconverters.be/fr/ordinateurs-de-bureau/44-test.html"
    assert item.image_url == "https://www.cashconverters.be/img/test.jpg"
