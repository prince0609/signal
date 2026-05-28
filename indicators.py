"""
HMA Stock Scanner — Technical Indicators
Pure functions for HMA, RSI, MACD, OBV, and volume analysis.
"""

import numpy as np
import pandas as pd


# ─── Moving Averages ────────────────────────────────────────────

def wma(series: pd.Series, period: int) -> pd.Series:
    """Weighted Moving Average."""
    weights = np.arange(1, period + 1, dtype=float)
    return series.rolling(period).apply(
        lambda x: np.dot(x, weights) / weights.sum(), raw=True
    )


def hma(series: pd.Series, period: int) -> pd.Series:
    """Hull Moving Average: WMA(2*WMA(n/2) - WMA(n), sqrt(n))."""
    half_period = max(int(period / 2), 1)
    sqrt_period = max(int(np.sqrt(period)), 1)
    wma_half = wma(series, half_period)
    wma_full = wma(series, period)
    raw_hma = 2 * wma_half - wma_full
    return wma(raw_hma, sqrt_period)


def hma_slope(hma_series: pd.Series, lookback: int = 5) -> float:
    """HMA slope as percentage change over lookback periods."""
    clean = hma_series.dropna()
    if len(clean) < lookback + 1:
        return 0.0
    recent = clean.iloc[-lookback:]
    if recent.iloc[0] == 0:
        return 0.0
    return ((recent.iloc[-1] - recent.iloc[0]) / recent.iloc[0]) * 100


def hma_crossover_age(hma_fast: pd.Series, hma_slow: pd.Series) -> int:
    """Trading days since last bullish crossover (fast crossing above slow)."""
    aligned = pd.DataFrame({"fast": hma_fast, "slow": hma_slow}).dropna()
    if aligned.empty:
        return 999

    signal = (aligned["fast"] > aligned["slow"]).astype(int)
    crossovers = signal.diff()
    bullish = crossovers[crossovers == 1]

    if bullish.empty:
        return 999

    last_idx = bullish.index[-1]
    remaining = aligned.loc[last_idx:]
    return len(remaining) - 1


# ─── RSI ─────────────────────────────────────────────────────────

def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Standard RSI using exponential moving average of gains/losses."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ─── MACD ────────────────────────────────────────────────────────

def compute_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal_period: int = 9):
    """MACD returning (macd_line, signal_line, histogram)."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ─── OBV ─────────────────────────────────────────────────────────

def compute_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On Balance Volume."""
    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    return (volume * direction).cumsum()


def obv_slope(obv_series: pd.Series, lookback: int = 20) -> float:
    """OBV trend via linear regression slope over lookback periods."""
    clean = obv_series.dropna()
    if len(clean) < lookback:
        return 0.0
    recent = clean.iloc[-lookback:]
    x = np.arange(len(recent))
    coeffs = np.polyfit(x, recent.values.astype(float), 1)
    return coeffs[0]


# ─── Volume Analysis ────────────────────────────────────────────

def count_accumulation_distribution_days(df: pd.DataFrame, lookback: int = 20) -> dict:
    """Count accumulation (price up + high vol) and distribution days."""
    recent = df.iloc[-lookback:]
    if recent.empty:
        return {"accumulation": 0, "distribution": 0}

    avg_vol = recent["Volume"].mean()
    acc_days = 0
    dist_days = 0

    for _, row in recent.iterrows():
        high_vol = row["Volume"] > avg_vol
        if row["Close"] > row["Open"] and high_vol:
            acc_days += 1
        elif row["Close"] < row["Open"] and high_vol:
            dist_days += 1

    return {"accumulation": acc_days, "distribution": dist_days}


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Compute Average True Range (ATR) using True Range and simple Wilder smoothing (EMA-like).
    Returns an ATR series aligned with the input close index.
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    # Wilder's smoothing (exponential with alpha=1/period) approximated via ewm
    atr = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    return atr
