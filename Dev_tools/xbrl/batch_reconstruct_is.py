"""
Batch filing-level IS reconstruction summary for 100-company sample.

Research only. Reads:
  filing_facts_<TICKER>_<ACCESSION>.csv
  presentation_rows.csv
  xbrl_glossary.csv (for labels)

Downloads *_cal.xml calculation linkbases (cached) and checks every subtotal
with the filer's own weights. Role-scoped, so totals don't double-count.

Usage:
  source ~/.config/northstar/sec.env
  PYTHONPATH=. python Dev_tools/xbrl/batch_reconstruct_is.py --limit 20
  PYTHONPATH=. python Dev_tools/xbrl/batch_reconstruct_is.py --file Dev_tools/xbrl/tickers_100_usable.txt --limit 100

Output:
  Dev_tools/xbrl/runlogs/reconstructed_is_batch_summary.csv
"""

import argparse
import csv
import os
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import requests

from northstar.data.sources.sec_edgar import SECEdgarClient

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
CACHE_DIR = RUNLOGS / "filing_fact_cache"
DEFAULT_TICKERS = Path("Dev_tools/xbrl/tickers_100_usable.txt")
OUT = RUNLOGS / "reconstructed_is_batch_summary.csv"

LINK_NS = "http://www.xbrl.org/2003/linkbase"
XLINK_NS = "http://www.w3.org/1999/xlink"
XLINK_LABEL = f"{{{XLINK_NS}}}label"
XLINK_HREF = f"{{{XLINK_NS}}}href"
XLINK_FROM = f"{{{XLINK_NS}}}from"
XLINK_TO = f"{{{XLINK_NS}}}to"
XLINK_ARCROLE = f"{{{XLINK_NS}}}arcrole"
NEGATED_LABELS = {"negatedLabel", "negatedTerseLabel", "negatedVerboseLabel"}
SKIP_LOCAL_PARTS = ("EarningsPerShare", "WeightedAverage", "SharesOutstanding", "EntityCommonStock")
STRUCTURAL_SUFFIXES = ("Abstract", "Table", "Axis", "Domain", "Member", "LineItems")

def get_user_agent():
    ua = os.getenv("SEC_USER_AGENT")
    if not ua:
        raise RuntimeError("SEC_USER_AGENT not set. Run: source ~/.config/northstar/sec.env")
    return ua

def make_session(ua):
    s = requests.Session()
    s.headers.update({"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})
    return s

def filing_base_url(cik, accession):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"

def filing_index_url(cik, accession):
    return urljoin(filing_base_url(cik, accession), f"{accession}-index.htm")

def concept_from_href(href):
    if not href:
        return ""
    frag = href.rsplit("#", 1)[-1]
    if "_" not in frag:
        return frag
    ns, concept = frag.split("_", 1)
    ns = ns.replace("us-gaap-", "us-gaap").replace("ifrs-full-", "ifrs-full")
    return f"{ns}:{concept}"

def is_structural(concept):
    return concept.split(":")[-1].endswith(STRUCTURAL_SUFFIXES)

def should_skip_subtree(concept):
    local = concept.split(":")[-1]
    return any(p in local for p in SKIP_LOCAL_PARTS)

def load_filing_facts(ticker):
    files = sorted(RUNLOGS.glob(f"filing_facts_{ticker}_*.csv"))
    if not files:
        return None, []
    path = files[-1]
    with path.open(newline="", encoding="utf-8") as h:
        rows = list(csv.DictReader(h))
    raw_acc = rows[0].get("filing_accession") if rows else path.stem.split("_")[-1]
    return raw_acc, rows

def load_presentation_index():
    index = defaultdict(list)
    p = RUNLOGS / "presentation_rows.csv"
    if not p.exists():
        return index
    with p.open(newline="", encoding="utf-8") as h:
        for r in csv.DictReader(h):
            if r["statement_category"] in ("income_statement", "comprehensive_income_statement"):
                clean_acc = r["filing_accession"].replace("-", "")
                index[(r["ticker"], clean_acc)].append(r)
    return index

def select_role(rows):
    """
    Prefer a true income-statement role. Fall back to a comprehensive-income
    role only when the filing has none (combined statements labeled only as
    'ComprehensiveIncome', e.g. ALLE, ATO).
    """
    income = [r for r in rows if r["statement_category"] == "income_statement"]
    pool = income if income else rows
    c = Counter(r["statement_role"] for r in pool)
    return c.most_common(1)[0][0]


def build_tree(rows):
    children = defaultdict(list)
    child_set = set()
    negated = set()
    calc_groups = defaultdict(list)
    all_concepts = set()
    for r in rows:
        parent = r["parent_concept"]
        child = r["child_concept"]
        lr = r["preferred_label_role"]
        try:
            order_key = int(r["sibling_order"]) if r["sibling_order"] else 9999
        except ValueError:
            order_key = 9999
        if lr == "totalLabel":
            calc_groups[parent].append(child)
        elif lr in NEGATED_LABELS:
            negated.add(child)
        else:
            children[parent].append((order_key, child))
            child_set.add(child)
        all_concepts.add(parent)
        all_concepts.add(child)
    for par in list(children.keys()):
        children[par].sort(key=lambda x: (x[0], x[1]))
        children[par] = [c for _, c in children[par]]
    roots = sorted(all_concepts - child_set)
    return children, roots, negated, calc_groups

def annual_periods(fact_rows):
    return sorted({r["period_end"] for r in fact_rows if r["period_start"] and r["period_end"] and r["unit"] == "USD"})

def build_value_map(fact_rows, period_end):
    vals = {}
    for r in fact_rows:
        if r["unit"] != "USD" or r["period_end"] != period_end or r["dimension_count"] != "0" or not r["period_start"]:
            continue
        try:
            vals[r["concept"]] = float(r["value"])
        except (TypeError, ValueError):
            continue
    return vals

def expected_cal_name(fact_rows):
    for r in fact_rows:
        u = r.get("inline_xml_url", "")
        if u.endswith("_htm.xml"):
            return u.rsplit("/", 1)[-1].replace("_htm.xml", "_cal.xml")
    return None

def find_cal_name(session, cik, accession, expected):
    base = filing_base_url(cik, accession)
    try:
        r = session.get(urljoin(base, "index.json"), timeout=30)
        r.raise_for_status()
        names = [i.get("name", "") for i in r.json().get("directory", {}).get("item", []) if i.get("name")]
        cands = [n for n in names if n.lower().endswith("_cal.xml")]
        if not cands:
            return None
        if expected:
            for n in cands:
                if n.lower() == expected.lower():
                    return n
        return cands[0]
    except Exception:
        return None

def load_cal_xml(session, ticker, cik, accession, cal_name):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = CACHE_DIR / f"{ticker}_{accession.replace('-', '')}_{cal_name}"
    if p.exists():
        return p.read_text(encoding="utf-8")
    url = urljoin(filing_base_url(cik, accession), cal_name)
    r = session.get(url, timeout=60)
    r.raise_for_status()
    p.write_text(r.text, encoding="utf-8")
    return r.text

def parse_calc_raw(xml_text):
    root = ET.fromstring(xml_text)
    arcs = []
    for link in root.iter(f"{{{LINK_NS}}}calculationLink"):
        role = link.get(f"{{{XLINK_NS}}}role") or ""
        locators = {}
        for loc in link.iter(f"{{{LINK_NS}}}loc"):
            label = loc.get(XLINK_LABEL) or ""
            if label:
                locators[label] = concept_from_href(loc.get(XLINK_HREF) or "")
        for arc in link.iter(f"{{{LINK_NS}}}calculationArc"):
            if "summation-item" not in (arc.get(XLINK_ARCROLE) or ""):
                continue
            frm = locators.get(arc.get(XLINK_FROM) or "", "")
            to = locators.get(arc.get(XLINK_TO) or "", "")
            if not frm or not to:
                continue
            try:
                w = float(arc.get("weight", "1"))
            except (TypeError, ValueError):
                w = 1.0
            arcs.append((role, frm, to, w))
    return arcs

def build_calc_map(raw_arcs, from_is_total, role):
    m = defaultdict(list)
    for arc_role, frm, to, w in raw_arcs:
        if role is not None and arc_role != role:
            continue
        total, item = (frm, to) if from_is_total else (to, frm)
        m[total].append((item, w))
    return m

def select_calc_role(raw_arcs, pres_role):
    roles = {r for r, _, _, _ in raw_arcs}
    if not roles:
        return None
    if pres_role in roles:
        return pres_role
    tail = pres_role.rsplit("/", 1)[-1].lower()
    for r in roles:
        if r.rsplit("/", 1)[-1].lower() == tail:
            return r
    return None

def choose_calc_direction(raw_arcs, values, tol, role):
    best_score = -1
    best = True
    for from_is_total in (True, False):
        calc_map = build_calc_map(raw_arcs, from_is_total, role)
        ok = 0
        for total, items in calc_map.items():
            if total not in values:
                continue
            if any(it not in values for it, _ in items):
                continue
            comp = sum(w * values[it] for it, w in items)
            if abs(comp - values[total]) <= tol:
                ok += 1
        if ok > best_score:
            best_score = ok
            best = from_is_total
    return best

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--file", type=str, default=str(DEFAULT_TICKERS))
    parser.add_argument("--tolerance", type=float, default=2_000_000.0)
    args = parser.parse_args()

    tickers_path = Path(args.file)
    tickers = [l.strip().upper() for l in tickers_path.read_text(encoding="utf-8", errors="ignore").splitlines() if l.strip()]
    if args.limit:
        tickers = tickers[:args.limit]

    print(f"Loaded {len(tickers)} tickers from {tickers_path}")

    ua = get_user_agent()
    session = make_session(ua)
    pres_index = load_presentation_index()
    rows = []

    for idx, ticker in enumerate(tickers, start=1):
        print(f"[{idx}/{len(tickers)}] {ticker}")
        acc, fact_rows = load_filing_facts(ticker)
        if not fact_rows:
            rows.append({"ticker": ticker, "status": "NO_FACTS", "filing_accession": "", "period_end": "", "totals_checked": 0, "OK": 0, "FAIL": 0, "SKIP": 0, "NO_CALC": 0, "missing": "", "filing_index_url": ""})
            continue
        cik = next((r["cik"] for r in fact_rows if r.get("cik")), "")
        clean_acc = acc.replace("-", "")
        pres_rows = pres_index.get((ticker, clean_acc), [])
        if not pres_rows:
            rows.append({"ticker": ticker, "status": "NO_PRESENTATION", "filing_accession": acc, "period_end": "", "totals_checked": 0, "OK": 0, "FAIL": 0, "SKIP": 0, "NO_CALC": 0, "missing": "", "filing_index_url": filing_index_url(cik, acc) if cik else ""})
            continue
        role = select_role(pres_rows)
        role_rows = [r for r in pres_rows if r["statement_role"] == role]
        children, roots, negated, pres_calc_groups = build_tree(role_rows)
        periods = annual_periods(fact_rows)
        period_end = periods[-1] if periods else ""
        if not period_end:
            rows.append({"ticker": ticker, "status": "NO_PERIOD", "filing_accession": acc, "period_end": "", "totals_checked": 0, "OK": 0, "FAIL": 0, "SKIP": 0, "NO_CALC": 0, "missing": "", "filing_index_url": filing_index_url(cik, acc)})
            continue
        values = build_value_map(fact_rows, period_end)
        cal_name = find_cal_name(session, cik, acc, expected_cal_name(fact_rows))
        calc_map = {}
        if cal_name:
            try:
                cal_text = load_cal_xml(session, ticker, cik, acc, cal_name)
                raw_arcs = parse_calc_raw(cal_text)
                calc_role = select_calc_role(raw_arcs, role)
                from_is_total = choose_calc_direction(raw_arcs, values, args.tolerance, calc_role)
                calc_map = build_calc_map(raw_arcs, from_is_total, calc_role)
            except Exception as e:
                print(f"  cal load failed: {e}")
        time.sleep(0.15)

        counts = Counter()
        missing = []

        def check_total(node, reported):
            if node in calc_map:
                group = calc_map[node]
            elif node in pres_calc_groups:
                group = [(c, 1.0) for c in pres_calc_groups[node]]
            else:
                return "NO_CALC"
            if any(it not in values for it, _ in group):
                return "SKIP"
            comp = sum(w * values[it] for it, w in group)
            return "OK" if abs(comp - reported) <= args.tolerance else "FAIL"

        # Walk only totals
        def walk_totals(node):
            if should_skip_subtree(node) or node.split(":")[-1].endswith(("Axis", "Domain", "Member")):
                return
            if is_structural(node):
                for ch in children.get(node, []):
                    walk_totals(ch)
                return
            if node in calc_map or node in pres_calc_groups:
                v = values.get(node)
                if v is None:
                    counts["SKIP"] += 1
                    missing.append(node.split(":")[-1])
                else:
                    counts[check_total(node, v)] += 1
            for ch in children.get(node, []):
                walk_totals(ch)

        for rt in roots:
            walk_totals(rt)

        total_checked = counts["OK"] + counts["FAIL"] + counts["SKIP"] + counts["NO_CALC"]
        if total_checked == 0:
            status = "NO_TOTALS"
        elif counts["FAIL"] > 0:
            status = "FAIL"
        elif counts["SKIP"] > 0:
            status = "PARTIAL"
        else:
            status = "RECONCILES"

        rows.append({
            "ticker": ticker,
            "status": status,
            "filing_accession": acc,
            "period_end": period_end,
            "totals_checked": total_checked,
            "OK": counts["OK"],
            "FAIL": counts["FAIL"],
            "SKIP": counts["SKIP"],
            "NO_CALC": counts["NO_CALC"],
            "missing": "|".join(missing[:10]),
            "filing_index_url": filing_index_url(cik, acc),
        })

    with OUT.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=["ticker","status","filing_accession","period_end","totals_checked","OK","FAIL","SKIP","NO_CALC","missing","filing_index_url"])
        w.writeheader()
        w.writerows(rows)

    by_status = Counter(r["status"] for r in rows)
    print("\nBatch filing-level summary")
    for s, n in by_status.most_common():
        print(f"  {s:<20} {n}")
    print(f"\nWrote {OUT}")

if __name__ == "__main__":
    main()
