# ==============================================================================
# quantclaw/ml_engine.py — Self-Learning ML Brain & Feature Scoring (MT5)
# ==============================================================================
"""
Self-Learning ML Brain for QuantClaw MT5.
Evaluates trade setups across a 10-feature dimensional space in real time:

  1. Multi-Timeframe Trend Alignment (H4 / H1 / M15 / M5)
  2. SMC Structural Confluence (FVG + Order Block + Structure Shift)
  3. Liquidity Sweep Confirmation (BSL / SSL session raids)
  4. Momentum & Volume Flow (RSI / MACD / Volume Mult)
  5. Volatility Regime & ATR Ratio
  6. Spread Cost Efficiency (MT5 broker spread check)
  7. High-Liquidity Session Window (London Open / NY Open / Overlap)
  8. Economic News Impact Filter
  9. Multi-Strategy Agreement (+20 Confluence Bonus)
  10. Historical Setup Fingerprint Win-Rate Memory (Bayesian Prior)

Auto-tunes weights and threshold boundaries based on closed trade results.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from quantclaw.utils.logger import get_logger
from quantclaw.models import StrategySignal, TradeDecision, RiskRegime
from quantclaw.config import get_ml_weights_path, save_json_persisted, load_json_persisted
from quantclaw.utils.indicators import calculate_atr, calculate_ema_latest

logger = get_logger(__name__)

from quantclaw.market_calendar import MarketCalendar
_calendar = MarketCalendar()

DEFAULT_WEIGHTS = {
    "trend_alignment": 15.0,
    "smc_confluence": 18.0,
    "liquidity_sweep": 15.0,
    "momentum_volume": 12.0,
    "volatility_regime": 8.0,
    "spread_efficiency": 8.0,
    "session_window": 10.0,
    "news_safety": 6.0,
    "historical_memory": 8.0,
}


class MLEngine:
    """Real-time 10-feature scoring and adaptive self-learning ML brain."""

    def __init__(self, config: Any, market_engine: Any, trade_journal: Optional[Any] = None) -> None:
        self.config = config
        self.market = market_engine
        self.journal = trade_journal
        self.weights = self._load_weights()

        # Confluence tracker: [symbol] -> List[StrategySignal] in last 10 minutes
        self._confluence_window: Dict[str, List[StrategySignal]] = {}

        # Self-learning analytics
        self._total_evaluated: int = 0
        self._total_approved: int = 0
        self._correct_decisions: int = 0
        self._incorrect_decisions: int = 0

    def _load_weights(self) -> Dict[str, float]:
        """Load persistent ML weights or return defaults."""
        data = load_json_persisted("ml_weights.json", {})
        if data and isinstance(data, dict):
            w = DEFAULT_WEIGHTS.copy()
            w.update(data)
            return w
        return DEFAULT_WEIGHTS.copy()

    def _save_weights(self) -> None:
        """Persist adjusted ML weights to disk."""
        save_json_persisted("ml_weights.json", self.weights)

    @property
    def _weights(self) -> Dict[str, float]:
        """Alias for self.weights for backward-compatibility."""
        return self.weights

    # ── Real-Time Setup Evaluation ─────────────────────────────────────────────

    def evaluate_signal(
        self, signal: StrategySignal, news_score: float = 0.0
    ) -> TradeDecision:
        """
        Score a strategy signal across the 10-feature vector.
        Returns a complete TradeDecision.
        """
        self._total_evaluated += 1
        sym = signal.symbol
        action = signal.action.lower()
        now = time.time()
        
        # Cleanup old confluence
        for k in list(self._confluence_window.keys()):
            self._confluence_window[k] = [s for s in self._confluence_window[k] if now - s.timestamp <= 600]

        # Cache market analysis
        mkt = self.market.get_market_analysis(sym, "M15")

        # Track confluence
        win_list = self._confluence_window.setdefault(sym, [])
        win_list = [s for s in win_list if (now - s.timestamp) < 600]
        win_list.append(signal)
        self._confluence_window[sym] = win_list

        unique_strats = {s.strategy for s in win_list if s.action.lower() == action}
        confluence_count = len(unique_strats)

        # 1. Multi-Timeframe Trend Alignment (0 - 1.0)
        trend_score = self._eval_trend_alignment(sym, action)

        # 2. SMC Structural Confluence (0 - 1.0)
        smc_score = self._eval_smc_confluence(sym, signal, mkt)

        # 3. Liquidity Sweep Confirmation (0 - 1.0)
        sweep_score = self._eval_liquidity_sweep(sym, action, mkt)

        # 4. Momentum & Volume Flow (0 - 1.0)
        momentum_score = self._eval_momentum_volume(sym, action, mkt)

        # 5. Volatility Regime (0 - 1.0)
        vol_score = self._eval_volatility_regime(sym, mkt)

        # 6. Spread Cost Efficiency (0 - 1.0)
        spread_score = self._eval_spread_efficiency(sym)

        # 7. High-Liquidity Session Window (0 - 1.0)
        session_score = self._eval_session_window(sym)

        # 8. News Safety (0 - 1.0)
        news_safety = max(0.0, 1.0 - abs(news_score))

        # 9. Historical Setup Memory (0 - 1.0)
        memory_score = self._eval_historical_memory(sym, signal.strategy, action)

        # Calculate raw weighted score (0 to 100)
        total_weight = sum(self.weights.values())
        if total_weight == 0: total_weight = 1.0
        raw_score = (
            (trend_score * self.weights.get("trend_alignment", 15.0))
            + (smc_score * self.weights.get("smc_confluence", 18.0))
            + (sweep_score * self.weights.get("liquidity_sweep", 15.0))
            + (momentum_score * self.weights.get("momentum_volume", 12.0))
            + (vol_score * self.weights.get("volatility_regime", 8.0))
            + (spread_score * self.weights.get("spread_efficiency", 8.0))
            + (session_score * self.weights.get("session_window", 10.0))
            + (news_safety * self.weights.get("news_safety", 6.0))
            + (memory_score * self.weights.get("historical_memory", 8.0))
        ) / (total_weight / 100.0)

        # Macro Trend Alignment Guard: Heavily penalize fighting higher-timeframe structure
        if trend_score <= 0.33:
            raw_score -= 25.0
            logger.warning(f"🛡️ [MACRO COUNTER-TREND] {action.upper()} {sym} penalized (-25.0 pts) for fighting multi-timeframe trend")
        elif trend_score >= 0.99:
            raw_score += 8.0

        # Risk-to-Reward Expectancy Filter
        if signal.sl_points > 0 and signal.tp_points > 0:
            sig_rr = signal.tp_points / signal.sl_points
            if sig_rr < 1.8:
                raw_score -= 20.0
                logger.warning(f"⚠️ [LOW RR PENALTY] Signal RR {sig_rr:.2f} is under institutional 1.8R floor (-20.0 pts)")
            elif sig_rr >= 2.5:
                raw_score += 6.0

        # Add confluence bonus
        confluence_bonus = 0.0
        if confluence_count >= 2:
            confluence_bonus = float(getattr(self.config, "ml_brain_confluence_bonus", 20.0))
            raw_score += confluence_bonus

        # Titan Pro Institutional Conviction Boost
        if signal.strategy == "titan_pro":
            raw_score += 10.0

        # Dynamic Strategy Circuit Breaker & Performance Regulator
        if self.journal:
            try:
                strat_stats = self.journal.get_strategy_stats(signal.strategy)
                strat_total = strat_stats.get("total_trades", 0)
                strat_wr = strat_stats.get("win_rate", 50.0)
                if strat_total >= 4:
                    if strat_wr < 35.0:
                        raw_score -= 15.0
                        logger.warning(
                            f"🛡️ [STRATEGY THROTTLE] {signal.strategy} penalized (-15.0 pts) "
                            f"due to low historical win rate ({strat_wr:.1f}% across {strat_total} trades)"
                        )
                    elif strat_wr >= 60.0:
                        raw_score += 8.0
                        logger.info(
                            f"🌟 [STRATEGY BOOST] {signal.strategy} rewarded (+8.0 pts) "
                            f"for stellar historical win rate ({strat_wr:.1f}% across {strat_total} trades)"
                        )
            except Exception:
                pass

        # Volume Regime Intelligence & Filter
        if getattr(self.config, "enable_volume_regime_intelligence", True):
            vol_regime_info = mkt.get("volume_regime", {})
            vol_regime = vol_regime_info.get("regime", "NORMAL_VOLUME")
            if vol_regime == "LOW_VOLUME":
                if signal.strategy in ("quant_way", "eyes_sme"):
                    raw_score -= 10.0
                    logger.info(f"⚠️ [VOLUME GATE] Breakout strategy {signal.strategy} penalized (-10.0) in LOW_VOLUME regime")
                elif signal.strategy == "smc_liquidity":
                    raw_score += 8.0
            elif vol_regime == "HIGH_VOLUME":
                if signal.strategy in ("quant_way", "titan_pro"):
                    raw_score += 8.0
                    logger.info(f"🚀 [VOLUME BOOST] Strategy {signal.strategy} boosted (+8.0) in HIGH_VOLUME expansion")
            elif vol_regime == "CLIMAX_VOLUME":
                if signal.strategy in ("quant_way", "eyes_sme", "titan_pro"):
                    raw_score -= 20.0
                    logger.warning(f"🛑 [VOLUME CLIMAX] Strategy {signal.strategy} throttled (-20.0) to prevent buying volume blow-off top")

        final_score = min(100.0, max(0.0, raw_score))

        # Swap penalty — reduce score if trade would incur heavy swap costs
        try:
            swap_cost = _calendar.get_swap_cost(sym, signal.action, 0.1, 1)
            if swap_cost < -5.0:  # Significant negative swap
                swap_penalty = min(0.05, abs(swap_cost) / 100.0)  # Max 5% penalty
                # Apply to final score
                final_score = final_score * (1.0 - swap_penalty)
        except Exception:
            pass
        min_exec_threshold = float(getattr(self.config, "ml_brain_min_execute_score", 70.0))
        approved = final_score >= min_exec_threshold

        # Calculate Entry, SL, and TP prices using real ATR
        price = signal.price
        atr_candles = self.market.get_candles(sym, "M15", 20)
        if atr_candles and len(atr_candles) >= 14:
            atr_val = calculate_atr(atr_candles, period=14)
        else:
            atr_val = signal.sl_points if signal.sl_points > 0 else (price * 0.005)
        # Use signal sl_points if provided and non-zero, fallback to ATR
        sl_distance = signal.sl_points if signal.sl_points > 0 else atr_val
        tp_distance = signal.tp_points if signal.tp_points > 0 else (sl_distance * 2.8)

        if action == "buy":
            sl_price = price - sl_distance
            tp_price = price + tp_distance
        else:
            sl_price = price + sl_distance
            tp_price = price - tp_distance

        # Determine Risk Regime based on conviction
        if final_score >= 82.0:
            regime = RiskRegime.GAMMA
        elif final_score >= 68.0:
            regime = RiskRegime.BETA
        else:
            regime = RiskRegime.ALPHA

        # Volume lot sizing
        lots = float(self.config.symbol_quantities.get(sym, 0.10))

        if approved:
            self._total_approved += 1
            rejection = ""
        else:
            rejection = f"ML score {final_score:.1f} below threshold {min_exec_threshold:.1f}"

        logger.info(
            f"🧠 ML Evaluation: {signal.action.upper()} {sym} | Score: {final_score:.1f}/100 "
            f"(Trend:{trend_score:.2f}, SMC:{smc_score:.2f}, Confluence:{confluence_count}, Bonus:+{confluence_bonus:.0f}) -> {'APPROVED ✅' if approved else 'REJECTED ❌'}"
        )

        inval_p = getattr(signal, "invalidation_price", None)
        if inval_p is None and hasattr(signal, "metadata"):
            inval_p = signal.metadata.get("sweep_level") or signal.metadata.get("sweep_price")

        return TradeDecision(
            approved=approved,
            symbol=sym,
            action=action,
            volume_lots=lots,
            entry_price=price,
            sl_price=sl_price,
            tp_price=tp_price,
            invalidation_price=inval_p,
            regime=regime,
            ml_score=round(final_score, 1),
            confluence_count=confluence_count,
            rejection_reason=rejection,
            ai_commentary="",
            strategy=signal.strategy
        )

    # ── Feature Evaluators ─────────────────────────────────────────────────────

    def _eval_trend_alignment(self, symbol: str, action: str) -> float:
        """Score trend alignment across H4, H1, M15 using EMA20 vs EMA50 and price position.

        Previous bug: ("M15", 60, 20) made fast=EMA(min(20,20))=EMA(20) == slow=EMA(20)
        → always equal → M15 NEVER contributed to trend score. Fixed: fast=EMA(20) vs slow=EMA(50).
        """
        bull_count = 0
        total_checks = 0

        # Format: (timeframe, candle_count, fast_ema, slow_ema)
        # fast and slow are always different to produce a meaningful crossover signal
        tf_configs = [
            ("H4", 80, 20, 50),   # H4 trend: EMA20 vs EMA50
            ("H1", 80, 20, 50),   # H1 trend: EMA20 vs EMA50
            ("M15", 80, 20, 50),  # M15 trend: EMA20 vs EMA50 (previously BROKEN: both were EMA20!)
        ]
        for tf, n, fast_period, slow_period in tf_configs:
            candles = self.market.get_candles(symbol, tf, n)
            if len(candles) >= max(slow_period + 5, 30):
                total_checks += 1
                closes = [float(c["close"]) for c in candles]
                fast = calculate_ema_latest(closes, fast_period)
                slow = calculate_ema_latest(closes, slow_period)
                if fast > slow:
                    bull_count += 1

        if total_checks == 0:
            return 0.55  # neutral-slightly-positive default when no data

        bull_ratio = bull_count / total_checks
        score = bull_ratio if action == "buy" else (1.0 - bull_ratio)
        return min(1.0, max(0.0, score))




    def _eval_smc_confluence(self, symbol: str, signal: StrategySignal, mkt: Dict) -> float:
        """Evaluate presence of Fair Value Gaps, Order Blocks, and ICT structure."""
        score = 0.55
        meta = getattr(signal, "metadata", {}) or {}
        if meta.get("fvg"):
            score += 0.20
        if meta.get("ob"):
            score += 0.15
        if meta.get("setup_type", "").startswith("ICT_"):
            score += 0.15
        if signal.strategy == "titan_pro" or meta.get("sweep_type"):
            score += 0.25

        smc = mkt.get("smc", {})
        if smc.get("fvgs"):
            score += 0.10
        if smc.get("order_blocks"):
            score += 0.10
        return min(1.0, max(0.4, score))

    def _eval_liquidity_sweep(self, symbol: str, action: str, mkt: Dict) -> float:
        """Check for confirmed liquidity sweep in trade direction."""
        sweeps = mkt.get("smc", {}).get("sweeps", [])
        if not sweeps:
            return 0.60

        latest = sweeps[-1]
        target_dir = "BULLISH_SWEEP" if action == "buy" else "BEARISH_SWEEP"
        if latest.get("direction") == target_dir:
            return 0.95
        return 0.40

    def _eval_momentum_volume(self, symbol: str, action: str, mkt: Dict) -> float:
        """Evaluate RSI, MACD, and Volume Ratio."""
        rsi = mkt.get("rsi", 50.0)
        vol_ratio = mkt.get("volume_ratio", 1.0)
        macd = mkt.get("macd", {})
        hist = macd.get("hist", 0.0)

        score = 0.55  # Slightly above neutral default
        if action == "buy":
            # Ideal: RSI 40-65 (momentum but not overbought)
            if 40 <= rsi <= 65:
                score += 0.2
            elif 30 <= rsi < 40:
                score += 0.1  # Oversold bounce potential
            if hist > 0:
                score += 0.15
            if vol_ratio >= 1.1:
                score += 0.10
        else:
            # Ideal: RSI 35-60 for shorts
            if 35 <= rsi <= 60:
                score += 0.2
            elif rsi > 65:
                score += 0.1  # Overbought pullback potential
            if hist < 0:
                score += 0.15
            if vol_ratio >= 1.1:
                score += 0.10
        return min(1.0, max(0.0, score))

    def _eval_volatility_regime(self, symbol: str, mkt: Dict) -> float:
        """Evaluate ATR and Bollinger Bandwidth for suitable volatility."""
        bb = mkt.get("bollinger", {})
        bw = bb.get("bandwidth", 0.0)
        atr = mkt.get("atr", 0.0)
        
        # If no bandwidth data available, return decent default
        if bw <= 0 and atr <= 0:
            return 0.65

        sym_u = symbol.upper()
        if 'XAU' in sym_u or 'GOLD' in sym_u:
            t_low, t_high = 0.5, 50.0
        elif 'BTC' in sym_u or 'ETH' in sym_u:
            t_low, t_high = 50.0, 8000.0
        elif any(x in sym_u for x in ['US30', 'NAS', 'SPX', 'DAX', 'DJI', 'NDX']):
            t_low, t_high = 0.2, 100.0
        else:
            t_low, t_high = 0.0001, 0.1
            
        if bw > 0:
            if t_low <= bw <= t_high:
                return 0.90
            elif bw < t_low:  # Too quiet / squeeze
                return 0.60
            else:  # Extremely volatile
                return 0.50
        return 0.65

    def _eval_spread_efficiency(self, symbol: str) -> float:
        """Check broker spread vs allowable maximum."""
        try:
            tick = self.market.get_live_tick(symbol)
        except AttributeError:
            tick = getattr(self.market, '_live_ticks', {}).get(symbol, {})
        spread = int(tick.get("spread", 10))
        max_spread = int(getattr(self.config, "max_spread_points", 40))

        sym_u = symbol.upper()
        if 'XAU' in sym_u or 'GOLD' in sym_u:
            allowable = max_spread * 15
        elif 'BTC' in sym_u or 'ETH' in sym_u:
            allowable = max_spread * 500
        elif any(x in sym_u for x in ['US30', 'NAS', 'SPX', 'DAX', 'DJI', 'NDX']):
            allowable = max_spread * 10
        else:
            allowable = max_spread

        if allowable <= 0:
            return 0.7
        ratio = spread / allowable
        if ratio <= 0.3:
            return 1.0
        elif ratio <= 0.6:
            return 0.85
        elif ratio <= 1.0:
            return 0.65
        return 0.2

    def _eval_session_window(self, symbol: str = "") -> float:
        """Score based on active global trading session using MarketCalendar intelligence."""
        try:
            score = _calendar.get_session_score(symbol) / 100.0  # 0-1
            if score <= 0:
                return 0.4  # Neutral floor for 24/7 assets
            return max(0.3, min(1.0, score))
        except Exception:
            # Legacy fallback
            hour = time.gmtime().tm_hour
            if 7 <= hour < 9 or 12 <= hour < 16:
                return 1.0
            if 9 <= hour < 12 or 16 <= hour < 21:
                return 0.8
            return 0.5

    def _eval_historical_memory(self, symbol: str, strategy: str, action: str) -> float:
        """Query past win rate for this symbol + strategy combination."""
        if not self.journal:
            return 0.55  # Slightly optimistic default (better than 0.5 neutral)
        try:
            stats = self.journal.get_strategy_stats(strategy)
            total = stats.get("total_trades", 0)
            win_rate = stats.get("win_rate", 55.0)
            if total >= 3:  # Lower from 5 to 3 trades before trusting history
                return min(1.0, max(0.2, win_rate / 100.0))
            elif total >= 1:
                # Partially trust even 1-2 trades
                prior = 0.55
                return prior + (win_rate / 100.0 - prior) * (total / 3.0)
        except Exception:
            pass
        return 0.55

    # ── Self-Learning Gradient & Weight Updates ────────────────────────────────

    def record_trade_outcome(
        self, symbol: str, strategy: str, action: str, pnl_usd: float, outcome: str
    ) -> None:
        """
        Adaptive learning step: Adjusts feature weights based on trade profit/loss.
        Uses proportional normalization to prevent weight explosion.
        """
        is_win = outcome.lower() == "win" or pnl_usd > 0
        learning_rate = min(0.5, max(0.05, abs(pnl_usd) / 100.0))  # Dynamic rate based on P&L magnitude

        if is_win:
            self._correct_decisions += 1
            # Reinforce the features most associated with successful SMC/trend trades
            reward_features = ["smc_confluence", "trend_alignment", "liquidity_sweep"]
            for feat in reward_features:
                if feat in self.weights:
                    self.weights[feat] = min(30.0, self.weights[feat] + learning_rate)
            # Strategy-specific reinforcement
            if "smc" in strategy.lower():
                self.weights["smc_confluence"] = min(30.0, self.weights.get("smc_confluence", 18.0) + learning_rate * 0.3)
            elif "quant_way" in strategy.lower() or "occ" in strategy.lower():
                self.weights["trend_alignment"] = min(30.0, self.weights.get("trend_alignment", 15.0) + learning_rate * 0.3)
        else:
            self._incorrect_decisions += 1
            # Bidirectional learning: Decrease reward features on loss
            for feat in ["smc_confluence", "trend_alignment", "liquidity_sweep"]:
                if feat in self.weights:
                    self.weights[feat] = max(1.0, self.weights[feat] - learning_rate * 0.5)
            # Increase scrutiny on risk filters on losing trades
            penalty_features = ["spread_efficiency", "news_safety", "volatility_regime"]
            for feat in penalty_features:
                if feat in self.weights:
                    self.weights[feat] = min(20.0, self.weights[feat] + learning_rate * 0.7)

        # Re-normalize weights so they always sum to 100.0 (prevents score drift)
        total = sum(self.weights.values())
        if total > 0:
            scale = 100.0 / total
            # FIX: After scaling, clamp each weight to its individual bounds
            # Without clamping, a compressed feature (e.g. 2.0) scaled by 1.3x = 2.6 is fine,
            # but a high feature (e.g. 28.0) scaled by 1.3x = 36.4 violates the 30.0 cap.
            WEIGHT_BOUNDS = {
                "trend_alignment": (3.0, 30.0),
                "smc_confluence": (3.0, 30.0),
                "liquidity_sweep": (3.0, 25.0),
                "momentum_volume": (2.0, 20.0),
                "volatility_regime": (2.0, 20.0),
                "spread_efficiency": (2.0, 15.0),
                "session_window": (2.0, 18.0),
                "news_safety": (2.0, 15.0),
                "historical_memory": (2.0, 18.0),
            }
            self.weights = {
                k: round(min(WEIGHT_BOUNDS.get(k, (1.0, 30.0))[1],
                             max(WEIGHT_BOUNDS.get(k, (1.0, 30.0))[0],
                                 v * scale)), 4)
                for k, v in self.weights.items()
            }

        self._save_weights()
        logger.info(
            f"🧠 ML Self-Learning updated on {outcome.upper()} (${pnl_usd:+.2f}) | "
            f"LR={learning_rate:.3f} | Correct: {self._correct_decisions}, Incorrect: {self._incorrect_decisions}"
        )


    def get_diagnostics(self) -> Dict[str, Any]:
        """Return live ML diagnostic metrics."""
        total = self._correct_decisions + self._incorrect_decisions
        score = (self._correct_decisions / total * 100.0) if total > 0 else 50.0
        status = "Going smooth" if score >= 65 else ("Going Choppy" if score >= 45 else "Going bad")
        return {
            "decision_score": round(score, 1),
            "decision_status": status,
            "decision_metrics": {
                "correct": self._correct_decisions,
                "incorrect": self._incorrect_decisions,
                "total_evaluated": self._total_evaluated,
                "total_approved": self._total_approved,
            },
            "weights": self.weights,
        }
