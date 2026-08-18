import logging
from datetime import datetime
from typing import Optional
import yfinance as yf
import pandas as pd

log = logging.getLogger(__name__)


def fetch(ticker: str, start_date: str, end_date: Optional[str] = None) -> pd.DataFrame:
    """Fetch daily close prices for a ticker between two dates.

    Returns a DataFrame indexed by date with a single 'close' column.
    Raises ValueError on empty result so the pipeline can retry with a different topic.
    """
    end_date = end_date or datetime.utcnow().strftime("%Y-%m-%d")
    log.info(f"Fetching {ticker} {start_date} → {end_date}")

    df = yf.download(
        ticker,
        start=start_date,
        end=end_date,
        interval="1d",
        auto_adjust=True,
        progress=False,
    )
    if df is None or df.empty:
        raise ValueError(f"No data returned for {ticker} {start_date}→{end_date}")

    # yfinance sometimes returns MultiIndex columns; flatten to just 'close'
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    close = df[["Close"]].rename(columns={"Close": "close"}).dropna()
    if close.empty:
        raise ValueError(f"All-NaN close series for {ticker}")

    log.info(f"Got {len(close)} rows, first={close.index[0].date()}, last={close.index[-1].date()}")
    return close


def portfolio_value(prices: pd.DataFrame, initial_investment: float) -> pd.Series:
    """Given a price series and starting $, return the portfolio value over time."""
    first = prices["close"].iloc[0]
    shares = initial_investment / first
    return prices["close"] * shares
