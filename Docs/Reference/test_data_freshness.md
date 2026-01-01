# Test Data Freshness Plan

**Status:** Phase 1 Complete
**Created:** January 1, 2026
**Owner:** Product

---

## Executive Summary

Gap fill for ES, NQ, and YM completed on January 1, 2026 using Databento API. Data now extends from April 2007 to December 31, 2025 for all three symbols. Automated refresh script handles ongoing updates.

---

## Current Data State (Post Gap Fill)

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

### Symlinks in test_data/

All ES, NQ, and YM files in `test_data/` are now symlinks to `~/Documents/backtest-data/`.

### Symbol Status

| Priority | Symbol | Status | Notes |
|----------|--------|--------|-------|
| 1 | ES | ✅ Complete | Databento |
| 2 | NQ | ✅ Complete | Databento |
| 3 | YM | ✅ Complete | Databento |
| 4 | SPX | ❌ N/A | Cash index — use ES futures |
| 5 | VIX | ❌ N/A | Cboe futures not on Databento |
| 6 | DAX | ⚠️ Gap | Eurex data only from Mar 2025; needs TradingView gap fill |

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
- **Dataset:** `GLBX.MDP3` (CME Globex)

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

### Cost Summary (Jan 1, 2026)

| Item | Cost |
|------|------|
| ES 1m (7 contracts, Aug 2024 → Jan 2026) | $2.48 |
| NQ 1m (7 contracts, Aug 2024 → Jan 2026) | $2.37 |
| ES 1d (7 contracts) | $0.01 |
| NQ 1d (7 contracts) | $0.01 |
| Verification samples | ~$0.10 |
| **Total spent** | **~$5.00** |
| **Remaining credit** | **~$120** |

### Contracts Used

ES: ESU4, ESZ4, ESH5, ESM5, ESU5, ESZ5, ESH6
NQ: NQU4, NQZ4, NQH5, NQM5, NQU5, NQZ5, NQH6

Rollover dates (approx 1 week before 3rd Friday expiration):
- U4: Sep 13, 2024
- Z4: Dec 13, 2024
- H5: Mar 14, 2025
- M5: Jun 13, 2025
- U5: Sep 12, 2025
- Z5: Dec 12, 2025
- H6: Mar 13, 2026

### Available Schemas

Databento provides: `ohlcv-1m`, `ohlcv-1h`, `ohlcv-1d`

**Not available:** 4h, 1w, 1mo (must aggregate locally)

---

## Automated Daily Refresh

### Script Location

`scripts/daily_data_refresh.py`

### Usage

```bash
# Refresh all symbols (ES, NQ)
python scripts/daily_data_refresh.py

# Refresh specific symbols
python scripts/daily_data_refresh.py ES

# Dry run (show what would be done)
python scripts/daily_data_refresh.py --dry-run

# Refresh specific date
python scripts/daily_data_refresh.py --date 2025-12-30
```

### Cron Setup (Recommended)

Run daily at 6am ET (after market close + data availability):

```bash
# Edit crontab
crontab -e

# Add this line:
0 6 * * * cd /Users/rajesh/Desktop/fractal-market-simulator && venv/bin/python scripts/daily_data_refresh.py >> logs/data_refresh.log 2>&1
```

Create logs directory:
```bash
mkdir -p logs
```

### What the Script Does

1. Determines yesterday's date (or specified date)
2. Identifies front-month contract for each symbol
3. Fetches 1m and 1d data from Databento
4. Converts to backtest format (ET timezone, semicolon-delimited)
5. Appends to existing files in `~/Documents/backtest-data/`
6. Regenerates aggregated timeframes (5m, 15m, 30m, 1h, 4h, 1w, 1mo)

### Cost

~$0.01/day for ES + NQ = ~$3.50/year

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

## Phase 2: Remaining Symbols

### SPX, YM, VIX, DAX

When ready, repeat the Databento gap fill process:

1. Estimate cost: `client.metadata.get_cost(...)`
2. Pull contracts for Aug 2024 → present
3. Create continuous series with rollovers
4. Append to existing files
5. Regenerate aggregated timeframes

Estimated cost: ~$2-3 per symbol for 1m + 1d data.

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

---

## Appendix: Q&A Log

### Q: Do you have an Interactive Brokers account?
**A:** No. Using Databento for gap fill instead.

### Q: Is 30m granularity sufficient for ongoing updates?
**A:** No, want 1m. Weekly TradingView 1m export works (~7K bars fits in single export).

### Q: Should we regenerate all timeframes from 1m?
**A:** Yes for intraday (5m, 15m, 30m, 1h, 4h). No for 1d — must pull separately due to session close semantics.

### Q: Why can't I do TradingView export for gap fill?
**A:** 17 months at 1m = ~500,000 bars. TradingView shows max ~10-20K bars per export. Would require 25-50 separate exports scrolling back each time. Not practical. But weekly 1m export (~7K bars) works fine for ongoing freshness.

### Q: Why would it take 1 hour to export 6 charts?
**A:** It wouldn't! Revised estimate: ~2 min per symbol = ~15 min total for all 6.

### Q: Can you do the Databento work if I sign up?
**A:** Yes. Just needed API key and user ID. Executed the full gap fill in this session.

### Q: 1D data can't be aggregated — pull from Databento?
**A:** Correct. 1D uses session close (4pm CT), not midnight. Pulled 1D separately. Cost: $0.02 total for ES + NQ.

### Q: Can 4h, 1w, 1mo be aggregated?
**A:** Yes. Verified by comparing my aggregation against Databento samples. 4h from 1h, 1w/1mo from 1d.

### Q: Keep ~/Documents/backtest-data/ authoritative and symlink test_data?
**A:** Done. All test_data/ files are now symlinks to backtest-data/.

### Q: Priority order for symbols?
**A:** ES, NQ, SPX, YM, VIX, DAX. Others (FTSE, Nifty, etc.) low priority.

---

## Execution Log

### January 1, 2026

**Gap Fill Execution:**

1. Created Databento account, obtained API key
2. Installed `databento` Python package
3. Estimated costs: ES $2.48, NQ $2.37, 1D $0.02
4. Pulled ES 1m data (7 contracts: ESU4-ESH6) → 497,713 bars continuous
5. Pulled NQ 1m data (7 contracts: NQU4-NQH6) → 497,765 bars continuous
6. Applied rollover logic, converted to ET timezone
7. Trimmed to start after original data ends (Aug 5, 2024 00:01:00)
8. Appended to original files in ~/Documents/backtest-data/
9. Regenerated 5m, 15m, 30m, 1h from 1m for both ES and NQ
10. Pulled 1D data separately (session bars), appended to originals
11. Regenerated 4h from 1h, 1w and 1mo from 1d
12. Created symlinks from test_data/ to backtest-data/
13. Cleaned up temp files

**Final State:**
- ES: 6.5M 1m bars, ends Dec 31, 2025 @ 6893.75
- NQ: 6.1M 1m bars, ends Dec 31, 2025 @ 25434.75
- All timeframes regenerated and current
- ~$5 of $125 Databento credit used
