"""
Extract annual XBRL facts from a company's latest SEC filing, including
company-extension concepts absent from SEC CompanyFacts.

Examples:
    source ~/.config/northstar/sec.env
    PYTHONPATH=. python Dev_tools/xbrl/harvest_filing_facts.py MO --terms cost expense marketing administration research impairment exit

Output:
    Dev_tools/xbrl/runlogs/filing_facts_<TICKER>_<ACCESSION>.csv

Keeps only non-dimensional annual USD facts by default.
Use --include-dimensional to keep segmented facts too.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
from decimal import Decimal, InvalidOperation
from datetime import date
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import requests

from northstar.data.sources.sec_edgar import SECEdgarClient

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
CACHE_DIR = RUNLOGS / "filing_fact_cache"
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A"}
CIK_OVERRIDES = {"XOM": "0000034088"}


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    if ":" in tag:
        return tag.rsplit(":", 1)[-1]
    return tag


def get_user_agent() -> str:
    ua = os.getenv("SEC_USER_AGENT")
    if not ua:
        raise RuntimeError("SEC_USER_AGENT not set. Run: source ~/.config/northstar/sec.env")
    return ua


def make_session(ua: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})
    return s


def filing_base_url(cik: str, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"


def filing_index_url(cik: str, accession: str) -> str:
    return urljoin(filing_base_url(cik, accession), f"{accession}-index.htm")


def get_annual_candidates(session: requests.Session, cik: str) -> list[dict]:
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    recent = r.json().get("filings", {}).get("recent", {})
    recs = []
    for form, acc, fdate, doc in zip(
        recent.get("form", []),
        recent.get("accessionNumber", []),
        recent.get("filingDate", []),
        recent.get("primaryDocument", []),
    ):
        if form in ANNUAL_FORMS:
            recs.append({"form": form, "accession": acc, "filing_date": fdate, "primary_document": doc})
    recs.sort(key=lambda x: x["filing_date"], reverse=True)
    return recs


def find_fact_xml_url(session, cik, accession, primary_document) -> str:
    base = filing_base_url(cik, accession)
    try:
        r = session.get(urljoin(base, "index.json"), timeout=30)
        r.raise_for_status()
        names = [str(i.get("name", "")) for i in r.json().get("directory", {}).get("item", []) if i.get("name")]
        expected = f"{Path(primary_document).stem}_htm.xml"
        for n in names:
            if n.lower() == expected.lower():
                return urljoin(base, n)
        cands = [n for n in names if n.lower().endswith("_htm.xml")]
        if len(cands) == 1:
            return urljoin(base, cands[0])
    except Exception:
        pass
    return urljoin(base, primary_document)


def load_xml(session, ticker, accession, url) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = CACHE_DIR / f"{ticker}_{accession.replace('-', '')}_{Path(url).name}"
    if p.exists():
        return p.read_text(encoding="utf-8")
    r = session.get(url, timeout=60)
    r.raise_for_status()
    p.write_text(r.text, encoding="utf-8")
    return r.text


def build_ns_map(xml_text: str) -> dict:
    m = re.findall(r'xmlns:([A-Za-z0-9_\-\.]+)\s*=\s*"([^"]+)"', xml_text)
    out = {}
    for prefix, uri in m:
        if uri not in out:
            out[uri] = prefix
    return out


def normalize_measure(m: str) -> str:
    s = m.strip()
    local = s.split(":")[-1].lower()
    if local == "usd":
        return "USD"
    if local == "shares":
        return "shares"
    if local == "pure":
        return "pure"
    return s


def parse_units(root: ET.Element) -> dict:
    units = {}
    for elem in root.iter():
        if local_name(elem.tag) != "unit":
            continue
        uid = elem.attrib.get("id", "")
        if not uid:
            continue
        divide = None
        for child in elem:
            if local_name(child.tag) == "divide":
                divide = child
                break
        if divide is not None:
            num, den = [], []
            for child in divide.iter():
                ln = local_name(child.tag)
                if ln == "unitNumerator":
                    for mm in child.iter():
                        if local_name(mm.tag) == "measure" and mm.text:
                            num.append(normalize_measure(mm.text))
                if ln == "unitDenominator":
                    for mm in child.iter():
                        if local_name(mm.tag) == "measure" and mm.text:
                            den.append(normalize_measure(mm.text))
            units[uid] = "/".join(num) + ("/" + "/".join(den) if den else "")
        else:
            meas = ""
            for child in elem.iter():
                if local_name(child.tag) == "measure" and child.text:
                    meas = normalize_measure(child.text)
                    break
            units[uid] = meas
    return units


def parse_contexts(root: ET.Element) -> dict:
    ctxs = {}
    for elem in root.iter():
        if local_name(elem.tag) != "context":
            continue
        cid = elem.attrib.get("id", "")
        if not cid:
            continue
        start = end = instant = ""
        dims = []
        for child in elem.iter():
            ln = local_name(child.tag)
            if ln == "startDate":
                start = (child.text or "").strip()
            elif ln == "endDate":
                end = (child.text or "").strip()
            elif ln == "instant":
                instant = (child.text or "").strip()
            elif ln == "explicitMember":
                dims.append(f"{child.attrib.get('dimension', '')}={(child.text or '').strip()}")
            elif ln == "typedMember":
                dims.append(f"{child.attrib.get('dimension', '')}=TYPED_MEMBER")
        ctxs[cid] = {"start": start, "end": end, "instant": instant, "dimensions": dims}
    return ctxs


def concept_from_element(elem: ET.Element, ns_map: dict) -> str:
    tag = elem.tag
    if not tag.startswith("{"):
        return tag.strip()
    uri, local = tag[1:].split("}", 1)
    prefix = ns_map.get(uri, "")
    if prefix:
        return f"{prefix}:{local}"
    low = uri.lower()
    if "us-gaap" in low:
        return f"us-gaap:{local}"
    if "dei" in low:
        return f"dei:{local}"
    if "srt" in low:
        return f"srt:{local}"
    return local


def parse_inline_numeric(elem: ET.Element) -> Decimal | None:
    text = "".join(elem.itertext()).strip().replace(",", "").replace("$", "").replace("\xa0", "").strip()
    if text in ("", "\u2014", "-", "\u2013"):
        return None
    neg = False
    if text.startswith("(") and text.endswith(")"):
        neg = True
        text = text[1:-1].strip()
    try:
        v = Decimal(text)
    except InvalidOperation:
        return None
    if elem.attrib.get("sign", "") == "-":
        v = -abs(v)
    scale = elem.attrib.get("scale", "")
    if scale not in ("", None):
        try:
            v = v * (Decimal(10) ** int(scale))
        except Exception:
            pass
    if neg:
        v = -abs(v)
    return v


def parse_instance_numeric(elem: ET.Element) -> Decimal | None:
    text = "".join(elem.itertext()).strip().replace(",", "").replace("$", "").replace("\xa0", "").strip()
    if text in ("", "\u2014", "-", "\u2013"):
        return None
    neg = False
    if text.startswith("(") and text.endswith(")"):
        neg = True
        text = text[1:-1].strip()
    try:
        v = Decimal(text)
    except InvalidOperation:
        return None
    if neg:
        v = -abs(v)
    return v


def parse_annual_facts(root, xml_text, contexts, units, include_dimensional) -> list[dict]:
    ns_map = build_ns_map(xml_text)
    rows = []
    for elem in root.iter():
        lname = local_name(elem.tag)
        if lname in ("context", "unit", "schemaRef", "xbrl"):
            continue
        ctx_ref = elem.attrib.get("contextRef") or elem.attrib.get("contextref") or ""
        if not ctx_ref:
            continue
        ctx = contexts.get(ctx_ref)
        if not ctx:
            continue
        start, end = ctx["start"], ctx["end"]
        if not start or not end:
            continue
        try:
            days = (date.fromisoformat(end) - date.fromisoformat(start)).days
        except ValueError:
            continue
        if not 330 <= days <= 370:
            continue
        dims = ctx["dimensions"]
        if dims and not include_dimensional:
            continue
        if lname == "nonFraction":
            concept = (elem.attrib.get("name") or "").strip()
            if not concept:
                continue
            uref = elem.attrib.get("unitRef") or elem.attrib.get("unitref") or ""
            unit = units.get(uref, uref)
            if unit != "USD":
                continue
            v = parse_inline_numeric(elem)
            if v is None:
                continue
            rows.append({"concept": concept, "value": str(v), "unit": unit,
                         "context_ref": ctx_ref, "period_start": start, "period_end": end,
                         "dimension_count": len(dims), "dimensions": " | ".join(dims),
                         "scale": elem.attrib.get("scale", ""), "sign": elem.attrib.get("sign", "")})
        elif lname == "nonNumeric":
            continue
        else:
            uref = elem.attrib.get("unitRef") or elem.attrib.get("unitref") or ""
            if not uref:
                continue
            unit = units.get(uref, uref)
            if unit != "USD":
                continue
            concept = concept_from_element(elem, ns_map)
            if not concept or ":" not in concept:
                continue
            v = parse_instance_numeric(elem)
            if v is None:
                continue
            rows.append({"concept": concept, "value": str(v), "unit": unit,
                         "context_ref": ctx_ref, "period_start": start, "period_end": end,
                         "dimension_count": len(dims), "dimensions": " | ".join(dims),
                         "scale": "", "sign": ""})
    seen = set()
    uniq = []
    for r in rows:
        k = (r["concept"], r["value"], r["unit"], r["period_start"], r["period_end"], r["dimensions"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    return uniq


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--include-dimensional", action="store_true")
    ap.add_argument("--terms", nargs="*", default=[])
    args = ap.parse_args()
    ticker = args.ticker.upper().strip()
    ua = get_user_agent()
    session = make_session(ua)
    client = SECEdgarClient(user_agent=ua)
    cik = CIK_OVERRIDES.get(ticker) or client.resolve_cik(ticker)
    cands = get_annual_candidates(session, cik)
    if not cands:
        raise SystemExit(f"No annual filing for {ticker}")
    rows, used = [], None
    last_url = ""
    for cand in cands[:4]:
        try:
            url = find_fact_xml_url(session, cik, cand["accession"], cand["primary_document"])
            last_url = url
            xml_text = load_xml(session, ticker, cand["accession"], url)
            root = ET.fromstring(xml_text)
            contexts = parse_contexts(root)
            units = parse_units(root)
            rows = parse_annual_facts(root, xml_text, contexts, units, args.include_dimensional)
            if rows:
                used = cand
                break
        except Exception as e:
            print(f"  tried {cand['form']} {cand['accession']}: {e}")
            continue
    if not rows or not used:
        print(f"Ticker: {ticker} CIK: {cik} -- no annual USD facts found in first {min(4, len(cands))} filings")
        return
    for r in rows:
        r.update({"ticker": ticker, "cik": cik, "form": used["form"],
                  "filing_date": used["filing_date"], "filing_accession": used["accession"],
                  "filing_index_url": filing_index_url(cik, used["accession"]), "inline_xml_url": last_url})
    rows.sort(key=lambda x: (x["concept"], x["period_end"], x["value"]))
    RUNLOGS.mkdir(parents=True, exist_ok=True)
    out = RUNLOGS / f"filing_facts_{ticker}_{used['accession'].replace('-', '')}.csv"
    fields = ["ticker", "cik", "form", "filing_date", "filing_accession", "filing_index_url",
              "inline_xml_url", "concept", "value", "unit", "context_ref",
              "period_start", "period_end", "dimension_count", "dimensions", "scale", "sign"]
    with out.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    ext = [r for r in rows if ":" in r["concept"] and not r["concept"].startswith(("us-gaap:", "dei:", "srt:", "invest:"))]
    print(f"Ticker: {ticker} CIK: {cik}")
    print(f"Filing: {used['form']} | {used['accession']} | filed {used['filing_date']}")
    print(f"Annual non-dimensional numeric facts: {len(rows)}")
    print(f"Company-extension facts: {len(ext)}")
    print(f"Wrote {out}")
    if args.terms:
        terms = [t.lower().replace(" ", "") for t in args.terms]
        print("\nMatching annual default-context facts:")
        shown = 0
        for r in rows:
            cn = re.sub(r"[^a-z0-9]+", "", r["concept"].lower())
            if any(t in cn for t in terms):
                try:
                    m = float(r["value"]) / 1_000_000
                    disp = f"{m:,.1f}M"
                except ValueError:
                    disp = r["value"]
                print(f"  {r['concept']:<70} {disp:>14}  unit={r['unit']}")
                shown += 1
                if shown >= 80:
                    break


if __name__ == "__main__":
    main()
