"""
Research-only comparison of reported annual revenue across:

    1. SEC CompanyFacts, using NorthStar's current SEC concept selector
    2. StockAnalysis, using NorthStar's existing source client and SA key
    3. Yahoo Finance, using the installed yfinance package

Outputs, all under the gitignored Dev_tools/xbrl/runlogs/ directory:

    revenue_source_comparison.csv
        One row per ticker and SEC annual period, with raw values and
        comparison diagnostics.

    revenue_source_summary.csv
        One compact row per ticker, showing each source's latest observation.

Important:
    - This does not establish that any mapping is correct.
    - StockAnalysis period labels are relative (LFY, LFY-1, etc.); the
      current client does not preserve the fiscal-year end date.
    - The script does not silently scale StockAnalysis values.
    - Yahoo Finance is an independent comparison source, not ground truth.
"""

from __future__ import annotations

import csv
import json
import math
import re
import time
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

from northstar.data.sources.sec_edgar import SECEdgarClient
from northstar.data.sources.stockanalysis import StockAnalysisClient
from northstar.data.transforms.sa_key import get_sa_labels
from northstar.data.transforms.sa_utils import to_float
from northstar.data.transforms.sec_xbrl import select_annual_facts


RUNLOGS = Path("Dev_tools/xbrl/runlogs")
TICKERS_FILE = Path("Dev_tools/xbrl/tickers_sample.txt")
MAX_PERIODS = 5


def normalize_label(value: object) -> str:
    """Normalize a label for exact, punctuation-insensitive comparison."""
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def safe_float(value: object) -> float | None:
    """Parse a finite numeric value using NorthStar's existing SA parser."""
    parsed = to_float(value)
    if parsed is not None:
        return parsed

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None

    return parsed if math.isfinite(parsed) else None


def relative_period(rank: int) -> str:
    return "LFY" if rank == 0 else f"LFY-{rank}"


def filing_url(cik: str, accession: str | None) -> str:
    if not accession:
        return ""

    try:
        cik_without_padding = str(int(cik))
    except (TypeError, ValueError):
        cik_without_padding = str(cik)

    accession_path = accession.replace("-", "")
    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{cik_without_padding}/{accession_path}/{accession}-index.htm"
    )


def load_tickers() -> list[str]:
    return [
        line.strip().upper()
        for line in TICKERS_FILE.read_text().splitlines()
        if line.strip()
    ]


def load_companyfacts(client: SECEdgarClient, ticker: str) -> tuple[str, dict]:
    """
    Reuse the cached CompanyFacts JSON from the earlier research harvest.
    Fetch and cache only when this ticker has no local payload yet.
    """
    cik = client.resolve_cik(ticker)
    cache_path = RUNLOGS / f"{ticker}_{cik}.json"

    if cache_path.exists():
        return cik, json.loads(cache_path.read_text(encoding="utf-8"))

    payload = client.fetch_companyfacts(ticker)
    RUNLOGS.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload), encoding="utf-8")
    time.sleep(0.25)
    return cik, payload


def get_sec_revenue(
    client: SECEdgarClient,
    ticker: str,
) -> tuple[str, list[dict], str]:
    """Return the newest SEC annual revenue observations and a status."""
    try:
        cik, payload = load_companyfacts(client, ticker)
        facts = select_annual_facts(payload, "revenue")

        records = []
        for rank, fact in enumerate(facts[:MAX_PERIODS]):
            end = str(fact.get("end") or "")
            accession = fact.get("accn")

            records.append({
                "period": relative_period(rank),
                "fiscal_year": fact.get("fy") or (end[:4] if end else ""),
                "period_start": fact.get("start") or "",
                "period_end": end,
                "value": safe_float(fact.get("value")),
                "taxonomy": fact.get("taxonomy") or "",
                "tag": fact.get("tag") or "",
                "label": fact.get("label") or "",
                "form": fact.get("form") or "",
                "filed": fact.get("filed") or "",
                "accession": accession or "",
                "filing_url": filing_url(cik, accession),
            })

        if records:
            return "OK", records, ""

        return "NO_MATCH", [], "SEC selector returned no annual revenue facts"

    except Exception as error:
        return "ERROR", [], str(error)


def stockanalysis_period_rank(header: object) -> int | None:
    """
    Return the LFY-relative rank for an annual StockAnalysis column.

    Supports already-mapped labels such as LFY-2 and raw headers such as
    FY 2024. TTM is intentionally excluded from this annual comparison.
    """
    label = str(header).strip().upper()

    match = re.fullmatch(r"LFY(?:-(\d+))?", label)
    if match:
        return int(match.group(1) or 0)

    match = re.fullmatch(r"FY\s*(\d{4})", label)
    if match:
        # Absolute FY columns are ranked separately in get_stockanalysis_revenue.
        return None

    return None


def get_stockanalysis_revenue(
    client: StockAnalysisClient,
    ticker: str,
) -> tuple[str, list[dict], str]:
    """Fetch the StockAnalysis income statement and extract its revenue row."""
    try:
        frame = client.fetch_statement(ticker, "IS")

        if frame is None or frame.empty:
            return "NO_DATA", [], "StockAnalysis returned no income-statement rows"

        line_item_column = next(
            (
                column for column in frame.columns
                if normalize_label(column) == "lineitem"
            ),
            None,
        )
        if line_item_column is None:
            return "ERROR", [], "No 'Line Item' column in StockAnalysis result"

        aliases = {
            normalize_label(label)
            for label in get_sa_labels("revenue")
        }

        matching_rows = []
        for _, row in frame.iterrows():
            raw_label = row.get(line_item_column)
            if normalize_label(raw_label) in aliases:
                matching_rows.append((str(raw_label), row))

        if not matching_rows:
            available = [
                str(value)
                for value in frame[line_item_column].dropna().tolist()
            ]
            return (
                "NO_REVENUE_ROW",
                [],
                "Mapped SA revenue label not found; available labels: "
                + " | ".join(available[:20]),
            )

        raw_label, row = matching_rows[0]
        metadata_columns = {"lineitem", "ticker", "key"}

        relative_columns: list[tuple[int, object]] = []
        absolute_year_columns: list[tuple[int, object]] = []

        for column in frame.columns:
            normalized_column = normalize_label(column)
            if normalized_column in metadata_columns:
                continue

            rank = stockanalysis_period_rank(column)
            if rank is not None:
                relative_columns.append((rank, column))
                continue

            match = re.fullmatch(r"FY\s*(\d{4})", str(column).strip(), re.IGNORECASE)
            if match:
                absolute_year_columns.append((int(match.group(1)), column))

        # If the source returned absolute FY columns, convert their order to
        # relative labels for comparison, while retaining the year in the note.
        if absolute_year_columns and not relative_columns:
            for rank, (year, column) in enumerate(
                sorted(absolute_year_columns, reverse=True)
            ):
                relative_columns.append((rank, column))

        records_by_rank: dict[int, dict] = {}

        for rank, column in sorted(relative_columns, key=lambda item: item[0]):
            raw_value = row.get(column)
            records_by_rank.setdefault(rank, {
                "period": relative_period(rank),
                "source_period_header": str(column),
                "fiscal_year": "",
                "period_end": "",
                "value": safe_float(raw_value),
                "raw_value": "" if raw_value is None else str(raw_value),
                "label": raw_label,
            })

        records = [
            records_by_rank[rank]
            for rank in sorted(records_by_rank)
            if rank < MAX_PERIODS
        ]

        if records:
            return "OK", records, ""

        return (
            "NO_ANNUAL_COLUMNS",
            [],
            "Revenue row found, but no LFY/FY annual columns were recognized",
        )

    except Exception as error:
        return "ERROR", [], str(error)


def get_yfinance_revenue(ticker: str) -> tuple[str, list[dict], str]:
    """Fetch Yahoo Finance annual income statement revenue through yfinance."""
    try:
        yf_ticker = yf.Ticker(ticker)

        try:
            frame = yf_ticker.income_stmt
        except Exception:
            frame = yf_ticker.get_income_stmt(freq="yearly", pretty=False)

        if frame is None or frame.empty:
            return "NO_DATA", [], "yfinance returned an empty annual income statement"

        preferred_rows = (
            "totalrevenue",
            "revenue",
            "revenues",
            "operatingrevenue",
        )

        normalized_index = {
            normalize_label(index): index
            for index in frame.index
        }

        selected_index = next(
            (
                normalized_index[name]
                for name in preferred_rows
                if name in normalized_index
            ),
            None,
        )

        if selected_index is None:
            available = [str(index) for index in frame.index]
            return (
                "NO_REVENUE_ROW",
                [],
                "No recognized yfinance revenue row; available rows: "
                + " | ".join(available[:25]),
            )

        raw_label = str(selected_index)
        records = []

        for column in frame.columns:
            timestamp = pd.to_datetime(column, errors="coerce")
            if pd.isna(timestamp):
                continue

            raw_value = frame.loc[selected_index, column]
            if isinstance(raw_value, pd.Series):
                raw_value = raw_value.iloc[0]

            records.append({
                "period_end": timestamp.date().isoformat(),
                "value": safe_float(raw_value),
                "raw_value": "" if raw_value is None else str(raw_value),
                "label": raw_label,
            })

        records.sort(key=lambda record: record["period_end"], reverse=True)

        for rank, record in enumerate(records):
            record["period"] = relative_period(rank)

        return "OK", records[:MAX_PERIODS], ""

    except Exception as error:
        return "ERROR", [], str(error)


def compare_values(
    sec_value: float | None,
    source_value: float | None,
) -> tuple[str, float | None, float | None]:
    """
    Compare unscaled raw values.

    Returns:
        assessment, SEC/source multiple, source-vs-SEC percentage difference
    """
    if sec_value is None or source_value is None:
        return "NO_COMPARABLE_VALUE", None, None

    if sec_value == 0:
        return "SEC_VALUE_ZERO", None, None

    multiple = sec_value / source_value if source_value != 0 else None
    pct_difference = ((source_value / sec_value) - 1.0) * 100.0

    if math.isclose(sec_value, source_value, rel_tol=0.02, abs_tol=1.0):
        return "CLOSE_RAW_VALUES_NOT_VERIFIED", multiple, pct_difference

    if multiple is not None:
        for factor, unit_name in (
            (1_000.0, "THOUSANDS"),
            (1_000_000.0, "MILLIONS"),
            (1_000_000_000.0, "BILLIONS"),
            (1_000_000_000_000.0, "TRILLIONS"),
        ):
            if math.isclose(multiple, factor, rel_tol=0.03):
                return f"LIKELY_SOURCE_IN_{unit_name}", multiple, pct_difference

    return "MATERIAL_DIFFERENCE_REVIEW", multiple, pct_difference


def compare_yfinance_period(
    sec_record: dict,
    yf_record: dict | None,
) -> tuple[str, float | None, float | None, int | None]:
    if yf_record is None:
        return "NO_MATCHING_RELATIVE_PERIOD", None, None, None

    try:
        sec_end = date.fromisoformat(sec_record["period_end"])
        yf_end = date.fromisoformat(yf_record["period_end"])
        gap_days = abs((sec_end - yf_end).days)
    except (TypeError, ValueError):
        gap_days = None

    assessment, multiple, pct_difference = compare_values(
        sec_record.get("value"),
        yf_record.get("value"),
    )

    if gap_days is not None and gap_days > 45:
        return "PERIOD_MISMATCH_REVIEW", multiple, pct_difference, gap_days

    return assessment, multiple, pct_difference, gap_days


def build_comparison_rows(
    ticker: str,
    sec_records: list[dict],
    sa_records: list[dict],
    yf_records: list[dict],
) -> list[dict]:
    sa_by_period = {record["period"]: record for record in sa_records}
    yf_by_period = {record["period"]: record for record in yf_records}

    if not sec_records:
        return [{
            "ticker": ticker,
            "relative_period": "",
            "sec_period_end": "",
            "sec_fiscal_year": "",
            "sec_value_usd": "",
            "sec_taxonomy": "",
            "sec_tag": "",
            "sec_label": "",
            "sec_filing_date": "",
            "sec_accession": "",
            "sec_filing_url": "",
            "stockanalysis_period": "",
            "stockanalysis_label": "",
            "stockanalysis_raw_value": "",
            "stockanalysis_value": "",
            "sec_to_stockanalysis_multiple": "",
            "stockanalysis_difference_pct": "",
            "stockanalysis_assessment": "NO_SEC_FACT",
            "yfinance_period_end": "",
            "yfinance_label": "",
            "yfinance_value": "",
            "sec_to_yfinance_multiple": "",
            "yfinance_difference_pct": "",
            "yfinance_period_gap_days": "",
            "yfinance_assessment": "NO_SEC_FACT",
        }]

    rows = []

    for sec_record in sec_records:
        period = sec_record["period"]
        sa_record = sa_by_period.get(period)
        yf_record = yf_by_period.get(period)

        sa_assessment, sa_multiple, sa_pct = compare_values(
            sec_record.get("value"),
            sa_record.get("value") if sa_record else None,
        )

        if sa_record is not None and sa_record.get("value") is not None:
            sa_assessment += "_RELATIVE_PERIOD_ONLY"

        yf_assessment, yf_multiple, yf_pct, yf_gap = compare_yfinance_period(
            sec_record,
            yf_record,
        )

        rows.append({
            "ticker": ticker,
            "relative_period": period,
            "sec_period_end": sec_record.get("period_end", ""),
            "sec_fiscal_year": sec_record.get("fiscal_year", ""),
            "sec_value_usd": sec_record.get("value", ""),
            "sec_taxonomy": sec_record.get("taxonomy", ""),
            "sec_tag": sec_record.get("tag", ""),
            "sec_label": sec_record.get("label", ""),
            "sec_filing_date": sec_record.get("filed", ""),
            "sec_accession": sec_record.get("accession", ""),
            "sec_filing_url": sec_record.get("filing_url", ""),
            "stockanalysis_period": (
                sa_record.get("source_period_header", "") if sa_record else ""
            ),
            "stockanalysis_label": sa_record.get("label", "") if sa_record else "",
            "stockanalysis_raw_value": (
                sa_record.get("raw_value", "") if sa_record else ""
            ),
            "stockanalysis_value": (
                sa_record.get("value", "") if sa_record else ""
            ),
            "sec_to_stockanalysis_multiple": (
                sa_multiple if sa_multiple is not None else ""
            ),
            "stockanalysis_difference_pct": (
                sa_pct if sa_pct is not None else ""
            ),
            "stockanalysis_assessment": sa_assessment,
            "yfinance_period_end": (
                yf_record.get("period_end", "") if yf_record else ""
            ),
            "yfinance_label": yf_record.get("label", "") if yf_record else "",
            "yfinance_value": (
                yf_record.get("value", "") if yf_record else ""
            ),
            "sec_to_yfinance_multiple": (
                yf_multiple if yf_multiple is not None else ""
            ),
            "yfinance_difference_pct": (
                yf_pct if yf_pct is not None else ""
            ),
            "yfinance_period_gap_days": (
                yf_gap if yf_gap is not None else ""
            ),
            "yfinance_assessment": yf_assessment,
        })

    return rows


def latest_value(records: list[dict], key: str) -> object:
    if not records:
        return ""
    return records[0].get(key, "")


def main() -> None:
    RUNLOGS.mkdir(parents=True, exist_ok=True)

    sec_client = SECEdgarClient()
    sa_client = StockAnalysisClient()

    comparison_rows = []
    summary_rows = []

    tickers = load_tickers()

    for index, ticker in enumerate(tickers, start=1):
        print(f"[{index}/{len(tickers)}] {ticker}")

        sec_status, sec_records, sec_note = get_sec_revenue(sec_client, ticker)
        sa_status, sa_records, sa_note = get_stockanalysis_revenue(sa_client, ticker)
        yf_status, yf_records, yf_note = get_yfinance_revenue(ticker)

        comparison_rows.extend(
            build_comparison_rows(
                ticker,
                sec_records,
                sa_records,
                yf_records,
            )
        )

        sec_latest = sec_records[0] if sec_records else {}
        sa_latest = sa_records[0] if sa_records else {}
        yf_latest = yf_records[0] if yf_records else {}

        latest_sa_assessment, _, _ = compare_values(
            sec_latest.get("value"),
            sa_latest.get("value"),
        )
        if sa_latest.get("value") is not None:
            latest_sa_assessment += "_RELATIVE_PERIOD_ONLY"

        latest_yf_assessment, _, _, latest_yf_gap = (
            compare_yfinance_period(sec_latest, yf_latest)
            if sec_latest and yf_latest
            else ("NO_MATCHING_RELATIVE_PERIOD", None, None, None)
        )

        summary_rows.append({
            "ticker": ticker,
            "sec_status": sec_status,
            "sec_note": sec_note,
            "sec_latest_period_end": sec_latest.get("period_end", ""),
            "sec_latest_tag": sec_latest.get("tag", ""),
            "sec_latest_value_usd": sec_latest.get("value", ""),
            "sec_accession": sec_latest.get("accession", ""),
            "sec_filing_url": sec_latest.get("filing_url", ""),
            "stockanalysis_status": sa_status,
            "stockanalysis_note": sa_note,
            "stockanalysis_latest_period": sa_latest.get("source_period_header", ""),
            "stockanalysis_latest_label": sa_latest.get("label", ""),
            "stockanalysis_latest_raw_value": sa_latest.get("raw_value", ""),
            "stockanalysis_latest_value": sa_latest.get("value", ""),
            "latest_sa_assessment": latest_sa_assessment,
            "yfinance_status": yf_status,
            "yfinance_note": yf_note,
            "yfinance_latest_period_end": yf_latest.get("period_end", ""),
            "yfinance_latest_label": yf_latest.get("label", ""),
            "yfinance_latest_value": yf_latest.get("value", ""),
            "latest_yfinance_assessment": latest_yf_assessment,
            "latest_yfinance_period_gap_days": (
                latest_yf_gap if latest_yf_gap is not None else ""
            ),
        })

        sec_value = sec_latest.get("value")
        sa_value = sa_latest.get("value")
        yf_value = yf_latest.get("value")

        print(
            f"  SEC={sec_status} ({sec_latest.get('tag', 'no fact')})"
            f" | StockAnalysis={sa_status}"
            f" ({sa_latest.get('label', sa_note or 'no row')})"
            f" | yfinance={yf_status}"
            f" ({yf_latest.get('label', yf_note or 'no row')})"
        )

        if sec_value is not None:
            print(
                f"  Latest raw values: SEC={sec_value:,.0f}"
                f" | SA={sa_value if sa_value is not None else 'n/a'}"
                f" | yfinance={yf_value if yf_value is not None else 'n/a'}"
            )

        time.sleep(0.4)

    comparison_path = RUNLOGS / "revenue_source_comparison.csv"
    summary_path = RUNLOGS / "revenue_source_summary.csv"

    comparison_fields = [
        "ticker",
        "relative_period",
        "sec_period_end",
        "sec_fiscal_year",
        "sec_value_usd",
        "sec_taxonomy",
        "sec_tag",
        "sec_label",
        "sec_filing_date",
        "sec_accession",
        "sec_filing_url",
        "stockanalysis_period",
        "stockanalysis_label",
        "stockanalysis_raw_value",
        "stockanalysis_value",
        "sec_to_stockanalysis_multiple",
        "stockanalysis_difference_pct",
        "stockanalysis_assessment",
        "yfinance_period_end",
        "yfinance_label",
        "yfinance_value",
        "sec_to_yfinance_multiple",
        "yfinance_difference_pct",
        "yfinance_period_gap_days",
        "yfinance_assessment",
    ]

    summary_fields = [
        "ticker",
        "sec_status",
        "sec_note",
        "sec_latest_period_end",
        "sec_latest_tag",
        "sec_latest_value_usd",
        "sec_accession",
        "sec_filing_url",
        "stockanalysis_status",
        "stockanalysis_note",
        "stockanalysis_latest_period",
        "stockanalysis_latest_label",
        "stockanalysis_latest_raw_value",
        "stockanalysis_latest_value",
        "latest_sa_assessment",
        "yfinance_status",
        "yfinance_note",
        "yfinance_latest_period_end",
        "yfinance_latest_label",
        "yfinance_latest_value",
        "latest_yfinance_assessment",
        "latest_yfinance_period_gap_days",
    ]

    with comparison_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=comparison_fields)
        writer.writeheader()
        writer.writerows(comparison_rows)

    with summary_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"\nWrote {comparison_path}")
    print(f"Wrote {summary_path}")
    print("These comparisons are research evidence, not mapping approval.")


if __name__ == "__main__":
    main()
