"""
Dynamic Sector Strength Engine
Automatically detects strong and weak NSE sectors using real momentum data.
"""

import os
import time
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# Define the NSE sector indices and their corresponding Yahoo Finance tickers.
# If a ticker is not available on yfinance, it can be left as None or mapped to a proxy ETF if needed.
SECTOR_INDEX_MAP = {
    "Auto": "^CNXAUTO",
    "Bank": "^NSEBANK",
    "Financial Services": "^CNXFIN",
    "FMCG": "^CNXFMCG",
    "Healthcare": "^CNXPHARMA", # Using Pharma as common proxy for healthcare on yfinance
    "IT": "^CNXIT",
    "Media": "^CNXMEDIA",
    "Metal": "^CNXMETAL",
    "Pharma": "^CNXPHARMA",
    "PSU Bank": "^CNXPSUBANK",
    "Realty": "^CNXREALTY",
    "Private Bank": "NIFTY_PVT_BANK.NS", # Sometimes works, otherwise will be handled by exception
    "Consumer Durables": "^CNXCONSUM",
    "Oil and Gas": "^CNXENERGY", # Proxy using broader energy
    # Cement, Chemicals, etc. lack direct yf indices so we omit their raw fetch if missing,
    # but the structure allows adding them if available.
}

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "sector_strength.csv")

# Global state to hold the calculated sector strengths
_SECTOR_STRENGTH_CACHE = None

def fetch_sector_data(ticker: str, retries: int = 3) -> pd.DataFrame:
    """
    Fetch at least 3 months (90 days) of daily OHLCV data for a sector index.
    Includes retry-safe logic and failed download handling.
    """
    for attempt in range(retries):
        try:
            # We fetch 6 months to ensure we have enough trading days for a 3-month (60 trading days) lookback
            df = yf.download(ticker, period="6mo", progress=False)
            if df is not None and not df.empty:
                # Yahoo finance returns MultiIndex columns sometimes in latest versions, flatten them
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [col[0] for col in df.columns]
                return df
        except Exception as e:
            time.sleep(1)
            continue
    return pd.DataFrame()


def calculate_sector_returns(df: pd.DataFrame) -> tuple:
    """
    Calculate 1-month (20 trading days) and 3-month (60 trading days) returns.
    Formula: Return = ((CurrentPrice - PastPrice) / PastPrice) * 100
    """
    if len(df) < 60:
        return None, None
    
    # We use 'Close' price for return calculations, handle NaN
    close_prices = df['Close'].dropna()
    
    if len(close_prices) < 60:
        return None, None

    current_price = float(close_prices.iloc[-1])
    price_1_month_ago = float(close_prices.iloc[-20])
    price_3_months_ago = float(close_prices.iloc[-60])
    
    one_month_return = ((current_price - price_1_month_ago) / price_1_month_ago) * 100
    three_month_return = ((current_price - price_3_months_ago) / price_3_months_ago) * 100
    
    return one_month_return, three_month_return


def calculate_sector_strength(one_month: float, three_month: float) -> float:
    """
    Calculate weighted sector strength scoring.
    SectorStrength = (0.7 * OneMonthReturn) + (0.3 * ThreeMonthReturn)
    Reason: Prioritize recent momentum while considering medium-term trend.
    """
    return (0.7 * one_month) + (0.3 * three_month)


def rank_sectors(results: list) -> pd.DataFrame:
    """
    Rank all sectors dynamically from strongest to weakest based on strength score.
    Returns a pandas DataFrame containing the required columns.
    """
    df = pd.DataFrame(results)
    if df.empty:
        return df
        
    df = df.sort_values(by="strength_score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    return df


def classify_sectors(df: pd.DataFrame) -> pd.DataFrame:
    """
    Automatically classify sectors:
    - Top 3 sectors -> STRONG
    - Bottom 3 sectors -> WEAK
    - Remaining sectors -> NEUTRAL
    """
    if df.empty:
        return df
        
    n_sectors = len(df)
    
    def get_class(rank):
        if rank <= 3:
            return "STRONG"
        elif rank > n_sectors - 3:
            return "WEAK"
        else:
            return "NEUTRAL"
            
    df["classification"] = df["rank"].apply(get_class)
    return df


def run_sector_analysis() -> pd.DataFrame:
    """
    Orchestrates the downloading, calculation, ranking, and classification.
    Also handles caching for daily automated execution.
    """
    global _SECTOR_STRENGTH_CACHE
    
    # Simple caching layer: if we already ran it today, use the cache
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    if os.path.exists(CACHE_FILE):
        mtime = datetime.fromtimestamp(os.path.getmtime(CACHE_FILE))
        if mtime.date() == datetime.today().date():
            try:
                df = pd.read_csv(CACHE_FILE)
                _SECTOR_STRENGTH_CACHE = df
                return df
            except:
                pass

    results = []
    
    for sector_name, ticker in SECTOR_INDEX_MAP.items():
        if not ticker:
            continue
            
        df = fetch_sector_data(ticker)
        
        one_m, three_m = calculate_sector_returns(df)
        if one_m is None or three_m is None:
            continue # Skip if failed or insufficient data
            
        strength = calculate_sector_strength(one_m, three_m)
        current_price = float(df['Close'].dropna().iloc[-1])
        
        results.append({
            "sector": sector_name,
            "current_price": round(current_price, 2),
            "1_month_return": round(one_m, 2),
            "3_month_return": round(three_m, 2),
            "strength_score": round(strength, 2),
        })
        
    # Process the final DataFrame
    ranked_df = rank_sectors(results)
    final_df = classify_sectors(ranked_df)
    
    # Cache the result as CSV (Optional advanced requirement met)
    if not final_df.empty:
        final_df.to_csv(CACHE_FILE, index=False)
        _SECTOR_STRENGTH_CACHE = final_df
        
    return final_df


def get_sector_bias(sector_name: str) -> int:
    """
    Main entry point for the scoring engine.
    - return +1 for STRONG sectors
    - return -1 for WEAK sectors
    - return 0 for NEUTRAL or unknown sectors
    """
    global _SECTOR_STRENGTH_CACHE
    
    # Initialization on first run
    if _SECTOR_STRENGTH_CACHE is None or _SECTOR_STRENGTH_CACHE.empty:
        run_sector_analysis()
        
    if _SECTOR_STRENGTH_CACHE is None or _SECTOR_STRENGTH_CACHE.empty:
        return 0
        
    # Match sector name (case-insensitive)
    match = _SECTOR_STRENGTH_CACHE[_SECTOR_STRENGTH_CACHE["sector"].str.lower() == sector_name.lower()]
    
    if match.empty:
        return 0
        
    classification = match.iloc[0]["classification"]
    
    if classification == "STRONG":
        return 1
    elif classification == "WEAK":
        return -1
    else:
        return 0
