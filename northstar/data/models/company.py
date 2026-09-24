"""Company and Security canonical data models."""
from dataclasses import dataclass, field
from typing import Optional, Dict


@dataclass
class Company:
    internal_id: str
    legal_name: str
    common_name: Optional[str] = None
    country: Optional[str] = "US"
    industry: Optional[str] = None
    sector: Optional[str] = None
    identifiers: Dict[str, str] = field(default_factory=dict)  # {"cik": "...", "figi": "..."}


@dataclass
class Security:
    ticker: str
    company_id: Optional[str] = None
    exchange: Optional[str] = None
    currency: str = "USD"
    isin: Optional[str] = None
    provider_ids: Dict[str, str] = field(default_factory=dict)  # {"marketscreener_slug": "..."}