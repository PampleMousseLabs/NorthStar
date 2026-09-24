"""Canonical model for financial statement observations (CapIQ-style)."""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class FinancialObservation:
    ticker: str
    metric: str                     # Canonical internal key (e.g., 'revenue', 'ebit', 'capex')
    period: str                     # Standardized period label: '2024', '2023', 'TTM', 'NFY'
    period_type: str                # 'FY', 'Q', 'TTM', 'FORWARD'
    value: Optional[float]          # Parsed float in actual units (not scaled to millions)
    fiscal_year: Optional[int] = None
    fiscal_quarter: Optional[int] = None
    currency: str = "USD"
    statement: Optional[str] = None # 'IS', 'BS', 'CFS', 'Ratios'
    source: str = "unknown"         # 'stockanalysis', 'marketscreener', 'sec'
    raw_label: Optional[str] = None # Original label: 'Cost of Revenue', 'Net Sales'
    retrieved_at: datetime = datetime.utcnow()