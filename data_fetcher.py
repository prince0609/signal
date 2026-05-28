"""
HMA Stock Scanner — Data Fetcher
Fetches OHLCV and delivery data from NSE via nsepython.
"""

import time
import pandas as pd
from datetime import datetime, timedelta

from config import (
    DAILY_DATA_DAYS, CHUNK_SIZE_DAYS, REQUEST_DELAY,
    DELIVERY_LOOKBACK_DAYS, NIFTY_50,
)
from utils import (
    date_to_nse_format, generate_date_chunks,
    cache_get, cache_set,
)

def fetch_daily_data(symbol: str, days: int = None, use_cache: bool = True) -> pd.DataFrame:
    """
    Fetch daily OHLCV and Delivery data for a stock dynamically from the local raw Bhavcopy SQLite database.
    yfinance is completely removed for individual stock data.
    """
    if days is None:
        days = DAILY_DATA_DAYS

    # Check cache first to avoid repetitive DataFrame rebuilding
    if use_cache:
        cached = cache_get(symbol, "daily")
        if cached is not None:
            return cached

    # Query local SQLite database populated by bhavcopy_downloader
    try:
        from database import get_db_connection
        with get_db_connection() as conn:
            query = '''
            SELECT date as Date, open as Open, high as High, low as Low, close as Close, volume as Volume, delivery_pct as Delivery_Pct
            FROM daily_data
            WHERE symbol = ?
            ORDER BY date ASC
            '''
            df = pd.read_sql_query(query, conn, params=(symbol,))
            
        if df is None or df.empty:
            return None
            
        # Limit to the requested number of trading days
        if len(df) > days:
            df = df.tail(days)
            
    except Exception:
        return None

    # Parse date and set as index
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date')

    # Ensure numeric types
    cols = ["Open", "High", "Low", "Close", "Volume", "Delivery_Pct"]
    result = df[cols].copy()
    for c in cols:
        result[c] = pd.to_numeric(result[c], errors="coerce")

    result = result.dropna(subset=["Open", "High", "Low", "Close"])

    if use_cache and not result.empty:
        cache_set(symbol, "daily", result)

    return result


def fetch_delivery_data(symbol: str, days: int = None) -> float:
    """
    Fetch average delivery percentage for a stock.
    Returns average delivery % over last N days, or None if unavailable.
    """
    if days is None:
        days = DELIVERY_LOOKBACK_DAYS

    # Check cache
    cached = cache_get(symbol, "delivery")
    if cached is not None:
        return cached

    try:
        from nsepython import deliverable_position_data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        df = deliverable_position_data(
            symbol,
            date_to_nse_format(start_date),
            date_to_nse_format(end_date),
        )

        if df is None or df.empty:
            return None

        # Find the delivery percentage column (name varies)
        del_col = None
        for col in df.columns:
            col_lower = col.lower()
            if "deliv" in col_lower and ("traded" in col_lower or "%" in col_lower):
                del_col = col
                break

        if del_col is None:
            # Try alternative column names
            for col in df.columns:
                if "COP_DELIV" in col.upper():
                    del_col = col
                    break

        if del_col is None:
            return None

        values = pd.to_numeric(df[del_col], errors="coerce").dropna()
        if values.empty:
            return None

        avg = float(values.mean())
        cache_set(symbol, "delivery", avg)
        return avg

    except Exception:
        return None


def resample_to_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Convert daily OHLCV to weekly candles."""
    if daily_df is None or daily_df.empty:
        return None

    weekly = daily_df.resample("W").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }).dropna()

    return weekly


def get_stock_list(universe: str = "nifty50") -> list:
    """
    Get list of stock symbols for scanning.
    Supports: nifty50, nifty200, nifty500, or comma-separated custom symbols.
    """
    universe = universe.lower().strip()

    if universe == "nifty50":
        return NIFTY_50

    # Support scanning all symbols present in the local DB
    if universe == "all":
        try:
            from database import get_db_connection
            with get_db_connection() as conn:
                df = pd.read_sql_query("SELECT DISTINCT symbol FROM daily_data ORDER BY symbol", conn)
            if not df.empty:
                return [s.strip().upper() for s in df['symbol'].tolist()]
        except Exception:
            # Fall through to other methods if DB not available
            pass

    # Try niftystocks library for larger universes
    try:
        from niftystocks import ns
        if universe == "nifty200":
            return ns.get_nifty200()
        elif universe == "nifty500":
            return ns.get_nifty500()
    except ImportError:
        pass
    except Exception:
        pass

    # Custom comma-separated list
    if "," in universe:
        return [s.strip().upper() for s in universe.split(",")]

    # Fallback to Nifty 50
    return NIFTY_50
