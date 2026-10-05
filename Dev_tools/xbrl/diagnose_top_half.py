"""
Top-half residual diagnostic. Reads cached CompanyFacts only. No network downloads.

Fixes applied:
    - Do NOT substitute 0.0 for untagged sga/rd. Missing means missing.
    - Tighter match tolerance: max($2M, 0.1% of operating income).
    - Report raw sga/rd/opex/costs tagged state explicitly per company.

Output: Dev_tools/xbrl/runlogs/top_half_diagnostics.csv
"""

import csv
import json
from datetime import date
from pathlib import Path

from northstar.data.sources.sec_edgar import SECEdgarClient
from northstar.data.transforms.sec_xbrl import select_annual_facts

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
TICKERS = Path("Dev_tools/xbrl/tickers_100_usable.txt")
OUTPUT = RUNLOGS / "top_half_diagnostics.csv"
TOL = 1_000_000.0
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A"}
METRICS = ["revenue", "cogs", "gross_profit", "sga", "rd",
           "operating_expenses", "costs_and_expenses", "operating_income"]


def latest(payload, metric, period):
    facts = [f for f in select_annual_facts(payload, metric) if f.get("end") == period]
    try:
        return float(facts[0]["value"]) if facts else None
    except (TypeError, ValueError):
        return None


def fmt(v):
    return "N/A" if v is None else f"{v / 1e6:,.1f}M"


def simple_identity_holds(v):
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


def period_facts(payload, period):
    out = {}
    for taxonomy, concepts in payload.get("facts", {}).items():
        for tag, concept in concepts.items():
            for f in concept.get("units", {}).get("USD", []):
                if f.get("form") not in ANNUAL_FORMS or f.get("end") != period:
                    continue
                start = f.get("start")
                if not start:
                    continue
                try:
                    days = (date.fromisoformat(period) - date.fromisoformat(start)).days
                    value = float(f.get("val"))
                except (TypeError, ValueError):
                    continue
                if not 330 <= days <= 370:
                    continue
                key = f"{taxonomy}:{tag}"
                if key not in out or str(f.get("filed", "")) > out[key][1]:
                    out[key] = (value, str(f.get("filed", "")))
    return {k: v[0] for k, v in out.items()}


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
        if v["operating_income"] is None or simple_identity_holds(v):
            continue

        # Build base ONLY from components that are actually tagged. Track what's missing.
        sga, rd = v["sga"], v["rd"]
        missing = []
        if sga is None:
            missing.append("sga")
        if rd is None:
            missing.append("rd")

        if v["gross_profit"] is not None and sga is not None and rd is not None:
            base, base_name = v["gross_profit"] - sga - rd, "gross_profit - sga - rd"
        elif v["cogs"] is not None and sga is not None and rd is not None:
            base, base_name = v["revenue"] - v["cogs"] - sga - rd, "revenue - cogs - sga - rd"
        else:
            rows.append({
                "ticker": ticker, "period_end": period, "base_formula": "INSUFFICIENT_INPUTS",
                "operating_income": v["operating_income"], "base": "", "residual": "",
                "missing_inputs": "+".join(missing) if missing else "cogs/gross_profit",
                "match_1": "", "match_2": "", "match_3": "",
            })
            continue

        residual = base - v["operating_income"]
        facts = period_facts(payload, period)
        band = max(2_000_000.0, abs(v["operating_income"]) * 0.001)
        exclude_substrings = ("comprehensiveincome", "oci", "availableforsale",
                              "cashflowhedge", "deferredtax", "taxexaminationpenalt")
        hits = sorted(
            (abs(abs(val) - abs(residual)), key, val)
            for key, val in facts.items()
            if abs(abs(val) - abs(residual)) <= band
            and not any(s in key.lower().replace(":", "").replace("-", "") for s in exclude_substrings)
        )[:3]

        rows.append({
            "ticker": ticker, "period_end": period, "base_formula": base_name,
            "operating_income": v["operating_income"], "base": base, "residual": residual,
            "missing_inputs": "",
            "match_1": hits[0][1] if len(hits) > 0 else "",
            "match_2": hits[1][1] if len(hits) > 1 else "",
            "match_3": hits[2][1] if len(hits) > 2 else "",
        })

    with OUTPUT.open("w", newline="", encoding="utf-8") as h:
        if rows:
            w = csv.DictWriter(h, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    complete = [r for r in rows if r["base_formula"] != "INSUFFICIENT_INPUTS"]
    incomplete = [r for r in rows if r["base_formula"] == "INSUFFICIENT_INPUTS"]

    print(f"Total non-identity companies: {len(rows)}")
    print(f"  With complete sga+rd inputs: {len(complete)}")
    print(f"  Missing sga and/or rd:       {len(incomplete)}\n")

    print(f"{'T':<6} {'BASE':<26} {'OPINC':>11} {'RESIDUAL':>11}  SINGLE-TAG MATCH")
    for r in complete:
        print(f"{r['ticker']:<6} {r['base_formula']:<26} {fmt(r['operating_income']):>11} "
              f"{fmt(r['residual']):>11}  {r['match_1'] or '(none: likely combination)'}")

    print(f"\n{'T':<6} missing inputs")
    for r in incomplete:
        print(f"{r['ticker']:<6} {r['missing_inputs']}")

    print(f"\nWrote {OUTPUT}")


if __name__ == "__main__":
    main()
