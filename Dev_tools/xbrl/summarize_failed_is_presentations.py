"""
Summarize income-statement presentation relationships for companies whose
top-half income-statement identity did not fit.

Reads local research CSVs only. Makes no network calls.

Outputs:
    runlogs/failed_is_presentation_edges.csv
    runlogs/failed_is_presentation_concepts.csv
"""

import csv
from collections import defaultdict
from pathlib import Path


RUNLOGS = Path("Dev_tools/xbrl/runlogs")
TARGETS_PATH = RUNLOGS / "top_half_diagnostics.csv"
EDGES_PATH = RUNLOGS / "presentation_rows.csv"
STATUS_PATH = RUNLOGS / "presentation_harvest_status.csv"
GLOSSARY_PATH = RUNLOGS / "xbrl_glossary.csv"

OUTPUT_EDGES = RUNLOGS / "failed_is_presentation_edges.csv"
OUTPUT_CONCEPTS = RUNLOGS / "failed_is_presentation_concepts.csv"


def read_csv(path: Path, required_columns: set[str]) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"Required input is missing: {path}")

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = required_columns - columns
        if missing:
            raise SystemExit(
                f"{path} is missing expected columns: {sorted(missing)}"
            )
        return list(reader)


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def main() -> None:
    target_rows = read_csv(TARGETS_PATH, {"ticker", "period_end"})
    presentation_rows = read_csv(
        EDGES_PATH,
        {
            "ticker",
            "filing_accession",
            "filing_index_url",
            "pre_xml_url",
            "statement_role",
            "statement_category",
            "parent_concept",
            "child_concept",
            "sibling_order",
            "preferred_label_role",
            "is_structural",
        },
    )
    status_rows = read_csv(STATUS_PATH, {"ticker", "status"})
    glossary_rows = read_csv(
        GLOSSARY_PATH,
        {"concept", "label", "company_count", "mapped", "mapped_refs"},
    )

    targets = {
        row["ticker"]: row.get("period_end", "")
        for row in target_rows
        if row.get("ticker")
    }
    target_tickers = set(targets)

    status_by_ticker = {row["ticker"]: row for row in status_rows}
    glossary_by_concept = {row["concept"]: row for row in glossary_rows}

    edges = []
    groups = defaultdict(
        lambda: {
            "tickers": set(),
            "roles": set(),
            "parents": set(),
            "example": None,
        }
    )

    for row in presentation_rows:
        ticker = row.get("ticker", "")
        if ticker not in target_tickers:
            continue
        if row.get("statement_category") != "income_statement":
            continue
        if truthy(row.get("is_structural")):
            continue

        concept = row.get("child_concept", "")
        if not concept:
            continue

        glossary = glossary_by_concept.get(concept, {})
        group = groups[concept]
        group["tickers"].add(ticker)
        group["roles"].add(row.get("statement_role", ""))
        group["parents"].add(row.get("parent_concept", ""))

        if group["example"] is None:
            group["example"] = row

        edges.append({
            "ticker": ticker,
            "valuation_period_end": targets[ticker],
            "filing_accession": row.get("filing_accession", ""),
            "statement_role": row.get("statement_role", ""),
            "parent_concept": row.get("parent_concept", ""),
            "sibling_order": row.get("sibling_order", ""),
            "concept": concept,
            "preferred_label_role": row.get("preferred_label_role", ""),
            "glossary_label": glossary.get("label", ""),
            "mapped": glossary.get("mapped", ""),
            "mapped_refs": glossary.get("mapped_refs", ""),
            "company_count_in_harvest": glossary.get("company_count", ""),
            "filing_index_url": row.get("filing_index_url", ""),
            "presentation_url": row.get("pre_xml_url", ""),
        })

    edge_fields = [
        "ticker",
        "valuation_period_end",
        "filing_accession",
        "statement_role",
        "parent_concept",
        "sibling_order",
        "concept",
        "preferred_label_role",
        "glossary_label",
        "mapped",
        "mapped_refs",
        "company_count_in_harvest",
        "filing_index_url",
        "presentation_url",
    ]

    edges.sort(
        key=lambda row: (
            row["ticker"],
            row["statement_role"],
            row["parent_concept"],
            row["sibling_order"],
            row["concept"],
        )
    )

    with OUTPUT_EDGES.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=edge_fields)
        writer.writeheader()
        writer.writerows(edges)

    concept_rows = []
    for concept, group in groups.items():
        example = group["example"] or {}
        glossary = glossary_by_concept.get(concept, {})
        concept_rows.append({
            "concept": concept,
            "label": glossary.get("label", ""),
            "mapped": glossary.get("mapped", ""),
            "mapped_refs": glossary.get("mapped_refs", ""),
            "company_count_in_100_company_harvest": glossary.get("company_count", ""),
            "companies_in_failed_top_half_set": len(group["tickers"]),
            "failed_set_tickers": "|".join(sorted(group["tickers"])),
            "presentation_roles": " | ".join(sorted(group["roles"])),
            "parent_concepts": " | ".join(sorted(p for p in group["parents"] if p)),
            "example_ticker": example.get("ticker", ""),
            "example_accession": example.get("filing_accession", ""),
            "example_filing_index_url": example.get("filing_index_url", ""),
            "example_presentation_url": example.get("pre_xml_url", ""),
        })

    concept_rows.sort(
        key=lambda row: (
            -int(row["companies_in_failed_top_half_set"]),
            row["mapped"] == "Y",
            row["concept"],
        )
    )

    concept_fields = [
        "concept",
        "label",
        "mapped",
        "mapped_refs",
        "company_count_in_100_company_harvest",
        "companies_in_failed_top_half_set",
        "failed_set_tickers",
        "presentation_roles",
        "parent_concepts",
        "example_ticker",
        "example_accession",
        "example_filing_index_url",
        "example_presentation_url",
    ]

    with OUTPUT_CONCEPTS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=concept_fields)
        writer.writeheader()
        writer.writerows(concept_rows)

    parsed_targets = sorted(
        ticker for ticker in target_tickers
        if status_by_ticker.get(ticker, {}).get("status") == "PARSED"
    )
    missing_targets = sorted(target_tickers - set(parsed_targets))

    print(f"Top-half failure companies: {len(target_tickers)}")
    print(f"With parsed presentation data: {len(parsed_targets)}")
    print(f"Without parsed presentation data: {', '.join(missing_targets) or 'none'}")
    print(f"Income-statement-classified non-structural edges: {len(edges)}")
    print(f"Distinct child concepts in those roles: {len(concept_rows)}")
    print(f"Wrote {OUTPUT_EDGES}")
    print(f"Wrote {OUTPUT_CONCEPTS}")


if __name__ == "__main__":
    main()
