"""
Top-half income statement checks from SEC XBRL, same fiscal period per ticker.

Checks:
    A. revenue - cogs == gross_profit      (only where all three are tagged)
    B. eps_diluted * shares_diluted ~= net_income
       Banks with preferred dividends will show a gap: EPS is based on
       net income applicable to common, not total net income.

Research only. Not mapping approval.
"""

import csv
import json
import time
from pathlib import Path

from northstar.data.sources.sec_edgar import SECEdgarClient
from northstar.data.transforms.sec_xbrl import select_annual_facts

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
TICKERS_FILE = Path("Dev_tools/xbrl/tickers_sample.txt")

METRICS = [
    "revenue", "cogs", "gross_profit", "sga", "rd", "operating_expenses",
    "depreciation_amortization", "operating_income", "interest_expense",
    "eps_basic", "eps_diluted", "shares_basic", "shares_diluted", "net_income",
]

TOLERANCE_USD = 1_000_000.0


def load_tickers() -> list[str]:
    return [
        line.strip().upper()
        for line in TICKERS_FILE.read_text().splitlines()
        if line.strip()
    ]


def load_payload(client: SECEdgarClient, ticker: str) -> dict:
    cik = client.resolve_cik(ticker)
    path = RUNLOGS / f"{ticker}_{cik}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    payload = client.fetch_companyfacts(ticker)
    path.write_text(json.dumps(payload), encoding="utf-8")
    time.sleep(0.25)
    return payload


def value_of(record: dict | None) -> float | None:
    if not record:
        return None
    try:
        return float(record["value"])
    except (KeyError, TypeError, ValueError):
        return None


def fmt_millions(value: float | None) -> str:
    return f"{value / 1e6:,.0f}" if value is not None else "N/A"


def gross_check(rev, cogs, gross) -> str:
    if rev is not None and cogs is not None and gross is not None:
        diff = (rev - cogs) - gross
        return "OK" if abs(diff) < TOLERANCE_USD else f"DIFF {diff / 1e6:,.0f}M"
    if gross is None:
        return "NO_GROSS_TAG"
    return "NO_COGS_TAG"


def eps_check(eps, shares, net_income) -> tuple[str, float | None]:
    if eps is None or shares is None or not net_income:
        return "N/A", None
    implied = eps * shares
    pct = (implied / net_income - 1.0) * 100.0
    return ("OK" if abs(pct) <= 2.0 else "REVIEW"), pct


def main() -> None:
    client = SECEdgarClient()
    rows = []

    header = (
        f"{'T':<5} {'PERIOD':<11} {'REV':>10} {'COGS':>10} {'GROSS':>10} "
        f"{'GROSS_CHK':<13} {'OPINC':>9} {'EPS_d':>7} {'SH_d(M)':>8} "
        f"{'NI':>9} {'EPSxSH_CHK':<16}"
    )
    print(header)
    print("-" * len(header))

    for ticker in load_tickers():
        try:
            payload = load_payload(client, ticker)

            anchor = select_annual_facts(payload, "revenue") or select_annual_facts(payload, "net_income")
            period = anchor[0]["end"] if anchor else None

            data = {}
            for metric in METRICS:
                facts = select_annual_facts(payload, metric)
                if period:
                    facts = [f for f in facts if f.get("end") == period]
                data[metric] = facts[0] if facts else None

            rev = value_of(data["revenue"])
            cogs = value_of(data["cogs"])
            gross = value_of(data["gross_profit"])
            opinc = value_of(data["operating_income"])
            eps_d = value_of(data["eps_diluted"])
            sh_d = value_of(data["shares_diluted"])
            ni = value_of(data["net_income"])

            g_chk = gross_check(rev, cogs, gross)
            e_status, e_pct = eps_check(eps_d, sh_d, ni)
            e_label = e_status if e_pct is None else f"{e_status} {e_pct:+.1f}%"

            print(
                f"{ticker:<5} {period or 'N/A':<11} "
                f"{fmt_millions(rev):>10} {fmt_millions(cogs):>10} {fmt_millions(gross):>10} "
                f"{g_chk:<13} {fmt_millions(opinc):>9} "
                f"{(f'{eps_d:.2f}' if eps_d is not None else 'N/A'):>7} "
                f"{fmt_millions(sh_d):>8} {fmt_millions(ni):>9} {e_label:<16}"
            )

            row = {"ticker": ticker, "period_end": period or "", "gross_check": g_chk,
                   "eps_check": e_status, "eps_check_pct": "" if e_pct is None else round(e_pct, 3)}
            for metric in METRICS:
                v = value_of(data[metric])
                row[metric] = "" if v is None else v
                row[f"{metric}_tag"] = (data[metric] or {}).get("tag", "")
            rows.append(row)

        except Exception as error:
            print(f"{ticker:<5} ERROR {error}")
            rows.append({"ticker": ticker, "gross_check": f"ERROR {error}"})

    fields = ["ticker", "period_end", "gross_check", "eps_check", "eps_check_pct"]
    for metric in METRICS:
        fields += [metric, f"{metric}_tag"]

    out_path = RUNLOGS / "is_top_waterfall.csv"
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print("-" * len(header))
    print(f"Wrote {out_path}")
    print("Values in $ millions except EPS. Research evidence, not approval.")


if __name__ == "__main__":
    main()
