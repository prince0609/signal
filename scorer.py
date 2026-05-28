"""
HMA Stock Scanner — Scoring Engine
Implements ALL 12 scoring rules. No rule is skipped.
"""

import pandas as pd
import numpy as np

from indicators import (
    hma, hma_slope, hma_crossover_age,
    compute_rsi, compute_macd, compute_obv, obv_slope,
    count_accumulation_distribution_days, compute_atr,
)
from config import (
    HMA_FAST_PERIOD, HMA_SLOW_PERIOD, RSI_PERIOD,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    OBV_SLOPE_LOOKBACK, HMA_SLOPE_LOOKBACK, VOLUME_LOOKBACK,
    RSI_MIN, RSI_MAX, OVEREXTENSION_THRESHOLD,
    STOP_LOSS_MULTIPLIER, MAX_RISK_PCT,
    FRESHNESS_TIER1_DAYS, FRESHNESS_TIER2_DAYS,
    HIGH_CONVICTION_MIN, WATCHLIST_MIN,
    SYMBOL_SECTOR_MAP,
)
from sector_strength import get_sector_bias


# ─── Rule 1: Weekly Trend Filter ────────────────────────────────

def weekly_trend_filter(weekly_df: pd.DataFrame) -> dict:
    """
    Classify stock into Bullish / Neutral / Bearish tier
    based on weekly HMA20 vs HMA55 and HMA20 slope.
    """
    close = weekly_df["Close"]
    hma20 = hma(close, HMA_FAST_PERIOD)
    hma55 = hma(close, HMA_SLOW_PERIOD)

    hma20_clean = hma20.dropna()
    hma55_clean = hma55.dropna()

    # If there is insufficient weekly data to compute HMAs, return 'Insufficient'
    if hma20_clean.empty or hma55_clean.empty:
        return {
            "tier": "Insufficient",
            "hma20": float(hma20_clean.iloc[-1]) if not hma20_clean.empty else 0.0,
            "hma55": float(hma55_clean.iloc[-1]) if not hma55_clean.empty else 0.0,
            "hma20_slope": 0.0,
            "hma55_series": hma55,
        }

    latest_hma20 = float(hma20_clean.iloc[-1])
    latest_hma55 = float(hma55_clean.iloc[-1])
    slope = hma_slope(hma20, HMA_SLOPE_LOOKBACK)

    if latest_hma20 <= latest_hma55:
        tier = "Bearish"
    elif slope > 0:
        tier = "Bullish"
    else:
        tier = "Neutral"

    return {
        "tier": tier,
        "hma20": latest_hma20,
        "hma55": latest_hma55,
        "hma20_slope": slope,
        "hma55_series": hma55,
    }


# ─── Rule 2: HMA Freshness Score ────────────────────────────────

def hma_freshness_score(daily_df: pd.DataFrame) -> dict:
    """Score based on how recently HMA20 crossed above HMA55."""
    close = daily_df["Close"]
    hma20 = hma(close, HMA_FAST_PERIOD)
    hma55 = hma(close, HMA_SLOW_PERIOD)
    age = hma_crossover_age(hma20, hma55)

    if age <= FRESHNESS_TIER1_DAYS:
        score = 2
    elif age <= FRESHNESS_TIER2_DAYS:
        score = 1
    else:
        score = 0

    return {"score": score, "crossover_age": age}


# ─── Rule 3: Distance from HMA55 ────────────────────────────────

def distance_from_hma55_score(price: float, hma55_value: float) -> dict:
    """Score based on distance of price from HMA55 (mean reversion safety)."""
    if hma55_value == 0:
        return {"score": 0, "distance_pct": 0.0}

    distance_pct = ((price - hma55_value) / hma55_value) * 100

    if distance_pct < 0:
        score = 0
    elif distance_pct <= 5:
        score = 2
    elif distance_pct <= 10:
        score = 1
    elif distance_pct <= 15:
        score = 0
    else:
        score = -1

    return {"score": score, "distance_pct": round(distance_pct, 2)}


# ─── Rule 4: Volume Quality ─────────────────────────────────────

def volume_quality_score(daily_df: pd.DataFrame, delivery_pct_avg: float = None) -> dict:
    """
    Volume quality based on accumulation/distribution days, OBV trend,
    and delivery percentage trend.
    """
    close = daily_df["Close"]
    volume = daily_df["Volume"]

    # Accumulation / Distribution day count
    ad = count_accumulation_distribution_days(daily_df, VOLUME_LOOKBACK)
    acc = ad["accumulation"]
    dist = ad["distribution"]

    # OBV trend
    obv = compute_obv(close, volume)
    obv_trend_val = obv_slope(obv, OBV_SLOPE_LOOKBACK)
    obv_rising = obv_trend_val > 0

    # Delivery % trend (if available)
    high_delivery = False
    if delivery_pct_avg is not None and delivery_pct_avg > 50:
        high_delivery = True

    # Check if daily data has Delivery_Pct column for trend analysis
    delivery_trend_rising = False
    if "Delivery_Pct" in daily_df.columns:
        recent_del = daily_df["Delivery_Pct"].dropna()
        if len(recent_del) >= 20:
            recent_5 = recent_del.iloc[-5:].mean()
            recent_20 = recent_del.iloc[-20:].mean()
            delivery_trend_rising = recent_5 > recent_20

    # Scoring logic
    strong_acc = acc >= max(dist * 1.5, dist + 3) and obv_rising
    moderate_acc = acc > dist
    heavy_dist = dist >= max(acc * 1.5, acc + 3) and not obv_rising

    # Boost with delivery data
    if high_delivery or delivery_trend_rising:
        if moderate_acc:
            strong_acc = True

    if strong_acc:
        score = 2
    elif moderate_acc:
        score = 1
    elif heavy_dist:
        score = -1
    else:
        score = 0

    return {
        "score": score,
        "acc_days": acc,
        "dist_days": dist,
        "obv_trend": "Rising" if obv_rising else "Falling",
        "delivery_pct": delivery_pct_avg,
    }


# ─── Rule 5: RSI ────────────────────────────────────────────────

def rsi_score_rule(rsi_value: float) -> int:
    """RSI must be in healthy bullish range: 40 ≤ RSI ≤ 65."""
    if RSI_MIN <= rsi_value <= RSI_MAX:
        return 1
    return 0


# ─── Rule 6: MACD Confirmation ──────────────────────────────────

def macd_score_rule(macd_val: float, signal_val: float) -> int:
    """MACD line must be above signal line."""
    return 1 if macd_val > signal_val else 0


# ─── Rule 7: Sector Bias ────────────────────────────────────────

def sector_bias_score(symbol: str) -> dict:
    """Assign sector bias based on stock's sector category."""
    sector = SYMBOL_SECTOR_MAP.get(symbol, "Unknown")
    bias = get_sector_bias(sector)
    return {"score": bias, "sector": sector}


# ─── Rule 8: Risk-Reward ────────────────────────────────────────

def risk_reward_score(price: float, hma55_value: float) -> dict:
    """Risk-reward based on HMA55 stop loss. Stop = HMA55 × 0.97."""
    stop_loss = hma55_value * STOP_LOSS_MULTIPLIER
    if price <= 0:
        return {"score": 0, "stop_loss": stop_loss, "risk_pct": 100.0}

    risk_pct = ((price - stop_loss) / price) * 100
    score = 1 if 0 < risk_pct <= MAX_RISK_PCT else 0

    return {
        "score": score,
        "stop_loss": round(stop_loss, 2),
        "risk_pct": round(risk_pct, 2),
    }


# ─── Rule 9: Deceleration Penalty ───────────────────────────────

def deceleration_penalty(weekly_df: pd.DataFrame) -> int:
    """
    Penalize if HMA55 slope is positive but momentum is weakening rapidly.
    Compares current slope vs older slope; if current < 50% of older → penalty.
    """
    close = weekly_df["Close"]
    hma55 = hma(close, HMA_SLOW_PERIOD)
    clean = hma55.dropna()

    if len(clean) < 15:
        return 0

    current_slope = hma_slope(clean, 5)
    if current_slope <= 0:
        return 0  # Already negative, not applicable

    # Compute older slope (5-10 periods back)
    older_segment = clean.iloc[:-5]
    if len(older_segment) < 5:
        return 0

    older_slope = hma_slope(older_segment, 5)
    if older_slope <= 0:
        return 0

    # Decelerating: current slope shrunk to less than half of older
    if current_slope < older_slope * 0.5:
        return -1

    return 0


# ─── Rule 10: Overextension Penalty ─────────────────────────────

def overextension_penalty(price: float, hma55_value: float) -> int:
    """Penalize stocks more than 15% above HMA55."""
    if hma55_value == 0:
        return 0
    distance_pct = ((price - hma55_value) / hma55_value) * 100
    return -1 if distance_pct > OVEREXTENSION_THRESHOLD else 0


# ─── Rule 11: Category Assignment ───────────────────────────────

def assign_category(stock_data: dict) -> str:
    """
    Assign category: Uptrend, Peak, Safer, Recovering, or Rising.
    """
    crossover_age = stock_data.get("crossover_age", 999)
    vol_score = stock_data.get("volume_score", 0)
    distance_pct = stock_data.get("distance_pct", 0)
    delivery_pct = stock_data.get("delivery_pct")
    near_52w_high = stock_data.get("near_52w_high", False)
    was_below_hma55 = stock_data.get("was_below_hma55", False)

    if crossover_age <= 10 and vol_score >= 1:
        return "Uptrend"
    if near_52w_high:
        return "Peak"
    if delivery_pct is not None and delivery_pct > 60 and distance_pct < 5:
        return "Safer"
    if was_below_hma55:
        return "Recovering"
    return "Rising"


# ─── Rule 12: Caution Flags ─────────────────────────────────────

def generate_caution_flags(stock_data: dict) -> list:
    """Generate warning labels (not score penalties)."""
    flags = []

    if stock_data.get("total_score", 0) < WATCHLIST_MIN:
        flags.append("Low Score")
    if stock_data.get("delivery_pct") is not None and stock_data["delivery_pct"] < 30:
        flags.append("Low Delivery")
    if stock_data.get("distance_pct", 0) > OVEREXTENSION_THRESHOLD:
        flags.append("Overextended")
    if stock_data.get("crossover_age", 0) > 30:
        flags.append("Mature Crossover")
    if stock_data.get("weekly_pullback", False):
        flags.append("Weekly Pullback")

    return flags


# ─── Master Scoring Function ────────────────────────────────────

def score_stock(
    daily_df: pd.DataFrame,
    weekly_df: pd.DataFrame,
    symbol: str,
    delivery_pct_avg: float = None,
) -> dict:
    """
    Apply ALL 12 rules to a stock and return comprehensive result dict.
    """
    result = {"ticker": symbol}
    price = float(daily_df["Close"].iloc[-1])
    result["price"] = round(price, 2)

    # ── Rule 1: Weekly Trend Filter (Gate) ──
    trend = weekly_trend_filter(weekly_df)
    result["tier"] = trend["tier"]
    result["hma20"] = round(trend["hma20"], 2)
    result["hma55"] = round(trend["hma55"], 2)
    result["hma20_slope"] = round(trend["hma20_slope"], 4)

    if trend["tier"] == "Bearish":
        result["score"] = 0
        result["conviction"] = "REJECTED"
        result["category"] = "N/A"
        result["caution_flags"] = ["Bearish Trend"]
        result["breakdown"] = {}
        return result

    # If weekly history is insufficient to compute HMAs, continue scoring but mark caution
    insufficient_history = False
    if trend["tier"] == "Insufficient":
        insufficient_history = True

    # ── Rule 2: HMA Freshness ──
    freshness = hma_freshness_score(daily_df)
    result["crossover_age"] = freshness["crossover_age"]

    # ── Rule 3: Distance from HMA55 ──
    dist = distance_from_hma55_score(price, trend["hma55"])
    result["distance_pct"] = dist["distance_pct"]

    # ── Rule 4: Volume Quality (includes delivery %) ──
    vol = volume_quality_score(daily_df, delivery_pct_avg)
    result["acc_days"] = vol["acc_days"]
    result["dist_days"] = vol["dist_days"]
    result["obv_trend"] = vol["obv_trend"]
    result["delivery_pct"] = delivery_pct_avg

    # ── Rule 5: RSI ──
    rsi_series = compute_rsi(daily_df["Close"], RSI_PERIOD)
    rsi_clean = rsi_series.dropna()
    current_rsi = float(rsi_clean.iloc[-1]) if not rsi_clean.empty else 50.0
    result["rsi"] = round(current_rsi, 2)

    # ── Rule 6: MACD ──
    macd_line, signal_line, _ = compute_macd(
        daily_df["Close"], MACD_FAST, MACD_SLOW, MACD_SIGNAL
    )
    cur_macd = float(macd_line.iloc[-1]) if not macd_line.empty else 0
    cur_signal = float(signal_line.iloc[-1]) if not signal_line.empty else 0
    result["macd_bullish"] = cur_macd > cur_signal

    # ── Rule 7: Sector Bias ──
    sector = sector_bias_score(symbol)
    result["sector"] = sector["sector"]

    # ── Rule 8: Risk-Reward ──
    # Compute ATR (daily) and derive ATR-based SL/T1/T2 per requirements
    atr_series = compute_atr(daily_df["High"], daily_df["Low"], daily_df["Close"], period=14)
    atr_val = float(atr_series.dropna().iloc[-1]) if not atr_series.dropna().empty else None
    result["atr"] = round(atr_val, 4) if atr_val is not None else None

    entry_point = price
    result["entry"] = round(entry_point, 2)

    if atr_val is not None:
        sl = entry_point - (atr_val * 3)
        t1 = entry_point + (atr_val * 3.0)
        t2 = entry_point + (atr_val * 6.0)
        result["stop_loss"] = round(sl, 2)
        result["target1"] = round(t1, 2)
        result["target2"] = round(t2, 2)

        # Percentages relative to entry
        result["sl_pct"] = round(((entry_point - sl) / entry_point) * 100, 2)
        result["t1_pct"] = round(((t1 - entry_point) / entry_point) * 100, 2)
        result["t2_pct"] = round(((t2 - entry_point) / entry_point) * 100, 2)

        # Risk % used for scoring (long only)
        risk_pct = result["sl_pct"]
    else:
        result["stop_loss"] = None
        result["target1"] = None
        result["target2"] = None
        result["sl_pct"] = None
        result["t1_pct"] = None
        result["t2_pct"] = None
        risk_pct = 100.0

    # Use risk_pct to determine RR score
    rr_score = 1 if 0 < risk_pct <= MAX_RISK_PCT else 0

    # ── Rule 9: Deceleration Penalty ──
    decel = deceleration_penalty(weekly_df)

    # ── Rule 10: Overextension Penalty ──
    overext = overextension_penalty(price, trend["hma55"])

    # ── Build Score Breakdown ──
    breakdown = {
        "hma_freshness": freshness["score"],
        "distance": dist["score"],
        "volume": vol["score"],
        "rsi": rsi_score_rule(current_rsi),
        "macd": macd_score_rule(cur_macd, cur_signal),
        "sector_bias": sector["score"],
        "risk_reward": rr_score,
        "deceleration": decel,
        "overextension": overext,
    }
    result["breakdown"] = breakdown

    total = sum(breakdown.values())
    total = max(total, 0)  # Floor at 0
    result["score"] = total

    # ── Conviction Level ──
    if trend["tier"] == "Neutral":
        result["conviction"] = "WATCHLIST"
    elif total >= HIGH_CONVICTION_MIN:
        result["conviction"] = "HIGH"
    elif total >= WATCHLIST_MIN:
        result["conviction"] = "WATCHLIST"
    else:
        result["conviction"] = "REJECTED"

    # ── Rule 11: Category ──
    # Check if near 52-week high
    high_52w = float(daily_df["High"].rolling(252, min_periods=50).max().iloc[-1])
    near_52w_high = price >= high_52w * 0.95

    # Check if recently recovered from below HMA55
    daily_hma55 = hma(daily_df["Close"], HMA_SLOW_PERIOD).dropna()
    was_below = False
    if len(daily_hma55) >= 20:
        recent_20 = daily_hma55.iloc[-20:-5]
        close_20 = daily_df["Close"].loc[recent_20.index] if not recent_20.empty else pd.Series()
        if not close_20.empty:
            was_below = (close_20 < recent_20).any()

    # Weekly pullback detection
    weekly_pullback = False
    if len(weekly_df) >= 2:
        last_2 = weekly_df.iloc[-2:]
        weekly_pullback = all(
            last_2["Close"].values[i] < last_2["Open"].values[i]
            for i in range(len(last_2))
        )

    cat_data = {
        "crossover_age": freshness["crossover_age"],
        "volume_score": vol["score"],
        "distance_pct": dist["distance_pct"],
        "delivery_pct": delivery_pct_avg,
        "near_52w_high": near_52w_high,
        "was_below_hma55": was_below,
    }
    result["category"] = assign_category(cat_data)

    # ── Rule 12: Caution Flags ──
    flag_data = {
        "total_score": total,
        "delivery_pct": delivery_pct_avg,
        "distance_pct": dist["distance_pct"],
        "crossover_age": freshness["crossover_age"],
        "weekly_pullback": weekly_pullback,
    }
    result["caution_flags"] = generate_caution_flags(flag_data)
    if insufficient_history:
        result["caution_flags"].append("Insufficient Weekly History")

    return result
