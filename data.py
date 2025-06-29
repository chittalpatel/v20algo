import pandas as pd
from datetime import datetime, timedelta, date
from config import DATA_DIR, DEFAULT_INITIAL_YEARS
from api import equity_history
import os
import numpy as np
import re

class StockData:
    def __init__(self, stock: str):
        self.stock = stock
        self.file_path = self.get_stock_file_path()

    def get_stock_file_path(self):
        file_safe_symbol = self.stock.replace('&', '-')
        return DATA_DIR / f"{file_safe_symbol}.csv"

    def load(self):
        """Load stock data from CSV, return DataFrame or None if not exists/empty."""
        if not self.file_path.exists():
            return None
        try:
            df = pd.read_csv(self.file_path, index_col='Date', parse_dates=True)
            if df.empty:
                return None
            return df
        except Exception:
            return None

    def save(self, df: pd.DataFrame):
        """Save DataFrame to CSV."""
        df.to_csv(self.file_path, date_format='%Y-%m-%d', index=True)

    def is_fresh(self, fresh_threshold: datetime):
        """Check if the data is fresh (last date >= fresh_threshold)."""
        df = self.load()
        if df is None or df.empty:
            return False
        last_date = df.index.max()
        return last_date.date() >= fresh_threshold.date()

    def _apply_corporate_actions(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Adjusts the DataFrame for splits and bonuses using the 'CA' column.
        The 'CA' column contains either nan or a list of dicts with 'subject' and 'exDate'.
        """
        if 'CA' not in df.columns:
            return df
        # Collect all actions
        actions = []
        for idx, ca_cell in df['CA'].items():
            # Robustly skip empty/invalid ca_cell
            skip = False
            if ca_cell is None:
                skip = True
            elif isinstance(ca_cell, float) and np.isnan(ca_cell):
                skip = True
            elif isinstance(ca_cell, (list, dict)) and not ca_cell:
                skip = True
            elif isinstance(ca_cell, str) and ca_cell.strip() == '':
                skip = True
            if skip:
                continue
            # If already a list/dict, use as is, else try to eval
            ca_list = ca_cell
            if isinstance(ca_list, str):
                try:
                    ca_list = eval(ca_list)
                except Exception:
                    continue
            if not isinstance(ca_list, list):
                ca_list = [ca_list]
            for ca in ca_list:
                if not isinstance(ca, dict):
                    continue
                subject = ca.get('subject', '')
                ex_date = ca.get('exDate', None)
                if not ex_date or not subject:
                    continue
                try:
                    ex_date_dt = pd.to_datetime(ex_date, errors='coerce')
                except Exception:
                    continue
                if pd.isna(ex_date_dt):
                    continue
                # Split
                if 'Face Value Split' in subject:
                    m = re.search(r'From Rs ([\d\.]+)[^\d]+To (Re|Rs) ([\d\.]+)', subject)
                    if m:
                        from_val = float(m.group(1))
                        to_val = float(m.group(3))
                        if from_val > 0 and to_val > 0 and from_val != to_val:
                            actions.append({
                                'type': 'split',
                                'ex_date': ex_date_dt,
                                'ratio': from_val / to_val
                            })
                # Bonus
                elif 'Bonus' in subject:
                    m = re.search(r'Bonus (\d+):(\d+)', subject)
                    if m:
                        bonus_num = int(m.group(1))
                        bonus_den = int(m.group(2))
                        if bonus_den > 0:
                            actions.append({
                                'type': 'bonus',
                                'ex_date': ex_date_dt,
                                'ratio': (bonus_num + bonus_den) / bonus_den
                            })
        # Sort actions by ex_date ascending
        actions.sort(key=lambda x: x['ex_date'])
        # Apply each action in order
        for action in actions:
            mask = df.index < action['ex_date']
            ratio = action['ratio']
            df.loc[mask, ['Open', 'High', 'Low', 'Close']] = df.loc[mask, ['Open', 'High', 'Low', 'Close']] / ratio
            df.loc[mask, 'Volume'] = df.loc[mask, 'Volume'] * ratio
        # Remove CA column
        df = df.drop(columns=['CA'])
        return df

    def download(self, start_date: date, end_date: date):
        """Download stock data using equity_history, return DataFrame and errors."""
        start_date_str = start_date.strftime('%d-%m-%Y')
        end_date_str = end_date.strftime('%d-%m-%Y')
        errors = []
        try:
            df = equity_history(self.stock, series="EQ", start_date=start_date_str, end_date=end_date_str)
            if df.empty:
                errors.append(f"No data returned for {self.stock} in the specified period.")
                return None, errors
            # Standardize columns
            column_mapping = {
                'CH_TIMESTAMP': 'Date',
                'CH_OPENING_PRICE': 'Open',
                'CH_TRADE_HIGH_PRICE': 'High',
                'CH_TRADE_LOW_PRICE': 'Low',
                'CH_CLOSING_PRICE': 'Close',
                'CH_TOT_TRADED_QTY': 'Volume'
            }
            ohlcv_columns = list(column_mapping.keys())
            if not all(col in df.columns for col in ohlcv_columns):
                errors.append(f"Expected columns not found in data for {self.stock}.")
                return None, errors
            df = df[ohlcv_columns + ['CA']] if 'CA' in df.columns else df[ohlcv_columns]
            df = df.rename(columns=column_mapping)
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
            numeric_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '', regex=False), errors='coerce')
            df.dropna(subset=['Open', 'High', 'Low', 'Close', 'Volume'], inplace=True)
            df.sort_values(by='Date', inplace=True)
            df = df.set_index('Date')
            # Apply corporate actions
            df = self._apply_corporate_actions(df)
            return df, errors
        except Exception as e:
            errors.append(f"Error downloading data for {self.stock}: {e}")
            import traceback
            print(traceback.format_exc())
            return None, errors

    def update_to_date(self, target_date: datetime, initial_years=DEFAULT_INITIAL_YEARS):
        """
        Ensure data is up to date to target_date. Handles initial download and incremental update.
        Returns (status, message)
        """
        df = self.load()
        if df is None:
            # Initial download
            start_date = target_date.date() - timedelta(days=initial_years * 365)
            new_df, errors = self.download(start_date, target_date.date())
            if new_df is not None and not new_df.empty:
                self.save(new_df)
                return 'initial_download', f"Initial download successful for {self.stock}"
            else:
                return 'failed', f"Initial download failed for {self.stock}: {errors}"
        else:
            last_date = df.index.max()
            if last_date.date() >= target_date.date():
                return 'already_up_to_date', f"{self.stock} already up to date."
            start_update_date = last_date.date() + timedelta(days=1)
            if start_update_date > target_date.date():
                return 'already_up_to_date', f"{self.stock} already up to date."
            new_df, errors = self.download(start_update_date, target_date.date())
            if new_df is None:
                return 'failed', f"Update download failed for {self.stock}: {errors}"
            elif new_df.empty:
                return 'no_new_data', f"No new data for {self.stock}"
            else:
                combined_df = pd.concat([df, new_df])
                combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
                combined_df.sort_index(inplace=True)
                self.save(combined_df)
                return 'updated', f"Update successful for {self.stock}"
