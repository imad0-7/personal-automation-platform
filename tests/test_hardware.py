from automation_platform.core.models import Listing
from automations.cashconverters.hardware import analyze_listing, extract


def item(title: str, price: int) -> Listing:
    return Listing(source="cashconverters", external_id="x", title=title,
                   url="https://example.test/x", price_cents=price)


def test_glued_am5_configuration_is_conservatively_parsed():
    result = extract("PC Ryzen 5 7500F 2x16g RTX4070SUPER 1To")
    fields = result["fields"]
    assert fields["platform"]["value"] == "AM5"
    assert fields["ram_type"]["value"] == "DDR5"
    assert fields["ram_type"]["kind"] == "inferred"
    assert fields["ram_gb"]["value"] == 32
    assert fields["gpu"]["value"] == "RTX 4070 SUPER"
    assert fields["storage"]["value"][0]["type"] == "inconnu"


def test_am5_offer_threshold_is_explicit():
    listing = item("PC Ryzen 5 7600 32 Go", 120000)
    reasons = analyze_listing(listing)
    assert reasons == ["AM5 à 1 200 € maximum"]


def test_am5_allows_probable_two_by_sixteen_without_unit():
    result = extract("Ryzen 5 7500F 2x16 RTX 4070")
    assert result["fields"]["ram_gb"]["value"] == 32
    assert result["fields"]["ram_type"]["value"] == "DDR5"
    assert result["fields"]["ram_type"]["kind"] == "inferred"


def test_am4_5060_strict_threshold():
    listing = item("PC Ryzen 5 5600X RTX 5060", 69999)
    assert "AM4 + RTX 5060 sous 700 €" in analyze_listing(listing)
    listing.price_cents = 70000
    assert "AM4 + RTX 5060 sous 700 €" not in analyze_listing(listing)


def test_unknown_cpu_is_queued_for_review_not_guessed():
    result = extract("PC gamer 32g 1to carte graphique puissante")
    assert "cpu" not in result["fields"]
    assert "Processeur non identifié" in result["questions"]
