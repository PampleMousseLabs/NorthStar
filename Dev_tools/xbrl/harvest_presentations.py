"""
Harvest XBRL presentation relationships from sampled companies' latest 10-K.

Sources:
    1. Standalone SEC presentation linkbase (*_pre.xml).
    2. Embedded presentation relationships in the filing's XSD schema.

Outputs:
    presentation_rows.csv
    presentation_tag_frequency.csv
    presentation_harvest_status.csv

Use --output-dir to keep experimental runs separate from benchmark outputs.
"""

from collections import defaultdict
import argparse
import csv
import os
import time
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import requests

from northstar.data.storage.xbrl_cache import xbrl_cache_root
from northstar.data.sources.sec_edgar import SECEdgarClient


RUNLOGS = Path("Dev_tools/xbrl/runlogs")
CACHE_ROOT = xbrl_cache_root(RUNLOGS)
CACHE_DIR = CACHE_ROOT / "presentation_cache"
TICKERS_FILE = Path("Dev_tools/xbrl/tickers_sample.txt")

LINK_NS = "http://www.xbrl.org/2003/linkbase"
XLINK_NS = "http://www.w3.org/1999/xlink"

LINK_PRESENTATION = f"{{{LINK_NS}}}presentationLink"
LINK_ARC = f"{{{LINK_NS}}}presentationArc"
LINK_CALCULATION = f"{{{LINK_NS}}}calculationLink"
LINK_CALC_ARC = f"{{{LINK_NS}}}calculationArc"
LINK_LOC = f"{{{LINK_NS}}}loc"

XLINK_ROLE = f"{{{XLINK_NS}}}role"
XLINK_ARCROLE = f"{{{XLINK_NS}}}arcrole"
XLINK_FROM = f"{{{XLINK_NS}}}from"
XLINK_TO = f"{{{XLINK_NS}}}to"
XLINK_LABEL = f"{{{XLINK_NS}}}label"
XLINK_HREF = f"{{{XLINK_NS}}}href"
XLINK_PREFERRED_LABEL = f"{{{XLINK_NS}}}preferredLabel"

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


def load_tickers(path: Path = TICKERS_FILE, limit: int | None = None) -> list[str]:
    tickers = [
        line.strip().upper()
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    return tickers[:limit] if limit else tickers


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


def latest_facts_filing_accession(ticker: str) -> str | None:
    """Return the accession from the most recently filed local facts CSV."""
    candidates = []

    for facts_path in RUNLOGS.glob(f"filing_facts_{ticker}_*.csv"):
        try:
            with facts_path.open(newline="", encoding="utf-8") as handle:
                first_row = next(csv.DictReader(handle), None)
        except (OSError, csv.Error):
            continue

        if not first_row:
            continue

        accession = (first_row.get("filing_accession") or "").strip()
        filing_date = (first_row.get("filing_date") or "").strip()

        if accession:
            candidates.append((filing_date, accession))

    if not candidates:
        return None

    return max(candidates)[1]


def get_filing_by_accession(
    session: requests.Session,
    cik: str,
    target_accession: str,
) -> dict | None:
    """Find exact filing metadata for an accession in SEC submissions."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = session.get(url, timeout=30)
    response.raise_for_status()

    recent = response.json().get("filings", {}).get("recent", {})

    for form, accession, filing_date, primary_document in zip(
        recent.get("form", []),
        recent.get("accessionNumber", []),
        recent.get("filingDate", []),
        recent.get("primaryDocument", []),
    ):
        if accession == target_accession:
            return {
                "form": form,
                "accession": accession,
                "filing_date": filing_date,
                "primary_document": primary_document,
            }

    return None


def get_filing_for_ticker(
    session: requests.Session,
    cik: str,
    ticker: str,
) -> dict | None:
    """
    Use the accession from harvested filing facts when present.

    This prevents facts from a 10-K/A being combined with presentation rows
    from the original 10-K. Only fall back to latest-10-K selection if this
    ticker has no local filing-facts CSV.
    """
    target_accession = latest_facts_filing_accession(ticker)

    if not target_accession:
        return get_latest_10k(session, cik)

    filing = get_filing_by_accession(session, cik, target_accession)

    if filing is None:
        raise RuntimeError(
            f"Facts accession {target_accession} for {ticker} was not found "
            "in the SEC recent-submissions response; refusing to use a "
            "different filing."
        )

    return filing


def find_presentation_source(
    session: requests.Session,
    cik: str,
    accession: str,
    primary_document: str,
) -> tuple[str | None, str]:
    """
    Find the best available presentation source in the SEC archive.

    Prefer a standalone _pre.xml. If absent, look for the filing's embedded
    presentation relationships in its XSD schema.

    Returns (URL, source_type), where source_type is PRE_XML, EMBEDDED_XSD,
    or NONE. Ambiguous archive matches raise an error rather than guessing.
    """
    base_url = filing_base_url(cik, accession)
    response = session.get(urljoin(base_url, "index.json"), timeout=30)
    response.raise_for_status()

    items = response.json().get("directory", {}).get("item", [])
    filenames = [
        str(item["name"])
        for item in items
        if item.get("name")
    ]

    pre_candidates = [
        name for name in filenames
        if name.lower().endswith("_pre.xml")
    ]

    expected_pre = f"{Path(primary_document).stem.lower()}_pre.xml"

    if pre_candidates:
        for candidate in pre_candidates:
            if candidate.lower() == expected_pre:
                return urljoin(base_url, candidate), "PRE_XML"

        if len(pre_candidates) == 1:
            return urljoin(base_url, pre_candidates[0]), "PRE_XML"

        raise RuntimeError(
            f"Multiple _pre.xml files, none matching "
            f"{primary_document}: {pre_candidates}"
        )

    xsd_candidates = [
        name for name in filenames
        if name.lower().endswith(".xsd")
    ]

    primary_stem = Path(primary_document).stem.lower()
    if primary_stem.endswith("_htm"):
        primary_stem = primary_stem[:-4]

    expected_xsd = f"{primary_stem}.xsd"

    for candidate in xsd_candidates:
        if candidate.lower() == expected_xsd:
            return urljoin(base_url, candidate), "EMBEDDED_XSD"

    if len(xsd_candidates) == 1:
        return urljoin(base_url, xsd_candidates[0]), "EMBEDDED_XSD"

    if len(xsd_candidates) > 1:
        raise RuntimeError(
            f"Multiple XSD files, none matching {expected_xsd}: "
            f"{xsd_candidates}"
        )

    return None, "NONE"


def load_presentation_source(
    session: requests.Session,
    ticker: str,
    accession: str,
    source_url: str,
    source_type: str,
) -> str:
    """Load a presentation source using a source-specific cache filename."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    suffix = "_pre.xml" if source_type == "PRE_XML" else "_embedded.xsd"
    cache_path = (
        CACHE_DIR / f"{ticker}_{accession.replace('-', '')}{suffix}"
    )

    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    response = session.get(source_url, timeout=30)
    response.raise_for_status()

    cache_path.write_text(response.text, encoding="utf-8")
    return response.text


def concept_from_href(href: str) -> str:
    """Convert a locator fragment such as us-gaap_Revenues to us-gaap:Revenues."""
    if not href:
        return ""

    fragment = href.rsplit("#", 1)[-1]
    if "_" not in fragment:
        return fragment

    namespace, concept = fragment.split("_", 1)
    return f"{namespace}:{concept}"


def classify_role(role: str, role_rows: list[dict] | None = None) -> str:
    """
    Classify a presentation role using its name and, when available,
    its presentation structure.
    """
    name = role.rsplit("/", 1)[-1].lower().replace("-", "").replace("_", "")

    disclosure_markers = (
        "parenthetical", "detail", "details", "disclosure",
        "policies", "policy", "schedule", "tables",
        "narrative", "reconcil", "rollforward", "reclassification",
    )
    if any(marker in name for marker in disclosure_markers):
        return "disclosure"

    # Respect an explicit comprehensive-income role designation before
    # structural evidence, which can otherwise promote it to income_statement.
    if "comprehensiveincome" in name:
        stripped = name.replace("comprehensiveincome", "")
        if any(word in stripped for word in ("income", "operations", "earnings")):
            return "income_statement"
        return "comprehensive_income_statement"

    if role_rows:
        concepts = set()

        for row in role_rows:
            for field in ("parent_concept", "child_concept"):
                concept = row.get(field, "")
                if concept:
                    concepts.add(concept.split(":", 1)[-1])

        has_income_root = any(
            concept in {
                "IncomeStatementAbstract",
                "StatementOfIncomeAndComprehensiveIncomeAbstract",
            }
            for concept in concepts
        )

        has_revenue = any(
            concept.startswith(("Revenue", "SalesRevenue"))
            or concept == "Revenues"
            for concept in concepts
        )

        if has_income_root and has_revenue:
            return "income_statement"

    if "cashflow" in name:
        return "cash_flow_statement"

    if (
        "balancesheet" in name
        or "financialposition" in name
        or "financialcondition" in name
    ):
        return "balance_sheet"

    if "equity" in name and any(
        word in name for word in (
            "statement", "statements", "changes",
            "stockholder", "shareholder", "investment",
        )
    ):
        return "equity_statement"

    has_statement_word = any(
        word in name for word in ("statement", "statements", "consolidated")
    )
    has_income_word = any(
        word in name for word in ("income", "operations", "earnings")
    )

    non_statement_income = (
        "earningspershare", "pershare", "incometax", "taxes",
        "segment", "accumulatedother", "netinterestincome",
        "natureofoperations", "discontinuedoperations",
        "otherincome", "restructuring", "interestincome",
    )

    if has_statement_word and has_income_word and not any(
        marker in name for marker in non_statement_income
    ):
        if "comprehensiveincome" in name:
            stripped = name.replace("comprehensiveincome", "")
            if any(
                word in stripped for word in ("income", "operations", "earnings")
            ):
                return "income_statement"
            return "comprehensive_income_statement"

        return "income_statement"

    if "comprehensiveincome" in name:
        return "comprehensive_income_statement"

    return "other"


def is_structural_concept(concept: str) -> bool:
    local_name = concept.split(":", 1)[-1]
    return local_name.endswith(
        ("Abstract", "Table", "Axis", "Domain", "Member", "LineItems")
    )


def parse_presentation_xml(
    xml_text: str,
    ticker: str,
    cik: str,
    filing: dict,
    index_url: str,
    source_url: str,
    source_type: str,
) -> list[dict]:
    """
    Parse presentationLink relationships from either _pre.xml or an XSD.

    Both sources use the XBRL linkbase presentationLink structure. The
    source_type field records which archive document supplied the network.
    """
    root = ET.fromstring(xml_text)
    rows = []

    for presentation_link in root.iter(LINK_PRESENTATION):
        role = presentation_link.get(XLINK_ROLE) or ""
        role_rows = []

        locators = {}
        for locator in presentation_link.findall(LINK_LOC):
            label = locator.get(XLINK_LABEL) or ""
            if label:
                locators[label] = concept_from_href(
                    locator.get(XLINK_HREF) or ""
                )

        for arc in presentation_link.findall(LINK_ARC):
            if "parent-child" not in (arc.get(XLINK_ARCROLE) or ""):
                continue

            child_concept = locators.get(arc.get(XLINK_TO) or "", "")
            if not child_concept:
                continue

            preferred = arc.get(XLINK_PREFERRED_LABEL) or ""

            role_rows.append({
                "ticker": ticker,
                "cik": cik,
                "form": filing["form"],
                "filing_date": filing["filing_date"],
                "filing_accession": filing["accession"],
                "filing_index_url": index_url,
                "pre_xml_url": source_url,
                "source_type": source_type,
                "statement_role": role,
                "statement_category": "",
                "parent_concept": locators.get(
                    arc.get(XLINK_FROM) or "", ""
                ),
                "child_concept": child_concept,
                "sibling_order": arc.get("order") or "",
                "preferred_label_role": preferred.rsplit("/", 1)[-1],
                "is_structural": is_structural_concept(child_concept),
            })

        role_category = classify_role(role, role_rows)

        for row in role_rows:
            row["statement_category"] = role_category

        rows.extend(role_rows)

    return rows


def parse_calculation_xml(
    xml_text: str,
    ticker: str,
    cik: str,
    filing: dict,
    index_url: str,
    source_url: str,
    source_type: str,
) -> list[dict]:
    """Extract weighted summation-item arcs from calculationLink networks."""
    root = ET.fromstring(xml_text)
    rows = []

    for calculation_link in root.iter(LINK_CALCULATION):
        role = calculation_link.get(XLINK_ROLE) or ""
        locators = {}

        for locator in calculation_link.findall(LINK_LOC):
            label = locator.get(XLINK_LABEL) or ""
            if label:
                locators[label] = concept_from_href(
                    locator.get(XLINK_HREF) or ""
                )

        for arc in calculation_link.findall(LINK_CALC_ARC):
            if "summation-item" not in (
                arc.get(XLINK_ARCROLE) or ""
            ):
                continue

            parent = locators.get(arc.get(XLINK_FROM) or "", "")
            child = locators.get(arc.get(XLINK_TO) or "", "")
            if not parent or not child:
                continue

            try:
                weight = float(arc.get("weight", "1"))
            except (TypeError, ValueError):
                weight = 1.0

            rows.append({
                "ticker": ticker,
                "cik": cik,
                "form": filing["form"],
                "filing_date": filing["filing_date"],
                "filing_accession": filing["accession"],
                "filing_index_url": index_url,
                "source_url": source_url,
                "source_type": source_type,
                "calculation_role": role,
                "parent_concept": parent,
                "child_concept": child,
                "weight": weight,
                "arc_order": arc.get("order") or "",
            })

    return rows


def write_calculation_detail(rows: list[dict], path: Path) -> None:
    fields = [
        "ticker", "cik", "form", "filing_date", "filing_accession",
        "filing_index_url", "source_url", "source_type",
        "calculation_role", "parent_concept", "child_concept",
        "weight", "arc_order",
    ]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_detail(rows: list[dict], path: Path) -> None:
    fields = [
        "ticker", "cik", "form", "filing_date", "filing_accession",
        "filing_index_url", "pre_xml_url", "source_type",
        "statement_role", "statement_category", "parent_concept",
        "child_concept", "sibling_order", "preferred_label_role",
        "is_structural",
    ]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_frequency(rows: list[dict], path: Path) -> None:
    """Aggregate by concept, category, and structural status."""
    groups = defaultdict(
        lambda: {"tickers": set(), "roles": set(), "example": None}
    )

    for row in rows:
        key = (
            row["child_concept"],
            row["statement_category"],
            row["is_structural"],
        )
        group = groups[key]
        group["tickers"].add(row["ticker"])
        group["roles"].add(row["statement_role"])

        if group["example"] is None:
            group["example"] = row

    sorted_groups = sorted(
        groups.items(),
        key=lambda item: (
            -len(item[1]["tickers"]),
            item[0][1],
            item[0][0],
        ),
    )

    fields = [
        "concept", "statement_category", "is_structural", "company_count",
        "tickers", "statement_roles", "example_ticker", "example_accession",
        "example_filing_index_url", "example_pre_xml_url", "source_type",
    ]

    with path.open("w", newline="", encoding="utf-8") as handle:
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
                "source_type": example["source_type"],
            })


def write_status(rows: list[dict], path: Path) -> None:
    fields = [
        "ticker", "cik", "status", "note", "filing_accession",
        "primary_document", "pre_xml_url", "source_type",
        "presentation_rows",
    ]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(TICKERS_FILE))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=RUNLOGS,
        help="Directory for the three output CSVs (default: existing runlogs).",
    )
    args = parser.parse_args()

    user_agent = get_user_agent()
    session = make_session(user_agent)
    client = SECEdgarClient(user_agent=user_agent)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    all_rows = []
    all_calculation_rows = []
    status_rows = []
    tickers = load_tickers(Path(args.file), args.limit)

    print(f"Loaded {len(tickers)} tickers from {args.file}")
    print(f"Output directory: {output_dir}")

    for index, ticker in enumerate(tickers, start=1):
        print(f"[{index}/{len(tickers)}] {ticker}")
        cik = CIK_OVERRIDES.get(ticker)

        try:
            if cik is None:
                cik = client.resolve_cik(ticker)

            filing = get_filing_for_ticker(session, cik, ticker)

            if filing is None:
                print("  NO_10K")
                status_rows.append({
                    "ticker": ticker,
                    "cik": cik,
                    "status": "NO_10K",
                    "note": "No 10-K or 10-K/A in recent submissions",
                    "filing_accession": "",
                    "primary_document": "",
                    "pre_xml_url": "",
                    "source_type": "NONE",
                    "presentation_rows": 0,
                })
                continue

            source_url, source_type = find_presentation_source(
                session,
                cik,
                filing["accession"],
                filing["primary_document"],
            )

            if source_url is None:
                print("  NO_PRESENTATION")
                status_rows.append({
                    "ticker": ticker,
                    "cik": cik,
                    "status": "NO_PRESENTATION",
                    "note": "No standalone _pre.xml or matching XSD found",
                    "filing_accession": filing["accession"],
                    "primary_document": filing["primary_document"],
                    "pre_xml_url": "",
                    "source_type": "NONE",
                    "presentation_rows": 0,
                })
                continue

            xml_text = load_presentation_source(
                session,
                ticker,
                filing["accession"],
                source_url,
                source_type,
            )

            index_url = filing_index_url(cik, filing["accession"])
            rows = parse_presentation_xml(
                xml_text,
                ticker,
                cik,
                filing,
                index_url,
                source_url,
                source_type,
            )

            all_rows.extend(rows)

            calculation_rows = []
            if source_type == "EMBEDDED_XSD":
                calculation_rows = parse_calculation_xml(
                    xml_text,
                    ticker,
                    cik,
                    filing,
                    index_url,
                    source_url,
                    source_type,
                )
                all_calculation_rows.extend(calculation_rows)

            if rows:
                print(
                    f"  PARSED ({source_type}): "
                    f"{len(rows)} presentation arcs"
                )
                if source_type == "EMBEDDED_XSD":
                    print(
                        f"  Calculation arcs: "
                        f"{len(calculation_rows)}"
                    )
                status = "PARSED"
                note = ""
            else:
                print(f"  NO_PRESENTATION_LINKS ({source_type})")
                status = "NO_PRESENTATION"
                note = (
                    f"{source_type} source found, but it contained no "
                    "presentationLink relationships"
                )

            status_rows.append({
                "ticker": ticker,
                "cik": cik,
                "status": status,
                "note": note,
                "filing_accession": filing["accession"],
                "primary_document": filing["primary_document"],
                "pre_xml_url": source_url,
                "source_type": source_type,
                "presentation_rows": len(rows),
            })

            time.sleep(0.15)

        except Exception as error:
            print(f"  ERROR: {error}")
            status_rows.append({
                "ticker": ticker,
                "cik": cik or "",
                "status": "ERROR",
                "note": str(error),
                "filing_accession": "",
                "primary_document": "",
                "pre_xml_url": "",
                "source_type": "NONE",
                "presentation_rows": 0,
            })

    detail_path = output_dir / "presentation_rows.csv"
    frequency_path = output_dir / "presentation_tag_frequency.csv"
    status_path = output_dir / "presentation_harvest_status.csv"
    calculation_path = output_dir / "calculation_rows.csv"

    write_detail(all_rows, detail_path)
    write_frequency(all_rows, frequency_path)
    write_status(status_rows, status_path)
    write_calculation_detail(all_calculation_rows, calculation_path)

    parsed = sum(row["status"] == "PARSED" for row in status_rows)
    embedded = sum(
        row.get("source_type") == "EMBEDDED_XSD"
        and row["status"] == "PARSED"
        for row in status_rows
    )
    standalone = sum(
        row.get("source_type") == "PRE_XML"
        and row["status"] == "PARSED"
        for row in status_rows
    )
    missing = sum(
        row["status"] == "NO_PRESENTATION"
        for row in status_rows
    )
    errors = sum(row["status"] == "ERROR" for row in status_rows)

    print(f"\nParsed filings: {parsed}/{len(status_rows)}")
    print(f"  Standalone _pre.xml: {standalone}")
    print(f"  Embedded XSD:        {embedded}")
    print(f"  No presentation:     {missing}")
    print(f"  Errors:              {errors}")
    print(f"Wrote {detail_path} ({len(all_rows)} rows)")
    print(
        f"Wrote {calculation_path} "
        f"({len(all_calculation_rows)} rows)"
    )
    print(f"Wrote {frequency_path}")
    print(f"Wrote {status_path}")


if __name__ == "__main__":
    main()
