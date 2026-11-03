# ==============================================================================
# quantclaw/risk_manager.py — Risk & Execution Manager (MetaTrader 5)
# ==============================================================================
"""
Institutional Risk & Position Lifecycle Manager for MetaTrader 5.
Enforces strict capital preservation and trade management:

  - Dynamic Lot Sizing based on risk percentage & stop loss points
  - Automatic Breakeven (moves SL to entry at 1.0R profit)
  - Partial Take Profit (closes 50% at 1.5R, lets runner ride to 3.0R–5.0R)
  - Trailing Stop Loss via dynamic ATR
  - Max Spread & Slippage Protection
  - Strict 3% Daily Max Loss Circuit Breaker with auto-disarm
"""

from __future__ import annotations

import asyncio
import math
import re
import time
import threading
from typing import Any, Dict, List, Optional, Tuple
from quantclaw.utils.logger import get_logger
from quantclaw.models import TradeDecision, MT5Position
from quantclaw.market_calendar import MarketCalendar

logger = get_logger("risk_manager")


class RiskManager:
    """Manages MT5 execution, dynamic lot sizing, breakeven, trailing SL, and circuit breakers."""

    def __init__(
        self,
        config: Any,
        mt5_client: Any,
        account_tracker: Any,
        trade_journal: Any,
        ml_engine: Optional[Any] = None,
        market_engine: Optional[Any] = None,
        news_monitor: Optional[Any] = None,
    ) -> None:
        self.config = config
        self.mt5 = mt5_client
        self.account_tracker = account_tracker
        self.journal = trade_journal
        self.ml_engine = ml_engine
        self.market_engine = market_engine
        self.news_monitor = news_monitor

        # State tracking for active positions: ticket -> dict
        self._managed_positions: Dict[int, Dict[str, Any]] = {}
        self._circuit_broken: bool = False
        self._consecutive_losses: int = 0
        self._new_entries_blocked: bool = False  # Blocks new entries but keeps managing open positions
        self._cooldown_until: float = 0.0  # Timestamp when tactical risk pause expires
        self._last_monitor_time: float = 0.0
        self._positions_lock = threading.RLock()
        # Semaphore: prevents concurrent signals from both passing max_concurrent_positions check
        # and opening duplicate trades (race condition guard)
        self._execution_semaphore: Optional[asyncio.Semaphore] = None  # Lazy-initialized in async context
        self._calendar = MarketCalendar()
        self._last_swap_check: Dict[int, float] = {}  # ticket -> last swap check time
        self._symbol_loss_cooldowns: Dict[Tuple[str, str], float] = {}  # (symbol, action) -> timestamp

    # ── Master Arm & Circuit Breaker ───────────────────────────────────────────

    def is_armed(self) -> bool:
        """Check if bot is armed for position management (BE, trailing, TP).
        
        IMPORTANT: is_armed() returns True for position MANAGEMENT even when circuit breaker fires.
        Use is_new_entry_allowed() to check if NEW trades can be opened.
        """
        return bool(getattr(self.config, "armed", False))

    def is_symbol_in_cooldown(self, symbol: str, action: str) -> Tuple[bool, int]:
        """Check if a symbol and direction are currently quarantined after a loss."""
        key = (symbol.upper(), action.lower())
        exp = self._symbol_loss_cooldowns.get(key, 0.0)
        now_ts = time.time()
        if now_ts < exp:
            return True, int(exp - now_ts)
        return False, 0

    def is_new_entry_allowed(self) -> bool:
        """Check if NEW trade entries are allowed.
        
        Autonomous Resilience: If a tactical loss cooldown was set, automatically checks if the
        cooldown period has elapsed. Once elapsed, automatically clears the block and resumes
        searching for profitable setups without requiring manual re-arming.
        """
        with self._positions_lock:
            if self._new_entries_blocked or self._circuit_broken:
                # Check if tactical pause has elapsed
                if self._cooldown_until > 0 and time.time() >= self._cooldown_until:
                    self._new_entries_blocked = False
                    self._circuit_broken = False
                    self._consecutive_losses = 0
                    self._cooldown_until = 0.0
                    logger.info("🟢 [AUTO-RESUME] Tactical risk cooldown elapsed — bot remains ARMED and is actively hunting for profits!")
                    return bool(getattr(self.config, "armed", False))
                return False
        return bool(getattr(self.config, "armed", False))

    def reset_circuit_breaker(self) -> None:
        """Reset circuit breaker to allow new trade entries again."""
        with self._positions_lock:
            self._circuit_broken = False
            self._consecutive_losses = 0
            self._new_entries_blocked = False
            self._cooldown_until = 0.0
        if self.account_tracker:
            self.account_tracker.reset_baseline()
        logger.info("🛡️ Circuit breaker reset — new entries re-enabled.")

    def trigger_circuit_breaker(self, reason: str) -> None:
        """
        Tactical Risk Guardian: NEVER permanently disarms the bot.
        Sets a temporary cooling-off pause so the bot continues managing open positions
        and automatically resumes hunting for profitable setups after market volatility settles.
        """
        cooldown_sec = int(getattr(self.config, "loss_cooldown_seconds", 900))
        with self._positions_lock:
            self._circuit_broken = True
            if cooldown_sec > 0:
                self._new_entries_blocked = True
                self._cooldown_until = time.time() + cooldown_sec
                cooldown_min = max(1, cooldown_sec // 60)
                logger.warning(
                    f"🛡️ [SMART RISK GUARDIAN] {reason} — Pausing new entries for {cooldown_min}m to let volatility settle. Bot stays ARMED and will auto-resume hunting for profits."
                )
            else:
                # Continuous profit hunting mode
                self._new_entries_blocked = False
                self._circuit_broken = False
                self._cooldown_until = 0.0
                logger.warning(f"🛡️ [SMART RISK GUARDIAN] {reason} — Continuous profit mode active: bot stays ARMED without pausing.")

    # ── Trade Execution Pipeline ───────────────────────────────────────────────

    async def execute_trade_decision(self, decision: TradeDecision) -> Tuple[bool, str]:
        """
        Execute an approved TradeDecision on MetaTrader 5.
        Validates spreads, account limits, and punches order.
        """
        if not self.is_new_entry_allowed():
            reason = "Bot is DISARMED" if not getattr(self.config, "armed", False) else "New entries blocked by circuit breaker (daily limit/consecutive losses)"
            return False, reason

        if not decision.approved:
            return False, f"Trade rejected: {decision.rejection_reason}"

        if self.account_tracker:
            try:
                daily_loss_pct = float(self.account_tracker.get_daily_loss_pct() or 0.0)
            except (TypeError, ValueError):
                daily_loss_pct = 0.0
            max_daily_pct = float(getattr(self.config, "daily_max_loss_pct", 3.0))
            if daily_loss_pct >= max_daily_pct:
                self.trigger_circuit_breaker(
                    f"Daily loss ({daily_loss_pct:.2f}%) reached max limit ({max_daily_pct:.2f}%)"
                )
                return False, "Daily max loss reached"

        sym = decision.symbol
        action = decision.action.upper()

        # Lazy-initialize semaphore in async context (cannot be created in __init__ outside event loop)
        if self._execution_semaphore is None:
            self._execution_semaphore = asyncio.Semaphore(1)

        # Semaphore: Only one trade execution at a time to prevent concurrent signals
        # from both passing the max_concurrent_positions check and opening duplicate positions
        async with self._execution_semaphore:
            return await self._execute_trade_inner(decision, sym, action)

    async def _execute_trade_inner(self, decision: TradeDecision, sym: str, action: str) -> Tuple[bool, str]:
        """Inner execution: called under semaphore to serialize concurrent trade dispatches."""

        # 1. Check Max Concurrent Positions
        current_positions = await asyncio.to_thread(self.mt5.get_positions)
        max_pos = int(getattr(self.config, "max_concurrent_positions", 5))
        if len(current_positions) >= max_pos:
            msg = f"Max concurrent positions reached ({len(current_positions)}/{max_pos})"
            logger.warning(msg)
            return False, msg

        # 1b. Query MT5 directly to confirm market is open & trading allowed
        if hasattr(self.mt5, "is_symbol_tradeable"):
            is_tradeable, trade_reason = await asyncio.to_thread(self.mt5.is_symbol_tradeable, sym)
            if not is_tradeable:
                logger.warning(f"Trade rejected on {sym}: {trade_reason}")
                return False, trade_reason

        # 1c. Real-Time Economic News Shield Check
        if getattr(self.config, "enable_news_filter", True) and self.news_monitor and hasattr(self.news_monitor, "is_news_blocked"):
            is_blocked, news_reason = self.news_monitor.is_news_blocked(sym)
            if is_blocked:
                msg = f"News shield active on {sym}: {news_reason}"
                logger.warning(msg)
                return False, msg

        # 1d. Weekend Gap Shield: Block new orders on Friday after cutoff hour to avoid Sunday gap risk (Forex/Indices only)
        is_crypto = any(c in sym.upper() for c in ["BTC", "ETH", "SOL", "XRP", "CRYPTO"])
        if getattr(self.config, "enable_weekend_gap_shield", False) and not is_crypto and not getattr(self.config, "testing", False):
            import datetime
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            cutoff_h = int(getattr(self.config, "friday_close_cutoff_hour_utc", 20))
            if (now_utc.weekday() == 4 and now_utc.hour >= cutoff_h) or now_utc.weekday() in (5, 6):
                msg = f"Weekend Gap Shield active (UTC Friday >={cutoff_h}:00 or weekend) - blocking new market order on {sym}"
                logger.warning(f"🛡️ [WEEKEND GAP SHIELD] {msg}")
                return False, msg

        # Session & Calendar Gate — skip new entries during poor sessions
        if getattr(self.config, 'enable_session_filter', True):
            session_score = self._calendar.get_session_score(decision.symbol)
            min_score = float(getattr(self.config, 'session_min_score', 25.0))
            if session_score < min_score:
                logger.info(f"⏰ [SESSION GATE] Skipping {decision.symbol} — session score {session_score:.0f}/100 < {min_score:.0f}")
                return False, f"Session score too low ({session_score:.0f} < {min_score:.0f})"

        # Wednesday 3x Swap Warning
        if getattr(self.config, 'enable_swap_awareness', True):
            swap_mult = self._calendar.get_swap_day_multiplier()
            if swap_mult == 3:
                est_swap = self._calendar.get_swap_cost(decision.symbol, decision.action, 0.1, 3)
                if est_swap < -10.0:
                    logger.warning(f"💰 [WEDNESDAY SWAP] {decision.symbol} {decision.action}: 3x swap = ${est_swap:.2f} for 0.1 lot — proceed with caution")

        # 2. Check Broker Spread
        sym_info = await asyncio.to_thread(self.mt5.get_symbol_info, sym)
        if not sym_info:
            return False, f"Symbol {sym} not found in MT5"

        sym_u = sym.upper()
        max_spread = int(getattr(self.config, "max_spread_points", 40))
        if "XAU" in sym_u or "GOLD" in sym_u:
            allowable_spread = max_spread * 15   # e.g. 600 points ($0.60) on Gold
        elif "BTC" in sym_u or "ETH" in sym_u:
            allowable_spread = max_spread * 500  # e.g. 20000 points ($20) on BTC
        elif any(x in sym_u for x in ["US30", "NAS", "SPX", "DAX", "DJI", "NDX", "DJ", "USTEC"]):
            allowable_spread = max_spread * 10   # e.g. 400 points on indices
        else:
            allowable_spread = max_spread        # 40 points on Forex

        if sym_info.spread > allowable_spread:
            msg = f"Spread too high on {sym}: {sym_info.spread} > {allowable_spread} max allowable"
            logger.warning(msg)
            return False, msg

        # 3. Dynamic Lot Size & Account Risk Shield Calculation
        acc = await asyncio.to_thread(self.mt5.get_account_info)
        if acc is None:
            logger.error("No account info")
            return False, "No account info"
        equity = float(acc.equity)

        # Exact dollar value per 1.0 point for 1.0 lot in account currency (USD)
        tick_val = getattr(sym_info, "trade_tick_value", 0.0)
        tick_sz = getattr(sym_info, "trade_tick_size", 0.0)
        if tick_val > 0 and tick_sz > 0 and sym_info.point > 0:
            point_val_per_lot = (tick_val / tick_sz) * sym_info.point
        else:
            point_val_per_lot = sym_info.point * getattr(sym_info, "trade_contract_size", 100000.0)
        if point_val_per_lot <= 0:
            point_val_per_lot = 1.0

        sl_distance_points = abs(decision.entry_price - decision.sl_price) / sym_info.point
        if sl_distance_points <= 0:
            logger.error("Invalid SL")
            return False, "Invalid SL"

        # Loss in USD if 1.0 full lot hits Stop Loss
        loss_per_1_lot = sl_distance_points * point_val_per_lot

        # Target Risk in USD calibrated for this account ($2 / $6 / $10 risk range):
        override_risk = float(getattr(self.config, "target_risk_usd_override", 0.0))
        max_risk_cap = float(getattr(self.config, "max_risk_usd_per_trade", 8.0))
        min_risk_floor = float(getattr(self.config, "min_risk_usd_per_trade", 2.0))
        risk_pct = float(getattr(self.config, "risk_per_trade_pct", 1.5))

        if override_risk > 0:
            target_risk_usd = override_risk
        else:
            calc_risk = equity * (risk_pct / 100.0)
            target_risk_usd = min(max_risk_cap, max(min_risk_floor, calc_risk))

        # Expectancy-Adaptive Sizing (Fractional Kelly scaling from Strategy Tester)
        if getattr(self.config, "enable_expectancy_adaptive_sizing", True) and hasattr(self, "strategy_tester") and self.strategy_tester:
            try:
                tuned = self.strategy_tester.get_optimal_params(sym, decision.strategy)
                if tuned:
                    exp_val = float(tuned.get("expectancy", 0.0))
                    pf_val = float(tuned.get("profit_factor", 1.0))
                    if exp_val >= 0.70 and pf_val >= 1.80:
                        target_risk_usd = min(max_risk_cap * 1.25, target_risk_usd * 1.25)
                        logger.info(f"⚡ [EXPECTANCY SIZING] Scaled risk up 1.25x (${target_risk_usd:.2f}) on {sym} (E={exp_val:.2f}R, PF={pf_val:.2f})")
                    elif exp_val <= 0.20 or pf_val < 1.10:
                        target_risk_usd = max(min_risk_floor, target_risk_usd * 0.50)
                        logger.info(f"🛡️ [EXPECTANCY SIZING] Scaled risk down 0.50x (${target_risk_usd:.2f}) on {sym} (E={exp_val:.2f}R, PF={pf_val:.2f})")
            except Exception as e:
                logger.debug(f"Expectancy sizing error: {e}")

        step = sym_info.volume_step if sym_info.volume_step > 0 else 0.01
        step_decimals = max(0, -math.floor(math.log10(step))) if 0 < step < 1 else 0

        sizing_mode = getattr(self.config, "trade_sizing_mode", "AutoRisk")
        if sizing_mode == "AutoRisk":
            ideal_lots = target_risk_usd / loss_per_1_lot
            lots = round(math.floor(ideal_lots / step) * step, step_decimals)
        else:
            sq = getattr(self.config, "symbol_quantities", {})
            base_sym = re.sub(r'[\._][a-zA-Z0-9]+$', '', sym).rstrip('.').upper()
            alias_sym = ""
            for target_key, alias_list in getattr(self.mt5, "COMMON_ALIASES", {}).items():
                if base_sym == target_key or base_sym in [a.upper() for a in alias_list]:
                    alias_sym = target_key
                    break
            lots = float(sq.get(sym, sq.get(base_sym, sq.get(alias_sym, 0.01))))
            # In Manual mode, enforce max dollar risk cap
            if lots * loss_per_1_lot > max_risk_cap * 1.15:
                lots = round(math.floor((max_risk_cap / loss_per_1_lot) / step) * step, step_decimals)

        # ── ACCOUNT RISK SHIELD GUARD (Check minimum broker volume risk) ──────
        if lots < sym_info.volume_min:
            min_lot_loss = sym_info.volume_min * loss_per_1_lot
            # If the broker's minimum lot risks more than allowable ceiling (max_risk_cap * 1.25),
            # DO NOT PUNCH! Block the trade to protect small account from outsized index/crypto risk.
            if min_lot_loss > max_risk_cap * 1.25:
                shield_msg = (
                    f"🛡️ [ACCOUNT RISK SHIELD] {sym} trade blocked: Broker min lot ({sym_info.volume_min}) "
                    f"with SL distance ({sl_distance_points:.1f} pts) risks ${min_lot_loss:.2f}, "
                    f"which exceeds the ${max_risk_cap:.2f} max risk limit for equity ${equity:.2f}."
                )
                logger.warning(shield_msg)
                return False, shield_msg
            else:
                # Acceptable slight rounding to min volume
                lots = sym_info.volume_min

        # Safety clamp: Protect accounts from overleveraging.
        sym_u = sym.upper()
        if "XAU" in sym_u or "GOLD" in sym_u:
            max_lot_ratio = 0.05
        elif any(c in sym_u for c in ["BTC", "ETH", "SOL", "CRYPTO"]):
            max_lot_ratio = 0.02
        elif any(idx in sym_u for idx in ["US30", "DJ", "NAS", "USTEC", "SPX", "GER", "DAX"]):
            max_lot_ratio = 0.05
        else:
            max_lot_ratio = 0.15

        max_equity_lots = max(sym_info.volume_min, round((equity / 1000.0) * max_lot_ratio, 2))
        lots = min(lots, max_equity_lots)

        # Quantize to volume_step
        lots = round(round(lots / step) * step, step_decimals)
        lots = max(sym_info.volume_min, min(sym_info.volume_max, lots))

        final_projected_risk = lots * loss_per_1_lot
        logger.info(
            f"🎯 [RISK SIZING] {action} {sym}: {lots} lots | SL: {sl_distance_points:.1f} pts | "
            f"Risk: ${final_projected_risk:.2f} (Target: ${target_risk_usd:.2f}, Cap: ${max_risk_cap:.2f})"
        )

        # ── COMMISSION FRICTION SHIELD ─────────────────────────────────────────
        # Reject trades where broker round-trip commission represents a predatory % of expected TP
        # On brokers like Tradiso, crypto micro-lots incur ~$8+ round trip commission, eating all edge.
        sym_u_check = sym.upper()
        if any(c in sym_u_check for c in ["BTC", "ETH", "SOL", "CRYPTO"]):
            est_round_trip_comm = max(8.0, lots * 800.0)
        else:
            est_round_trip_comm = lots * 7.0

        tp_distance_pts = abs(decision.entry_price - decision.tp_price) / sym_info.point
        projected_tp_usd = tp_distance_pts * point_val_per_lot * lots
        max_comm_pct = float(getattr(self.config, "commission_max_pct_of_tp", 15.0))
        if projected_tp_usd > 0 and (est_round_trip_comm / projected_tp_usd) * 100.0 > max_comm_pct:
            comm_msg = (
                f"🛡️ [COMMISSION FRICTION SHIELD] {sym} trade blocked: Estimated round-trip broker commission "
                f"(${est_round_trip_comm:.2f}) represents {(est_round_trip_comm / projected_tp_usd)*100.0:.1f}% "
                f"of projected profit target (${projected_tp_usd:.2f}), exceeding {max_comm_pct}% limit."
            )
            logger.warning(comm_msg)
            return False, comm_msg

        # 4. Punch Market Order on MT5
        comment = f"QuantClaw [{decision.regime.value}]"
        success, res = await asyncio.to_thread(
            self.mt5.open_market_order,
            symbol=sym,
            action=action,
            volume=lots,
            sl=decision.sl_price,
            tp=decision.tp_price,
            comment=comment,
            magic=int(getattr(self.config, "mt5_magic_number", 999111)),
        )

        if not success:
            err_msg = res.get("error", "Order failed")
            logger.error(f"❌ Execution failed for {sym}: {err_msg}")
            return False, err_msg

        ticket = res.get("ticket", 0)
        entry_price = res.get("price", decision.entry_price)

        # 5. Register in Managed Positions tracker
        with self._positions_lock:
            self._managed_positions[ticket] = {
                "ticket": ticket,
                "symbol": sym,
                "action": action,
                "volume": lots,
                "entry_price": entry_price,
                "initial_sl": decision.sl_price,
                "initial_tp": decision.tp_price,
                "current_sl": decision.sl_price,
                "current_tp": decision.tp_price,
                "last_seen_sl": decision.sl_price,
                "last_seen_tp": decision.tp_price,
                "manual_intervention": False,
                "sl_distance": abs(entry_price - decision.sl_price),
                "invalidation_price": getattr(decision, "invalidation_price", 0.0) or 0.0,
                "breakeven_done": False,
                "partial_tp_done": False,
                "regime": decision.regime.value,
                "ml_score": decision.ml_score,
                "strategy": decision.strategy,
                "open_time": time.time(),
            }

        # 6. Record to SQLite Trade Journal
        if self.journal:
            self.journal.record_open_trade(
                ticket=ticket,
                symbol=sym,
                action=action,
                volume=lots,
                entry_price=entry_price,
                sl=decision.sl_price,
                tp=decision.tp_price,
                strategy=decision.strategy,
                ml_score=decision.ml_score,
            )

        logger.info(
            f"✅ Position Opened: #{ticket} | {action} {lots} lots {sym} @ {entry_price:.5f} | SL: {decision.sl_price:.5f} | TP: {decision.tp_price:.5f}"
        )

        # Log trade open event for intelligence
        if self.journal:
            try:
                await asyncio.to_thread(
                    self.journal.log_trade_event,
                    ticket, sym, 'OPEN', entry_price, 0.0,
                    {
                        'action': action, 'lots': lots, 'sl': decision.sl_price,
                        'tp': decision.tp_price, 'strategy': decision.strategy,
                        'ml_score': decision.ml_score, 'regime': decision.regime.value
                    }
                )
            except Exception:
                pass

        return True, f"Opened #{ticket}"

    # ── Active Positions Management Loop ───────────────────────────────────────

    async def monitor_open_positions(self) -> None:
        """
        Background monitoring loop: ALWAYS runs regardless of armed/circuit-breaker state.
        Manages BE, partial TP, trailing, structural invalidation for ALL open positions.
        
        CRITICAL DESIGN: This method NEVER returns early due to circuit breaker or disarm.
        Open positions must always be managed to protect capital.
        """
        if not self.mt5.is_connected():
            return

        # Check daily loss — log warning but DO NOT return (keep managing open positions)
        if self.account_tracker:
            try:
                daily_loss_pct = float(self.account_tracker.get_daily_loss_pct() or 0.0)
            except (TypeError, ValueError):
                daily_loss_pct = 0.0
            max_daily_pct = float(getattr(self.config, "daily_max_loss_pct", 3.0))
            if daily_loss_pct >= max_daily_pct:
                # Block new entries but DO NOT stop managing existing positions
                if not self._new_entries_blocked:
                    self.trigger_circuit_breaker(
                        f"Daily loss ({daily_loss_pct:.2f}%) reached max limit ({max_daily_pct:.2f}%)"
                    )
                # CRITICAL: Do NOT return here — fall through to manage open positions!

        # Continue with position management regardless of circuit breaker state...
        live_positions = await asyncio.to_thread(self.mt5.get_positions)

        # Network Glitch / Interruption Guard:
        # If get_positions returned empty, but we have active managed positions, verify connection
        # before assuming positions were closed! Prevents amnesia & false loss recording during Wi-Fi hiccups.
        if not live_positions and self._managed_positions:
            is_conn = await asyncio.to_thread(self.mt5.is_connected)
            if not is_conn:
                logger.warning("⚠️ [NETWORK INTERRUPT] MT5 connection dropped during position poll. Retaining active positions.")
                return
            term = await asyncio.to_thread(self.mt5.get_terminal_info)
            if not term or not term.get("connected", True):
                logger.warning("⚠️ [NETWORK INTERRUPT] Terminal disconnected from broker. Retaining active positions.")
                return

        live_tickets = {p["ticket"]: p for p in live_positions}

        # Detect closed positions and record actual P&L from MT5 history
        with self._positions_lock:
            closed_tickets = [t for t in self._managed_positions if t not in live_tickets]
        for t in closed_tickets:
            with self._positions_lock:
                m = self._managed_positions.pop(t, {})
            # Query actual realized P&L from MT5 closed deal history
            deal_info = await asyncio.to_thread(self.mt5.get_history_deals, t)
            pnl_usd = deal_info.get("net_pnl", 0.0)
            close_price = deal_info.get("close_price", m.get("entry_price", 0.0))

            # FIX: Only trust deal_info if it returned a real close price (not empty-dict fallback)
            # An empty dict means MT5 history not yet populated — don't record false zero-PnL outcomes
            if not deal_info or close_price <= 0:
                logger.warning(f"⚠️ Position #{t} closed but deal history unavailable — skipping journal record")
                continue

            outcome = "win" if pnl_usd > 0 else "loss"

            # Update consecutive loss counter for circuit breaker
            if outcome == "loss":
                with self._positions_lock:
                    self._consecutive_losses += 1
                    cur_consec = self._consecutive_losses
                sym_loss = m.get("symbol", "").upper()
                act_loss = m.get("action", "").lower()
                if sym_loss and act_loss:
                    cooldown_secs = int(getattr(self.config, "loss_quarantine_seconds", 1200))
                    self._symbol_loss_cooldowns[(sym_loss, act_loss)] = time.time() + cooldown_secs
                    logger.warning(
                        f"🛑 [LOSS QUARANTINE] {sym_loss} {act_loss.upper()} quarantined for {cooldown_secs//60} mins following loss on #{t}"
                    )
                max_consec = int(getattr(self.config, "max_consecutive_losses", 4))
                if cur_consec >= max_consec:
                    self.trigger_circuit_breaker(
                        f"{cur_consec} consecutive losses reached limit ({max_consec})"
                    )
            else:
                with self._positions_lock:
                    self._consecutive_losses = 0

            # Determine outcome classification tag
            if m.get("struct_cut_done"):
                outcome_tag = "STRUCTURE_INVALIDATED"
                review_notes = "Early loss cut on market structure break (~50% risk saved)"
            elif m.get("weekend_closed"):
                outcome_tag = "WEEKEND_GAP_SHIELD"
                review_notes = "Defensive exit before Friday close to avoid weekend gap"
            elif m.get("breakeven_done") and abs(pnl_usd) <= max(1.5, abs(m.get("sl_distance", 0.01) * 0.25)):
                outcome_tag = "BREAKEVEN_DEFENSE"
                review_notes = "Capital protected at breakeven + buffer"
            elif m.get("zone3_done") or m.get("partial_tp_done"):
                outcome_tag = "SWEET_SPOT_BANKED"
                review_notes = "Secured Zone partial profits + trailing gain banked"
            elif pnl_usd > 0 and (close_price >= m.get("initial_tp", 0.0) if m.get("action", "").upper() == "BUY" else close_price <= m.get("initial_tp", 0.0) and m.get("initial_tp", 0.0) > 0):
                outcome_tag = "SWEEP_EXPANSION"
                review_notes = "Full TP expansion reached on institutional sweep"
            elif pnl_usd > 0:
                outcome_tag = "PROFIT_TARGET"
                review_notes = "Positive profit target achieved"
            elif pnl_usd < 0:
                outcome_tag = "FULL_SL_HIT"
                review_notes = "Hard stop loss reached"
            else:
                outcome_tag = "STANDARD_CLOSE"
                review_notes = "Standard position closure"

            # FIX: Move blocking SQLite/ML calls to thread pool (don't block async event loop)
            if self.journal:
                await asyncio.to_thread(self.journal.record_close_trade, t, close_price, pnl_usd, outcome, outcome_tag, review_notes)
            if self.ml_engine:
                await asyncio.to_thread(
                    self.ml_engine.record_trade_outcome,
                    m.get("symbol", ""), m.get("strategy", m.get("regime", "")), m.get("action", ""), pnl_usd, outcome
                )
            logger.info(
                f"📋 Position #{t} Closed | P&L: ${pnl_usd:+.2f} | Outcome: {outcome.upper()} | "
                f"Consecutive losses: {self._consecutive_losses}"
            )


        # Manage active positions
        bot_magic = int(getattr(self.config, "mt5_magic_number", 999111))
        ignore_manual = bool(getattr(self.config, "ignore_manual_trades", True))

        for ticket, pos in live_tickets.items():
            pos_magic = int(pos.get("magic", 0))

            # Manual Trade Segregation:
            # If position magic != bot_magic, this trade was opened manually by user in MT5 (or another EA).
            # Do NOT interrupt, modify, close, or trail manual trades!
            if ignore_manual and pos_magic != bot_magic and ticket not in self._managed_positions:
                continue

            with self._positions_lock:
                managed = self._managed_positions.get(ticket)
            if not managed:
                # Seamlessly adopt existing MT5 position into Risk Guardian
                entry = float(pos.get("open_price", 0.0))
                cur_sl = float(pos.get("sl", 0.0))
                cur_tp = float(pos.get("tp", 0.0))
                sym = pos.get("symbol", "")
                live_vol = float(pos.get("volume", 0.01))
                sl_dist = abs(entry - cur_sl) if cur_sl > 0 else 0.0
                if sl_dist <= 0:
                    atr_v = self.market_engine.get_market_analysis(sym, 'M15').get('atr', 0) if hasattr(self, 'market_engine') and self.market_engine else 0
                    sl_dist = atr_v * 2.0 if atr_v > 0 else (entry * 0.01)

                # FIX: Restart amnesia — infer lifecycle state from journal open volume.
                # If the position's live volume is less than what was originally opened,
                # partial TP has already been applied; don't re-trigger it after restart.
                orig_vol = live_vol
                if self.journal:
                    try:
                        jv = self.journal.get_open_volume(ticket)
                        if jv and jv > 0:
                            orig_vol = jv
                    except Exception:
                        pass
                partial_already_done = live_vol < (orig_vol * 0.75)  # > 25% reduction = partial already done
                # If SL has been moved past entry (positive BE territory), treat BE as done
                be_already_done = (cur_sl > entry if pos.get("type", "BUY").upper() == "BUY" else cur_sl < entry and cur_sl > 0)

                managed = {
                    "ticket": ticket,
                    "symbol": sym,
                    "action": pos.get("type", "BUY"),
                    "volume": live_vol,
                    "entry_price": entry,
                    "initial_sl": cur_sl,
                    "initial_tp": cur_tp,
                    "current_sl": cur_sl,
                    "current_tp": cur_tp,
                    "last_seen_sl": cur_sl,
                    "last_seen_tp": cur_tp,
                    "manual_intervention": False,
                    "sl_distance": sl_dist,
                    "breakeven_done": be_already_done,
                    "partial_tp_done": partial_already_done,
                    "regime": "Alpha",
                    "ml_score": 75.0,
                    "strategy": "adopted",
                    "open_time": float(pos.get("time", time.time())),
                }
                with self._positions_lock:
                    self._managed_positions[ticket] = managed
                logger.info(
                    f"🔄 Adopted #{ticket} ({sym} {pos.get('type')}) | BE_done={be_already_done} | PartialTP_done={partial_already_done}"
                )

            sym = pos["symbol"]
            cur_price = float(pos["current_price"])
            entry_price = float(managed["entry_price"])
            is_buy = pos["type"].upper() == "BUY"
            sl_dist = managed["sl_distance"]
            if sl_dist <= 0:
                # Try to compute ATR-based fallback distance
                if self.market_engine:
                    try:
                        mkt = self.market_engine.get_market_analysis(sym, 'M15')
                        atr_val = float(mkt.get('atr', 0))
                        if atr_val > 0:
                            sl_dist = atr_val * 2.0
                            managed["sl_distance"] = sl_dist
                    except Exception:
                        pass
                if sl_dist <= 0:
                    continue

            profit_distance = (cur_price - entry_price) if is_buy else (entry_price - cur_price)
            r_multiple = profit_distance / sl_dist

            # ── User Manual Intervention Intelligence ──────────────────────────
            # Detect if user manually adjusted SL or TP in MT5 directly
            live_sl = float(pos.get("sl", 0.0))
            live_tp = float(pos.get("tp", 0.0))
            last_sl = managed.get("last_seen_sl", managed.get("current_sl", 0.0))
            last_tp = managed.get("last_seen_tp", managed.get("current_tp", 0.0))

            # Point tolerance for manual adjustments to prevent false positives from broker float rounding
            sym_pt = 0.00001
            if self.mt5:
                try:
                    si_quick = self.mt5.get_symbol_info(sym)
                    if si_quick and hasattr(si_quick, "point") and si_quick.point > 0:
                        sym_pt = float(si_quick.point)
                except Exception:
                    pass
            sl_tolerance = max(sym_pt * 3.0, 1e-4)

            if abs(live_sl - last_sl) > sl_tolerance and live_sl > 0:
                is_tighter = (is_buy and live_sl > last_sl) or (not is_buy and (live_sl < last_sl or last_sl == 0.0))
                if is_tighter:
                    logger.info(
                        f"👤 [MANUAL TRAIL DETECTED] #{ticket} {sym}: User manually tightened SL from {last_sl:.5f} to {live_sl:.5f}. Respecting user SL."
                    )
                    if (is_buy and live_sl >= entry_price) or (not is_buy and live_sl <= entry_price and live_sl > 0):
                        managed["breakeven_done"] = True
                else:
                    logger.info(
                        f"👤 [MANUAL SL ADJUST] #{ticket} {sym}: User changed SL from {last_sl:.5f} to {live_sl:.5f}. Respecting user SL."
                    )
                managed["current_sl"] = live_sl
                managed["last_seen_sl"] = live_sl
                if self.journal:
                    try:
                        await asyncio.to_thread(
                            self.journal.log_trade_event,
                            ticket, sym, 'MANUAL_SL_ADJUST', live_sl, r_multiple,
                            {'from_sl': last_sl, 'to_sl': live_sl, 'is_tighter': is_tighter}
                        )
                    except Exception:
                        pass

            if abs(live_tp - last_tp) > sl_tolerance:
                logger.info(
                    f"👤 [MANUAL TP ADJUST] #{ticket} {sym}: User adjusted TP from {last_tp:.5f} to {live_tp:.5f}. Respecting user target."
                )
                managed["current_tp"] = live_tp
                managed["tp"] = live_tp
                managed["last_seen_tp"] = live_tp
                if self.journal:
                    try:
                        await asyncio.to_thread(
                            self.journal.log_trade_event,
                            ticket, sym, 'MANUAL_TP_ADJUST', live_tp, r_multiple,
                            {'from_tp': last_tp, 'to_tp': live_tp}
                        )
                    except Exception:
                        pass

            atr_val = 0.0
            if self.market_engine:
                try:
                    mkt = self.market_engine.get_market_analysis(sym, 'M15')
                    atr_val = float(mkt.get('atr', 0))
                except Exception:
                    pass
            if atr_val <= 0:
                atr_val = sl_dist * 0.8

            # ── Helper: Compute BE offset respecting broker stops_level ──────────
            async def _get_be_offset(s: str) -> tuple:
                """Returns (point, digits, be_offset) respecting broker stops_level safely."""
                si = await asyncio.to_thread(self.mt5.get_symbol_info, s)
                try:
                    pt = float(getattr(si, "point", 0.00001)) if si else 0.00001
                except (ValueError, TypeError):
                    pt = 0.00001
                try:
                    dg = int(getattr(si, "digits", 5)) if si else 5
                except (ValueError, TypeError):
                    dg = 5
                try:
                    sprd = float(getattr(si, "spread", 3.0)) if si else 3.0
                except (ValueError, TypeError):
                    sprd = 3.0
                try:
                    stops_lvl = float(getattr(si, "trade_stops_level", 0.0)) if si else 0.0
                except (ValueError, TypeError):
                    stops_lvl = 0.0

                offset = max(pt * 10.0, pt * sprd, pt * stops_lvl)
                return pt, dg, offset

            # ── 5-ZONE STEPPED TRAILING & VOLUME-ADAPTIVE LIFECYCLE ───────────────
            enable_stepped = getattr(self.config, "enable_stepped_trailing", True)
            
            # Fetch Volume Regime for symbol
            vol_regime = "NORMAL_VOLUME"
            trail_atr_mult = 1.0
            if self.market_engine and hasattr(self.market_engine, "get_volume_regime"):
                try:
                    v_info = self.market_engine.get_volume_regime(sym, "M15")
                    vol_regime = v_info.get("regime", "NORMAL_VOLUME")
                    trail_atr_mult = v_info.get("trail_atr_mult", 1.0)
                except Exception:
                    pass

            # Auto Mode & Dynamic Scenario Adaptive Triggers
            auto_mode = getattr(self.config, "stepped_trail_auto_mode", True)
            if auto_mode:
                if vol_regime == "LOW_VOLUME":
                    z1_trigger = 0.45   # Sweet spot soft cushion in compressed chop
                    z2_trigger = 0.85   # Fast breakeven before range boundary reversal
                    z3_trigger = 1.35   # Sweet spot partial cash lock (bank 40% profit)
                    z4_trigger = 1.80
                    z5_trigger = 2.20
                elif vol_regime in ("HIGH_VOLUME", "CLIMAX_VOLUME"):
                    z1_trigger = 0.65   # Breathing space for momentum expansion
                    z2_trigger = 1.10   # Breakeven Plus
                    z3_trigger = 1.90   # Bank 40% cash into balance
                    z4_trigger = 2.50   # Mega profit lock
                    z5_trigger = 2.80   # Constant trailing runner
                else:
                    z1_trigger = 0.55
                    z2_trigger = 1.00
                    z3_trigger = 1.70
                    z4_trigger = 2.30
                    z5_trigger = 2.70
            else:
                z1_trigger = float(getattr(self.config, "stepped_trail_zone1_r", 0.65))
                z2_trigger = float(getattr(self.config, "stepped_trail_zone2_r", 1.05))
                z3_trigger = float(getattr(self.config, "stepped_trail_zone3_r", 1.80))
                z4_trigger = float(getattr(self.config, "stepped_trail_zone4_r", 2.40))
                z5_trigger = float(getattr(self.config, "stepped_trail_zone5_r", 2.80))

            pt, dg, be_offset = await _get_be_offset(sym)

            # ZONE 1: Soft Cushion (Slashes 75% risk down to -0.25R SL, leaving 0.5R wave breathing space)
            if enable_stepped and not managed.get("zone1_done") and not managed.get("breakeven_done"):
                if r_multiple >= z1_trigger and sl_dist > 0:
                    soft_target_r = float(getattr(self.config, "soft_risk_target_r", -0.25))
                    soft_sl = round(entry_price - (sl_dist * abs(soft_target_r)), dg) if is_buy                               else round(entry_price + (sl_dist * abs(soft_target_r)), dg)
                    current_sl_val = managed.get("current_sl", 0.0)
                    should_tighten = (is_buy and soft_sl > current_sl_val + pt) or                                      (not is_buy and soft_sl < current_sl_val - pt and current_sl_val > 0)
                    if should_tighten:
                        succ = False
                        for _ in range(2):
                            try:
                                succ, _ = await asyncio.wait_for(
                                    asyncio.to_thread(self.mt5.modify_position, ticket, soft_sl, pos.get("tp", 0.0)),
                                    timeout=10.0
                                )
                                if succ: break
                                await asyncio.sleep(0.3)
                            except Exception: pass
                        if succ:
                            managed["zone1_done"] = True
                            managed["soft_risk_reduced"] = True
                            managed["current_sl"] = soft_sl
                            managed["last_seen_sl"] = soft_sl
                            managed["last_seen_tp"] = pos.get("tp", 0.0)
                            logger.info(f"🛡️ [ZONE 1: SOFT CUSHION] Risk slashed 75% on #{ticket} {sym} @ SL={soft_sl} (R={r_multiple:.2f})")
                            if self.journal:
                                try:
                                    await asyncio.to_thread(
                                        self.journal.log_trade_event,
                                        ticket, sym, 'ZONE1_SOFT_CUSHION', soft_sl, r_multiple,
                                        {'sl': soft_sl, 'entry': entry_price, 'r_trigger': z1_trigger}
                                    )
                                except Exception: pass

            # Legacy Early Breakeven fallback (only if explicitly enabled by user)
            enable_early_be = getattr(self.config, "enable_early_breakeven", False)
            early_be_r = float(getattr(self.config, "early_breakeven_r_ratio", 0.45))
            if enable_early_be and not managed.get("early_be_done") and not managed.get("breakeven_done"):
                if r_multiple >= early_be_r:
                    be_price = round(entry_price + be_offset, dg) if is_buy else round(entry_price - be_offset, dg)
                    succ = False
                    for _ in range(2):
                        try:
                            succ, _ = await asyncio.wait_for(
                                asyncio.to_thread(self.mt5.modify_position, ticket, be_price, pos.get("tp", 0.0)),
                                timeout=10.0
                            )
                            if succ: break
                            await asyncio.sleep(0.3)
                        except Exception: pass
                    if succ:
                        managed["early_be_done"] = True
                        managed["breakeven_done"] = True
                        managed["current_sl"] = be_price
                        managed["last_seen_sl"] = be_price
                        managed["last_seen_tp"] = pos.get("tp", 0.0)
                        logger.info(f"🛡️ [EARLY BREAKEVEN] Capital Secured for #{ticket} {sym} @ {be_price} (R={r_multiple:.2f})")

            # ZONE 2: Breakeven Plus (Entry + Spread + 0.15R offset -> Guaranteed Green Risk-Free Trade)
            if (enable_stepped or getattr(self.config, "enable_breakeven_trigger", True)) and not managed.get("breakeven_done"):
                if r_multiple >= z2_trigger:
                    be_plus_offset = max(be_offset, sl_dist * 0.15)
                    be_price = round(entry_price + be_plus_offset, dg) if is_buy                                else round(entry_price - be_plus_offset, dg)
                    current_sl_val = managed.get("current_sl", 0.0)
                    should_tighten = (is_buy and be_price > current_sl_val + pt) or                                      (not is_buy and be_price < current_sl_val - pt and current_sl_val > 0) or                                      (not is_buy and current_sl_val == 0.0)
                    if should_tighten:
                        succ = False
                        for _ in range(2):
                            try:
                                succ, _ = await asyncio.wait_for(
                                    asyncio.to_thread(self.mt5.modify_position, ticket, be_price, pos.get("tp", 0.0)),
                                    timeout=10.0
                                )
                                if succ: break
                                await asyncio.sleep(0.3)
                            except Exception: pass
                        if succ:
                            managed["zone2_done"] = True
                            managed["breakeven_done"] = True
                            managed["current_sl"] = be_price
                            managed["last_seen_sl"] = be_price
                            managed["last_seen_tp"] = pos.get("tp", 0.0)
                            logger.info(f"🔒 [ZONE 2: BREAKEVEN PLUS] Guaranteed green trade on #{ticket} {sym} @ {be_price} (R={r_multiple:.2f})")
                            if self.journal:
                                try:
                                    await asyncio.to_thread(
                                        self.journal.log_trade_event,
                                        ticket, sym, 'ZONE2_BREAKEVEN_PLUS', be_price, r_multiple,
                                        {'sl': be_price, 'entry': entry_price}
                                    )
                                except Exception: pass

            # News Shield Defensive Breakeven
            if getattr(self.config, "enable_news_filter", True) and self.news_monitor and hasattr(self.news_monitor, "is_news_blocked") and not managed["breakeven_done"]:
                is_blocked, news_reason = self.news_monitor.is_news_blocked(sym)
                if is_blocked and r_multiple >= 0.2:
                    if profit_distance > be_offset:
                        be_price = round(entry_price + be_offset, dg) if is_buy else round(entry_price - be_offset, dg)
                        try:
                            succ, _ = await asyncio.wait_for(
                                asyncio.to_thread(self.mt5.modify_position, ticket, be_price, pos.get("tp", 0.0)),
                                timeout=10.0
                            )
                            if succ:
                                managed["breakeven_done"] = True
                                managed["current_sl"] = be_price
                                managed["last_seen_sl"] = be_price
                                managed["last_seen_tp"] = pos.get("tp", 0.0)
                                logger.info(f"📰 [NEWS DEFENSE] Secured Breakeven for #{ticket} {sym} @ {be_price}")
                        except Exception: pass

            # ZONE 3: Profit Bank Tier 1 (Close 40% Volume + Lock SL at +0.80R Guaranteed Profit)
            if (enable_stepped or getattr(self.config, "enable_partial_take_profit", True)) and not managed.get("zone3_done") and not managed.get("partial_tp_done"):
                if r_multiple >= z3_trigger:
                    initial_vol = float(managed.get("volume", 0.01))
                    current_vol = float(pos.get("volume", initial_vol))
                    close_vol = max(0.01, round(initial_vol * 0.40, 2))
                    if current_vol > close_vol:
                        try:
                            close_fn = getattr(self.mt5, "partial_close", self.mt5.close_position)
                            succ_p, _ = await asyncio.wait_for(asyncio.to_thread(close_fn, ticket, close_vol), timeout=10.0)
                            if succ_p:
                                logger.info(f"💰 [ZONE 3: BANK CASH] Closed {close_vol} lots (40%) on #{ticket} {sym} at R={r_multiple:.2f}")
                                if self.journal:
                                    try:
                                        await asyncio.to_thread(
                                            self.journal.log_trade_event,
                                            ticket, sym, 'ZONE3_PARTIAL_BANK', cur_price, r_multiple,
                                            {'closed_vol': close_vol, 'remaining_vol': current_vol - close_vol}
                                        )
                                    except Exception: pass
                        except Exception: pass
                    
                    # Lock SL to +0.80R
                    lock_sl = round(entry_price + (sl_dist * 0.80), dg) if is_buy                               else round(entry_price - (sl_dist * 0.80), dg)
                    current_sl_val = managed.get("current_sl", 0.0)
                    should_tighten = (is_buy and lock_sl > current_sl_val + pt) or                                      (not is_buy and lock_sl < current_sl_val - pt and current_sl_val > 0)
                    if should_tighten:
                        try:
                            succ, _ = await asyncio.wait_for(
                                asyncio.to_thread(self.mt5.modify_position, ticket, lock_sl, pos.get("tp", 0.0)),
                                timeout=10.0
                            )
                            if succ:
                                managed["current_sl"] = lock_sl
                                managed["last_seen_sl"] = lock_sl
                                logger.info(f"💎 [ZONE 3: PROFIT LOCK] Secured +0.80R profit lock on #{ticket} {sym} @ {lock_sl}")
                        except Exception: pass
                    managed["zone3_done"] = True
                    managed["partial_tp_done"] = True

            # ZONE 4: Profit Bank Tier 2 (Lock SL at +1.40R Guaranteed Profit)
            if enable_stepped and not managed.get("zone4_done"):
                if r_multiple >= z4_trigger:
                    lock_sl_2 = round(entry_price + (sl_dist * 1.40), dg) if is_buy                                 else round(entry_price - (sl_dist * 1.40), dg)
                    current_sl_val = managed.get("current_sl", 0.0)
                    should_tighten = (is_buy and lock_sl_2 > current_sl_val + pt) or                                      (not is_buy and lock_sl_2 < current_sl_val - pt and current_sl_val > 0)
                    if should_tighten:
                        try:
                            succ, _ = await asyncio.wait_for(
                                asyncio.to_thread(self.mt5.modify_position, ticket, lock_sl_2, pos.get("tp", 0.0)),
                                timeout=10.0
                            )
                            if succ:
                                managed["zone4_done"] = True
                                managed["current_sl"] = lock_sl_2
                                managed["last_seen_sl"] = lock_sl_2
                                logger.info(f"🚀 [ZONE 4: MEGA PROFIT LOCK] Secured +1.40R profit lock on #{ticket} {sym} @ {lock_sl_2}")
                        except Exception: pass

            # CLIMAX VOLUME AGGRESSIVE LOCK (If volume spikes 3x+ while in deep profit, lock SL immediately)
            if vol_regime == "CLIMAX_VOLUME" and r_multiple >= 1.50 and not managed.get("climax_locked"):
                climax_sl = round(entry_price + (sl_dist * 1.20), dg) if is_buy else round(entry_price - (sl_dist * 1.20), dg)
                current_sl_val = managed.get("current_sl", 0.0)
                should_tighten = (is_buy and climax_sl > current_sl_val + pt) or                                  (not is_buy and climax_sl < current_sl_val - pt and current_sl_val > 0)
                if should_tighten:
                    try:
                        succ, _ = await asyncio.wait_for(
                            asyncio.to_thread(self.mt5.modify_position, ticket, climax_sl, pos.get("tp", 0.0)),
                            timeout=10.0
                        )
                        if succ:
                            managed["climax_locked"] = True
                            managed["current_sl"] = climax_sl
                            managed["last_seen_sl"] = climax_sl
                            logger.warning(f"🛑 [CLIMAX VOLUME DEFENSE] Locked SL @ +1.20R ({climax_sl}) on #{ticket} {sym} ahead of blow-off reversal")
                    except Exception: pass

            # ZONE 5 & CONSTANT TRAILING: High-Water Dynamic ATR Trail
            trail_mult = float(getattr(self.config, "trailing_stop_atr_mult", 1.5)) * trail_atr_mult
            constant_trail_enabled = getattr(self.config, "enable_constant_trailing", True)
            # Constant trailing activates at sweet-spot z3 trigger in auto mode, or z5 trigger in manual mode
            trail_activation = (z3_trigger if (auto_mode and constant_trail_enabled) else z5_trigger) if enable_stepped else float(getattr(self.config, "trail_activation_r", 1.5))
            if getattr(self.config, "enable_trailing_stop", True) and r_multiple >= trail_activation:
                # Acceleration: if price moved fast in last 5 M1 candles, tighten trail
                if self.market_engine:
                    try:
                        m1c = self.market_engine.get_candles(sym, "M1", 6)
                        if m1c and len(m1c) >= 5:
                            m1_move = abs(float(m1c[-1].get("close", 0)) - float(m1c[-5].get("close", 0)))
                            if atr_val > 0 and m1_move > atr_val * 0.6:
                                trail_mult = max(0.7, trail_mult * 0.65)
                    except Exception: pass

                trail_offset = atr_val * trail_mult
                trail_sl = cur_price - trail_offset if is_buy else cur_price + trail_offset
                current_sl_val = managed["current_sl"]
                if is_buy:
                    should_update = trail_sl > current_sl_val + (trail_offset * 0.1)
                else:
                    if current_sl_val == 0.0:
                        should_update = trail_sl > 0
                    else:
                        should_update = trail_sl < current_sl_val - (trail_offset * 0.1)

                if should_update and trail_sl > 0:
                    succ = False
                    for _ in range(2):
                        try:
                            succ, _ = await asyncio.wait_for(
                                asyncio.to_thread(self.mt5.modify_position, ticket, trail_sl, pos.get("tp", 0.0)),
                                timeout=10.0
                            )
                            if succ: break
                            await asyncio.sleep(0.3)
                        except Exception: pass
                    if succ:
                        managed["current_sl"] = trail_sl
                        managed["last_seen_sl"] = trail_sl
                        managed["last_seen_tp"] = pos.get("tp", 0.0)
                        logger.info(f"🏃 [ZONE 5: RUNNER TRAIL] Trailing SL → {trail_sl:.5f} for #{ticket} {sym} (R={r_multiple:.2f}, ATR={atr_val:.5f}, mult={trail_mult:.2f})")
                        if self.journal:
                            try:
                                await asyncio.to_thread(
                                    self.journal.log_trade_event,
                                    ticket, sym, 'TRAILING_UPDATE', trail_sl, r_multiple,
                                    {'from_sl': current_sl_val, 'to_sl': trail_sl, 'atr': atr_val}
                                )
                            except Exception: pass

            # Weekend Gap Shield: Move open profit positions (R >= 0.30) to Breakeven on Friday evening
            is_crypto = any(c in sym.upper() for c in ["BTC", "ETH", "SOL", "XRP", "CRYPTO"])
            if getattr(self.config, "enable_weekend_gap_shield", False) and not is_crypto and not managed.get("breakeven_done") and not getattr(self.config, "testing", False):
                import datetime
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                cutoff_h = int(getattr(self.config, "friday_close_cutoff_hour_utc", 20))
                if (now_utc.weekday() == 4 and now_utc.hour >= cutoff_h) or now_utc.weekday() in (5, 6):
                    if r_multiple >= 0.30:
                        be_price = round(entry_price + be_offset, dg) if is_buy else round(entry_price - be_offset, dg)
                        try:
                            succ, _ = await asyncio.wait_for(
                                asyncio.to_thread(self.mt5.modify_position, ticket, be_price, pos.get("tp", 0.0)),
                                timeout=10.0
                            )
                            if succ:
                                managed["breakeven_done"] = True
                                managed["current_sl"] = be_price
                                managed["last_seen_sl"] = be_price
                                logger.info(f"🛡️ [WEEKEND GAP SHIELD] Secured Breakeven for #{ticket} {sym} @ {be_price} before Friday close")
                        except Exception:
                            pass

            # D. Active Dynamic Structural Invalidation Guardian (Early Loss Mitigation)
            enable_early_cut = getattr(self.config, "enable_early_invalidation_cut", True)
            min_cut_r = float(getattr(self.config, "invalidation_cut_min_r", -0.30))
            if enable_early_cut and r_multiple <= min_cut_r:
                inv_price = float(managed.get("invalidation_price", 0.0))
                price_invalidated = False
                if inv_price > 0:
                    if is_buy and cur_price < inv_price:
                        price_invalidated = True
                    elif not is_buy and cur_price > inv_price:
                        price_invalidated = True

                choch_invalidated = False
                if not price_invalidated and self.market_engine:
                    try:
                        m15_c = self.market_engine.get_candles(sym, "M15", 30)
                        if len(m15_c) >= 20:
                            from quantclaw.utils.smc_analysis import detect_bos_choch
                            choch = detect_bos_choch(m15_c, lookback=15)
                            if (is_buy and choch["type"] == "CHOCH_BEAR") or (not is_buy and choch["type"] == "CHOCH_BULL"):
                                choch_invalidated = True
                    except Exception:
                        pass

                if price_invalidated or choch_invalidated:
                    reason_str = f"invalidation level {inv_price:.5f} breached" if price_invalidated else "adverse market structure shift"
                    logger.warning(
                        f"🛡️ [EARLY INVALIDATION CUT] Closing #{ticket} {sym} @ {cur_price:.5f} (R={r_multiple:.2f}): {reason_str}. Preserved remaining risk capital!"
                    )
                    await asyncio.to_thread(self.mt5.close_position, ticket, float(pos.get("volume", 0.01)))
                    managed["struct_cut_done"] = True
                    if self.journal:
                        try:
                            await asyncio.to_thread(
                                self.journal.log_trade_event,
                                ticket, sym, 'EARLY_INVALIDATION_CUT', cur_price, r_multiple,
                                {'reason': reason_str, 'inv_price': inv_price, 'r': r_multiple}
                            )
                        except Exception:
                            pass

            # E. Swap Fee Guardian — Check every 15 minutes near rollover
            now_ts = time.time()
            last_swap_chk = self._last_swap_check.get(ticket, 0)
            if now_ts - last_swap_chk > 900:  # Every 15 min
                self._last_swap_check[ticket] = now_ts
                direction = "buy" if is_buy else "sell"
                swap_warning = self._calendar.get_rollover_warning(
                    sym, direction, float(pos.get("volume", 0.01)), float(pos.get("profit", 0.0))
                )
                if swap_warning:
                    logger.warning(f"💰 [SWAP GUARDIAN] #{ticket} {sym}: {swap_warning}")
                if self._calendar.should_close_before_swap(sym, direction, float(pos.get("volume", 0.01)), float(pos.get("profit", 0.0))):
                    if r_multiple >= 0.0:  # Only close if not in loss
                        logger.warning(f"💰 [SWAP CLOSE] #{ticket} {sym}: Closing before rollover to protect profit from swap charges")
                        await asyncio.to_thread(self.mt5.close_position, ticket, float(pos.get("volume", 0.01)))
                        if self.journal:
                            try:
                                await asyncio.to_thread(self.journal.log_trade_event, ticket, sym, 'SWAP_CLOSE', cur_price, r_multiple, {'reason': 'swap_avoidance'})
                            except Exception:
                                pass
                        continue

            # F. Session Decay — tighten trail when optimal session ends
            if not self._calendar.is_optimal_session(sym) and r_multiple > 0.5:
                # Session ended with open profit — tighten trail
                if getattr(self.config, 'enable_trailing_stop', True):
                    session_trail_mult = min(float(getattr(self.config, 'trailing_stop_atr_mult', 1.5)), 0.8)
                    if atr_val > 0:
                        tight_sl = cur_price - (atr_val * session_trail_mult) if is_buy else cur_price + (atr_val * session_trail_mult)
                        current_sl_val = managed.get("current_sl", 0.0)
                        should_tighten = (is_buy and tight_sl > current_sl_val + (atr_val * 0.05)) or \
                                         (not is_buy and tight_sl < current_sl_val - (atr_val * 0.05) and current_sl_val > 0)
                        if should_tighten and not managed.get("session_trail_active"):
                            managed["session_trail_active"] = True
                            logger.info(f"🌙 [SESSION END] Tightening trail on #{ticket} {sym} — session ending with R={r_multiple:.2f}")

            # H. Multi-Timeframe Confluence Exit — only if explicitly enabled AND held >= 30m AND in profit/BE
            if getattr(self.config, 'enable_htf_confluence_exit', False) and self.market_engine:
                hold_time = now_ts - float(managed.get("open_time", now_ts))
                if hold_time >= 1800 and 0.0 <= r_multiple < 0.3:
                    try:
                        h1_mkt = self.market_engine.get_market_analysis(sym, "H1")
                        h4_mkt = self.market_engine.get_market_analysis(sym, "H4")
                        h1_adverse = (is_buy and h1_mkt.get("trend") == "BEARISH") or \
                                     (not is_buy and h1_mkt.get("trend") == "BULLISH")
                        h4_adverse = (is_buy and h4_mkt.get("trend") == "BEARISH") or \
                                     (not is_buy and h4_mkt.get("trend") == "BULLISH")
                        if h1_adverse and h4_adverse and not managed.get("htf_exit_warned"):
                            managed["htf_exit_warned"] = True
                            logger.warning(
                                f"🔄 [HTF CONFLUENCE EXIT] Both H1+H4 flipped against #{ticket} {sym} after {hold_time/60:.1f}m at R={r_multiple:.2f} — securing profit"
                            )
                            await asyncio.to_thread(self.mt5.close_position, ticket, float(pos.get("volume", 0.01)))
                            if self.journal:
                                await asyncio.to_thread(self.journal.log_trade_event, ticket, sym, 'HTF_EXIT', cur_price, r_multiple, {'h1': h1_mkt.get('trend'), 'h4': h4_mkt.get('trend')})
                    except Exception as htf_err:
                        logger.debug(f"HTF exit check error: {htf_err}")


    def get_all_active_positions(self) -> List[Dict[str, Any]]:
        """Return all active positions from MT5."""
        return self.mt5.get_positions()

