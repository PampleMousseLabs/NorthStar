"""
Validate MO FY2025 income-statement math using filing-level XBRL facts.

Research evidence:
    Gross profit:
        Revenue - COGS - Other Cost of Operating Revenue

    Operating income:
        Gross Profit
        - Marketing / Administration / Research
        - Asset Impairment and Business Exit Costs
        - Goodwill Impairment

This script reads the locally harvested filing facts only.
It makes no SEC network calls and writes no files.
"""

import csv
from decimal import Decimal
from pathlib import Path


FACTS_PATH = Path(
    "Dev_tools/xbrl/runlogs/filing_facts_MO_000076418026000017.csv"
)

START = "2025-01-01"
END = "2025-12-31"

CONCEPTS = {
    "revenue": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    "cogs": "us-gaap:CostOfGoodsAndServicesSold",
    "other_cost_of_operating_revenue": "us-gaap:OtherCostOfOperatingRevenue",
    "gross_profit": "us-gaap:GrossProfit",
    "marketing_admin_research": "mo:MarketingAdministrationandResearchCosts",
    "asset_impairment_business_exit": "mo:AssetImpairmentandBusinessExitCosts",
    "goodwill_impairment": "us-gaap:GoodwillImpairmentLoss",
    "operating_income": "us-gaap:OperatingIncomeLoss",
}


def load_value(concept: str) -> Decimal:
    values = set()

    with FACTS_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["concept"] != concept:
                continue
            if row["period_start"] != START:
                continue
            if row["period_end"] != END:
                continue
            if row["dimension_count"] != "0":
                continue
            if row["unit"] != "USD":
                continue

            values.add(Decimal(row["value"]))

    if not values:
        raise RuntimeError(f"No FY2025 default-context USD fact for {concept}")

    if len(values) != 1:
        raise RuntimeError(
            f"Expected one value for {concept}; found {sorted(values)}"
        )

    return values.pop()


def millions(value: Decimal) -> str:
    return f"{value / Decimal(1_000_000):,.1f}M"


def main() -> None:
    if not FACTS_PATH.exists():
        raise SystemExit(
            f"Missing {FACTS_PATH}. Run harvest_filing_facts.py MO first."
        )

    values = {
        key: load_value(concept)
        for key, concept in CONCEPTS.items()
    }

    calculated_gp = (
        values["revenue"]
        - values["cogs"]
        - values["other_cost_of_operating_revenue"]
    )

    calculated_opinc = (
        values["gross_profit"]
        - values["marketing_admin_research"]
        - values["asset_impairment_business_exit"]
        - values["goodwill_impairment"]
    )

    print("MO FY2025 filing-level XBRL reconciliation")
    print("-" * 62)

    for key, concept in CONCEPTS.items():
        print(f"{key:<36} {millions(values[key]):>12}  {concept}")

    print("\nGross Profit check")
    print(
        f"  Revenue - COGS - Other Operating Cost = {millions(calculated_gp)}"
    )
    print(f"  Reported Gross Profit                 = {millions(values['gross_profit'])}")

    print("\nOperating Income check")
    print(
        f"  GP - Marketing/Admin/R&D - Asset/Exit - Goodwill = "
        f"{millions(calculated_opinc)}"
    )
    print(
        f"  Reported Operating Income                          = "
        f"{millions(values['operating_income'])}"
    )

    if calculated_gp != values["gross_profit"]:
        raise SystemExit("FAIL: Gross Profit does not reconcile.")

    if calculated_opinc != values["operating_income"]:
        raise SystemExit("FAIL: Operating Income does not reconcile.")

    print("\nPASS: MO FY2025 filing-level income statement reconciles exactly.")


if __name__ == "__main__":
    main()
