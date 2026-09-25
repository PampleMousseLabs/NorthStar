"""
NorthStar SEC XBRL concept mapping.

Purpose:
    Map NorthStar canonical metrics to candidate SEC XBRL concepts.

Important:
    This is a research-stage mapping and will expand over time.
    Concepts may require industry-specific overrides.
"""

from typing import Dict, List, Tuple

# Concept tuple = (taxonomy, tag)
Concept = Tuple[str, str]

# ------------------------------------------------------------------
# Core concept candidates
# Ordered by preference where known.
# ------------------------------------------------------------------

_EXPLICIT_XBRL_ALIASES: Dict[str, dict] = {
    "revenue": {
        "default_concepts": [
            ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
            ("us-gaap", "Revenues"),
            ("us-gaap", "SalesRevenueNet"),
            ("us-gaap", "OperatingRevenues"),
        ],
        "industry_overrides": {
            "bank": [
                ("us-gaap", "RevenuesNetOfInterestExpense"),
                ("us-gaap", "Revenues"),
                ("us-gaap", "InterestIncomeExpenseNet"),
                ("us-gaap", "NoninterestIncome"),
            ],
            "reit": [
                ("us-gaap", "Revenues"),
                ("us-gaap", "RealEstateRevenueNet"),
                ("us-gaap", "OperatingLeasesIncomeStatementLeaseRevenue"),
            ],
        },
        "units": ["USD"],
        "forms": ["10-K", "10-K/A", "20-F", "20-F/A"],
        "duration_days_min": 330,
        "duration_days_max": 370,
    },
}


def get_xbrl_concepts(metric: str, industry: str | None = None) -> List[Concept]:
    """
    Return preferred SEC XBRL concept candidates for a canonical NorthStar metric.
    """
    metric_def = _EXPLICIT_XBRL_ALIASES.get(metric)
    if not metric_def:
        return []

    if industry:
        industry_concepts = metric_def.get("industry_overrides", {}).get(industry.lower())
        if industry_concepts:
            return industry_concepts

    return metric_def.get("default_concepts", [])


def get_xbrl_units(metric: str) -> List[str]:
    metric_def = _EXPLICIT_XBRL_ALIASES.get(metric, {})
    return metric_def.get("units", [])


def get_xbrl_forms(metric: str) -> List[str]:
    metric_def = _EXPLICIT_XBRL_ALIASES.get(metric, {})
    return metric_def.get("forms", [])


def get_duration_bounds(metric: str) -> tuple[int, int] | None:
    metric_def = _EXPLICIT_XBRL_ALIASES.get(metric, {})
    if "duration_days_min" in metric_def and "duration_days_max" in metric_def:
        return (
            metric_def["duration_days_min"],
            metric_def["duration_days_max"],
        )
    return None