"""
Build canonical income statement order from presentation linkbase.

Input:  presentation_rows.csv (96/100 parsed, 155k rows)
Output: canonical_order_IS_xbrl.csv
        One row per observed IS face concept, ordered by median sibling position.

This is the XBRL equivalent of canonical_order_IS.csv from the SA drift tool.
Research only — order is evidence, not final platform approval.
"""
import csv
from collections import defaultdict
from pathlib import Path

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
INPUT = RUNLOGS / "presentation_rows.csv"
GLOSSARY = RUNLOGS / "xbrl_glossary.csv"
OUTPUT = RUNLOGS / "canonical_order_IS_xbrl.csv"

def load_glossary():
    if not GLOSSARY.exists():
        return {}
    with GLOSSARY.open(newline="", encoding="utf-8") as h:
        return {r["concept"]: r for r in csv.DictReader(h)}

def main():
    glossary = load_glossary()
    positions = defaultdict(list)
    tickers_by_concept = defaultdict(set)
    roles_by_concept = defaultdict(set)
    examples = {}

    with INPUT.open(newline="", encoding="utf-8") as h:
        for row in csv.DictReader(h):
            if row["statement_category"] != "income_statement":
                continue
            if row["is_structural"].lower() == "true":
                continue
            concept = row["child_concept"]
            if not concept:
                continue
            try:
                order = int(row["sibling_order"]) if row["sibling_order"] else 999
            except ValueError:
                order = 999

            positions[concept].append(order)
            tickers_by_concept[concept].add(row["ticker"])
            roles_by_concept[concept].add(row["statement_role"])
            if concept not in examples:
                examples[concept] = row

    rows = []
    for concept, orders in positions.items():
        median_pos = sorted(orders)[len(orders)//2]
        g = glossary.get(concept, {})
        rows.append({
            "canonical_position": median_pos,
            "concept": concept,
            "label": g.get("label", ""),
            "mapped": g.get("mapped", ""),
            "mapped_refs": g.get("mapped_refs", ""),
            "company_count": len(tickers_by_concept[concept]),
            "median_order": median_pos,
            "example_ticker": examples[concept]["ticker"],
            "example_accession": examples[concept]["filing_accession"],
        })

    rows.sort(key=lambda r: (r["median_order"], r["concept"]))

    for idx, r in enumerate(rows, start=1):
        r["canonical_position"] = idx

    with OUTPUT.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=[
            "canonical_position","concept","label","mapped","mapped_refs",
            "company_count","median_order","example_ticker","example_accession"
        ])
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {OUTPUT} ({len(rows)} concepts)")
    print("\nTop 50 by canonical position (20+ companies):")
    for r in rows:
        if r["company_count"] >= 20:
            print(f"{r['canonical_position']:>3} {r['company_count']:>3} {r['mapped']} {r['concept']:<70} {r['label'][:40]}")
    print(f"\nUnmapped face concepts in 20+ companies: {sum(1 for r in rows if r['mapped']=='N' and r['company_count']>=20)}")

if __name__ == "__main__":
    main()
