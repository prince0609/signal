"""
NSE Raw Bhavcopy Downloader
Downloads daily Bhavcopy CSV and MTO Delivery files securely and archives them to local SQLite.
"""

import os
import io
import time
import zipfile
import requests
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from rich.console import Console
from rich.progress import track

from database import get_db_connection, cleanup_old_data

console = Console()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
}

def get_bhavcopy_url(date_obj: datetime) -> str:
    """Format: https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip"""
    date_str = date_obj.strftime("%Y%m%d")
    return f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip"

def get_mto_url(date_obj: datetime) -> str:
    """Format: https://archives.nseindia.com/archives/equities/mto/MTO_DDMMYYYY.DAT"""
    date_str = date_obj.strftime("%d%m%Y")
    return f"https://archives.nseindia.com/archives/equities/mto/MTO_{date_str}.DAT"

def process_date(date_obj: datetime, session: requests.Session) -> bool:
    """
    Downloads Bhavcopy and MTO for a specific date, merges them, and saves to SQLite.
    Returns True if data was found and saved, False if no data (e.g., weekend/holiday).
    """
    bhav_url = get_bhavcopy_url(date_obj)
    mto_url = get_mto_url(date_obj)
    date_db_str = date_obj.strftime("%Y-%m-%d")

    try:
        # 1. Fetch Bhavcopy
        res = session.get(bhav_url, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return False # Probably a holiday or weekend

        # Ensure it's a zip file
        try:
            z = zipfile.ZipFile(io.BytesIO(res.content))
            with z.open(z.namelist()[0]) as f:
                bhav_df = pd.read_csv(f)
        except Exception:
            return False

        # Filter only common equities
        if "Sgmt" in bhav_df.columns:
            bhav_df = bhav_df[(bhav_df['Sgmt'] == 'CM') & (bhav_df['SctySrs'].isin(['EQ', 'BE']))]
        elif "SERIES" in bhav_df.columns: # Older format fallback just in case
            bhav_df = bhav_df[bhav_df['SERIES'].isin(['EQ', 'BE'])]

        # Map to standard ticker symbol
        sym_col = "TckrSymb" if "TckrSymb" in bhav_df.columns else "SYMBOL"
        open_col = "OpnPric" if "OpnPric" in bhav_df.columns else "OPEN"
        high_col = "HghPric" if "HghPric" in bhav_df.columns else "HIGH"
        low_col = "LwPric" if "LwPric" in bhav_df.columns else "LOW"
        close_col = "ClsPric" if "ClsPric" in bhav_df.columns else "CLOSE"
        vol_col = "TtlTradgVol" if "TtlTradgVol" in bhav_df.columns else "TOTTRDQTY"

        # Construct final df
        df = pd.DataFrame({
            'date': date_db_str,
            'symbol': bhav_df[sym_col].astype(str).str.strip(),
            'open': pd.to_numeric(bhav_df[open_col], errors='coerce'),
            'high': pd.to_numeric(bhav_df[high_col], errors='coerce'),
            'low': pd.to_numeric(bhav_df[low_col], errors='coerce'),
            'close': pd.to_numeric(bhav_df[close_col], errors='coerce'),
            'volume': pd.to_numeric(bhav_df[vol_col], errors='coerce'),
        })

        # 2. Fetch MTO Delivery Data
        delivery_dict = {}
        try:
            mto_res = session.get(mto_url, headers=HEADERS, timeout=10)
            if mto_res.status_code == 200:
                lines = mto_res.text.strip().split('\n')
                for line in lines[4:]: # Skip headers
                    parts = line.split(',')
                    if len(parts) >= 6 and parts[0] == '20' and parts[3] == 'EQ':
                        symbol = parts[2].strip()
                        deliv_pct = parts[-1].strip()
                        try:
                            delivery_dict[symbol] = float(deliv_pct)
                        except ValueError:
                            pass
        except Exception:
            pass # Ignore MTO errors

        df['delivery_pct'] = df['symbol'].map(delivery_dict).fillna(0.0)

        # Drop NaN
        df = df.dropna(subset=['open', 'high', 'low', 'close'])

        # 3. Save to database directly
        if not df.empty:
            records = df.to_records(index=False).tolist()
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(
                    "INSERT OR IGNORE INTO daily_data (date, symbol, open, high, low, close, volume, delivery_pct) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    records
                )
                conn.commit()
            return True

    except Exception:
        pass
        
    return False

def sync_database(days_back: int = 400):
    """
    Downloads all missing dates up to `days_back` into SQLite. 400 days covers approx 270 trading days.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    # Generate list of dates to check
    all_dates = [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]
    all_dates.reverse() # Start from today and go backwards

    # Filter out dates already in DB
    existing_dates = set()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT date FROM daily_data")
        for row in cursor.fetchall():
            existing_dates.add(row[0])

    dates_to_fetch = [d for d in all_dates if d.strftime("%Y-%m-%d") not in existing_dates and d.weekday() < 5] # Only weekdays

    if not dates_to_fetch:
        console.print("[dim green]Database is already fully synchronized.[/dim green]")
        return

    console.print(f"[cyan]Found {len(dates_to_fetch)} potential trading days to synchronize.[/cyan]")
    
    session = requests.Session()
    
    successful_days = 0
    # Try downloading
    for d in track(dates_to_fetch, description="Synchronizing Bhavcopies..."):
        success = process_date(d, session)
        if success:
            successful_days += 1
        time.sleep(1.0) # Prevent rate-limiting from NSE

    console.print(f"[bold green]Data synchronized successfully! Downloaded {successful_days} trading days.[/bold green]")
    
    # Keep DB lean: Delete data older than 410 trading days
    removed = cleanup_old_data(410)
    if removed > 0:
        console.print(f"[dim]Cleaned up old records from database.[/dim]")

if __name__ == "__main__":
    sync_database(5)
