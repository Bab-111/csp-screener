"""
tests/test_scorer.py — Unit tests for v2.0 scoring functions.
Run with: python -m pytest tests/
"""

import pytest
from screener.scorer import (
    score_vrp, score_ann_yield, score_earnings, score_delta,
    score_premium_efficiency, score_liquidity, score_trend,
    Candidate, WEIGHTS,
)

# ── Weights ────────────────────────────────────────────────────────────────────
def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

def test_weights_v2_structure():
    assert "prem_eff" in WEIGHTS
    assert "vrp" in WEIGHTS
    assert "ivr" not in WEIGHTS      # removed in v2
    assert "cushion" not in WEIGHTS  # removed in v2
    assert "trend" not in WEIGHTS    # removed in v2

# ── VRP ────────────────────────────────────────────────────────────────────────
def test_vrp_poor():         assert score_vrp(3)  == 20.0
def test_vrp_average():      assert score_vrp(7)  == 50.0
def test_vrp_good():         assert score_vrp(12) == 75.0
def test_vrp_excellent():    assert score_vrp(20) == 100.0
def test_vrp_extreme():      assert score_vrp(30) == 85.0   # penalty for extreme VRP
def test_vrp_boundary_5():   assert score_vrp(5)  == 50.0
def test_vrp_boundary_10():  assert score_vrp(10) == 75.0
def test_vrp_boundary_15():  assert score_vrp(15) == 100.0
def test_vrp_boundary_25():  assert score_vrp(25) == 85.0   # just into penalty zone

# ── Annual yield ───────────────────────────────────────────────────────────────
def test_yield_below_floor():  assert score_ann_yield(0.10) == 50.0  # passes dynamic floor
def test_yield_modest():       assert score_ann_yield(0.17) == 50.0
def test_yield_good():         assert score_ann_yield(0.22) == 70.0
def test_yield_great():        assert score_ann_yield(0.28) == 85.0
def test_yield_excellent():    assert score_ann_yield(0.38) == 100.0

# ── Earnings ───────────────────────────────────────────────────────────────────
def test_earnings_reject():      assert score_earnings(10)   == 0.0
def test_earnings_unconfirmed(): assert score_earnings(None) == 30.0  # penalty, not zero
def test_earnings_caution():     assert score_earnings(15)   == 40.0
def test_earnings_good():        assert score_earnings(30)   == 70.0
def test_earnings_excellent():   assert score_earnings(60)   == 100.0

# ── Delta ──────────────────────────────────────────────────────────────────────
def test_delta_very_low():   assert score_delta(0.08) == 100.0
def test_delta_low():        assert score_delta(0.12) == 90.0
def test_delta_medium():     assert score_delta(0.16) == 75.0
def test_delta_upper():      assert score_delta(0.20) == 60.0
def test_delta_reject():     assert score_delta(0.22) == 0.0   # > 0.20 hard filtered

# ── Premium efficiency ─────────────────────────────────────────────────────────
def test_prem_eff_poor():     assert score_premium_efficiency(0.3, 10.0) == 20.0  # 0.03
def test_prem_eff_average():  assert score_premium_efficiency(0.8, 10.0) == 50.0  # 0.08
def test_prem_eff_good():     assert score_premium_efficiency(1.2, 10.0) == 75.0  # 0.12
def test_prem_eff_excellent(): assert score_premium_efficiency(2.0, 10.0) == 100.0 # 0.20
def test_prem_eff_zero_move(): assert score_premium_efficiency(1.0, 0.0) == 20.0  # guard

# ── Liquidity ──────────────────────────────────────────────────────────────────
def test_liquidity_all():
    assert score_liquidity(6000, 0.02, 6_000_000) == 100.0

def test_liquidity_none():
    assert score_liquidity(100, 0.15, 500_000) == 0.0

def test_liquidity_partial():
    # OI 6000 (+40) + spread 5% (3-7% → +25) + vol 3M (2-5M → +10) = 75
    assert score_liquidity(6000, 0.05, 3_000_000) == 75.0

# ── Trend (display only) ───────────────────────────────────────────────────────
def test_trend_all_true():    assert score_trend(100, 90, 80)  == 100.0
def test_trend_two_true():    assert score_trend(100, 90, 95)  == 70.0
def test_trend_none():        assert score_trend(70, 80, 90)   == 10.0

# ── Final score arithmetic ─────────────────────────────────────────────────────
def test_final_score_arithmetic():
    """Score must be the weighted sum of the 6 factors, no more."""
    c = Candidate(
        ticker="TEST", strike=200, dte=30, expiry="2026-08-15",
        premium=2.0, delta=-0.14, iv=0.35, hv30=0.24,
        vrp=11.0, ivhv_ratio=1.46, ivr=60.0,
        ann_yield=0.24, earnings_days=45,
        prob_otm=0.86, breakeven=198.0, collateral=20000,
        cushion=0.04, exp_move=9.0, prem_efficiency=0.222,
        oi=3500, spread_pct=0.03, volume20d=5_000_000,
        ma50=195.0, ma200=180.0, price=210.0, low52w=160.0,
        vix_regime="calm",
    )
    c.compute_score()

    expected = (
        c.s_vrp       * WEIGHTS["vrp"]       +
        c.s_yield     * WEIGHTS["ann_yield"]  +
        c.s_earnings  * WEIGHTS["earnings"]   +
        c.s_delta     * WEIGHTS["delta"]      +
        c.s_prem_eff  * WEIGHTS["prem_eff"]   +
        c.s_liquidity * WEIGHTS["liquidity"]
    )
    assert abs(expected - c.final_score) < 0.01

def test_final_score_range():
    c = Candidate(
        ticker="TEST", strike=100, dte=30, expiry="2026-08-15",
        premium=1.50, delta=-0.15, iv=0.35, hv30=0.25,
        vrp=10.0, ivhv_ratio=1.40, ivr=55.0,
        ann_yield=0.24, earnings_days=45,
        prob_otm=0.85, breakeven=98.5, collateral=10000,
        cushion=0.04, exp_move=5.0, prem_efficiency=0.30,
        oi=5000, spread_pct=0.02, volume20d=5_000_000,
        ma50=95, ma200=85, price=110, low52w=80, vix_regime="calm",
    )
    c.compute_score()
    assert 0 <= c.final_score <= 100
    assert c.risk_label in ("Low", "Medium", "High",
                             "Medium ⚠ earn unconfirmed",
                             "High ⚠ earn unconfirmed")
    assert c.juice_score >= 0

def test_no_v1_fields_in_score():
    """Confirm v1 scoring fields (IVR, cushion, trend) are NOT in WEIGHTS."""
    for removed in ("ivr", "cushion", "trend"):
        assert removed not in WEIGHTS, f"{removed} should be removed from WEIGHTS in v2.0"
