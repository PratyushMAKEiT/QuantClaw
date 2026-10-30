# ==============================================================================
# quantclaw/market_engine.py — 24/7 MetaTrader 5 Market Data Engine
# ==============================================================================
"""
24/7 High-Frequency Market Ingestion & Multi-Timeframe Buffer Manager for MT5.
Continuously fetches and buffers OHLCV candles & live ticks directly from
MetaTrader 5 for Forex, Gold, Crypto, and Indices across M1, M5, M15, M30, H1, H4, D1.
Calculates technical indicators & SMC structures on candle closes.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional
from quantclaw.utils.logger import get_logger
from quantclaw.market_calendar import MarketCalendar
from quantclaw.utils.indicators import (
    calculate_atr,
    calculate_rsi,
    calculate_ema_latest,
    calculate_smma_series,
    calculate_bollinger_bands,
    calculate_stochastic,
    calculate_macd,
    calculate_adx,
    calculate_volume_metrics,
    classify_volume_regime,
)
from quantclaw.utils.smc_analysis import detect_fvgs, detect_order_blocks, detect_liquidity_sweeps

logger = get_logger(__name__)

SUPPORTED_TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]


class MarketEngine:
    """
    24/7 Real-Time Multi-Symbol & Multi-Timeframe Data Engine.
    Polls MT5 at high frequency, manages in-memory candle buffers, and triggers
    callbacks for candle close and volatility spike events.
    """

    def __init__(self, mt5_client: Any, max_buffer_bars: int = 400) -> None:
        self.mt5 = mt5_client
        self.max_buffer_bars = max_buffer_bars

        # Multi-timeframe buffer: [symbol][timeframe] -> List[CandleDict]
        self._buffers: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        # Last known candle timestamp per symbol and timeframe
        self._last_candle_time: Dict[str, Dict[str, int]] = {}
        # Live ticks cache: [symbol] -> Dict
        self._live_ticks: Dict[str, Dict[str, Any]] = {}
        self._symbols: List[str] = []
        self._last_tf_poll: Dict[str, float] = {}

        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._subscribers: List[Callable[[str, str, Dict[str, Any]], Any]] = []
        self.calendar = MarketCalendar()
        self._volatility_states: Dict[str, str] = {}  # symbol -> "DORMANT"|"BUILDING"|"ACTIVE"|"EXPLOSIVE"|"COOLING"
        self._atr_history: Dict[str, list] = {}  # symbol -> last 20 ATR values for state machine

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def subscribe(self, callback: Callable[[str, str, Dict[str, Any]], Any]) -> None:
        """Subscribe a callback to candle close events: callback(symbol, timeframe, candle)."""
        self._subscribers.append(callback)

    async def start(self, symbols: List[str]) -> None:
        """Start the background 24/7 polling loop for specified symbols."""
        if self._running:
            return
        self._running = True
        self._symbols = symbols

        # Pre-seed initial candle buffers
        await self._seed_buffers(symbols)
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(f"🚀 Market Engine started: Monitoring {len(symbols)} symbols across {len(SUPPORTED_TIMEFRAMES)} timeframes.")

    async def stop(self) -> None:
        """Stop market engine."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("Market Engine stopped.")

    async def set_symbols(self, symbols: List[str]) -> None:
        """Dynamically re-seed and update monitored symbols while engine is running."""
        self._symbols = list(symbols)
        await self._seed_buffers(symbols)
        logger.info(f"🔄 Market Engine dynamically updated to {len(symbols)} symbols: {', '.join(symbols)}")

    # ── Seeding & Ingestion ───────────────────────────────────────────────────

    async def _seed_buffers(self, symbols: List[str]) -> None:
        """Initial load of historical candles from MT5."""
        for sym in symbols:
            info = await asyncio.to_thread(self.mt5.get_symbol_info, sym)
            if info is None: continue
            real_sym = getattr(info, "symbol", sym)
            keys_to_seed = set([sym, real_sym])

            for k in keys_to_seed:
                if k not in self._buffers:
                    self._buffers[k] = {}
                    self._last_candle_time[k] = {}

            for tf in SUPPORTED_TIMEFRAMES:
                try:
                    rates = await asyncio.to_thread(self.mt5.get_rates, real_sym, tf, self.max_buffer_bars)
                    for k in keys_to_seed:
                        if rates:
                            self._buffers[k][tf] = list(rates)
                            self._last_candle_time[k][tf] = rates[-1]["time"]
                        else:
                            self._buffers[k][tf] = []
                            self._last_candle_time[k][tf] = 0
                except Exception as e:
                    logger.warning(f"Error seeding {sym} ({real_sym}) {tf}: {e}")

    async def _poll_loop(self) -> None:
        """Continuous async loop polling live candles from MT5."""
        while self._running:
            try:
                if not self.mt5.is_connected():
                    await asyncio.sleep(2.0)
                    continue

                for sym in self._symbols:
                    info = await asyncio.to_thread(self.mt5.get_symbol_info, sym)
                    real_sym = getattr(info, "symbol", sym) if info else sym

                    # Update live tick
                    if info:
                        tick_data = {
                            "bid": info.bid,
                            "ask": info.ask,
                            "last": info.last,
                            "spread": info.spread,
                            "time": time.time(),
                        }
                        self._live_ticks[sym] = tick_data
                        self._live_ticks[real_sym] = tick_data

                        # Update live swap rates from broker if available
                        if hasattr(info, 'swap_long') and info.swap_long != 0:
                            self.calendar.update_live_swaps(sym, float(info.swap_long), float(info.swap_short))

                    # Poll fast timeframes (M1, M5, M15) on every loop, slower timeframes less often
                    TF_POLL_INTERVAL = {'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30, 'H1': 60, 'H4': 300, 'D1': 600}
                    for tf in SUPPORTED_TIMEFRAMES:
                        if time.time() - self._last_tf_poll.get(f'{sym}:{tf}', 0) < TF_POLL_INTERVAL.get(tf, 5):
                            continue
                        self._last_tf_poll[f'{sym}:{tf}'] = time.time()
                        try:
                            recent_rates = await asyncio.to_thread(self.mt5.get_rates, real_sym, tf, 5)
                            if not recent_rates:
                                continue

                            for k in set([sym, real_sym]):
                                buf = self._buffers.setdefault(k, {}).setdefault(tf, [])
                                last_known = self._last_candle_time.setdefault(k, {}).get(tf, 0)
                                latest_incoming = recent_rates[-1]["time"]

                                # Detect new candle close
                                if latest_incoming > last_known and last_known > 0:
                                    closed_candle = recent_rates[-2] if len(recent_rates) >= 2 else recent_rates[0]
                                    buf.append(closed_candle)
                                    if len(buf) > self.max_buffer_bars:
                                        buf.pop(0)

                                    self._last_candle_time[k][tf] = latest_incoming
                                    # Dispatch candle close event
                                    if k == sym:
                                        self._dispatch_candle_event(sym, tf, closed_candle)
                                else:
                                    # Update current developing candle in-place
                                    if buf:
                                        buf[-1] = recent_rates[-1]
                                    else:
                                        buf.extend(recent_rates)

                        except Exception as tf_err:
                            logger.warning(f"Error updating {sym} {tf}: {tf_err}")

                await asyncio.sleep(0.75)  # High frequency 750ms cycle
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"MarketEngine poll loop error: {e}")
                await asyncio.sleep(1.0)

    def _dispatch_candle_event(self, symbol: str, timeframe: str, candle: Dict[str, Any]) -> None:
        """Trigger callbacks on new closed candle."""
        for cb in self._subscribers:
            try:
                cb(symbol, timeframe, candle)
            except Exception as e:
                logger.error(f"Error in subscriber callback: {e}")

    # ── Market Analysis & Indicators Snapshot ──────────────────────────────────

    def get_candles(self, symbol: str, timeframe: str = "M15", limit: int = 100) -> List[Dict[str, Any]]:
        """Get cached candles for a symbol and timeframe."""
        buf = self._buffers.get(symbol, {}).get(timeframe.upper(), [])
        if not buf and hasattr(self.mt5, "resolve_symbol"):
            real_sym = self.mt5.resolve_symbol(symbol)
            buf = self._buffers.get(real_sym, {}).get(timeframe.upper(), [])
        return buf[-limit:] if buf else []

    def get_live_tick(self, symbol: str) -> dict:
        tick = self._live_ticks.get(symbol, {})
        if not tick and hasattr(self.mt5, "resolve_symbol"):
            tick = self._live_ticks.get(self.mt5.resolve_symbol(symbol), {})
        return tick

    def get_latest_price(self, symbol: str) -> float:
        """Get the latest price for a symbol."""
        tick = self._live_ticks.get(symbol)
        if tick and tick.get("last", 0) > 0:
            return float(tick["last"])
        m1 = self.get_candles(symbol, "M1", 1)
        if m1:
            return float(m1[-1]["close"])
        return 0.0

    def _update_volatility_state(self, symbol: str, atr: float) -> str:
        hist = self._atr_history.setdefault(symbol, [])
        hist.append(atr)
        if len(hist) > 20:
            hist.pop(0)
        if len(hist) < 5:
            return "BUILDING"
        avg_atr = sum(hist[:-1]) / max(len(hist) - 1, 1)
        if avg_atr <= 0:
            return "DORMANT"
        ratio = atr / avg_atr
        if ratio < 0.5:
            state = "DORMANT"
        elif ratio < 0.8:
            state = "BUILDING"
        elif ratio < 1.3:
            state = "ACTIVE"
        elif ratio < 2.0:
            state = "EXPLOSIVE"
        else:
            state = "COOLING"
        self._volatility_states[symbol] = state
        return state

    def get_calendar_status(self) -> dict:
        """Get full market calendar status for all monitored symbols."""
        status = self.calendar.get_full_status()
        status["symbols"] = {sym: self.calendar.get_symbol_status(sym) for sym in self._symbols}
        return status

    def get_market_analysis(self, symbol: str, timeframe: str = "M15") -> Dict[str, Any]:
        """
        Generate comprehensive multi-indicator & SMC market analysis for symbol.
        """
        candles = self.get_candles(symbol, timeframe, 150)
        if len(candles) < 20:
            tick = self.get_live_tick(symbol)
            spread_pts = int(tick.get("spread", 0))
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "price": self.get_latest_price(symbol),
                "rsi": 50.0,
                "atr": 0.0010,
                "adx": {"adx": 20.0, "plus_di": 0.0, "minus_di": 0.0},
                "trend": "NEUTRAL",
                "smc": {"fvgs": [], "order_blocks": [], "sweeps": []},
                "session_score": self.calendar.get_session_score(symbol),
                "is_optimal_session": self.calendar.is_optimal_session(symbol),
                "volatility_state": "BUILDING",
                "spread_points": spread_pts,
                "is_market_open": self.calendar.is_market_open(symbol),
                "swap_buy_tonight": self.calendar.get_swap_cost(symbol, "buy", 1.0),
                "swap_sell_tonight": self.calendar.get_swap_cost(symbol, "sell", 1.0),
                "is_wednesday_swap": self.calendar.get_swap_day_multiplier() == 3,
            }

        closes = [float(c["close"]) for c in candles]
        price = closes[-1]
        atr = calculate_atr(candles, 14)
        rsi = calculate_rsi(closes, 14)
        ema_20 = calculate_ema_latest(closes, 20)
        ema_50 = calculate_ema_latest(closes, 50)
        ema_200 = calculate_ema_latest(closes, min(len(closes), 200))
        bb = calculate_bollinger_bands(closes, 20, 2.0)
        macd = calculate_macd(closes, 12, 26, 9)
        stoch = calculate_stochastic(candles, 14, 3)
        adx_data = calculate_adx(candles, 14)
        vol_metrics = calculate_volume_metrics(candles, 20)

        # SMC Analysis — pass live ATR so detect_fvgs uses adaptive gap sizing
        # CRITICAL: Without atr, detect_fvgs falls back to static 0.01% filter (wrong for crypto/indices)
        smc_lookback = candles[-80:] if len(candles) >= 80 else candles
        fvgs = detect_fvgs(smc_lookback, atr=atr)
        obs = detect_order_blocks(smc_lookback)
        sweeps = detect_liquidity_sweeps(smc_lookback)

        # Determine overall technical bias
        bull_points = 0
        bear_points = 0

        if price > ema_50:
            bull_points += 1
        else:
            bear_points += 1

        if ema_20 > ema_50:
            bull_points += 1
        else:
            bear_points += 1

        if rsi > 52:
            bull_points += 1
        elif rsi < 48:
            bear_points += 1

        if macd["hist"] > 0:
            bull_points += 1
        else:
            bear_points += 1

        if bull_points >= 3:
            trend = "BULLISH"
        elif bear_points >= 3:
            trend = "BEARISH"
        else:
            trend = "RANGING"

        tick = self.get_live_tick(symbol)
        spread_pts = int(tick.get("spread", 0))
        session_score = self.calendar.get_session_score(symbol)
        vol_state = self._update_volatility_state(symbol, atr)

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "price": price,
            "atr": atr,
            "rsi": rsi,
            "ema_20": ema_20,
            "ema_50": ema_50,
            "ema_200": ema_200,
            "bollinger": bb,
            "macd": macd,
            "stochastic": stoch,
            "adx": adx_data,
            "volume_ratio": vol_metrics["volume_ratio"],
            "volume_regime": classify_volume_regime(vol_metrics["volume_ratio"], adx_data.get("adx", 20.0)),
            "trend": trend,
            "smc": {
                "fvgs": fvgs[-5:] if fvgs else [],
                "order_blocks": obs[-5:] if obs else [],
                "sweeps": sweeps[-3:] if sweeps else [],
            },
            "session_score": session_score,
            "is_optimal_session": self.calendar.is_optimal_session(symbol),
            "volatility_state": vol_state,
            "spread_points": spread_pts,
            "is_market_open": self.calendar.is_market_open(symbol),
            "swap_buy_tonight": self.calendar.get_swap_cost(symbol, "buy", 1.0),
            "swap_sell_tonight": self.calendar.get_swap_cost(symbol, "sell", 1.0),
            "is_wednesday_swap": self.calendar.get_swap_day_multiplier() == 3,
        }

    def get_volume_regime(self, symbol: str, timeframe: str = "M15") -> Dict[str, Any]:
        """Classify and return current volume regime for symbol and timeframe."""
        candles = self.get_candles(symbol, timeframe, 30)
        if len(candles) < 15:
            return classify_volume_regime(1.0, 20.0)
        vol_metrics = calculate_volume_metrics(candles, 20)
        adx_data = calculate_adx(candles, 14)
        return classify_volume_regime(vol_metrics["volume_ratio"], adx_data.get("adx", 20.0))

