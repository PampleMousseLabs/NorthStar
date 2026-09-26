"""
NorthStar SEC XBRL concept mapping.

Income statement backbone, top to bottom.
Evidence: 100-company CompanyFacts waterfall + presentation roles + filing checks
(XOM 0000034088-26-000045, JPM 0001628280-26-008131, BAC 0000070858-26-000157,
PRU 0001137774-26-000048).

All income statement metrics, including EPS and weighted-average shares, are
DURATION facts and use the 330-370 day annual filter.

SEC CompanyFacts unit keys:
    monetary amounts   -> "USD"
    per-share amounts  -> "USD/shares"
    share counts       -> "shares"
"""

from typing import Dict, List, Tuple

Concept = Tuple[str, str]

ANNUAL_FORMS = ["10-K", "10-K/A", "20-F", "20-F/A"]


def _annual(concepts, units, industry_overrides=None) -> dict:
    return {
        "default_concepts": concepts,
        "industry_overrides": industry_overrides or {},
        "units": units,
        "forms": ANNUAL_FORMS,
        "duration_days_min": 330,
        "duration_days_max": 370,
    }


_EXPLICIT_XBRL_ALIASES: Dict[str, dict] = {
    "revenue": _annual(
        [
            ("us-gaap", "Revenues"),
            ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
            # Evidence: ARE FY2025 (REIT) reports only the IncludingAssessedTax variant
            ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
            ("us-gaap", "RegulatedAndUnregulatedOperatingRevenue"),
            ("us-gaap", "SalesRevenueNet"),
            ("us-gaap", "OperatingRevenues"),
        ],
        ["USD"],
        {
            "bank": [
                ("us-gaap", "Revenues"),
                ("us-gaap", "RevenuesNetOfInterestExpense"),
                ("us-gaap", "InterestIncomeExpenseNet"),
                ("us-gaap", "NoninterestIncome"),
            ],
            "reit": [
                ("us-gaap", "Revenues"),
                ("us-gaap", "RealEstateRevenueNet"),
                ("us-gaap", "OperatingLeasesIncomeStatementLeaseRevenue"),
            ],
            "utility": [
                ("us-gaap", "RegulatedAndUnregulatedOperatingRevenue"),
                ("us-gaap", "Revenues"),
            ],
        },
    ),
    "cogs": _annual(
        [
            ("us-gaap", "CostOfGoodsAndServicesSold"),
            ("us-gaap", "CostOfRevenue"),
            ("us-gaap", "CostOfGoodsSold"),
            ("us-gaap", "CostOfServices"),
        ],
        ["USD"],
    ),
    "gross_profit": _annual([("us-gaap", "GrossProfit")], ["USD"]),
    "sga": _annual([("us-gaap", "SellingGeneralAndAdministrativeExpense")], ["USD"]),
    "rd": _annual([("us-gaap", "ResearchAndDevelopmentExpense")], ["USD"]),
    "operating_expenses": _annual([("us-gaap", "OperatingExpenses")], ["USD"]),
    "depreciation_amortization": _annual(
        [
            ("us-gaap", "DepreciationDepletionAndAmortization"),
            ("us-gaap", "DepreciationAndAmortization"),
            ("us-gaap", "AmortizationOfIntangibleAssets"),
        ],
        ["USD"],
    ),
    "operating_income": _annual(
        [("us-gaap", "OperatingIncomeLoss")],
        ["USD"],
        {"bank": []},
    ),
    "interest_expense": _annual(
        [
            ("us-gaap", "InterestExpense"),
            ("us-gaap", "InterestExpenseDebt"),
        ],
        ["USD"],
    ),
    "other_income": _annual(
        [
            ("us-gaap", "OtherNonoperatingIncomeExpense"),
            ("us-gaap", "NonoperatingIncomeExpense"),
        ],
        ["USD"],
    ),
    "pretax_income": _annual(
        [
            ("us-gaap", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"),
            ("us-gaap", "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"),
            ("us-gaap", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"),
        ],
        ["USD"],
    ),
    "pretax_income_domestic": _annual(
        # Component. Used to derive pretax when no consolidated pretax tag exists.
        # Evidence: BNY FY2025 4,431 + 2,627 = 7,058 = ProfitLoss 5,583 + tax 1,475
        [("us-gaap", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic")],
        ["USD"],
    ),
    "pretax_income_foreign": _annual(
        [("us-gaap", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign")],
        ["USD"],
    ),
    "taxes": _annual([("us-gaap", "IncomeTaxExpenseBenefit")], ["USD"]),
    "equity_method_earnings": _annual(
        # Bridge line between pretax_income and net_income_incl_nci.
        # Evidence (exact match): ALB 243.7M, AMZN -554.0M, APTV -38.0M, AMCR 5.0M
        [("us-gaap", "IncomeLossFromEquityMethodInvestments")],
        ["USD"],
    ),
    "discontinued_operations": _annual(
        # Bridge line between pretax_income and net_income_incl_nci.
        # Including-NCI concept first, since the bridge targets income incl. NCI.
        # Evidence (exact match): BG -3.0M, CARR 29.0M (NetOfTax);
        #                         AMD 66.0M, APP -99.4M (AttributableToReportingEntity);
        #                         APD -8.0M (both)
        [
            ("us-gaap", "IncomeLossFromDiscontinuedOperationsNetOfTax"),
            ("us-gaap", "IncomeLossFromDiscontinuedOperationsNetOfTaxAttributableToReportingEntity"),
        ],
        ["USD"],
    ),
    "net_income_incl_nci": _annual(
        # Evidence: XOM FY2025 41,268 - 11,504 = 29,764 (ProfitLoss)
        # Evidence: ACN FY2025 10,270.4 - 2,438.0 = 7,832.4 (ContinuingOperations...IncludingPortion)
        [
            ("us-gaap", "ProfitLoss"),
            ("us-gaap", "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest"),
            ("us-gaap", "NetIncomeLoss"),
        ],
        ["USD"],
    ),
    "minority_interest": _annual(
        # Evidence: XOM FY2025 = 920. Can be negative (NEE tax equity).
        [
            ("us-gaap", "NetIncomeLossAttributableToNoncontrollingInterest"),
            ("us-gaap", "NetIncomeLossAttributableToNonredeemableNoncontrollingInterest"),
            ("us-gaap", "NetIncomeLossAttributableToRedeemableNoncontrollingInterest"),
            ("us-gaap", "MinorityInterestInNetIncomeLossOperatingPartnerships"),
        ],
        ["USD"],
    ),
    "net_income": _annual(
        [
            ("us-gaap", "NetIncomeLoss"),
            ("us-gaap", "ProfitLoss"),
        ],
        ["USD"],
    ),
    "eps_basic": _annual([("us-gaap", "EarningsPerShareBasic")], ["USD/shares"]),
    "eps_diluted": _annual([("us-gaap", "EarningsPerShareDiluted")], ["USD/shares"]),
    "shares_basic": _annual(
        [("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic")],
        ["shares"],
    ),
    "shares_diluted": _annual(
        [("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding")],
        ["shares"],
    ),
}


def get_xbrl_concepts(metric: str, industry: str | None = None) -> List[Concept]:
    metric_def = _EXPLICIT_XBRL_ALIASES.get(metric)
    if not metric_def:
        return []
    if industry:
        industry_concepts = metric_def.get("industry_overrides", {}).get(industry.lower())
        if industry_concepts is not None:
            return industry_concepts
    return metric_def.get("default_concepts", [])


def get_xbrl_units(metric: str) -> List[str]:
    return _EXPLICIT_XBRL_ALIASES.get(metric, {}).get("units", [])


def get_xbrl_forms(metric: str) -> List[str]:
    return _EXPLICIT_XBRL_ALIASES.get(metric, {}).get("forms", [])


def get_duration_bounds(metric: str) -> tuple[int, int] | None:
    metric_def = _EXPLICIT_XBRL_ALIASES.get(metric, {})
    minimum = metric_def.get("duration_days_min")
    maximum = metric_def.get("duration_days_max")
    if minimum is not None and maximum is not None:
        return (minimum, maximum)
    return None
