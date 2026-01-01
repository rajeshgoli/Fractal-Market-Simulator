# Test Data Freshness

Backtest data for ES, NQ, YM, and DAX is kept fresh via automated Databento API pulls. This document covers data locations, formats, and the refresh workflow.

---

## Data Coverage

### Authoritative Location

`~/Documents/backtest-data/` — All data lives here. `test_data/` contains symlinks.

### ES (E-mini S&P 500)

| Timeframe | Bars | Range | Source |
|-----------|------|-------|--------|
| 1m | 6,531,249 | Apr 2007 → Dec 31, 2025 | Original + Databento gap fill |
| 5m | 1,322,855 | Apr 2007 → Dec 31, 2025 | Aggregated from 1m |
| 15m | 441,620 | Apr 2007 → Dec 31, 2025 | Aggregated from 1m |
| 30m | 222,641 | Apr 2007 → Dec 31, 2025 | Aggregated from 1m |
| 1h | 112,406 | Apr 2007 → Dec 31, 2025 | Aggregated from 1m |
| 4h | 29,133 | Apr 2007 → Dec 31, 2025 | Aggregated from 1h |
| 1d | 11,382 | Feb 1983 → Dec 30, 2025 | Original + Databento (session bars) |
| 1w | 2,240 | Feb 1983 → Dec 2025 | Aggregated from 1d |
| 1mo | 515 | Feb 1983 → Dec 2025 | Aggregated from 1d |

### NQ (E-mini Nasdaq 100)

| Timeframe | Bars | Range | Source |
|-----------|------|-------|--------|
| 1m | 6,147,483 | Apr 2007 → Dec 31, 2025 | Original + Databento gap fill |
| 5m | 1,309,900 | Apr 2007 → Dec 31, 2025 | Aggregated from 1m |
| 15m | 440,823 | Apr 2007 → Dec 31, 2025 | Aggregated from 1m |
| 30m | 222,515 | Apr 2007 → Dec 31, 2025 | Aggregated from 1m |
| 1h | 112,381 | Apr 2007 → Dec 31, 2025 | Aggregated from 1m |
| 4h | 29,130 | Apr 2007 → Dec 31, 2025 | Aggregated from 1h |
| 1d | 6,995 | Oct 1988 → Dec 30, 2025 | Original + Databento (session bars) |
| 1w | 1,384 | Oct 1988 → Dec 2025 | Aggregated from 1d |
| 1mo | 319 | Oct 1988 → Dec 2025 | Aggregated from 1d |

### YM (Mini Dow)

| Timeframe | Bars | Range | Source |
|-----------|------|-------|--------|
| 1m | ~5.3M | Apr 2007 → Dec 31, 2025 | Original + Databento gap fill |
| 5m | ~1.1M | Apr 2007 → Dec 31, 2025 | Aggregated from 1m |
| 15m | ~350K | Apr 2007 → Dec 31, 2025 | Aggregated from 1m |
| 30m | ~175K | Apr 2007 → Dec 31, 2025 | Aggregated from 1m |
| 1h | ~88K | Apr 2007 → Dec 31, 2025 | Aggregated from 1m |
| 4h | ~22K | Apr 2007 → Dec 31, 2025 | Aggregated from 1h |
| 1d | ~4.5K | Apr 2007 → Dec 31, 2025 | Original + Databento (session bars) |
| 1w | ~900 | Apr 2007 → Dec 2025 | Aggregated from 1d |
| 1mo | ~210 | Apr 2007 → Dec 2025 | Aggregated from 1d |

### DAX (German DAX Index Futures)

| Timeframe | Range | Source |
|-----------|-------|--------|
| 1m | Mar 2025 → Dec 2025 | Databento (XEUR.EOBI) — file: dax-1m-from-mar25.csv |
| 5m | 2000 → Aug 2024 | Original (gap after) |
| 10m | Aug 2024 → Dec 2025 | TradingView export |
| 15m | 2000 → Aug 2024 | Original (gap after) |
| 30m | 2000 → Dec 2025 | Continuous (original + 10m aggregation) |
| 1h | 2000 → Dec 2025 | Continuous |
| 4h | 2000 → Dec 2025 | Continuous |
| 1d | 1990 → Dec 2025 | Continuous (original + Databento) |
| 1w | 1990 → Dec 2025 | Aggregated from 1d |
| 1mo | 1990 → Dec 2025 | Aggregated from 1d |

**Note:** DAX has a gap in sub-30m data from Aug 2024 to Mar 2025. If gap fill needed later, only this 7-month window at 1m is required.

### Symlinks in test_data/

All ES, NQ, YM, and DAX files in `test_data/` are now symlinks to `~/Documents/backtest-data/`.

### Symbol Status

| Priority | Symbol | Status | Notes |
|----------|--------|--------|-------|
| 1 | ES | ✅ Complete | Databento |
| 2 | NQ | ✅ Complete | Databento |
| 3 | YM | ✅ Complete | Databento |
| 4 | SPX | ❌ N/A | Cash index — use ES futures |
| 5 | VIX | ❌ N/A | Cboe futures not on Databento |
| 6 | DAX | ✅ Complete | Databento (XEUR.EOBI) from Mar 2025; TV 10m fill for Aug 24-Mar 25 |

---

## Timeframe Aggregation Rules

### What Can Be Aggregated

| Target | Source | Method |
|--------|--------|--------|
| 5m, 15m, 30m | 1m | Simple OHLCV aggregation |
| 1h | 1m | Simple OHLCV aggregation |
| 4h | 1h | Simple OHLCV aggregation |
| 1w | 1d | Aggregation (W-FRI for week ending Friday) |
| 1mo | 1d | Aggregation (MS for month start) |

### What Must Be Pulled Separately

| Timeframe | Why |
|-----------|-----|
| **1d** | Session close semantics (4pm CT for ES/NQ), not midnight |

**Verified:** 1h aggregation from 1m matches Databento 1h data (same OHLCV values when using same contract).

---

## Databento Usage

### API Details

- **Credentials:** `~/.databento_credentials` (not in git)
- **Datasets:**
  - `GLBX.MDP3` (CME Globex) — ES, NQ, YM
  - `XEUR.EOBI` (Eurex) — DAX (uses parent symbol `FDAX.FUT`)

To load credentials in Python:
```python
from pathlib import Path

def load_databento_key():
    creds = Path.home() / ".databento_credentials"
    for line in creds.read_text().splitlines():
        if line.startswith("DATABENTO_API_KEY="):
            return line.split("=", 1)[1]
    raise ValueError("Key not found")
```

### Daily Refresh Costs

| Symbol | Daily | Annual |
|--------|-------|--------|
| ES | $0.005 | $1.83 |
| NQ | $0.005 | $1.83 |
| YM | $0.005 | $1.72 |
| DAX | $0.024 | $8.76 |
| **Total** | **$0.039/day** | **~$14/year** |

Note: DAX (Eurex) costs ~5x more than CME symbols per bar.

### Contract Naming

CME futures use quarterly expiration codes: H=Mar, M=Jun, U=Sep, Z=Dec

Example: `ESH6` = E-mini S&P 500, March 2026 expiry

The script auto-detects the front-month contract and handles rollovers (~1 week before 3rd Friday expiration).

### Available Schemas

Databento provides: `ohlcv-1m`, `ohlcv-1h`, `ohlcv-1d`

**Not available:** 4h, 1w, 1mo (must aggregate locally)

---

## Automated Daily Refresh

### Script Location

`scripts/daily_data_refresh.py`

### Setup (New Users)

1. **Get Databento API key:** Sign up at [databento.com](https://databento.com)

2. **Create credentials file:**
   ```bash
   echo "DATABENTO_API_KEY=your_key_here" > ~/.databento_credentials
   ```

3. **Install dependencies:**
   ```bash
   cd /path/to/fractal-market-simulator
   source venv/bin/activate
   pip install databento pandas
   ```

### Usage

```bash
# Activate virtual environment first
source venv/bin/activate

# Refresh all symbols (ES, NQ, YM, DAX)
python scripts/daily_data_refresh.py

# Refresh specific symbols
python scripts/daily_data_refresh.py ES NQ

# Dry run (show what would be fetched)
python scripts/daily_data_refresh.py --dry-run

# Fetch up to specific date
python scripts/daily_data_refresh.py --to 2026-01-15
```

### What the Script Does

1. Detects last date in each symbol's CSV file
2. Fetches missing data from Databento (1m and 1d)
3. Handles contract rollovers (CME) or continuous futures (Eurex)
4. Converts to backtest format (semicolon-delimited, local timezone)
5. Appends to existing files in `~/Documents/backtest-data/`
6. Regenerates aggregated timeframes (5m, 15m, 30m, 1h, 4h, 1w, 1mo)

### Manual Alternative (TradingView Export)

If Databento automation is unavailable, fallback to manual TradingView export:

### Aggregation Script (aggregate.py)

```python
#!/usr/bin/env python3
"""Aggregate 1m to higher timeframes."""
import pandas as pd
from pathlib import Path
import sys

def load(path):
    df = pd.read_csv(path, sep=';', header=None,
                     names=['date', 'time', 'open', 'high', 'low', 'close', 'volume'])
    df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'], format='%d/%m/%Y %H:%M:%S')
    df.set_index('datetime', inplace=True)
    return df

def save(df, path):
    df = df.reset_index()
    df['date'] = df['datetime'].dt.strftime('%d/%m/%Y')
    df['time'] = df['datetime'].dt.strftime('%H:%M:%S')
    df[['date', 'time', 'open', 'high', 'low', 'close', 'volume']].to_csv(
        path, sep=';', header=False, index=False)

def aggregate(df, tf):
    return df.resample(tf).agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).dropna()

def main(input_1m, symbol, output_dir):
    df = load(input_1m)
    out = Path(output_dir)
    for tf, name in [('5min','5m'), ('15min','15m'), ('30min','30m'), ('1h','1h')]:
        save(aggregate(df, tf), out / f"{symbol}-{name}-new.csv")
        print(f"Created {symbol}-{name}-new.csv")

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else '.')
```

---

## Findings & Lessons Learned

### 1. Daily Bars Need Session Semantics

Daily (1d) bars cannot be aggregated from 1m — they use session close times (4pm CT for ES/NQ), not midnight. Must pull 1d separately from Databento.

### 2. Contract Roll Handling

Databento provides individual contracts, not continuous series. Must:
- Pull each contract separately
- Apply rollover logic (switch ~1 week before expiration)
- Handle price discontinuities at rolls

The original backtest data and Databento may use different rollover methodologies, causing small price discrepancies at the splice point. This is expected and acceptable.

### 3. Aggregation Verification

Verified that 1h aggregated from 1m matches the source 1h data exactly. Safe to aggregate: 5m, 15m, 30m, 1h from 1m; 4h from 1h; 1w and 1mo from 1d.

### 4. Time Format Consistency

- Original data: Eastern Time (ET), format `dd/mm/yyyy;HH:MM:SS`
- TradingView: Unix timestamps (convert to ET)
- Databento: UTC (convert to ET with `tz_convert('America/New_York')`)

### 5. Symlinks vs Copies

Using symlinks from `test_data/` to `~/Documents/backtest-data/` saves disk space and ensures single source of truth. Tradeoff: breaks if source directory moves.

---

## References

- [Databento Futures](https://databento.com/futures)
- [Databento Pricing](https://databento.com/pricing)
- [TradingView Export Guide](https://www.tradingview.com/support/solutions/43000537255-how-to-export-chart-data/)
- [FirstRate Data ES](https://firstratedata.com/i/futures/ES)

