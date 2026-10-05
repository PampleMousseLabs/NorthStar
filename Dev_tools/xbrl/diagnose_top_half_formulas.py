"""
Top-half formula diagnostic. Cached CompanyFacts only. No downloads.

Targets companies with tagged operating income where no simple identity holds.
Tries base formulas using only tagged components, then base plus up to 2
operating adjustments (D&A, impairments, restructuring, equity earnings).

Output: Dev_tools/xbrl/runlogs/top_half_formula_diagnostics.csv
"""

import csv
import itertools
import json
from pathlib import Path

from northstar.data.sources.sec_edgar import SECEdgarClient
from northstar.data.transforms.sec_xbrl import select_annual_facts

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
TICKERS = Path("Dev_tools/xbrl/tickers_100_usable.txt")
OUTPUT = RUNLOGS / "top_half_formula_diagnostics.csv"
TOL = 1_000_000.0
METRICS = ["revenue", "cogs", "gross_profit", "sga", "ga_expense", "rd",
           "operating_expenses", "costs_and_expenses",
           "depreciation_amortization", "goodwill_impairment",
           "restructuring_charges", "asset_impairment",
           "equity_method_earnings", "operating_income"]


def latest(payload, metric, period):
    facts = [f for f in select_annual_facts(payload, metric) if f.get("end") == period]
    try:
        return float(facts[0]["value"]) if facts else None
    except (TypeError, ValueError):
        return None


def fmt(v):
    return "N/A" if v is None else f"{v / 1e6:,.1f}M"


def simple_holds(v):
    rev, gp, opex, costs, op = (v["revenue"], v["gross_profit"],
                                v["operating_expenses"], v["costs_and_expenses"],
                                v["operating_income"])
    checks = []
    if rev is not None and costs is not None:
        checks.append(rev - costs)
    if gp is not None and opex is not None:
        checks.append(gp - opex)
    if rev is not None and opex is not None:
        checks.append(rev - opex)
    return any(abs(c - op) <= TOL for c in checks)


def main():
    client = SECEdgarClient()
    tickers = [l.strip().upper() for l in TICKERS.read_text().splitlines() if l.strip()]
    rows = []

    for ticker in tickers:
        try:
            cik = client.resolve_cik(ticker)
        except Exception:
            continue
        cache = RUNLOGS / f"{ticker}_{cik}.json"
        if not cache.exists():
            continue
        payload = json.loads(cache.read_text(encoding="utf-8"))
        anchor = select_annual_facts(payload, "revenue")
        if not anchor:
            continue
        period = anchor[0]["end"]
        v = {m: latest(payload, m, period) for m in METRICS}
        if v["operating_income"] is None or simple_holds(v):
            continue

        rev, cogs, gross = v["revenue"], v["cogs"], v["gross_profit"]
        sga, ga, rd = v["sga"], v["ga_expense"], v["rd"]
        opex, costs = v["operating_expenses"], v["costs_and_expenses"]
        op = v["operating_income"]

        bases = []
        if rev is not None and costs is not None:
            bases.append(("revenue - costs", rev - costs))
        if gross is not None and opex is not None:
            bases.append(("gross - opex", gross - opex))
        if rev is not None and opex is not None:
            bases.append(("revenue - opex", rev - opex))
        if gross is not None and sga is not None:
            bases.append(("gross - sga", gross - sga))
        if gross is not None and sga is not None and rd is not None:
            bases.append(("gross - sga - rd", gross - sga - rd))
        if gross is not None and ga is not None:
            bases.append(("gross - ga", gross - ga))
        if gross is not None and ga is not None and rd is not None:
            bases.append(("gross - ga - rd", gross - ga - rd))
        if rev is not None and cogs is not None and sga is not None:
            bases.append(("rev - cogs - sga", rev - cogs - sga))
        if rev is not None and cogs is not None and sga is not None and rd is not None:
            bases.append(("rev - cogs - sga - rd", rev - cogs - sga - rd))
        if rev is not None and cogs is not None and ga is not None:
            bases.append(("rev - cogs - ga", rev - cogs - ga))
        if rev is not None and cogs is not None and ga is not None and rd is not None:
            bases.append(("rev - cogs - ga - rd", rev - cogs - ga - rd))

        adjustments = []
        if v["depreciation_amortization"] is not None:
            adjustments.append((" - da", -v["depreciation_amortization"]))
        if v["goodwill_impairment"] is not None:
            adjustments.append((" - gw", -v["goodwill_impairment"]))
        if v["restructuring_charges"] is not None:
            adjustments.append((" - restruct", -v["restructuring_charges"]))
        if v["asset_impairment"] is not None:
            adjustments.append((" - impair", -v["asset_impairment"]))
        if v["equity_method_earnings"] is not None:
            adjustments.append((" + equity", v["equity_method_earnings"]))

        matches = []
        nearest_name = ""
        nearest_gap = None

        for base_name, base_value in bases:
            gap = abs(base_value - op)
            if nearest_gap is None or gap < nearest_gap:
                nearest_gap, nearest_name = gap, base_name
            if gap <= TOL:
                matches.append(base_name)
            for size in (1, 2):
                if len(adjustments) < size:
                    continue
                for combo in itertools.combinations(adjustments, size):
                    name = base_name + "".join(n for n, _ in combo)
                    value = base_value + sum(x for _, x in combo)
                    gap2 = abs(value - op)
                    if gap2 < nearest_gap:
                        nearest_gap, nearest_name = gap2, name
                    if gap2 <= TOL and name not in matches:
                        matches.append(name)

        tagged = ",".join(m for m in METRICS if v[m] is not None)
        rows.append({
            "ticker": ticker,
            "period_end": period,
            "operating_income": op,
            "bases_tried": len(bases),
            "match_count": len(matches),
            "matching_formulas": " | ".join(matches[:3]),
            "nearest_formula": nearest_name,
            "nearest_gap": "" if nearest_gap is None else nearest_gap,
            "tagged": tagged,
        })

    with OUTPUT.open("w", newline="", encoding="utf-8") as h:
        if rows:
            w = csv.DictWriter(h, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    with_match = [r for r in rows if r["match_count"] > 0]
    print(f"Targets: {len(rows)}  with formula match: {len(with_match)}\n")
    print(f"{'T':<6} {'MATCHES':<45} {'NEAREST GAP':>11}  NEAREST FORMULA")
    for r in rows:
        m = r["matching_formulas"][:45] if r["matching_formulas"] else "(none)"
        g = r["nearest_gap"]
        gstr = fmt(g) if g != "" else "N/A"
        print(f"{r['ticker']:<6} {m:<45} {gstr:>11}  {r['nearest_formula'][:50]}")
    print(f"\nWrote {OUTPUT}")


if __name__ == "__main__":
    main()
