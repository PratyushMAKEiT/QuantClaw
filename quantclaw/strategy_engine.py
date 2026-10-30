# ==============================================================================
# quantclaw/strategy_engine.py — 24/7 Multi-Engine Strategy Matrix (MT5)
# ==============================================================================
"""
24/7 Multi-Engine Strategy Matrix for MetaTrader 5.
Runs 5 distinct institutional trading strategies in parallel across multi-timeframe
candles (M1, M5, M15, M30, H1, H4):

  1. SMC Liquidity Sweeps & Order Block Engine (Smart Money Concepts / ICT)
  2. Institutional Trend & Momentum Engine (OCC R5 SMMA Ribbon)
  3. Eyes Smart Structure Pro (Pivot Breaks + ATR Impulse Wave)
  4. Mean-Reversion & Squeeze Snapper (RSI/Stochastic Divergence + Bollinger Bands)
  5. Quant Way Institutional Flow (EMA 20/50 Pullback + Volume Surge)

Emits unified StrategySignal objects with precise stop loss and take profit targets.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional
from quantclaw.utils.logger import get_logger
from quantclaw.models import StrategySignal
from quantclaw.utils.indicators import (
    calculate_atr,
    calculate_rsi,
    calculate_ema_latest,
    calculate_smma_series,
    calculate_bollinger_bands,
    calculate_stochastic,
    calculate_macd,
    calculate_volume_metrics,
    calculate_adx,
    calculate_supertrend_latest,
    calculate_ema_series,
)
from quantclaw.utils.smc_analysis import (
    _c_val,
    detect_fvgs,
    detect_order_blocks,
    detect_liquidity_sweeps,
    detect_sweeps,
    evaluate_institutional_ict_setup,
    detect_bos_choch,
)

logger = get_logger(__name__)

from quantclaw.market_calendar import MarketCalendar
_calendar = MarketCalendar()


class StrategyEngine:
    """Evaluates 5 institutional strategies on live MT5 multi-timeframe candles."""

    def __init__(self, config: Any, market_engine: Any) -> None:
        self.config = config
        self.market = market_engine
        self._signal_callbacks: List[Callable[[StrategySignal], Any]] = []
        self._recent_signals: deque = deque(maxlen=200)

        # Anti-spam cooldown per symbol + strategy: key -> timestamp
        self._cooldowns: Dict[str, float] = {}

    def subscribe(self, callback: Callable[[StrategySignal], Any]) -> None:
        """Register callback for new strategy signals."""
        self._signal_callbacks.append(callback)

    def on_candle_close(self, symbol: str, timeframe: str, candle: Dict[str, Any]) -> None:
        """Called automatically by MarketEngine on every closed candle."""
        if timeframe not in ('M5', 'M15', 'H1', 'H4'): return
        self.scan_symbol(symbol, timeframe)

    def scan_symbol(self, symbol: str, timeframe: str = "M15") -> List[StrategySignal]:
        """Scan all active strategies for a given symbol and timeframe."""
        # Session quality gate — only apply if session filter is enabled
        if getattr(self.config, 'enable_session_filter', False):
            session_score = _calendar.get_session_score(symbol)
            min_session = float(getattr(self.config, 'session_min_score', 20.0))
            if session_score < min_session:
                return []  # Wrong session — don't waste CPU evaluating signals

        # Day of week gate — reduce activity on Friday afternoon
        dow_score = _calendar.get_day_of_week_score(symbol)
        if dow_score < 40.0:
            return []  # Friday close or weekend
        candles = self.market.get_candles(symbol, timeframe, 100)
        if len(candles) < 20:
            return []

        signals: List[StrategySignal] = []

        if getattr(self.config, "strategy_titan_pro_enabled", True):
            try:
                sig = self._eval_titan_pro(symbol, timeframe, candles)
                if sig: signals.append(sig)
            except Exception as e:
                logger.warning(f"Error in _eval_titan_pro: {e}")

        if getattr(self.config, "strategy_smc_enabled", True):
            try:
                sig = self._eval_smc_liquidity(symbol, timeframe, candles)
                if sig: signals.append(sig)
            except Exception as e:
                logger.warning(f"Error in _eval_smc_liquidity: {e}")

        if getattr(self.config, "strategy_occ_r5_enabled", True):
            try:
                sig = self._eval_occ_r5_trend(symbol, timeframe, candles)
                if sig: signals.append(sig)
            except Exception as e:
                logger.warning(f"Error in _eval_occ_r5_trend: {e}")

        if getattr(self.config, "strategy_eyes_sme_enabled", True):
            try:
                sig = self._eval_eyes_sme(symbol, timeframe, candles)
                if sig: signals.append(sig)
            except Exception as e:
                logger.warning(f"Error in _eval_eyes_sme: {e}")

        if getattr(self.config, "strategy_mean_rev_enabled", True):
            try:
                sig = self._eval_mean_reversion(symbol, timeframe, candles)
                if sig: signals.append(sig)
            except Exception as e:
                logger.warning(f"Error in _eval_mean_reversion: {e}")

        if getattr(self.config, "strategy_quant_way_enabled", True):
            try:
                sig = self._eval_quant_way(symbol, timeframe, candles)
                if sig: signals.append(sig)
            except Exception as e:
                logger.warning(f"Error in _eval_quant_way: {e}")


        # Dispatch signals through cooldown filter
        for s in signals:
            ckey = f"{s.symbol}:{s.strategy}"
            now = time.time()
            # 5-minute cooldown per strategy per symbol
            if now - self._cooldowns.get(ckey, 0) < getattr(self.config, 'signal_cooldown_seconds', 300):
                continue

            self._cooldowns[ckey] = now
            self._recent_signals.append(s)
            

            logger.info(
                f"🎯 Strategy Signal: [{s.strategy.upper()}] {s.action.upper()} {s.symbol} ({s.timeframe}) @ {s.price:.5f} | Strength: {s.strength:.1f}"
            )
            for cb in self._signal_callbacks:
                try:
                    cb(s)
                except Exception as e:
                    logger.error(f"Error in strategy signal callback: {e}")

        return signals

    # ── Strategy 0: TITAN PRO Institutional Order Flow & Liquidity Reversal ────

    def _eval_titan_pro(
        self, symbol: str, timeframe: str, candles: List[Dict[str, Any]]
    ) -> Optional[StrategySignal]:
        """
        Flagship Institutional Strategy: TITAN PRO (Turtle Soup & Displacement Reversal).
        
        Rules:
        1. Multi-Timeframe Institutional Trend:
           - H1 EMA 50 & H1 Supertrend must confirm the macro direction.
           - H4 (if available) must not oppose H1.
        2. Liquidity Sweep (Turtle Soup):
           - In Bullish trend: price dips below swing low (Sell-Side Liquidity grab) and rejects upward.
           - In Bearish trend: price pushes above swing high (Buy-Side Liquidity grab) and rejects downward.
        3. Displacement Confirmation:
           - Rejection candle with strong wick on liquidity grab side or strong body in trend direction.
           - ADX >= adx_trend_threshold to avoid dead markets.
        4. Target:
           - Structural SL beyond sweep wick + ATR buffer.
           - 1:2.2 Risk-Reward ratio.
        """
        if len(candles) < 20:
            return None

        atr = calculate_atr(candles, 14)
        if atr <= 0:
            return None

        # 1. ADX Filter: Reject completely dead sideways markets
        adx_data = calculate_adx(candles, 14)
        adx_val = float(adx_data.get("adx", 0.0))
        adx_thresh = float(getattr(self.config, "adx_trend_threshold", 13.0))
        if adx_val < adx_thresh:
            return None

        # 2. HTF (H1) Macro Trend Gate
        h1_candles = self.market.get_candles(symbol, "H1", 60)
        if len(h1_candles) < 25:
            return None

        h1_closes = [float(c["close"]) for c in h1_candles]
        h1_ema50 = calculate_ema_latest(h1_closes, min(50, len(h1_closes)))
        h1_st = calculate_supertrend_latest(h1_candles, period=10, multiplier=3.0)
        h1_trend = h1_st.get("trend", "NONE")

        h1_bullish = (h1_closes[-1] >= h1_ema50 * 0.998) and (h1_trend == "BULLISH")
        h1_bearish = (h1_closes[-1] <= h1_ema50 * 1.002) and (h1_trend == "BEARISH")

        if not h1_bullish and not h1_bearish:
            return None

        # Check H4 alignment if available
        h4_candles = self.market.get_candles(symbol, "H4", 40)
        if len(h4_candles) >= 20:
            h4_st = calculate_supertrend_latest(h4_candles, period=10, multiplier=3.0)
            h4_trend = h4_st.get("trend", "NONE")
            if h1_bullish and h4_trend == "BEARISH":
                return None
            if h1_bearish and h4_trend == "BULLISH":
                return None

        action = "buy" if h1_bullish else "sell"

        # 3. Liquidity Sweep & Displacement Detection
        lookback = int(getattr(self.config, "titan_pro_swing_lookback", 15))
        lookback = min(lookback, len(candles) - 3)
        if lookback < 5:
            return None

        prior_candles = candles[-(lookback + 2):-2]
        if not prior_candles:
            return None

        prior_highs = [float(_c_val(c, "high", 0.0)) for c in prior_candles]
        prior_lows = [float(_c_val(c, "low", 0.0)) for c in prior_candles]
        swing_high = max(prior_highs) if prior_highs else 0.0
        swing_low = min(prior_lows) if prior_lows else 0.0

        if swing_high <= 0 or swing_low <= 0:
            return None

        # Inspect the last 2 candles for sweep & displacement
        c_last = candles[-1]
        c_prev = candles[-2]

        last_high = float(_c_val(c_last, "high", 0.0))
        last_low = float(_c_val(c_last, "low", 0.0))
        last_close = float(_c_val(c_last, "close", 0.0))
        last_open = float(_c_val(c_last, "open", 0.0))

        prev_high = float(_c_val(c_prev, "high", 0.0))
        prev_low = float(_c_val(c_prev, "low", 0.0))
        prev_close = float(_c_val(c_prev, "close", 0.0))

        sweep_detected = False
        sweep_level = 0.0

        if action == "buy":
            # SSL Sweep: price dropped below swing_low but closed back above it
            swept_in_last = (last_low < swing_low and last_close > swing_low)
            swept_in_prev = (prev_low < swing_low and (prev_close > swing_low or last_close > swing_low))
            if swept_in_last or swept_in_prev:
                # Displacement check: Bullish rejection wick or strong green body
                rng = max(1e-5, last_high - last_low)
                body = abs(last_close - last_open)
                lower_wick = min(last_open, last_close) - last_low
                is_bull_displacement = (last_close > last_open and body >= rng * 0.40) or (lower_wick >= rng * 0.35) or (last_close > prev_high)
                if is_bull_displacement:
                    sweep_detected = True
                    sweep_level = min(last_low, prev_low)
        else:
            # BSL Sweep: price popped above swing_high but closed back below it
            swept_in_last = (last_high > swing_high and last_close < swing_high)
            swept_in_prev = (prev_high > swing_high and (prev_close < swing_high or last_close < swing_high))
            if swept_in_last or swept_in_prev:
                # Displacement check: Bearish rejection wick or strong red body
                rng = max(1e-5, last_high - last_low)
                body = abs(last_close - last_open)
                upper_wick = last_high - max(last_open, last_close)
                is_bear_displacement = (last_close < last_open and body >= rng * 0.40) or (upper_wick >= rng * 0.35) or (last_close < prev_low)
                if is_bear_displacement:
                    sweep_detected = True
                    sweep_level = max(last_high, prev_high)

        if not sweep_detected:
            # Secondary check: built-in detect_sweeps
            swp = detect_sweeps(candles, period=lookback)
            if action == "buy" and swp.get("swept_ssl") and last_close > last_open:
                sweep_detected = True
                sweep_level = float(swp.get("ssl_price", last_low))
            elif action == "sell" and swp.get("swept_bsl") and last_close < last_open:
                sweep_detected = True
                sweep_level = float(swp.get("bsl_price", last_high))

        if not sweep_detected:
            return None

        # 4. Entry, SL, and TP Calculation (High RR: 1:2.8)
        entry_price = last_close
        rr = float(getattr(self.config, "titan_pro_rr_ratio", 2.8))
        min_sl = max(0.35 * atr, 1e-4)

        if action == "buy":
            sl_price = sweep_level - (0.25 * atr)
            sl_points = entry_price - sl_price
            if sl_points < min_sl:
                sl_points = min_sl
                sl_price = entry_price - sl_points
            tp_points = sl_points * rr
        else:
            sl_price = sweep_level + (0.25 * atr)
            sl_points = sl_price - entry_price
            if sl_points < min_sl:
                sl_points = min_sl
                sl_price = entry_price + sl_points
            tp_points = sl_points * rr

        # Strength calculation
        strength = 88.0
        if len(h4_candles) >= 20:
            strength += 4.0
        vol_data = calculate_volume_metrics(candles, 20)
        if vol_data.get("relative_volume", 1.0) >= 1.2:
            strength += 4.0

        return StrategySignal(
            strategy="titan_pro",
            symbol=symbol,
            action=action,
            timeframe=timeframe,
            price=entry_price,
            sl_points=sl_points,
            tp_points=tp_points,
            strength=min(98.0, strength),
            metadata={
                "htf_trend": "BULLISH" if action == "buy" else "BEARISH",
                "sweep_level": sweep_level,
                "sweep_type": "SSL_GRAB" if action == "buy" else "BSL_GRAB",
                "rr_ratio": rr,
                "atr": atr,
            }
        )

    # ── Strategy 1: SMC Liquidity & Order Block Engine ─────────────────────────

    def _eval_smc_liquidity(
        self, symbol: str, timeframe: str, candles: List[Dict[str, Any]]
    ) -> Optional[StrategySignal]:
        """
        Institutional Smart Money Concepts (ICT) Engine:
        Detects multi-bar Liquidity Sweep (BSL/SSL) + Market Structure Shift (MSS/ChoCH) +
        Retest into Fair Value Gap (FVG) / Order Block (OB) in Premium/Discount zones.

        Filters: H1 HTF trend, ADX >= 20 (trend strength), Supertrend directional alignment.
        """
        atr = calculate_atr(candles, 14)
        if atr <= 0:
            return None

        # ADX Trend Strength Filter: Reject setups in ranging/choppy markets
        adx_data = calculate_adx(candles, 14)
        adx_value = adx_data.get("adx", 0.0)
        adx_threshold = float(getattr(self.config, "adx_trend_threshold", 13.0))
        if adx_value < adx_threshold:
            logger.debug(f"⏳ ICT skipped on {symbol}: ADX={adx_value:.1f} < {adx_threshold:.0f} (choppy market)")
            return None

        # 1. Run complete ICT setup detector (Higher RR >= 2.5)
        setup = evaluate_institutional_ict_setup(candles, atr, min_rr=2.5)
        if not setup:
            return None

        action = setup["action"]

        # 2. HTF (H1) Trend & Order Flow Filter
        h1_candles = self.market.get_candles(symbol, "H1", 60)
        h1_aligned = True
        if len(h1_candles) >= 30:
            h1_closes = [float(c["close"]) for c in h1_candles]
            h1_ema50 = calculate_ema_latest(h1_closes, min(50, len(h1_closes)))
            if action == "buy":
                h1_choch = detect_bos_choch(h1_candles, lookback=15)
                h1_aligned = (h1_closes[-1] >= h1_ema50 * 0.998) or (h1_choch["type"] in ("CHOCH_BULL", "BOS_BULL"))
            else:
                h1_choch = detect_bos_choch(h1_candles, lookback=15)
                h1_aligned = (h1_closes[-1] <= h1_ema50 * 1.002) or (h1_choch["type"] in ("CHOCH_BEAR", "BOS_BEAR"))

        if not h1_aligned:
            logger.debug(f"⏳ ICT setup on {symbol} ({action.upper()}) rejected by H1 HTF trend filter.")
            return None

        # 3. Supertrend Directional Filter: Reject if Supertrend opposes the trade direction
        # This eliminates the largest class of counter-trend false entries
        st_data = calculate_supertrend_latest(candles, period=10, multiplier=3.0)
        st_trend = st_data.get("trend", "BULLISH")
        if (action == "buy" and st_trend == "BEARISH") or (action == "sell" and st_trend == "BULLISH"):
            logger.debug(f"⏳ ICT setup on {symbol} ({action.upper()}) rejected by Supertrend ({st_trend}) filter.")
            return None

        price = setup["entry_price"]
        sl_points = setup["sl_points"]
        tp_points = setup["tp_points"]
        strength = setup["strength"]

        return StrategySignal(
            strategy="smc_liquidity",
            symbol=symbol,
            action=action,
            timeframe=timeframe,
            price=price,
            sl_points=sl_points,
            tp_points=tp_points,
            strength=strength,
            metadata={
                "setup_type": setup["setup_type"],
                "sweep_price": setup["sweep_price"],
                "equilibrium": setup["equilibrium"],
                "rr": setup["rr"],
                "fvg": setup.get("fvg"),
                "ob": setup.get("ob"),
                "adx": adx_value,
                "supertrend": st_trend,
            },
        )



    # ── Strategy 2: OCC R5 Institutional Trend & SMMA Cross ───────────────────

    def _eval_occ_r5_trend(
        self, symbol: str, timeframe: str, candles: List[Dict[str, Any]]
    ) -> Optional[StrategySignal]:
        """
        OCC R5 SMMA Crossover System:
        Fast SMMA cross over Slow SMMA with multi-timeframe trend alignment.
        Filters: ADX >= 20 (prevents ranging market false crosses), Supertrend direction.
        """
        closes = [float(c["close"]) for c in candles]
        opens = [float(c["open"]) for c in candles]
        period = int(getattr(self.config, "occ_r5_smma_period", 8))
        if len(closes) < period * 2:
            return None

        smma_close = calculate_smma_series(closes, period)
        smma_open = calculate_smma_series(opens, period)
        atr = calculate_atr(candles, 14)
        if atr <= 0:
            return None
        price = closes[-1]

        # ADX Filter: SMMA crossovers in ranging markets (ADX < 20) are pure noise
        adx_data = calculate_adx(candles, 14)
        adx_value = adx_data.get("adx", 0.0)
        if adx_value < 20.0:
            return None  # Choppy market — SMMA crosses unreliable

        # Crossover detection on last 2 bars
        c0, o0 = smma_close[-1], smma_open[-1]
        c1, o1 = smma_close[-2], smma_open[-2]

        # Guard: 0.0 = warmup sentinel from SMMA — comparison would be meaningless noise
        if c0 == 0.0 or o0 == 0.0 or c1 == 0.0 or o1 == 0.0:
            return None

        bull_cross = (c1 <= o1) and (c0 > o0)
        bear_cross = (c1 >= o1) and (c0 < o0)

        # Supertrend directional filter
        st_data = calculate_supertrend_latest(candles, period=10, multiplier=3.0)
        st_trend = st_data.get("trend", "BULLISH")

        # Higher Timeframe Trend Filter (H1 EMA 50)
        h1_candles = self.market.get_candles(symbol, "H1", 60)
        h1_trend_bull = False
        h1_trend_bear = False
        if len(h1_candles) >= 50:
            h1_closes = [float(c["close"]) for c in h1_candles]
            h1_ema50 = calculate_ema_latest(h1_closes, 50)
            h1_trend_bull = h1_closes[-1] > h1_ema50
            h1_trend_bear = h1_closes[-1] < h1_ema50

        if bull_cross and h1_trend_bull and st_trend == "BULLISH":
            sl_dist = atr * 0.9
            tp_dist = sl_dist * 2.8
            return StrategySignal(
                strategy="occ_r5_trend",
                symbol=symbol,
                action="buy",
                timeframe=timeframe,
                price=price,
                sl_points=sl_dist,
                tp_points=tp_dist,
                strength=78.0,
            )
        elif bear_cross and h1_trend_bear and st_trend == "BEARISH":
            sl_dist = atr * 0.9
            tp_dist = sl_dist * 2.8
            return StrategySignal(
                strategy="occ_r5_trend",
                symbol=symbol,
                action="sell",
                timeframe=timeframe,
                price=price,
                sl_points=sl_dist,
                tp_points=tp_dist,
                strength=78.0,
            )

        return None



    # ── Strategy 3: Eyes Smart Structure Pro ──────────────────────────────────

    def _eval_eyes_sme(
        self, symbol: str, timeframe: str, candles: List[Dict[str, Any]]
    ) -> Optional[StrategySignal]:
        """
        Eyes Smart Structure:
        Pivot breakout accompanied by ATR expansion impulse candle + volume surge.
        Filters: ADX >= 20 (trending breakout), Supertrend alignment, H1 trend filter.
        """
        pivot_len = int(getattr(self.config, "eyes_sme_pivot_len", 5))
        atr_len = int(getattr(self.config, "eyes_sme_atr_len", 7))
        # FIX: Config desync — was hardcoded to 1.2 while config default is 1.5
        impulse_factor = float(getattr(self.config, "eyes_sme_impulse_factor", 1.5))

        if len(candles) < pivot_len * 2 + 5:
            return None

        atr = calculate_atr(candles, atr_len)
        if atr <= 0:
            return None
        price = float(candles[-1]["close"])
        body = abs(price - float(candles[-1]["open"]))

        # ADX Filter: Pivot breakouts only valid in trending markets
        adx_data = calculate_adx(candles, 14)
        adx_value = adx_data.get("adx", 0.0)
        if adx_value < 20.0:
            return None  # No valid trend — breakout likely to fail

        # Identify previous pivot high/low
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        pivot_high = max(highs[-(pivot_len * 2 + 3 + pivot_len) : -pivot_len - 1])
        pivot_low = min(lows[-(pivot_len * 2 + 3 + pivot_len) : -pivot_len - 1])

        # Volume check
        vol_metrics = calculate_volume_metrics(candles, 20)
        vol_ok = vol_metrics.get("volume_ratio", 1.0) >= 1.0

        # H1 trend filter
        h1_candles = self.market.get_candles(symbol, "H1", 60)
        h1_bull = True
        h1_bear = True
        if len(h1_candles) >= 30:
            h1_closes = [float(c["close"]) for c in h1_candles]
            h1_ema20 = calculate_ema_latest(h1_closes, 20)
            h1_ema50 = calculate_ema_latest(h1_closes, min(50, len(h1_closes)))
            h1_bull = h1_ema20 > h1_ema50
            h1_bear = h1_ema20 < h1_ema50

        # Bullish impulse breakout
        if price > pivot_high and body > (atr * impulse_factor) and vol_ok and h1_bull:
            sl_dist = atr * 0.9
            tp_dist = sl_dist * 2.8
            return StrategySignal(
                strategy="eyes_sme",
                symbol=symbol,
                action="buy",
                timeframe=timeframe,
                price=price,
                sl_points=sl_dist,
                tp_points=tp_dist,
                strength=82.0,
            )
        # Bearish impulse breakout
        elif price < pivot_low and body > (atr * impulse_factor) and vol_ok and h1_bear:
            sl_dist = atr * 0.9
            tp_dist = sl_dist * 2.8
            return StrategySignal(
                strategy="eyes_sme",
                symbol=symbol,
                action="sell",
                timeframe=timeframe,
                price=price,
                sl_points=sl_dist,
                tp_points=tp_dist,
                strength=82.0,
            )

        return None

    # ── Strategy 4: Mean-Reversion & Volatility Snapper ─────────────────────────

    def _eval_mean_reversion(
        self, symbol: str, timeframe: str, candles: List[Dict[str, Any]]
    ) -> Optional[StrategySignal]:
        """
        Mean-Reversion Snapper:
        Oversold/Overbought RSI + Stochastic with Bollinger Band extreme tag.
        Requires ADX < 30 (ranging market context) — mean reversion works in ranges, not trends.
        TP targeting correct: distance from current price TO middle band (not past it).
        """
        closes = [float(c["close"]) for c in candles]
        if len(closes) < 25:
            return None

        rsi = calculate_rsi(closes, 14)
        bb = calculate_bollinger_bands(closes, 20, 2.0)
        stoch = calculate_stochastic(candles, 14, 3)
        atr = calculate_atr(candles, 14)
        price = closes[-1]

        if atr <= 0:
            return None

        # ADX filter: Mean reversion only works in genuine ranging consolidation (ADX < 22)
        # Any ADX >= 22 indicates directional trend momentum where knife-catching causes steep drawdowns
        adx_data = calculate_adx(candles, 14)
        adx_value = adx_data.get("adx", 0.0)
        if adx_value >= 22.0:
            return None  # Trend momentum detected — mean reversion rejected

        # Macro Trend Alignment Guard: Never catch a falling knife against H1 trend
        h1_candles = self.market.get_candles(symbol, "H1", 50)
        h1_trend = "NEUTRAL"
        if len(h1_candles) >= 20:
            st_data = calculate_supertrend_latest(h1_candles, period=10, multiplier=3.0)
            h1_trend = st_data.get("trend", "NEUTRAL")

        middle_band = bb.get("middle", price)

        # Bullish Mean-Reversion (Oversold extreme) - Forbidden if H1 is Bearish
        if rsi < 35 and stoch["k"] < 25 and bb.get("pct_b", 1.0) <= 0.10:
            if h1_trend == "BEARISH":
                return None  # Do NOT buy into an H1 downtrend
            sl_dist = atr * 1.4
            raw_tp_dist = abs(middle_band - price) if middle_band > price else sl_dist * 1.5
            tp_dist = max(sl_dist * 1.5, raw_tp_dist)
            strength = 72.0 + (5.0 if rsi < 28 else 0.0)
            return StrategySignal(
                strategy="mean_reversion",
                symbol=symbol,
                action="buy",
                timeframe=timeframe,
                price=price,
                sl_points=sl_dist,
                tp_points=tp_dist,
                strength=min(85.0, strength),
            )
        # Bearish Mean-Reversion (Overbought extreme) - Forbidden if H1 is Bullish
        elif rsi > 65 and stoch["k"] > 75 and bb.get("pct_b", 0.0) >= 0.90:
            if h1_trend == "BULLISH":
                return None  # Do NOT short an H1 uptrend
            sl_dist = atr * 1.4
            raw_tp_dist = abs(price - middle_band) if middle_band < price else sl_dist * 1.5
            tp_dist = max(sl_dist * 1.5, raw_tp_dist)
            strength = 72.0 + (5.0 if rsi > 72 else 0.0)
            return StrategySignal(
                strategy="mean_reversion",
                symbol=symbol,
                action="sell",
                timeframe=timeframe,
                price=price,
                sl_points=sl_dist,
                tp_points=tp_dist,
                strength=min(85.0, strength),
            )

        return None

    # ── Strategy 5: Quant Way Institutional Flow ───────────────────────────────

    def _eval_quant_way(
        self, symbol: str, timeframe: str, candles: List[Dict[str, Any]]
    ) -> Optional[StrategySignal]:
        """
        Quant Way Flow:
        EMA 20/50 Trend Pullback + Rejection Wick (volume confirmation).
        Filters: ADX >= 20 (confirming trend context for pullback entry).
        """
        closes = [float(c["close"]) for c in candles]
        if len(closes) < 55:
            return None

        ema_fast = calculate_ema_latest(closes, int(getattr(self.config, "quant_way_ema_fast", 20)))
        ema_slow = calculate_ema_latest(closes, int(getattr(self.config, "quant_way_ema_slow", 50)))
        atr = calculate_atr(candles, 14)
        price = closes[-1]
        candle = candles[-1]

        if atr <= 0:
            return None

        # ADX Filter: Pullback strategies only work in trending markets
        adx_data = calculate_adx(candles, 14)
        adx_value = adx_data.get("adx", 0.0)
        if adx_value < 20.0:
            return None  # No trend context — pullback has no direction to return to

        high = float(candle["high"])
        low = float(candle["low"])
        open_p = float(candle["open"])
        vol_metrics = calculate_volume_metrics(candles, 20)
        # FIX: Config desync — was hardcoded to 1.2 while config default is 1.5
        vol_mult = float(getattr(self.config, "quant_way_vol_multiplier", 1.5))
        vol_ok = vol_metrics.get("volume_ratio", 1.0) >= vol_mult

        # Pullback proximity: price within 1.5*ATR of fast EMA
        near_ema_fast = abs(price - ema_fast) <= atr * 1.5

        # Bullish Pullback: fast EMA > slow EMA, price pulled back near fast EMA, rejection wick
        if ema_fast > ema_slow and near_ema_fast:
            lower_wick = min(open_p, price) - low
            body = abs(price - open_p)
            if lower_wick >= body * 0.5 and vol_ok:
                sl_dist = atr * 0.9
                tp_dist = sl_dist * 2.8
                return StrategySignal(
                    strategy="quant_way",
                    symbol=symbol,
                    action="buy",
                    timeframe=timeframe,
                    price=price,
                    sl_points=sl_dist,
                    tp_points=tp_dist,
                    strength=76.0,
                )
        # Bearish Pullback: fast EMA < slow EMA, price near fast EMA, rejection wick
        elif ema_fast < ema_slow and near_ema_fast:
            upper_wick = high - max(open_p, price)
            body = abs(price - open_p)
            if upper_wick >= body * 0.5 and vol_ok:
                sl_dist = atr * 0.9
                tp_dist = sl_dist * 2.8
                return StrategySignal(
                    strategy="quant_way",
                    symbol=symbol,
                    action="sell",
                    timeframe=timeframe,
                    price=price,
                    sl_points=sl_dist,
                    tp_points=tp_dist,
                    strength=76.0,
                )

        return None

    def get_recent_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return list of recent strategy signals as dictionaries."""
        signals = list(self._recent_signals)[-limit:]
        res = []
        for s in reversed(signals):
            if hasattr(s, "model_dump"):
                res.append(s.model_dump())
            elif hasattr(s, "dict"):
                res.append(s.dict())
            elif hasattr(s, "__dict__"):
                res.append(dict(s.__dict__))
            elif isinstance(s, dict):
                res.append(s)
        return res

