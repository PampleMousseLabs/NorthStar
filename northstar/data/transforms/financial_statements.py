# northstar/data/transforms/financial_statements.py

from northstar.data.models import FinancialObservation
from northstar.data.transforms.sa_key import SA_REVERSE
from northstar.data.transforms.sa_utils import to_float


def stockanalysis_to_observations(df, ticker: str, statement: str) -> list[FinancialObservation]:
    """
    Convert a raw StockAnalysisClient DataFrame into canonical FinancialObservations.

    Period columns are whatever the source produced (TTM, LFY, LFY-1, ...).
    Unmapped line items are skipped, not silently guessed at.
    """
    observations = []
    period_cols = [c for c in df.columns if c not in ("Line Item", "Ticker", "Key")]

    for _, row in df.iterrows():
        raw_label = str(row["Line Item"]).strip().lower()
        metric = SA_REVERSE.get(raw_label)
        if metric is None:
            continue  # unmapped — log later, don't guess

        for period in period_cols:
            value = to_float(row.get(period))
            if value is None:
                continue

            observations.append(FinancialObservation(
                ticker=ticker.lower(),
                metric=metric,
                period=period,
                period_type="TTM" if period == "TTM" else "FY",
                value=value,
                statement=statement,
                source="stockanalysis",
                raw_label=row["Line Item"],
            ))

    return observations