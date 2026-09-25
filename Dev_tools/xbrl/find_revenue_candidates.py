import os
import sys
import json
import requests
from pathlib import Path

SEC_USER_AGENT = os.getenv("SEC_USER_AGENT")
if not SEC_USER_AGENT:
    raise RuntimeError("Set SEC_USER_AGENT before running.")

def fetch(url):
    return requests.get(
        url,
        headers={"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"},
        timeout=30,
    ).json()

def resolve(ticker):
    companies = fetch("https://www.sec.gov/files/company_tickers.json")
    for c in companies.values():
        if str(c.get("ticker", "")).upper() == ticker.upper():
            return f"{int(c['cik_str']):010d}"
    raise LookupError(ticker)

def load_companyfacts(ticker, cik):
    cache = Path(f"Dev_tools/xbrl/runlogs/{ticker}_{cik}.json")
    if cache.exists():
        return json.loads(cache.read_text())
    data = fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    cache.write_text(json.dumps(data))
    return data

def latest_by_end(concept):
    best = {}
    for unit, facts in concept.get("units", {}).items():
        if unit != "USD":
            continue
        for f in facts:
            if f.get("form") not in {"10-K", "10-K/A", "20-F", "20-F/A"}:
                continue
            if f.get("fp") != "FY":
                continue
            if f.get("segment"):
                continue
            if not f.get("end"):
                continue
            end = f.get("end")
            prev = best.get(end)
            if prev is None or str(f.get("filed", "")) > str(prev.get("filed", "")):
                best[end] = f
    ends = sorted(best.keys(), reverse=True)
    return [(e, best[e]) for e in ends[:3]]

def main():
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "JPM"
    cik = resolve(ticker)
    data = load_companyfacts(ticker, cik)
    print(f"Ticker: {ticker} CIK: {cik}")

    for taxonomy, concepts in data.get("facts", {}).items():
        for tag, concept in concepts.items():
            tag_lower = tag.lower()
            label_lower = str(concept.get("label", "")).lower()
            combined = tag_lower + " " + label_lower

            if "availableforsale" in tag_lower.replace("-", "").replace("_", ""):
                continue
            if "available-for-sale" in label_lower:
                continue
            if "deferred" in combined and "revenue" in combined:
                continue

            if not any(k in combined for k in ["revenue", "sales", "rental", "interest income", "noninterest"]):
                continue

            rows = latest_by_end(concept)
            if not rows:
                continue

            print(f"\n{taxonomy} / {tag}")
            print(f"  label: {concept.get('label', '')}")
            for end, f in rows:
                print(f"    end={end} value={f.get('val')} filed={f.get('filed')} form={f.get('form')} accn={f.get('accn')}")

if __name__ == "__main__":
    main()