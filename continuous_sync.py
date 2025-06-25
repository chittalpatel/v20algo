import pandas as pd
from datetime import datetime, timedelta
import time
import sys
import random
import logging
import holidays
from datetime import date
from api import equity_history, is_suspended
from config import DATA_DIR, STOCKS_FILE, DEFAULT_INITIAL_YEARS, MASTER_STOCKS_FILE
from sync_data import ensure_data_dir, get_stock_list, download_stock_data, get_stock_file_path

import warnings
warnings.filterwarnings("ignore")

# Configure logging for continuous sync
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('continuous_sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Indian holidays calendar
indian_holidays = holidays.India()

# Global set to track suspended stocks
suspended_stocks = set()


def get_previous_trading_day(target_date=None):
    """
    Get the previous trading day, accounting for weekends and Indian holidays.

    Args:
        target_date: Date to start from (defaults to today)

    Returns:
        datetime: Previous trading day
    """
    if target_date is None:
        target_date = datetime.now().date()

    # Start from the target date and go backwards
    current_date = target_date

    # Go back up to 5 days to find a trading day (should be enough for most cases)
    for _ in range(5):
        current_date = current_date - timedelta(days=1)

        # Check if it's a weekend
        if current_date.weekday() >= 5:  # Saturday (5) or Sunday (6)
            continue

        # Check if it's a holiday
        if current_date in indian_holidays:
            continue

        # If we reach here, it's a trading day
        return datetime.combine(current_date, datetime.min.time())

    # If we can't find a trading day in 10 days, return the original date
    # This is a fallback for edge cases
    logger.warning(f"Could not find previous trading day within 5 days of {target_date}")
    return datetime.combine(target_date, datetime.min.time())


def get_fresh_data_threshold():
    """
    Get the date threshold for considering data fresh.
    Returns the previous trading day, accounting for weekends and Indian holidays.
    """
    today = datetime.now().date()
    previous_trading_day = get_previous_trading_day(today)
    return previous_trading_day


def is_data_fresh(file_path, fresh_threshold):
    """
    Check if the data in the file is fresh (not older than the threshold)
    """
    try:
        if not file_path.exists():
            return False

        df = pd.read_csv(file_path, index_col='Date', parse_dates=True)

        if df.empty:
            return False

        last_date = df.index.max()
        return last_date.date() >= fresh_threshold.date()

    except Exception as e:
        logger.error(f"Error checking data freshness for {file_path}: {e}")
        return False


def sync_single_stock(symbol, fresh_threshold):
    """
    Sync a single stock.
    """
    if symbol in suspended_stocks:
        return False, "suspended"
    file_path = get_stock_file_path(symbol)

    try:
        # Check if file exists and get last date
        if file_path.exists():
            try:
                existing_df = pd.read_csv(file_path, index_col='Date', parse_dates=True)
                if existing_df.empty:
                    # File is empty, need full download
                    start_date = fresh_threshold - timedelta(days=DEFAULT_INITIAL_YEARS * 365)
                    logger.info(f"{symbol}: Initial download from {start_date.date()} to {fresh_threshold.date()}")
                    new_data_df, errors = download_stock_data(symbol, start_date, fresh_threshold)

                    # Log any errors from download
                    for error in errors:
                        logger.error(f"{symbol}: {error}")

                    if new_data_df is not None and not new_data_df.empty:
                        new_data_df.to_csv(file_path, date_format='%Y-%m-%d', index=False)
                        logger.info(f"{symbol}: Initial download SUCCESS")
                        return True, "initial_download"
                    else:
                        # Check for suspension only if download failed
                        suspended, status_str = is_suspended(symbol)
                        if suspended:
                            logger.info(f"{symbol}: Suspended ({status_str}), skipping further attempts.")
                            suspended_stocks.add(symbol)
                            return False, "suspended"
                        logger.error(f"{symbol}: Initial download FAILED")
                        return False, "download_failed"

                last_date = existing_df.index.max()

                # Check if already fresh
                if last_date.date() >= fresh_threshold.date():
                    return True, "already_fresh"

                # Need to update
                start_update_date = last_date + timedelta(days=1)
                if start_update_date > fresh_threshold:
                    return True, "already_fresh"

                logger.info(f"{symbol}: Update from {start_update_date.date()} to {fresh_threshold.date()}")
                new_data_df, errors = download_stock_data(symbol, start_update_date, fresh_threshold)

                # Log any errors from download
                for error in errors:
                    logger.error(f"{symbol}: {error}")

                if new_data_df is None:
                    # Check for suspension only if download failed
                    suspended, status_str = is_suspended(symbol)
                    if suspended:
                        logger.info(f"{symbol}: Suspended ({status_str}), skipping further attempts.")
                        suspended_stocks.add(symbol)
                        return False, "suspended"
                    logger.error(f"{symbol}: Update download FAILED")
                    return False, "download_failed"
                elif new_data_df.empty:
                    # Check if this is because no new data exists or data processing failed
                    if errors:
                        logger.error(f"{symbol}: Update FAILED - {errors}")
                        return False, "download_failed"
                    else:
                        logger.info(f"{symbol}: No new data available")
                        return True, "no_new_data"
                else:
                    # Combine old and new data
                    combined_df = pd.concat([existing_df, new_data_df])
                    combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
                    combined_df.sort_index(inplace=True)
                    combined_df.to_csv(file_path, date_format='%Y-%m-%d', index=False)
                    logger.info(f"{symbol}: Update SUCCESS")
                    return True, "updated"

            except Exception as e:
                logger.error(f"{symbol}: File error - {e}")
                return False, f"file_error: {e}"
        else:
            # File doesn't exist, perform initial download
            start_date = fresh_threshold - timedelta(days=DEFAULT_INITIAL_YEARS * 365)
            logger.info(f"{symbol}: Initial download from {start_date.date()} to {fresh_threshold.date()}")
            new_data_df, errors = download_stock_data(symbol, start_date, fresh_threshold)

            # Log any errors from download
            for error in errors:
                logger.error(f"{symbol}: {error}")

            if new_data_df is not None and not new_data_df.empty:
                new_data_df.to_csv(file_path, date_format='%Y-%m-%d', index=False)
                logger.info(f"{symbol}: Initial download SUCCESS")
                return True, "initial_download"
            else:
                # Check for suspension only if download failed
                suspended, status_str = is_suspended(symbol)
                if suspended:
                    logger.info(f"{symbol}: Suspended ({status_str}), skipping further attempts.")
                    suspended_stocks.add(symbol)
                    return False, "suspended"
                logger.error(f"{symbol}: Initial download FAILED")
                return False, "download_failed"

    except Exception as e:
        logger.error(f"{symbol}: Unexpected error - {e}")
        return False, f"error: {e}"


def continuous_sync():
    """
    Continuously sync data until all stocks are fresh
    """
    ensure_data_dir()

    logger.info("Starting continuous sync loop")

    while True:
        try:
            stocks = get_stock_list()  # Reload every cycle
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Error: {e}")
            return

        fresh_threshold = get_fresh_data_threshold()

        # Track results for this cycle
        cycle_stats = {
            "fresh": 0,
            "updated": 0,
            "initial_download": 0,
            "no_new_data": 0,
            "failed": 0,
            "file_error": 0,
            "suspended": 0
        }

        # Check which stocks need syncing, excluding suspended
        stocks_to_sync = []
        for symbol in stocks:
            if symbol in suspended_stocks:
                cycle_stats["suspended"] += 1
                continue
            file_path = get_stock_file_path(symbol)
            if not is_data_fresh(file_path, fresh_threshold):
                stocks_to_sync.append(symbol)
            else:
                cycle_stats["fresh"] += 1

        if not stocks_to_sync:
            next_check = datetime.now() + timedelta(hours=24)
            logger.info(f"All stocks fresh. Sleeping 24 hours until {next_check.strftime('%Y-%m-%d %H:%M:%S')}")
            time.sleep(24 * 60 * 60)  # Sleep for 24 hours
            continue

        logger.info(f"Cycle: Syncing {len(stocks_to_sync)} stocks")

        # Sync stocks that need updating
        for i, symbol in enumerate(stocks_to_sync, 1):
            success, status = sync_single_stock(symbol, fresh_threshold)

            if success:
                if status in cycle_stats:
                    cycle_stats[status] += 1
                else:
                    cycle_stats["updated"] += 1
            else:
                if status == "suspended":
                    cycle_stats["suspended"] += 1
                elif "file_error" in status:
                    cycle_stats["file_error"] += 1
                else:
                    cycle_stats["failed"] += 1

            # Random delay between stocks to avoid overwhelming the API
            time.sleep(random.uniform(3, 5))

        # Print cycle summary
        logger.info(f"Cycle Summary - Fresh: {cycle_stats['fresh']}, Updated: {cycle_stats['updated']}, "
                   f"Initial: {cycle_stats['initial_download']}, No Data: {cycle_stats['no_new_data']}, "
                   f"Failed: {cycle_stats['failed']}, File Errors: {cycle_stats['file_error']}, Suspended: {cycle_stats['suspended']}")


def main():
    """Main function"""
    try:
        continuous_sync()
    except KeyboardInterrupt:
        logger.info("Continuous sync interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Continuous sync failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
