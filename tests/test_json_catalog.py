import json
from pathlib import Path

from automations.cashconverters.parser import parse_catalog


def test_accepts_prestashop_json_wrapper(fixture_dir: Path):
    full = (fixture_dir / "catalog.html").read_text()
    fragment = full.split('<div id="js-product-list">', 1)[1].rsplit("</div>", 1)[0]
    payload = json.dumps({"rendered_products": fragment, "rendered_products_top": ""})
    assert parse_catalog(payload, "json-feed")[0].external_id == "1234567"
