"""
Build a 100-company SEC/XBRL research ticker sample.

Input:  Dev_tools/xbrl/constituents.csv
Output: Dev_tools/xbrl/tickers_100_usable.txt

Skips share-class tickers containing a dot (BRK.B, BF.B). The SEC ticker
file uses a different convention for those and they fail CIK lookup.
"""

import csv
from pathlib import Path

source = Path("Dev_tools/xbrl/constituents.csv")
output = Path("Dev_tools/xbrl/tickers_100_usable.txt")

if not source.exists():
    raise SystemExit(f"Missing {source}")

tickers = []
skipped = []

with source.open(newline="", encoding="utf-8", errors="ignore") as handle:
    for row in csv.reader(handle):
        if not row:
            continue

        ticker = row[0].strip().strip('"').upper()

        if ticker in {"TICKER", "SYMBOL"}:
            continue

        if "." in ticker:
            skipped.append(ticker)
            continue

        if ticker and ticker not in tickers:
            tickers.append(ticker)

        if len(tickers) >= 100:
            break

output.write_text("\n".join(tickers) + "\n", encoding="utf-8")

print(f"Wrote {len(tickers)} tickers to {output}")
print(f"Skipped share-class tickers: {', '.join(skipped) or 'none'}")
