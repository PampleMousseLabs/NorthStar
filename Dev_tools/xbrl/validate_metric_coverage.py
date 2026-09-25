"""
Validate NorthStar SEC XBRL metric mappings across a ticker sample.

Writes two files:
  runlogs/coverage_<metric>_summary.csv  one row per ticker (readable)
  runlogs/coverage_<metric>_detail.csv   one row per ticker-period, with filing URL

Flags:
  NO_MATCH  dictionary produced nothing
  STALE     latest annual period is older than ~18 months
  MIXED     history stitched across more than one concept (informational)
"""

import csv
import json
import sys
import time
from datetime import date
from pathlib import Path

from northstar.data.sources.sec_edgar import SECEdgarClient
from northstar.data.transforms.sec_xbrl import select_annual_facts

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
TICKERS_FILE = Path("Dev_tools/xbrl/tickers_sample.txt")
STALE_DAYS = 550


def load_tickers() -> list[str]:
    return [
        line.strip().upper()
        for line in TICKERS_FILE.read_text().splitlines()
        if line.strip()
    ]


def load_companyfacts(client: SECEdgarClient, ticker: str, cik: str) -> dict:
    cache_path = RUNLOGS / f"{ticker}_{cik}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    payload = client.fetch_companyfacts(ticker)
    cache_path.write_text(json.dumps(payload))
    time.sleep(0.3)
    return payload


def filing_url(cik: str, accn: str) -> str:
    """Build a direct link to the filing index so a mapping can be verified."""
    if not accn:
        return ""
    cik_plain = str(int(cik))
    accn_nodash = accn.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{cik_plain}/{accn_nodash}/{accn}-index.htm"
    )


def main() -> None:
    metric = sys.argv[1] if len(sys.argv) > 1 else "revenue"
    tickers = load_tickers()
    client = SECEdgarClient()
    RUNLOGS.mkdir(parents=True, exist_ok=True)

    summary_rows = []
    detail_rows = []
    today = date.today()

    for index, ticker in enumerate(tickers, start=1):
        print(f"[{index}/{len(tickers)}] {ticker}: {metric}")

        try:
            cik = client.resolve_cik(ticker)
            companyfacts = load_companyfacts(client, ticker, cik)
            facts = select_annual_facts(companyfacts, metric)
        except Exception as error:
            summary_rows.append({
                "ticker": ticker, "metric": metric, "status": "ERROR",
                "note": str(error), "latest_tag": "", "latest_end": "",
                "latest_value": "", "earliest_end": "", "periods": 0,
                "distinct_tags": "", "latest_filing_url": "",
            })
            print(f"  ERROR: {error}")
            continue

        if not facts:
            summary_rows.append({
                "ticker": ticker, "metric": metric, "status": "NO_MATCH",
                "note": "dictionary produced no annual facts", "latest_tag": "",
                "latest_end": "", "latest_value": "", "earliest_end": "",
                "periods": 0, "distinct_tags": "", "latest_filing_url": "",
            })
            print("  NO_MATCH")
            continue

        for fact in facts:
            detail_rows.append({
                "ticker": ticker,
                "metric": metric,
                "period_end": fact["end"],
                "period_start": fact["start"],
                "value": fact["value"],
                "taxonomy": fact["taxonomy"],
                "tag": fact["tag"],
                "form": fact["form"],
                "filed": fact["filed"],
                "accn": fact["accn"],
                "filing_url": filing_url(cik, fact["accn"]),
            })

        latest = facts[0]
        earliest = facts[-1]
        distinct_tags = sorted({f["tag"] for f in facts})

        age_days = (today - date.fromisoformat(latest["end"])).days
        if age_days > STALE_DAYS:
            status = "STALE"
            note = f"latest annual period is {age_days} days old"
        elif len(distinct_tags) > 1:
            status = "MIXED"
            note = f"history spans {len(distinct_tags)} concepts"
        else:
            status = "MATCH"
            note = ""

        summary_rows.append({
            "ticker": ticker,
            "metric": metric,
            "status": status,
            "note": note,
            "latest_tag": latest["tag"],
            "latest_end": latest["end"],
            "latest_value": latest["value"],
            "earliest_end": earliest["end"],
            "periods": len(facts),
            "distinct_tags": " | ".join(distinct_tags),
            "latest_filing_url": filing_url(cik, latest["accn"]),
        })

        print(
            f"  {status}: {latest['tag']}"
            f" | end={latest['end']}"
            f" | value={latest['value']:,}"
            f" | periods={len(facts)}"
        )

    summary_path = RUNLOGS / f"coverage_{metric}_summary.csv"
    detail_path = RUNLOGS / f"coverage_{metric}_detail.csv"

    with summary_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "ticker", "metric", "status", "note", "latest_tag", "latest_end",
            "latest_value", "earliest_end", "periods", "distinct_tags",
            "latest_filing_url",
        ])
        writer.writeheader()
        writer.writerows(summary_rows)

    with detail_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "ticker", "metric", "period_end", "period_start", "value",
            "taxonomy", "tag", "form", "filed", "accn", "filing_url",
        ])
        writer.writeheader()
        writer.writerows(detail_rows)

    counts: dict[str, int] = {}
    for row in summary_rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    print(f"\nCoverage summary for metric={metric}")
    for status in sorted(counts):
        print(f"  {status}: {counts[status]}/{len(summary_rows)}")
    print(f"\nWrote {summary_path}")
    print(f"Wrote {detail_path}")


if __name__ == "__main__":
    main()