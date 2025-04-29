from datetime import date
from typing import Union, List
import pandas as pd
from config import DATA_DIR


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
    file_path = DATA_DIR / f"{stock}.csv"
    data = pd.read_csv(file_path, index_col='Date', parse_dates=True)
    clean_data = []
    for idx, row in data.tail(days).iterrows():
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
        while end < self.n and self.prices[end].is_green:
            if self.prices[end].low < low.low:
                low = self.prices[end]
            if self.prices[end].high > high.high:
                high = self.prices[end]
            end += 1
        margin = 100 * (high.high/low.low - 1)
        if margin > self.margin:
            if self.filter_by_last_close:
                close = self.prices[-1].close
                close_margin = 100 * (high.high/close - 1)
                if close_margin > self.last_close_margin:
                    valid = True
                else:
                    valid = False
            else:
                valid = True
        if valid:
            self.ans.append(f"{self.stock}|{self.prices[start].fdate}|{round(margin, 2)}%|{round(self.prices[start-1].ma, 2)}|{low.fdate}|{round(low.low, 2)}|{high.fdate}|{round(high.high, 2)}")
        return end + 1

    def run_algo(self):
        start = 1
        while start < self.n:
            if self.prices[start].is_green:
                start = self._run(start)
            else:
                start += 1
        return self.ans
