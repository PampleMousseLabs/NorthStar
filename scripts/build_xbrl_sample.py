"""
Build a SEC/XBRL research ticker sample from constituents.csv.

Usage:
    python scripts/build_xbrl_sample.py 250

Output:
    Dev_tools/xbrl/tickers_250_usable.txt

Skips share-class tickers with dots, e.g. BRK.B, BF.B.
"""

import csv
import sys
from pathlib import Path

limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100

source = Path("Dev_tools/xbrl/constituents.csv")
output = Path(f"Dev_tools/xbrl/tickers_{limit}_usable.txt")

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

        if len(tickers) >= limit:
            break

output.write_text("\n".join(tickers) + "\n", encoding="utf-8")

print(f"Wrote {len(tickers)} tickers to {output}")
print(f"Skipped share-class tickers: {', '.join(skipped) or 'none'}")
