"""
Income statement waterfall reconciliation from SEC XBRL.

Two-step check:
    1. pretax_income - taxes            == net_income_incl_nci
    2. net_income_incl_nci - minority_interest == net_income

Also reports implied NCI (step 1 result minus net_income) against the tagged
NCI value, so a disagreement between them is visible rather than hidden.

Research tool. Not mapping approval.
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
    "revenue",
    "operating_income",
    "pretax_income",
    "taxes",
    "net_income_incl_nci",
    "minority_interest",
    "net_income",
]

TOLERANCE_USD = 1_000_000.0


def load_tickers() -> list[str]:
    return [
        line.strip().upper()
        for line in TICKERS_FILE.read_text().splitlines()
        if line.strip()
    ]


def load_sec_facts(client: SECEdgarClient, ticker: str) -> dict:
    cik = client.resolve_cik(ticker)
    cache_path = RUNLOGS / f"{ticker}_{cik}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    payload = client.fetch_companyfacts(ticker)
    cache_path.write_text(json.dumps(payload), encoding="utf-8")
    time.sleep(0.25)
    return payload


def latest_metrics(payload: dict, period_end: str | None = None) -> dict:
    """
    Select the latest annual fact per metric.

    If period_end is given, only facts ending on that date are considered, so
    every line in the waterfall comes from the same fiscal period.
    """
    out = {}
    for metric in METRICS:
        facts = select_annual_facts(payload, metric)
        if period_end:
            facts = [f for f in facts if f.get("end") == period_end]
        out[metric] = facts[0] if facts else None
    return out


def value_of(record: dict | None) -> float | None:
    if record is None:
        return None
    try:
        return float(record["value"])
    except (KeyError, TypeError, ValueError):
        return None


def millions(value: float | None) -> str:
    return f"{value / 1e6:,.0f}" if value is not None else "N/A"


def main() -> None:
    client = SECEdgarClient()
    RUNLOGS.mkdir(parents=True, exist_ok=True)
    rows = []

    header = (
        f"{'TICKER':<6} {'PERIOD':<11} {'PRETAX':>10} {'TAX':>9} "
        f"{'NI+NCI':>10} {'NCI':>8} {'NI':>10}  CHECK"
    )
    print(header)
    print("-" * len(header))

    for ticker in load_tickers():
        try:
            payload = load_sec_facts(client, ticker)

            anchor = latest_metrics(payload)
            anchor_record = (
                anchor.get("net_income")
                or anchor.get("pretax_income")
                or anchor.get("revenue")
            )
            period_end = anchor_record["end"] if anchor_record else None

            data = latest_metrics(payload, period_end=period_end)

            pretax = value_of(data["pretax_income"])
            taxes = value_of(data["taxes"])
            incl_nci = value_of(data["net_income_incl_nci"])
            nci_tagged = value_of(data["minority_interest"])
            net_income = value_of(data["net_income"])

            # Step 1: pretax - taxes == net income including NCI
            if pretax is not None and taxes is not None and incl_nci is not None:
                step1_diff = (pretax - taxes) - incl_nci
                step1 = "OK" if abs(step1_diff) < TOLERANCE_USD else "FAIL"
            else:
                step1_diff = None
                step1 = "N/A"

            # Step 2: net income including NCI - NCI == net income
            if incl_nci is not None and net_income is not None:
                implied_nci = incl_nci - net_income
                if nci_tagged is None:
                    step2_diff = implied_nci
                    step2 = "OK" if abs(implied_nci) < TOLERANCE_USD else "NCI_UNTAGGED"
                else:
                    step2_diff = implied_nci - nci_tagged
                    step2 = "OK" if abs(step2_diff) < TOLERANCE_USD else "NCI_DISAGREE"
            else:
                implied_nci = None
                step2_diff = None
                step2 = "N/A"

            status = "RECONCILES" if (step1 == "OK" and step2 == "OK") else f"{step1}/{step2}"

            print(
                f"{ticker:<6} {period_end or 'N/A':<11} "
                f"{millions(pretax):>10} {millions(taxes):>9} "
                f"{millions(incl_nci):>10} {millions(nci_tagged):>8} "
                f"{millions(net_income):>10}  {status}"
            )

            rows.append({
                "ticker": ticker,
                "period_end": period_end or "",
                "revenue": value_of(data["revenue"]) or "",
                "operating_income": value_of(data["operating_income"]) or "",
                "pretax_income": pretax if pretax is not None else "",
                "taxes": taxes if taxes is not None else "",
                "net_income_incl_nci": incl_nci if incl_nci is not None else "",
                "net_income_incl_nci_tag": (data["net_income_incl_nci"] or {}).get("tag", ""),
                "minority_interest_tagged": nci_tagged if nci_tagged is not None else "",
                "minority_interest_tag": (data["minority_interest"] or {}).get("tag", ""),
                "minority_interest_implied": implied_nci if implied_nci is not None else "",
                "net_income": net_income if net_income is not None else "",
                "step1_pretax_minus_tax_diff": step1_diff if step1_diff is not None else "",
                "step1_status": step1,
                "step2_nci_diff": step2_diff if step2_diff is not None else "",
                "step2_status": step2,
                "overall": status,
                "accession": (data["net_income"] or {}).get("accn", ""),
            })

        except Exception as error:
            print(f"{ticker:<6} ERROR: {error}")
            rows.append({"ticker": ticker, "overall": f"ERROR: {error}"})

    out_path = RUNLOGS / "income_statement_reconciliation.csv"
    fields = [
        "ticker", "period_end", "revenue", "operating_income", "pretax_income",
        "taxes", "net_income_incl_nci", "net_income_incl_nci_tag",
        "minority_interest_tagged", "minority_interest_tag",
        "minority_interest_implied", "net_income",
        "step1_pretax_minus_tax_diff", "step1_status",
        "step2_nci_diff", "step2_status", "overall", "accession",
    ]

    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print("-" * len(header))
    print(f"Wrote {out_path}")
    print("Values shown in $ millions. Reconciliation is evidence, not approval.")


if __name__ == "__main__":
    main()
