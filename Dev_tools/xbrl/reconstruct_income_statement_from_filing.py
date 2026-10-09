"""
Reconstruct the face of the income statement directly from a company's SEC
filing XBRL linkbases, and verify every subtotal with the filer's own math.

Accepts one or many tickers:
    PYTHONPATH=. python Dev_tools/xbrl/reconstruct_income_statement_from_filing.py MO CF CCL
    PYTHONPATH=. python Dev_tools/xbrl/reconstruct_income_statement_from_filing.py BA XYZ APD ALB AMCR APH BBY CAH CARR CVNA COR

Output:
    Dev_tools/xbrl/runlogs/reconstructed_IS_<TICKER>_<ACCESSION>.csv
"""

from collections import Counter, defaultdict
import argparse
import csv
import sys

csv.field_size_limit(sys.maxsize)
import os
import time
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import requests

from northstar.data.sources.sec_edgar import SECEdgarClient

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
CACHE_DIR = RUNLOGS / "filing_fact_cache"

LINK_NS = "http://www.xbrl.org/2003/linkbase"
XLINK_NS = "http://www.w3.org/1999/xlink"
XLINK_LABEL = f"{{{XLINK_NS}}}label"
XLINK_HREF = f"{{{XLINK_NS}}}href"
XLINK_FROM = f"{{{XLINK_NS}}}from"
XLINK_TO = f"{{{XLINK_NS}}}to"
XLINK_ARCROLE = f"{{{XLINK_NS}}}arcrole"

NEGATED_LABELS = {"negatedLabel", "negatedTerseLabel", "negatedVerboseLabel"}

SKIP_LOCAL_PARTS = (
    "EarningsPerShare",
    "WeightedAverage",
    "SharesOutstanding",
    "EntityCommonStock",
)

STRUCTURAL_SUFFIXES = ("Abstract", "Table", "Axis", "Domain", "Member", "LineItems")


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


def concept_from_href(href: str) -> str:
    if not href:
        return ""
    fragment = href.rsplit("#", 1)[-1]
    if "_" not in fragment:
        return fragment
    namespace, concept = fragment.split("_", 1)
    # Normalize standard taxonomy prefixes
    namespace = namespace.replace("us-gaap-", "us-gaap").replace("ifrs-full-", "ifrs-full")
    return f"{namespace}:{concept}"


def is_structural(concept: str) -> bool:
    local = concept.split(":")[-1]
    return local.endswith(STRUCTURAL_SUFFIXES)


def should_skip_subtree(concept: str) -> bool:
    local = concept.split(":")[-1]
    return any(part in local for part in SKIP_LOCAL_PARTS)


def load_filing_facts(ticker: str):
    files = sorted(RUNLOGS.glob(f"filing_facts_{ticker}_*.csv"))
    if not files:
        raise SystemExit(
            f"No filing facts for {ticker}. Run:\n"
            f"  PYTHONPATH=. python Dev_tools/xbrl/harvest_filing_facts.py {ticker}"
        )
    path = files[-1]
    with path.open(newline="", encoding="utf-8") as h:
        rows = list(csv.DictReader(h))
    raw_acc = rows[0].get("filing_accession") if rows else path.stem.split("_")[-1]
    return raw_acc, rows


def load_labels() -> dict:
    labels = {}
    path = RUNLOGS / "xbrl_glossary.csv"
    if path.exists():
        with path.open(newline="", encoding="utf-8") as h:
            for r in csv.DictReader(h):
                labels[r["concept"]] = r.get("label", "")
    return labels


def load_presentation_index() -> dict:
    index = defaultdict(list)
    path = RUNLOGS / "presentation_rows.csv"
    if not path.exists():
        return index
    with path.open(newline="", encoding="utf-8") as h:
        for r in csv.DictReader(h):
            if r["statement_category"] == "income_statement":
                # Normalize accession key by removing hyphens
                clean_acc = r["filing_accession"].replace("-", "")
                index[(r["ticker"], clean_acc)].append(r)
    return index


def select_role(rows: list) -> str:
    counts = Counter()
    for r in rows:
        counts[r["statement_role"]] += 1
    return counts.most_common(1)[0][0]


def build_tree(rows: list):
    children = defaultdict(list)
    meta = {}
    all_concepts = set()
    child_concepts = set()
    negated = set()
    pres_calc_groups = defaultdict(list)

    for r in rows:
        parent = r["parent_concept"]
        child = r["child_concept"]
        label_role = r["preferred_label_role"]
        order_raw = r["sibling_order"]
        try:
            order_key = int(order_raw)
        except (TypeError, ValueError):
            order_key = 9999

        if label_role == "totalLabel":
            pres_calc_groups[parent].append(child)
        elif label_role in NEGATED_LABELS:
            negated.add(child)
        else:
            children[parent].append((order_key, child))
            meta[child] = (parent, order_raw)
            child_concepts.add(child)

        all_concepts.add(parent)
        all_concepts.add(child)

    for parent, items in children.items():
        items.sort(key=lambda item: (item[0], item[1]))
        children[parent] = [child for _, child in items]

    roots = sorted(all_concepts - child_concepts)
    return children, meta, roots, negated, pres_calc_groups


def annual_periods(fact_rows: list) -> list:
    periods = set()
    for r in fact_rows:
        if r["period_start"] and r["period_end"] and r["unit"] == "USD":
            periods.add(r["period_end"])
    return sorted(periods)


def build_value_map(fact_rows: list, period_end: str) -> dict:
    values = {}
    for r in fact_rows:
        if r["unit"] != "USD":
            continue
        if r["period_end"] != period_end:
            continue
        if r["dimension_count"] != "0":
            continue
        if not r["period_start"]:
            continue
        try:
            values[r["concept"]] = float(r["value"])
        except (TypeError, ValueError):
            continue
    return values


def expected_cal_name(fact_rows: list) -> str | None:
    for r in fact_rows:
        url = r.get("inline_xml_url", "")
        if url.endswith("_htm.xml"):
            return url.rsplit("/", 1)[-1].replace("_htm.xml", "_cal.xml")
    return None


def find_cal_name(session, cik, accession, expected, ticker):
    base = filing_base_url(cik, accession)
    try:
        r = session.get(urljoin(base, "index.json"), timeout=30)
        r.raise_for_status()
        names = [
            i.get("name", "")
            for i in r.json().get("directory", {}).get("item", [])
            if i.get("name")
        ]
        cands = [n for n in names if n.lower().endswith("_cal.xml")]
        if not cands:
            return None
        if expected:
            for n in cands:
                if n.lower() == expected.lower():
                    return n
        if len(cands) == 1:
            return cands[0]
        return cands[0]
    except Exception:
        return None


def load_cal_xml(session, ticker, cik, accession, cal_name):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{ticker}_{accession.replace('-', '')}_{cal_name}"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    url = urljoin(filing_base_url(cik, accession), cal_name)
    r = session.get(url, timeout=60)
    r.raise_for_status()
    cache_path.write_text(r.text, encoding="utf-8")
    return r.text


def parse_calc_raw(xml_text: str) -> list:
    """
    Return (role, from_concept, to_concept, weight) per summation-item arc.

    A _cal.xml holds one calculation network per statement/disclosure role.
    Locator labels are scoped to their own calculationLink, and the same
    total can appear in several networks, so arcs must stay role-scoped or
    components get double counted.
    """
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
                weight = float(arc.get("weight", "1"))
            except (TypeError, ValueError):
                weight = 1.0
            arcs.append((role, frm, to, weight))

    return arcs


def build_calc_map(raw_arcs: list, from_is_total: bool, role: str | None = None) -> dict:
    """Build total -> [(component, weight)] for one calculation network."""
    calc_map = defaultdict(list)
    for arc_role, frm, to, weight in raw_arcs:
        if role is not None and arc_role != role:
            continue
        total, item = (frm, to) if from_is_total else (to, frm)
        calc_map[total].append((item, weight))
    return calc_map


def select_calc_role(raw_arcs: list, presentation_role: str) -> str | None:
    """
    Pick the calculation network for this statement.

    Prefer an exact role URI match with the presentation linkbase. Otherwise
    fall back to the network whose concepts best overlap the statement.
    """
    roles = {arc_role for arc_role, _, _, _ in raw_arcs}
    if not roles:
        return None
    if presentation_role in roles:
        return presentation_role

    presentation_tail = presentation_role.rsplit("/", 1)[-1].lower()
    for role in roles:
        if role.rsplit("/", 1)[-1].lower() == presentation_tail:
            return role
    return None


def choose_calc_direction(raw_arcs: list, values: dict, tol: float,
                          role: str | None = None) -> bool:
    best_score = -1
    best_from_is_total = True
    for from_is_total in (True, False):
        calc_map = build_calc_map(raw_arcs, from_is_total, role)
        ok = 0
        for total, items in calc_map.items():
            if total not in values:
                continue
            if any(item not in values for item, _ in items):
                continue
            computed = sum(w * values[item] for item, w in items)
            if abs(computed - values[total]) <= tol:
                ok += 1
        if ok > best_score:
            best_score = ok
            best_from_is_total = from_is_total
    return best_from_is_total


def infer_signs(items: list, target: float, tol: float, max_components: int = 16):
    if len(items) > max_components:
        return None
    items = sorted(items, key=lambda item: -abs(item[1]))
    signs = [1.0] * len(items)

    def dfs(index, running):
        if index == len(items):
            return abs(running - target) <= tol
        for sign in (1.0, -1.0):
            signs[index] = sign
            if dfs(index + 1, running + sign * items[index][1]):
                return True
        return False

    if dfs(0, 0.0):
        return [(items[i][0], signs[i] * items[i][1]) for i in range(len(items))]
    return None


def reconstruct(session, ticker: str, labels: dict, pres_index: dict,
                period_override: str | None, tol: float) -> None:
    accession, fact_rows = load_filing_facts(ticker)
    cik = next((r["cik"] for r in fact_rows if r.get("cik")), "")
    if not cik:
        raise SystemExit(f"{ticker}: no CIK in filing facts CSV")

    clean_acc = accession.replace("-", "")
    rows = pres_index.get((ticker, clean_acc))
    if not rows:
        print(f"\n=== {ticker} ===\nNo income-statement presentation rows for {ticker} ({accession}). Skipping.\n")
        return

    role = select_role(rows)
    role_rows = [r for r in rows if r["statement_role"] == role]
    children, meta, roots, negated, pres_calc_groups = build_tree(role_rows)

    periods = annual_periods(fact_rows)
    if not periods:
        print(f"\n=== {ticker} ===\nNo annual USD periods in filing facts. Skipping.\n")
        return

    period_end = period_override or periods[-1]
    if period_end not in periods:
        print(f"\n=== {ticker} ===\nPeriod {period_end} not in filing facts; have {periods}. Skipping.\n")
        return

    values = build_value_map(fact_rows, period_end)

    cal_name = find_cal_name(session, cik, accession, expected_cal_name(fact_rows), ticker)
    if cal_name:
        cal_text = load_cal_xml(session, ticker, cik, accession, cal_name)
        raw_arcs = parse_calc_raw(cal_text)
        calc_role = select_calc_role(raw_arcs, role)
        from_is_total = choose_calc_direction(raw_arcs, values, tol, calc_role)
        calc_map = build_calc_map(raw_arcs, from_is_total, calc_role)
        scoped = sum(1 for r, _, _, _ in raw_arcs if calc_role is None or r == calc_role)
        direction = "from=total" if from_is_total else "to=total"
        if calc_role is None:
            cal_note = (
                f"cal: {len(raw_arcs)} arcs, NO ROLE MATCH "
                f"(all networks merged, totals may double count), {direction}"
            )
        else:
            cal_note = f"cal: {scoped}/{len(raw_arcs)} arcs in statement network, {direction}"
    else:
        calc_map = {}
        cal_note = "cal: NOT FOUND (presentation totalLabel fallback only)"
    time.sleep(0.2)

    print("\n" + "=" * 100)
    print(f"{ticker} | {accession} | period {period_end} | role ...{role[-45:]} | {cal_note}")
    print("-" * 100)

    out_rows = []
    missing = []
    counts = defaultdict(int)

    def check_total(node, reported):
        if node in calc_map:
            group = calc_map[node]
            source = "cal"
        elif node in pres_calc_groups:
            raw = pres_calc_groups[node]
            if any(c not in values for c in raw):
                return "SKIP", "component value missing"
            inferred = infer_signs([(c, values[c]) for c in raw], reported, tol)
            if inferred is None:
                return "SKIP", "too many components to infer signs"
            group = inferred
            source = "INFERRED"
        else:
            return "NO_CALC", "no summation arcs"

        if any(item not in values for item, _ in group):
            return "SKIP", "component value missing"

        computed = sum(w * values[item] for item, w in group)
        delta = computed - reported
        if abs(delta) <= tol:
            return "OK", f"{source}, {len(group)} components"
        return "FAIL", (
            f"{source}: computed {computed / 1e6:,.1f}M vs reported "
            f"{reported / 1e6:,.1f}M (delta {delta / 1e6:+,.1f}M)"
        )

    def render_node(node, depth):
        local = node.split(":")[-1]

        if local.endswith(("Axis", "Domain", "Member")):
            return
        if should_skip_subtree(node):
            return

        label = labels.get(node) or local
        indent = "  " * depth

        if local in ("StatementLineItems", "IncomeStatementAbstract") or local.endswith("Table"):
            for child in children.get(node, []):
                render_node(child, depth)
            return

        if is_structural(node):
            print(f"{indent}{label[:60]}")
            out_rows.append({
                "ticker": ticker, "filing_accession": accession, "period_end": period_end,
                "depth": depth, "label": label, "concept": node, "value": "",
                "is_header": True, "is_total": False, "negated": False,
                "parent_concept": meta.get(node, ("", ""))[0],
                "sibling_order": meta.get(node, ("", ""))[1],
                "check_status": "", "check_detail": "",
            })
            for child in children.get(node, []):
                render_node(child, depth + 1)
            return

        value = values.get(node)
        is_total = node in calc_map or node in pres_calc_groups
        neg = node in negated

        check_status, check_detail = "", ""
        if is_total:
            if value is None:
                check_status, check_detail = "SKIP", "total value missing"
            else:
                check_status, check_detail = check_total(node, value)
            counts[check_status] += 1

        if value is None:
            missing.append(local)
            value_text = "-"
        else:
            value_text = f"{value / 1e6:,.1f}"

        marker = " [T]" if is_total else ""
        if neg:
            marker += " (neg)"

        line = f"{indent}{label[:46]:<46}{value_text:>12}{marker}"
        if check_status:
            line += f"   {check_status}"
            if check_detail and check_status in ("OK", "FAIL"):
                line += f" - {check_detail}"
        print(line.rstrip())

        out_rows.append({
            "ticker": ticker, "filing_accession": accession, "period_end": period_end,
            "depth": depth, "label": label, "concept": node,
            "value": "" if value is None else value,
            "is_header": False, "is_total": is_total, "negated": neg,
            "parent_concept": meta.get(node, ("", ""))[0],
            "sibling_order": meta.get(node, ("", ""))[1],
            "check_status": check_status, "check_detail": check_detail,
        })

        for child in children.get(node, []):
            render_node(child, depth + 1)

    for root in roots:
        render_node(root, 0)

    out_path = RUNLOGS / f"reconstructed_IS_{ticker}_{clean_acc}.csv"
    fields = [
        "ticker", "filing_accession", "period_end", "depth", "label", "concept",
        "value", "is_header", "is_total", "negated", "parent_concept",
        "sibling_order", "check_status", "check_detail",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)

    total_checked = counts["OK"] + counts["FAIL"] + counts["SKIP"] + counts["NO_CALC"]
    print("-" * 100)
    print(f"Totals checked: {total_checked}   OK: {counts['OK']}   FAIL: {counts['FAIL']}   "
          f"SKIP: {counts['SKIP']}   NO_CALC: {counts['NO_CALC']}")
    if missing:
        print(f"Missing values this period: {', '.join(missing)}")
    else:
        print("Missing values this period: none")
    print(f"Wrote {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconstruct and verify a company's income statement from SEC filing XBRL linkbases."
    )
    parser.add_argument("tickers", nargs="+", help="One or more tickers, e.g. MO CF CCL")
    parser.add_argument("--period", default=None, help="Period end YYYY-MM-DD. Default: latest annual period.")
    parser.add_argument("--tolerance", type=float, default=2_000_000.0)
    args = parser.parse_args()

    user_agent = get_user_agent()
    session = make_session(user_agent)
    labels = load_labels()
    pres_index = load_presentation_index()

    for ticker in args.tickers:
        try:
            reconstruct(
                session=session,
                ticker=ticker.upper(),
                labels=labels,
                pres_index=pres_index,
                period_override=args.period,
                tol=args.tolerance,
            )
        except Exception as e:
            print(f"\n=== {ticker} ===\nERROR: {e}\n")


if __name__ == "__main__":
    main()
