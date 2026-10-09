"""
Build an observed XBRL glossary from research harvest output.

Inputs:
    Dev_tools/xbrl/runlogs/tag_frequency.csv              (required)
    Dev_tools/xbrl/runlogs/presentation_tag_frequency.csv (optional)
    northstar.data.transforms.sec_xbrl_key                (current mapping)

Output:
    Dev_tools/xbrl/runlogs/xbrl_glossary.csv

This is the SEC/XBRL analogue of the StockAnalysis line-item inventory:
what exists in the wild, how common it is, and whether NorthStar maps it.

The statement_family_guess column is a keyword heuristic to order review.
It is not a canonical statement assignment.
"""

import csv
import sys

csv.field_size_limit(sys.maxsize)
from collections import defaultdict
from pathlib import Path

from northstar.data.transforms.sec_xbrl_key import _EXPLICIT_XBRL_ALIASES

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
TAG_FREQUENCY = RUNLOGS / "tag_frequency.csv"
PRESENTATION = RUNLOGS / "presentation_tag_frequency.csv"
OUTPUT = RUNLOGS / "xbrl_glossary.csv"

CASH_FLOW_TERMS = (
    "netcash", "cashprovidedbyusedin", "payments", "proceeds",
    "capitalexpenditure", "cashflow", "dividendspaid", "repurchase",
    "issuance", "amortizationof", "depreciationdepletion",
)

INCOME_TERMS = (
    "revenue", "sales", "costof", "grossprofit", "income", "loss",
    "expense", "earnings", "tax", "interest", "operating", "profit",
    "earningspershare", "weightedaverage",
)

STRUCTURAL_SUFFIXES = ("Abstract", "Table", "Axis", "Domain", "Member", "LineItems")


def build_mapping_index() -> dict[str, list[str]]:
    """concept -> ['revenue:default[0]', 'revenue:bank[0]', ...]"""
    index = defaultdict(list)

    for metric, definition in _EXPLICIT_XBRL_ALIASES.items():
        for position, (taxonomy, tag) in enumerate(definition.get("default_concepts", [])):
            index[f"{taxonomy}:{tag}"].append(f"{metric}:default[{position}]")

        for industry, concepts in definition.get("industry_overrides", {}).items():
            for position, (taxonomy, tag) in enumerate(concepts):
                index[f"{taxonomy}:{tag}"].append(f"{metric}:{industry}[{position}]")

    return index


def load_presentation_index() -> dict[str, dict]:
    """concept -> observed statement categories and one filing example."""
    if not PRESENTATION.exists():
        return {}

    index = defaultdict(lambda: {
        "categories": set(),
        "example_ticker": "",
        "example_accession": "",
        "example_url": "",
    })

    with PRESENTATION.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            concept = row.get("concept", "")
            if not concept:
                continue

            entry = index[concept]

            category = row.get("statement_category", "")
            if category:
                entry["categories"].add(category)

            if not entry["example_ticker"]:
                entry["example_ticker"] = row.get("example_ticker", "")
                entry["example_accession"] = row.get("example_accession", "")
                entry["example_url"] = row.get("example_filing_index_url", "")

    return index


def guess_family(tag: str, label: str, shape: str) -> str:
    if tag.endswith(STRUCTURAL_SUFFIXES):
        return "structural"

    text = f"{tag} {label}".replace(" ", "").lower()

    if any(term in text for term in CASH_FLOW_TERMS):
        return "cash_flow_candidate"
    if shape == "instant":
        return "balance_sheet_candidate"
    if any(term in text for term in INCOME_TERMS):
        return "income_statement_candidate"
    if shape == "duration":
        return "duration_unclear"
    return "unknown"


def main() -> None:
    if not TAG_FREQUENCY.exists():
        raise SystemExit(f"Missing {TAG_FREQUENCY}. Run harvest_tags.py first.")

    mapping = build_mapping_index()
    presentation = load_presentation_index()

    if not presentation:
        print("Note: no presentation_tag_frequency.csv found; "
              "statement placement columns will be blank.\n")

    rows = []

    with TAG_FREQUENCY.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            taxonomy = row["taxonomy"]
            tag = row["tag"]
            concept = f"{taxonomy}:{tag}"
            label = row.get("label", "")
            shape = row.get("shape", "")

            refs = mapping.get(concept, [])
            place = presentation.get(concept, {})

            rows.append({
                "concept": concept,
                "taxonomy": taxonomy,
                "tag": tag,
                "label": label,
                "shape": shape,
                "company_count": int(row.get("company_count") or 0),
                "mapped": "Y" if refs else "N",
                "mapped_refs": " | ".join(refs),
                "statement_family_guess": guess_family(tag, label, shape),
                "presentation_categories": " | ".join(sorted(place.get("categories", []))),
                "example_ticker": place.get("example_ticker", ""),
                "example_accession": place.get("example_accession", ""),
                "example_filing_url": place.get("example_url", ""),
                "tickers": row.get("tickers", ""),
            })

    rows.sort(key=lambda r: (r["mapped"] != "Y", -r["company_count"], r["concept"]))

    fields = [
        "concept", "taxonomy", "tag", "label", "shape", "company_count",
        "mapped", "mapped_refs", "statement_family_guess",
        "presentation_categories", "example_ticker", "example_accession",
        "example_filing_url", "tickers",
    ]

    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    mapped_count = sum(1 for r in rows if r["mapped"] == "Y")

    print(f"Wrote {OUTPUT}")
    print(f"Observed concepts: {len(rows)}")
    print(f"Mapped by sec_xbrl_key: {mapped_count}")

    families = defaultdict(int)
    for row in rows:
        families[row["statement_family_guess"]] += 1

    print("\nStatement-family guess:")
    for family, count in sorted(families.items(), key=lambda item: -item[1]):
        print(f"  {family:<28} {count}")

    print("\nTop 30 unmapped income-statement candidates:")
    shown = 0
    for row in rows:
        if row["mapped"] == "Y" or row["statement_family_guess"] != "income_statement_candidate":
            continue
        print(f"  {row['company_count']:>3}  {row['concept']:<78}  {row['label'][:60]}")
        shown += 1
        if shown >= 30:
            break

    unmapped_high = [
        r for r in rows
        if r["mapped"] == "N"
        and r["company_count"] >= 50
        and r["statement_family_guess"] != "structural"
    ]
    print(f"\nUnmapped concepts in 50+ companies (any family): {len(unmapped_high)}")


if __name__ == "__main__":
    main()
