"""
Top-half income-statement validation with adjustment bridges. Research tool.

A company RECONCILES when a formula built only from tagged standard XBRL
metrics reproduces reported OperatingIncomeLoss within $2M.

Method:
    1. Try base formulas (total-cost, gross-profit, CCL cost-stack).
    2. If no base closes exactly, retry each base with up to 3 tagged
       adjustment lines (D&A, impairments, restructuring, equity earnings).
       Mirrors the bridge approach proven for pretax -> net income.
    3. Every adjustment used is recorded. Untagged adjustments are never
       assumed. No company-specific concepts are used.

Caveat: an exact match within $2M is strong evidence, not proof. Every match
lists its formula and adjustments in the output CSV for review.

Output:
    Dev_tools/xbrl/runlogs/top_half_archetype_summary.csv
"""

import csv
import json
from collections import Counter
from itertools import combinations
from pathlib import Path

from northstar.data.sources.sec_edgar import SECEdgarClient
from northstar.data.transforms.sec_xbrl import select_annual_facts
from Dev_tools.xbrl.industry_map import industry_for

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
TICKERS_FILE = Path("Dev_tools/xbrl/tickers_100_usable.txt")
OUTPUT_FILE = RUNLOGS / "top_half_archetype_summary.csv"

TOL = 2_000_000.0
MAX_ADJUSTMENTS = 4

METRICS = [
    "revenue", "cogs", "gross_profit", "sga", "ga_expense", "rd",
    "operating_expenses", "operating_costs_and_expenses", "costs_and_expenses",
    "depreciation_amortization", "goodwill_impairment",
    "restructuring_charges", "asset_impairment",
    "equity_method_earnings", "other_operating_income", "operating_income",
]

# Adjustments that may sit between a base subtotal and operating income.
# sign is applied to the tagged XBRL value: expenses subtract, income adds.
ADJUSTMENTS = (
    ("depreciation_amortization", "d&a", -1.0),
    ("goodwill_impairment", "goodwill_impairment", -1.0),
    ("asset_impairment", "asset_impairment", -1.0),
    ("restructuring_charges", "restructuring", -1.0),
    ("equity_method_earnings", "equity_method_earnings", 1.0),
    ("other_operating_income", "other_operating_net", 1.0),
)


def load_tickers() -> list[str]:
    return [
        line.strip().upper()
        for line in TICKERS_FILE.read_text().splitlines()
        if line.strip()
    ]


def val(record: dict | None) -> float | None:
    if not record:
        return None
    try:
        return float(record["value"])
    except (KeyError, TypeError, ValueError):
        return None


def fmt(v: float | None) -> str:
    return "N/A" if v is None else f"{v / 1e6:,.1f}M"


def base_formulas(v: dict) -> list[tuple[str, float]]:
    """
    Ordered base formulas using only tagged standard metrics.
    sga falls back to ga_expense (GeneralAndAdministrativeExpense).
    First exact match wins.
    """
    rev = v["revenue"]
    cogs = v["cogs"]
    gross = v["gross_profit"]
    opex = v["operating_expenses"]
    op_costs = v["operating_costs_and_expenses"]
    costs = v["costs_and_expenses"]
    sga = v["sga"] if v["sga"] is not None else v["ga_expense"]
    rd = v["rd"]
    da = v["depreciation_amortization"]

    gross_anchor = gross
    if gross_anchor is None and rev is not None and cogs is not None:
        gross_anchor = rev - cogs

    bases = []

    if rev is not None and costs is not None:
        bases.append(("revenue - costs_and_expenses", rev - costs))
    if gross_anchor is not None and opex is not None:
        bases.append(("gross_profit - operating_expenses", gross_anchor - opex))
    if rev is not None and opex is not None:
        bases.append(("revenue - operating_expenses", rev - opex))
    if rev is not None and op_costs is not None and sga is not None and da is not None:
        # CCL evidence: 26,622 - 15,947 - 3,402 - 2,790 = 4,483 exact
        bases.append(("revenue - operating_costs - sga - d&a", rev - op_costs - sga - da))
    if gross_anchor is not None and sga is not None:
        bases.append(("gross_profit - sga", gross_anchor - sga))
    if gross_anchor is not None and sga is not None and rd is not None:
        bases.append(("gross_profit - sga - rd", gross_anchor - sga - rd))
    if rev is not None and cogs is not None and sga is not None:
        bases.append(("revenue - cogs - sga", rev - cogs - sga))
    if rev is not None and cogs is not None and sga is not None and rd is not None:
        bases.append(("revenue - cogs - sga - rd", rev - cogs - sga - rd))

    return bases


def evaluate_top_half(v: dict) -> tuple[str, str, float | None, str]:
    """
    Returns (status, formula, residual, adjustments_used).

    status: RECONCILES | MISMATCH | INCOMPLETE_DATA | NO_OPERATING_INCOME
    """
    op = v["operating_income"]
    if op is None:
        return "NO_OPERATING_INCOME", "NONE", None, ""

    bases = base_formulas(v)
    if not bases:
        return "INCOMPLETE_DATA", "NONE", None, ""

    tagged_adjustments = [
        (short, sign, v[metric])
        for metric, short, sign in ADJUSTMENTS
        if v[metric] is not None
    ]

    best_name = ""
    best_gap = None

    for base_name, base_value in bases:
        gap = abs(base_value - op)
        if best_gap is None or gap < best_gap:
            best_gap = gap
            best_name = base_name

        if gap <= TOL:
            return "RECONCILES", base_name, gap, ""

        for size in range(1, min(MAX_ADJUSTMENTS, len(tagged_adjustments)) + 1):
            for combo in combinations(tagged_adjustments, size):
                adjustment_total = sum(sign * value for _, sign, value in combo)
                calc = base_value + adjustment_total
                if abs(calc - op) <= TOL:
                    adj_names = "+".join(short for short, _, _ in combo)
                    return (
                        "RECONCILES",
                        f"{base_name} | adj({adj_names})",
                        abs(calc - op),
                        adj_names,
                    )

    return "MISMATCH", best_name, best_gap, ""


def main() -> None:
    client = SECEdgarClient()
    tickers = load_tickers()
    RUNLOGS.mkdir(parents=True, exist_ok=True)

    rows = []
    adjustment_counter = Counter()
    with_adjustment = 0

    print(f"{'TICKER':<6} {'PERIOD':<11} {'REV ($M)':>10} {'OPINC ($M)':>11} {'STATUS':<20} {'FORMULA'}")
    print("-" * 110)

    for ticker in tickers:
        try:
            cik = client.resolve_cik(ticker)
        except Exception:
            continue

        cache = RUNLOGS / f"{ticker}_{cik}.json"
        if not cache.exists():
            continue

        payload = json.loads(cache.read_text(encoding="utf-8"))
        industry = industry_for(ticker)

        anchor = select_annual_facts(payload, "revenue", industry=industry)
        if not anchor:
            continue
        period = anchor[0]["end"]

        v = {}
        for m in METRICS:
            facts = select_annual_facts(payload, m, industry=industry)
            if period:
                facts = [f for f in facts if f.get("end") == period]
            v[m] = val(facts[0] if facts else None)

        status, formula, gap, adjustments = evaluate_top_half(v)

        if status == "RECONCILES" and adjustments:
            with_adjustment += 1
            for name in adjustments.split("+"):
                adjustment_counter[name] += 1

        print(
            f"{ticker:<6} {period:<11} {fmt(v['revenue']):>10} {fmt(v['operating_income']):>11} "
            f"{status:<20} {formula}"
        )

        rows.append({
            "ticker": ticker,
            "period_end": period,
            "revenue": v["revenue"] or "",
            "cogs": v["cogs"] or "",
            "gross_profit": v["gross_profit"] or "",
            "sga": v["sga"] or "",
            "rd": v["rd"] or "",
            "operating_income": v["operating_income"] or "",
            "status": status,
            "archetype": formula,
            "adjustments_used": adjustments,
            "residual": gap if gap is not None else "",
        })

    fields = [
        "ticker", "period_end", "revenue", "cogs", "gross_profit", "sga", "rd",
        "operating_income", "status", "archetype", "adjustments_used", "residual",
    ]

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    reconciles = sum(1 for r in rows if r["status"] == "RECONCILES")
    no_opinc = sum(1 for r in rows if r["status"] == "NO_OPERATING_INCOME")
    mismatch = sum(1 for r in rows if r["status"] == "MISMATCH")
    incomplete = sum(1 for r in rows if r["status"] == "INCOMPLETE_DATA")

    print("-" * 110)
    print(f"Total analyzed:          {len(rows)}")
    print(f"RECONCILES:              {reconciles}  ({reconciles - with_adjustment} base only, {with_adjustment} with adjustments)")
    print(f"NO_OPERATING_INCOME:     {no_opinc}")
    print(f"MISMATCH:                {mismatch}")
    print(f"INCOMPLETE_DATA:         {incomplete}")

    if adjustment_counter:
        print("\nAdjustments that closed a gap:")
        for name, count in adjustment_counter.most_common():
            print(f"  {name:<25} {count}")

    print("\nStill MISMATCH (residual size shows severity):")
    for r in rows:
        if r["status"] == "MISMATCH":
            residual = r["residual"]
            residual_m = f"{float(residual) / 1e6:,.1f}M" if residual != "" else "N/A"
            print(f"  {r['ticker']:<6} {r['period_end']:<11} residual={residual_m:>12}  nearest={r['archetype']}")

    print(f"\nWrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
