# ==============================================================================
# quantclaw/utils/indicators.py — Technical Indicators Engine
# ==============================================================================
"""
Technical Indicators Engine for QuantClaw MT5.
Calculates technical indicators (ATR, RSI, EMAs, SMMA, Supertrend, ADX,
Bollinger Bands, MACD, Stochastic, Volume Profile) in pure Python.
Keeps the system ultra-fast and lightweight without requiring pandas/ta-lib.
"""

from typing import List, Dict, Any
import math


def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """Calculate RSI using Wilder's smoothing."""
    if len(prices) < period + 1:
        return 50.0

    changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [c if c > 0.0 else 0.0 for c in changes]
    losses = [-c if c < 0.0 else 0.0 for c in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calculate_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    """Calculate Average True Range (ATR) using Wilder's smoothing."""
    if len(candles) < 2:
        return 0.0

    tr_values = []
    try:
        first_high = float(candles[0].get("high", 0.0))
        first_low = float(candles[0].get("low", 0.0))
        tr_values.append(max(0.0, first_high - first_low))
    except (ValueError, TypeError):
        tr_values.append(0.0)

    for i in range(1, len(candles)):
        try:
            high = float(candles[i].get("high", 0.0))
            low = float(candles[i].get("low", 0.0))
            prev_close = float(candles[i - 1].get("close", 0.0))
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(max(0.0, tr))
        except (ValueError, TypeError):
            tr_values.append(0.0)

    if len(candles) < period + 1:
        # Return simple average of available TRs, or 0.0 (never 1.0 — a 1.0 ATR is
        # 100,000 pts on EURUSD and would cause catastrophic SL/TP sizing).
        avg_tr = sum(tr_values) / float(len(tr_values)) if tr_values else 0.0
        return round(avg_tr, 5) if avg_tr > 0 else 0.0

    atr = sum(tr_values[:period]) / period
    for i in range(period, len(tr_values)):
        atr = (atr * (period - 1) + tr_values[i]) / period

    return round(atr, 5)


def calculate_ema_latest(prices: List[float], period: int) -> float:
    """Calculate latest Exponential Moving Average (EMA)."""
    if len(prices) < period:
        return prices[-1] if prices else 0.0

    ema = sum(prices[:period]) / period
    multiplier = 2.0 / (period + 1.0)
    for i in range(period, len(prices)):
        ema = (prices[i] - ema) * multiplier + ema
    return ema


def calculate_smma_series(prices: List[float], period: int) -> List[float]:
    """Calculate Smoothed Moving Average (SMMA / RMA) series.

    Note: indices 0..period-2 are set to 0.0 (warmup / no-data sentinel).
    Valid values start at index period-1. Consumers should check for 0.0 before use.
    """
    if len(prices) < period:
        return [0.0] * len(prices)

    smma = [0.0] * len(prices)
    # Seed: first valid SMMA = SMA of first 'period' bars (index period-1)
    smma[period - 1] = sum(prices[:period]) / period
    for i in range(period, len(prices)):
        smma[i] = (smma[i - 1] * (period - 1) + prices[i]) / period
    # Early bars (0..period-2) remain 0.0 — callers must guard against these
    return smma



def calculate_ema_series(prices: List[float], period: int) -> List[float]:
    """
    Calculate the full EMA series for all bars.
    Returns list of same length as prices, with 0.0 before the first valid EMA.
    """
    if len(prices) < period:
        return [0.0] * len(prices)

    result = [0.0] * len(prices)
    multiplier = 2.0 / (period + 1.0)
    result[period - 1] = sum(prices[:period]) / period
    for i in range(period, len(prices)):
        result[i] = (prices[i] - result[i - 1]) * multiplier + result[i - 1]
    return result


def calculate_bollinger_bands(prices: List[float], period: int = 20, num_std: float = 2.0) -> Dict[str, float]:
    """Calculate Bollinger Bands (Upper, Middle, Lower, Bandwidth, %B)."""
    if len(prices) < period:
        p = prices[-1] if prices else 0.0
        return {"upper": p, "middle": p, "lower": p, "bandwidth": 0.0, "pct_b": 0.5}

    subset = prices[-period:]
    middle = sum(subset) / period
    variance = sum((x - middle) ** 2 for x in subset) / (period - 1)
    std_dev = math.sqrt(variance)

    upper = middle + (num_std * std_dev)
    lower = middle - (num_std * std_dev)
    bandwidth = (upper - lower) / middle if middle > 0 else 0.0

    latest = prices[-1]
    pct_b = (latest - lower) / (upper - lower) if (upper - lower) > 0 else 0.5

    return {
        "upper": round(upper, 5),
        "middle": round(middle, 5),
        "lower": round(lower, 5),
        "bandwidth": round(bandwidth, 5),
        "pct_b": round(pct_b, 4),
    }


def calculate_stochastic(candles: List[Dict[str, Any]], k_period: int = 14, d_period: int = 3) -> Dict[str, float]:
    """Calculate Stochastic Oscillator (%K and %D)."""
    if len(candles) < k_period:
        return {"k": 50.0, "d": 50.0}

    k_values = []
    for i in range(k_period - 1, len(candles)):
        window = candles[i - k_period + 1 : i + 1]
        highs = [float(c.get("high", 0.0)) for c in window]
        lows = [float(c.get("low", 0.0)) for c in window]
        close = float(window[-1].get("close", 0.0))

        highest = max(highs)
        lowest = min(lows)
        k = ((close - lowest) / (highest - lowest) * 100.0) if (highest - lowest) > 0 else 50.0
        k_values.append(k)

    latest_k = k_values[-1] if k_values else 50.0
    latest_d = sum(k_values[-d_period:]) / len(k_values[-d_period:]) if k_values else 50.0

    return {"k": round(latest_k, 2), "d": round(latest_d, 2)}


def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, float]:
    """Calculate MACD line, Signal line, and Histogram."""
    if len(prices) < slow + signal:
        return {"macd": 0.0, "signal": 0.0, "hist": 0.0}

    # Fast EMA series
    fast_mult = 2.0 / (fast + 1.0)
    slow_mult = 2.0 / (slow + 1.0)

    fast_ema = [0.0] * len(prices)
    slow_ema = [0.0] * len(prices)

    fast_ema[fast - 1] = sum(prices[:fast]) / fast
    for i in range(fast, len(prices)):
        fast_ema[i] = (prices[i] - fast_ema[i - 1]) * fast_mult + fast_ema[i - 1]

    slow_ema[slow - 1] = sum(prices[:slow]) / slow
    for i in range(slow, len(prices)):
        slow_ema[i] = (prices[i] - slow_ema[i - 1]) * slow_mult + slow_ema[i - 1]

    macd_line = [fast_ema[i] - slow_ema[i] for i in range(slow - 1, len(prices))]

    sig_mult = 2.0 / (signal + 1.0)
    sig_ema = [0.0] * len(macd_line)
    sig_ema[signal - 1] = sum(macd_line[:signal]) / signal
    for i in range(signal, len(macd_line)):
        sig_ema[i] = (macd_line[i] - sig_ema[i - 1]) * sig_mult + sig_ema[i - 1]

    latest_macd = macd_line[-1]
    latest_sig = sig_ema[-1]
    hist = latest_macd - latest_sig

    return {"macd": round(latest_macd, 5), "signal": round(latest_sig, 5), "hist": round(hist, 5)}


def calculate_supertrend_latest(
    candles: List[Dict[str, Any]], period: int = 10, multiplier: float = 3.0
) -> Dict[str, Any]:
    """Calculate latest Supertrend value and direction."""
    if len(candles) < period + 1:
        return {"value": 0.0, "direction": 1, "trend": "BULLISH"}

    tr_values = []
    try:
        first_high = float(candles[0].get("high", 0.0))
        first_low = float(candles[0].get("low", 0.0))
        tr_values.append(first_high - first_low)
    except (ValueError, TypeError):
        tr_values.append(0.0)

    for i in range(1, len(candles)):
        try:
            high = float(candles[i].get("high", 0.0))
            low = float(candles[i].get("low", 0.0))
            prev_close = float(candles[i - 1].get("close", 0.0))
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)
        except (ValueError, TypeError):
            tr_values.append(0.0)

    atr = [0.0] * len(candles)
    atr[period - 1] = sum(tr_values[:period]) / period
    for i in range(period, len(candles)):
        atr[i] = (atr[i - 1] * (period - 1) + tr_values[i]) / period

    final_upper = [0.0] * len(candles)
    final_lower = [0.0] * len(candles)
    trend = [1] * len(candles)

    # Seed initial values for bars before valid ATR (period-1 bar)
    for i in range(period - 1):
        try:
            high = float(candles[i].get("high", 0.0))
            low = float(candles[i].get("low", 0.0))
        except (ValueError, TypeError):
            high, low = 0.0, 0.0
        hl2 = (high + low) / 2.0
        final_upper[i] = hl2 + multiplier * (atr[period - 1] if atr[period - 1] > 0 else 0.001)
        final_lower[i] = hl2 - multiplier * (atr[period - 1] if atr[period - 1] > 0 else 0.001)

    # Start Supertrend calculation from the first bar with valid ATR
    for i in range(period - 1, len(candles)):
        try:
            high = float(candles[i].get("high", 0.0))
            low = float(candles[i].get("low", 0.0))
            close = float(candles[i].get("close", 0.0))
        except (ValueError, TypeError):
            high, low, close = 0.0, 0.0, 0.0

        hl2 = (high + low) / 2.0
        basic_upper = hl2 + (multiplier * atr[i])
        basic_lower = hl2 - (multiplier * atr[i])

        if i == 0:
            final_upper[i] = basic_upper
            final_lower[i] = basic_lower
            continue

        try:
            prev_close = float(candles[i - 1].get("close", 0.0))
        except (ValueError, TypeError):
            prev_close = 0.0

        if basic_upper < final_upper[i - 1] or prev_close > final_upper[i - 1]:
            final_upper[i] = basic_upper
        else:
            final_upper[i] = final_upper[i - 1]

        if basic_lower > final_lower[i - 1] or prev_close < final_lower[i - 1]:
            final_lower[i] = basic_lower
        else:
            final_lower[i] = final_lower[i - 1]

        if trend[i - 1] == 1:
            if close < final_lower[i]:
                trend[i] = -1
                final_upper[i] = basic_upper
            else:
                trend[i] = 1
        else:
            if close > final_upper[i]:
                trend[i] = 1
                final_lower[i] = basic_lower
            else:
                trend[i] = -1

    latest_val = final_lower[-1] if trend[-1] == 1 else final_upper[-1]
    latest_trend = "BULLISH" if trend[-1] == 1 else "BEARISH"
    return {"value": latest_val, "direction": trend[-1], "trend": latest_trend}


def calculate_volume_metrics(candles: List[Dict[str, Any]], period: int = 20) -> Dict[str, Any]:
    """Calculate volume metrics (latest, average, and ratio)."""
    if len(candles) < 2:
        return {"latest_volume": 0.0, "avg_volume": 1.0, "volume_ratio": 0.0}

    volumes = []
    for c in candles:
        try:
            # MT5 returns 'tick_volume' and 'real_volume', not 'volume'
            vol = float(c.get("tick_volume", c.get("real_volume", c.get("volume", 0.0))))
            volumes.append(vol)
        except (ValueError, TypeError):
            volumes.append(0.0)

    latest = volumes[-1]
    slice_len = min(len(volumes) - 1, period)
    if slice_len <= 0:
        return {"latest_volume": latest, "avg_volume": 1.0, "volume_ratio": 0.0}

    avg = sum(volumes[-(slice_len + 1) : -1]) / slice_len
    ratio = latest / avg if avg > 0.0 else 0.0
    return {"latest_volume": latest, "avg_volume": avg, "volume_ratio": ratio}


def calculate_adx(candles: List[Dict[str, Any]], period: int = 14) -> Dict[str, float]:
    """Calculate ADX (Average Directional Index) and Directional Movement."""
    if len(candles) < period + 1:
        return {"adx": 20.0, "plus_di": 0.0, "minus_di": 0.0}

    tr_list: List[float] = []
    plus_dm_list: List[float] = []
    minus_dm_list: List[float] = []

    for i in range(1, len(candles)):
        try:
            high = float(candles[i].get("high", 0.0))
            low = float(candles[i].get("low", 0.0))
            prev_close = float(candles[i - 1].get("close", 0.0))
            prev_high = float(candles[i - 1].get("high", 0.0))
            prev_low = float(candles[i - 1].get("low", 0.0))
        except (ValueError, TypeError):
            tr_list.append(0.0)
            plus_dm_list.append(0.0)
            minus_dm_list.append(0.0)
            continue

        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)

        up_move = high - prev_high
        down_move = prev_low - low
        plus_dm = up_move if (up_move > down_move and up_move > 0.0) else 0.0
        minus_dm = down_move if (down_move > up_move and down_move > 0.0) else 0.0
        plus_dm_list.append(plus_dm)
        minus_dm_list.append(minus_dm)

    if len(tr_list) < period:
        return {"adx": 20.0, "plus_di": 0.0, "minus_di": 0.0}

    atr_w = sum(tr_list[:period])
    pdi_w = sum(plus_dm_list[:period])
    mdi_w = sum(minus_dm_list[:period])

    dx_values: List[float] = []
    for i in range(period, len(tr_list)):
        atr_w = atr_w - atr_w / period + tr_list[i]
        pdi_w = pdi_w - pdi_w / period + plus_dm_list[i]
        mdi_w = mdi_w - mdi_w / period + minus_dm_list[i]

        plus_di = (100.0 * pdi_w / atr_w) if atr_w > 0.0 else 0.0
        minus_di = (100.0 * mdi_w / atr_w) if atr_w > 0.0 else 0.0
        di_sum = plus_di + minus_di
        dx = (100.0 * abs(plus_di - minus_di) / di_sum) if di_sum > 0.0 else 0.0
        dx_values.append(dx)

    if not dx_values:
        return {"adx": 20.0, "plus_di": 0.0, "minus_di": 0.0}

    adx = sum(dx_values[:period]) / period if len(dx_values) >= period else sum(dx_values) / len(dx_values)
    for dx in dx_values[period:]:
        adx = (adx * (period - 1) + dx) / period

    final_plus_di = (100.0 * pdi_w / atr_w) if atr_w > 0.0 else 0.0
    final_minus_di = (100.0 * mdi_w / atr_w) if atr_w > 0.0 else 0.0

    return {
        "adx": round(max(0.0, min(100.0, adx)), 2),
        "plus_di": round(final_plus_di, 2),
        "minus_di": round(final_minus_di, 2),
    }


def classify_volume_regime(
    volume_ratio: float,
    adx_val: float = 20.0,
    atr_ratio: float = 1.0,
) -> Dict[str, Any]:
    """
    Classify the market into 4 volume & liquidity regimes:
    1. LOW_VOLUME: Slow, drifting market. False breakouts are common.
       Action: Compress TP target (1.5R - 1.8R), prioritize SMC liquidity sweeps,
       tighten soft SL earlier to secure small gains before range reverses.
    2. NORMAL_VOLUME: Healthy institutional liquidity and balanced momentum.
       Action: Standard 5-Zone stepped trailing, standard 2.0R - 2.8R targets.
    3. HIGH_VOLUME: Strong institutional expansion / session open / trend surge.
       Action: Expand target RR to 3.2R - 3.8R, provide 1.25x ATR trail buffer so wicks don't knock runners out.
    4. CLIMAX_VOLUME: Exhaustion spike / blow-off volume.
       Action: Block late breakout entries; if open trade is in profit (>1.5R), immediately lock trailing SL.
    """
    vr = float(volume_ratio) if volume_ratio is not None else 1.0
    adx = float(adx_val) if adx_val is not None else 20.0

    if vr > 3.0:
        regime = "CLIMAX_VOLUME"
        target_rr_mult = 1.0
        trail_atr_mult = 0.75
        allow_breakout = False
        description = "Exhaustion Volume Spike: High reversal risk. Late breakouts blocked, profits tightened."
    elif vr >= 1.8 or (vr >= 1.4 and adx >= 28.0):
        regime = "HIGH_VOLUME"
        target_rr_mult = 1.25
        trail_atr_mult = 1.25
        allow_breakout = True
        description = "Institutional Volume Expansion: Strong directional momentum. Expanding targets for maximum profit."
    elif vr < 0.70 or (vr < 0.85 and adx < 14.0):
        regime = "LOW_VOLUME"
        target_rr_mult = 0.70
        trail_atr_mult = 0.80
        allow_breakout = False
        description = "Low Volume Consolidation: Prone to fakeouts. Targeting range sweeps and securing quick profits."
    else:
        regime = "NORMAL_VOLUME"
        target_rr_mult = 1.0
        trail_atr_mult = 1.0
        allow_breakout = True
        description = "Healthy Volume Flow: Standard balanced market conditions. Operating standard 5-zone stepped trailing."

    return {
        "regime": regime,
        "volume_ratio": round(vr, 2),
        "target_rr_mult": target_rr_mult,
        "trail_atr_mult": trail_atr_mult,
        "allow_breakout": allow_breakout,
        "description": description,
    }
