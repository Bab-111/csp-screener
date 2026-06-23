"""
universe.py — Ticker universe for the CSP screener.

Organised into tiers so you can run a quick scan (TIER_1 only)
or a full scan (all tiers).  Biotech, Chinese ADRs, leveraged ETFs
and sub-$20 names are pre-excluded at the list level.

INDEX COVERAGE (top 50% by options liquidity/volume):
  - S&P 500 top ~250 by options activity
  - Nasdaq 100 top ~50 by options activity
  - Dow 30 (all 30, minus biotech/excluded)
"""

# ── Tier 1: Highest-liquidity large-caps & ETFs ───────────────────────────────
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

# ── Tier 4: S&P 500 / Nasdaq 100 / Dow 30 — top 50% by options volume ────────
TIER_4_SP500 = [
    # Cybersecurity
    "PANW", "CRWD", "ZS", "FTNT",
    # Financials / Alt asset managers
    "BX", "KKR", "APO", "SCHW", "AXP", "BLK",
    "CB", "MET", "PRU", "AFL", "ALL",
    # Healthcare devices / services
    "TMO", "DHR", "SYK", "BSX", "EW", "ZBH",
    "ISRG", "MDT", "BDX", "BAX", "HCA",
    # Consumer / retail
    "TGT", "LOW", "TJX", "SBUX", "CMG",
    "YUM", "DPZ", "DG", "DLTR", "KR", "SYY",
    # Semis (non-Tier1)
    "KEYS", "MPWR", "ENTG", "SWKS", "STX", "WDC", "NTAP",
    # Energy (non-Tier1)
    "EOG", "PXD", "MPC", "VLO", "PSX", "LNG", "DVN", "APA",
    # Industrials / Defense
    "HON", "RTX", "LMT", "NOC", "GD", "LHX", "TXT", "HII",
    # Transportation / Logistics
    "UNP", "CSX", "NSC", "UPS", "FDX", "JBHT",
    # REITs
    "AMT", "CCI", "EQIX", "PLD", "O", "WELL",
    # Telecom
    "T", "VZ", "TMUS", "CHTR", "CMCSA",
    # Regional banks
    "RF", "CFG", "FITB", "HBAN", "KEY", "MTB", "ZION",
]

TIER_4_NDX = [
    # E-commerce / travel / gig
    "MELI", "ABNB", "DASH",
    # Enterprise SaaS
    "TEAM", "WDAY", "VEEV", "OKTA", "MDB",
    # MedTech
    "DXCM", "IDXX", "ALGN",
    # Industrials / professional services
    "FAST", "ODFL", "CTAS", "VRSK", "CPRT", "PAYX", "ADP",
    # EDA / design software
    "ANSS", "CDNS", "SNPS",
    # Biotech (large, non-binary)
    "REGN", "VRTX", "BIIB", "ILMN",
    # Clean energy
    "FSLR", "ENPH",
    # Consumer staples
    "MNST", "KHC", "PEP", "KO",
]

TIER_4_DOW = [
    # Dow 30 names not already in Tier 1–3
    "CSCO", "DOW", "IBM", "PG", "TRV",
]

TIER_4 = TIER_4_SP500 + TIER_4_NDX + TIER_4_DOW

# ── Pre-excluded (never scan) ─────────────────────────────────────────────────
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
QUICK_SCAN = TIER_1
FULL_SCAN  = TIER_1 + TIER_2 + TIER_3 + TIER_4


def get_universe(tier: str = "full") -> list[str]:
    """Return the deduplicated ticker list for the given tier name."""
    mapping = {
        "quick":  TIER_1,
        "full":   FULL_SCAN,
        "tier1":  TIER_1,
        "tier2":  TIER_2,
        "tier3":  TIER_3,
        "tier4":  TIER_4,
    }
    tickers = mapping.get(tier.lower(), FULL_SCAN)
    # Deduplicate preserving order, remove excluded
    seen = set()
    result = []
    for t in tickers:
        if t not in EXCLUDED and t not in seen:
            result.append(t)
            seen.add(t)
    return result
