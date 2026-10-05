from northstar.data.transforms.sec_xbrl_key import (
    get_duration_bounds,
    get_xbrl_concepts,
    get_xbrl_forms,
    get_xbrl_units,
)

FULL_IS_METRICS = (
    "revenue", "cogs", "gross_profit", "sga", "rd",
    "operating_expenses", "depreciation_amortization",
    "operating_income", "interest_expense", "other_income",
    "pretax_income", "taxes",
    "equity_method_earnings", "discontinued_operations",
    "net_income_incl_nci", "minority_interest", "net_income",
    "net_income_to_common",
    "comprehensive_income", "goodwill_impairment", "restructuring_charges",
    "debt_extinguishment", "asset_impairment", "income_from_continuing_ops",
    "costs_and_expenses", "ga_expense", "preferred_dividends",
    "eps_basic", "eps_diluted", "shares_basic", "shares_diluted",
)


def test_top_half_keys_exist():
    assert get_xbrl_concepts("cogs")[0] == ("us-gaap", "CostOfGoodsAndServicesSold")
    assert get_xbrl_concepts("gross_profit")[0] == ("us-gaap", "GrossProfit")
    assert get_xbrl_concepts("sga")[0] == ("us-gaap", "SellingGeneralAndAdministrativeExpense")
    assert get_xbrl_concepts("rd")[0] == ("us-gaap", "ResearchAndDevelopmentExpense")
    assert get_xbrl_concepts("operating_expenses")[0] == ("us-gaap", "OperatingExpenses")
    assert get_xbrl_concepts("interest_expense")[0] == ("us-gaap", "InterestExpense")
    assert get_xbrl_concepts("eps_basic")[0] == ("us-gaap", "EarningsPerShareBasic")
    assert get_xbrl_concepts("eps_diluted")[0] == ("us-gaap", "EarningsPerShareDiluted")
    assert get_xbrl_concepts("shares_basic")[0] == ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic")
    assert get_xbrl_concepts("shares_diluted")[0] == ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding")


def test_bottom_half_still_correct():
    assert get_xbrl_concepts("revenue")[0] == ("us-gaap", "Revenues")
    assert ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax") in get_xbrl_concepts("revenue")
    # Utility prioritizes Revenues first now (to resolve LNT holding co)
    assert get_xbrl_concepts("revenue", industry="utility")[0] == ("us-gaap", "Revenues")
    assert get_xbrl_concepts("operating_income")[0] == ("us-gaap", "OperatingIncomeLoss")
    assert get_xbrl_concepts("operating_income", industry="bank") == []
    assert get_xbrl_concepts("taxes")[0] == ("us-gaap", "IncomeTaxExpenseBenefit")
    assert get_xbrl_concepts("net_income")[0] == ("us-gaap", "NetIncomeLoss")
    assert get_xbrl_concepts("net_income_incl_nci")[0] == ("us-gaap", "ProfitLoss")


def test_bridge_metrics():
    """Lines between pretax_income and net_income_incl_nci for some companies."""
    assert get_xbrl_concepts("equity_method_earnings")[0] == (
        "us-gaap", "IncomeLossFromEquityMethodInvestments",
    )
    disc = get_xbrl_concepts("discontinued_operations")
    assert disc[0] == ("us-gaap", "IncomeLossFromDiscontinuedOperationsNetOfTax")
    assert ("us-gaap", "IncomeLossFromDiscontinuedOperationsNetOfTaxAttributableToReportingEntity") in disc


def test_metadata():
    for metric in FULL_IS_METRICS:
        assert "10-K" in get_xbrl_forms(metric), metric
        assert get_duration_bounds(metric) == (330, 370), metric
        assert get_xbrl_units(metric)


def test_sec_unit_keys():
    assert get_xbrl_units("revenue") == ["USD"]
    assert get_xbrl_units("equity_method_earnings") == ["USD"]
    assert get_xbrl_units("discontinued_operations") == ["USD"]
    assert get_xbrl_units("eps_basic") == ["USD/shares"]
    assert get_xbrl_units("eps_diluted") == ["USD/shares"]
    assert get_xbrl_units("shares_basic") == ["shares"]
    assert get_xbrl_units("shares_diluted") == ["shares"]


if __name__ == "__main__":
    test_top_half_keys_exist()
    test_bottom_half_still_correct()
    test_bridge_metrics()
    test_metadata()
    test_sec_unit_keys()
    print("NorthStar SEC XBRL key tests: PASS")
