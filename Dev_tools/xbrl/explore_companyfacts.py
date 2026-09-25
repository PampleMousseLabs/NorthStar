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
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        return json.loads(cache.read_text())
    data = fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    cache.write_text(json.dumps(data))
    return data

def show_exact_concept(data, taxonomy, tag):
    concept = data.get("facts", {}).get(taxonomy, {}).get(tag)
    if concept is None:
        print(f"Concept not found: {taxonomy}/{tag}")
        return
    print(f"\nConcept: {taxonomy}/{tag}")
    print(f"Label: {concept.get('label', '')}")
    for unit, facts in concept.get("units", {}).items():
        annual = [
            f for f in facts
            if f.get("form") in {"10-K", "10-K/A", "20-F", "20-F/A"}
            and f.get("fp") == "FY"
            and not f.get("segment")
            and f.get("start")
            and f.get("end")
        ]
        annual.sort(key=lambda f: (f.get("end", ""), f.get("filed", "")), reverse=True)
        print(f"\nUnit: {unit}")
        for f in annual[:10]:
            print(
                f"  value={f.get('val')}"
                f" | start={f.get('start')}"
                f" | end={f.get('end')}"
                f" | fy={f.get('fy')}"
                f" | form={f.get('form')}"
                f" | filed={f.get('filed')}"
                f" | accn={f.get('accn')}"
            )

def main():
    # Usage:
    #   python Dev_tools/xbrl/explore_companyfacts.py AAPL
    #   python Dev_tools/xbrl/explore_companyfacts.py AAPL us-gaap RevenueFromContractWithCustomerExcludingAssessedTax
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "AAPL"
    cik = resolve(ticker)
    print(f"Ticker: {ticker}  CIK: {cik}")
    data = load_companyfacts(ticker, cik)
    print(f"Taxonomies: {list(data.get('facts', {}).keys())}")
    if len(sys.argv) == 4:
        show_exact_concept(data, sys.argv[2], sys.argv[3])
    else:
        # default: show the current core revenue tag
        show_exact_concept(data, "us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax")

if __name__ == "__main__":
    main()