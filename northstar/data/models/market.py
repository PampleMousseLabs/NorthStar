"""Canonical models for market marks and macroeconomic series."""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class MarketObservation:
    ticker: str
    price: Optional[float] = None
    market_cap: Optional[float] = None       # Base units (actual dollars)
    enterprise_value: Optional[float] = None # Base units
    shares_outstanding: Optional[float] = None
    beta: Optional[float] = None
    source: str = "yfinance"
    timestamp: datetime = datetime.utcnow()


@dataclass
class MacroObservation:
    series_id: str                          # e.g., 'DGS10', 'FEDFUNDS'
    date: str                               # 'YYYY-MM-DD'
    value: Optional[float] = None
    series_name: Optional[str] = None
    source: str = "fred"
    retrieved_at: datetime = datetime.utcnow()