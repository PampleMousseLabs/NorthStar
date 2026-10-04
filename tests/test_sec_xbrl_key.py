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


def test_new_face_is_metrics():
    assert get_xbrl_concepts("comprehensive_income")[0] == (
        "us-gaap", "ComprehensiveIncomeNetOfTax",
    )
    assert get_xbrl_concepts("goodwill_impairment")[0] == (
        "us-gaap", "GoodwillImpairmentLoss",
    )
    assert get_xbrl_concepts("restructuring_charges")[0] == (
        "us-gaap", "RestructuringCharges",
    )
    assert get_xbrl_concepts("debt_extinguishment")[0] == (
        "us-gaap", "GainsLossesOnExtinguishmentOfDebt",
    )
    assert get_xbrl_concepts("asset_impairment")[0] == (
        "us-gaap", "AssetImpairmentCharges",
    )
    assert get_xbrl_concepts("income_from_continuing_ops")[0] == (
        "us-gaap", "IncomeLossFromContinuingOperations",
    )
    assert get_xbrl_concepts("costs_and_expenses")[0] == (
        "us-gaap", "CostsAndExpenses",
    )
    assert get_xbrl_concepts("ga_expense")[0] == (
        "us-gaap", "GeneralAndAdministrativeExpense",
    )
    assert get_xbrl_concepts("preferred_dividends")[0] == (
        "us-gaap", "PreferredStockDividendsIncomeStatementImpact",
    )


def test_bottom_half_still_correct():
    assert get_xbrl_concepts("revenue")[0] == ("us-gaap", "Revenues")
    assert get_xbrl_concepts("net_income") == [("us-gaap", "NetIncomeLoss")]
    assert get_xbrl_concepts("net_income_incl_nci")[0] == ("us-gaap", "ProfitLoss")
    assert get_xbrl_concepts("operating_income", industry="bank") == []


def test_metadata():
    for metric in FULL_IS_METRICS:
        assert "10-K" in get_xbrl_forms(metric), metric
        assert get_duration_bounds(metric) == (330, 370), metric
        assert get_xbrl_units(metric)


if __name__ == "__main__":
    test_new_face_is_metrics()
    test_bottom_half_still_correct()
    test_metadata()
    print("NorthStar SEC XBRL key tests: PASS")
