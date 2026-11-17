#!/usr/bin/env python3

import csv
import re
from collections import Counter
from pathlib import Path

BASE = Path("Dev_tools/xbrl/runlogs")

INVENTORY_FILE = BASE / "canonical_is_concept_inventory.csv"
CLASSIFICATION_FILE = BASE / "canonical_is_concept_classification.csv"
OUTPUT_FILE = BASE / "canonical_is_taxonomy.csv"

# Only merge concepts where the economic identity is sufficiently clear.
# Keep this list deliberately conservative.
ALIAS_GROUPS = {
    "total_revenue": {
        "us-gaap:Revenues",
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:SalesRevenueNet",
    },
    "cost_of_revenue": {
        "us-gaap:CostOfRevenue",
        "us-gaap:CostOfGoodsAndServicesSold",
    },
    "gross_profit": {
        "us-gaap:GrossProfit",
    },
    "selling_general_and_administrative": {
        "us-gaap:SellingGeneralAndAdministrativeExpense",
    },
    "research_and_development": {
        "us-gaap:ResearchAndDevelopmentExpense",
    },
    "operating_income": {
        "us-gaap:OperatingIncomeLoss",
    },
    "pretax_income": {
        "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    },
    "income_tax_expense_benefit": {
        "us-gaap:IncomeTaxExpenseBenefit",
    },
    "net_income": {
        "us-gaap:NetIncomeLoss",
    },
    "earnings_per_share_basic": {
        "us-gaap:EarningsPerShareBasic",
    },
    "earnings_per_share_diluted": {
        "us-gaap:EarningsPerShareDiluted",
    },
    "weighted_average_shares_basic": {
        "us-gaap:WeightedAverageNumberOfSharesOutstandingBasic",
    },
    "weighted_average_shares_diluted": {
        "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
    },
}

LABELS = {
    "total_revenue": "Total Revenue",
    "cost_of_revenue": "Cost of Revenue",
    "gross_profit": "Gross Profit",
    "selling_general_and_administrative": "Selling, General and Administrative",
    "research_and_development": "Research and Development",
    "operating_income": "Operating Income",
    "pretax_income": "Pretax Income",
    "income_tax_expense_benefit": "Income Tax Expense (Benefit)",
    "net_income": "Net Income",
    "earnings_per_share_basic": "Basic Earnings per Share",
    "earnings_per_share_diluted": "Diluted Earnings per Share",
    "weighted_average_shares_basic": "Weighted Average Shares — Basic",
    "weighted_average_shares_diluted": "Weighted Average Shares — Diluted",
}


def snake_case(value):
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"([A-Z])([A-Z][a-z])", r"\1_\2", value)
    value = re.sub(r"[^A-Za-z0-9]+", "_", value)
    return value.strip("_").lower()


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    inventory = read_csv(INVENTORY_FILE)
    classifications = read_csv(CLASSIFICATION_FILE)

    inventory_by_concept = {r["concept"]: r for r in inventory}
    classification_by_concept = {r["concept"]: r for r in classifications}

    if len(inventory_by_concept) != len(inventory):
        raise SystemExit("Duplicate concepts found in inventory.")

    if len(classification_by_concept) != len(classifications):
        raise SystemExit("Duplicate concepts found in classification.")

    missing = sorted(set(inventory_by_concept) - set(classification_by_concept))
    if missing:
        raise SystemExit(
            f"{len(missing)} inventory concepts lack classifications. "
            f"First examples: {missing[:10]}"
        )

    alias_lookup = {}
    for canonical_id, concepts in ALIAS_GROUPS.items():
        for concept in concepts:
            if concept in alias_lookup:
                raise SystemExit(f"Concept assigned to multiple aliases: {concept}")
            alias_lookup[concept] = canonical_id

    output = []

    for concept, inv in inventory_by_concept.items():
        cls = classification_by_concept[concept]

        if ":" in concept:
            namespace, local_name = concept.split(":", 1)
        else:
            namespace, local_name = "", concept

        canonical_id = alias_lookup.get(concept)

        if canonical_id:
            mapping_method = "curated_alias"
            mapping_status = "curated"
            canonical_label = LABELS[canonical_id]
        else:
            # Unique provisional identity: no unreviewed cross-concept merges.
            canonical_id = (
                f"provisional__{snake_case(namespace)}__{snake_case(local_name)}"
            )
            mapping_method = "source_identity"
            canonical_label = local_name
            if cls["canonical_section"] == "unresolved":
                mapping_status = "unresolved"
            elif cls["canonical_section"] == "context_dependent":
                mapping_status = "context_dependent"
            else:
                mapping_status = "provisional"

        output.append({
            "concept": concept,
            "namespace": namespace,
            "canonical_line_item": canonical_id,
            "canonical_line_item_label": canonical_label,
            "canonical_section": cls["canonical_section"],
            "concept_role": cls["concept_role"],
            "mapping_status": mapping_status,
            "mapping_method": mapping_method,
            "placement_method": cls["placement_method"],
            "strongest_evidence_zone": cls["strongest_evidence_zone"],
            "company_count": inv["company_count"],
            "filing_role_count": inv["filing_role_count"],
            "presentation_count": inv["presentation_count"],
            "evidence_company_count": cls["evidence_company_count"],
            "evidence_group_count": cls["evidence_group_count"],
            "classification_notes": cls["classification_notes"],
        })

    fields = list(output[0].keys())

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)

    methods = Counter(r["mapping_method"] for r in output)
    statuses = Counter(r["mapping_status"] for r in output)
    canonical_groups = Counter(r["canonical_line_item"] for r in output)
    merged = {
        key: count for key, count in canonical_groups.items() if count > 1
    }

    print(f"Source concepts: {len(output)}")
    print(f"Distinct canonical identities: {len(canonical_groups)}")
    print(f"Concepts in merged identities: {sum(merged.values())}")
    print(f"Merged identity groups: {len(merged)}")

    print("\nMapping methods:")
    for key, count in sorted(methods.items()):
        print(f"  {key:<20} {count:>5}")

    print("\nMapping statuses:")
    for key, count in sorted(statuses.items()):
        print(f"  {key:<20} {count:>5}")

    print("\nCurated alias groups:")
    for key, count in sorted(merged.items()):
        print(f"  {key:<48} {count:>3} concepts")

    print(f"\nOutput: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
