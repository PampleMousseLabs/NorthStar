"""
Scaled Income Statement waterfall. Research tool, not a NorthStar source.

Scoring rules (evidence from 100-company runs):
  - Stale annual periods (year < 2024) never count as RECONCILES.
  - If no consolidated pretax tag exists, pretax = domestic + foreign
    (recorded in pretax_source; verified by the waterfall itself).
  - Untagged taxes are treated as 0.0 (self-correcting for pass-through REITs).
  - Bridge lines (equity method, discontinued ops) are applied only when the
    plain pretax - tax equation fails.
  - If net_income_incl_nci equals parent net_income, step 2 is OK even if a
    separate NCI tag exists.
  - Gross check uses inclusive $1M tolerance (10-K rounding).
"""

import argparse
import csv
import json
import math
import time
from collections import Counter
from itertools import combinations
from pathlib import Path

from northstar.data.sources.sec_edgar import SECEdgarClient
from northstar.data.transforms.sec_xbrl import select_annual_facts

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
TICKERS_SAMPLE = Path("Dev_tools/xbrl/tickers_sample.txt")
CONSTITUENTS = Path("Dev_tools/xbrl/constituents.csv")

METRICS = [
    "revenue", "cogs", "gross_profit", "sga", "rd",
    "operating_expenses", "depreciation_amortization",
    "operating_income", "interest_expense", "other_income",
    "pretax_income", "pretax_income_domestic", "pretax_income_foreign", "taxes",
    "equity_method_earnings", "discontinued_operations",
    "net_income_incl_nci", "minority_interest", "net_income", "net_income_to_common",
    "eps_basic", "eps_diluted", "shares_basic", "shares_diluted",
]
BRIDGE_METRICS = ("equity_method_earnings", "discontinued_operations")
TOL = 1_000_000.0
STALE_BEFORE_YEAR = 2024

SUMMARY_FIELDS = [
    "ticker", "period_end", "stale", "revenue", "cogs", "gross_profit", "gross_check",
    "operating_income", "pretax_income", "pretax_source",
    "pretax_income_domestic", "pretax_income_foreign", "taxes",
    "equity_method_earnings", "discontinued_operations", "step1_bridge",
    "net_income_incl_nci", "minority_interest_tagged", "minority_interest_implied",
    "net_income", "net_income_source", "net_income_note",
    "net_income_to_common", "parent_minus_common", "common_context_check",
    "net_income_accession", "net_income_filing_url",
    "step1_pretax_minus_tax", "step2_nci", "overall",
    "revenue_tag", "cogs_tag", "gross_tag", "opinc_tag", "pretax_tag",
    "tax_tag", "incl_nci_tag", "ni_tag",
]


def load_tickers(path: Path, limit: int) -> list[str]:
    tickers = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.lower().startswith(("ticker", "symbol")):
            continue
        first = line.split(",")[0].strip().strip('"').upper()
        if first and first not in tickers:
            tickers.append(first)
    return tickers[:limit]


def load_payload(client: SECEdgarClient, ticker: str) -> dict:
    cik = client.resolve_cik(ticker)
    cache = RUNLOGS / f"{ticker}_{cik}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    payload = client.fetch_companyfacts(ticker)
    cache.write_text(json.dumps(payload), encoding="utf-8")
    time.sleep(0.25)
    return payload


def val(record: dict | None) -> float | None:
    if not record:
        return None
    try:
        return float(record["value"])
    except (KeyError, TypeError, ValueError):
        return None


def blank(value):
    return "" if value is None else value


def close(a: float, b: float) -> bool:
    return abs(a - b) <= TOL


def is_stale(period_end: str | None) -> bool:
    if not period_end or not period_end[:4].isdigit():
        return False
    return int(period_end[:4]) < STALE_BEFORE_YEAR


def gross_check(rev, cogs, gross) -> str:
    if rev is not None and cogs is not None and gross is not None:
        return "OK" if abs((rev - cogs) - gross) <= TOL else "FAIL"
    if gross is None and rev is not None:
        return "NO_GROSS"
    return "N/A"


def resolve_pretax(tagged, domestic, foreign) -> tuple[float | None, str]:
    if tagged is not None:
        return tagged, "tagged"
    if domestic is not None:
        return domestic + (foreign if foreign is not None else 0.0), "derived_domestic_plus_foreign"
    return None, "missing"


def step1_check(pretax, taxes, incl, bridges: dict) -> tuple[str, str]:
    if pretax is None or incl is None:
        return "N/A", ""
    base = pretax - (taxes if taxes is not None else 0.0)
    available = [name for name, amount in bridges.items() if amount is not None]
    for size in range(len(available) + 1):
        for combo in combinations(available, size):
            total = base + sum(bridges[name] for name in combo)
            if close(total, incl):
                return "OK", "+".join(combo) or "none"
    return "FAIL", ""



def resolve_parent_net_income(reported, total, nci, common):
    """
    Research-only parent-income resolution.

    Prefer directly tagged NetIncomeLoss.
    Otherwise derive ProfitLoss minus TOTAL NCI only when both records have
    matching annual periods, USD units, and filing accession numbers.

    Filing evidence:
        CF FY2025, accession 0001324404-26-000007:
        1,798M consolidated earnings - 343M NCI = 1,455M to common.

    Derived values are not independent reconciliation evidence.
    """
    if reported is not None:
        number = val(reported)
        if (
            reported.get("taxonomy") == "us-gaap"
            and reported.get("tag") == "NetIncomeLoss"
            and number is not None
            and math.isfinite(number)
        ):
            return number, "tagged", ""
        return None, "missing", "Invalid directly reported parent-income fact"

    if total is not None:
        if (
            total.get("taxonomy") == "us-gaap"
            and total.get("tag") == "ProfitLoss"
        ):
            total_value = val(total)

            if nci is not None:
                if (
                    nci.get("taxonomy") != "us-gaap"
                    or nci.get("tag") != "NetIncomeLossAttributableToNoncontrollingInterest"
                ):
                    return None, "missing", "NCI candidate is not the total-NCI concept"

                if total.get("unit") != "USD" or nci.get("unit") != "USD":
                    return None, "missing", "Units do not match the required USD basis"

                for field in ("start", "end", "accn"):
                    if not total.get(field) or total.get(field) != nci.get(field):
                        return None, "missing", f"Total income and NCI differ on {field}"

                nci_value = val(nci)

                if (
                    total_value is None
                    or nci_value is None
                    or not math.isfinite(total_value)
                    or not math.isfinite(nci_value)
                ):
                    return None, "missing", "Non-numeric or non-finite income/NCI value"

                return (
                    total_value - nci_value,
                    "derived_incl_nci_minus_nci",
                    "ProfitLoss minus total NCI; matching period, unit and accession",
                )

            # No tagged NCI: allow common-shareholder income if present
            if common is not None:
                common_value = val(common)
                if (
                    common.get("taxonomy") == "us-gaap"
                    and common.get("tag") == "NetIncomeLossAvailableToCommonStockholdersBasic"
                    and common.get("unit") == "USD"
                    and common_value is not None
                    and math.isfinite(common_value)
                ):
                    return (
                        common_value,
                        "fallback_common_stockholders_basic",
                        "No NetIncomeLoss/NCI; used common-stockholder income",
                    )

            # No NCI and no common fallback: use ProfitLoss explicitly as total-only fallback.
            if total_value is not None and math.isfinite(total_value):
                return (
                    total_value,
                    "fallback_profitloss_no_nci_tag",
                    "No NetIncomeLoss, no NCI and no common-income tag; used ProfitLoss",
                )

    return None, "missing", "No valid parent-income fact or fallback"


def step2_check(incl, ni, tagged_nci) -> tuple[str, float | None]:
    if incl is None or ni is None:
        return "N/A", None
    implied = incl - ni
    if close(incl, ni):
        # ProfitLoss equals parent net_income: only pass if the tagged NCI is
        # either missing or matches the implied NCI. This removes false
        # positives like AEE/AEP/AMT/BSX/CAT/CF/BALL.
        if tagged_nci is None:
            return "OK", implied
        return ("OK" if close(implied, tagged_nci) else "NCI_MISMATCH"), implied
    if tagged_nci is None:
        return ("OK" if abs(implied) <= TOL else "NCI_UNTAGGED"), implied
    return ("OK" if close(implied, tagged_nci) else "NCI_MISMATCH"), implied


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--file", type=str, default="")
    args = parser.parse_args()

    if args.file:
        ticker_path = Path(args.file)
    elif CONSTITUENTS.exists():
        ticker_path = CONSTITUENTS
    else:
        ticker_path = TICKERS_SAMPLE

    tickers = load_tickers(ticker_path, args.limit)
    print(f"Loaded {len(tickers)} tickers from {ticker_path}")

    client = SECEdgarClient()
    RUNLOGS.mkdir(parents=True, exist_ok=True)

    summary_rows = []
    tag_counter = Counter()
    bridge_counter = Counter()
    pretax_source_counter = Counter()

    for idx, ticker in enumerate(tickers, start=1):
        print(f"[{idx}/{len(tickers)}] {ticker}")
        try:
            payload = load_payload(client, ticker)
            anchor = select_annual_facts(payload, "revenue") or select_annual_facts(payload, "net_income")
            period_end = anchor[0]["end"] if anchor else None
            stale = is_stale(period_end)

            data = {}
            for metric in METRICS:
                facts = select_annual_facts(payload, metric)
                if period_end:
                    facts = [f for f in facts if f.get("end") == period_end]
                data[metric] = facts[0] if facts else None
                if data[metric]:
                    tag_counter[(metric, data[metric].get("tag", ""))] += 1

            rev, cogs, gross = val(data["revenue"]), val(data["cogs"]), val(data["gross_profit"])
            domestic, foreign = val(data["pretax_income_domestic"]), val(data["pretax_income_foreign"])
            pretax, pretax_source = resolve_pretax(val(data["pretax_income"]), domestic, foreign)
            pretax_source_counter[pretax_source] += 1
            taxes = val(data["taxes"])
            incl, tagged_nci, ni = (
                val(data["net_income_incl_nci"]),
                val(data["minority_interest"]),
                val(data["net_income"]),
            )
            ni_common = val(data["net_income_to_common"])
            ni, ni_source, ni_note = resolve_parent_net_income(
                data["net_income"],
                data["net_income_incl_nci"],
                data["minority_interest"],
                data["net_income_to_common"],
            )
            parent_minus_common = (
                ni - ni_common
                if ni is not None and ni_common is not None
                else None
            )

            ni_basis = (
                data["net_income"]
                if ni_source == "tagged"
                else data["net_income_incl_nci"]
                if ni_source.startswith("derived")
                else None
            )
            common_record = data["net_income_to_common"]
            common_context_check = "NO_COMPARISON"

            if ni_basis is not None and common_record is not None:
                same_context = all(
                    ni_basis.get(field)
                    and ni_basis.get(field) == common_record.get(field)
                    for field in ("start", "end", "accn", "unit")
                )
                common_context_check = (
                    "SAME_PERIOD_FILING_UNIT"
                    if same_context
                    else "CONTEXT_DIFFERENCE_REVIEW"
                )

            ni_accession = (ni_basis or {}).get("accn", "")
            cik_text = str(payload.get("cik", ""))
            ni_filing_url = ""
            if ni_accession and cik_text.isdigit():
                ni_filing_url = (
                    "https://www.sec.gov/Archives/edgar/data/"
                    f"{int(cik_text)}/{ni_accession.replace('-', '')}/"
                    f"{ni_accession}-index.htm"
                )
            bridges = {name: val(data[name]) for name in BRIDGE_METRICS}

            g_chk = gross_check(rev, cogs, gross)
            step1, bridge_used = step1_check(pretax, taxes, incl, bridges)
            if step1 == "OK":
                bridge_counter[bridge_used] += 1
            step2, implied_nci = step2_check(incl, ni, tagged_nci)
            if ni_source.startswith("derived"):
                # The equation used to derive NI cannot independently validate it.
                step2 = "DERIVED_NOT_INDEPENDENT"

            if stale:
                overall = "STALE"
            elif step1 == "OK" and step2 == "OK" and g_chk in ("OK", "NO_GROSS"):
                overall = "RECONCILES"
            else:
                overall = f"{g_chk}/{step1}/{step2}"

            summary_rows.append({
                "ticker": ticker,
                "period_end": period_end or "",
                "stale": stale,
                "revenue": blank(rev),
                "cogs": blank(cogs),
                "gross_profit": blank(gross),
                "gross_check": g_chk,
                "operating_income": blank(val(data["operating_income"])),
                "pretax_income": blank(pretax),
                "pretax_source": pretax_source,
                "pretax_income_domestic": blank(domestic),
                "pretax_income_foreign": blank(foreign),
                "taxes": blank(taxes),
                "equity_method_earnings": blank(bridges["equity_method_earnings"]),
                "discontinued_operations": blank(bridges["discontinued_operations"]),
                "step1_bridge": bridge_used,
                "net_income_incl_nci": blank(incl),
                "minority_interest_tagged": blank(tagged_nci),
                "minority_interest_implied": blank(implied_nci),
                "net_income": blank(ni),
                "net_income_source": ni_source,
                "net_income_note": ni_note,
                "net_income_to_common": blank(ni_common),
                "parent_minus_common": blank(parent_minus_common),
                "common_context_check": common_context_check,
                "net_income_accession": ni_accession,
                "net_income_filing_url": ni_filing_url,
                "step1_pretax_minus_tax": step1,
                "step2_nci": step2,
                "overall": overall,
                "revenue_tag": (data["revenue"] or {}).get("tag", ""),
                "cogs_tag": (data["cogs"] or {}).get("tag", ""),
                "gross_tag": (data["gross_profit"] or {}).get("tag", ""),
                "opinc_tag": (data["operating_income"] or {}).get("tag", ""),
                "pretax_tag": (data["pretax_income"] or {}).get("tag", ""),
                "tax_tag": (data["taxes"] or {}).get("tag", ""),
                "incl_nci_tag": (data["net_income_incl_nci"] or {}).get("tag", ""),
                "ni_tag": (data["net_income"] or {}).get("tag", ""),
            })

        except Exception as error:
            print(f"  ERROR {error}")
            summary_rows.append({"ticker": ticker, "overall": f"ERROR {error}", "stale": False})

    out_summary = RUNLOGS / "scaled_is_summary.csv"
    out_tags = RUNLOGS / "scaled_tag_selection.csv"

    with out_summary.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary_rows)

    with out_tags.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "tag", "count"])
        for (metric, tag), count in tag_counter.most_common():
            writer.writerow([metric, tag, count])

    reconciles = sum(1 for r in summary_rows if r.get("overall") == "RECONCILES")
    stale_count = sum(1 for r in summary_rows if r.get("overall") == "STALE")
    errors = sum(1 for r in summary_rows if str(r.get("overall", "")).startswith("ERROR"))

    print(f"\nWrote {out_summary} ({len(summary_rows)} rows)")
    print(f"Wrote {out_tags}")
    print(f"\nRECONCILES: {reconciles}/{len(summary_rows)}")
    print(f"STALE:      {stale_count}")
    print(f"ERROR:      {errors}")

    print("\nPretax source:")
    for source, count in pretax_source_counter.most_common():
        print(f"  {source:<50} {count}")

    print("\nStep-1 bridge used (step1 OK rows):")
    for bridge, count in bridge_counter.most_common():
        print(f"  {bridge:<50} {count}")

    print("\nNot reconciling:")
    for r in summary_rows:
        if r.get("overall") != "RECONCILES":
            print(f"  {r['ticker']:<6} {str(r.get('period_end', '')):<11} "
                  f"{r.get('overall', ''):<32} pretax={r.get('pretax_source', '')}")


if __name__ == "__main__":
    main()
