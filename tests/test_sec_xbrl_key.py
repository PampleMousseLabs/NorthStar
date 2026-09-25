"""
NorthStar SEC XBRL key tests.

Assertions reflect evidence from the 10-company research sample
(Dev_tools/xbrl). When the dictionary changes on new evidence, update the
evidence notes here alongside the assertions.
"""

from northstar.data.transforms.sec_xbrl_key import (
    get_duration_bounds,
    get_xbrl_concepts,
    get_xbrl_forms,
    get_xbrl_units,
)


def test_revenue_default_chain():
    concepts = get_xbrl_concepts("revenue")

    # Evidence: 'Revenues' is the consolidated top line for JPM, BAC, PLD, O,
    # MET, PRU in companyfacts. Evaluating the ASC 606 tag first understated
    # MET (2.4B vs 77.1B). The broad total must lead the chain.
    assert concepts[0] == ("us-gaap", "Revenues")
    assert ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax") in concepts

    # Evidence: NEE FY2025 10-K (0000753308-26-000015) presents this concept
    # on CONSOLIDATEDSTATEMENTSOFINCOME; NEE's 'Revenues' history ends FY2012.
    assert ("us-gaap", "RegulatedAndUnregulatedOperatingRevenue") in concepts


def test_revenue_bank_override():
    concepts = get_xbrl_concepts("revenue", industry="bank")

    # Evidence: BAC never reports RevenuesNetOfInterestExpense (JPM only);
    # both JPM and BAC carry 19 annual periods under 'Revenues'.
    assert concepts[0] == ("us-gaap", "Revenues")
    assert ("us-gaap", "RevenuesNetOfInterestExpense") in concepts


def test_revenue_utility_override():
    concepts = get_xbrl_concepts("revenue", industry="utility")
    assert concepts[0] == ("us-gaap", "RegulatedAndUnregulatedOperatingRevenue")


def test_revenue_reit_override():
    concepts = get_xbrl_concepts("revenue", industry="reit")
    assert concepts[0] == ("us-gaap", "Revenues")


def test_unknown_metric_and_industry():
    assert get_xbrl_concepts("not_a_metric") == []
    # Unknown industry falls back to the default chain.
    assert get_xbrl_concepts("revenue", industry="widgets") == get_xbrl_concepts("revenue")


def test_revenue_metadata():
    assert "USD" in get_xbrl_units("revenue")
    assert "10-K" in get_xbrl_forms("revenue")
    assert get_duration_bounds("revenue") == (330, 370)
    assert get_duration_bounds("not_a_metric") is None


if __name__ == "__main__":
    test_revenue_default_chain()
    test_revenue_bank_override()
    test_revenue_utility_override()
    test_revenue_reit_override()
    test_unknown_metric_and_industry()
    test_revenue_metadata()
    print("NorthStar SEC XBRL key tests: PASS")
