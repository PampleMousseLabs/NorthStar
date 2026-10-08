import subprocess
from pathlib import Path

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
TICKERS_FILE = Path("Dev_tools/xbrl/tickers_100_usable.txt")

tickers = [l.strip().upper() for l in TICKERS_FILE.read_text().splitlines() if l.strip()]

for i, ticker in enumerate(tickers, start=1):
    existing = list(RUNLOGS.glob(f"filing_facts_{ticker}_*.csv"))
    if existing:
        continue
    
    print(f"[{i}/{len(tickers)}] Harvesting {ticker}...")
    try:
        # Use existing harvester
        subprocess.run(
            ["python", "Dev_tools/xbrl/harvest_filing_facts.py", ticker],
            check=True,
            capture_output=True,
            text=True
        )
    except Exception as e:
        print(f"  FAILED {ticker}: {e}")
