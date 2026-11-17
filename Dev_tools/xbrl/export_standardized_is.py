#!/usr/bin/env python3
"""Export canonical, multi-period income statements from harvested SEC facts."""

import argparse
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
RUNLOGS = BASE / "runlogs"

LAYOUT_FILE = RUNLOGS / "canonical_is_statement_layout.csv"
PRESENTATION_FILE = RUNLOGS / "presentation_rows.csv"
GLOSSARY_FILE = RUNLOGS / "xbrl_glossary.csv"

OUTPUT_FIELDS = [
    "ticker",
    "cik",
    "form",
    "filing_date",
    "filing_accession",
    "period_start",
    "period_end",
    "concept",
    "source_label",
    "canonical_line_item",
    "canonical_line_item_label",
    "canonical_section",
    "concept_role",
    "statement_order",
    "statement_zone",
    "mapping_status",
    "mapping_method",
    "placement_method",
    "reported_value",
    "derived_value",
    "derivation_method",
    "derivation_inputs",
    "unit",
    "decimals",
    "context_ref",
    "value_status",
    "presentation_status",
    "presentation_roles",
    "presentation_parents",
    "presentation_sibling_orders",
    "dimensional_contexts",
    "dimensional_units",
]


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def accession_key(value):
    return (value or "").replace("-", "")


def precision_rank(value):
    value = str(value or "").strip().upper()
    if value == "INF":
        return (2, 0)
    try:
        return (1, int(value))
    except ValueError:
        return (0, 0)


def annual_periods(facts, layout, fact_index):
    """
    Select the three most recent distinct annual periods with reported
    principal anchors. Resolve duplicate period ends by anchor coverage.
    """
    anchor_names = {
        "total_revenue",
        "gross_profit",
        "operating_income",
        "pretax_income",
        "net_income",
    }

    candidates = set()

    for row in facts:
        if row.get("unit") != "USD":
            continue
        if row.get("dimension_count") != "0":
            continue

        start_text = row.get("period_start", "")
        end_text = row.get("period_end", "")
        if not start_text or not end_text:
            continue

        try:
            start = date.fromisoformat(start_text)
            end = date.fromisoformat(end_text)
        except ValueError:
            continue

        if 330 <= (end - start).days <= 380:
            candidates.add((start_text, end_text))

    by_end = defaultdict(list)

    for start_text, end_text in candidates:
        populated_anchors = set()

        for item in layout:
            canonical_name = item.get("canonical_line_item", "")
            if canonical_name not in anchor_names:
                continue

            concept = item.get("concept", "")
            rows = fact_index.get((concept, start_text, end_text), [])

            value, status, unit, *_ = select_consolidated_fact(rows)

            if status == "reported" and unit == "USD" and value is not None:
                populated_anchors.add(canonical_name)

        duration = (
            date.fromisoformat(end_text) - date.fromisoformat(start_text)
        ).days

        by_end[end_text].append({
            "start": start_text,
            "end": end_text,
            "anchor_count": len(populated_anchors),
            "duration_distance": abs(duration - 365),
        })

    selected = []

    for end_text, same_end in by_end.items():
        same_end.sort(
            key=lambda period: (
                period["anchor_count"],
                -period["duration_distance"],
                period["start"],
            ),
            reverse=True,
        )

        best = same_end[0]

        # Do not select annual periods with no reported principal anchors.
        if best["anchor_count"] > 0:
            selected.append((best["start"], best["end"]))

    selected.sort(key=lambda period: (period[1], period[0]))
    return selected[-3:]



def latest_fact_files():
    candidates = defaultdict(list)

    for path in RUNLOGS.glob("filing_facts_*.csv"):
        try:
            with path.open(newline="", encoding="utf-8-sig") as handle:
                first = next(csv.DictReader(handle), None)
            if not first:
                continue

            ticker = first.get("ticker", "").upper()
            if ticker:
                candidates[ticker].append((
                    first.get("filing_date", ""),
                    first.get("filing_accession", ""),
                    path,
                ))
        except (OSError, csv.Error):
            continue

    selected = {}
    for ticker, entries in candidates.items():
        selected[ticker] = sorted(entries, reverse=True)[0][2]

    return selected


def load_presentation_index():
    index = defaultdict(list)
    if not PRESENTATION_FILE.exists():
        return index

    for row in read_csv(PRESENTATION_FILE):
        if row.get("statement_category") not in (
            "income_statement",
            "comprehensive_income_statement",
        ):
            continue

        key = (
            row.get("ticker", "").upper(),
            accession_key(row.get("filing_accession")),
        )

        # Only leaf concepts are evidence of individual presented lines.
        if row.get("is_structural", "").strip().lower() == "true":
            continue

        concept = row.get("child_concept", "")
        if concept:
            index[key].append(row)

    return index


def load_glossary():
    labels = {}
    if not GLOSSARY_FILE.exists():
        return labels

    for row in read_csv(GLOSSARY_FILE):
        concept = row.get("concept", "")
        if concept:
            labels[concept] = row.get("label", "")

    return labels


def build_fact_index(facts):
    """Index facts by concept and exact annual period."""
    index = defaultdict(list)

    for row in facts:
        concept = row.get("concept", "")
        start = row.get("period_start", "")
        end = row.get("period_end", "")

        if not concept or not start or not end:
            continue

        try:
            dimension_count = int(row.get("dimension_count") or 0)
        except ValueError:
            dimension_count = 0

        index[(concept, start, end)].append((dimension_count, row))

    return index


def select_consolidated_fact(rows):
    """Select an unambiguous fact in a supported standardized-statement unit."""
    accepted_units = {"USD", "USD/shares", "shares"}
    by_unit = defaultdict(list)
    excluded_units = set()
    has_nondimensional_fact = False

    for row in rows:
        dimension_count, fact = row
        if dimension_count != 0:
            continue

        has_nondimensional_fact = True
        unit = fact.get("unit", "")

        if unit not in accepted_units:
            if unit:
                excluded_units.add(unit)
            continue

        try:
            value = float(fact.get("value", ""))
        except (TypeError, ValueError):
            continue

        by_unit[unit].append(
            (precision_rank(fact.get("decimals")), value, fact)
        )

    if not by_unit:
        if excluded_units:
            return (
                None,
                "non_usd_excluded",
                ";".join(sorted(excluded_units)),
                "",
                "",
                "",
            )

        return None, "dimensional_only", "", "", "", ""

    if len(by_unit) > 1:
        units = sorted(by_unit)
        return None, "conflicting_units", ";".join(units), "", "", ""

    unit, candidates = next(iter(by_unit.items()))
    best_precision = max(item[0] for item in candidates)
    best = [item for item in candidates if item[0] == best_precision]
    best_values = {item[1] for item in best}

    if len(best_values) > 1:
        contexts = sorted({
            item[2].get("context_ref", "")
            for item in best
            if item[2].get("context_ref")
        })
        decimals = sorted({
            item[2].get("decimals", "")
            for item in best
            if item[2].get("decimals") is not None
        })
        return (
            None,
            "conflicting_facts",
            unit,
            ";".join(decimals),
            ";".join(contexts),
            "",
        )

    chosen = sorted(best, key=lambda item: item[2].get("context_ref", ""))[0]
    contexts = sorted({
        item[2].get("context_ref", "")
        for item in best
        if item[2].get("context_ref")
    })

    return (
        format(chosen[1], ".15g"),
        "reported",
        unit,
        chosen[2].get("decimals", ""),
        ";".join(contexts),
        "",
    )


def dimensional_evidence(rows):
    dimensional = [
        fact for dimension_count, fact in rows
        if dimension_count > 0
    ]

    contexts = sorted({
        fact.get("context_ref", "")
        for fact in dimensional
        if fact.get("context_ref")
    })
    units = sorted({
        fact.get("unit", "")
        for fact in dimensional
        if fact.get("unit")
    })

    return ";".join(contexts), ";".join(units)


def export(tickers, output_path):
    layout = read_csv(LAYOUT_FILE)
    layout.sort(key=lambda row: (
        int(row.get("statement_order") or 999999),
        row.get("canonical_line_item", ""),
        row.get("concept", ""),
    ))

    presentation = load_presentation_index()
    glossary = load_glossary()
    latest = latest_fact_files()

    selected_tickers = sorted(tickers or latest.keys())
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_rows = 0
    ticker_count = 0
    period_count = 0
    status_counts = defaultdict(int)
    presentation_counts = defaultdict(int)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()

        for ticker in selected_tickers:
            path = latest.get(ticker)
            if path is None:
                print(f"SKIP {ticker}: no fact file")
                continue

            facts = read_csv(path)
            if not facts:
                print(f"SKIP {ticker}: empty fact file")
                continue

            metadata = facts[0]
            accession = metadata.get("filing_accession", "")
            filing_key = (ticker, accession_key(accession))
            filing_presentation = presentation.get(filing_key, [])
            has_presentation = bool(filing_presentation)

            presentation_by_concept = defaultdict(list)
            for row in filing_presentation:
                presentation_by_concept[row.get("child_concept", "")].append(row)

            fact_index = build_fact_index(facts)
            periods = annual_periods(facts, layout, fact_index)

            def canonical_reported_value(canonical_name):
                candidates_found = []

                for layout_item in layout:
                    if layout_item.get("canonical_line_item") != canonical_name:
                        continue

                    concept_name = layout_item["concept"]
                    fact_rows = fact_index.get(
                        (concept_name, start, end), []
                    )
                    candidate_value, candidate_status, candidate_unit, *_ = (
                        select_consolidated_fact(fact_rows)
                    )

                    if (
                        candidate_status == "reported"
                        and candidate_unit == "USD"
                        and candidate_value is not None
                    ):
                        from decimal import Decimal
                        candidates_found.append(
                            (Decimal(str(candidate_value)), concept_name)
                        )

                if not candidates_found:
                    return None, []

                distinct_values = {value for value, _ in candidates_found}
                if len(distinct_values) != 1:
                    return None, []

                return (
                    candidates_found[0][0],
                    sorted({concept for _, concept in candidates_found}),
                )

            if not periods:
                print(f"SKIP {ticker}: no consolidated annual USD periods")
                continue

            ticker_count += 1
            period_count += len(periods)

            for start, end in periods:
                for item in layout:
                    concept = item["concept"]
                    candidates = fact_index.get((concept, start, end), [])

                    value, value_status, unit, decimals, contexts, _ = (
                        select_consolidated_fact(candidates)
                    )

                    dimensional_contexts, dimensional_units = (
                        dimensional_evidence(candidates)
                    )

                    if value_status == "dimensional_only" and not dimensional_contexts:
                        value_status = "not_reported"

                    derived_value = ""
                    derivation_method = ""
                    derivation_inputs = ""

                    if (
                        item.get("canonical_line_item") == "gross_profit"
                        and value_status == "not_reported"
                    ):
                        from decimal import Decimal

                        revenue, revenue_concepts = canonical_reported_value(
                            "total_revenue"
                        )
                        cost, cost_concepts = canonical_reported_value(
                            "cost_of_revenue"
                        )

                        if revenue is not None and cost is not None:
                            derived_value = str(revenue - cost)
                            derivation_method = (
                                "total_revenue - cost_of_revenue"
                            )
                            derivation_inputs = ";".join(
                                [*revenue_concepts, *cost_concepts]
                            )
                            value_status = "derived"
                            unit = "USD"

                    evidence = presentation_by_concept.get(concept, [])
                    if not has_presentation:
                        presentation_status = "no_presentation_evidence"
                    elif evidence:
                        presentation_status = "presented_on_face"
                    else:
                        presentation_status = "not_on_face"

                    roles = sorted({
                        row.get("statement_role", "")
                        for row in evidence
                        if row.get("statement_role")
                    })
                    parents = sorted({
                        row.get("parent_concept", "")
                        for row in evidence
                        if row.get("parent_concept")
                    })
                    sibling_orders = sorted({
                        row.get("sibling_order", "")
                        for row in evidence
                        if row.get("sibling_order")
                    })

                    output = {
                        "ticker": ticker,
                        "cik": metadata.get("cik", ""),
                        "form": metadata.get("form", ""),
                        "filing_date": metadata.get("filing_date", ""),
                        "filing_accession": accession,
                        "period_start": start,
                        "period_end": end,
                        "concept": concept,
                        "source_label": glossary.get(concept, ""),
                        "canonical_line_item": item.get("canonical_line_item", ""),
                        "canonical_line_item_label": item.get("canonical_line_item_label", ""),
                        "canonical_section": item.get("canonical_section", ""),
                        "concept_role": item.get("concept_role", ""),
                        "statement_order": item.get("statement_order", ""),
                        "statement_zone": item.get("statement_zone", ""),
                        "mapping_status": item.get("mapping_status", ""),
                        "mapping_method": item.get("mapping_method", ""),
                        "placement_method": item.get("placement_method", ""),
                        "reported_value": value if value is not None else "",
                        "derived_value": derived_value,
                        "derivation_method": derivation_method,
                        "derivation_inputs": derivation_inputs,
                        "unit": unit,
                        "decimals": decimals,
                        "context_ref": contexts,
                        "value_status": value_status,
                        "presentation_status": presentation_status,
                        "presentation_roles": ";".join(roles),
                        "presentation_parents": ";".join(parents),
                        "presentation_sibling_orders": ";".join(sibling_orders),
                        "dimensional_contexts": dimensional_contexts,
                        "dimensional_units": dimensional_units,
                    }

                    writer.writerow(output)
                    total_rows += 1
                    status_counts[value_status] += 1
                    presentation_counts[presentation_status] += 1

            print(
                f"{ticker}: {len(periods)} annual periods, "
                f"{len(periods) * len(layout):,} canonical rows"
            )

    print("\n===== STANDARDIZED EXPORT =====")
    print(f"Companies exported: {ticker_count}")
    print(f"Annual company-periods: {period_count}")
    print(f"Canonical concepts: {len(layout)}")
    print(f"Rows written: {total_rows:,}")
    print(f"Output: {output_path}")

    print("\n===== VALUE STATUS =====")
    for status, count in sorted(status_counts.items()):
        print(f"{status:24} {count:>10,}")

    print("\n===== PRESENTATION STATUS =====")
    for status, count in sorted(presentation_counts.items()):
        print(f"{status:24} {count:>10,}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ticker",
        nargs="+",
        help="One or more tickers; omit to export all latest filings.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=RUNLOGS / "standardized_income_statements.csv",
    )
    args = parser.parse_args()

    tickers = [ticker.upper() for ticker in args.ticker] if args.ticker else None
    export(tickers, args.output)


if __name__ == "__main__":
    main()
