"""Conservative reconstruction of missing XBRL components from dimensional facts."""

import csv
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

LINK_NS = "http://www.xbrl.org/2003/linkbase"
XLINK_NS = "http://www.w3.org/1999/xlink"

def _concept_from_href(href):
    fragment = (href or "").rsplit("#", 1)[-1]
    if "_" not in fragment:
        return fragment
    namespace, concept = fragment.split("_", 1)
    namespace = namespace.replace("us-gaap-", "us-gaap").replace(
        "ifrs-full-", "ifrs-full"
    )
    return f"{namespace}:{concept}"

def _precision(row):
    decimals = str(row.get("decimals", "")).strip().upper()
    if decimals == "INF":
        return (2, 0)
    try:
        return (1, int(decimals))
    except (TypeError, ValueError):
        return (0, 0)

def _definition_xml(session, ticker, cik, accession, fact_rows, cache_dir):
    inline_url = next(
        (r.get("inline_xml_url", "") for r in fact_rows
         if r.get("inline_xml_url", "").endswith("_htm.xml")),
        "",
    )
    if not inline_url:
        return None

    def_name = Path(urlparse(inline_url).path).name.replace(
        "_htm.xml", "_def.xml"
    )
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / (
        f"{ticker}_{accession.replace('-', '')}_{def_name}"
    )

    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    if session is None:
        return None

    url = urljoin(
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{int(cik)}/{accession.replace('-', '')}/",
        def_name,
    )
    response = session.get(url, timeout=60)
    response.raise_for_status()
    cache_path.write_text(response.text, encoding="utf-8")
    return response.text

def _member_parents(xml_text):
    """Return parent -> direct children for each definition-link role."""
    root = ET.fromstring(xml_text)
    networks = []

    for link in root.iter(f"{{{LINK_NS}}}definitionLink"):
        locators = {}
        for loc in link.iter(f"{{{LINK_NS}}}loc"):
            label = loc.get(f"{{{XLINK_NS}}}label") or ""
            href = loc.get(f"{{{XLINK_NS}}}href") or ""
            if label and href:
                locators[label] = _concept_from_href(href)

        parents = {}
        for arc in link.iter(f"{{{LINK_NS}}}definitionArc"):
            arcrole = arc.get(f"{{{XLINK_NS}}}arcrole") or ""
            if not arcrole.endswith("domain-member"):
                continue
            parent = locators.get(arc.get(f"{{{XLINK_NS}}}from") or "")
            child = locators.get(arc.get(f"{{{XLINK_NS}}}to") or "")
            if parent and child:
                parents.setdefault(parent, set()).add(child)

        if parents:
            networks.append(parents)

    return networks

def resolve_dimensional_component(
    session,
    ticker,
    cik,
    accession,
    fact_rows,
    period_end,
    parent_concept,
    reported_parent_value,
    missing_concept,
    expected_value,
    tolerance,
    cache_dir,
):
    """
    Find a dimensional sibling rollup for one missing calculation component.

    A result is accepted only when:
      - facts are annual USD facts for the reported parent's period start;
      - each fact has exactly one dimension;
      - members are direct siblings in a definition-linkbase network;
      - at least two sibling facts are present; and
      - exactly one distinct sibling set reconciles to expected_value.
    """
    parent_rows = []
    for row in fact_rows:
        if (
            row.get("concept") == parent_concept
            and row.get("unit") == "USD"
            and row.get("period_end") == period_end
            and row.get("dimension_count") == "0"
            and row.get("period_start")
        ):
            try:
                value = float(row["value"])
            except (TypeError, ValueError):
                continue
            if value == reported_parent_value:
                parent_rows.append((_precision(row), row["period_start"]))

    if not parent_rows:
        return None

    best_precision = max(p for p, _ in parent_rows)
    period_starts = sorted({
        start for precision, start in parent_rows
        if precision == best_precision
    })
    if not period_starts:
        return None
    period_start = period_starts[0]

    # axis -> member -> candidate facts
    facts_by_axis = {}
    for row in fact_rows:
        if (
            row.get("concept") != missing_concept
            or row.get("unit") != "USD"
            or row.get("period_start") != period_start
            or row.get("period_end") != period_end
            or row.get("dimension_count") != "1"
        ):
            continue

        dimensions = (row.get("dimensions") or "").strip()
        if "=" not in dimensions or "|" in dimensions:
            continue
        axis, member = (part.strip() for part in dimensions.split("=", 1))
        if not axis or not member:
            continue

        try:
            value = float(row["value"])
        except (TypeError, ValueError):
            continue

        facts_by_axis.setdefault(axis, {}).setdefault(member, []).append(
            (_precision(row), value)
        )

    if not facts_by_axis:
        return None

    # Resolve each member only if its best-precision facts agree.
    values_by_axis = {}
    for axis, members in facts_by_axis.items():
        resolved = {}
        for member, candidates in members.items():
            best = max(p for p, _ in candidates)
            best_values = {
                value for precision, value in candidates if precision == best
            }
            if len(best_values) == 1:
                resolved[member] = best_values.pop()
        if resolved:
            values_by_axis[axis] = resolved

    # Accept one unique aggregate dimensional fact when it independently
    # reconciles to the missing calculation component.
    candidate_members = [
        (axis, member)
        for axis, members in facts_by_axis.items()
        for member in members
    ]
    if len(candidate_members) == 1:
        axis, member = candidate_members[0]
        value = values_by_axis.get(axis, {}).get(member)
        if value is not None and abs(value - expected_value) <= tolerance:
            return value, (
                f"single aggregate dimensional fact "
                f"({axis}={member}; reconciles to "
                f"{value / 1e6:,.1f}M)"
            )

    try:
        xml_text = _definition_xml(
            session, ticker, cik, accession, fact_rows, cache_dir
        )
        if not xml_text:
            return None
        networks = _member_parents(xml_text)
    except Exception:
        return None

    matches = {}
    for parents in networks:
        for axis, member_values in values_by_axis.items():
            for parent, children in parents.items():
                available = children.intersection(member_values)
                if len(available) < 2:
                    continue

                member_set = tuple(sorted(available))
                total = sum(member_values[m] for m in member_set)
                if abs(total - expected_value) <= tolerance:
                    matches[member_set] = total

    if not matches:
        return None

    distinct_totals = []
    for total in matches.values():
        if not any(abs(total - existing) <= tolerance for existing in distinct_totals):
            distinct_totals.append(total)

    if len(distinct_totals) != 1:
        return None

    total = distinct_totals[0]
    detail = (
        f"dimensional rollup ({len(matches)} matching sibling sets; "
        f"all reconcile to {total / 1e6:,.1f}M)"
    )
    return total, detail


def resolve_dimensional_components(
    ticker,
    fact_rows,
    period_end,
    parent_concept,
    reported_parent_value,
    missing_items,
    known_total,
    tolerance,
):
    """
    Resolve multiple missing components only when each has one unique
    one-dimensional USD fact for the parent's exact annual period.

    The combined weighted components must reconcile to the reported parent.
    No residual is allocated among missing components.
    """
    parent_rows = []
    for row in fact_rows:
        if (
            row.get("concept") == parent_concept
            and row.get("unit") == "USD"
            and row.get("period_end") == period_end
            and row.get("dimension_count") == "0"
            and row.get("period_start")
        ):
            try:
                value = float(row["value"])
            except (TypeError, ValueError):
                continue
            if value == reported_parent_value:
                parent_rows.append((_precision(row), row["period_start"]))

    if not parent_rows:
        return None

    best_precision = max(p for p, _ in parent_rows)
    period_starts = sorted({
        start for precision, start in parent_rows
        if precision == best_precision
    })
    if len(period_starts) != 1:
        return None
    period_start = period_starts[0]

    resolved = {}
    details = []

    for concept, weight in missing_items:
        if weight == 0:
            return None

        candidates = {}
        for row in fact_rows:
            if (
                row.get("concept") != concept
                or row.get("unit") != "USD"
                or row.get("period_start") != period_start
                or row.get("period_end") != period_end
                or row.get("dimension_count") != "1"
            ):
                continue

            dimensions = (row.get("dimensions") or "").strip()
            if "=" not in dimensions or "|" in dimensions:
                continue

            axis, member = (
                part.strip() for part in dimensions.split("=", 1)
            )
            if not axis or not member:
                continue

            try:
                value = float(row["value"])
            except (TypeError, ValueError):
                continue

            candidates.setdefault((axis, member), []).append(
                (_precision(row), value)
            )

        # Multiple members are ambiguous here. The single-component
        # resolver remains responsible for sibling rollups.
        if len(candidates) != 1:
            return None

        (axis, member), rows = next(iter(candidates.items()))
        best = max(precision for precision, _ in rows)
        best_values = {
            value for precision, value in rows if precision == best
        }
        if len(best_values) != 1:
            return None

        value = best_values.pop()
        resolved[concept] = value
        details.append(
            f"{concept}={value / 1e6:,.1f}M "
            f"({axis}={member})"
        )

    computed = known_total + sum(
        weight * resolved[concept] for concept, weight in missing_items
    )
    delta = computed - reported_parent_value
    if abs(delta) > tolerance:
        return None

    return resolved, (
        f"unique dimensional facts; combined weighted check reconciles "
        f"(delta {delta / 1e6:+,.3f}M): " + "; ".join(details)
    )
