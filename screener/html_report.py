"""
html_report.py — Generates a self-contained HTML report of screener results.

No external dependencies, no build step. Opens directly in any browser.
Designed to be the artifact GitHub Actions uploads after each manual run.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import List

from .scorer import Candidate


def _risk_color(risk: str) -> str:
    return {"Low": "#3B6D11", "Medium": "#854F0B", "High": "#A32D2D"}.get(risk, "#444")

def _risk_bg(risk: str) -> str:
    return {"Low": "#EAF3DE", "Medium": "#FAEEDA", "High": "#FCEBEB"}.get(risk, "#F1EFE8")


def generate_html_report(
    candidates: List[Candidate],
    vix: float,
    regime: str,
    scanned: int,
    passed: int,
    account_size: float,
    errors: dict | None = None,
    rejection_summary: dict | None = None,
) -> str:
    """Returns a complete HTML document as a string."""

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    errors = errors or {}
    rejection_summary = rejection_summary or {}

    # ── Table rows ──────────────────────────────────────────────────────────
    rows_html = ""
    for i, c in enumerate(candidates, 1):
        earn_str = str(c.earnings_days) if c.earnings_days else "N/A"
        risk_color = _risk_color(c.risk_label)
        risk_bg = _risk_bg(c.risk_label)

        rows_html += f"""
        <tr>
          <td class="num">{i}</td>
          <td class="ticker">{c.ticker}</td>
          <td class="num">${c.strike:,.2f}</td>
          <td class="num">{c.dte}</td>
          <td class="num">${c.premium:,.2f}</td>
          <td class="num">{c.delta:+.2f}</td>
          <td class="num">{c.iv*100:.1f}%</td>
          <td class="num">{c.hv30*100:.1f}%</td>
          <td class="num">{c.vrp:+.1f}</td>
          <td class="num">{c.ivr:.0f}</td>
          <td class="num">{c.ann_yield*100:.1f}%</td>
          <td class="num">{earn_str}</td>
          <td class="num">{c.prob_otm*100:.1f}%</td>
          <td class="num">${c.breakeven:,.2f}</td>
          <td class="num">${c.collateral:,.0f}</td>
          <td class="num">{c.juice_score:.4f}</td>
          <td class="num score">{c.final_score:.1f}</td>
          <td><span class="risk-pill" style="color:{risk_color};background:{risk_bg}">{c.risk_label}</span></td>
        </tr>"""

    # ── Commentary cards ────────────────────────────────────────────────────
    commentary_html = ""
    for i, c in enumerate(candidates, 1):
        earn_str = f"{c.earnings_days} days" if c.earnings_days else "Not available — verify before entry"
        ivhv_str = f"{c.ivhv_ratio:.2f}x" if c.ivhv_ratio > 0 else "N/A"
        risk_color = _risk_color(c.risk_label)
        risk_bg = _risk_bg(c.risk_label)

        trend_flags = []
        if c.ma50 > 0:
            trend_flags.append(f"Price {'above' if c.price > c.ma50 else 'below'} 50d MA (${c.ma50:.2f})")
        if c.ma200 > 0:
            trend_flags.append(f"Price {'above' if c.price > c.ma200 else 'below'} 200d MA (${c.ma200:.2f})")
        if c.ma50 > 0 and c.ma200 > 0:
            trend_flags.append(f"{'Golden cross' if c.ma50 > c.ma200 else 'Death cross'} (50d vs 200d)")
        trend_str = " · ".join(trend_flags) if trend_flags else "MA data unavailable"

        pct_25k = c.collateral / 25_000 * 100
        collat_warn = ""
        if pct_25k > 100:
            collat_warn = f'<div class="warn">⚠ Collateral exceeds $25K minimum account ({pct_25k:.0f}% of it)</div>'
        elif pct_25k > 25:
            collat_warn = f'<div class="warn">⚠ {pct_25k:.0f}% of a $25K account — check position sizing</div>'

        commentary_html += f"""
        <div class="card" style="border-left: 3px solid {risk_color}">
          <div class="card-header">
            <span class="card-rank">{i}</span>
            <span class="card-ticker">{c.ticker}</span>
            <span class="card-detail">${c.strike:.2f} Put · {c.dte} DTE · Exp {c.expiry}</span>
            <span class="risk-pill" style="color:{risk_color};background:{risk_bg}">{c.risk_label} Risk</span>
          </div>
          <div class="card-grid">
            <div class="card-section">
              <h4>Volatility edge</h4>
              <p>IV {c.iv*100:.1f}% · HV30 {c.hv30*100:.1f}% · VRP {c.vrp:+.1f}pp · IVHVRatio {ivhv_str} · IVR proxy {c.ivr:.0f}</p>
            </div>
            <div class="card-section">
              <h4>Structure</h4>
              <p>Spot ${c.price:.2f} · Premium ${c.premium:.2f} · Annualized yield {c.ann_yield*100:.1f}%</p>
              <p>Expected move ${c.exp_move:.2f} · Cushion vs. expected move {c.cushion*100:.1f}% (negative = strike inside the market's expected range) · Break-even ${c.breakeven:.2f}</p>
            </div>
            <div class="card-section">
              <h4>Earnings</h4>
              <p>{earn_str} — always verify on earnings calendar before entry</p>
            </div>
            <div class="card-section">
              <h4>Execution</h4>
              <p>OI {c.oi:,.0f} · Spread {c.spread_pct*100:.2f}% · Collateral ${c.collateral:,.0f}</p>
              {collat_warn}
            </div>
            <div class="card-section">
              <h4>Trend</h4>
              <p>{trend_str}</p>
            </div>
            <div class="card-section">
              <h4>Score breakdown</h4>
              <p>VRP {c.s_vrp:.0f}×25 + Yield {c.s_yield:.0f}×20 + Earn {c.s_earnings:.0f}×15 + Δ {c.s_delta:.0f}×10 + IVR {c.s_ivr:.0f}×10 + Cushion {c.s_cushion:.0f}×10 + Liq {c.s_liquidity:.0f}×5 + Trend {c.s_trend:.0f}×5 = <b>{c.final_score:.1f}</b></p>
            </div>
          </div>
        </div>"""

    error_html = ""
    if errors:
        error_list = "".join(f"<li><code>{t}</code> — {e}</li>" for t, e in list(errors.items())[:20])
        error_html = f"""
        <details class="errors">
          <summary>{len(errors)} tickers skipped (no data / fetch error)</summary>
          <ul>{error_list}</ul>
        </details>"""

    rejection_html = ""
    if rejection_summary:
        sorted_reasons = sorted(rejection_summary.items(), key=lambda x: -x[1])
        rows = "".join(
            f'<div class="reject-row"><span class="reject-count">{count}×</span>'
            f'<span class="reject-label">{reason}</span></div>'
            for reason, count in sorted_reasons
        )
        rejection_html = f"""
        <div class="reject-box">
          <h3>Why nothing qualified</h3>
          <p class="reject-intro">Every contract that was evaluated failed at least one hard filter below. Counts are per-contract, not per-ticker — one ticker can contribute several rejected strikes.</p>
          {rows}
        </div>"""

    empty_state = ""
    if not candidates:
        empty_state = (
            '<div class="empty">No candidates passed all filters on this run. '
            'This can be a legitimate finding on a calm/low-volatility day — '
            'see the breakdown below for exactly why.</div>'
            + rejection_html
        )

    regime_class = "regime-override" if "Override" in regime else ("regime-elevated" if "Elevated" in regime else "regime-normal")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CSP Screener Report — {now}</title>
<style>
  :root {{
    --bg: #ffffff; --bg2: #f7f6f3; --text: #1a1a18; --text2: #5f5e5a;
    --border: #e5e3da; --accent: #185fa5;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#1a1a18; --bg2:#242422; --text:#e8e6dd; --text2:#a8a69c; --border:#3a3936; --accent:#85b7eb; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text); margin: 0; padding: 2rem 1.5rem 4rem;
    line-height: 1.5;
  }}
  .wrap {{ max-width: 1400px; margin: 0 auto; }}
  h1 {{ font-size: 22px; font-weight: 600; margin: 0 0 4px; }}
  .subtitle {{ color: var(--text2); font-size: 14px; margin-bottom: 1.5rem; }}
  .meta-bar {{
    display: flex; flex-wrap: wrap; gap: 1.5rem; background: var(--bg2);
    border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.25rem;
    margin-bottom: 2rem; font-size: 13px;
  }}
  .meta-item {{ display: flex; flex-direction: column; gap: 2px; }}
  .meta-label {{ color: var(--text2); font-size: 11px; text-transform: uppercase; letter-spacing: .05em; }}
  .meta-value {{ font-weight: 600; }}
  .regime-normal .meta-value {{ color: #3B6D11; }}
  .regime-elevated .meta-value {{ color: #854F0B; }}
  .regime-override .meta-value {{ color: #A32D2D; }}

  table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; margin-bottom: 2.5rem; }}
  thead th {{
    text-align: right; padding: 8px 10px; background: var(--bg2);
    border-bottom: 2px solid var(--border); font-weight: 600; white-space: nowrap;
    position: sticky; top: 0;
  }}
  thead th:nth-child(2), thead th:first-child {{ text-align: left; }}
  tbody td {{ padding: 7px 10px; border-bottom: 1px solid var(--border); }}
  tbody tr:hover {{ background: var(--bg2); }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.ticker {{ font-weight: 600; }}
  td.score {{ font-weight: 700; color: var(--accent); }}
  .risk-pill {{
    display: inline-block; padding: 2px 9px; border-radius: 20px;
    font-size: 11px; font-weight: 600;
  }}

  .card {{
    background: var(--bg2); border: 1px solid var(--border); border-radius: 10px;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
  }}
  .card-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: .75rem; flex-wrap: wrap; }}
  .card-rank {{ color: var(--text2); font-weight: 600; }}
  .card-ticker {{ font-size: 17px; font-weight: 700; }}
  .card-detail {{ color: var(--text2); font-size: 13px; flex: 1; }}
  .card-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: .9rem; }}
  .card-section h4 {{
    font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
    color: var(--text2); margin: 0 0 4px; font-weight: 600;
  }}
  .card-section p {{ font-size: 13px; margin: 0 0 4px; }}
  .warn {{ color: #A32D2D; font-size: 12px; font-weight: 600; margin-top: 4px; }}

  .empty {{ padding: 2rem; text-align: center; color: var(--text2); background: var(--bg2); border-radius: 10px 10px 0 0; }}
  .reject-box {{ background: var(--bg2); border-radius: 0 0 10px 10px; padding: 1.25rem 1.5rem 1.5rem; border-top: 1px solid var(--border); }}
  .reject-box h3 {{ font-size: 14px; margin: 0 0 6px; }}
  .reject-intro {{ font-size: 12px; color: var(--text2); margin: 0 0 1rem; }}
  .reject-row {{ display: flex; gap: 10px; padding: 5px 0; font-size: 13px; border-bottom: 1px solid var(--border); }}
  .reject-row:last-child {{ border-bottom: none; }}
  .reject-count {{ color: var(--accent); font-weight: 600; min-width: 38px; font-variant-numeric: tabular-nums; }}
  .reject-label {{ color: var(--text); }}

  details.errors {{ margin-top: 2rem; font-size: 13px; color: var(--text2); }}
  details.errors summary {{ cursor: pointer; padding: 8px 0; }}
  details.errors ul {{ columns: 3; gap: 1.5rem; }}
  details.errors code {{ font-weight: 600; color: var(--text); }}

  .footer {{ margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid var(--border); color: var(--text2); font-size: 12px; }}

  @media (max-width: 900px) {{
    table {{ font-size: 11px; }}
    thead th, tbody td {{ padding: 5px 6px; }}
    details.errors ul {{ columns: 1; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Institutional CSP Screener Report</h1>
  <div class="subtitle">Generated {now}</div>

  <div class="meta-bar {regime_class}">
    <div class="meta-item"><span class="meta-label">VIX</span><span class="meta-value">{vix:.2f}</span></div>
    <div class="meta-item"><span class="meta-label">Regime</span><span class="meta-value">{regime}</span></div>
    <div class="meta-item"><span class="meta-label">Tickers scanned</span><span class="meta-value">{scanned}</span></div>
    <div class="meta-item"><span class="meta-label">Contracts passed</span><span class="meta-value">{passed}</span></div>
    <div class="meta-item"><span class="meta-label">Account size</span><span class="meta-value">${account_size:,.0f}</span></div>
    <div class="meta-item"><span class="meta-label">Showing</span><span class="meta-value">Top {len(candidates)}</span></div>
  </div>

  {empty_state}

  {"<table><thead><tr>"
    "<th>#</th><th>Ticker</th><th>Strike</th><th>DTE</th><th>Premium</th><th>Delta</th>"
    "<th>IV%</th><th>HV%</th><th>VRP</th><th>IVR*</th><th>Yield/yr</th><th>Earn days</th>"
    "<th>ProbOTM</th><th>BrkEven</th><th>Collateral</th><th>Juice</th><th>Score</th><th>Risk</th>"
    "</tr></thead><tbody>" + rows_html + "</tbody></table>" if candidates else ""}

  {f'<p style="color:var(--text2);font-size:12px;margin-top:-1.5rem">* IVR = rolling-HV percentile proxy (not true options-based IV Rank) — verify on your broker before trading.</p>' if candidates else ""}

  {f'<h2 style="font-size:18px;margin:2rem 0 1rem">Trade commentary</h2>{commentary_html}' if candidates else ""}

  {error_html}

  <div class="footer">
    Data source: yfinance (Yahoo Finance, ~15min delayed) · Educational use only · Not financial advice<br>
    Always verify earnings dates, open interest, and bid-ask spreads on your broker before placing a trade.
  </div>
</div>
</body>
</html>"""


def save_html_report(
    candidates: List[Candidate],
    vix: float,
    regime: str,
    scanned: int,
    passed: int,
    account_size: float,
    path: str,
    errors: dict | None = None,
    rejection_summary: dict | None = None,
) -> None:
    html = generate_html_report(
        candidates, vix, regime, scanned, passed, account_size,
        errors, rejection_summary,
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(html, encoding="utf-8")
