"""
NorthStar source-layer smoke test.

Purpose:
    Verify that the source clients extracted from Canneberge
    can be imported independently by NorthStar.

This test intentionally does NOT make network calls.
"""

from northstar.data.sources.yfinance_live import YFinanceLiveClient
from northstar.data.sources.stockanalysis import StockAnalysisClient
from northstar.data.sources.marketscreener import MarketScreenerClient
from northstar.data.sources.fred import FREDClient
from northstar.data.sources.beta_vol import BetaVolClient


def test_source_imports():
    """Verify all extracted source modules import successfully."""
    assert YFinanceLiveClient is not None
    assert StockAnalysisClient is not None
    assert MarketScreenerClient is not None
    assert FREDClient is not None
    assert BetaVolClient is not None


if __name__ == "__main__":
    test_source_imports()
    print("NorthStar source-layer imports: PASS")