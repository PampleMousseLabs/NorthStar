"""
Analyze failures from scaled_is_summary.csv.

For each failed pretax-to-net-income reconciliation:

    residual = net_income_incl_nci - (pretax_income - taxes)

Search the company's cached SEC CompanyFacts payload for annual USD facts from
the same fiscal period whose absolute values approximately match the residual.

This produces research candidates only. A numerical match is not mapping
approval; candidate tags must still be checked against statement placement
and filing examples.

Outputs:
    Dev_tools/xbrl/runlogs/scaled_is_issue_summary.csv
    Dev_tools/xbrl/runlogs/scaled_is_bridge_candidates.csv
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from northstar.data.sources.sec_edgar import SECEdgarClient


RUNLOGS = Path("Dev_tools/xbrl/runlogs")
SUMMARY_PATH = RUNLOGS / "scaled_is_summary.csv"
ISSUE_OUTPUT = RUNLOGS / "scaled_is_issue_summary.csv"
CANDIDATE_OUTPUT = RUNLOGS / "scaled_is_bridge_candidates.csv"

ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A"}
MIN_ANNUAL_DAYS = 330
MAX_ANNUAL_DAYS = 370

PREFERRED_WORDS = (
    "equity",
    "jointventure",
    "discontinued",
    "extraordinary",
    "continuingoperations",
    "noncontrolling",
    "minority",
    "affiliate",
    "gainloss",
    "income",
)


def parse_number(value: str | None) -> float | None:
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def duration_days(start: str, end: str) -> int | None:
    if not start or not end:
        return None

    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except ValueError:
        return None


def load_summary() -> list[dict]:
    with SUMMARY_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_companyfacts(
    client: SECEdgarClient,
    ticker: str,
) -> tuple[str, dict] | None:
    try:
        cik = client.resolve_cik(ticker)
    except Exception:
        return None

    cache_path = RUNLOGS / f"{ticker}_{cik}.json"

    if not cache_path.exists():
        return None

    try:
        return cik, json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def latest_facts_by_concept(
    payload: dict,
    period_end: str,
) -> list[dict]:
    """
    Return one latest-filed annual USD fact per taxonomy/concept/value tuple.
    """
    selected = {}

    for taxonomy, concepts in payload.get("facts", {}).items():
        for tag, concept in concepts.items():
            label = str(concept.get("label", ""))

            for unit, facts in concept.get("units", {}).items():
                if unit != "USD":
                    continue

                for fact in facts:
                    if fact.get("form") not in ANNUAL_FORMS:
                        continue

                    if fact.get("end") != period_end:
                        continue

                    start = fact.get("start")
                    days = duration_days(start, period_end)

                    if days is None or not MIN_ANNUAL_DAYS <= days <= MAX_ANNUAL_DAYS:
                        continue

                    value = parse_number(fact.get("val"))
                    if value is None:
                        continue

                    key = (taxonomy, tag, value)
                    current = selected.get(key)

                    if (
                        current is None
                        or str(fact.get("filed", "")) > str(current.get("filed", ""))
                    ):
                        selected[key] = {
                            "taxonomy": taxonomy,
                            "tag": tag,
                            "label": label,
                            "value": value,
                            "start": start,
                            "end": period_end,
                            "filed": fact.get("filed", ""),
                            "form": fact.get("form", ""),
                            "accn": fact.get("accn", ""),
                        }

    return list(selected.values())


def candidate_rank(candidate: dict, residual: float) -> tuple:
    value = candidate["value"]

    absolute_difference = abs(abs(value) - abs(residual))
    denominator = max(abs(residual), 1.0)
    relative_difference = absolute_difference / denominator

    searchable = (
        candidate["tag"] + " " + candidate["label"]
    ).replace(" ", "").lower()

    keyword_priority = 0 if any(
        word in searchable for word in PREFERRED_WORDS
    ) else 1

    return (
        relative_difference,
        keyword_priority,
        candidate["tag"],
    )


def filing_url(cik: str, accession: str) -> str:
    if not accession:
        return ""

    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{int(cik)}/{accession.replace('-', '')}/{accession}-index.htm"
    )


def main() -> None:
    if not SUMMARY_PATH.exists():
        raise SystemExit(f"Missing input: {SUMMARY_PATH}")

    client = SECEdgarClient()
    summary_rows = load_summary()

    issue_rows = []
    candidate_rows = []

    counts: dict[str, int] = {}

    for row in summary_rows:
        ticker = row.get("ticker", "")
        period_end = row.get("period_end", "")
        overall = row.get("overall", "")
        gross_status = row.get("gross_check", "")
        step1 = row.get("step1_pretax_minus_tax", "")
        step2 = row.get("step2_nci", "")

        period_year = 0
        if period_end[:4].isdigit():
            period_year = int(period_end[:4])

        if overall.startswith("ERROR"):
            issue_type = "RETRIEVAL_OR_PROCESSING_ERROR"
        elif not period_end:
            issue_type = "NO_ANNUAL_ANCHOR"
        elif period_year and period_year < 2024:
            issue_type = "STALE_PERIOD"
        elif step1 == "FAIL":
            issue_type = "STEP1_BRIDGE_REQUIRED"
        elif step2 in {"NCI_UNTAGGED", "NCI_MISMATCH"}:
            issue_type = "NCI_REVIEW"
        elif overall == "RECONCILES":
            issue_type = "RECONCILES"
        else:
            issue_type = "OTHER_REVIEW"

        counts[issue_type] = counts.get(issue_type, 0) + 1

        pretax = parse_number(row.get("pretax_income"))
        taxes = parse_number(row.get("taxes"))
        income_including_nci = parse_number(row.get("net_income_incl_nci"))

        residual = None
        if (
            pretax is not None
            and taxes is not None
            and income_including_nci is not None
        ):
            residual = income_including_nci - (pretax - taxes)

        issue_rows.append({
            "ticker": ticker,
            "period_end": period_end,
            "issue_type": issue_type,
            "gross_status": gross_status,
            "step1_status": step1,
            "step2_status": step2,
            "overall": overall,
            "pretax_income": "" if pretax is None else pretax,
            "taxes": "" if taxes is None else taxes,
            "net_income_incl_nci": (
                "" if income_including_nci is None else income_including_nci
            ),
            "step1_residual": "" if residual is None else residual,
            "revenue_tag": row.get("revenue_tag", ""),
            "pretax_tag": row.get("pretax_tag", ""),
            "net_income_tag": row.get("ni_tag", ""),
        })

        if issue_type != "STEP1_BRIDGE_REQUIRED" or residual is None:
            continue

        loaded = load_companyfacts(client, ticker)
        if loaded is None:
            continue

        cik, payload = loaded
        candidates = latest_facts_by_concept(payload, period_end)
        candidates.sort(key=lambda candidate: candidate_rank(candidate, residual))

        accepted = []
        for candidate in candidates:
            absolute_difference = abs(abs(candidate["value"]) - abs(residual))
            relative_difference = absolute_difference / max(abs(residual), 1.0)

            # Keep close numerical candidates. The $5M floor handles rounding.
            if relative_difference <= 0.10 or absolute_difference <= 5_000_000:
                accepted.append(candidate)

        for rank, candidate in enumerate(accepted[:12], start=1):
            signed_difference = candidate["value"] - residual
            absolute_magnitude_difference = (
                abs(candidate["value"]) - abs(residual)
            )

            candidate_rows.append({
                "ticker": ticker,
                "period_end": period_end,
                "residual": residual,
                "candidate_rank": rank,
                "taxonomy": candidate["taxonomy"],
                "tag": candidate["tag"],
                "label": candidate["label"],
                "candidate_value": candidate["value"],
                "candidate_minus_residual": signed_difference,
                "absolute_magnitude_difference": absolute_magnitude_difference,
                "filed": candidate["filed"],
                "form": candidate["form"],
                "accession": candidate["accn"],
                "filing_url": filing_url(cik, candidate["accn"]),
            })

    issue_fields = [
        "ticker",
        "period_end",
        "issue_type",
        "gross_status",
        "step1_status",
        "step2_status",
        "overall",
        "pretax_income",
        "taxes",
        "net_income_incl_nci",
        "step1_residual",
        "revenue_tag",
        "pretax_tag",
        "net_income_tag",
    ]

    candidate_fields = [
        "ticker",
        "period_end",
        "residual",
        "candidate_rank",
        "taxonomy",
        "tag",
        "label",
        "candidate_value",
        "candidate_minus_residual",
        "absolute_magnitude_difference",
        "filed",
        "form",
        "accession",
        "filing_url",
    ]

    with ISSUE_OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=issue_fields)
        writer.writeheader()
        writer.writerows(issue_rows)

    with CANDIDATE_OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=candidate_fields)
        writer.writeheader()
        writer.writerows(candidate_rows)

    print("Scaled IS issue classification")
    print("------------------------------")

    for issue_type, count in sorted(counts.items()):
        print(f"{issue_type:<32} {count:>3}")

    print("\nStep-1 failures and residuals")
    print("----------------------------")

    for row in issue_rows:
        if row["issue_type"] == "STEP1_BRIDGE_REQUIRED":
            residual_millions = float(row["step1_residual"]) / 1_000_000
            print(
                f"{row['ticker']:<6} "
                f"{row['period_end']:<12} "
                f"residual={residual_millions:>10,.1f}M"
            )

    print(f"\nWrote {ISSUE_OUTPUT}")
    print(f"Wrote {CANDIDATE_OUTPUT}")


if __name__ == "__main__":
    main()
