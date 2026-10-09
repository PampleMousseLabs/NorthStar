"""
Harvest filing-level XBRL facts for any tickers missing a filing_facts CSV.

Usage:
    source ~/.config/northstar/sec.env
    python scripts/harvest_missing_facts.py Dev_tools/xbrl/tickers_250_usable.txt

Skips tickers that already have a filing_facts_<TICKER>_*.csv.
Sets PYTHONPATH for each subprocess, so it works without PYTHONPATH=. prefix.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNLOGS = REPO_ROOT / "Dev_tools/xbrl/runlogs"
HARVESTER = REPO_ROOT / "Dev_tools/xbrl/harvest_filing_facts.py"

tickers_file = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "Dev_tools/xbrl/tickers_100_usable.txt"

tickers = [l.strip().upper() for l in tickers_file.read_text().splitlines() if l.strip()]
missing = [t for t in tickers if not list(RUNLOGS.glob(f"filing_facts_{t}_*.csv"))]

env = os.environ.copy()
env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

if not env.get("SEC_USER_AGENT"):
    raise SystemExit("SEC_USER_AGENT not set. Run: source ~/.config/northstar/sec.env")

print(f"Tickers in sample: {len(tickers)}   Missing filing facts: {len(missing)}")

failed = []
for i, ticker in enumerate(missing, start=1):
    print(f"[{i}/{len(missing)}] {ticker}", flush=True)
    result = subprocess.run(
        [sys.executable, str(HARVESTER), ticker],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
    )
    if result.returncode != 0:
        last = (result.stderr.strip().splitlines() or ["unknown error"])[-1]
        print(f"  FAILED: {last}")
        failed.append(ticker)

print(f"\nDone. Harvested {len(missing) - len(failed)}/{len(missing)}.")
if failed:
    print(f"Failed: {' '.join(failed)}")
