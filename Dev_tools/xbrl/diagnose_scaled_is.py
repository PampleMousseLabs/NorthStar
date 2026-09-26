"""
Root-cause diagnostics for scaled_is_summary.csv failures.

Reads only local files:
    Dev_tools/xbrl/runlogs/scaled_is_summary.csv
    Dev_tools/xbrl/runlogs/<TICKER>_<CIK>.json   (cached CompanyFacts)

No network calls. Research only; candidate tags are leads, not approvals.

Output:
    Dev_tools/xbrl/runlogs/scaled_is_diagnostics.csv
"""

import argparse
import csv
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
SUMMARY = RUNLOGS / "scaled_is_summary.csv"
OUT = RUNLOGS / "scaled_is_diagnostics.csv"

ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A"}
CACHE_NAME = re.compile(r"^(?P<ticker>[A-Z0-9.\-]+)_(?P<cik>\d{10})\.json$")
STALE_BEFORE_YEAR = 2024
TOL = 1_000_000.0


def num(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt(value):
    return "N/A" if value is None else f"{value / 1e6:,.1f}M"


def find_cache(ticker):
    for path in RUNLOGS.glob(f"{ticker}_*.json"):
        match = CACHE_NAME.match(path.name)
        if match and match.group("ticker") == ticker:
            return path
    return None


def annual_usd_facts(payload, period_end):
    """Latest-filed annual USD fact per taxonomy:tag for one period end."""
    out = {}
    for taxonomy, concepts in payload.get("facts", {}).items():
        for tag, concept in concepts.items():
            for fact in concept.get("units", {}).get("USD", []):
                if fact.get("form") not in ANNUAL_FORMS or fact.get("end") != period_end:
                    continue
                start = fact.get("start")
                if not start:
                    continue
                try:
                    days = (date.fromisoformat(period_end) - date.fromisoformat(start)).days
                except ValueError:
                    continue
                if not 330 <= days <= 370:
                    continue
                value = num(fact.get("val"))
                if value is None:
                    continue
                key = f"{taxonomy}:{tag}"
                filed = str(fact.get("filed", ""))
                previous = out.get(key)
                if previous is None or filed > previous["filed"]:
                    out[key] = {"value": value, "filed": filed}
    return out


def candidate_lines(facts, terms, exclude=(), limit=6):
    hits = []
    for key, info in facts.items():
        low = key.lower()
        if any(t in low for t in terms) and not any(e in low for e in exclude):
            hits.append((abs(info["value"]), key, info["value"]))
    hits.sort(reverse=True)
    if not hits:
        return ["    (no matching tags for this period)"]
    return [f"    {fmt(value):>14}  {key}" for _, key, value in hits[:limit]]


def match_lines(facts, target, limit=5):
    band = max(TOL, abs(target) * 0.01)
    hits = []
    for key, info in facts.items():
        gap = abs(abs(info["value"]) - abs(target))
        if gap <= band:
            hits.append((gap, key, info["value"]))
    hits.sort()
    if not hits:
        return [f"    (no single tag within {fmt(band)} of {fmt(target)}; likely a combination of lines)"]
    return [f"    {fmt(value):>14}  {key}  (gap {fmt(gap)})" for gap, key, value in hits[:limit]]


def classify(row):
    overall = row.get("overall", "") or ""
    period = row.get("period_end", "") or ""
    if overall.startswith("ERROR"):
        return ["RETRIEVAL_ERROR"]

    issues = []
    if period[:4].isdigit() and int(period[:4]) < STALE_BEFORE_YEAR:
        issues.append("STALE")
    if num(row.get("revenue")) is None:
        issues.append("REVENUE_MISSING")
    if row.get("gross_check") == "FAIL":
        issues.append("GROSS_FAIL")

    step1 = row.get("step1_pretax_minus_tax", "")
    if step1 == "FAIL":
        issues.append("STEP1_RESIDUAL")
    elif step1 == "N/A":
        issues.append("STEP1_MISSING_INPUT")

    step2 = row.get("step2_nci", "")
    if step2 in ("NCI_MISMATCH", "NCI_UNTAGGED"):
        issues.append(step2)
    elif step2 == "N/A":
        issues.append("STEP2_MISSING_INPUT")

    return issues or ["RECONCILES"]


def describe(issue, row, facts):
    def get(key):
        return num(row.get(key))

    if issue == "STALE":
        return [f"STALE: latest annual period selected is {row.get('period_end')}"]

    if issue == "REVENUE_MISSING":
        return ["REVENUE_MISSING: current key found no revenue; revenue-like tags this period:"] + \
            candidate_lines(facts, ("revenue", "sales"),
                            exclude=("availableforsale", "deferred", "salestype", "proceeds"))

    if issue == "GROSS_FAIL":
        rev, cogs, gross = get("revenue"), get("cogs"), get("gross_profit")
        diff = None if None in (rev, cogs, gross) else (rev - cogs) - gross
        lines = [f"GROSS_FAIL: revenue {fmt(rev)} [{row.get('revenue_tag')}] - cogs {fmt(cogs)} "
                 f"[{row.get('cogs_tag')}] - gross {fmt(gross)} = {fmt(diff)}"]
        if diff is not None:
            lines += match_lines(facts, diff)
        return lines

    if issue == "STEP1_MISSING_INPUT":
        missing = [k for k in ("pretax_income", "taxes", "net_income_incl_nci") if get(k) is None]
        return [f"STEP1_MISSING_INPUT: missing {', '.join(missing) or 'nothing?'}; candidate tags this period:"] + \
            candidate_lines(facts, ("beforeincometax", "incometaxexpense", "profitloss"))

    if issue == "STEP1_RESIDUAL":
        pretax, taxes, incl = get("pretax_income"), get("taxes"), get("net_income_incl_nci")
        if None in (pretax, taxes, incl):
            return ["STEP1_RESIDUAL: inputs incomplete"]
        residual = incl - (pretax - taxes)
        return [f"STEP1_RESIDUAL: incl_nci {fmt(incl)} - (pretax {fmt(pretax)} - tax {fmt(taxes)}) = {fmt(residual)}; "
                f"equity_method {fmt(get('equity_method_earnings'))}, disc_ops {fmt(get('discontinued_operations'))}"] + \
            match_lines(facts, residual)

    if issue in ("NCI_MISMATCH", "NCI_UNTAGGED"):
        incl, ni = get("net_income_incl_nci"), get("net_income")
        tagged, implied = get("minority_interest_tagged"), get("minority_interest_implied")
        fallback = ""
        if incl is not None and ni is not None and abs(incl - ni) < TOL:
            fallback = "  <-- incl_nci == net_income: ProfitLoss likely untagged, fell back to NetIncomeLoss"
        return [f"{issue}: incl_nci {fmt(incl)} - net_income {fmt(ni)} = implied NCI {fmt(implied)} "
                f"vs tagged NCI {fmt(tagged)}{fallback}"] + \
            candidate_lines(facts, ("noncontrolling", "minorityinterest", "profitloss",
                                    "preferredstockdividend", "availabletocommon"))

    if issue == "STEP2_MISSING_INPUT":
        return [f"STEP2_MISSING_INPUT: incl_nci {fmt(get('net_income_incl_nci'))}, "
                f"net_income {fmt(get('net_income'))}"]

    return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", default="", help="Only print companies with this issue type")
    args = parser.parse_args()

    if not SUMMARY.exists():
        raise SystemExit(f"Missing {SUMMARY}. Run scale_is_waterfall.py first.")

    with SUMMARY.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    counts = Counter()
    blocks = []
    out_rows = []

    for row in rows:
        ticker = row.get("ticker", "")
        period = row.get("period_end", "") or ""
        issues = classify(row)
        counts.update(issues)
        if issues == ["RECONCILES"]:
            continue

        lines = []
        if issues == ["RETRIEVAL_ERROR"]:
            lines.append(row.get("overall", ""))
        else:
            facts = {}
            cache = find_cache(ticker)
            if cache is None:
                lines.append("no cached CompanyFacts file found")
            elif period:
                try:
                    facts = annual_usd_facts(json.loads(cache.read_text(encoding="utf-8")), period)
                except (OSError, ValueError) as error:
                    lines.append(f"could not read cache: {error}")
            for issue in issues:
                lines.extend(describe(issue, row, facts))

        blocks.append((ticker, period, issues, lines))
        for line in lines:
            out_rows.append({"ticker": ticker, "period_end": period,
                             "issues": "|".join(issues), "detail": line.strip()})

    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ticker", "period_end", "issues", "detail"])
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Companies: {len(rows)}")
    print("Issue counts (a company can have more than one):")
    for issue, count in counts.most_common():
        print(f"  {issue:<22} {count}")

    for ticker, period, issues, lines in blocks:
        if args.issue and args.issue not in issues:
            continue
        print(f"\n=== {ticker} {period} [{', '.join(issues)}]")
        for line in lines:
            print(f"  {line}")

    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
