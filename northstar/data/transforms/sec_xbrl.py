"""
Transform SEC EDGAR companyfacts into NorthStar financial observations.

SEC networking belongs in northstar.data.sources.sec_edgar.
Metric-to-concept mappings belong in sec_xbrl_key.
This module selects and normalizes facts from an already-fetched payload.
"""

from datetime import date

from northstar.data.models import FinancialObservation
from northstar.data.transforms.sec_xbrl_key import (
    get_duration_bounds,
    get_xbrl_concepts,
    get_xbrl_forms,
    get_xbrl_units,
)


def _duration_days(start: str, end: str) -> int:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    return (end_date - start_date).days


def _candidate_facts(
    companyfacts: dict,
    metric: str,
    industry: str | None = None,
) -> list[dict]:
    """
    Collect valid annual facts from mapped XBRL concepts.

    Candidate concept order is retained as concept_priority so that
    preferred concepts beat fallback concepts later.
    """
    concepts = get_xbrl_concepts(metric, industry=industry)
    allowed_units = set(get_xbrl_units(metric))
    allowed_forms = set(get_xbrl_forms(metric))
    duration_bounds = get_duration_bounds(metric)

    candidates = []

    for priority, (taxonomy, tag) in enumerate(concepts):
        concept = (
            companyfacts
            .get("facts", {})
            .get(taxonomy, {})
            .get(tag)
        )

        if not concept:
            continue

        for unit, facts in concept.get("units", {}).items():
            if allowed_units and unit not in allowed_units:
                continue

            for fact in facts:
                if allowed_forms and fact.get("form") not in allowed_forms:
                    continue

                # Skip dimensional/segment facts. We want the consolidated fact.
                if fact.get("segment"):
                    continue

                start = fact.get("start")
                end = fact.get("end")

                if not start or not end:
                    continue

                if duration_bounds is not None:
                    days = _duration_days(start, end)
                    minimum, maximum = duration_bounds

                    if not minimum <= days <= maximum:
                        continue

                candidates.append({
                    "taxonomy": taxonomy,
                    "tag": tag,
                    "label": concept.get("label", ""),
                    "unit": unit,
                    "concept_priority": priority,
                    "value": fact.get("val"),
                    "start": start,
                    "end": end,
                    "filed": fact.get("filed"),
                    "form": fact.get("form"),
                    "fy": fact.get("fy"),
                    "fp": fact.get("fp"),
                    "accn": fact.get("accn"),
                })

    return candidates


def select_annual_facts(
    companyfacts: dict,
    metric: str,
    industry: str | None = None,
) -> list[dict]:
    """
    Select one annual fact per economic period.

    Rules:
    1. Use NorthStar's ordered concept candidates.
    2. Require appropriate unit/form/duration.
    3. Prefer the highest-priority mapped concept for each period.
    4. Within that concept, prefer the latest filing for the period.

    Latest-filed selection intentionally produces the latest restated /
    comparative representation. Point-in-time 'known and knowable'
    selection will be a separate future policy.
    """
    candidates = _candidate_facts(
        companyfacts,
        metric,
        industry=industry,
    )

    by_period = {}

    for fact in candidates:
        period_key = (fact["start"], fact["end"])
        current = by_period.get(period_key)

        if current is None:
            by_period[period_key] = fact
            continue

        new_rank = (
            -fact["concept_priority"],
            fact.get("filed") or "",
        )
        current_rank = (
            -current["concept_priority"],
            current.get("filed") or "",
        )

        if new_rank > current_rank:
            by_period[period_key] = fact

    return sorted(
        by_period.values(),
        key=lambda fact: fact["end"],
        reverse=True,
    )


def to_financial_observations(
    companyfacts: dict,
    ticker: str,
    metric: str,
    industry: str | None = None,
) -> list[FinancialObservation]:
    """
    Convert selected annual SEC facts into NorthStar observations.

    Relative LFY labels are assigned from the resulting annual-period order.
    """
    facts = select_annual_facts(
        companyfacts,
        metric,
        industry=industry,
    )

    observations = []

    for index, fact in enumerate(facts):
        period = "LFY" if index == 0 else f"LFY-{index}"

        observations.append(
            FinancialObservation(
                ticker=ticker.upper(),
                metric=metric,
                period=period,
                period_type="FY",
                value=float(fact["value"]),
                fiscal_year=date.fromisoformat(fact["end"]).year,
                currency="USD" if fact["unit"] == "USD" else fact["unit"],
                statement="IS",
                source="sec_edgar",
                raw_label=fact["label"],
            )
        )

    return observations