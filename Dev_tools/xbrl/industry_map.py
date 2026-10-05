"""
Research-only ticker -> industry map for SEC XBRL key overrides.

Single source of truth for Dev_tools scripts. Industry strings must match
the industry_overrides keys in northstar/data/transforms/sec_xbrl_key.py.

This is a temporary hand list. A real classification (SIC code from SEC
submissions, or a platform company model) replaces it later.
"""

INDUSTRY_BY_TICKER = {
    **{t: "bank" for t in ("JPM", "BAC", "SCHW", "COF", "CBOE")},
    **{t: "reit" for t in ("ARE", "BXP", "CPT", "AMT", "PLD", "O", "CBRE")},
    **{t: "utility" for t in ("AWK", "AEE", "AEP", "LNT", "ATO", "CNP")},
}


def industry_for(ticker: str) -> str | None:
    return INDUSTRY_BY_TICKER.get(ticker.upper())
