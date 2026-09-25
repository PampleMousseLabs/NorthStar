from northstar.data.transforms.sec_xbrl_key import (
    get_xbrl_concepts,
    get_xbrl_units,
    get_xbrl_forms,
    get_duration_bounds,
)


def test_revenue_default_concepts():
    concepts = get_xbrl_concepts("revenue")
    assert ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax") in concepts
    assert ("us-gaap", "Revenues") in concepts


def test_revenue_bank_override():
    concepts = get_xbrl_concepts("revenue", industry="bank")
    assert concepts[0] == ("us-gaap", "RevenuesNetOfInterestExpense")


def test_revenue_reit_override():
    concepts = get_xbrl_concepts("revenue", industry="reit")
    assert ("us-gaap", "Revenues") in concepts


def test_revenue_metadata():
    assert "USD" in get_xbrl_units("revenue")
    assert "10-K" in get_xbrl_forms("revenue")
    assert get_duration_bounds("revenue") == (330, 370)


if __name__ == "__main__":
    test_revenue_default_concepts()
    test_revenue_bank_override()
    test_revenue_reit_override()
    test_revenue_metadata()
    print("NorthStar SEC XBRL key tests: PASS")