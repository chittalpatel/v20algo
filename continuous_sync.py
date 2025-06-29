import pandas as pd
from datetime import datetime, timedelta
import time
import sys
import random
import logging
import holidays
from datetime import date
from api import is_suspended
from config import DATA_DIR, STOCKS_FILE, DEFAULT_INITIAL_YEARS, MASTER_STOCKS_FILE
from data import StockData

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


def get_stock_list():
    """Read stock symbols from stocks.txt and master file."""
    def _get_stock_list(file_path):
        if not file_path.exists():
            raise FileNotFoundError(f"Stock list file '{file_path}' not found. Please create it.")
        with open(file_path, 'r') as f:
            stocks = sorted(list(set([line.strip().upper() for line in f if line.strip()])))
        if not stocks:
            raise ValueError(f"Stock list file '{file_path}' is empty.")
        return stocks
    return list(set(_get_stock_list(STOCKS_FILE) + _get_stock_list(MASTER_STOCKS_FILE)))


def ensure_data_dir():
    """Ensure data directory exists"""
    DATA_DIR.mkdir(exist_ok=True)


def get_previous_trading_day(target_date=None):
    """
    Get the previous trading day, accounting for weekends and Indian holidays.
    """
    if target_date is None:
        target_date = datetime.now().date()
    current_date = target_date
    for _ in range(5):
        current_date = current_date - timedelta(days=1)
        if current_date.weekday() >= 5:
            continue
        if current_date in indian_holidays:
            continue
        return datetime.combine(current_date, datetime.min.time())
    logger.warning(f"Could not find previous trading day within 5 days of {target_date}")
    return datetime.combine(target_date, datetime.min.time())


def get_fresh_data_threshold():
    today = datetime.now().date()
    previous_trading_day = get_previous_trading_day(today)
    return previous_trading_day


def sync_single_stock(symbol, fresh_threshold):
    """
    Sync a single stock using StockData.
    """
    if symbol in suspended_stocks:
        return False, "suspended"
    stock_data = StockData(symbol)
    try:
        if stock_data.is_fresh(fresh_threshold):
            return True, "already_fresh"
        status, message = stock_data.update_to_date(fresh_threshold, DEFAULT_INITIAL_YEARS)
        if status == 'initial_download':
            logger.info(f"{symbol}: {message}")
            return True, "initial_download"
        elif status == 'updated':
            logger.info(f"{symbol}: {message}")
            return True, "updated"
        elif status == 'no_new_data':
            logger.info(f"{symbol}: {message}")
            return True, "no_new_data"
        elif status == 'already_up_to_date':
            return True, "already_fresh"
        else:
            # Check for suspension only if download failed
            suspended, status_str = is_suspended(symbol)
            if suspended:
                logger.info(f"{symbol}: Suspended ({status_str}), skipping further attempts.")
                suspended_stocks.add(symbol)
                return False, "suspended"
            logger.error(f"{symbol}: {message}")
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
        cycle_stats = {
            "fresh": 0,
            "updated": 0,
            "initial_download": 0,
            "no_new_data": 0,
            "failed": 0,
            "file_error": 0,
            "suspended": 0
        }
        stocks_to_sync = []
        for symbol in stocks:
            if symbol in suspended_stocks:
                cycle_stats["suspended"] += 1
                continue
            stock_data = StockData(symbol)
            if not stock_data.is_fresh(fresh_threshold):
                stocks_to_sync.append(symbol)
            else:
                cycle_stats["fresh"] += 1
        if not stocks_to_sync:
            next_check = datetime.now() + timedelta(hours=24)
            logger.info(f"All stocks fresh. Sleeping 24 hours until {next_check.strftime('%Y-%m-%d %H:%M:%S')}")
            time.sleep(24 * 60 * 60)
            continue
        logger.info(f"Cycle: Syncing {len(stocks_to_sync)} stocks")
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
        logger.info(f"Cycle Summary - Fresh: {cycle_stats['fresh']}, Updated: {cycle_stats['updated']}, "
                   f"Initial: {cycle_stats['initial_download']}, No Data: {cycle_stats['no_new_data']}, "
                   f"Failed: {cycle_stats['failed']}, File Errors: {cycle_stats['file_error']}, Suspended: {cycle_stats['suspended']}")

def main():
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
