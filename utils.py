"""
HMA Stock Scanner — Utility Functions
Date helpers, caching, and progress display.
"""

import os
import pickle
import hashlib
from datetime import datetime, timedelta


# ─── Date Helpers ────────────────────────────────────────────────

def date_to_nse_format(dt: datetime) -> str:
    """Convert datetime to NSE date format: dd-mm-yyyy"""
    return dt.strftime("%d-%m-%Y")


def generate_date_chunks(start_date: datetime, end_date: datetime, chunk_days: int = 35):
    """Split a date range into chunks for NSE API (which limits ~40 days/request)."""
    chunks = []
    current = start_date
    while current < end_date:
        chunk_end = min(current + timedelta(days=chunk_days), end_date)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


# ─── Caching ─────────────────────────────────────────────────────

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
CACHE_EXPIRY_HOURS = 12


def _cache_key(symbol: str, data_type: str) -> str:
    """Generate a cache filename for a symbol and data type."""
    key = f"{symbol}_{data_type}_{datetime.now().strftime('%Y%m%d')}"
    return hashlib.md5(key.encode()).hexdigest() + ".pkl"


def cache_get(symbol: str, data_type: str):
    """Retrieve cached data if it exists and is fresh."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, _cache_key(symbol, data_type))
    if not os.path.exists(path):
        return None
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        if datetime.now() - mtime > timedelta(hours=CACHE_EXPIRY_HOURS):
            os.remove(path)
            return None
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def cache_set(symbol: str, data_type: str, data):
    """Store data in cache."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, _cache_key(symbol, data_type))
    try:
        with open(path, "wb") as f:
            pickle.dump(data, f)
    except Exception:
        pass


def clear_cache():
    """Remove all cached files."""
    if os.path.exists(CACHE_DIR):
        for f in os.listdir(CACHE_DIR):
            try:
                os.remove(os.path.join(CACHE_DIR, f))
            except Exception:
                pass


# ─── Formatting ──────────────────────────────────────────────────

def format_number(value, decimals=2):
    """Format a number with commas and decimal places."""
    if value is None:
        return "N/A"
    try:
        return f"{value:,.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def format_pct(value, decimals=1):
    """Format a percentage value."""
    if value is None:
        return "N/A"
    try:
        return f"{value:.{decimals}f}%"
    except (TypeError, ValueError):
        return str(value)


import requests

def send_telegram_message(message: str):
    """
    Sends a message to a Telegram chat via BOT API.
    Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception:
        return False
