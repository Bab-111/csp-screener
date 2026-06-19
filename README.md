# Institutional CSP Screener

A real, runnable Cash Secured Put screener that pulls **live market data** via yfinance, applies institutional-grade filters, scores every eligible put contract using a quantitative framework, and outputs a ranked table — as an HTML report and a terminal table.

No estimated values. No invented numbers. Real data or nothing.

---

## Two ways to run this

### Option A — On GitHub, click a button (no install)

1. Push this repo to GitHub
2. Go to the **Actions** tab → click **Run CSP Screener** in the sidebar
3. Click **Run workflow** (top right) — pick tier, top N, account size → **Run workflow**
4. Wait 1–10 minutes depending on tier
5. See results two ways:
   - **HTML page**: `https://YOUR_USERNAME.github.io/REPO_NAME/` (auto-updates after every run)
   - **Downloadable files**: open the completed run → **Artifacts** section → download HTML/CSV/JSON

**One-time setup** for the HTML page: repo **Settings → Pages** → Source = "Deploy from a branch" → branch = `gh-pages` / `(root)` → Save. (The `gh-pages` branch is created automatically the first time the workflow runs — just re-check this setting after your first run.)

### Option B — On your own computer

```bash
git clone https://github.com/YOUR_USERNAME/csp-screener.git
cd csp-screener
pip install -r requirements.txt
cp .env.example .env          # edit ACCOUNT_SIZE etc.
python run.py                  # quick scan, ~40 tickers, ~2 min
```

Both options run identical code — same filters, same scoring, same output format.

---

## What it does

1. Fetches live option chains, prices, volume, IV, and earnings dates for 40–100 tickers
2. Applies hard rejection filters (delta, IV rank, earnings distance, spread, OI, collateral)
3. Scores every passing contract across 8 weighted factors
4. Ranks by Final Score, breaks ties with Juice Score
5. Outputs an HTML report (`output/report.html`) and a Rich terminal table
6. Saves CSV and JSON for further analysis

---

## Scoring framework

| Factor | Formula | Weight |
|--------|---------|--------|
| Volatility Risk Premium | IV − HV | 25% |
| Annualized Yield | (Premium/Strike) × (365/DTE) | 20% |
| Earnings Distance | Days to confirmed earnings | 15% |
| Delta Score | \|Δ\| | 10% |
| IV Rank (proxy) | Rolling HV percentile | 10% |
| Expected Move Cushion | ((Spot−Strike)−ExpMove)/Spot | 10% |
| Liquidity | OI + spread + volume composite | 5% |
| Trend | 50d/200d MA conditions | 5% |

**Juice Score** (tiebreaker): `(VRP × AnnYield × ProbOTM) / |Delta|`

---

## CLI options (Option B)

```
--tier       quick | full | tier1 | tier2 | tier3   (default: quick)
--top        N candidates to show                    (default: 10)
--account    Account size in USD                     (default: .env)
--workers    Parallel fetch threads                  (default: 8)
--no-csv     Skip CSV output
--no-json    Skip JSON output
--no-html    Skip HTML report
--no-commentary  Table only, skip per-trade text
```

---

## Output

### HTML report (`output/report.html`)
Self-contained file — open directly in any browser. Includes the meta bar (VIX, regime, scan stats), the full ranked table, and a per-trade commentary card for every candidate. Works in light and dark mode automatically.

### Terminal table (Rich)
```
  #  Ticker  Strike   DTE  Premium  Delta    IV%   HV%    VRP    IVR*  Yield/yr  Earn  ProbOTM  BrkEven  Collat.  Juice  Score  Risk
  1  NVDA    $185.00   30   $3.42   -0.15   48.2%  38.1%  +10.1  61     26.3%    52    85.0%    $181.58  $18,500  0.112   81.5  Medium
```

### Files saved to `output/`
- `report.html` — fixed filename, always overwritten with the latest run
- `csp_results_YYYYMMDD_HHMMSS.csv` — timestamped, importable to Excel
- `csp_results_YYYYMMDD_HHMMSS.json` — timestamped, includes score breakdown

---

## Data source notes

| Field | Source | Notes |
|-------|--------|-------|
| Stock price | yfinance (Yahoo Finance) | ~15 min delayed |
| Options chain | yfinance | Bid/ask/OI/IV from Yahoo |
| IV | yfinance `impliedVolatility` | Per-contract |
| HV30 | Computed from 2y daily OHLCV | 30-day log-return std × √252 |
| IV Rank | **HV proxy** — rolling 30d HV percentile over 1 year | ⚠️ Not true IV Rank |
| Earnings date | yfinance `calendar` | Not always populated — verify |
| 50d / 200d MA | Computed from price history | |
| VIX | yfinance `^VIX` | Used for macro regime check |

### ⚠️ IVR proxy note
True IV Rank requires a database of historical option IV (52-week IV high and low). yfinance doesn't provide this. The screener uses a **rolling realized-HV percentile** as a proxy. For production-grade IVR, swap `screener/data.py` for a Tradier or Polygon options-history call.

### Earnings dates
yfinance calendar data is often missing or approximate. **Always verify the next earnings date before entering a trade.**

---

## Project structure

```
csp-screener/
├── .github/
│   └── workflows/
│       └── run-screener.yml   # GitHub Actions — manual "Run workflow" button
├── run.py                     # Entry point
├── requirements.txt
├── .env.example                # Copy to .env for local runs
├── screener/
│   ├── __init__.py
│   ├── universe.py             # Ticker lists (Tier 1/2/3)
│   ├── data.py                  # yfinance fetcher + Black-Scholes helpers
│   ├── scorer.py                 # Hard filters + scoring engine
│   ├── output.py                  # Rich terminal output + CSV/JSON export
│   └── html_report.py              # Self-contained HTML report generator
├── output/                     # Results saved here (gitignored except via Actions)
└── tests/
    └── test_scorer.py          # 36 unit tests
```

---

## Hard filter reference

| Filter | Default | Config key |
|--------|---------|-----------|
| Stock price | ≥ $20 | — |
| Avg daily volume | ≥ 2M shares | `MIN_AVG_VOLUME` |
| Option OI (contract) | ≥ 1,000 | `MIN_OI` |
| Bid-ask spread | ≤ 7% of mid | `MAX_SPREAD_PCT` |
| IV Rank proxy | ≥ 30 | `MIN_IVR` |
| Delta | ≤ 0.25 | — |
| Days to earnings | ≥ 14 | `MIN_EARNINGS_DAYS` |
| Prob OTM | ≥ 75% | `MIN_PROB_OTM` |
| DTE window | 21–45 days | `TARGET_DTE_MIN/MAX` |
| Annual yield | ≥ 15% | `MIN_ANNUAL_YIELD` |
| Collateral | ≤ 25% of account | `MAX_POSITION_PCT` |

---

## Running tests

```bash
pip install pytest
python -m pytest tests/ -v
```

36/36 tests covering all scoring functions.

---

## Disclaimer

This tool is for research and educational purposes. Nothing here is financial advice. Options trading involves substantial risk. Always verify data independently before committing capital.
