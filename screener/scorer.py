"""
scorer.py — Applies all hard filters and computes the final CSP score
for every eligible put contract on a given stock.

Scoring weights (must sum to 1.0):
  VRP           25%
  Ann Yield     20%
  Earnings      15%
  Delta         10%
  IVR           10%
  Cushion       10%
  Liquidity      5%
  Trend          5%
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from .data import StockData, bs_put_price, RISK_FREE_RATE


# ── Scoring weights ────────────────────────────────────────────────────────────
WEIGHTS = {
    "vrp":       0.25,
    "ann_yield": 0.20,
    "earnings":  0.15,
    "delta":     0.10,
    "ivr":       0.10,
    "cushion":   0.10,
    "liquidity": 0.05,
    "trend":     0.05,
}


# ── Score lookup tables ────────────────────────────────────────────────────────
def score_vrp(vrp: float) -> float:
    if vrp < 5:   return 20.0
    if vrp < 10:  return 50.0
    if vrp < 15:  return 75.0
    return 100.0

def score_ann_yield(y: float) -> float:
    """y is a decimal, e.g. 0.26 for 26%."""
    if y < 0.15:  return 20.0
    if y < 0.20:  return 50.0
    if y < 0.30:  return 75.0
    return 100.0

def score_earnings(days: Optional[int]) -> float:
    if days is None or days < 14:  return 0.0
    if days < 21:                  return 40.0
    if days < 45:                  return 70.0
    return 100.0

def score_delta(delta_abs: float) -> float:
    if delta_abs <= 0.15:  return 100.0
    if delta_abs <= 0.20:  return 80.0
    if delta_abs <= 0.25:  return 60.0
    return 0.0

def score_ivr(ivr: float) -> float:
    if ivr < 30:   return 0.0      # hard filter
    if ivr < 40:   return 50.0
    if ivr < 60:   return 75.0
    if ivr < 80:   return 100.0
    return 90.0                    # >80 slight penalty

def score_cushion(c: float) -> float:
    """c is a decimal fraction, e.g. 0.03 for 3%."""
    if c < 0:     return 20.0
    if c < 0.02:  return 50.0
    if c < 0.05:  return 75.0
    return 100.0

def score_liquidity(oi: float, spread_pct: float, volume20d: float) -> float:
    pts = 0.0
    if oi >= 5000:        pts += 40
    elif oi >= 1000:      pts += 20
    if spread_pct <= 0.03: pts += 40
    elif spread_pct <= 0.07: pts += 20
    if volume20d >= 5_000_000:  pts += 20
    elif volume20d >= 2_000_000: pts += 10
    return min(pts, 100.0)

def score_trend(price: float, ma50: float, ma200: float) -> float:
    conditions = [
        price  > ma50  if ma50  > 0 else False,
        price  > ma200 if ma200 > 0 else False,
        ma50   > ma200 if (ma50 > 0 and ma200 > 0) else False,
    ]
    true_count = sum(conditions)
    return [10.0, 40.0, 70.0, 100.0][true_count]


# ── Candidate result dataclass ─────────────────────────────────────────────────
@dataclass
class Candidate:
    ticker:       str
    strike:       float
    dte:          int
    expiry:       str
    premium:      float      # option mid price
    delta:        float      # negative put delta from live chain
    iv:           float      # implied vol (decimal)
    hv30:         float      # 30-day realized vol (decimal)
    vrp:          float      # IV - HV in percentage points (iv-hv)*100
    ivhv_ratio:   float
    ivr:          float      # IV Rank proxy 0-100
    ann_yield:    float      # decimal
    earnings_days: Optional[int]
    prob_otm:     float      # 1 - |delta|
    breakeven:    float
    collateral:   float
    cushion:      float
    exp_move:     float
    oi:           float
    spread_pct:   float
    volume20d:    float
    ma50:         float
    ma200:        float
    price:        float
    low52w:       float

    # Scores (filled by compute_score)
    s_vrp:       float = 0.0
    s_yield:     float = 0.0
    s_earnings:  float = 0.0
    s_delta:     float = 0.0
    s_ivr:       float = 0.0
    s_cushion:   float = 0.0
    s_liquidity: float = 0.0
    s_trend:     float = 0.0
    final_score: float = 0.0
    juice_score: float = 0.0
    risk_label:  str   = ""

    def compute_score(self) -> "Candidate":
        # Cushion penalty if strike near 52-week low
        cushion_score = score_cushion(self.cushion)
        if self.low52w > 0:
            dist_from_low = (self.strike - self.low52w) / self.strike
            if dist_from_low < 0.02:
                cushion_score = max(0, cushion_score - 15)

        self.s_vrp       = score_vrp(self.vrp)
        self.s_yield     = score_ann_yield(self.ann_yield)
        self.s_earnings  = score_earnings(self.earnings_days)
        self.s_delta     = score_delta(abs(self.delta))
        self.s_ivr       = score_ivr(self.ivr)
        self.s_cushion   = cushion_score
        self.s_liquidity = score_liquidity(self.oi, self.spread_pct, self.volume20d)
        self.s_trend     = score_trend(self.price, self.ma50, self.ma200)

        self.final_score = (
            WEIGHTS["vrp"]       * self.s_vrp
          + WEIGHTS["ann_yield"] * self.s_yield
          + WEIGHTS["earnings"]  * self.s_earnings
          + WEIGHTS["delta"]     * self.s_delta
          + WEIGHTS["ivr"]       * self.s_ivr
          + WEIGHTS["cushion"]   * self.s_cushion
          + WEIGHTS["liquidity"] * self.s_liquidity
          + WEIGHTS["trend"]     * self.s_trend
        )

        # Juice Score — all in raw decimal
        vrp_dec = self.vrp / 100.0   # convert pp back to decimal
        if abs(self.delta) > 0:
            self.juice_score = (
                vrp_dec * self.ann_yield * self.prob_otm
            ) / abs(self.delta)
        else:
            self.juice_score = 0.0

        self.risk_label = self._risk()
        return self

    def _risk(self) -> str:
        d = abs(self.delta)
        p = self.prob_otm
        # earnings_days should never be None at this point — unconfirmed
        # earnings are now rejected by the hard filter before a Candidate
        # is ever built. If this fires anyway, treat it as the most
        # conservative case rather than silently defaulting to 0.
        if self.earnings_days is None:
            return "High"
        e = self.earnings_days
        if d < 0.15 and p > 0.85 and e > 30 and 40 <= self.ivr <= 70:
            return "Low"
        if d <= 0.20 and p >= 0.80 and e >= 14:
            return "Medium"
        return "High"


# ── Hard filter ────────────────────────────────────────────────────────────────
def passes_hard_filters(
    row: pd.Series,
    sd: StockData,
    earnings_days: Optional[int],
    account_size: float,
    max_position_pct: float,
    min_ivr: float,
    min_prob_otm: float,
    min_annual_yield: float,
    min_avg_volume: float,
    min_oi: int,
    max_spread_pct: float,
    min_earnings_days: int,
) -> tuple[bool, str]:
    """Returns (passes, reason_if_failed)."""

    if sd.price < 20:
        return False, f"price ${sd.price:.2f} < $20"

    if sd.volume20d < min_avg_volume:
        return False, f"avg vol {sd.volume20d/1e6:.1f}M < {min_avg_volume/1e6:.1f}M"

    oi = row.get("openInterest", 0) or 0
    if oi < min_oi:
        return False, f"OI {oi} < {min_oi}"

    spread = row.get("spread_pct", 1.0) or 1.0
    if spread > max_spread_pct:
        return False, f"spread {spread:.1%} > {max_spread_pct:.1%}"

    if sd.ivr < min_ivr:
        return False, f"IVR {sd.ivr:.1f} < {min_ivr}"

    delta_abs = abs(row.get("bs_delta", 0) or 0)
    if delta_abs > 0.25:
        return False, f"|delta| {delta_abs:.2f} > 0.25"

    # Unconfirmed earnings date is NOT the same as "earnings far away" —
    # treating unknown as safe is exactly backwards. If we can't confirm
    # the date, we can't confirm the position is safe from an earnings
    # gap, so it must be excluded rather than silently scored as neutral.
    if earnings_days is None:
        return False, "earnings date unconfirmed — cannot verify safety, excluded"

    if earnings_days < min_earnings_days:
        return False, f"earnings in {earnings_days}d < {min_earnings_days}d"

    prob_otm = 1 - delta_abs
    if prob_otm < min_prob_otm:
        return False, f"prob OTM {prob_otm:.1%} < {min_prob_otm:.1%}"

    ann_yield = row.get("ann_yield", 0) or 0
    if ann_yield < min_annual_yield:
        return False, f"ann yield {ann_yield:.1%} < {min_annual_yield:.1%}"

    collateral = row.get("strike", 0) * 100
    if collateral > account_size * max_position_pct:
        return False, f"collateral ${collateral:,.0f} > {max_position_pct:.0%} of account"

    if row.get("iv", 0) <= 0:
        return False, "no IV data"

    if row.get("mid", 0) <= 0:
        return False, "zero bid"

    # VRP floor: if IV is below realized HV, the seller has no actual
    # volatility edge — the market isn't overpricing risk, it's underpricing
    # it. Including these would let "Juice Score" arithmetic mask trades
    # that are structurally backwards (selling cheap, not expensive, vol).
    vrp = row.get("vrp", 0) or 0
    if vrp <= 0:
        return False, f"VRP {vrp*100:+.1f}pp ≤ 0 — IV below realized vol, no seller's edge"

    return True, ""


# ── Main screener function ─────────────────────────────────────────────────────
def screen_ticker(
    sd: StockData,
    config: dict,
) -> tuple[list[Candidate], list[str]]:
    """
    Given a populated StockData, apply all filters and return
    (candidates, rejection_reasons) — one reason string per
    contract that failed a hard filter, so a 0-result run can
    be diagnosed instead of just reported as empty.
    """
    if not sd.valid or sd.options_df is None:
        return [], [f"{sd.ticker}: {sd.error or 'fetch failed'}"]

    today = datetime.date.today()
    earnings_days: Optional[int] = None
    if sd.earnings_date:
        earnings_days = (sd.earnings_date - today).days
        if earnings_days < 0:
            earnings_days = None   # past earnings, ignore

    candidates = []
    rejections = []

    for _, row in sd.options_df.iterrows():
        ok, reason = passes_hard_filters(
            row, sd, earnings_days,
            account_size      = config.get("account_size", 50_000),
            max_position_pct  = config.get("max_position_pct", 0.25),
            min_ivr            = config.get("min_ivr", 30),
            min_prob_otm      = config.get("min_prob_otm", 0.75),
            min_annual_yield  = config.get("min_annual_yield", 0.15),
            min_avg_volume    = config.get("min_avg_volume", 2_000_000),
            min_oi            = config.get("min_oi", 1000),
            max_spread_pct    = config.get("max_spread_pct", 0.07),
            min_earnings_days = config.get("min_earnings_days", 14),
        )
        if not ok:
            rejections.append(f"{sd.ticker} ${row['strike']:.2f}: {reason}")
            continue

        delta     = float(row.get("bs_delta", 0) or 0)
        iv        = float(row.get("iv", 0) or 0)
        vrp_pp    = (iv - sd.hv30) * 100   # convert to percentage points

        c = Candidate(
            ticker        = sd.ticker,
            strike        = float(row["strike"]),
            dte           = sd.dte,
            expiry        = sd.expiry,
            premium       = float(row["mid"]),
            delta         = delta,
            iv            = iv,
            hv30          = sd.hv30,
            vrp           = vrp_pp,
            ivhv_ratio    = float(row.get("ivhv_ratio", 0) or 0),
            ivr           = sd.ivr,
            ann_yield     = float(row.get("ann_yield", 0) or 0),
            earnings_days = earnings_days,
            prob_otm      = 1 - abs(delta),
            breakeven     = float(row.get("breakeven", 0) or 0),
            collateral    = float(row["strike"]) * 100,
            cushion       = float(row.get("cushion", 0) or 0),
            exp_move      = float(row.get("exp_move", 0) or 0),
            oi            = float(row.get("openInterest", 0) or 0),
            spread_pct    = float(row.get("spread_pct", 0) or 0),
            volume20d     = sd.volume20d,
            ma50          = sd.ma50,
            ma200         = sd.ma200,
            price         = sd.price,
            low52w        = sd.low52w,
        )
        c.compute_score()
        candidates.append(c)

    return candidates, rejections
