"""
tests/test_scorer.py — Unit tests for scoring functions.
Run with: python -m pytest tests/
"""

import pytest
from screener.scorer import (
    score_vrp, score_ann_yield, score_earnings, score_delta,
    score_ivr, score_cushion, score_liquidity, score_trend,
)

# ── VRP ────────────────────────────────────────────────────────────────────────
def test_vrp_below_threshold():    assert score_vrp(3)  == 20.0
def test_vrp_average():            assert score_vrp(7)  == 50.0
def test_vrp_good():               assert score_vrp(12) == 75.0
def test_vrp_excellent():          assert score_vrp(16) == 100.0
def test_vrp_boundary_5():         assert score_vrp(5)  == 50.0
def test_vrp_boundary_10():        assert score_vrp(10) == 75.0
def test_vrp_boundary_15():        assert score_vrp(15) == 100.0

# ── Annual yield ───────────────────────────────────────────────────────────────
def test_yield_poor():             assert score_ann_yield(0.10) == 20.0
def test_yield_acceptable():       assert score_ann_yield(0.17) == 50.0
def test_yield_good():             assert score_ann_yield(0.25) == 75.0
def test_yield_excellent():        assert score_ann_yield(0.35) == 100.0

# ── Earnings ───────────────────────────────────────────────────────────────────
def test_earnings_reject():        assert score_earnings(10)  == 0.0
def test_earnings_none():          assert score_earnings(None)== 0.0
def test_earnings_caution():       assert score_earnings(15)  == 40.0
def test_earnings_good():          assert score_earnings(30)  == 70.0
def test_earnings_excellent():     assert score_earnings(60)  == 100.0

# ── Delta ──────────────────────────────────────────────────────────────────────
def test_delta_excellent():        assert score_delta(0.12) == 100.0
def test_delta_good():             assert score_delta(0.18) == 80.0
def test_delta_acceptable():       assert score_delta(0.23) == 60.0
def test_delta_reject():           assert score_delta(0.26) == 0.0

# ── IVR ────────────────────────────────────────────────────────────────────────
def test_ivr_too_low():            assert score_ivr(20)  == 0.0
def test_ivr_low():                assert score_ivr(35)  == 50.0
def test_ivr_mid():                assert score_ivr(50)  == 75.0
def test_ivr_high():               assert score_ivr(70)  == 100.0
def test_ivr_extreme():            assert score_ivr(85)  == 90.0   # penalized

# ── Cushion ────────────────────────────────────────────────────────────────────
def test_cushion_inside():         assert score_cushion(-0.01) == 20.0
def test_cushion_tight():          assert score_cushion(0.01)  == 50.0
def test_cushion_good():           assert score_cushion(0.03)  == 75.0
def test_cushion_excellent():      assert score_cushion(0.06)  == 100.0

# ── Liquidity ──────────────────────────────────────────────────────────────────
def test_liquidity_all():
    assert score_liquidity(6000, 0.02, 6_000_000) == 100.0

def test_liquidity_none():
    assert score_liquidity(500, 0.10, 500_000) == 0.0

def test_liquidity_partial():
    # OI >= 5000 (+40) + spread 3-7% (+20) + vol >= 5M (+20) = 80
    s = score_liquidity(5000, 0.05, 5_000_000)
    assert s == 80.0

# ── Trend ──────────────────────────────────────────────────────────────────────
def test_trend_all_true():
    assert score_trend(100, 90, 80)  == 100.0   # price>50MA, price>200MA, 50>200

def test_trend_two_true():
    # price(100) > 50MA(90) ✓, price(100) > 200MA(85) ✓, 50MA(90) > 200MA(85) ✓ — actually all 3
    # For 2/3: price(100) > 50MA(90) ✓, price(100) < 200MA(110) ✗, 50MA(90) < 200MA(110) ✗ = 1 true
    # True 2/3 case: price(100) > 50MA(90) ✓, price(100) > 200MA(95) ✓, 50MA(90) < 200MA(95) ✗
    assert score_trend(100, 90, 95) == 70.0

def test_trend_none():
    assert score_trend(70, 80, 90)   == 10.0    # all false

# ── Final score sanity ─────────────────────────────────────────────────────────
def test_final_score_range():
    """Final score should always be 0-100."""
    from screener.scorer import Candidate
    c = Candidate(
        ticker="TEST", strike=100, dte=30, expiry="2025-01-17",
        premium=1.50, delta=-0.15, iv=0.45, hv30=0.35,
        vrp=10.0, ivhv_ratio=1.28, ivr=60.0,
        ann_yield=0.22, earnings_days=45,
        prob_otm=0.85, breakeven=98.5, collateral=10000,
        cushion=0.04, exp_move=5.0, oi=5000,
        spread_pct=0.02, volume20d=5_000_000,
        ma50=95, ma200=85, price=110, low52w=80,
    )
    c.compute_score()
    assert 0 <= c.final_score <= 100
    assert c.risk_label in ("Low", "Medium", "High")
    assert c.juice_score >= 0
