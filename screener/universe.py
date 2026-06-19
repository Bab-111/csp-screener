"""
universe.py — Ticker universe for the CSP screener.

Organised into tiers so you can run a quick scan (TIER_1 only)
or a full scan (all tiers).  Biotech, Chinese ADRs, leveraged ETFs
and sub-$20 names are pre-excluded at the list level.
"""

# ── Tier 1: Highest-liquidity large-caps & ETFs ───────────────────────────────
# Best option chains, tightest spreads, most reliable data from yfinance
TIER_1 = [
    # Mega-cap tech
    "AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA", "TSLA",
    # Semiconductors
    "AMD", "INTC", "AVGO", "QCOM", "MU",
    # Financials
    "JPM", "BAC", "GS", "MS", "V", "MA",
    # Energy
    "XOM", "CVX", "COP",
    # Healthcare
    "UNH", "JNJ", "LLY", "ABBV",
    # Consumer
    "WMT", "COST", "HD", "MCD", "NKE",
    # Liquid ETFs (non-leveraged)
    "SPY", "QQQ", "IWM", "GLD", "TLT", "XLF", "XLE", "XLK",
]

# ── Tier 2: Active mid/large-caps with solid option liquidity ─────────────────
TIER_2 = [
    "PLTR", "SOFI", "COIN", "HOOD", "SNAP", "UBER", "LYFT",
    "CRM", "ORCL", "ADBE", "NOW", "SNOW", "DDOG", "NET",
    "DIS", "NFLX", "SPOT", "ROKU",
    "BA", "CAT", "DE", "MMM", "GE",
    "F", "GM", "RIVN",
    "PFE", "MRK", "BMY", "AMGN", "GILD",
    "SLB", "HAL", "OXY",
]

# ── Tier 3: Extended Russell 1000 coverage ────────────────────────────────────
TIER_3 = [
    "AMAT", "LRCX", "KLAC", "MRVL", "ON",
    "TXN", "ADI", "MCHP",
    "PYPL", "SQ", "AFRM",
    "ZM", "DOCU", "TWLO",
    "BKNG", "EXPE", "MAR", "HLT",
    "WFC", "C", "USB", "PNC", "TFC",
    "CVS", "WBA", "CI", "HUM", "ELV",
]

# ── Pre-excluded (never scan) ─────────────────────────────────────────────────
# Biotech, Chinese ADRs, leveraged ETFs — kept here for documentation
EXCLUDED = [
    # Biotech (binary event risk)
    "MRNA", "BNTX", "BIIB", "REGN", "VRTX", "ILMN",
    # Chinese ADRs
    "BABA", "JD", "PDD", "BIDU", "NIO", "XPEV", "LI",
    # Leveraged ETFs
    "TQQQ", "SQQQ", "SOXL", "SOXS", "UVXY", "SVXY",
    "LABU", "LABD", "TECL", "TECS",
]

# ── Convenience groupings ─────────────────────────────────────────────────────
QUICK_SCAN   = TIER_1                          # ~40 tickers, ~2 min
FULL_SCAN    = TIER_1 + TIER_2 + TIER_3       # ~100 tickers, ~8 min

def get_universe(tier: str = "quick") -> list[str]:
    """Return the ticker list for the given tier name."""
    mapping = {
        "quick":  QUICK_SCAN,
        "full":   FULL_SCAN,
        "tier1":  TIER_1,
        "tier2":  TIER_2,
        "tier3":  TIER_3,
    }
    tickers = mapping.get(tier.lower(), QUICK_SCAN)
    # Remove any that appear in the exclusion list
    return [t for t in tickers if t not in EXCLUDED]
