# CSP Options Screener

An institutional-grade **Cash Secured Put** screener for premium harvesting and Wheel Strategy entries. Connects to live market data, scores candidates across 8 quantitative factors, and outputs a ranked Top 10 table with full trade commentary.

---

## What It Does

- Scans S&P 500, Nasdaq 100, Russell 1000, and liquid ETFs
- Applies hard rejection filters (price, volume, OI, spread, IVR, delta, earnings, DTE)
- Scores every passing candidate across 8 weighted factors (VRP, yield, earnings distance, delta, IVR, expected move cushion, liquidity, trend)
- Computes a Juice Score tiebreaker
- Detects macro regime (VIX) and applies conservative overrides when VIX > 25
- Outputs a clean ranked table + per-trade commentary to terminal and CSV

---

## Strategy Profile

| Parameter | Value |
|-----------|-------|
| Account size | $25,000 – $100,000 |
| Style | 80% premium harvest / 20% Wheel entry |
| Target DTE | 21 – 45 days |
| Target delta | 0.10 – 0.20 |
| Max position size | 25% of account |

---

## Data Sources

The screener uses **[Polygon.io](https://polygon.io)** for:
- Real-time and delayed quotes
- Options chains (bid/ask/IV/delta/OI/volume)
- Historical price data (for HV and MA calculations)
- Options snapshots (IV surface)

And **[Earnings Whispers](https://www.earningswhispers.com)** or **Polygon earnings calendar** for confirmed earnings dates.

### API Keys Required

```
POLYGON_API_KEY=your_key_here
```

Free tier works for end-of-day data. Starter tier ($29/mo) enables real-time options chains.

---

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/csp-screener.git
cd csp-screener
pip install -r requirements.txt
cp config/config.example.yaml config/config.yaml
# Add your API key to config/config.yaml
python src/main.py
```

---

## Output

```
══════════════════════════════════════════════════════════════════
 CSP SCREENER  |  2025-01-15 09:32:14 ET  |  VIX: 18.42  NORMAL
══════════════════════════════════════════════════════════════════
 Scanned: 1,247 tickers  |  Passed filters: 34  |  Showing Top 10
══════════════════════════════════════════════════════════════════

Rank  Ticker  Strike    DTE  Premium  Delta   IVR   VRP  AnnYield  EarnDays  ProbOTM  BreakEven  Collateral  JuiceScore  FinalScore  Risk
───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
   1  NVDA    $195.00    28   $4.12  -0.158  68.4  +9.3    27.1%        52     84.2%    $190.88      $19,500      0.1821       87.3    Medium
   2  AMD     $138.00    28   $3.05  -0.147  61.2  +8.1    24.9%        44     85.3%    $134.95      $13,800      0.1654       84.1    Low
...

Results saved to output/csp_screen_2025-01-15.csv
```

---

## Project Structure

```
csp-screener/
├── src/
│   ├── main.py              # Entry point
│   ├── screener.py          # Core screening logic
│   ├── data/
│   │   ├── polygon_client.py    # Polygon.io API wrapper
│   │   ├── universe.py          # Ticker universe management
│   │   └── earnings.py          # Earnings calendar fetcher
│   ├── scoring/
│   │   ├── filters.py           # Hard rejection filters
│   │   ├── factors.py           # 8 scoring factors
│   │   ├── regime.py            # VIX regime detection
│   │   └── juice.py             # Juice Score + final ranking
│   └── output/
│       ├── formatter.py         # Terminal table output
│       └── exporter.py          # CSV/JSON export
├── config/
│   ├── config.example.yaml  # Config template
│   └── universe_lists.py    # SP500/NDX100/R1000 ticker lists
├── tests/
│   ├── test_filters.py
│   ├── test_scoring.py
│   └── test_data_mock.py
├── output/                  # Generated output files (gitignored)
├── docs/
│   └── scoring_spec.md      # Full scoring methodology
├── requirements.txt
└── README.md
```

---

## Configuration

Edit `config/config.yaml`:

```yaml
api:
  polygon_key: "YOUR_KEY_HERE"
  data_mode: "live"          # live | delayed | backtest

account:
  size: 50000                # Your account size in USD
  max_position_pct: 0.25     # Max 25% per position

filters:
  min_stock_price: 20
  min_avg_volume: 2000000
  min_option_oi: 1000
  max_spread_pct: 0.07
  min_ivr: 30
  max_delta: 0.25
  min_earnings_days: 14
  min_prob_otm: 0.75
  dte_min: 7
  dte_max: 60

scoring:
  vrp_weight: 0.25
  yield_weight: 0.20
  earnings_weight: 0.15
  delta_weight: 0.10
  ivr_weight: 0.10
  cushion_weight: 0.10
  liquidity_weight: 0.05
  trend_weight: 0.05

output:
  top_n: 10
  save_csv: true
  save_json: false
  output_dir: "./output"
```

---

## Scoring Methodology

Full specification in [`docs/scoring_spec.md`](docs/scoring_spec.md).

| Factor | Formula | Weight |
|--------|---------|--------|
| VRP | IV − HV | 25% |
| Annualized Yield | (Premium/Strike) × (365/DTE) | 20% |
| Earnings Distance | Days to confirmed earnings | 15% |
| Delta Score | \|Delta\| | 10% |
| IV Rank | 52-week IV percentile | 10% |
| Expected Move Cushion | ((Price−Strike)−ExpMove)/Price | 10% |
| Liquidity | OI + Spread + Volume composite | 5% |
| Trend | 50/200 MA conditions | 5% |

---

## Roadmap

- [ ] Polygon.io live data integration
- [ ] Hard filter pipeline
- [ ] 8-factor scoring engine
- [ ] VIX regime detection
- [ ] Terminal output + CSV export
- [ ] Backtest mode (historical IV data)
- [ ] Tastytrade API alternative data source
- [ ] Web dashboard (Streamlit)
- [ ] Email/Slack alerts for new opportunities

---

## Disclaimer

This tool is for research and educational purposes. It does not constitute financial advice. All trading involves risk. Verify all data independently before committing capital.

---

## License

MIT
