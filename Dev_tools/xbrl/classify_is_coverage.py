"""
Classify 100-company income-statement research coverage.

Purpose:
    Distinguish companies that reconcile using generic standard XBRL mappings
    from companies that require company-extension concepts or have unresolved
    standard-concept gaps.

Inputs:
    scaled_is_summary.csv
    top_half_archetype_summary.csv
    filing_facts_*.csv (optional evidence for extension concepts)

Output:
    runlogs/is_coverage_classification.csv

Categories:
    STANDARD_RECONCILES
        Top-half and bottom-half standard checks reconcile.

    NO_OPERATING_INCOME
        No OperatingIncomeLoss fact. Common for banks/insurers/financials and
        not necessarily an error.

    EXTENSION_REQUIRED
        Raw filing facts show company-extension concepts likely needed for
        operating-income reconstruction.

    STANDARD_BUT_UNRESOLVED
        Standard data exists, but current generic formulas do not reconcile.

    DATA_GAP
        Revenue/operating income/other anchor facts are missing.

    RETRIEVAL_ERROR
        Ticker or SEC retrieval problem.
"""

import csv
import glob
from pathlib import Path


RUNLOGS = Path("Dev_tools/xbrl/runlogs")

SCALED_IS = RUNLOGS / "scaled_is_summary.csv"
TOP_HALF = RUNLOGS / "top_half_archetype_summary.csv"
OUTPUT = RUNLOGS / "is_coverage_classification.csv"


def load_csv(path: Path) -> dict[str, dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            row["ticker"]: row
            for row in csv.DictReader(handle)
            if row.get("ticker")
        }


def has_extension_facts(ticker: str) -> list[str]:
    """
    Return extension concepts found in the latest harvested filing-facts CSV.

    Presence is evidence only; it does not automatically mean the concept is
    required for the income statement.
    """
    files = sorted(glob.glob(str(RUNLOGS / f"filing_facts_{ticker}_*.csv")))

    if not files:
        return []

    # Latest filesystem-modified output is the current research extraction.
    latest = max(files, key=lambda filename: Path(filename).stat().st_mtime)

    concepts = set()

    with open(latest, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            concept = row.get("concept", "")
            if ":" not in concept:
                continue

            prefix = concept.split(":", 1)[0].lower()

            if prefix in {"us-gaap", "dei", "srt", "invest", "ifrs-full"}:
                continue

            text = concept.lower()

            if any(
                term in text
                for term in (
                    "cost",
                    "expense",
                    "marketing",
                    "administration",
                    "research",
                    "impairment",
                    "restructuring",
                    "operating",
                )
            ):
                concepts.add(concept)

    return sorted(concepts)


def main() -> None:
    if not SCALED_IS.exists():
        raise SystemExit(f"Missing {SCALED_IS}")
    if not TOP_HALF.exists():
        raise SystemExit(f"Missing {TOP_HALF}")

    scaled = load_csv(SCALED_IS)
    top = load_csv(TOP_HALF)

    rows = []

    for ticker in sorted(set(scaled) | set(top)):
        scaled_row = scaled.get(ticker, {})
        top_row = top.get(ticker, {})

        scaled_status = scaled_row.get("overall", "")
        top_status = top_row.get("status", "")
        archetype = top_row.get("archetype", "")
        extensions = has_extension_facts(ticker)

        if scaled_status.startswith("ERROR"):
            category = "RETRIEVAL_ERROR"
        elif top_status == "NO_OPERATING_INCOME":
            category = "NO_OPERATING_INCOME"
        elif top_status == "RECONCILES" and scaled_status == "RECONCILES":
            category = "STANDARD_RECONCILES"
        elif extensions:
            category = "EXTENSION_REQUIRED"
        elif top_status in {"MISMATCH", "INCOMPLETE_DATA"}:
            category = "STANDARD_BUT_UNRESOLVED"
        else:
            category = "DATA_GAP"

        rows.append({
            "ticker": ticker,
            "coverage_category": category,
            "top_half_status": top_status,
            "top_half_archetype": archetype,
            "bottom_half_status": scaled_status,
            "revenue_tag": scaled_row.get("revenue_tag", ""),
            "operating_income_tag": scaled_row.get("opinc_tag", ""),
            "extension_concepts_found": " | ".join(extensions),
            "extension_concept_count": len(extensions),
        })

    rows.sort(key=lambda row: (row["coverage_category"], row["ticker"]))

    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "ticker",
            "coverage_category",
            "top_half_status",
            "top_half_archetype",
            "bottom_half_status",
            "revenue_tag",
            "operating_income_tag",
            "extension_concept_count",
            "extension_concepts_found",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    counts = {}
    for row in rows:
        category = row["coverage_category"]
        counts[category] = counts.get(category, 0) + 1

    print("Income-statement coverage classification")
    print("----------------------------------------")

    for category in sorted(counts):
        print(f"{category:<28} {counts[category]}")

    print("\nExtension-required candidates:")
    for row in rows:
        if row["coverage_category"] == "EXTENSION_REQUIRED":
            print(
                f"  {row['ticker']:<6} "
                f"top={row['top_half_status']:<18} "
                f"bottom={row['bottom_half_status']:<32} "
                f"extensions={row['extension_concepts_found'][:120]}"
            )

    print(f"\nWrote {OUTPUT}")


if __name__ == "__main__":
    main()
