"""
Harvest the universe of XBRL tags actually used by a sample of companies.

Outputs two CSVs:
  runlogs/harvest_facts.csv     one row per (ticker, taxonomy, tag, unit)
  runlogs/tag_frequency.csv     one row per (taxonomy, tag), ranked by company count

This is the XBRL equivalent of line_items_*.csv in the StockAnalysis drift tool:
it tells you what exists before you decide what it means.
"""

import csv
import json
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

from northstar.data.sources.sec_edgar import SECEdgarClient

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
ANNUAL_MIN_DAYS = 330
ANNUAL_MAX_DAYS = 370
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A"}
STANDARD_NAMESPACES = {"us-gaap", "ifrs-full", "dei", "srt", "invest", "ffd", "ecd"}


def load_tickers(path: str) -> list[str]:
    return [
        line.strip().upper()
        for line in Path(path).read_text().splitlines()
        if line.strip()
    ]


def load_companyfacts(client: SECEdgarClient, ticker: str) -> dict:
    """Use cached JSON when available so repeat runs don't re-hit the SEC."""
    cik = client.resolve_cik(ticker)
    cache = RUNLOGS / f"{ticker}_{cik}.json"

    if cache.exists():
        return json.loads(cache.read_text())

    data = client.fetch_companyfacts(ticker)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data))
    time.sleep(0.3)
    return data


def summarize_concept(concept: dict) -> dict | None:
    """
    Reduce one concept to a single summary row.

    Classifies duration (income/cash-flow style) vs instant (balance-sheet style),
    which is a free first signal for statement assignment.
    """
    best = None
    annual_count = 0
    shape = None
    unit_seen = None

    for unit, facts in concept.get("units", {}).items():
        for fact in facts:
            if fact.get("form") not in ANNUAL_FORMS:
                continue
            if fact.get("segment"):
                continue

            end = fact.get("end")
            if not end:
                continue

            start = fact.get("start")

            if start:
                days = (date.fromisoformat(end) - date.fromisoformat(start)).days
                if not ANNUAL_MIN_DAYS <= days <= ANNUAL_MAX_DAYS:
                    continue
                shape = "duration"
            else:
                shape = shape or "instant"

            annual_count += 1
            unit_seen = unit

            if best is None or (end, fact.get("filed") or "") > (
                best["end"],
                best.get("filed") or "",
            ):
                best = fact

    if best is None:
        return None

    return {
        "unit": unit_seen,
        "shape": shape,
        "annual_fact_count": annual_count,
        "latest_end": best.get("end"),
        "latest_value": best.get("val"),
        "latest_filed": best.get("filed"),
        "latest_form": best.get("form"),
    }


def main() -> None:
    tickers_path = sys.argv[1] if len(sys.argv) > 1 else "Dev_tools/xbrl/tickers_sample.txt"
    tickers = load_tickers(tickers_path)

    client = SECEdgarClient()
    RUNLOGS.mkdir(parents=True, exist_ok=True)

    facts_path = RUNLOGS / "harvest_facts.csv"
    freq_path = RUNLOGS / "tag_frequency.csv"

    companies_per_tag: dict[tuple[str, str], set[str]] = defaultdict(set)
    label_per_tag: dict[tuple[str, str], str] = {}
    shape_per_tag: dict[tuple[str, str], str] = {}

    with facts_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "ticker", "taxonomy", "tag", "label", "is_extension", "shape",
            "unit", "annual_fact_count", "latest_end", "latest_value",
            "latest_filed", "latest_form",
        ])

        for index, ticker in enumerate(tickers, start=1):
            print(f"[{index}/{len(tickers)}] {ticker}")

            try:
                data = load_companyfacts(client, ticker)
            except Exception as error:
                print(f"  ERROR: {error}")
                continue

            for taxonomy, concepts in data.get("facts", {}).items():
                is_extension = taxonomy not in STANDARD_NAMESPACES

                for tag, concept in concepts.items():
                    summary = summarize_concept(concept)
                    if summary is None:
                        continue

                    label = concept.get("label", "") or ""

                    writer.writerow([
                        ticker, taxonomy, tag, label, is_extension,
                        summary["shape"], summary["unit"],
                        summary["annual_fact_count"], summary["latest_end"],
                        summary["latest_value"], summary["latest_filed"],
                        summary["latest_form"],
                    ])

                    key = (taxonomy, tag)
                    companies_per_tag[key].add(ticker)
                    label_per_tag.setdefault(key, label)
                    shape_per_tag.setdefault(key, summary["shape"])

    rows = sorted(
        companies_per_tag.items(),
        key=lambda item: (-len(item[1]), item[0][0], item[0][1]),
    )

    with freq_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["taxonomy", "tag", "label", "shape", "company_count", "tickers"])

        for (taxonomy, tag), tickers_seen in rows:
            writer.writerow([
                taxonomy, tag, label_per_tag.get((taxonomy, tag), ""),
                shape_per_tag.get((taxonomy, tag), ""),
                len(tickers_seen), "|".join(sorted(tickers_seen)),
            ])

    print(f"\nWrote {facts_path}")
    print(f"Wrote {freq_path}")


if __name__ == "__main__":
    main()