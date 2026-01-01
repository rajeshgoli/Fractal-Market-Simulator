#!/usr/bin/env python3
"""
Daily data refresh script for market data.

Pulls yesterday's 1m and 1d data from Databento, appends to existing files,
and regenerates aggregated timeframes.

Usage:
    python daily_data_refresh.py              # Refresh all symbols
    python daily_data_refresh.py ES NQ        # Refresh specific symbols
    python daily_data_refresh.py --dry-run    # Show what would be done

Cron example (run daily at 6am):
    0 6 * * * cd /path/to/fractal-market-simulator && venv/bin/python scripts/daily_data_refresh.py >> logs/data_refresh.log 2>&1

Credentials: ~/.databento_credentials
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import databento as db
import pandas as pd


# Configuration
BACKTEST_DATA = Path.home() / "Documents/backtest-data"

# Symbol configurations
SYMBOLS = {
    "ES": {
        "dataset": "GLBX.MDP3",
        "contract_prefix": "ES",
        "dir": "es",
    },
    "NQ": {
        "dataset": "GLBX.MDP3",
        "contract_prefix": "NQ",
        "dir": "nq",
    },
    # Future symbols (uncomment when ready)
    # "YM": {"dataset": "GLBX.MDP3", "contract_prefix": "YM", "dir": "ym"},
    # "SPX": {"dataset": "OPRA.PILLAR", "contract_prefix": "SPX", "dir": "spx"},  # Check dataset
    # "VIX": {"dataset": "GLBX.MDP3", "contract_prefix": "VX", "dir": "vix"},
    # "DAX": {"dataset": "XEUR.T7", "contract_prefix": "FDAX", "dir": "dax"},  # Check dataset
}

# Contract expiration months: H=Mar, M=Jun, U=Sep, Z=Dec
CONTRACT_MONTHS = ["H", "M", "U", "Z"]


def load_databento_key() -> str:
    """Load API key from credentials file."""
    creds_path = Path.home() / ".databento_credentials"
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {creds_path}\n"
            "Create it with:\n"
            "  DATABENTO_API_KEY=your_key_here\n"
            "  DATABENTO_USER_ID=your_user_id"
        )
    for line in creds_path.read_text().splitlines():
        if line.startswith("DATABENTO_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise ValueError("DATABENTO_API_KEY not found in credentials file")


def get_front_month_contract(symbol_prefix: str, date: datetime) -> str:
    """Get the front month contract symbol for a given date."""
    year = date.year
    month = date.month

    # Determine which contract month we're in
    # Contracts expire ~3rd Friday of expiration month
    # Roll to next contract about 1 week before expiration
    if month <= 2 or (month == 3 and date.day <= 7):
        contract_month = "H"
        contract_year = year
    elif month <= 5 or (month == 6 and date.day <= 7):
        contract_month = "M"
        contract_year = year
    elif month <= 8 or (month == 9 and date.day <= 7):
        contract_month = "U"
        contract_year = year
    elif month <= 11 or (month == 12 and date.day <= 7):
        contract_month = "Z"
        contract_year = year
    else:
        contract_month = "H"
        contract_year = year + 1

    # Format: ESH5 (year as single digit for current decade)
    year_digit = contract_year % 10
    return f"{symbol_prefix}{contract_month}{year_digit}"


def fetch_daily_data(
    client: db.Historical,
    symbol: str,
    config: dict,
    target_date: datetime,
    dry_run: bool = False,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Fetch 1m and 1d data for a single day."""
    contract = get_front_month_contract(config["contract_prefix"], target_date)
    start = target_date.strftime("%Y-%m-%d")
    end = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"  {symbol}: {contract} for {start}")

    if dry_run:
        return None, None

    # Fetch 1m data
    try:
        data_1m = client.timeseries.get_range(
            dataset=config["dataset"],
            symbols=[contract],
            schema="ohlcv-1m",
            start=start,
            end=end,
        )
        df_1m = data_1m.to_df().reset_index()
        print(f"    1m: {len(df_1m)} bars")
    except Exception as e:
        print(f"    1m: Error - {e}")
        df_1m = None

    # Fetch 1d data
    try:
        data_1d = client.timeseries.get_range(
            dataset=config["dataset"],
            symbols=[contract],
            schema="ohlcv-1d",
            start=start,
            end=end,
        )
        df_1d = data_1d.to_df().reset_index()
        print(f"    1d: {len(df_1d)} bars")
    except Exception as e:
        print(f"    1d: Error - {e}")
        df_1d = None

    return df_1m, df_1d


def convert_to_backtest_format(df: pd.DataFrame, tz: str = "America/New_York") -> pd.DataFrame:
    """Convert Databento DataFrame to backtest format."""
    df = df.copy()
    df["ts_event"] = df["ts_event"].dt.tz_convert(tz)
    df["date"] = df["ts_event"].dt.strftime("%d/%m/%Y")
    df["time"] = df["ts_event"].dt.strftime("%H:%M:%S")
    return df[["date", "time", "open", "high", "low", "close", "volume"]]


def append_to_file(df: pd.DataFrame, filepath: Path) -> int:
    """Append DataFrame to CSV file. Returns number of rows appended."""
    if df is None or len(df) == 0:
        return 0

    with open(filepath, "a") as f:
        df.to_csv(f, sep=";", header=False, index=False)

    return len(df)


def regenerate_aggregates(symbol_dir: Path, symbol: str):
    """Regenerate aggregated timeframes from 1m and 1d data."""

    def load_csv(path: Path) -> pd.DataFrame:
        df = pd.read_csv(
            path, sep=";", header=None,
            names=["date", "time", "open", "high", "low", "close", "volume"]
        )
        df["datetime"] = pd.to_datetime(
            df["date"] + " " + df["time"], format="mixed", dayfirst=True
        )
        df.set_index("datetime", inplace=True)
        return df

    def save_csv(df: pd.DataFrame, path: Path, time_fmt: str = "%H:%M:%S"):
        df = df.reset_index()
        df["date"] = df["datetime"].dt.strftime("%d/%m/%Y")
        df["time"] = df["datetime"].dt.strftime(time_fmt)
        df[["date", "time", "open", "high", "low", "close", "volume"]].to_csv(
            path, sep=";", header=False, index=False
        )

    def aggregate(df: pd.DataFrame, tf: str) -> pd.DataFrame:
        return df.resample(tf).agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
        }).dropna()

    # Regenerate from 1m: 5m, 15m, 30m, 1h
    print(f"  Regenerating aggregates for {symbol}...")
    try:
        df_1m = load_csv(symbol_dir / f"{symbol}-1m.csv")
        for tf, name in [("5min", "5m"), ("15min", "15m"), ("30min", "30m"), ("1h", "1h")]:
            agg = aggregate(df_1m, tf)
            save_csv(agg, symbol_dir / f"{symbol}-{name}.csv")

        # 4h from 1h
        df_1h = load_csv(symbol_dir / f"{symbol}-1h.csv")
        save_csv(aggregate(df_1h, "4h"), symbol_dir / f"{symbol}-4h.csv")

        # 1w, 1mo from 1d
        df_1d = load_csv(symbol_dir / f"{symbol}-1d.csv")
        save_csv(aggregate(df_1d, "W-FRI"), symbol_dir / f"{symbol}-1w.csv")
        save_csv(aggregate(df_1d, "MS"), symbol_dir / f"{symbol}-1mo.csv")

        print(f"    Done")
    except Exception as e:
        print(f"    Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Daily data refresh from Databento")
    parser.add_argument("symbols", nargs="*", help="Symbols to refresh (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--date", help="Date to fetch (YYYY-MM-DD, default: yesterday)")
    parser.add_argument("--no-aggregate", action="store_true", help="Skip aggregation step")
    args = parser.parse_args()

    # Determine target date
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        target_date = datetime.now() - timedelta(days=1)

    # Determine symbols to process
    symbols_to_process = args.symbols if args.symbols else list(SYMBOLS.keys())
    symbols_to_process = [s.upper() for s in symbols_to_process]

    # Validate symbols
    for s in symbols_to_process:
        if s not in SYMBOLS:
            print(f"Unknown symbol: {s}. Available: {list(SYMBOLS.keys())}")
            sys.exit(1)

    print(f"Data refresh for {target_date.strftime('%Y-%m-%d')}")
    print(f"Symbols: {', '.join(symbols_to_process)}")
    print(f"Dry run: {args.dry_run}")
    print()

    # Load credentials and create client
    if not args.dry_run:
        api_key = load_databento_key()
        client = db.Historical(api_key)
    else:
        client = None

    # Process each symbol
    for symbol in symbols_to_process:
        config = SYMBOLS[symbol]
        symbol_dir = BACKTEST_DATA / config["dir"]

        print(f"Processing {symbol}...")

        # Fetch data
        df_1m, df_1d = fetch_daily_data(client, symbol, config, target_date, args.dry_run)

        if args.dry_run:
            continue

        # Convert and append
        if df_1m is not None and len(df_1m) > 0:
            df_1m_fmt = convert_to_backtest_format(df_1m)
            rows = append_to_file(df_1m_fmt, symbol_dir / f"{config['dir']}-1m.csv")
            print(f"    Appended {rows} rows to {config['dir']}-1m.csv")

        if df_1d is not None and len(df_1d) > 0:
            df_1d_fmt = convert_to_backtest_format(df_1d)
            rows = append_to_file(df_1d_fmt, symbol_dir / f"{config['dir']}-1d.csv")
            print(f"    Appended {rows} rows to {config['dir']}-1d.csv")

        # Regenerate aggregates
        if not args.no_aggregate:
            regenerate_aggregates(symbol_dir, config["dir"])

    print("\nDone!")


if __name__ == "__main__":
    main()
