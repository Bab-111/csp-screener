"""
scorer.py — CSP Screener v2.0 scoring engine.

Scoring weights (sum = 1.0):
  VRP                  30%   (core edge — IV overpricing vs realized vol)
  Annualized Yield     25%   (premium income per capital deployed)
  Earnings Distance    20%   (binary event risk avoidance)
  Delta                10%   (assignment probability proxy)
  Premium Efficiency   10%   (premium per dollar of expected move)
  Liquidity             5%   (execution quality)

Removed from scoring vs v1:
  - IVR proxy (HV percentile) — too noisy, not true IV Rank
  - Trend score — context only, not a premium signal

IVHVRatio and trend now appear in commentary/display only.

Sources consolidated:
  - v2.0 spec (trader's preferred design)
  - External audit recommendations
  - Saxo Bank Options Guidebook (foundational option mechanics)
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .data import StockData, RISK_FREE_RATE


# ── Scoring weights (must sum exactly to 1.0) ─────────────────────────────────
WEIGHTS = {
    "vrp":        0.30,
    "ann_yield":  0.25,
    "earnings":   0.20,
    "delta":      0.10,
    "prem_eff":   0.10,
    "liquidity":  0.05,
}

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"


# ── Individual factor scoring functions ───────────────────────────────────────

def score_vrp(vrp: float) -> float:
    """
    VRP = (IV - HV30) in percentage points.
    Measures how much the market is overpaying for volatility —
    the seller's structural edge. Source: Saxo guidebook confirms
    premium = intrinsic + extrinsic; for OTM CSPs all premium is
    extrinsic (time value), so VRP directly measures the quality
    of that extrinsic value.
    Very high VRP (>25pp) gets slight penalty — per audit, extreme
    VRP often signals an event risk not fully captured by filters.
    """
    if vrp < 5:    return 20.0
    if vrp < 10:   return 50.0
    if vrp < 15:   return 75.0
    if vrp < 25:   return 100.0
    return 85.0   # >25pp — elevated but penalised for potential event risk


def score_ann_yield(y: float, vix_regime: str = "normal") -> float:
    """
    Annualized yield = (premium / strike) × (365 / DTE).
    Dynamic floor by VIX regime per v2.0 spec and audit.
    Thresholds:
      calm (VIX ≤ 20):    floor at 12%
      normal (VIX 20-25): floor at 15%
      override (VIX > 25): floor at 18%
    This is passed as a scoring function (not a hard filter) —
    the hard filter enforces the floor, scoring gives relative ranking.
    """
    if y < 0.20:   return 50.0   # passes floor but modest
    if y < 0.25:   return 70.0
    if y < 0.35:   return 85.0
    return 100.0


def score_earnings(days: Optional[int]) -> float:
    """
    Earnings distance from Saxo guidebook principle: options are
    time-sensitive instruments; earnings = binary event that can
    gap through any strike instantly. This is the highest-weight
    structural risk for a CSP seller.
    None (unconfirmed) = conservative penalty score of 30.
    """
    if days is None:  return 30.0   # unconfirmed — penalised, not rejected
    if days < 14:     return 0.0    # hard reject (also filtered above)
    if days < 21:     return 40.0
    if days < 45:     return 70.0
    return 100.0


def score_delta(delta_abs: float) -> float:
    """
    Delta ≤ 0.20 hard cap per v2.0 spec (tighter than original 0.25).
    Lower delta = lower assignment probability = more pure time-value harvest.
    Saxo guidebook: a put writer has obligation to buy stock at strike —
    delta directly reflects likelihood of that obligation being triggered.
    """
    if delta_abs <= 0.10:  return 100.0
    if delta_abs <= 0.15:  return 90.0
    if delta_abs <= 0.18:  return 75.0
    if delta_abs <= 0.20:  return 60.0
    return 0.0   # > 0.20 never reaches here (hard filtered)


def score_premium_efficiency(premium: float, exp_move: float) -> float:
    """
    Premium Efficiency = Premium / Expected Move.
    New metric replacing IVR proxy. Measures how much you collect
    per dollar of actual expected stock movement — the direct answer
    to "am I being paid well for this risk?"
    Higher ratio = more premium per unit of risk.
    Formula: Premium / (Price × IV × sqrt(DTE/365))
    """
    if exp_move <= 0:  return 20.0
    ratio = premium / exp_move
    if ratio < 0.05:   return 20.0
    if ratio < 0.10:   return 50.0
    if ratio < 0.15:   return 75.0
    return 100.0


def score_liquidity(oi: float, spread_pct: float, volume20d: float) -> float:
    """
    Composite liquidity score. Saxo guidebook emphasises that
    options are tradeable instruments — exit flexibility and fill
    quality depend directly on OI, spread, and underlying volume.
    """
    pts = 0.0
    if oi >= 5000:             pts += 40
    elif oi >= 1000:           pts += 25
    elif oi >= 200:            pts += 10
    if spread_pct <= 0.03:     pts += 40
    elif spread_pct <= 0.07:   pts += 25
    elif spread_pct <= 0.12:   pts += 10
    if volume20d >= 5_000_000:   pts += 20
    elif volume20d >= 2_000_000: pts += 10
    return min(pts, 100.0)


def score_trend(price: float, ma50: float, ma200: float) -> float:
    """
    Trend score — NOT used in final score (display/commentary only).
    Per v2.0 spec: trend is context for a CSP seller, not a ranking
    signal. A put seller wants the stock to stay flat or rise, so an
    uptrend is favourable context, but it doesn't change the premium edge.
    Kept here to populate the display field without affecting ranking.
    """
    conditions = [
        price > ma50  if ma50  > 0 else False,
        price > ma200 if ma200 > 0 else False,
        ma50  > ma200 if (ma50 > 0 and ma200 > 0) else False,
    ]
    true_count = sum(conditions)
    return [10.0, 40.0, 70.0, 100.0][true_count]


# ── Candidate dataclass ───────────────────────────────────────────────────────
@dataclass
class Candidate:
    # Market data
    ticker:        str
    strike:        float
    dte:           int
    expiry:        str
    premium:       float      # option mid price (extrinsic value for OTM puts)
    delta:         float      # negative put delta
    iv:            float      # implied vol (decimal)
    hv30:          float      # 30-day realized vol (decimal)
    vrp:           float      # (IV - HV) × 100 — in percentage points
    ivhv_ratio:    float      # IV / HV — display only
    ivr:           float      # HV percentile proxy — display only, not scored
    ann_yield:     float      # (premium/strike) × (365/DTE)
    earnings_days: Optional[int]
    prob_otm:      float      # 1 - |delta| — display only (redundant with delta)
    breakeven:     float      # strike - premium (per Saxo guidebook formula)
    collateral:    float      # strike × 100
    cushion:       float      # ((price-strike) - exp_move) / price
    exp_move:      float      # price × IV × sqrt(DTE/365)
    prem_efficiency: float    # premium / exp_move
    oi:            float
    spread_pct:    float
    volume20d:     float
    ma50:          float
    ma200:         float
    price:         float
    low52w:        float
    vix_regime:    str = "normal"   # "calm" / "normal" / "override"

    # Factor scores (filled by compute_score)
    s_vrp:        float = 0.0
    s_yield:      float = 0.0
    s_earnings:   float = 0.0
    s_delta:      float = 0.0
    s_prem_eff:   float = 0.0
    s_liquidity:  float = 0.0
    s_trend:      float = 0.0   # display only — not in final score
    final_score:  float = 0.0
    juice_score:  float = 0.0
    risk_label:   str   = ""

    def compute_score(self) -> "Candidate":
        # Cushion penalty: if strike is within 2% of 52-week low,
        # reduce premium efficiency score (the strike is near a danger zone)
        prem_eff_score = score_premium_efficiency(self.premium, self.exp_move)
        if self.low52w > 0:
            dist_from_low = (self.strike - self.low52w) / self.strike
            if dist_from_low < 0.02:
                prem_eff_score = max(0, prem_eff_score - 15)

        self.s_vrp       = score_vrp(self.vrp)
        self.s_yield     = score_ann_yield(self.ann_yield, self.vix_regime)
        self.s_earnings  = score_earnings(self.earnings_days)
        self.s_delta     = score_delta(abs(self.delta))
        self.s_prem_eff  = prem_eff_score
        self.s_liquidity = score_liquidity(self.oi, self.spread_pct, self.volume20d)
        self.s_trend     = score_trend(self.price, self.ma50, self.ma200)  # display only

        self.final_score = (
            WEIGHTS["vrp"]       * self.s_vrp
          + WEIGHTS["ann_yield"] * self.s_yield
          + WEIGHTS["earnings"]  * self.s_earnings
          + WEIGHTS["delta"]     * self.s_delta
          + WEIGHTS["prem_eff"]  * self.s_prem_eff
          + WEIGHTS["liquidity"] * self.s_liquidity
        )

        # Juice Score — tiebreaker only, per Saxo guidebook's notion that
        # premium quality = yield × probability × edge / risk
        vrp_dec = self.vrp / 100.0
        if abs(self.delta) > 0:
            self.juice_score = (vrp_dec * self.ann_yield * self.prob_otm) / abs(self.delta)
        else:
            self.juice_score = 0.0

        self.risk_label = self._risk()
        return self

    def _risk(self) -> str:
        """
        Risk label based on delta and earnings only (per audit: ProbOTM is
        redundant with delta in this framework — express risk through delta).
        """
        d = abs(self.delta)
        e = self.earnings_days   # None = unconfirmed

        if self.vix_regime == "override":
            # In high-VIX override mode, nothing qualifies as Low
            if e is None:
                return "High ⚠ VIX override + earn unconfirmed"
            if d <= 0.15 and e >= 21:
                return "Medium (VIX override active)"
            return "High (VIX override active)"

        if e is None:
            if d <= 0.15:
                return "Medium ⚠ earn unconfirmed"
            return "High ⚠ earn unconfirmed"

        # Normal and elevated regimes
        if d <= 0.12 and e > 45:
            return "Low"
        if d <= 0.15 and e > 30:
            return "Low"
        if d <= 0.18 and e >= 21:
            return "Medium"
        if d <= 0.20 and e >= 14:
            return "Medium"
        return "High"


# ── Hard rejection filters ────────────────────────────────────────────────────
def passes_hard_filters(
    row: pd.Series,
    sd: StockData,
    earnings_days: Optional[int],
    account_size: float,
    max_position_pct: float,
    min_annual_yield: float,
    min_avg_volume: float,
    min_oi: int,
    max_spread_pct: float,
    min_earnings_days: int,
    max_delta: float,
    vix_regime: str,
) -> tuple[bool, str]:
    """Returns (passes, reason_if_failed)."""

    # 1. Stock price floor
    if sd.price < 20:
        return False, f"price ${sd.price:.2f} < $20"

    # 2. Underlying liquidity
    if sd.volume20d < min_avg_volume:
        return False, f"avg vol {sd.volume20d/1e6:.1f}M < {min_avg_volume/1e6:.1f}M"

    # 3. Option contract OI (specific contract, not chain aggregate)
    oi = row.get("openInterest", 0) or 0
    if oi < min_oi:
        return False, f"OI {oi} < {min_oi}"

    # 4. Bid-ask spread
    spread = row.get("spread_pct", 1.0) or 1.0
    if spread > max_spread_pct:
        return False, f"spread {spread:.1%} > {max_spread_pct:.1%}"

    # 5. Delta — tighter at 0.20 per v2.0 (was 0.25)
    #    VIX override tightens further to 0.15
    delta_abs = abs(row.get("bs_delta", 0) or 0)
    if delta_abs > max_delta:
        return False, f"|delta| {delta_abs:.2f} > {max_delta} ({vix_regime} regime)"

    # 6. Earnings — confirmed within 14d = hard reject
    #    Unconfirmed = pass with warning (scored conservatively at 30/100)
    if earnings_days is not None and earnings_days < min_earnings_days:
        return False, f"earnings in {earnings_days}d < {min_earnings_days}d (confirmed)"

    # 7. Annual yield floor — dynamic by VIX regime per v2.0 and audit
    ann_yield = row.get("ann_yield", 0) or 0
    if ann_yield < min_annual_yield:
        return False, f"ann yield {ann_yield:.1%} < {min_annual_yield:.1%} ({vix_regime} floor)"

    # 8. VRP floor — IV must exceed realized HV for a seller's edge to exist
    #    Per Saxo guidebook: premium = intrinsic + extrinsic; for OTM puts,
    #    all premium is extrinsic. If IV < HV, the extrinsic is underpriced.
    vrp = row.get("vrp", 0) or 0
    if vrp <= 0:
        return False, f"VRP {vrp*100:+.1f}pp ≤ 0 — no seller's edge (IV below realized vol)"

    # 9. No IV data or zero bid
    if row.get("iv", 0) <= 0:
        return False, "no IV data"
    if row.get("mid", 0) <= 0:
        return False, "zero bid — no market"

    # 10. Capital concentration — flag but don't reject
    #     (handled in output, not a hard filter per audit)

    return True, ""


# ── Main screener function ────────────────────────────────────────────────────
def screen_ticker(
    sd: StockData,
    config: dict,
) -> tuple[list[Candidate], list[str]]:
    """
    Apply hard filters and score every passing contract for one ticker.
    Returns (candidates, rejection_reasons).
    """
    if not sd.valid or sd.options_df is None:
        return [], [f"{sd.ticker}: {sd.error or 'fetch failed'}"]

    today = datetime.date.today()
    earnings_days: Optional[int] = None
    if sd.earnings_date:
        earnings_days = (sd.earnings_date - today).days
        if earnings_days < 0:
            earnings_days = None

    # Resolve VIX regime and dynamic thresholds
    vix = config.get("vix", 20.0)
    if vix > 25:
        vix_regime    = "override"
        max_delta     = 0.15
        min_yield     = 0.18
    elif vix > 20:
        vix_regime    = "elevated"
        max_delta     = config.get("max_delta", 0.20)
        min_yield     = 0.15
    else:
        vix_regime    = "calm"
        max_delta     = config.get("max_delta", 0.20)
        min_yield     = 0.12

    # Allow config to further tighten (but never loosen) the yield floor
    min_yield = max(min_yield, config.get("min_annual_yield", 0.0))

    candidates = []
    rejections = []

    for _, row in sd.options_df.iterrows():
        ok, reason = passes_hard_filters(
            row, sd, earnings_days,
            account_size      = config.get("account_size", 50_000),
            max_position_pct  = config.get("max_position_pct", 0.25),
            min_annual_yield  = min_yield,
            min_avg_volume    = config.get("min_avg_volume", 2_000_000),
            min_oi            = config.get("min_oi", 200),
            max_spread_pct    = config.get("max_spread_pct", 0.12),
            min_earnings_days = config.get("min_earnings_days", 14),
            max_delta         = max_delta,
            vix_regime        = vix_regime,
        )
        if not ok:
            rejections.append(f"{sd.ticker} ${row['strike']:.2f}: {reason}")
            continue

        delta = float(row.get("bs_delta", 0) or 0)
        iv    = float(row.get("iv", 0) or 0)
        prem  = float(row.get("mid", 0) or 0)
        exp_m = float(row.get("exp_move", 0) or 0)

        c = Candidate(
            ticker           = sd.ticker,
            strike           = float(row["strike"]),
            dte              = sd.dte,
            expiry           = sd.expiry,
            premium          = prem,
            delta            = delta,
            iv               = iv,
            hv30             = sd.hv30,
            vrp              = (iv - sd.hv30) * 100,
            ivhv_ratio       = float(row.get("ivhv_ratio", 0) or 0),
            ivr              = sd.ivr,   # display only
            ann_yield        = float(row.get("ann_yield", 0) or 0),
            earnings_days    = earnings_days,
            prob_otm         = 1 - abs(delta),   # display only
            breakeven        = float(row.get("breakeven", 0) or 0),
            collateral       = float(row["strike"]) * 100,
            cushion          = float(row.get("cushion", 0) or 0),
            exp_move         = exp_m,
            prem_efficiency  = (prem / exp_m) if exp_m > 0 else 0.0,
            oi               = float(row.get("openInterest", 0) or 0),
            spread_pct       = float(row.get("spread_pct", 0) or 0),
            volume20d        = sd.volume20d,
            ma50             = sd.ma50,
            ma200            = sd.ma200,
            price            = sd.price,
            low52w           = sd.low52w,
            vix_regime       = vix_regime,
        )
        c.compute_score()
        candidates.append(c)

    return candidates, rejections
