"""
Top-Half Operating Income Waterfall Reconciliation Engine.

Tests reported financial figures against the 4 recognized GAAP income statement archetypes:
    Archetype 1: Total Cost / Single Step (Revenue - Costs/Opex)
    Archetype 2: Commercial / Distribution (Gross Profit - SG&A)
    Archetype 3: Tech / R&D Heavy (Gross Profit - SG&A - R&D)
    Archetype 4: Multi-Line Industrial (Gross Profit - SG&A - [R&D] - Impairments - Restructuring + Equity)

Output:
    Dev_tools/xbrl/runlogs/top_half_archetype_summary.csv
"""

import csv
import json
from pathlib import Path

from northstar.data.sources.sec_edgar import SECEdgarClient
from northstar.data.transforms.sec_xbrl import select_annual_facts
from Dev_tools.xbrl.industry_map import industry_for

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
TICKERS_FILE = Path("Dev_tools/xbrl/tickers_100_usable.txt")
OUTPUT_FILE = RUNLOGS / "top_half_archetype_summary.csv"

TOL = 2_000_000.0  # $2M tolerance for rounding / minor line items

METRICS = [
    "revenue", "cogs", "gross_profit", "sga", "ga_expense", "rd",
    "operating_expenses", "operating_costs_and_expenses", "costs_and_expenses",
    "depreciation_amortization", "goodwill_impairment",
    "restructuring_charges", "asset_impairment",
    "equity_method_earnings", "operating_income"
]


def load_tickers() -> list[str]:
    return [line.strip().upper() for line in TICKERS_FILE.read_text().splitlines() if line.strip()]


def val(record: dict | None) -> float | None:
    if not record:
        return None
    try:
        return float(record["value"])
    except (KeyError, TypeError, ValueError):
        return None


def fmt(v: float | None) -> str:
    return "N/A" if v is None else f"{v / 1e6:,.1f}M"


def evaluate_top_half(v: dict) -> tuple[str, str, float | None]:
    """
    Evaluates top half numbers against the 4 operating income archetypes.
    Returns: (status, archetype_matched, gap)
    """
    op = v["operating_income"]
    rev = v["revenue"]
    gp = v["gross_profit"]
    cogs = v["cogs"]
    opex = v["operating_expenses"]
    operating_costs = v["operating_costs_and_expenses"]
    costs = v["costs_and_expenses"]
    da = v["depreciation_amortization"]
    sga = v["sga"] or v["ga_expense"]
    rd = v["rd"]
    gw = v["goodwill_impairment"] or 0.0
    impair = v["asset_impairment"] or 0.0
    restr = v["restructuring_charges"] or 0.0
    equity = v["equity_method_earnings"] or 0.0

    if op is None:
        return "NO_OPERATING_INCOME", "NONE", None

    # Determine gross profit anchor (use reported GP or derive Rev - COGS)
    gross_anchor = gp if gp is not None else (rev - cogs if rev is not None and cogs is not None else None)

    # -------------------------------------------------------------
    # Archetype 1: Total Cost / Single Step
    # -------------------------------------------------------------
    if rev is not None and costs is not None and abs((rev - costs) - op) <= TOL:
        return "RECONCILES", "ARCH_1_TOTAL_COSTS", abs((rev - costs) - op)
    if rev is not None and opex is not None and abs((rev - opex) - op) <= TOL:
        return "RECONCILES", "ARCH_1_OPERATING_EXPENSES", abs((rev - opex) - op)
    if gross_anchor is not None and opex is not None and abs((gross_anchor - opex) - op) <= TOL:
        return "RECONCILES", "ARCH_1_GROSS_MINUS_OPEX", abs((gross_anchor - opex) - op)

    # -------------------------------------------------------------
    # Archetype 1B: Service / Cruise Operating Cost Stack
    #
    # Revenue - OperatingCostsAndExpenses - SG&A - D&A = Operating Income
    # Example: CCL FY2025.
    # -------------------------------------------------------------
    if (
        rev is not None
        and operating_costs is not None
        and sga is not None
        and da is not None
    ):
        calc_op = rev - operating_costs - sga - da
        if abs(calc_op - op) <= TOL:
            return (
                "RECONCILES",
                "ARCH_1B_OPERATING_COSTS_SGA_DA",
                abs(calc_op - op),
            )

    # -------------------------------------------------------------
    # Archetype 2: Commercial / Distribution (Gross - SG&A)
    # -------------------------------------------------------------
    if gross_anchor is not None and sga is not None:
        calc_op = gross_anchor - sga
        if abs(calc_op - op) <= TOL:
            return "RECONCILES", "ARCH_2_COMMERCIAL_SGA_ONLY", abs(calc_op - op)

    # -------------------------------------------------------------
    # Archetype 3: Tech / R&D Heavy (Gross - SG&A - R&D)
    # -------------------------------------------------------------
    if gross_anchor is not None and sga is not None and rd is not None:
        calc_op = gross_anchor - sga - rd
        if abs(calc_op - op) <= TOL:
            return "RECONCILES", "ARCH_3_TECH_SGA_AND_RD", abs(calc_op - op)

    # -------------------------------------------------------------
    # Archetype 4: Multi-Line Industrial (Gross - SG&A - [R&D] - Impairments - Restructuring +/- Equity)
    # -------------------------------------------------------------
    if gross_anchor is not None and sga is not None:
        rd_deduct = rd if rd is not None else 0.0
        # Try combinations with non-recurring operating lines
        calc_op_multi = gross_anchor - sga - rd_deduct - gw - impair - restr
        if abs(calc_op_multi - op) <= TOL:
            return "RECONCILES", "ARCH_4_INDUSTRIAL_MULTI_LINE", abs(calc_op_multi - op)
        # Try with equity earnings operating component
        if abs((calc_op_multi + equity) - op) <= TOL:
            return "RECONCILES", "ARCH_4_INDUSTRIAL_WITH_EQUITY", abs((calc_op_multi + equity) - op)

    # If no exact match, compute best nearest gap
    candidates = []
    if rev is not None and costs is not None:
        candidates.append(("Total Costs", abs((rev - costs) - op)))
    if gross_anchor is not None and sga is not None:
        candidates.append(("Gross - SG&A", abs((gross_anchor - sga) - op)))
        if rd is not None:
            candidates.append(("Gross - SG&A - R&D", abs((gross_anchor - sga - rd) - op)))

    if candidates:
        candidates.sort(key=lambda x: x[1])
        return "MISMATCH", candidates[0][0], candidates[0][1]

    return "INCOMPLETE_DATA", "NONE", None


def main() -> None:
    client = SECEdgarClient()
    tickers = load_tickers()
    RUNLOGS.mkdir(parents=True, exist_ok=True)

    rows = []
    reconciled_count = 0
    no_opinc_count = 0

    print(f"{'TICKER':<6} {'PERIOD':<11} {'REV ($M)':>10} {'GROSS ($M)':>11} {'OPINC ($M)':>11} {'STATUS':<14} {'ARCHETYPE'}")
    print("-" * 95)

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

        status, archetype, gap = evaluate_top_half(v)

        if status == "RECONCILES":
            reconciled_count += 1
        elif status == "NO_OPERATING_INCOME":
            no_opinc_count += 1

        print(
            f"{ticker:<6} {period:<11} "
            f"{fmt(v['revenue']):>10} {fmt(v['gross_profit']):>11} {fmt(v['operating_income']):>11} "
            f"{status:<14} {archetype}"
        )

        rows.append({
            "ticker": ticker,
            "period_end": period,
            "revenue": v["revenue"] or "",
            "cogs": v["cogs"] or "",
            "gross_profit": v["gross_profit"] or "",
            "sga": v["sga"] or "",
            "rd": v["rd"] or "",
            "operating_costs_and_expenses": v["operating_costs_and_expenses"] or "",
            "operating_income": v["operating_income"] or "",
            "status": status,
            "archetype": archetype,
            "gap": gap if gap is not None else ""
        })

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print("-" * 95)
    print(f"Total Tickers Analyzed: {len(rows)}")
    print(f"Top-Half Reconciles:    {reconciled_count}")
    print(f"No Operating Income:    {no_opinc_count} (Banks / Financials)")
    print(f"Wrote summary to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
