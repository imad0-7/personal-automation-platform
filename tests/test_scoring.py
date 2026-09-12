from automation_platform.core.models import Listing
from automations.cashconverters.config import CashConvertersConfig
from automations.cashconverters.scoring import score_listing


def test_deterministic_scoring_detects_pc_terms():
    cfg = CashConvertersConfig.load()
    item = Listing(
        source="cashconverters", external_id="1", title="PC Gaming Ryzen 7 RTX 4070",
        url="https://example.test/1", price_cents=69900, category="ordinateurs de bureau",
    )
    score_listing(item, cfg)
    assert item.score >= cfg.urgent_min_score
    assert "RYZEN" in item.score_reasons
    assert "RTX" in item.score_reasons


def test_accessory_exclusion_reduces_score():
    cfg = CashConvertersConfig.load()
    item = Listing(
        source="cashconverters", external_id="2", title="Housse PC Gaming ROG",
        url="https://example.test/2", price_cents=2000,
    )
    score_listing(item, cfg)
    assert item.score < cfg.notify_min_score
