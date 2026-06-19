"""
data.py — Live market data fetcher using yfinance.

Fetches:
  - Stock price, volume, 52-week high/low
  - Options chain (puts) for the nearest target DTE expiry
  - 30-day realized HV from daily price history
  - IV Rank from 1-year option history (approximated via HV proxy)
  - Moving averages (50d, 200d)
  - Next earnings date
"""

from __future__ import annotations

import datetime
import warnings
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ── Constants ──────────────────────────────────────────────────────────────────
TRADING_DAYS_YEAR = 252
MIN_HISTORY_DAYS  = 252          # 1 year of daily bars needed for IVR
RISK_FREE_RATE    = 0.045        # 3-month T-bill proxy; update or fetch live


# ── Black-Scholes helpers ──────────────────────────────────────────────────────
def _norm_cdf(x: float) -> float:
    from scipy.stats import norm
    return float(norm.cdf(x))


def bs_put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes put price. Returns 0 if inputs are degenerate."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    from math import log, sqrt, exp
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    return float(K * exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1))


def bs_delta(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes put delta (negative value)."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    from math import log, sqrt
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    return float(_norm_cdf(d1) - 1)


def implied_vol_bisection(
    market_price: float,
    S: float, K: float, T: float, r: float,
    tol: float = 1e-5,
    max_iter: int = 100,
) -> Optional[float]:
    """Solve for IV using bisection. Returns None if no solution found."""
    if market_price <= 0 or T <= 0:
        return None
    lo, hi = 0.001, 5.0
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        price = bs_put_price(S, K, T, r, mid)
        if abs(price - market_price) < tol:
            return mid
        if price < market_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ── Core data class ────────────────────────────────────────────────────────────
class StockData:
    """All data needed to score a CSP candidate."""

    def __init__(self, ticker: str):
        self.ticker   = ticker
        self.valid    = False
        self.error    = None

        # Populated by fetch()
        self.price:     float = 0.0
        self.volume20d: float = 0.0
        self.high52w:   float = 0.0
        self.low52w:    float = 0.0
        self.ma50:      float = 0.0
        self.ma200:     float = 0.0
        self.hv30:      float = 0.0       # 30-day realized vol
        self.ivr:       float = 0.0       # IV Rank 0–100
        self.earnings_date: Optional[datetime.date] = None
        self.options_df: Optional[pd.DataFrame] = None   # puts for best expiry
        self.expiry:    Optional[str] = None
        self.dte:       int = 0

    def fetch(self, dte_min: int = 21, dte_max: int = 45) -> "StockData":
        """Pull all data from yfinance. Returns self for chaining."""
        try:
            tk = yf.Ticker(self.ticker)

            # ── 1. Price history ───────────────────────────────────────────
            hist = tk.history(period="2y", interval="1d", auto_adjust=True)
            if hist.empty or len(hist) < MIN_HISTORY_DAYS:
                self.error = "insufficient price history"
                return self

            closes = hist["Close"].dropna()
            self.price    = float(closes.iloc[-1])
            self.high52w  = float(closes.iloc[-252:].max())
            self.low52w   = float(closes.iloc[-252:].min())
            self.volume20d = float(hist["Volume"].iloc[-20:].mean())

            # ── 2. Moving averages ─────────────────────────────────────────
            self.ma50  = float(closes.iloc[-50:].mean())  if len(closes) >= 50  else 0.0
            self.ma200 = float(closes.iloc[-200:].mean()) if len(closes) >= 200 else 0.0

            # ── 3. 30-day realized HV ──────────────────────────────────────
            log_returns = np.log(closes / closes.shift(1)).dropna()
            self.hv30 = float(log_returns.iloc[-30:].std() * np.sqrt(TRADING_DAYS_YEAR))

            # ── 4. IV Rank proxy ───────────────────────────────────────────
            # True IVR needs 1y of option IV history which yfinance doesn't
            # provide. We approximate: compute rolling 30-day HV over 1 year
            # and rank current HV within that range.
            # This is a PROXY — stated as such in output.
            rolling_hv = (
                log_returns.rolling(30)
                .std()
                .dropna()
                .iloc[-252:]
                * np.sqrt(TRADING_DAYS_YEAR)
            )
            if len(rolling_hv) > 10:
                hv_min = float(rolling_hv.min())
                hv_max = float(rolling_hv.max())
                if hv_max > hv_min:
                    self.ivr = float(
                        (self.hv30 - hv_min) / (hv_max - hv_min) * 100
                    )
                else:
                    self.ivr = 50.0
            else:
                self.ivr = 50.0

            # ── 5. Earnings date ───────────────────────────────────────────
            try:
                cal = tk.calendar
                if cal is not None and not cal.empty:
                    dates = cal.loc["Earnings Date"] if "Earnings Date" in cal.index else None
                    if dates is not None:
                        ed = dates.iloc[0] if hasattr(dates, "iloc") else dates
                        if pd.notna(ed):
                            self.earnings_date = pd.Timestamp(ed).date()
            except Exception:
                self.earnings_date = None

            # ── 6. Options chain ───────────────────────────────────────────
            today = datetime.date.today()
            expiries = tk.options
            if not expiries:
                self.error = "no options listed"
                return self

            # Find the expiry closest to 30 DTE within [dte_min, dte_max]
            best_expiry = None
            best_dte    = None
            for exp_str in expiries:
                exp_date = datetime.date.fromisoformat(exp_str)
                dte = (exp_date - today).days
                if dte_min <= dte <= dte_max:
                    if best_dte is None or abs(dte - 30) < abs(best_dte - 30):
                        best_expiry = exp_str
                        best_dte    = dte

            if best_expiry is None:
                self.error = f"no expiry found in {dte_min}–{dte_max} DTE window"
                return self

            self.expiry = best_expiry
            self.dte    = best_dte

            chain  = tk.option_chain(best_expiry)
            puts   = chain.puts.copy()

            if puts.empty:
                self.error = "empty puts chain"
                return self

            # Keep only OTM puts (strike < current price)
            puts = puts[puts["strike"] < self.price].copy()
            if puts.empty:
                self.error = "no OTM puts available"
                return self

            # Compute mid price
            puts["mid"] = (puts["bid"] + puts["ask"]) / 2

            # Filter out zero-bid options
            puts = puts[puts["bid"] > 0].copy()

            # Compute spread %
            puts["spread_pct"] = (puts["ask"] - puts["bid"]) / puts["mid"].replace(0, np.nan)

            # Compute IV from yfinance (already provided as impliedVolatility)
            puts["iv"] = puts["impliedVolatility"].fillna(0)

            # Compute delta via B-S (yfinance doesn't always provide Greeks)
            T = best_dte / 365.0
            puts["bs_delta"] = puts.apply(
                lambda r: bs_delta(self.price, r["strike"], T, RISK_FREE_RATE, r["iv"])
                if r["iv"] > 0 else np.nan,
                axis=1,
            )

            # Compute annualized yield
            puts["ann_yield"] = (puts["mid"] / puts["strike"]) * (365 / best_dte)

            # Compute VRP = IV - HV30
            puts["vrp"] = puts["iv"] - self.hv30

            # Expected move and cushion
            puts["exp_move"] = self.price * puts["iv"] * np.sqrt(T)
            puts["cushion"]  = (
                (self.price - puts["strike"]) - puts["exp_move"]
            ) / self.price

            # Break-even
            puts["breakeven"] = puts["strike"] - puts["mid"]

            # Collateral
            puts["collateral"] = puts["strike"] * 100

            # IVHVRatio
            puts["ivhv_ratio"] = puts["iv"] / self.hv30 if self.hv30 > 0 else np.nan

            self.options_df = puts.reset_index(drop=True)
            self.valid = True

        except Exception as e:
            self.error = str(e)

        return self
