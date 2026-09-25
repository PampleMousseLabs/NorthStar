"""
Harvest XBRL presentation relationships from the latest 10-K of sampled companies.

Outputs (Dev_tools/xbrl/runlogs/, gitignored):
    presentation_rows.csv              one row per parent-child relationship
    presentation_tag_frequency.csv     concept frequency by statement category
    presentation_harvest_status.csv    retrieval status per ticker
"""

from collections import defaultdict
import csv
import os
import time
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import requests

from northstar.data.sources.sec_edgar import SECEdgarClient

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
CACHE_DIR = RUNLOGS / "presentation_cache"
TICKERS_FILE = Path("Dev_tools/xbrl/tickers_sample.txt")

LINK_NS = "http://www.xbrl.org/2003/linkbase"
XLINK_NS = "http://www.w3.org/1999/xlink"

LINK_PRESENTATION = f"{{{LINK_NS}}}presentationLink"
LINK_ARC = f"{{{LINK_NS}}}presentationArc"
LINK_LOC = f"{{{LINK_NS}}}loc"

XLINK_ROLE = f"{{{XLINK_NS}}}role"
XLINK_ARCROLE = f"{{{XLINK_NS}}}arcrole"
XLINK_FROM = f"{{{XLINK_NS}}}from"
XLINK_TO = f"{{{XLINK_NS}}}to"
XLINK_LABEL = f"{{{XLINK_NS}}}label"
XLINK_HREF = f"{{{XLINK_NS}}}href"
XLINK_PREFERRED_LABEL = f"{{{XLINK_NS}}}preferredLabel"

# SEC ticker file resolves XOM to a newer CIK with no 10-K history.
CIK_OVERRIDES = {
    "XOM": "0000034088",
}


def get_user_agent() -> str:
    user_agent = os.getenv("SEC_USER_AGENT")
    if not user_agent:
        raise RuntimeError(
            "SEC_USER_AGENT not set. Run: source ~/.config/northstar/sec.env"
        )
    return user_agent


def make_session(user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate",
    })
    return session


def load_tickers() -> list[str]:
    return [
        line.strip().upper()
        for line in TICKERS_FILE.read_text().splitlines()
        if line.strip()
    ]


def filing_base_url(cik: str, accession: str) -> str:
    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{int(cik)}/{accession.replace('-', '')}/"
    )


def filing_index_url(cik: str, accession: str) -> str:
    return urljoin(filing_base_url(cik, accession), f"{accession}-index.htm")


def get_latest_10k(session: requests.Session, cik: str) -> dict | None:
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = session.get(url, timeout=30)
    response.raise_for_status()

    recent = response.json().get("filings", {}).get("recent", {})
    records = list(zip(
        recent.get("form", []),
        recent.get("accessionNumber", []),
        recent.get("filingDate", []),
        recent.get("primaryDocument", []),
    ))

    for desired_form in ("10-K", "10-K/A"):
        for form, accession, filing_date, primary_document in records:
            if form == desired_form:
                return {
                    "form": form,
                    "accession": accession,
                    "filing_date": filing_date,
                    "primary_document": primary_document,
                }
    return None


def find_pre_xml_url(
    session: requests.Session,
    cik: str,
    accession: str,
    primary_document: str,
) -> str | None:
    """Locate the presentation linkbase via the SEC archive directory JSON."""
    base_url = filing_base_url(cik, accession)
    response = session.get(urljoin(base_url, "index.json"), timeout=30)
    response.raise_for_status()

    items = response.json().get("directory", {}).get("item", [])
    candidates = [
        str(item["name"])
        for item in items
        if item.get("name") and str(item["name"]).lower().endswith("_pre.xml")
    ]

    if not candidates:
        return None

    expected = f"{Path(primary_document).stem.lower()}_pre.xml"
    for candidate in candidates:
        if candidate.lower() == expected:
            return urljoin(base_url, candidate)

    if len(candidates) == 1:
        return urljoin(base_url, candidates[0])

    raise RuntimeError(
        f"Multiple _pre.xml files, none matching {primary_document}: {candidates}"
    )


def load_pre_xml(
    session: requests.Session,
    ticker: str,
    accession: str,
    pre_url: str,
) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{ticker}_{accession.replace('-', '')}_pre.xml"

    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    response = session.get(pre_url, timeout=30)
    response.raise_for_status()
    cache_path.write_text(response.text, encoding="utf-8")
    return response.text


def concept_from_href(href: str) -> str:
    """us-gaap_Revenues -> us-gaap:Revenues"""
    if not href:
        return ""
    fragment = href.rsplit("#", 1)[-1]
    if "_" not in fragment:
        return fragment
    namespace, concept = fragment.split("_", 1)
    return f"{namespace}:{concept}"


def classify_role(role: str) -> str:
    """Broad statement/disclosure category. Conservative: unknown stays 'other'."""
    name = role.rsplit("/", 1)[-1].lower()

    disclosure_markers = (
        "parenthetical", "detail", "details", "disclosure",
        "policies", "policy", "schedule", "table",
    )
    if any(marker in name for marker in disclosure_markers):
        return "disclosure"

    if "comprehensiveincome" in name:
        return "comprehensive_income_statement"
    if "cashflow" in name:
        return "cash_flow_statement"
    if "balancesheet" in name or "financialposition" in name or "financialcondition" in name:
        return "balance_sheet"
    if any(k in name for k in (
        "statementsofincome", "statementofincome",
        "statementsofoperations", "statementofoperations",
        "statementsofearnings", "statementofearnings",
    )):
        return "income_statement"
    if any(k in name for k in (
        "stockholdersequity", "shareholdersequity", "changesinequity",
    )):
        return "equity_statement"

    return "other"


def is_structural_concept(concept: str) -> bool:
    local_name = concept.split(":", 1)[-1]
    return local_name.endswith(
        ("Abstract", "Table", "Axis", "Domain", "Member", "LineItems")
    )


def parse_pre_xml(
    xml_text: str,
    ticker: str,
    cik: str,
    filing: dict,
    index_url: str,
    pre_url: str,
) -> list[dict]:
    root = ET.fromstring(xml_text)
    rows = []

    for presentation_link in root.iter(LINK_PRESENTATION):
        role = presentation_link.get(XLINK_ROLE) or ""
        role_category = classify_role(role)

        locators = {}
        for locator in presentation_link.findall(LINK_LOC):
            label = locator.get(XLINK_LABEL) or ""
            if label:
                locators[label] = concept_from_href(locator.get(XLINK_HREF) or "")

        for arc in presentation_link.findall(LINK_ARC):
            if "parent-child" not in (arc.get(XLINK_ARCROLE) or ""):
                continue

            child_concept = locators.get(arc.get(XLINK_TO) or "", "")
            if not child_concept:
                continue

            preferred = arc.get(XLINK_PREFERRED_LABEL) or ""

            rows.append({
                "ticker": ticker,
                "cik": cik,
                "form": filing["form"],
                "filing_date": filing["filing_date"],
                "filing_accession": filing["accession"],
                "filing_index_url": index_url,
                "pre_xml_url": pre_url,
                "statement_role": role,
                "statement_category": role_category,
                "parent_concept": locators.get(arc.get(XLINK_FROM) or "", ""),
                "child_concept": child_concept,
                "sibling_order": arc.get("order") or "",
                "preferred_label_role": preferred.rsplit("/", 1)[-1],
                "is_structural": is_structural_concept(child_concept),
            })

    return rows


def write_detail(rows: list[dict], path: Path) -> None:
    fields = [
        "ticker", "cik", "form", "filing_date", "filing_accession",
        "filing_index_url", "pre_xml_url", "statement_role",
        "statement_category", "parent_concept", "child_concept",
        "sibling_order", "preferred_label_role", "is_structural",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_frequency(rows: list[dict], path: Path) -> None:
    """Aggregate by (concept, statement_category) so disclosure hits don't
    masquerade as primary-statement evidence."""
    groups = defaultdict(lambda: {"tickers": set(), "roles": set(), "example": None})

    for row in rows:
        key = (row["child_concept"], row["statement_category"], row["is_structural"])
        group = groups[key]
        group["tickers"].add(row["ticker"])
        group["roles"].add(row["statement_role"])
        if group["example"] is None:
            group["example"] = row

    sorted_groups = sorted(
        groups.items(),
        key=lambda item: (-len(item[1]["tickers"]), item[0][1], item[0][0]),
    )

    fields = [
        "concept", "statement_category", "is_structural", "company_count",
        "tickers", "statement_roles", "example_ticker", "example_accession",
        "example_filing_index_url", "example_pre_xml_url",
    ]

    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for (concept, category, structural), group in sorted_groups:
            example = group["example"]
            writer.writerow({
                "concept": concept,
                "statement_category": category,
                "is_structural": structural,
                "company_count": len(group["tickers"]),
                "tickers": "|".join(sorted(group["tickers"])),
                "statement_roles": " | ".join(sorted(group["roles"])),
                "example_ticker": example["ticker"],
                "example_accession": example["filing_accession"],
                "example_filing_index_url": example["filing_index_url"],
                "example_pre_xml_url": example["pre_xml_url"],
            })


def write_status(rows: list[dict], path: Path) -> None:
    fields = [
        "ticker", "cik", "status", "note", "filing_accession",
        "primary_document", "pre_xml_url", "presentation_rows",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    user_agent = get_user_agent()
    session = make_session(user_agent)
    client = SECEdgarClient(user_agent=user_agent)

    RUNLOGS.mkdir(parents=True, exist_ok=True)

    all_rows = []
    status_rows = []
    tickers = load_tickers()

    for index, ticker in enumerate(tickers, start=1):
        print(f"[{index}/{len(tickers)}] {ticker}")
        cik = CIK_OVERRIDES.get(ticker)

        try:
            if cik is None:
                cik = client.resolve_cik(ticker)

            filing = get_latest_10k(session, cik)
            if filing is None:
                print("  NO_10K")
                status_rows.append({
                    "ticker": ticker, "cik": cik, "status": "NO_10K",
                    "note": "No 10-K or 10-K/A in recent submissions",
                    "filing_accession": "", "primary_document": "",
                    "pre_xml_url": "", "presentation_rows": 0,
                })
                continue

            pre_url = find_pre_xml_url(
                session, cik, filing["accession"], filing["primary_document"]
            )
            if pre_url is None:
                print("  NO_PRE_XML")
                status_rows.append({
                    "ticker": ticker, "cik": cik, "status": "NO_PRE_XML",
                    "note": "No _pre.xml in archive directory",
                    "filing_accession": filing["accession"],
                    "primary_document": filing["primary_document"],
                    "pre_xml_url": "", "presentation_rows": 0,
                })
                continue

            xml_text = load_pre_xml(session, ticker, filing["accession"], pre_url)
            index_url = filing_index_url(cik, filing["accession"])
            rows = parse_pre_xml(xml_text, ticker, cik, filing, index_url, pre_url)
            all_rows.extend(rows)

            print(f"  PARSED: {len(rows)} presentation arcs")
            status_rows.append({
                "ticker": ticker, "cik": cik, "status": "PARSED", "note": "",
                "filing_accession": filing["accession"],
                "primary_document": filing["primary_document"],
                "pre_xml_url": pre_url, "presentation_rows": len(rows),
            })

            time.sleep(0.15)

        except Exception as error:
            print(f"  ERROR: {error}")
            status_rows.append({
                "ticker": ticker, "cik": cik or "", "status": "ERROR",
                "note": str(error), "filing_accession": "",
                "primary_document": "", "pre_xml_url": "", "presentation_rows": 0,
            })

    detail_path = RUNLOGS / "presentation_rows.csv"
    frequency_path = RUNLOGS / "presentation_tag_frequency.csv"
    status_path = RUNLOGS / "presentation_harvest_status.csv"

    write_detail(all_rows, detail_path)
    write_frequency(all_rows, frequency_path)
    write_status(status_rows, status_path)

    parsed = sum(row["status"] == "PARSED" for row in status_rows)
    print(f"\nParsed filings: {parsed}/{len(status_rows)}")
    print(f"Wrote {detail_path} ({len(all_rows)} rows)")
    print(f"Wrote {frequency_path}")
    print(f"Wrote {status_path}")


if __name__ == "__main__":
    main()
