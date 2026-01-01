#!/usr/bin/env python3
"""
Data refresh script for market data.

Automatically detects the last date in existing data and fetches everything
from there to yesterday. Run anytime to catch up on missing data.

Usage:
    python daily_data_refresh.py              # Catch up all symbols to yesterday
    python daily_data_refresh.py ES NQ        # Catch up specific symbols
    python daily_data_refresh.py --dry-run    # Show what would be fetched
    python daily_data_refresh.py --to 2026-01-15  # Fetch up to specific date

Credentials: ~/.databento_credentials
"""

import argparse
import subprocess
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
    # "SPX": {"dataset": "OPRA.PILLAR", "contract_prefix": "SPX", "dir": "spx"},
    # "VIX": {"dataset": "GLBX.MDP3", "contract_prefix": "VX", "dir": "vix"},
    # "DAX": {"dataset": "XEUR.T7", "contract_prefix": "FDAX", "dir": "dax"},
}


def load_databento_key() -> str:
    """Load API key from credentials file."""
    creds_path = Path.home() / ".databento_credentials"
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {creds_path}\n"
            "Create it with:\n"
            "  DATABENTO_API_KEY=your_key_here"
        )
    for line in creds_path.read_text().splitlines():
        if line.startswith("DATABENTO_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise ValueError("DATABENTO_API_KEY not found in credentials file")


def get_last_date_in_file(filepath: Path) -> datetime | None:
    """Get the last date from a CSV file by reading its last line."""
    if not filepath.exists():
        return None

    # Use tail for efficiency on large files
    try:
        result = subprocess.run(
            ["tail", "-1", str(filepath)],
            capture_output=True, text=True, check=True
        )
        last_line = result.stdout.strip()
        if not last_line:
            return None

        # Parse date from first field (format: dd/mm/yyyy)
        date_str = last_line.split(";")[0]
        return datetime.strptime(date_str, "%d/%m/%Y")
    except Exception:
        return None


def get_front_month_contract(symbol_prefix: str, date: datetime) -> str:
    """Get the front month contract symbol for a given date."""
    year = date.year
    month = date.month

    # Contracts expire ~3rd Friday of expiration month
    # Roll to next contract about 1 week before expiration
    if month <= 2 or (month == 3 and date.day <= 7):
        contract_month, contract_year = "H", year
    elif month <= 5 or (month == 6 and date.day <= 7):
        contract_month, contract_year = "M", year
    elif month <= 8 or (month == 9 and date.day <= 7):
        contract_month, contract_year = "U", year
    elif month <= 11 or (month == 12 and date.day <= 7):
        contract_month, contract_year = "Z", year
    else:
        contract_month, contract_year = "H", year + 1

    return f"{symbol_prefix}{contract_month}{contract_year % 10}"


def get_contracts_for_range(symbol_prefix: str, start: datetime, end: datetime) -> list[str]:
    """Get all contracts needed to cover a date range."""
    contracts = set()
    current = start
    while current <= end:
        contracts.add(get_front_month_contract(symbol_prefix, current))
        current += timedelta(days=1)
    return sorted(contracts)


def fetch_range_data(
    client: db.Historical,
    config: dict,
    start_date: datetime,
    end_date: datetime,
    dry_run: bool = False,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Fetch 1m and 1d data for a date range, handling contract rollovers."""

    contracts = get_contracts_for_range(config["contract_prefix"], start_date, end_date)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"    Contracts: {', '.join(contracts)}")
    print(f"    Range: {start_str} to {end_date.strftime('%Y-%m-%d')}")

    if dry_run:
        return None, None

    all_1m = []
    all_1d = []

    for contract in contracts:
        # Fetch 1m data
        try:
            data_1m = client.timeseries.get_range(
                dataset=config["dataset"],
                symbols=[contract],
                schema="ohlcv-1m",
                start=start_str,
                end=end_str,
            )
            df = data_1m.to_df().reset_index()
            df["contract"] = contract
            all_1m.append(df)
            print(f"      {contract} 1m: {len(df)} bars")
        except Exception as e:
            print(f"      {contract} 1m: Error - {e}")

        # Fetch 1d data
        try:
            data_1d = client.timeseries.get_range(
                dataset=config["dataset"],
                symbols=[contract],
                schema="ohlcv-1d",
                start=start_str,
                end=end_str,
            )
            df = data_1d.to_df().reset_index()
            df["contract"] = contract
            all_1d.append(df)
            print(f"      {contract} 1d: {len(df)} bars")
        except Exception as e:
            print(f"      {contract} 1d: Error - {e}")

    # Combine and deduplicate (prefer front month for each timestamp)
    df_1m = None
    df_1d = None

    if all_1m:
        combined = pd.concat(all_1m, ignore_index=True)
        # For each timestamp, keep only the front month contract
        combined["date_only"] = combined["ts_event"].dt.date

        def get_active(row):
            return get_front_month_contract(
                config["contract_prefix"],
                datetime.combine(row["date_only"], datetime.min.time())
            )

        combined["active"] = combined.apply(get_active, axis=1)
        df_1m = combined[combined["contract"] == combined["active"]].copy()
        df_1m = df_1m.sort_values("ts_event").drop_duplicates(subset="ts_event", keep="first")
        print(f"    1m total (deduplicated): {len(df_1m)} bars")

    if all_1d:
        combined = pd.concat(all_1d, ignore_index=True)
        combined["date_only"] = combined["ts_event"].dt.date

        def get_active(row):
            return get_front_month_contract(
                config["contract_prefix"],
                datetime.combine(row["date_only"], datetime.min.time())
            )

        combined["active"] = combined.apply(get_active, axis=1)
        df_1d = combined[combined["contract"] == combined["active"]].copy()
        df_1d = df_1d.sort_values("ts_event").drop_duplicates(subset="ts_event", keep="first")
        print(f"    1d total (deduplicated): {len(df_1d)} bars")

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

    def save_csv(df: pd.DataFrame, path: Path):
        df = df.reset_index()
        df["date"] = df["datetime"].dt.strftime("%d/%m/%Y")
        df["time"] = df["datetime"].dt.strftime("%H:%M:%S")
        df[["date", "time", "open", "high", "low", "close", "volume"]].to_csv(
            path, sep=";", header=False, index=False
        )

    def aggregate(df: pd.DataFrame, tf: str) -> pd.DataFrame:
        return df.resample(tf).agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
        }).dropna()

    print(f"  Regenerating aggregates...")
    try:
        # From 1m: 5m, 15m, 30m, 1h
        df_1m = load_csv(symbol_dir / f"{symbol}-1m.csv")
        for tf, name in [("5min", "5m"), ("15min", "15m"), ("30min", "30m"), ("1h", "1h")]:
            save_csv(aggregate(df_1m, tf), symbol_dir / f"{symbol}-{name}.csv")

        # 4h from 1h
        df_1h = load_csv(symbol_dir / f"{symbol}-1h.csv")
        save_csv(aggregate(df_1h, "4h"), symbol_dir / f"{symbol}-4h.csv")

        # 1w, 1mo from 1d
        df_1d = load_csv(symbol_dir / f"{symbol}-1d.csv")
        save_csv(aggregate(df_1d, "W-FRI"), symbol_dir / f"{symbol}-1w.csv")
        save_csv(aggregate(df_1d, "MS"), symbol_dir / f"{symbol}-1mo.csv")

        print(f"    Done (5m, 15m, 30m, 1h, 4h, 1w, 1mo)")
    except Exception as e:
        print(f"    Error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Catch up market data from last available date to yesterday"
    )
    parser.add_argument("symbols", nargs="*", help="Symbols to refresh (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--to", dest="end_date", help="End date (default: yesterday)")
    parser.add_argument("--no-aggregate", action="store_true", help="Skip aggregation")
    args = parser.parse_args()

    # Determine end date
    if args.end_date:
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d")
    else:
        end_date = datetime.now() - timedelta(days=1)

    # Determine symbols
    symbols_to_process = args.symbols if args.symbols else list(SYMBOLS.keys())
    symbols_to_process = [s.upper() for s in symbols_to_process]

    # Validate symbols
    for s in symbols_to_process:
        if s not in SYMBOLS:
            print(f"Unknown symbol: {s}. Available: {list(SYMBOLS.keys())}")
            sys.exit(1)

    print(f"Data refresh to {end_date.strftime('%Y-%m-%d')}")
    print(f"Symbols: {', '.join(symbols_to_process)}")
    print(f"Dry run: {args.dry_run}")
    print()

    # Load credentials
    if not args.dry_run:
        api_key = load_databento_key()
        client = db.Historical(api_key)
    else:
        client = None

    # Process each symbol
    for symbol in symbols_to_process:
        config = SYMBOLS[symbol]
        symbol_dir = BACKTEST_DATA / config["dir"]
        csv_1m = symbol_dir / f"{config['dir']}-1m.csv"

        print(f"{symbol}:")

        # Get last date in file
        last_date = get_last_date_in_file(csv_1m)
        if last_date is None:
            print(f"  No existing data found in {csv_1m}")
            continue

        print(f"  Last data: {last_date.strftime('%Y-%m-%d')}")

        # Calculate start date (day after last data)
        start_date = last_date + timedelta(days=1)

        if start_date > end_date:
            print(f"  Already up to date!")
            continue

        days_to_fetch = (end_date - start_date).days + 1
        print(f"  Need to fetch: {days_to_fetch} days")

        # Fetch data
        df_1m, df_1d = fetch_range_data(client, config, start_date, end_date, args.dry_run)

        if args.dry_run:
            print()
            continue

        # Append data
        if df_1m is not None and len(df_1m) > 0:
            df_1m_fmt = convert_to_backtest_format(df_1m)
            rows = append_to_file(df_1m_fmt, csv_1m)
            print(f"  Appended {rows} rows to {config['dir']}-1m.csv")

        csv_1d = symbol_dir / f"{config['dir']}-1d.csv"
        if df_1d is not None and len(df_1d) > 0:
            df_1d_fmt = convert_to_backtest_format(df_1d)
            rows = append_to_file(df_1d_fmt, csv_1d)
            print(f"  Appended {rows} rows to {config['dir']}-1d.csv")

        # Regenerate aggregates
        if not args.no_aggregate:
            regenerate_aggregates(symbol_dir, config["dir"])

        print()

    print("Done!")


if __name__ == "__main__":
    main()
