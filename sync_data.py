import pandas as pd
from datetime import datetime, timedelta
from tqdm import tqdm
import time
from datetime import date
from api import equity_history
from config import DATA_DIR, STOCKS_FILE, DEFAULT_INITIAL_YEARS

import warnings
warnings.filterwarnings("ignore")


def ensure_data_dir():
    """Ensure data directory exists"""
    DATA_DIR.mkdir(exist_ok=True)


def get_stock_list():
    """Read stock symbols from stocks.txt"""
    if not STOCKS_FILE.exists():
        raise FileNotFoundError(f"Stock list file '{STOCKS_FILE}' not found. Please create it.")
    with open(STOCKS_FILE, 'r') as f:
        # Ensure symbols are uppercase and remove duplicates
        stocks = sorted(list(set([line.strip().upper() for line in f if line.strip()])))
    if not stocks:
        raise ValueError(f"Stock list file '{STOCKS_FILE}' is empty.")
    return stocks


def get_last_trading_day():
    """
    Get the most recent trading day.
    Adjusts for weekends. Does not account for specific market holidays,
    """
    today = datetime.now()
    # Use today's date but zero out time for consistent comparisons
    today_date_only = today.replace(hour=0, minute=0, second=0, microsecond=0)

    # If today is Saturday (5), last trading day was Friday (-1 day)
    if today.weekday() == 5:
        return today_date_only - timedelta(days=1)
    # If today is Sunday (6), last trading day was Friday (-2 days)
    elif today.weekday() == 6:
        return today_date_only - timedelta(days=2)
    # If it's a weekday, assume today *could* be the last trading day
    # or the day before if the market hasn't closed/data isn't available yet.
    return today_date_only


def download_stock_data(stock_symbol: str, start_date: date, end_date: date):
    print(f"Fetching data for {stock_symbol}...")
    try:
        start_date_str = start_date.strftime('%d-%m-%Y')
        end_date_str = end_date.strftime('%d-%m-%Y')

        # Fetch historical data using nsepython
        # Note: nsepython might sometimes be unreliable or slow.
        # Consider error handling and retries in a production scenario.
        df = equity_history(stock_symbol, series="EQ", start_date=start_date_str, end_date=end_date_str)

        # --- Data Processing ---
        if df.empty:
            print(f"No data returned for {stock_symbol} in the specified period.")
            return

        # Rename columns to a standard format
        # Adjust these names if nsepython changes its output format
        column_mapping = {
            'CH_TIMESTAMP': 'Date',
            'CH_OPENING_PRICE': 'Open',
            'CH_TRADE_HIGH_PRICE': 'High',
            'CH_TRADE_LOW_PRICE': 'Low',
            'CH_CLOSING_PRICE': 'Close',
            'CH_TOT_TRADED_QTY': 'Volume'
            # Add other columns if needed, e.g., 'CH_TOTAL_TRADES': 'TotalTrades'
        }
        # Select only the columns we need and rename them
        ohlcv_columns = list(column_mapping.keys())
        if not all(col in df.columns for col in ohlcv_columns):
             print(f"Error: Expected columns not found in data for {stock_symbol}.")
             print(f"Available columns: {df.columns.tolist()}")
             # Attempt to find similar columns (example heuristic, might need refinement)
             potential_mappings = {
                 'date': ['Date', 'CH_TIMESTAMP', 'timestamp'],
                 'open': ['Open', 'CH_OPENING_PRICE', 'open'],
                 'high': ['High', 'CH_TRADE_HIGH_PRICE', 'high'],
                 'low': ['Low', 'CH_TRADE_LOW_PRICE', 'low'],
                 'close': ['Close', 'CH_CLOSING_PRICE', 'close'],
                 'volume': ['Volume', 'CH_TOT_TRADED_QTY', 'volume']
             }
             found_mapping = {}
             for target, potentials in potential_mappings.items():
                 for potential in potentials:
                     if potential in df.columns:
                         found_mapping[potential] = target
                         break
                 else: # If no potential column was found for the target
                     print(f"Warning: Could not find a column for '{target}'")

             if len(found_mapping) < 6: # Check if we found enough columns
                 print("Error: Could not map essential OHLCV columns. Aborting.")
                 return
             else:
                 print(f"Attempting to use inferred column mapping: {found_mapping}")
                 df = df[list(found_mapping.keys())].rename(columns=found_mapping)
                 # Ensure correct column order after potential inference
                 df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]

        else:
             df = df[ohlcv_columns].rename(columns=column_mapping)


        # Convert columns to appropriate types
        df['Date'] = pd.to_datetime(df['Date'], format='%Y-%m-%d') # Adjust format if needed based on nsepython output
        numeric_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        for col in numeric_cols:
            # Replace commas and convert to numeric, coercing errors
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '', regex=False), errors='coerce')

        # Drop rows where conversion failed for essential price columns
        df.dropna(subset=['Open', 'High', 'Low', 'Close', 'Volume'], inplace=True)

        # Sort by date (important for moving average calculation)
        df.sort_values(by='Date', inplace=True)

        # Calculate 200-day moving average
        df['MA'] = df['Close'].rolling(200).mean().round(2)
        df = df.dropna().reset_index(drop=True)
        return df

    except Exception as e:
        print(f"An error occurred while fetching or processing data for {stock_symbol}: {e}")
        import traceback
        traceback.print_exc() # Print detailed traceback for debugging


def sync_data(initial_years=DEFAULT_INITIAL_YEARS):
    """
    Synchronizes local stock data. Downloads initial history for missing
    stocks and updates existing stocks to the last known trading day.
    """
    ensure_data_dir()
    try:
        stocks = get_stock_list()
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        return

    target_date = get_last_trading_day()
    # Use current time for reference, not necessarily for fetching data up to the minute
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now_str}] Starting data sync...")
    print(f"Targeting data up to: {target_date.date()}")
    print(f"Found {len(stocks)} stocks in '{STOCKS_FILE}'.")

    # Counters for summary
    stats = {
        "initial_download": 0,
        "updated": 0,
        "already_up_to_date": 0,
        "no_new_data": 0,
        "failed": 0,
        "file_error": 0,
    }

    # Use tqdm for progress bar
    for symbol in tqdm(stocks, desc="Syncing Data", unit="stock"):
        file_path = DATA_DIR / f"{symbol}.csv"
        time.sleep(0.1) # Small delay per stock to avoid rapid-fire requests

        # --- Case 1: File does NOT exist ---
        if not file_path.exists():
            print(f"\n[{symbol}] File not found. Performing initial download ({initial_years} years).")
            start_date = target_date - timedelta(days=initial_years * 365)

            new_data_df = download_stock_data(symbol, start_date, target_date)

            if new_data_df is not None and not new_data_df.empty:
                try:
                    new_data_df.to_csv(file_path, date_format='%Y-%m-%d', index=False)
                    print(f"[{symbol}] Initial download successful.")
                    stats["initial_download"] += 1
                except Exception as e:
                    print(f"[{symbol}] Failed to save initial data: {e}")
                    stats["failed"] += 1 # Count as failure if save fails
            else:
                print(f"[{symbol}] Failed to download initial data or no data returned.")
                stats["failed"] += 1
            continue # Move to next symbol

        # --- Case 2: File EXISTS ---
        try:
            existing_df = pd.read_csv(file_path, index_col='Date', parse_dates=True)

            # Handle empty existing file
            if existing_df.empty:
                print(f"\n[{symbol}] Existing file is empty. Attempting full redownload ({initial_years} years).")
                start_date = target_date - timedelta(days=initial_years * 365)
                new_data_df = download_stock_data(symbol, start_date, target_date)
                if new_data_df is not None and not new_data_df.empty:
                    new_data_df.to_csv(file_path, date_format='%Y-%m-%d', index=False)
                    print(f"[{symbol}] Redownload successful.")
                    stats["initial_download"] += 1 # Count as initial as it replaced empty
                else:
                    print(f"[{symbol}] Failed redownload for empty file.")
                    stats["failed"] += 1
                continue # Move to next symbol

            # Find last date in the existing file
            last_date_in_file = existing_df.index.max()

            # --- Subcase 2a: Already up-to-date ---
            if last_date_in_file.date() >= target_date.date():
                # Use TQDM's persistence for status, avoid excessive printing
                # tqdm.write(f"[{symbol}] Data already up-to-date (Last: {last_date_in_file.date()})")
                stats["already_up_to_date"] += 1
                continue # Move to next symbol

            # --- Subcase 2b: Needs update ---
            start_update_date = last_date_in_file + timedelta(days=1)

            # Defensive check: If calculated start is after target, something's odd, treat as up-to-date
            if start_update_date > target_date:
                tqdm.write(f"[{symbol}] Warning: Calculated update start date {start_update_date.date()} is after target {target_date.date()}. Skipping update.")
                stats["already_up_to_date"] += 1
                continue

            # Download only the new data portion
            tqdm.write(f"[{symbol}] Updating from {start_update_date.date()} to {target_date.date()}")
            new_data_df = download_stock_data(symbol, start_update_date, target_date)

            # If download failed
            if new_data_df is None:
                tqdm.write(f"[{symbol}] Update download failed.")
                stats["failed"] += 1
            # If download succeeded but returned no new rows (e.g., holidays, market closed)
            elif new_data_df.empty:
                tqdm.write(f"[{symbol}] No new data found since {last_date_in_file.date()}.")
                stats["no_new_data"] += 1
            # If download succeeded with new data
            else:
                # Combine old and new data
                combined_df = pd.concat([existing_df, new_data_df])

                # Remove potential duplicates (e.g., if script run multiple times on same day)
                # Keep the 'last' entry which would be from the latest download attempt.
                combined_df = combined_df[~combined_df.index.duplicated(keep='last')]

                # Sort by date index to ensure chronological order
                combined_df.sort_index(inplace=True)

                # Overwrite the old file with the complete combined data
                combined_df.to_csv(file_path, date_format='%Y-%m-%d', index=False)
                tqdm.write(f"[{symbol}] Update successful. New last date: {combined_df.index.max().date()}")
                stats["updated"] += 1

        # Handle errors during file reading or processing
        except pd.errors.EmptyDataError:
            print(f"\n[{symbol}] Error: Existing file is corrupt (empty data error). Consider deleting it and re-running.")
            stats["file_error"] += 1
        except Exception as e:
            print(f"\n[{symbol}] Error processing existing file: {type(e).__name__} - {e}")
            stats["file_error"] += 1

    # --- Print Summary ---
    print("\n----- Sync Summary -----")
    print(f"Initial Downloads.....: {stats['initial_download']}")
    print(f"Updated...............: {stats['updated']}")
    print(f"Already Up-to-date..: {stats['already_up_to_date']}")
    print(f"No New Data Found.....: {stats['no_new_data']}")
    print(f"Download/Save Failures: {stats['failed']}")
    print(f"File Read Errors......: {stats['file_error']}")
    print(f"------------------------")
    total_processed = sum(stats.values())
    print(f"Total Stocks Processed: {total_processed}/{len(stocks)}")
    if total_processed != len(stocks):
        print("Warning: Total processed count doesn't match stock list size. Check logs.")
    print(f"Sync finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    sync_data()
