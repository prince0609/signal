"""
Database setup for local NSE historical data.
"""
import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nse_history.db")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Table for daily OHLCV and Delivery percentages
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_data (
                date TEXT,
                symbol TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                delivery_pct REAL,
                PRIMARY KEY (symbol, date)
            )
        ''')
        # Index on symbol + date for fast lookups during scanning
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol_date ON daily_data(symbol, date ASC)')
        conn.commit()

@contextmanager
def get_db_connection():
    init_db()  # Ensure table exists before any query
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()

def get_latest_date_in_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(date) FROM daily_data")
        res = cursor.fetchone()
        return res[0] if res else None

def get_db_size():
    if os.path.exists(DB_PATH):
        return os.path.getsize(DB_PATH) / (1024 * 1024)
    return 0.0

def cleanup_old_data(days_to_keep: int = 410):
    """
    Deletes records older than the last N distinct trading dates to keep the DB size lean.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Find the N-th latest distinct trading date
        cursor.execute("SELECT DISTINCT date FROM daily_data ORDER BY date DESC LIMIT 1 OFFSET ?", (days_to_keep - 1,))
        res = cursor.fetchone()
        
        if res:
            threshold_date = res[0]
            # Delete everything strictly older than that threshold
            cursor.execute("DELETE FROM daily_data WHERE date < ?", (threshold_date,))
            conn.commit()
            return cursor.rowcount
    return 0

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
    removed = cleanup_old_data(410)
    if removed > 0:
        print(f"Cleaned up {removed} old records.")
