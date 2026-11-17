#!/usr/bin/env python3

import csv
from collections import Counter
from pathlib import Path

BASE = Path("Dev_tools/xbrl/runlogs")

FILES = (
    BASE / "canonical_is_concept_classification.csv",
    BASE / "canonical_is_taxonomy.csv",
)

# Display order follows a conventional income statement.
ZONES = {
    "before_revenue": (10, "Before revenue"),
    "revenue": (20, "Revenue"),
    "cost_of_revenue": (30, "Cost of revenue"),
    "gross_profit": (40, "Gross profit"),
    "revenue_to_operating_income_no_gross_profit": (
        45, "Revenue to operating income — no gross profit subtotal"
    ),
    "gross_profit_to_operating_income": (
        50, "Gross profit to operating income"
    ),
    "operating_expenses": (50, "Operating expenses"),
    "operating_income": (60, "Operating income"),
    "operating_income_to_pretax": (
        70, "Operating income to pretax income"
    ),
    "nonoperating": (70, "Nonoperating income and expense"),
    "pretax": (80, "Pretax income"),
    "pretax_to_tax": (85, "Pretax income to income taxes"),
    "income_taxes": (90, "Income taxes"),
    "tax_to_net_income": (95, "Income taxes to net income"),
    "discontinued_operations": (97, "Discontinued operations"),
    "net_income": (100, "Net income"),
    "attribution": (110, "Net income attribution"),
    "per_share": (120, "Per-share measures"),
    "share_count": (125, "Weighted average shares"),
    "comprehensive_income": (130, "Other comprehensive income"),
    "after_net_income": (135, "Other post-net-income items"),
    "supplementary": (140, "Supplementary information"),
    "context_dependent": (150, "Context-dependent — placement varies"),
    "unresolved": (160, "Unresolved — placement not established"),
}


def zone_for(row):
    role = row.get("concept_role", "")
    section = row.get("canonical_section", "")
    evidence = row.get("strongest_evidence_zone", "")

    # Specific roles take precedence over broad sections.
    if role == "attribution":
        return ZONES["attribution"]
    if role == "per_share":
        return ZONES["per_share"]
    if role == "share_count":
        return ZONES["share_count"]
    if role == "comprehensive_income":
        return ZONES["comprehensive_income"]
    if role == "discontinued_operations":
        return ZONES["discontinued_operations"]

    # Explicit canonical sections.
    section_map = {
        "revenue": "revenue",
        "cost_of_revenue": "cost_of_revenue",
        "gross_profit": "gross_profit",
        "operating_expenses": "operating_expenses",
        "operating_income": "operating_income",
        "nonoperating": "nonoperating",
        "pretax": "pretax",
        "income_taxes": "income_taxes",
        "net_income": "net_income",
        "comprehensive_income": "comprehensive_income",
        "discontinued_operations": "discontinued_operations",
    }

    if section in section_map:
        return ZONES[section_map[section]]

    # Use observed placement for concepts whose economic section is uncertain.
    if evidence in ZONES:
        return ZONES[evidence]

    if section == "context_dependent":
        return ZONES["context_dependent"]
    if section == "contextual":
        return (150, "Context-dependent subtotal")
    return ZONES["unresolved"]


def main():
    for path in FILES:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fields = list(reader.fieldnames or [])
            rows = list(reader)

        if not rows:
            raise SystemExit(f"No rows found: {path}")

        for column in ("display_order", "display_zone"):
            if column not in fields:
                fields.append(column)

        counts = Counter()

        for row in rows:
            order, label = zone_for(row)
            row["display_order"] = str(order)
            row["display_zone"] = label
            counts[(order, label)] += 1

        # Keep source concept order within each display zone.
        rows.sort(key=lambda r: (
            int(r["display_order"]),
            r["concept"],
        ))

        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

        print(f"\nUpdated: {path}")
        print(f"Rows: {len(rows)}")
        print("Display zones:")
        for (order, label), count in sorted(counts.items()):
            print(f"  {order:>3} | {count:>3} | {label}")


if __name__ == "__main__":
    main()
