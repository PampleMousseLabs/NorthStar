"""
For each top-half MISMATCH, measure the residual against unmapped annual
facts in the same period. Cached CompanyFacts only; no downloads.

Residual = base_formula_value - reported_operating_income

Reports single-concept matches and 2-concept sums. Excludes concepts already
mapped, and excludes tax-note / OCI / cash-flow noise.

Research output only. A numeric match is a candidate, not approval.
"""

import csv
import json
from collections import Counter
from datetime import date
from itertools import combinations
from pathlib import Path

from northstar.data.sources.sec_edgar import SECEdgarClient
from northstar.data.transforms.sec_xbrl import select_annual_facts
from northstar.data.transforms.sec_xbrl_key import _EXPLICIT_XBRL_ALIASES
from Dev_tools.xbrl.industry_map import industry_for

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
SUMMARY = RUNLOGS / "top_half_archetype_summary.csv"
OUTPUT = RUNLOGS / "top_half_residual_candidates.csv"

ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A"}

EXCLUDE = (
    "incometax", "unrecognizedtax", "deferredtax", "effectiveincometax",
    "comprehensiveincome", "aoci", "othercomprehensive",
    "netcashprovided", "netcashused", "proceedsfrom", "paymentsfor",
    "paymentsto", "cashandcash", "sharebasedcompensation",
    "weightedaverage", "earningspershare", "dividend",
    "pension", "postretirement", "definedbenefit", "definedcontribution",
)


def mapped_concepts() -> set[str]:
    out = set()
    for definition in _EXPLICIT_XBRL_ALIASES.values():
        for taxonomy, tag in definition.get("default_concepts", []):
            out.add(f"{taxonomy}:{tag}")
        for concepts in definition.get("industry_overrides", {}).values():
            for taxonomy, tag in concepts:
                out.add(f"{taxonomy}:{tag}")
    return out


def annual_facts(payload: dict, period_end: str) -> dict[str, float]:
    out = {}
    for taxonomy, concepts in payload.get("facts", {}).items():
        for tag, concept in concepts.items():
            for fact in concept.get("units", {}).get("USD", []):
                if fact.get("form") not in ANNUAL_FORMS:
                    continue
                if fact.get("end") != period_end:
                    continue
                start = fact.get("start")
                if not start:
                    continue
                try:
                    days = (date.fromisoformat(period_end) - date.fromisoformat(start)).days
                    value = float(fact["val"])
                except (TypeError, ValueError):
                    continue
                if not 330 <= days <= 370:
                    continue
                key = f"{taxonomy}:{tag}"
                prior = out.get(key)
                if prior is None or str(fact.get("filed", "")) > prior[1]:
                    out[key] = (value, str(fact.get("filed", "")))
    return {k: v[0] for k, v in out.items()}


def is_noise(concept: str) -> bool:
    text = concept.lower().replace("-", "").replace("_", "").split(":", 1)[-1]
    return any(term in text for term in EXCLUDE)


def main() -> None:
    if not SUMMARY.exists():
        raise SystemExit(f"Missing {SUMMARY}. Run validate_top_half_archetypes.py first.")

    with SUMMARY.open(newline="", encoding="utf-8") as handle:
        targets = [r for r in csv.DictReader(handle) if r["status"] == "MISMATCH"]

    if not targets:
        print("No MISMATCH rows.")
        return

    client = SECEdgarClient()
    already_mapped = mapped_concepts()
    rows = []
    concept_hits = Counter()

    for target in targets:
        ticker = target["ticker"]
        period = target["period_end"]

        try:
            residual = float(target["residual"])
            operating_income = float(target["operating_income"])
        except (TypeError, ValueError):
            continue

        try:
            cik = client.resolve_cik(ticker)
        except Exception:
            continue

        cache = RUNLOGS / f"{ticker}_{cik}.json"
        if not cache.exists():
            continue

        payload = json.loads(cache.read_text(encoding="utf-8"))
        facts = annual_facts(payload, period)

        tolerance = max(2_000_000.0, abs(operating_income) * 0.001)

        candidates = {
            concept: value
            for concept, value in facts.items()
            if concept not in already_mapped
            and not is_noise(concept)
            and abs(value) > 0
        }

        singles = sorted(
            (
                (abs(abs(value) - abs(residual)), concept, value)
                for concept, value in candidates.items()
                if abs(abs(value) - abs(residual)) <= tolerance
            )
        )

        pairs = []
        if not singles:
            sized = [
                (c, v) for c, v in candidates.items()
                if abs(v) <= abs(residual) * 1.05
            ]
            sized.sort(key=lambda item: -abs(item[1]))
            for (c1, v1), (c2, v2) in combinations(sized[:40], 2):
                for s1 in (1.0, -1.0):
                    for s2 in (1.0, -1.0):
                        total = s1 * v1 + s2 * v2
                        gap = abs(abs(total) - abs(residual))
                        if gap <= tolerance:
                            pairs.append((gap, c1, s1 * v1, c2, s2 * v2))
            pairs.sort()

        print(f"\n=== {ticker} {period}  residual={residual / 1e6:,.1f}M  "
              f"base={target['archetype']} ===")

        if singles:
            for gap, concept, value in singles[:4]:
                print(f"  SINGLE  {value / 1e6:>12,.1f}M  {concept}  (gap {gap / 1e6:,.2f}M)")
                concept_hits[concept] += 1
                rows.append({
                    "ticker": ticker, "period_end": period, "residual": residual,
                    "match_type": "single", "concept_1": concept, "value_1": value,
                    "concept_2": "", "value_2": "", "gap": gap,
                    "base_formula": target["archetype"],
                })
        elif pairs:
            for gap, c1, v1, c2, v2 in pairs[:4]:
                print(f"  PAIR    {v1 / 1e6:>12,.1f}M  {c1}")
                print(f"          {v2 / 1e6:>12,.1f}M  {c2}  (gap {gap / 1e6:,.2f}M)")
                concept_hits[c1] += 1
                concept_hits[c2] += 1
                rows.append({
                    "ticker": ticker, "period_end": period, "residual": residual,
                    "match_type": "pair", "concept_1": c1, "value_1": v1,
                    "concept_2": c2, "value_2": v2, "gap": gap,
                    "base_formula": target["archetype"],
                })
        else:
            print("  (no single or 2-concept match - likely wrong base formula "
                  "or company-extension concepts)")
            rows.append({
                "ticker": ticker, "period_end": period, "residual": residual,
                "match_type": "none", "concept_1": "", "value_1": "",
                "concept_2": "", "value_2": "", "gap": "",
                "base_formula": target["archetype"],
            })

    fields = ["ticker", "period_end", "residual", "match_type",
              "concept_1", "value_1", "concept_2", "value_2", "gap", "base_formula"]

    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print("\n" + "=" * 70)
    print("Concepts appearing across multiple companies (promotion candidates):")
    for concept, count in concept_hits.most_common(15):
        if count >= 2:
            print(f"  {count:>2}x  {concept}")

    resolved = sum(1 for r in rows if r["match_type"] != "none")
    unresolved = len({r["ticker"] for r in rows if r["match_type"] == "none"})
    print(f"\nCompanies with candidate matches: {len(targets) - unresolved}/{len(targets)}")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
