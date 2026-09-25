"""
SEC EDGAR XBRL source adapter.

Responsible only for communication with SEC EDGAR:
- ticker -> CIK resolution
- companyfacts retrieval

Interpretation of XBRL facts belongs in transforms, not here.
"""

import os
from typing import Any

import requests


TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


class SECEdgarClient:
    def __init__(self, user_agent: str | None = None):
        self.user_agent = user_agent or os.getenv("SEC_USER_AGENT")

        if not self.user_agent:
            raise RuntimeError(
                "SEC_USER_AGENT is required. Set it in the terminal before "
                "using the SEC EDGAR source."
            )

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
        })

        self._ticker_map = None

    def _get_json(self, url: str) -> dict[str, Any]:
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return response.json()

    def _load_ticker_map(self) -> dict:
        if self._ticker_map is None:
            self._ticker_map = self._get_json(TICKER_URL)
        return self._ticker_map

    def resolve_cik(self, ticker: str) -> str:
        ticker_upper = ticker.strip().upper()

        for company in self._load_ticker_map().values():
            if str(company.get("ticker", "")).upper() == ticker_upper:
                return f"{int(company['cik_str']):010d}"

        raise LookupError(f"SEC CIK not found for ticker: {ticker}")

    def fetch_companyfacts(self, ticker: str) -> dict[str, Any]:
        cik = self.resolve_cik(ticker)
        url = COMPANYFACTS_URL.format(cik=cik)
        return self._get_json(url)