# ==============================================================================
# quantclaw/account_tracker.py — Live MT5 Account Tracker & Drawdown Monitor
# ==============================================================================
"""
Live MetaTrader 5 Account Telemetry & Daily Loss Circuit Monitor.
Continuously queries MT5 account info (Balance, Equity, Margin, Free Margin,
Margin Level %, Floating P&L) and tracks daily/weekly growth against targets.
"""

from __future__ import annotations

import asyncio
import datetime
import time
from typing import Any, Dict, Optional
from quantclaw.utils.logger import get_logger
from quantclaw.models import MT5AccountInfo

import threading

logger = get_logger("account_tracker")


class AccountTracker:
    """Tracks MT5 balance, equity, daily profit/loss, and circuit breaker thresholds."""

    def __init__(self, mt5_client: Any, trade_journal: Optional[Any] = None) -> None:
        self.mt5 = mt5_client
        self.journal = trade_journal

        self._start_of_day_equity: float = 0.0
        self._current_day: str = ""
        self._live_account: Optional[MT5AccountInfo] = None
        self._last_poll_time: float = 0.0
        self._last_snapshot_time: float = 0.0
        self._peak_equity: float = 0.0
        self._max_drawdown_pct: float = 0.0
        self._weekly_start_equity: float = 0.0
        self._today_realized_pnl: float = 0.0
        self._connected_cached: bool = False
        self._last_login: int = 0
        self._account_switched: bool = False
        self._lock = threading.Lock()

        # Try to load start-of-day equity from journal (survives mid-day restarts)
        self._try_load_sod_equity()

    def _try_load_sod_equity(self) -> None:
        """Load midnight equity from SQLite journal to survive mid-day restarts."""
        try:
            if self.journal and hasattr(self.journal, "get_equity_history"):
                history = self.journal.get_equity_history(days=1)
                if history:
                    # First record of today = start-of-day baseline
                    today_str = datetime.date.today().isoformat()
                    today_records = [h for h in history if str(h.get("date", "")).startswith(today_str)]
                    if today_records:
                        sod = float(today_records[0].get("equity", 0.0))
                        if sod > 0:
                            self._start_of_day_equity = sod
                            self._current_day = today_str
                            logger.info(f"📅 Start-of-day equity loaded from journal: ${sod:,.2f}")
        except Exception as e:
            logger.debug(f"Could not load SOD equity from journal: {e}")

    async def poll_account(self) -> Optional[MT5AccountInfo]:
        """Poll live account info from MT5 and record periodic equity snapshots."""
        today_str = datetime.date.today().isoformat()
        
        acc = await asyncio.to_thread(self.mt5.get_account_info)
        connected = bool(acc and acc.login > 0)

        # Query true net realized P&L directly from MT5 closed deals today
        realized_today = 0.0
        try:
            get_pnl_fn = getattr(self.mt5, "get_today_realized_pnl", None)
            if callable(get_pnl_fn):
                res = await asyncio.to_thread(get_pnl_fn)
                if isinstance(res, (int, float)):
                    realized_today = float(res)
            elif self.journal and hasattr(self.journal, "get_today_pnl"):
                res = await asyncio.to_thread(self.journal.get_today_pnl)
                if isinstance(res, (int, float)):
                    realized_today = float(res)
        except Exception:
            realized_today = 0.0
        
        with self._lock:
            self._today_realized_pnl = realized_today
            self._connected_cached = connected

            if today_str != self._current_day:
                self._current_day = today_str
                self._start_of_day_equity = acc.equity if acc else 0.0

            if not acc or acc.login <= 0:
                return self._live_account

            # Account switch detection (e.g. from funded to demo)
            if self._last_login != 0 and acc.login != self._last_login:
                logger.warning(f"⚠️ [ACCOUNT SWITCH] MT5 terminal switched accounts from #{self._last_login} to #{acc.login}. Symbol list will be re-discovered for new broker.")
                logger.info(f"🔄 Account switched from #{self._last_login} to #{acc.login}. Resetting baseline equity to ${acc.equity:,.2f}.")
                self._start_of_day_equity = acc.equity
                self._peak_equity = acc.equity
                self._max_drawdown_pct = 0.0
                self._account_switched = True  # Signal for main loop to re-discover symbols
            elif self._last_login == 0:
                # First poll on startup: if start-of-day equity is from a different account (difference > 10%), align baseline to live account
                if self._start_of_day_equity <= 0.0 or abs(self._start_of_day_equity - acc.equity) / max(1.0, acc.equity) > 0.10:
                    logger.info(f"🔄 Initializing start-of-day baseline equity for account #{acc.login}: ${acc.equity:,.2f}.")
                    self._start_of_day_equity = acc.equity
                    self._peak_equity = acc.equity
                    self._max_drawdown_pct = 0.0
            self._last_login = acc.login

            self._live_account = acc
            self._last_poll_time = time.time()

            # Mathematically anchor SOD equity to midnight: current equity minus all P&L generated today
            calculated_sod = acc.equity - (realized_today + getattr(acc, "profit", 0.0))
            if calculated_sod > 0.0:
                self._start_of_day_equity = calculated_sod
            elif self._start_of_day_equity <= 0.0:
                self._start_of_day_equity = acc.equity

            if acc.equity > self._peak_equity:
                self._peak_equity = acc.equity
            dd = (self._peak_equity - acc.equity) / max(1.0, self._peak_equity) * 100
            if dd > self._max_drawdown_pct:
                self._max_drawdown_pct = dd
                
            if 0 < acc.margin_level < 150.0:
                logger.warning(f"Margin call warning: {acc.margin_level}%")
                
            now = time.time()
            if self.journal and (now - self._last_snapshot_time) >= 60.0:
                self.journal.record_equity_snapshot(acc.equity, acc.balance, acc.profit)
                self._last_snapshot_time = now

        return acc

    def get_live_state(self) -> Dict[str, Any]:
        """Return formatted account state for dashboard and APIs."""
        with self._lock:
            acc = self._live_account
            sod = self._start_of_day_equity

        if not acc:
            return {
                "connected": False,
                "login": 0,
                "server": "--",
                "balance": 0.0,
                "equity": 0.0,
                "margin": 0.0,
                "margin_free": 0.0,
                "margin_level": 0.0,
                "floating_pnl": 0.0,
                "today_pnl": 0.0,
                "today_pnl_pct": 0.0,
                "currency": "USD",
                "trade_allowed": False,
            }

        # Use exact MT5 closed deals realized net P&L for today_pnl
        today_pnl = self._today_realized_pnl
        equity_delta = acc.equity - sod if sod > 0 else 0.0
        today_pnl_pct = (today_pnl / sod * 100.0) if sod > 0 else 0.0

        return {
            "connected": self._connected_cached,
            "login": acc.login,
            "server": acc.server,
            "company": acc.company,
            "balance": round(acc.balance, 2),
            "equity": round(acc.equity, 2),
            "margin": round(acc.margin, 2),
            "margin_free": round(acc.margin_free, 2),
            "margin_level": round(acc.margin_level, 1),
            "floating_pnl": round(acc.profit, 2),
            "today_pnl": round(today_pnl, 2),
            "today_pnl_pct": round(today_pnl_pct, 2),
            "currency": acc.currency,
            "trade_allowed": acc.trade_allowed,
            "trade_expert": acc.trade_expert,
            "leverage": acc.leverage,
            "peak_equity": self._peak_equity,
            "max_drawdown_pct": self._max_drawdown_pct
        }

    def get_daily_loss_pct(self) -> float:
        """Calculate today's drawdown percentage from start of day equity."""
        with self._lock:
            acc = self._live_account
            sod = self._start_of_day_equity
            connected = self._connected_cached
        if not connected or not acc or acc.equity <= 0.0 or sod <= 0.0:
            return 0.0
        loss = sod - acc.equity
        if loss <= 0.0:
            return 0.0
        return (loss / sod) * 100.0

    def check_and_clear_account_switch(self) -> bool:
        """Returns True if account was switched since last call. Clears the flag."""
        with self._lock:
            switched = self._account_switched
            self._account_switched = False
            return switched

    def reset_baseline(self) -> None:
        """Reset start-of-day baseline to current equity upon manual circuit breaker reset."""
        with self._lock:
            if self._live_account and self._live_account.equity > 0:
                self._start_of_day_equity = self._live_account.equity
                self._peak_equity = self._live_account.equity
                self._max_drawdown_pct = 0.0

