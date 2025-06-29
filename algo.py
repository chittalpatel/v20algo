from datetime import date
from typing import Union, List
import pandas as pd
from config import DATA_DIR
from sync_data import get_stock_file_path
import os

class Price:
    def __init__(self, _date: Union[str, date], _open: float, close: float, low: float, high: float, volume:float, ma: float):
        self.date = date.fromisoformat(_date) if type(_date) == 'str' else _date
        self.open = _open
        self.close = close
        self.low = low
        self.high = high
        self.volume = volume
        self.ma = ma

    @property
    def is_green(self):
        return self.close > self.open

    @property
    def fdate(self):
        return self.date.strftime("%-d-%b-%Y")

    def __str__(self):
        return f"< Date {self.date} | Open {self.open} | Close {self.close} >"


def get_daily_price(stock: str, days: int) -> List[Price]:
    file_path = get_stock_file_path(stock)
    if not os.path.exists(file_path):
        return []
    data = pd.read_csv(file_path, index_col='Date', parse_dates=True)

    # Read extra data to ensure we have enough for MA calculation
    # We need at least 200 days + the requested days
    required_data_points = days + 200

    if len(data) < required_data_points:
        # If we don't have enough data, use all available data
        data_for_ma = data
    else:
        # Take the most recent required_data_points
        data_for_ma = data.tail(required_data_points)

    # Calculate 200-day moving average
    data_for_ma['MA'] = data_for_ma['Close'].rolling(200).mean().round(2)

    # Remove rows where MA is NaN (first 199 rows)
    data_with_ma = data_for_ma.dropna(subset=['MA'])

    # Take the last 'days' rows that have valid MA
    final_data = data_with_ma.tail(days)

    clean_data = []
    for idx, row in final_data.iterrows():
        clean_data.append(
            Price(
                _date=idx.date(),
                _open=row['Open'],
                close=row['Close'],
                low=row['Low'],
                high=row['High'],
                volume=row['Volume'],
                ma=row['MA'],
            )
        )
    return clean_data


class Algo:
    def __init__(self, stock: str, history: int, margin: int = 20, filter_by_last_close: bool = True, last_close_margin: int = 5):
        self.stock = stock
        self.prices = get_daily_price(stock, history)
        self.n = len(self.prices)
        self.margin = margin
        self.filter_by_last_close = filter_by_last_close
        self.last_close_margin = last_close_margin
        self.ans = []

    def _run(self, start: int):
        end = start + 1
        low = self.prices[start]
        high = self.prices[start]
        valid = False
        profit_potential = None  # To store profit potential
        while end < self.n and self.prices[end].is_green:
            if self.prices[end].low < low.low:
                low = self.prices[end]
            if self.prices[end].high > high.high:
                high = self.prices[end]
            end += 1
        v20margin = 100 * (high.high/low.low - 1)
        if v20margin > self.margin:
            close = self.prices[-1].close
            profit_potential = 100 * (high.high/close - 1)
            if self.filter_by_last_close:
                close_margin = 100 * (close/low.low - 1)
                if close_margin <= self.last_close_margin:
                    valid = True
                else:
                    valid = False
            else:
                valid = True
        if valid:
            # Find the buy date: first day after 'end' where price's low <= low.low
            buy_date = None
            for i in range(end, self.n):
                if self.prices[i].low <= low.low:
                    buy_date = self.prices[i].fdate
                    break
            self.ans.append({
                'stock': self.stock,
                'profit_margin': round(profit_potential, 2) if profit_potential is not None else None,
                'v20margin': round(v20margin, 2),
                'ma': round(self.prices[start-1].ma, 2),
                'low_date': low.fdate,
                'low_price': round(low.low, 2),
                'high_date': high.fdate,
                'high_price': round(high.high, 2),
                'buy_date': buy_date
            })
        return end + 1

    def run_algo(self):
        start = 1
        while start < self.n:
            if self.prices[start].is_green:
                start = self._run(start)
            else:
                start += 1
        return self.ans
