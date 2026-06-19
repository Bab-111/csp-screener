"""
output.py — Renders the final ranked table and per-trade commentary
using the Rich library for a proper terminal display.
"""

from __future__ import annotations

import csv
import datetime
import json
import os
from pathlib import Path
from typing import List

from rich.console import Console
from rich.table import Table
from rich import box
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule

from .scorer import Candidate

console = Console()


# ── Helpers ────────────────────────────────────────────────────────────────────
def _risk_color(risk: str) -> str:
    return {"Low": "green", "Medium": "yellow", "High": "red"}.get(risk, "white")

def _pct(v: float, decimals: int = 1) -> str:
    return f"{v * 100:.{decimals}f}%"

def _dollar(v: float) -> str:
    return f"${v:,.2f}"

def _pp(v: float) -> str:
    """Format percentage points (VRP etc.)."""
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f} pp"


# ── Main output functions ──────────────────────────────────────────────────────
def print_header(vix_est: float, regime: str, scanned: int, passed: int) -> None:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.print()
    console.print(Rule("[bold]Institutional CSP Screener[/bold]", style="dim"))
    console.print(f"  [dim]Run time  :[/dim]  {now}")
    console.print(f"  [dim]Data src  :[/dim]  yfinance (live delayed ~15 min)")
    console.print(f"  [dim]VIX proxy :[/dim]  {vix_est:.1f}  [dim](estimated from VIX ticker)[/dim]")
    console.print(f"  [dim]Regime    :[/dim]  {regime}")
    console.print(f"  [dim]Scanned   :[/dim]  {scanned} tickers")
    console.print(f"  [dim]Passed    :[/dim]  {passed} contracts across all tickers")
    console.print()


def print_results_table(candidates: List[Candidate]) -> None:
    if not candidates:
        console.print("[red]No candidates passed all filters.[/red]")
        return

    t = Table(
        title="Top CSP Candidates — Ranked by Final Score",
        box=box.SIMPLE_HEAD,
        show_lines=True,
        header_style="bold",
        title_style="bold cyan",
    )

    t.add_column("#",          style="dim",     width=3,  justify="right")
    t.add_column("Ticker",     style="bold",    width=6)
    t.add_column("Strike",     justify="right", width=8)
    t.add_column("DTE",        justify="right", width=4)
    t.add_column("Premium",    justify="right", width=8)
    t.add_column("Delta",      justify="right", width=6)
    t.add_column("IV%",        justify="right", width=6)
    t.add_column("HV%",        justify="right", width=6)
    t.add_column("VRP",        justify="right", width=7)
    t.add_column("IVR*",       justify="right", width=6)
    t.add_column("Yield/yr",   justify="right", width=8)
    t.add_column("Earn days",  justify="right", width=9)
    t.add_column("ProbOTM",    justify="right", width=8)
    t.add_column("BrkEven",    justify="right", width=8)
    t.add_column("Collat.",    justify="right", width=9)
    t.add_column("Juice",      justify="right", width=7)
    t.add_column("Score",      justify="right", width=6)
    t.add_column("Risk",       justify="center",width=7)

    for i, c in enumerate(candidates, 1):
        risk_col = f"[{_risk_color(c.risk_label)}]{c.risk_label}[/]"
        earn_str = str(c.earnings_days) if c.earnings_days else "N/A"

        t.add_row(
            str(i),
            c.ticker,
            _dollar(c.strike),
            str(c.dte),
            _dollar(c.premium),
            f"{c.delta:+.2f}",
            _pct(c.iv),
            _pct(c.hv30),
            _pp(c.vrp),
            f"{c.ivr:.0f}",
            _pct(c.ann_yield),
            earn_str,
            _pct(c.prob_otm),
            _dollar(c.breakeven),
            f"${c.collateral:,.0f}",
            f"{c.juice_score:.4f}",
            f"{c.final_score:.1f}",
            risk_col,
        )

    console.print(t)
    console.print(
        "  [dim]* IVR = HV-rank proxy (rolling 30d HV percentile over 1y). "
        "Full IVR requires options history — verify on your broker.[/dim]"
    )
    console.print()


def print_commentary(candidates: List[Candidate]) -> None:
    console.print(Rule("[bold]Trade Commentary[/bold]", style="dim"))
    console.print()

    for i, c in enumerate(candidates, 1):
        earn_str = (
            f"{c.earnings_days} days" if c.earnings_days else "Not available — verify"
        )
        ivhv_str = f"{c.ivhv_ratio:.2f}x" if c.ivhv_ratio > 0 else "N/A"

        # Trend assessment
        trend_flags = []
        if c.ma50 > 0:
            trend_flags.append(
                f"Price {'above' if c.price > c.ma50 else 'below'} 50d MA (${c.ma50:.2f})"
            )
        if c.ma200 > 0:
            trend_flags.append(
                f"Price {'above' if c.price > c.ma200 else 'below'} 200d MA (${c.ma200:.2f})"
            )
        if c.ma50 > 0 and c.ma200 > 0:
            trend_flags.append(
                f"{'Golden cross ✓' if c.ma50 > c.ma200 else 'Death cross ✗'} (50d vs 200d)"
            )
        trend_str = " · ".join(trend_flags) if trend_flags else "MA data unavailable"

        # Capital warning
        collat_warn = ""
        pct_25k = c.collateral / 25_000 * 100
        if pct_25k > 100:
            collat_warn = f"  ⚠️  IMPOSSIBLE on $25K account ({pct_25k:.0f}% of minimum account)\n"
        elif pct_25k > 25:
            collat_warn = f"  ⚠️  {pct_25k:.0f}% of $25K account — check position sizing\n"

        score_breakdown = (
            f"VRP {c.s_vrp:.0f}×25% + Yield {c.s_yield:.0f}×20% + "
            f"Earn {c.s_earnings:.0f}×15% + Δ {c.s_delta:.0f}×10% + "
            f"IVR {c.s_ivr:.0f}×10% + Cushion {c.s_cushion:.0f}×10% + "
            f"Liq {c.s_liquidity:.0f}×5% + Trend {c.s_trend:.0f}×5% = "
            f"[bold]{c.final_score:.1f}[/bold]"
        )

        text = (
            f"[bold]{i}. {c.ticker}[/bold]  —  "
            f"${c.strike:.2f} Put  /  {c.dte} DTE  /  Exp {c.expiry}  "
            f"[{_risk_color(c.risk_label)}][{c.risk_label} Risk][/]\n\n"
            f"  [cyan]Volatility edge[/cyan]\n"
            f"    IV {_pct(c.iv)} · HV30 {_pct(c.hv30)} · "
            f"VRP {_pp(c.vrp)} · IVHVRatio {ivhv_str} · IVR proxy {c.ivr:.0f}\n\n"
            f"  [cyan]Structure[/cyan]\n"
            f"    Spot ${c.price:.2f} · Strike ${c.strike:.2f} · "
            f"Premium ${c.premium:.2f} · Annualised yield {_pct(c.ann_yield)}\n"
            f"    Expected move ${c.exp_move:.2f} · "
            f"Cushion beyond exp. move {_pct(c.cushion)}\n"
            f"    Break-even ${c.breakeven:.2f} "
            f"({(c.price - c.breakeven)/c.price:.1%} below spot)\n\n"
            f"  [cyan]Earnings[/cyan]\n"
            f"    {earn_str}  ⚠️  Always verify on earnings calendar\n\n"
            f"  [cyan]Execution[/cyan]\n"
            f"    OI {c.oi:,.0f} · Spread {_pct(c.spread_pct)} · "
            f"Collateral ${c.collateral:,.0f}\n"
            f"{collat_warn}"
            f"  [cyan]Trend[/cyan]\n"
            f"    {trend_str}\n\n"
            f"  [cyan]Score breakdown[/cyan]\n"
            f"    {score_breakdown}\n"
        )

        console.print(
            Panel(
                text,
                border_style=_risk_color(c.risk_label),
                padding=(0, 1),
            )
        )
        console.print()


# ── File export ────────────────────────────────────────────────────────────────
def save_csv(candidates: List[Candidate], path: str) -> None:
    if not candidates:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "rank", "ticker", "strike", "dte", "expiry", "premium", "delta",
        "iv_pct", "hv30_pct", "vrp_pp", "ivhv_ratio", "ivr_proxy",
        "ann_yield_pct", "earnings_days", "prob_otm_pct", "breakeven",
        "collateral", "exp_move", "cushion_pct", "oi", "spread_pct",
        "juice_score", "final_score", "risk",
        "s_vrp", "s_yield", "s_earnings", "s_delta",
        "s_ivr", "s_cushion", "s_liquidity", "s_trend",
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i, c in enumerate(candidates, 1):
            w.writerow({
                "rank": i, "ticker": c.ticker,
                "strike": c.strike, "dte": c.dte, "expiry": c.expiry,
                "premium": round(c.premium, 4),
                "delta": round(c.delta, 4),
                "iv_pct": round(c.iv * 100, 2),
                "hv30_pct": round(c.hv30 * 100, 2),
                "vrp_pp": round(c.vrp, 2),
                "ivhv_ratio": round(c.ivhv_ratio, 3),
                "ivr_proxy": round(c.ivr, 1),
                "ann_yield_pct": round(c.ann_yield * 100, 2),
                "earnings_days": c.earnings_days,
                "prob_otm_pct": round(c.prob_otm * 100, 2),
                "breakeven": round(c.breakeven, 2),
                "collateral": c.collateral,
                "exp_move": round(c.exp_move, 2),
                "cushion_pct": round(c.cushion * 100, 2),
                "oi": int(c.oi),
                "spread_pct": round(c.spread_pct * 100, 3),
                "juice_score": round(c.juice_score, 6),
                "final_score": round(c.final_score, 2),
                "risk": c.risk_label,
                "s_vrp": c.s_vrp, "s_yield": c.s_yield,
                "s_earnings": c.s_earnings, "s_delta": c.s_delta,
                "s_ivr": c.s_ivr, "s_cushion": c.s_cushion,
                "s_liquidity": c.s_liquidity, "s_trend": c.s_trend,
            })
    console.print(f"  [dim]CSV saved → {path}[/dim]")


def save_json(candidates: List[Candidate], path: str) -> None:
    if not candidates:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = []
    for i, c in enumerate(candidates, 1):
        data.append({
            "rank": i, "ticker": c.ticker,
            "strike": c.strike, "dte": c.dte, "expiry": c.expiry,
            "premium": round(c.premium, 4),
            "delta": round(c.delta, 4),
            "iv_pct": round(c.iv * 100, 2),
            "hv30_pct": round(c.hv30 * 100, 2),
            "vrp_pp": round(c.vrp, 2),
            "ivhv_ratio": round(c.ivhv_ratio, 3),
            "ivr_proxy": round(c.ivr, 1),
            "ann_yield_pct": round(c.ann_yield * 100, 2),
            "earnings_days": c.earnings_days,
            "prob_otm_pct": round(c.prob_otm * 100, 2),
            "breakeven": round(c.breakeven, 2),
            "collateral": c.collateral,
            "exp_move": round(c.exp_move, 2),
            "cushion_pct": round(c.cushion * 100, 2),
            "oi": int(c.oi),
            "spread_pct": round(c.spread_pct * 100, 3),
            "juice_score": round(c.juice_score, 6),
            "final_score": round(c.final_score, 2),
            "risk": c.risk_label,
            "score_breakdown": {
                "vrp": c.s_vrp, "yield": c.s_yield,
                "earnings": c.s_earnings, "delta": c.s_delta,
                "ivr": c.s_ivr, "cushion": c.s_cushion,
                "liquidity": c.s_liquidity, "trend": c.s_trend,
            },
        })
    with open(path, "w") as f:
        json.dump({"generated": datetime.datetime.now().isoformat(), "results": data}, f, indent=2)
    console.print(f"  [dim]JSON saved → {path}[/dim]")
