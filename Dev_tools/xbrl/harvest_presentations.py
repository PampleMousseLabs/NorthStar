"""
Harvest the presentation structure from the latest 10-K of sampled companies.

Uses BeautifulSoup to parse the SEC index and locate the '_pre.xml' presentation files.
Writes details and aggregated frequency analysis to local CSVs.
"""

from collections import defaultdict
import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import requests
from xml.etree import ElementTree as ET

from northstar.data.sources.sec_edgar import SECEdgarClient

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
TICKERS_FILE = Path("Dev_tools/xbrl/tickers_sample.txt")
SEC_USER_AGENT = "NorthStar personal research twolter1234@gmail.com"

# Hardcoded overrides for tickers where the SEC automated mapping points to the wrong CIK
CIK_OVERRIDES = {
    "XOM": "0000034088",  # Parent Exxon Mobil Corp, not the trust or subsidiary
}


def fetch_index(cik: str, accn: str, session) -> str:
    cik_plain = str(int(cik))
    accn_nodash = accn.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_plain}/{accn_nodash}/{accn}-index.htm"
    r = session.get(url, headers={"User-Agent": SEC_USER_AGENT}, timeout=30)
    r.raise_for_status()
    return r.text


def find_pre_xml_url(index_html: str) -> str | None:
    """Robust extraction of the presentation XML link using BeautifulSoup."""
    soup = BeautifulSoup(index_html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith("_pre.xml"):
            return urljoin("https://www.sec.gov", href)
    return None


def parse_pre_xml(xml_text: str, ticker: str, cik: str, accn: str, url: str):
    root = ET.fromstring(xml_text)
    rows = []

    # Find presentation links (statement roles)
    for pl in root.iter("{http://www.xbrl.org/2003/linkbase}presentationLink"):
        role = pl.get("{http://www.w3.org/1999/xlink}role") or ""

        # Collect arcs inside this presentation link
        arcs = pl.findall(".//{http://www.xbrl.org/2003/linkbase}presentationArc")
        if not arcs:
            continue

        for arc in arcs:
            arcrole = arc.get("{http://www.w3.org/1999/xlink}arcrole") or ""
            if "parent-child" not in arcrole:
                continue

            order = arc.get("order")
            f = arc.get("{http://www.w3.org/1999/xlink}from")
            t = arc.get("{http://www.w3.org/1999/xlink}to")

            # Resolve locator labels to href references
            def tag_from_label(label: str) -> str:
                for loc in pl.findall(".//{http://www.xbrl.org/2003/linkbase}loc"):
                    loc_label = loc.get("{http://www.w3.org/1999/xlink}label")
                    if loc_label == label:
                        href = loc.get("{http://www.w3.org/1999/xlink}href") or ""
                        if "#" in href:
                            fragment = href.split("#")[-1]
                            if "_" in fragment:
                                parts = fragment.split("_", 1)
                                if len(parts) == 2:
                                    ns = parts[0].replace("us-gaap-", "us-gaap").replace("ifrs-full-", "ifrs-full")
                                    tag = parts[1]
                                    return f"{ns}:{tag}"
                        return fragment.replace("_", ":")
                return ""

            from_tag = tag_from_label(f) if f else ""
            to_tag = tag_from_label(t) if t else ""

            if to_tag:
                rows.append({
                    "ticker": ticker,
                    "cik": cik,
                    "filing_accn": accn,
                    "filing_url": url,
                    "statement_role": role,
                    "parent_tag": from_tag,
                    "child_tag": to_tag,
                    "sibling_order": int(order) if order and order.isdigit() else None,
                })

    return rows


def main() -> None:
    tickers = [line.strip().upper() for line in TICKERS_FILE.read_text().splitlines() if line.strip()]
    client = SECEdgarClient()
    session = requests.Session()
    session.headers.update({"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"})

    detail_path = RUNLOGS / "presentation_rows.csv"
    freq_path = RUNLOGS / "presentation_tag_frequency.csv"

    all_rows = []

    for index, ticker in enumerate(tickers, start=1):
        print(f"[{index}/{len(tickers)}] {ticker}")
        try:
            # Resolve CIK with override fallbacks
            if ticker in CIK_OVERRIDES:
                cik = CIK_OVERRIDES[ticker]
            else:
                cik = client.resolve_cik(ticker)

            sub_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            sub_resp = session.get(sub_url, timeout=30)
            sub_resp.raise_for_status()
            sub = sub_resp.json()

            recent = sub.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            accns = recent.get("accessionNumber", [])

            target_accn = None
            for form, accn in zip(forms, accns):
                if form in {"10-K", "10-K/A"}:
                    target_accn = accn
                    break

            if not target_accn:
                print("  No 10-K found")
                continue

            index_html = fetch_index(cik, target_accn, session)
            pre_url = find_pre_xml_url(index_html)
            if not pre_url:
                print("  Could not find _pre.xml link in index")
                continue

            pre_resp = session.get(pre_url, timeout=30)
            pre_resp.raise_for_status()
            rows = parse_pre_xml(pre_resp.text, ticker, cik, target_accn, pre_url)

            if not rows:
                print("  Parsed 0 presentation rows")
            else:
                all_rows.extend(rows)
                print(f"  Parsed {len(rows)} presentation arcs")

        except Exception as error:
            print(f"  ERROR: {error}")

    if all_rows:
        with detail_path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "ticker", "cik", "filing_accn", "filing_url",
                "statement_role", "parent_tag", "child_tag",
                "sibling_order",
            ])
            for r in all_rows:
                writer.writerow([
                    r["ticker"], r["cik"], r["filing_accn"], r["filing_url"],
                    r["statement_role"], r["parent_tag"], r["child_tag"],
                    r["sibling_order"] if r["sibling_order"] is not None else "",
                ])

        # Corrected aggregation using defaultdict(set)
        from collections import Counter
        tag_counts = Counter()
        tag_rows = defaultdict(set)

        for r in all_rows:
            if r["child_tag"]:
                tag = r["child_tag"]
                tag_counts[tag] += 1
                tag_rows[tag].add(r["ticker"])

        with freq_path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "tag", "label_hint", "statement_roles", "company_count",
                "tickers", "example_filing_url",
            ])
            for tag, count in tag_counts.most_common():
                tickers_for_tag = sorted(tag_rows[tag])
                roles = sorted({r["statement_role"] for r in all_rows if r["child_tag"] == tag and r["statement_role"]})
                roles_str = "; ".join(roles) if roles else ""
                example_url = ""
                for r in all_rows:
                    if r["child_tag"] == tag:
                        example_url = r["filing_url"]
                        break
                writer.writerow([tag, "", roles_str, len(tickers_for_tag), "|".join(tickers_for_tag), example_url])

        print(f"\nWrote {detail_path} ({len(all_rows)} rows)")
        print(f"Wrote {freq_path} ({len(tag_counts)} unique tags)")


if __name__ == "__main__":
    main()