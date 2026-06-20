#!/usr/bin/env python3
"""
run.py — Main entry point for the Institutional CSP Screener.

Usage:
    python run.py                        # quick scan, top 10
    python run.py --tier full            # full Russell 1000 scan
    python run.py --tier quick --top 5   # quick scan, top 5
    python run.py --account 100000       # override account size
    python run.py --no-csv --no-json     # terminal only
"""

import argparse
import datetime
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

load_dotenv(".env")

from screener.universe import get_universe
from screener.data import StockData
from screener.scorer import screen_ticker
from screener.output import (
    print_header, print_results_table, print_commentary,
    save_csv, save_json,
)
from screener.html_report import save_html_report

console = Console()


# ── VIX fetch ──────────────────────────────────────────────────────────────────
def fetch_vix() -> tuple[float, str]:
    """Fetch VIX from yfinance. Returns (value, regime)."""
    try:
        import yfinance as yf
        vix = yf.Ticker("^VIX")
        hist = vix.history(period="2d")
        if not hist.empty:
            val = float(hist["Close"].iloc[-1])
            if val <= 20:
                regime = "Normal"
            elif val <= 25:
                regime = "Elevated"
            else:
                regime = "Override Active (MaxDelta→0.15, MinIVR→50)"
            return val, regime
    except Exception:
        pass
    return 20.0, "Normal (VIX unavailable — defaulting to Normal)"


# ── Per-ticker worker ──────────────────────────────────────────────────────────
def process_ticker(
    ticker: str,
    config: dict,
) -> tuple[str, list, list, str | None]:
    """Fetch data + screen one ticker. Returns (ticker, candidates, rejections, fetch_error)."""
    try:
        sd = StockData(ticker).fetch(
            dte_min=config["target_dte_min"],
            dte_max=config["target_dte_max"],
        )
        if not sd.valid:
            return ticker, [], [], sd.error
        candidates, rejections = screen_ticker(sd, config)
        return ticker, candidates, rejections, None
    except Exception as e:
        return ticker, [], [], str(e)


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Institutional CSP Screener")
    parser.add_argument("--tier",     default="quick",
                        choices=["quick", "full", "tier1", "tier2", "tier3"],
                        help="Universe tier to scan (default: quick)")
    parser.add_argument("--top",      type=int, default=None,
                        help="Number of top candidates to show (default: from .env or 10)")
    parser.add_argument("--account",  type=float, default=None,
                        help="Account size in USD (default: from .env or 50000)")
    parser.add_argument("--workers",  type=int, default=8,
                        help="Parallel fetch workers (default: 8)")
    parser.add_argument("--no-csv",   action="store_true", help="Skip CSV output")
    parser.add_argument("--no-json",  action="store_true", help="Skip JSON output")
    parser.add_argument("--no-html",  action="store_true", help="Skip HTML report")
    parser.add_argument("--no-commentary", action="store_true",
                        help="Skip per-trade commentary")
    args = parser.parse_args()

    # ── Build config from .env + CLI overrides ─────────────────────────────
    config = {
        "account_size":       args.account or float(os.getenv("ACCOUNT_SIZE", 50_000)),
        "max_position_pct":   float(os.getenv("MAX_POSITION_PCT", 0.25)),
        "target_dte_min":     int(os.getenv("TARGET_DTE_MIN", 21)),
        "target_dte_max":     int(os.getenv("TARGET_DTE_MAX", 45)),
        "min_ivr":            float(os.getenv("MIN_IVR", 30)),
        "min_prob_otm":       float(os.getenv("MIN_PROB_OTM", 0.75)),
        "min_annual_yield":   float(os.getenv("MIN_ANNUAL_YIELD", 0.15)),
        "min_avg_volume":     float(os.getenv("MIN_AVG_VOLUME", 2_000_000)),
        "min_oi":             int(os.getenv("MIN_OI", 1000)),
        "max_spread_pct":     float(os.getenv("MAX_SPREAD_PCT", 0.07)),
        "min_earnings_days":  int(os.getenv("MIN_EARNINGS_DAYS", 14)),
        "top_n":              args.top or int(os.getenv("TOP_N", 10)),
        "max_per_ticker":     int(os.getenv("MAX_PER_TICKER", 1)),
        "output_dir":         os.getenv("OUTPUT_DIR", "output"),
        "save_csv":           os.getenv("SAVE_CSV", "true").lower() == "true",
        "save_json":          os.getenv("SAVE_JSON", "true").lower() == "true",
        "save_html":          os.getenv("SAVE_HTML", "true").lower() == "true",
    }

    # ── VIX & macro override ───────────────────────────────────────────────
    vix, regime = fetch_vix()
    if vix > 25:
        console.print("[yellow]⚠ Macro override active: VIX > 25. "
                      "Tightening delta to 0.15 and IVR to 50.[/yellow]")
        config["max_delta_override"] = 0.15
        config["min_ivr"] = max(config["min_ivr"], 50)

    # ── Universe ───────────────────────────────────────────────────────────
    tickers = get_universe(args.tier)
    console.print(f"\n[bold]Scanning {len(tickers)} tickers ({args.tier} tier)...[/bold]\n")

    # ── Parallel fetch + screen ────────────────────────────────────────────
    all_candidates = []
    errors = {}
    all_rejections = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching data...", total=len(tickers))

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(process_ticker, t, config): t
                for t in tickers
            }
            for future in as_completed(futures):
                ticker, candidates, rejections, error = future.result()
                if error:
                    errors[ticker] = error
                else:
                    all_candidates.extend(candidates)
                    all_rejections.extend(rejections)
                progress.advance(task)

    # ── Rank, diversify, & truncate ─────────────────────────────────────────
    all_candidates.sort(
        key=lambda c: (c.final_score, c.juice_score),
        reverse=True,
    )

    # Keep only the single best-scoring contract per ticker. Without this,
    # one ticker with several strikes passing filters (or a data anomaly
    # inflating its score) can crowd out every other name in the Top N —
    # which defeats the purpose of a diversified candidate list.
    max_per_ticker = config.get("max_per_ticker", 1)
    seen_count: dict[str, int] = {}
    diversified = []
    for c in all_candidates:
        n = seen_count.get(c.ticker, 0)
        if n < max_per_ticker:
            diversified.append(c)
            seen_count[c.ticker] = n + 1

    top = diversified[:config["top_n"]]

    # ── Aggregate rejection reasons for diagnosis ────────────────────────────
    # Bucket by the filter that caused the rejection (the text before the
    # first colon-delimited clause) so "0 results" becomes a readable
    # breakdown instead of a wall of per-contract text.
    rejection_summary: dict[str, int] = {}
    for r in all_rejections:
        # r looks like "TICKER $strike: <reason text>"
        reason_text = r.split(":", 1)[-1].strip() if ":" in r else r
        # Collapse to the leading clause (the filter name), drop the
        # specific numbers so similar rejections group together
        key = reason_text.split(" ", 1)[0] if reason_text else "unknown"
        # Use a slightly longer key for readability on a few common cases
        if "earnings" in reason_text.lower():
            key = "earnings date unconfirmed / too close"
        elif "VRP" in reason_text:
            key = "no volatility edge (IV below realized vol)"
        elif "delta" in reason_text.lower():
            key = "delta outside target range"
        elif "spread" in reason_text.lower():
            key = "bid-ask spread too wide"
        elif "OI" in reason_text:
            key = "open interest too low"
        elif "IVR" in reason_text:
            key = "IV Rank too low"
        elif "yield" in reason_text.lower():
            key = "annualized yield too low"
        elif "collateral" in reason_text.lower():
            key = "position too large for account"
        elif "prob OTM" in reason_text:
            key = "probability OTM too low"
        rejection_summary[key] = rejection_summary.get(key, 0) + 1

    # ── Output ─────────────────────────────────────────────────────────────
    print_header(
        vix_est  = vix,
        regime   = regime,
        scanned  = len(tickers),
        passed   = len(all_candidates),
    )

    if not top:
        console.print("[red bold]No candidates passed all filters.[/red bold]")
        if rejection_summary:
            console.print("\n[bold]Why nothing qualified:[/bold]")
            for reason, count in sorted(rejection_summary.items(), key=lambda x: -x[1]):
                console.print(f"  [dim]{count:>4}x[/dim]  {reason}")
        if errors:
            console.print(
                f"\n[dim]Tickers with errors ({len(errors)}): "
                f"{', '.join(list(errors.keys())[:10])}{'...' if len(errors) > 10 else ''}[/dim]"
            )
    else:
        print_results_table(top)
        if not args.no_commentary:
            print_commentary(top)

    # ── Save files ─────────────────────────────────────────────────────────
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir   = config["output_dir"]

    if top:
        if config["save_csv"] and not args.no_csv:
            save_csv(top, f"{out_dir}/csp_results_{timestamp}.csv")

        if config["save_json"] and not args.no_json:
            save_json(top, f"{out_dir}/csp_results_{timestamp}.json")

    if config["save_html"] and not args.no_html:
        html_path = f"{out_dir}/report.html"   # fixed filename — easy to find/link
        save_html_report(
            candidates         = top,
            vix                = vix,
            regime             = regime,
            scanned            = len(tickers),
            passed             = len(all_candidates),
            account_size       = config["account_size"],
            path               = html_path,
            errors             = errors,
            rejection_summary  = rejection_summary,
        )
        console.print(f"  [dim]HTML report saved → {html_path}[/dim]")

    # ── Error summary (optional) ───────────────────────────────────────────
    if errors:
        console.print(
            f"\n  [dim]Skipped {len(errors)} tickers (no data / filtered at fetch).[/dim]"
        )


if __name__ == "__main__":
    main()
