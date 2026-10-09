"""
Explain exceptions from reconstructed_is_batch_summary.csv.

  FAIL            -> which subtotal failed and by how much
  PARTIAL         -> which subtotals were skipped and why
  NO_PRESENTATION -> harvest status, accession alignment, candidate IS roles

Reads local runlogs only. No network.
"""

import csv
import sys

csv.field_size_limit(sys.maxsize)
from collections import defaultdict
from pathlib import Path

RUNLOGS = Path("Dev_tools/xbrl/runlogs")
SUMMARY = RUNLOGS / "reconstructed_is_batch_summary.csv"

ROLE_KEEP = ("income", "operation", "earning")
ROLE_DROP = ("detail", "table", "polic", "parenthetical", "tax",
             "pershare", "comprehensive", "segment", "discontinued")


def read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as h:
        return list(csv.DictReader(h))


def latest(pattern: str) -> Path | None:
    files = sorted(RUNLOGS.glob(pattern))
    return files[-1] if files else None


def print_checks(ticker: str, wanted: str) -> None:
    path = latest(f"reconstructed_IS_{ticker}_*.csv")
    if path is None:
        print(f"  {ticker:<6} (no reconstructed CSV found)")
        return
    hits = [r for r in read(path) if r.get("check_status") == wanted]
    if not hits:
        print(f"  {ticker:<6} (no {wanted} rows in {path.name})")
    for r in hits:
        try:
            shown = f"{float(r['value']) / 1e6:,.1f}M"
        except (TypeError, ValueError):
            shown = "-"
        print(f"  {ticker:<6} {r['label'][:44]:<44} {shown:>12}  {r.get('check_detail', '')}")


def main() -> None:
    summary = read(SUMMARY)
    by_status = defaultdict(list)
    for r in summary:
        by_status[r["status"]].append(r["ticker"])

    print("=" * 110)
    print(f"FAIL ({len(by_status['FAIL'])}): failing subtotals")
    print("=" * 110)
    for t in by_status["FAIL"]:
        print_checks(t, "FAIL")

    print("\n" + "=" * 110)
    print(f"PARTIAL ({len(by_status['PARTIAL'])}): skipped subtotals")
    print("=" * 110)
    for t in by_status["PARTIAL"]:
        print_checks(t, "SKIP")

    print("\n" + "=" * 110)
    print(f"NO_PRESENTATION ({len(by_status['NO_PRESENTATION'])}): why no IS rows")
    print("=" * 110)

    harvest = {r["ticker"]: r for r in read(RUNLOGS / "presentation_harvest_status.csv")}
    wanted = set(by_status["NO_PRESENTATION"])
    roles = defaultdict(dict)
    for r in read(RUNLOGS / "presentation_rows.csv"):
        if r["ticker"] in wanted:
            roles[r["ticker"]][r["statement_role"]] = r["statement_category"]

    for t in by_status["NO_PRESENTATION"]:
        h = harvest.get(t, {})
        pres_acc = h.get("filing_accession", "").replace("-", "")
        facts = latest(f"filing_facts_{t}_*.csv")
        facts_acc = facts.stem.split("_")[-1] if facts else "NONE"
        aligned = "ALIGNED" if pres_acc and pres_acc == facts_acc else "MISMATCH"

        print(f"\n  {t:<6} harvest={h.get('status', 'NOT_IN_HARVEST'):<11} "
              f"pres_acc={pres_acc or '-':<20} facts_acc={facts_acc:<20} {aligned}")

        candidates = [
            (role, cat) for role, cat in roles[t].items()
            if any(k in role.rsplit("/", 1)[-1].lower() for k in ROLE_KEEP)
            and not any(k in role.rsplit("/", 1)[-1].lower() for k in ROLE_DROP)
        ]
        if not candidates:
            print("         (no candidate income-statement role found)")
        for role, cat in sorted(candidates)[:4]:
            print(f"         [{cat:<14}] {role}")


if __name__ == "__main__":
    main()
