"""
NorthStar canonical data models smoke test.
Verifies instantiation, defaults, and field structures.
"""
from datetime import datetime
from northstar.data.models import (
    Company,
    Security,
    FinancialObservation,
    MarketObservation,
    MacroObservation,
)


def test_models():
    # 1. Company & Security
    c = Company(internal_id="aapl_us", legal_name="Apple Inc.", industry="Consumer Electronics")
    s = Security(ticker="AAPL", company_id=c.internal_id)
    assert s.ticker == "AAPL"
    assert s.currency == "USD"

    # 2. FinancialObservation (CapIQ-style observation)
    obs = FinancialObservation(
        ticker="AAPL",
        metric="revenue",
        period="2024",
        period_type="FY",
        fiscal_year=2024,
        value=391035000000.0,
        source="stockanalysis",
        raw_label="Revenue",
    )
    assert obs.metric == "revenue"
    assert obs.fiscal_year == 2024
    assert obs.value == 391035000000.0
    assert isinstance(obs.retrieved_at, datetime)

    # 3. MarketObservation
    mkt = MarketObservation(ticker="AAPL", price=224.50, market_cap=3400000000000.0)
    assert mkt.price == 224.50

    # 4. MacroObservation
    macro = MacroObservation(series_id="DGS10", date="2026-09-23", value=4.15)
    assert macro.value == 4.15


if __name__ == "__main__":
    test_models()
    print("NorthStar canonical model tests: PASS")