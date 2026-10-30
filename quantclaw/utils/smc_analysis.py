# ==============================================================================
# quantclaw/utils/smc_analysis.py — Smart Money Concepts & Liquidity Engine
# ==============================================================================
"""
SMC, ICT, and Liquidity Heatmap Analysis Engine.
Implements programmatic detection of Fair Value Gaps (FVG), Order Blocks (OB),
Liquidity Sweeps, Market Structure Shifts (MSS), and resting order book liquidity pools.
"""

import logging
import json
import time
import re
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger("quantclaw.smc_analysis")


def _c_val(c: Any, key: str, default: Any = None) -> Any:
    """Helper to extract attribute/key value safely from dict or object."""
    if isinstance(c, dict):
        return c.get(key, default)
    return getattr(c, key, default)


def detect_fvgs(candles: List[Any], atr: float = 0.0) -> List[Dict[str, Any]]:
    """
    Detect Fair Value Gaps (FVG) / Imbalances in a 3-candle sequence.

    Mitigation definition (institutional ICT standard):
    - A Bullish FVG is MITIGATED when price retests INTO the gap from below
      (i.e. low of any subsequent candle enters the gap: low <= fvg["top"]).
    - A Bearish FVG is MITIGATED when price retests INTO the gap from above
      (i.e. high of any subsequent candle enters the gap: high >= fvg["bottom"]).
    Full penetration through the far extreme is INVALIDATION (gap already absorbed).

    Gap size filter: requires gap >= 15% of ATR (adapts across all assets).
    Falls back to 0.01% minimum if ATR is not available.
    """
    fvgs = []
    if not candles or len(candles) < 3:
        return fvgs

    # Dynamic minimum gap size: 15% of ATR, fallback 0.01% of price
    min_gap_atr = atr * 0.15 if atr > 0 else 0.0

    # 1. Identify all historical FVGs
    for i in range(2, len(candles)):
        try:
            h0 = float(_c_val(candles[i-2], "high"))
            l0 = float(_c_val(candles[i-2], "low"))
            h2 = float(_c_val(candles[i], "high"))
            l2 = float(_c_val(candles[i], "low"))
        except (TypeError, ValueError):
            continue

        # Bullish FVG: Low of candle 3 is greater than high of candle 1
        if l2 > h0 and h0 > 0:
            gap_size = l2 - h0
            # Use ATR-relative filter if available, else fallback to 0.01% of price
            min_gap = min_gap_atr if min_gap_atr > 0 else (h0 * 0.0001)
            if gap_size >= min_gap:
                fvgs.append({
                    "type": "BULLISH",
                    "top": l2,
                    "bottom": h0,
                    "midpoint": (l2 + h0) / 2.0,
                    "index": i - 1,
                    "time": _c_val(candles[i-1], "time"),
                    "mitigated": False,
                    "gap_size": gap_size,
                })
        # Bearish FVG: High of candle 3 is less than low of candle 1
        elif h2 < l0 and h2 > 0:
            gap_size = l0 - h2
            min_gap = min_gap_atr if min_gap_atr > 0 else (h2 * 0.0001)
            if gap_size >= min_gap:
                fvgs.append({
                    "type": "BEARISH",
                    "top": l0,
                    "bottom": h2,
                    "midpoint": (l0 + h2) / 2.0,
                    "index": i - 1,
                    "time": _c_val(candles[i-1], "time"),
                    "mitigated": False,
                    "gap_size": gap_size,
                })

    # 2. Check mitigation: price ENTERS the gap zone (institutional ICT definition)
    for fvg in fvgs:
        fvg_start_idx = fvg["index"] + 1
        for j in range(fvg_start_idx + 1, len(candles)):
            try:
                high = float(_c_val(candles[j], "high"))
                low = float(_c_val(candles[j], "low"))
            except (TypeError, ValueError):
                continue

            if fvg["type"] == "BULLISH":
                # Bullish FVG: top=candle2.low, bottom=candle0.high
                # Mitigated when price ENTERS the gap from below (touches near edge = top)
                if low <= fvg["top"]:
                    fvg["mitigated"] = True
                    break
            else:
                # Bearish FVG: top=candle0.low, bottom=candle2.high
                # Mitigated when price ENTERS the gap from above (touches near edge = bottom)
                if high >= fvg["bottom"]:
                    fvg["mitigated"] = True
                    break

    return fvgs



def detect_order_blocks(candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Detect Order Blocks (OB) - the last opposite candle before a strong directional expansion.
    """
    obs = []
    if len(candles) < 5:
        return obs

    for i in range(1, len(candles) - 3):
        try:
            o0 = float(_c_val(candles[i], "open") or 0.0)
            h0 = float(_c_val(candles[i], "high") or 0.0)
            l0 = float(_c_val(candles[i], "low") or 0.0)
            c0 = float(_c_val(candles[i], "close") or 0.0)
            # Check for strong expansion in the next 3 candles
            moves = []
            for j in range(1, 4):
                c_next = float(_c_val(candles[i+j], "close") or 0.0)
                o_next = float(_c_val(candles[i+j], "open") or 0.0)
                moves.append(c_next - o_next)
        except (TypeError, ValueError):
            continue

        body_size = abs(c0 - o0)
        avg_body_vals = []
        for c in candles[max(0, i-10):i]:
            try:
                avg_body_vals.append(abs(float(_c_val(c, "close") or 0.0) - float(_c_val(c, "open") or 0.0)))
            except (TypeError, ValueError):
                avg_body_vals.append(0.0)
        avg_body = sum(avg_body_vals) / max(1, len(avg_body_vals))

        # Bullish OB: Bearish candle (c0 < o0) followed by strong upward expansion
        if c0 < o0 and sum(moves) > 2.0 * avg_body and all(m > 0 for m in moves[:2]):
            obs.append({
                "type": "BULLISH",
                "top": max(o0, c0),
                "bottom": l0,
                "time": _c_val(candles[i], "time"),
                "mitigated": False,
                "index": i
            })
        # Bearish OB: Bullish candle (c0 > o0) followed by strong downward expansion
        elif c0 > o0 and sum(moves) < -2.0 * avg_body and all(m < 0 for m in moves[:2]):
            obs.append({
                "type": "BEARISH",
                "top": h0,
                "bottom": min(o0, c0),
                "time": _c_val(candles[i], "time"),
                "mitigated": False,
                "index": i
            })

    # Check mitigation using _c_val for consistent access
    for ob in obs:
        ob_start_idx = ob["index"] + 1
        for j in range(ob_start_idx, len(candles)):
            try:
                high = float(_c_val(candles[j], "high") or 0.0)
                low = float(_c_val(candles[j], "low") or 0.0)
                close = float(_c_val(candles[j], "close") or 0.0)
            except (TypeError, ValueError):
                continue

            if ob["type"] == "BULLISH":
                # OB invalidated when price closes below the OB bottom
                if close < ob["bottom"]:
                    ob["mitigated"] = True
                    break
            else:
                # OB invalidated when price closes above the OB top
                if close > ob["top"]:
                    ob["mitigated"] = True
                    break

    return obs


def detect_swing_points(candles: List[Dict[str, Any]], left: int = 3, right: int = 3) -> Dict[str, List[Dict[str, Any]]]:
    """Identify swing highs and swing lows using fractal/pivot confirmation."""
    swing_highs = []
    swing_lows = []
    n = len(candles)
    if n < left + right + 1:
        return {"highs": [], "lows": []}

    for i in range(left, n - right):
        h = float(_c_val(candles[i], "high", 0.0))
        l = float(_c_val(candles[i], "low", 0.0))
        t = _c_val(candles[i], "time", 0)

        # Swing High: higher than left neighbors and right neighbors
        is_high = True
        for j in range(1, left + 1):
            if float(_c_val(candles[i - j], "high", 0.0)) >= h:
                is_high = False
                break
        if is_high:
            for j in range(1, right + 1):
                if float(_c_val(candles[i + j], "high", 0.0)) > h:
                    is_high = False
                    break
        if is_high:
            swing_highs.append({"index": i, "price": h, "time": t})

        # Swing Low: lower than left neighbors and right neighbors
        is_low = True
        for j in range(1, left + 1):
            if float(_c_val(candles[i - j], "low", 0.0)) <= l:
                is_low = False
                break
        if is_low:
            for j in range(1, right + 1):
                if float(_c_val(candles[i + j], "low", 0.0)) < l:
                    is_low = False
                    break
        if is_low:
            swing_lows.append({"index": i, "price": l, "time": t})

    return {"highs": swing_highs, "lows": swing_lows}


def detect_sweeps(candles: List[Dict[str, Any]], period: int = 20) -> Dict[str, Any]:
    """
    Detect if any recent candle swept Liquidity (recent swing Highs/Lows or range extremes) and reversed.
    """
    result = {"swept_bsl": False, "swept_ssl": False, "bsl_price": 0.0, "ssl_price": 0.0, "sweep_index": -1}
    if len(candles) < 4:
        return result

    effective_period = min(period, max(3, len(candles) - 2))
    # 1. Classical Range Extreme Sweep check (checks latest candle against prior range)
    prior_candles = candles[-(effective_period + 1):-1]
    try:
        highs = [float(_c_val(c, "high", 0.0)) for c in prior_candles]
        lows  = [float(_c_val(c, "low", 0.0))  for c in prior_candles]
        latest_high = float(_c_val(candles[-1], "high", 0.0))
        latest_low = float(_c_val(candles[-1], "low", 0.0))
        latest_close = float(_c_val(candles[-1], "close", 0.0))

        highest_high = max(highs) if highs else 0.0
        lowest_low = min(lows) if lows else 0.0

        result["bsl_price"] = highest_high
        result["ssl_price"] = lowest_low

        if latest_high > highest_high and latest_close < highest_high:
            result["swept_bsl"] = True
            result["bsl_price"] = latest_high
            result["sweep_index"] = len(candles) - 1

        if latest_low < lowest_low and latest_close > lowest_low:
            result["swept_ssl"] = True
            result["ssl_price"] = latest_low
            result["sweep_index"] = len(candles) - 1
    except (KeyError, TypeError, ValueError):
        pass

    # 2. Multi-bar Swing Sweep check (if sufficient candles are provided)
    if len(candles) >= 15:
        swings = detect_swing_points(candles[:-2], left=2, right=2)
        recent_window = candles[-10:]
        for idx_offset, c in enumerate(recent_window):
            c_high = float(_c_val(c, "high", 0.0))
            c_low = float(_c_val(c, "low", 0.0))
            c_close = float(_c_val(c, "close", 0.0))

            for sh in swings["highs"]:
                if c_high > sh["price"] and c_close < sh["price"]:
                    result["swept_bsl"] = True
                    result["bsl_price"] = max(result["bsl_price"], c_high)
                    result["sweep_index"] = len(candles) - 10 + idx_offset

            for sl in swings["lows"]:
                if c_low < sl["price"] and c_close > sl["price"]:
                    result["swept_ssl"] = True
                    result["ssl_price"] = min(result["ssl_price"] if result["ssl_price"] > 0 else sl["price"], c_low)
                    result["sweep_index"] = len(candles) - 10 + idx_offset

    return result




def detect_bos_choch(candles: list, lookback: int = 20) -> dict:
    """Detect Break of Structure (BOS) and Change of Character (ChoCH).
    BOS: Market continues the trend by breaking a previous swing high/low.
    ChoCH: Market reverses by breaking against the established trend.
    Returns dict with 'type' ('BOS_BULL', 'BOS_BEAR', 'CHOCH_BULL', 'CHOCH_BEAR', 'NONE'),
    'price' (the broken level), and 'strength'.
    """
    if len(candles) < lookback + 2:
        return {"type": "NONE", "price": 0.0, "strength": 0.0}
    try:
        window = candles[-(lookback + 2):]
        recent = candles[-1]
        current_close = float(_c_val(recent, "close", 0.0))
        
        highs = [float(_c_val(c, "high", 0.0)) for c in window[:-1]]
        lows  = [float(_c_val(c, "low", 0.0)) for c in window[:-1]]
        
        prev_swing_high = max(highs[:-3]) if len(highs) > 3 else max(highs)
        prev_swing_low  = min(lows[:-3])  if len(lows) > 3  else min(lows)
        
        # Detect prior trend: last N closes going up or down
        mid = len(window) // 2
        early_close = float(_c_val(window[0], "close", 0.0))
        mid_close   = float(_c_val(window[mid], "close", 0.0))
        last_close  = current_close
        
        uptrend = early_close < mid_close < last_close
        downtrend = early_close > mid_close > last_close
        
        if current_close > prev_swing_high:
            # Breaking above previous high
            t = "BOS_BULL" if uptrend else "CHOCH_BULL"
            strength = min(1.0, (current_close - prev_swing_high) / max(0.0001, prev_swing_high) * 100)
            return {"type": t, "price": prev_swing_high, "strength": strength}
        elif current_close < prev_swing_low:
            # Breaking below previous low
            t = "BOS_BEAR" if downtrend else "CHOCH_BEAR"
            strength = min(1.0, (prev_swing_low - current_close) / max(0.0001, prev_swing_low) * 100)
            return {"type": t, "price": prev_swing_low, "strength": strength}
        
        return {"type": "NONE", "price": 0.0, "strength": 0.0}
    except Exception as e:
        return {"type": "NONE", "price": 0.0, "strength": 0.0}

def detect_liquidity_sweeps(candles: List[Dict[str, Any]], period: int = 20) -> List[Dict[str, Any]]:
    """Detect liquidity sweeps and return a list of sweep event dictionaries."""
    sweeps = []
    res = detect_sweeps(candles, period)
    if res.get("swept_bsl"):
        sweeps.append({"direction": "BEARISH_SWEEP", "price": res.get("bsl_price", 0.0), "time": time.time(), "index": res.get("sweep_index", -1)})
    if res.get("swept_ssl"):
        sweeps.append({"direction": "BULLISH_SWEEP", "price": res.get("ssl_price", 0.0), "time": time.time(), "index": res.get("sweep_index", -1)})
    return sweeps


def evaluate_institutional_ict_setup(
    candles: List[Dict[str, Any]],
    atr: float,
    min_rr: float = 2.0
) -> Optional[Dict[str, Any]]:
    """
    Complete Institutional ICT/SMC Model:
    1. Liquidity Sweep: BSL (for Short) or SSL (for Long) swept in last 15 bars.
    2. Market Structure Shift (MSS/ChoCH): Impulsive displacement candle in reversal direction.
    3. Retest into Unmitigated Fair Value Gap (FVG) or Order Block (OB).
    4. Premium/Discount Matrix: Longs in Discount (<50%), Shorts in Premium (>50%).
    5. Invalidation Stop Loss beyond sweep extreme; Target opposite liquidity pool (>= min_rr).
    """
    if len(candles) < 15 or atr <= 0:
        return None

    current_price = float(_c_val(candles[-1], "close", 0.0))
    # Extend lookback from 20 to 150 candles to capture daily structure, Asian session OBs,
    # previous-day highs/lows, and multi-session institutional order flow zones.
    lookback_candles = candles[-150:] if len(candles) >= 150 else candles
    fvgs = detect_fvgs(lookback_candles, atr=atr)
    obs = detect_order_blocks(lookback_candles)
    sweeps = detect_liquidity_sweeps(candles, period=15)

    if not sweeps:
        return None

    latest_sweep = sweeps[-1]
    swings = detect_swing_points(candles, left=2, right=2)

    # ── Bullish ICT Setup (SSL Swept -> Bullish MSS -> Retest Discount FVG/OB) ──
    if latest_sweep["direction"] == "BULLISH_SWEEP":
        sweep_low = float(latest_sweep.get("price", 0.0))
        # Find displacement high after the sweep
        recent_highs = [float(_c_val(c, "high", 0.0)) for c in candles[-10:]]
        disp_high = max(recent_highs) if recent_highs else current_price + atr

        # Dealing range equilibrium (50% level)
        equilibrium = (sweep_low + disp_high) / 2.0
        # Check if current price is in Discount (< 50% equilibrium)
        in_discount = current_price <= (equilibrium + atr * 0.4)

        # Check for active bullish FVG or OB near current price
        valid_fvgs = [f for f in fvgs if f["type"] == "BULLISH" and (f["bottom"] - atr * 0.5 <= current_price <= f["top"] + atr * 0.8)]
        valid_obs = [ob for ob in obs if ob["type"] == "BULLISH" and (ob["bottom"] - atr * 0.5 <= current_price <= ob["top"] + atr * 0.8)]

        # ChoCH check: did price break upward structure?
        choch = detect_bos_choch(candles, lookback=15)
        has_bull_shift = choch["type"] in ("CHOCH_BULL", "BOS_BULL") or (current_price > sweep_low + atr * 0.5)

        if in_discount and (valid_fvgs or valid_obs or has_bull_shift) and sweep_low > 0:
            sl_price = sweep_low - (atr * 0.3)  # Invalidation below sweep low
            sl_dist = abs(current_price - sl_price)
            # Target opposite liquidity pool (recent swing high or minimum 2.2R)
            eligible_highs = [sh["price"] for sh in swings["highs"] if sh["price"] > current_price + sl_dist]
            target_high = max(eligible_highs) if eligible_highs else (current_price + sl_dist * min_rr)
            tp_price = max(target_high, current_price + sl_dist * min_rr)
            rr = (tp_price - current_price) / max(0.0001, sl_dist)

            if rr >= min_rr:
                return {
                    "action": "buy",
                    "entry_price": current_price,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "sl_points": sl_dist,
                    "tp_points": tp_price - current_price,
                    "rr": rr,
                    "setup_type": "ICT_BULLISH_REVERSAL",
                    "sweep_price": sweep_low,
                    "fvg": valid_fvgs[-1] if valid_fvgs else None,
                    "ob": valid_obs[-1] if valid_obs else None,
                    "equilibrium": equilibrium,
                    "strength": min(92.0, 75.0 + (5.0 if valid_fvgs else 0.0) + (5.0 if valid_obs else 0.0) + (5.0 if has_bull_shift else 0.0))
                }

    # ── Bearish ICT Setup (BSL Swept -> Bearish MSS -> Retest Premium FVG/OB) ──
    elif latest_sweep["direction"] == "BEARISH_SWEEP":
        sweep_high = float(latest_sweep.get("price", 0.0))
        # Find displacement low after the sweep
        recent_lows = [float(_c_val(c, "low", 0.0)) for c in candles[-10:]]
        disp_low = min(recent_lows) if recent_lows else current_price - atr

        # Dealing range equilibrium (50% level)
        equilibrium = (sweep_high + disp_low) / 2.0
        # Check if current price is in Premium (> 50% equilibrium)
        in_premium = current_price >= (equilibrium - atr * 0.2)

        # Check for active bearish FVG or OB near current price
        valid_fvgs = [f for f in fvgs if f["type"] == "BEARISH" and (f["bottom"] - atr * 0.8 <= current_price <= f["top"] + atr * 0.5)]
        valid_obs = [ob for ob in obs if ob["type"] == "BEARISH" and (ob["bottom"] - atr * 0.8 <= current_price <= ob["top"] + atr * 0.5)]

        # ChoCH check: did price break downward structure?
        choch = detect_bos_choch(candles, lookback=15)
        has_bear_shift = choch["type"] in ("CHOCH_BEAR", "BOS_BEAR") or (current_price < sweep_high - atr * 0.5)

        if in_premium and (valid_fvgs or valid_obs or has_bear_shift) and sweep_high > 0:
            sl_price = sweep_high + (atr * 0.3)  # Invalidation above sweep high
            sl_dist = abs(sl_price - current_price)
            # Target opposite liquidity pool (recent swing low or minimum 2.2R)
            eligible_lows = [sl_["price"] for sl_ in swings["lows"] if sl_["price"] < current_price - sl_dist]
            target_low = min(eligible_lows) if eligible_lows else (current_price - sl_dist * min_rr)
            tp_price = min(target_low, current_price - sl_dist * min_rr)
            rr = (current_price - tp_price) / max(0.0001, sl_dist)

            if rr >= min_rr:
                return {
                    "action": "sell",
                    "entry_price": current_price,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "sl_points": sl_dist,
                    "tp_points": current_price - tp_price,
                    "rr": rr,
                    "setup_type": "ICT_BEARISH_REVERSAL",
                    "sweep_price": sweep_high,
                    "fvg": valid_fvgs[-1] if valid_fvgs else None,
                    "ob": valid_obs[-1] if valid_obs else None,
                    "equilibrium": equilibrium,
                    "strength": min(92.0, 75.0 + (5.0 if valid_fvgs else 0.0) + (5.0 if valid_obs else 0.0) + (5.0 if has_bear_shift else 0.0))
                }

    return None


def calculate_liquidity_heatmap(
    orderbook: Dict[str, Any], mark_price: float, range_pct: float = 2.0
) -> Dict[str, Any]:
    """
    Analyze resting limit orders in the L2 orderbook.
    Finds resting liquidity pools (clusters of large orders) and calculates
    resting bid/ask liquidity ratio.
    """
    result = {
        "bid_liquidity_usd": 0.0,
        "ask_liquidity_usd": 0.0,
        "liquidity_ratio": 0.5,
        "buy_liquidity_pools": [],  # List of price levels
        "sell_liquidity_pools": [],
    }

    if not isinstance(orderbook, dict):
        orderbook = {}

    bids = orderbook.get("bids", []) or []
    asks = orderbook.get("asks", []) or []

    if not bids and not asks:
        return result

    bid_vol_in_range = 0.0
    ask_vol_in_range = 0.0

    lower_bound = mark_price * (1.0 - range_pct / 100.0)
    upper_bound = mark_price * (1.0 + range_pct / 100.0)

    # Process Bids
    processed_bids = []
    for item in bids:
        try:
            price = float(item[0])
            size = float(item[1])
        except (IndexError, ValueError, TypeError):
            continue

        if lower_bound <= price <= mark_price:
            bid_vol_in_range += size * price
            processed_bids.append((price, size))

    # Process Asks
    processed_asks = []
    for item in asks:
        try:
            price = float(item[0])
            size = float(item[1])
        except (IndexError, ValueError, TypeError):
            continue

        if mark_price <= price <= upper_bound:
            ask_vol_in_range += size * price
            processed_asks.append((price, size))

    result["bid_liquidity_usd"] = bid_vol_in_range
    result["ask_liquidity_usd"] = ask_vol_in_range

    total_vol = bid_vol_in_range + ask_vol_in_range
    if total_vol > 0.0:
        result["liquidity_ratio"] = bid_vol_in_range / total_vol

    # Identify top 3 resting liquidity pools on both sides (by size)
    processed_bids.sort(key=lambda x: x[1], reverse=True)
    processed_asks.sort(key=lambda x: x[1], reverse=True)

    result["buy_liquidity_pools"] = [p[0] for p in processed_bids[:3]]
    result["sell_liquidity_pools"] = [p[0] for p in processed_asks[:3]]

    return result


def analyze_smc_setup(
    candles_5m: List[Dict[str, Any]],
    candles_1h: List[Dict[str, Any]],
    orderbook: Optional[Dict[str, Any]] = None,
    mark_price: float = 0.0
) -> Dict[str, Any]:
    """
    Combine SMC, ICT sweeps, and Orderbook Liquidity into a single trading bias report.
    Returns:
        {
            "bias_score": float (-1.0 to 1.0),
            "signal": "BUY" | "SELL" | "NEUTRAL",
            "reasoning": str,
            "fvg_count": int,
            "ob_present": bool,
            "liquidity_ratio": float,
            "buy_pools": list,
            "sell_pools": list
        }
    """
    # 1. Check sweeps on 5m candles
    sweeps = detect_sweeps(candles_5m, period=20)
    
    # 2. Get unmitigated FVGs and OBs
    fvgs = detect_fvgs(candles_5m)
    obs = detect_order_blocks(candles_5m)
    
    unmit_bull_fvg = any(f["type"] == "BULLISH" and not f["mitigated"] for f in fvgs)
    unmit_bear_fvg = any(f["type"] == "BEARISH" and not f["mitigated"] for f in fvgs)
    
    unmit_bull_ob = any(o["type"] == "BULLISH" and not o["mitigated"] for o in obs)
    unmit_bear_ob = any(o["type"] == "BEARISH" and not o["mitigated"] for o in obs)

    # 3. Analyze higher time frame (1h) bias
    htf_sweeps = detect_sweeps(candles_1h, period=10)
    
    # 4. Integrate Liquidity Heatmap
    liq_ratio = 0.5
    buy_pools = []
    sell_pools = []
    if orderbook and mark_price > 0.0:
        liq_analysis = calculate_liquidity_heatmap(orderbook, mark_price)
        liq_ratio = liq_analysis["liquidity_ratio"]
        buy_pools = liq_analysis["buy_liquidity_pools"]
        sell_pools = liq_analysis["sell_liquidity_pools"]

    # 5. Core SMC Rules & Bias Calculation
    bias_score = 0.0
    reasons = []

    # Sweep signals
    if sweeps["swept_ssl"]:
        bias_score += 0.4
        reasons.append("SSL Swept (Sell-Side Liquidity)")
    if sweeps["swept_bsl"]:
        bias_score -= 0.4
        reasons.append("BSL Swept (Buy-Side Liquidity)")

    # Structure support / blocks
    if unmit_bull_ob:
        bias_score += 0.2
        reasons.append("Bullish OB Active")
    if unmit_bear_ob:
        bias_score -= 0.2
        reasons.append("Bearish OB Active")

    # Fair Value Gaps
    if unmit_bull_fvg:
        bias_score += 0.15
        reasons.append("Bullish FVG Open")
    if unmit_bear_fvg:
        bias_score -= 0.15
        reasons.append("Bearish FVG Open")

    # Orderbook Liquidity bias
    if liq_ratio > 0.60:
        bias_score += 0.15
        reasons.append("Resting Bids Cluster")
    elif liq_ratio < 0.40:
        bias_score -= 0.15
        reasons.append("Resting Asks Cluster")

    # Higher Time Frame Trend (strict alignment requirement)
    htf_trend = "NEUTRAL"
    try:
        closes_1h = [float(c["close"]) for c in candles_1h]
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
        from quantclaw.utils.indicators import calculate_ema_latest
        htf_ema = calculate_ema_latest(closes_1h, 20) if len(closes_1h) >= 20 else (sum(closes_1h) / len(closes_1h) if closes_1h else 0)
        htf_trend = "BULLISH" if (closes_1h and closes_1h[-1] > htf_ema) else "BEARISH"
        if htf_trend == "BULLISH":
            bias_score += 0.15
        elif htf_trend == "BEARISH":
            bias_score -= 0.15
    except Exception:
        pass

    # Clamp bias score
    bias_score = max(-1.0, min(1.0, bias_score))

    # Determine Signal (Strictly require bias threshold of 0.55 AND HTF trend alignment)
    signal = "NEUTRAL"
    if bias_score >= 0.55 and htf_trend == "BULLISH":
        signal = "BUY"
    elif bias_score <= -0.55 and htf_trend == "BEARISH":
        signal = "SELL"

    reasoning_text = ", ".join(reasons) if reasons else "No clear structure setups"
    
    return {
        "bias_score": round(bias_score, 2),
        "signal": signal,
        "reasoning": f"{signal} Setup: {reasoning_text} | HTF Alignment.",
        "fvg_count": len([f for f in fvgs if not f["mitigated"]]),
        "ob_present": unmit_bull_ob or unmit_bear_ob,
        "liquidity_ratio": round(liq_ratio, 2),
        "buy_pools": buy_pools,
        "sell_pools": sell_pools
    }
