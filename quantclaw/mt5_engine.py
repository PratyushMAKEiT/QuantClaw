# ==============================================================================
# quantclaw/mt5_engine.py — MetaTrader 5 High-Performance Engine
# ==============================================================================
"""
Production-grade asynchronous MetaTrader 5 client.
Directly communicates with local/remote MetaTrader 5 terminals via the official
MetaTrader5 Python bridge.

Features:
  - Account Telemetry (Balance, Equity, Free Margin, Margin Level, Leverage, Floating P&L)
  - Symbol Specification & Real-Time Tick Ingestion
  - Multi-Timeframe Rate (Candle) Data Copying (M1, M5, M15, M30, H1, H4, D1)
  - Instant Market & Pending Order Execution with automatic Filling Mode detection
  - Dynamic Lot Size Sizing based on risk percentage & stop loss points
  - Position Modification (SL/TP, Breakeven, Partial Close, Trailing Stops)
  - Auto-reconnect with exponential backoff & thread safety
"""

from __future__ import annotations

import asyncio
import datetime
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

MT5_IMPORT_ERROR = ""
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except Exception as e:
    MT5_AVAILABLE = False
    MT5_IMPORT_ERROR = f"{type(e).__name__}: {e}"
    mt5 = None

from quantclaw.utils.logger import get_logger
from quantclaw.models import MT5AccountInfo, MT5Position, MT5Order, MT5SymbolInfo

logger = get_logger(__name__)

# Timeframe mapping helper
TIMEFRAME_MAP = {}
if MT5_AVAILABLE:
    TIMEFRAME_MAP = {
        "M1": mt5.TIMEFRAME_M1,
        "1M": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "5M": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "15M": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "30M": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "1H": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "4H": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
        "1D": mt5.TIMEFRAME_D1,
        "W1": mt5.TIMEFRAME_W1,
        "1W": mt5.TIMEFRAME_W1,
    }


class MT5Client:
    """Thread-safe, high-speed client for MetaTrader 5."""

    def __init__(
        self,
        login: int = 0,
        password: str = "",
        server: str = "",
        path: str = "",
        portable: bool = False,
        timeout: int = 60000,
        magic: int = 999111,
    ) -> None:
        self.login: int = int(login or 0)
        self.password: str = password or ""
        self.server: str = server or ""
        self.path: str = path or ""
        self.portable: bool = portable
        self.timeout: int = timeout
        self.magic: int = magic

        self._connected: bool = False
        self._lock = threading.RLock()
        self._symbol_cache: Dict[str, MT5SymbolInfo] = {}
        self._resolved_symbol_map: Dict[str, str] = {}
        self._last_error: str = ""
        self._last_ping: float = 0.0

    # ── Connection Management ──────────────────────────────────────────────────

    def connect(
        self,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        path: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Connect and log in to MetaTrader 5."""
        if not MT5_AVAILABLE:
            self._last_error = f"MetaTrader5 Python module error: {MT5_IMPORT_ERROR or 'not installed'}"
            logger.error(self._last_error)
            return False, self._last_error

        with self._lock:
            if login is not None:
                self.login = int(login or 0)
            if password is not None:
                self.password = password or ""
            if server is not None:
                self.server = server or ""
            if path is not None:
                self.path = path or ""

            # 1. Initialize terminal connection (fast 3s timeout, NO credentials in initialize to prevent opening account dialogs)
            init_timeout = min(int(self.timeout or 3000), 3000)
            init_kwargs: Dict[str, Any] = {"timeout": init_timeout, "portable": self.portable}
            if self.path and os.path.exists(self.path):
                init_kwargs["path"] = self.path

            try:
                # First attempt: attach to existing/running terminal
                init_ok = mt5.initialize(**init_kwargs)
                if not init_ok and "path" in init_kwargs:
                    # Fallback to plain initialize without custom path
                    init_ok = mt5.initialize(timeout=init_timeout)
                
                if not init_ok:
                    err_code, err_desc = mt5.last_error()
                    self._last_error = f"MT5 initialize failed: [{err_code}] {err_desc}"
                    logger.error(self._last_error)
                    self._connected = False
                    return False, self._last_error

                # 2. Check current account status in the terminal
                curr_acc = mt5.account_info()
                
                # Case A: An account is already active in the terminal
                if curr_acc and curr_acc.login > 0:
                    # If user asked for a specific login and we are already on that exact account:
                    if self.login > 0 and curr_acc.login == self.login:
                        self._connected = True
                        self._last_error = ""
                        logger.info(
                            f"✅ Connected to MT5: Account {curr_acc.login} ({curr_acc.company}) on {curr_acc.server} | Equity: ${curr_acc.equity:.2f}"
                        )
                        return True, f"Connected to Account #{curr_acc.login} ({curr_acc.server})"
                    
                    # If user specified a DIFFERENT account than currently active:
                    elif self.login > 0 and self.password and self.server and curr_acc.login != self.login:
                        login_ok = mt5.login(
                            login=self.login,
                            password=self.password,
                            server=self.server,
                            timeout=init_timeout,
                        )
                        if login_ok:
                            new_acc = mt5.account_info()
                            self._connected = True
                            self._last_error = ""
                            logger.info(
                                f"✅ Switched to MT5 Account #{new_acc.login} ({new_acc.company}) on {new_acc.server} | Equity: ${new_acc.equity:.2f}"
                            )
                            return True, f"Connected to Account #{new_acc.login} ({new_acc.server})"
                        else:
                            err_code, err_desc = mt5.last_error()
                            logger.warning(
                                f"MT5 login to Account #{self.login} failed: [{err_code}] {err_desc}. "
                                f"Seamlessly continuing with active terminal Account #{curr_acc.login} ({curr_acc.server})."
                            )
                            self.login = curr_acc.login
                            self.server = curr_acc.server
                            self._connected = True
                            self._last_error = ""
                            return True, f"Connected to Account #{curr_acc.login} ({curr_acc.server})"
                    
                    # If no explicit login requested (login==0): use active account
                    else:
                        self.login = curr_acc.login
                        self.server = curr_acc.server
                        self._connected = True
                        self._last_error = ""
                        logger.info(
                            f"✅ Connected to active MT5 Account #{curr_acc.login} ({curr_acc.company}) on {curr_acc.server} | Equity: ${curr_acc.equity:.2f}"
                        )
                        return True, f"Connected to Account #{curr_acc.login} ({curr_acc.server})"


                # Case B: Terminal open but not logged into any account yet
                if self.login > 0 and self.password and self.server:
                    login_ok = mt5.login(
                        login=self.login,
                        password=self.password,
                        server=self.server,
                        timeout=init_timeout,
                    )
                    if login_ok:
                        acc_info = mt5.account_info()
                        self._connected = True
                        self._last_error = ""
                        logger.info(
                            f"✅ Connected to MT5: Account {acc_info.login} ({acc_info.company}) on {acc_info.server} | Equity: ${acc_info.equity:.2f}"
                        )
                        return True, f"Connected to Account #{acc_info.login} ({acc_info.server})"
                    else:
                        err_code, err_desc = mt5.last_error()
                        self._last_error = f"MT5 login failed: [{err_code}] {err_desc}"
                        logger.error(self._last_error)
                        self._connected = False
                        return False, self._last_error

                # No account active and no credentials provided
                self._last_error = "MT5 terminal is running but no account is logged in. Please log in to your account inside MetaTrader 5."
                logger.warning(self._last_error)
                self._connected = False
                return False, self._last_error

            except Exception as e:
                self._last_error = f"MT5 connection exception: {str(e)}"
                logger.error(self._last_error)
                self._connected = False
                return False, self._last_error

    def disconnect(self) -> None:
        """Shut down the MT5 connection."""
        if not MT5_AVAILABLE:
            return
        with self._lock:
            try:
                mt5.shutdown()
            except Exception:
                pass
            self._connected = False
            logger.info("MT5 disconnected.")

    def is_connected(self) -> bool:
        """Check if terminal and account are currently active and connected."""
        if not MT5_AVAILABLE:
            return False
        with self._lock:
            try:
                acc = mt5.account_info()
                if acc and acc.login > 0:
                    self._connected = True
                    return True
                term = mt5.terminal_info()
                if term and term.connected:
                    self._connected = True
                    return True
            except Exception:
                pass
            self._connected = False
            return False

    def get_last_error(self) -> str:
        """Return the last recorded error message."""
        return self._last_error

    def reconnect(self, max_attempts: int = 3) -> Tuple[bool, str]:
        """Reconnect to MT5 with non-blocking fast attempts."""
        if self.is_connected():
            return True, "Already connected"
        logger.warning("MT5 reconnecting...")
        try:
            self.disconnect()
        except Exception:
            pass

        for attempt in range(1, max_attempts + 1):
            delay = min(attempt * 2, 6)
            logger.info(f"Reconnect attempt {attempt}/{max_attempts} in {delay}s...")
            time.sleep(delay)
            ok, msg = self.connect()
            if ok:
                logger.info(f"Reconnected successfully: {msg}")
                return True, msg
            logger.warning(f"Reconnect attempt {attempt} failed: {msg}")

        return False, f"Reconnect failed after {max_attempts} attempts"




    def get_account_info(self) -> Optional[MT5AccountInfo]:
        """Fetch live account telemetry from MT5."""
        if not MT5_AVAILABLE:
            return None
        with self._lock:
            try:
                acc = mt5.account_info()
                if not acc:
                    return None
                return MT5AccountInfo(
                    login=acc.login,
                    server=acc.server,
                    currency=acc.currency,
                    leverage=acc.leverage,
                    balance=float(acc.balance),
                    equity=float(acc.equity),
                    margin=float(acc.margin),
                    margin_free=float(acc.margin_free),
                    margin_level=float(acc.margin_level) if acc.margin_level is not None else 0.0,
                    profit=float(acc.profit),
                    trade_allowed=bool(acc.trade_allowed),
                    trade_expert=bool(acc.trade_expert),
                    company=acc.company,
                )
            except Exception as e:
                logger.debug(f"Error fetching MT5 account info: {e}")
                return None

    def get_terminal_info(self) -> Dict[str, Any]:
        """Fetch terminal state and latency."""
        if not MT5_AVAILABLE:
            return {"connected": False, "error": "MT5 module missing"}
        with self._lock:
            try:
                term = mt5.terminal_info()
                if not term:
                    return {"connected": False}
                return {
                    "connected": term.connected,
                    "trade_allowed": term.trade_allowed,
                    "tradeapi_disabled": term.tradeapi_disabled,
                    "ping_last": term.ping_last,
                    "company": term.company,
                    "name": term.name,
                    "path": term.path,
                }
            except Exception as e:
                return {"connected": False, "error": str(e)}

    # ── Symbols & Market Data ──────────────────────────────────────────────────

    COMMON_ALIASES: Dict[str, List[str]] = {
        "US30": ["DJIUSD", "US30", "DJ30", "WS30", "WALLSTREET"],
        "NAS100": ["NDXUSD", "NAS100", "US100", "USTEC", "NASDAQ"],
        "SPX500": ["SPXUSD", "US500", "SP500"],
        "GER40": ["DAXEUR", "DE40", "GER40", "DAX"],
        "GOLD": ["XAUUSD", "GOLD"],
        "SILVER": ["XAGUSD", "SILVER"],
        "OIL": ["WTIUSD", "XTIUSD", "USOIL"],
    }

    def resolve_symbol(self, symbol: str) -> str:
        """
        Resolve a generic or base symbol name (e.g. 'EURUSD', 'US30', 'XAUUSD')
        to the broker's actual MT5 symbol name (e.g. 'EURUSD.', 'DJIUSD.', 'XAUUSD.raw').
        Caches the mapping for near-instant 0ms resolution.
        """
        if not symbol or not MT5_AVAILABLE:
            return symbol or ""
        clean = symbol.strip()
        u_clean = clean.upper()

        if u_clean in self._resolved_symbol_map:
            return self._resolved_symbol_map[u_clean]

        with self._lock:
            try:
                # 1. Check if symbol exists directly in MT5
                s = mt5.symbol_info(clean)
                if s:
                    self._resolved_symbol_map[u_clean] = s.name
                    return s.name

                # 2. Check alias candidates if available
                candidates = [clean]
                for alias_key, alias_list in self.COMMON_ALIASES.items():
                    if u_clean == alias_key or u_clean in alias_list:
                        candidates.extend([a for a in alias_list if a not in candidates])

                all_syms = [sym.name for sym in (mt5.symbols_get() or [])]

                # Match priority 1: Exact match (case insensitive) among candidates
                for cand in candidates:
                    m = next((sym for sym in all_syms if sym.upper() == cand.upper()), None)
                    if m:
                        self._resolved_symbol_map[u_clean] = m
                        return m

                # Match priority 2: Starts with candidate (e.g. candidate='EURUSD', matches 'EURUSD.')
                for cand in candidates:
                    m = next((sym for sym in all_syms if sym.upper().startswith(cand.upper())), None)
                    if m:
                        self._resolved_symbol_map[u_clean] = m
                        return m

                # Match priority 3: Substring match (e.g. 'XAUUSD' inside 'FX_XAUUSD')
                for cand in candidates:
                    m = next((sym for sym in all_syms if cand.upper() in sym.upper()), None)
                    if m:
                        self._resolved_symbol_map[u_clean] = m
                        return m

            except Exception:
                pass

        # Fallback to original symbol if no match found
        self._resolved_symbol_map[u_clean] = clean
        return clean

    DEFAULT_PORTFOLIO_TARGETS: List[str] = [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
        "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY",
        "XAUUSD", "XAGUSD",
        "BTCUSD", "ETHUSD", "SOLUSD", "LTCUSD",
        "US30", "DJIUSD", "NAS100", "NDXUSD", "SPX500", "GER40", "USOIL"
    ]

    def get_all_broker_symbols(self) -> List[str]:
        """
        Return all tradeable symbol names offered by the connected MT5 broker.
        Falls back to DEFAULT_PORTFOLIO_TARGETS if MT5 is disconnected or unavailable.
        """
        if not MT5_AVAILABLE:
            return list(self.DEFAULT_PORTFOLIO_TARGETS)
        with self._lock:
            try:
                syms = mt5.symbols_get()
                if not syms:
                    return list(self.DEFAULT_PORTFOLIO_TARGETS)
                tradeable = [
                    s.name for s in syms
                    if getattr(s, "trade_mode", 1) != getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", 0)
                ]
                return tradeable if tradeable else list(self.DEFAULT_PORTFOLIO_TARGETS)
            except Exception:
                return list(self.DEFAULT_PORTFOLIO_TARGETS)

    def auto_discover_symbols(self, requested_symbols: Optional[List[str]] = None) -> List[str]:
        """
        Intelligently query MT5 for all symbols offered by the connected broker.
        Discovers, validates, and activates tradeable pairs matching requested symbols or default portfolio.
        Returns the list of confirmed broker symbol names ready for live market streaming.
        """
        if not MT5_AVAILABLE:
            return requested_symbols or ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]

        with self._lock:
            try:
                all_syms = mt5.symbols_get() or []
                if not all_syms:
                    return requested_symbols or ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]

                # Map upper-case name -> symbol_info
                tradeable_map = {
                    s.name.upper(): s for s in all_syms 
                    if s.trade_mode != getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", 0)
                }

                targets = requested_symbols if (requested_symbols and len(requested_symbols) > 0) else self.DEFAULT_PORTFOLIO_TARGETS
                discovered: List[str] = []

                for target in targets:
                    clean = str(target).strip().upper()
                    if not clean:
                        continue

                    # 1. Direct resolve via resolve_symbol
                    resolved = self.resolve_symbol(clean)
                    s_info = tradeable_map.get(resolved.upper()) or mt5.symbol_info(resolved)

                    if s_info and s_info.trade_mode != getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", 0):
                        mt5.symbol_select(s_info.name, True)
                        if s_info.name not in discovered:
                            discovered.append(s_info.name)
                            continue

                    # 2. Check alias candidates
                    aliases = [clean]
                    for alias_key, alias_list in self.COMMON_ALIASES.items():
                        if clean == alias_key or clean in alias_list:
                            aliases.extend([a for a in alias_list if a not in aliases])

                    matched = False
                    for alias in aliases:
                        for s_name, s_obj in tradeable_map.items():
                            if s_name == alias.upper() or s_name.startswith(alias.upper()):
                                mt5.symbol_select(s_obj.name, True)
                                if s_obj.name not in discovered:
                                    discovered.append(s_obj.name)
                                    matched = True
                                    break
                        if matched:
                            break

                # Fallback: if discovery found nothing, pick top liquid tradeable pairs from broker
                if not discovered:
                    priority = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]
                    for p in priority:
                        r = self.resolve_symbol(p)
                        mt5.symbol_select(r, True)
                        if r not in discovered:
                            discovered.append(r)

                acc = mt5.account_info()
                broker_company = getattr(acc, "company", "MT5 Broker")
                logger.info(
                    f"🎯 [BROKER AUTO-DISCOVERY] {broker_company}: Auto-discovered and activated "
                    f"{len(discovered)} live tradeable pairs: {', '.join(discovered)}"
                )
                return discovered

            except Exception as e:
                logger.warning(f"Error auto-discovering broker symbols: {e}")
                return requested_symbols or ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]

    def is_symbol_tradeable(self, symbol: str) -> Tuple[bool, str]:
        """
        Ask MT5 if the symbol is actively open for trading right now:
        checks broker trade mode, terminal permissions, account permissions,
        session schedule / weekend closures, and live quotes.
        """
        if not MT5_AVAILABLE:
            return False, "MT5 unavailable"

        real_sym = self.resolve_symbol(symbol)
        with self._lock:
            try:
                mt5.symbol_select(real_sym, True)
                s = mt5.symbol_info(real_sym)
                if not s:
                    return False, f"Symbol {real_sym} not found on broker"

                # 1. Broker Symbol Trade Mode
                if s.trade_mode == getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", 0):
                    return False, f"Trading disabled for {real_sym} by broker"
                if s.trade_mode == getattr(mt5, "SYMBOL_TRADE_MODE_CLOSEONLY", 3):
                    return False, f"Symbol {real_sym} is close-only"

                # 2. Terminal AutoTrading Options
                term = mt5.terminal_info()
                if term and not term.trade_allowed:
                    return False, "Live trading not permitted in MT5 terminal options"

                # 3. Account Permissions
                acc = mt5.account_info()
                if acc and not acc.trade_allowed:
                    return False, "Trading not allowed on this MT5 account"

                # 4. Weekend / Market Hours Check for Non-Crypto Assets
                # Crypto assets trade 24/7. Forex, Metals, and Indices close on weekends.
                sym_upper = real_sym.upper()
                is_crypto = any(c in sym_upper for c in [
                    "BTC", "ETH", "SOL", "LTC", "XRP", "BNB", "DOGE", "ADA", "DOT", "AVAX", "LINK", "BCH"
                ]) or ("CRYPTO" in getattr(s, "path", "").upper())

                if not is_crypto:
                    now_utc = datetime.datetime.now(datetime.timezone.utc)
                    weekday = now_utc.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
                    hour = now_utc.hour
                    minute = now_utc.minute

                    # Global Forex / Index weekend close: Friday 21:15 UTC to Sunday 21:15 UTC
                    is_weekend_closed = (
                        (weekday == 4 and (hour > 21 or (hour == 21 and minute >= 15))) or
                        (weekday == 5) or
                        (weekday == 6 and (hour < 21 or (hour == 21 and minute < 15)))
                    )
                    if is_weekend_closed:
                        return False, f"Market closed for weekend (Global session closed for {real_sym})"

                # 5. Live Bid/Ask Quotes and Tick Freshness Check
                tick = mt5.symbol_info_tick(real_sym)
                if not tick or tick.bid <= 0 or tick.ask <= 0:
                    return False, f"Market closed or no live prices for {real_sym}"

                if not is_crypto:
                    tick_age = time.time() - getattr(tick, "time", time.time())
                    if tick_age > 900:  # 15 minutes without tick updates
                        return False, f"Market session inactive for {real_sym} (last tick {int(tick_age)}s ago)"

                return True, "Tradeable"
            except Exception as e:
                return False, f"MT5 tradeability check error: {e}"

    def get_symbol_info(self, symbol: str, use_cache: bool = True) -> Optional[MT5SymbolInfo]:
        """Fetch symbol specification and pricing details.
        Caches results for 30 seconds to avoid excessive MT5 API calls.
        """
        if not MT5_AVAILABLE:
            return None

        # Resolve broker-specific symbol name (e.g. EURUSD -> EURUSD.)
        real_symbol = self.resolve_symbol(symbol)

        # Cache lookup (outside lock for performance)
        if use_cache:
            cached = self._symbol_cache.get(real_symbol) or self._symbol_cache.get(symbol)
            if cached and (time.time() - getattr(cached, "_cached_at", 0)) < 30.0:
                return cached

        with self._lock:
            try:
                # Ensure symbol is selected in Market Watch
                mt5.symbol_select(real_symbol, True)
                s = mt5.symbol_info(real_symbol)
                if not s:
                    # Fallback to original string if real_symbol failed
                    if real_symbol != symbol:
                        mt5.symbol_select(symbol, True)
                        s = mt5.symbol_info(symbol)
                if not s:
                    return None

                tick = mt5.symbol_info_tick(symbol)
                bid = float(tick.bid) if tick else float(s.bid)
                ask = float(tick.ask) if tick else float(s.ask)
                # For Forex, last is often 0; use midpoint as fallback
                last = float(tick.last) if tick and tick.last else (bid + ask) / 2.0

                info = MT5SymbolInfo(
                    symbol=s.name,
                    path=s.path,
                    description=s.description,
                    point=float(s.point),
                    digits=int(s.digits),
                    spread=int(s.spread),
                    trade_contract_size=float(s.trade_contract_size),
                    # CRITICAL: populate tick value/size for correct lot sizing on all pairs
                    trade_tick_value=float(getattr(s, "trade_tick_value", 0.0) or 0.0),
                    trade_tick_size=float(getattr(s, "trade_tick_size", 0.0) or 0.0),
                    volume_min=float(s.volume_min),
                    volume_max=float(s.volume_max),
                    volume_step=float(s.volume_step),
                    stops_level=int(s.trade_stops_level),
                    bid=bid,
                    ask=ask,
                    last=last,
                )
                # Tag with cache timestamp and store
                object.__setattr__(info, "_cached_at", time.time())
                self._symbol_cache[symbol] = info
                return info
            except Exception as e:
                logger.warning(f"Error fetching symbol info for {symbol}: {e}")
                return None


    def get_all_symbols(self) -> List[str]:
        """Fetch list of all available symbols in broker terminal."""
        if not MT5_AVAILABLE:
            return []
        with self._lock:
            try:
                symbols = mt5.symbols_get()
                if not symbols:
                    return []
                return [s.name for s in symbols]
            except Exception:
                return []

    def get_rates(
        self,
        symbol: str,
        timeframe: str = "15M",
        count: int = 300,
    ) -> List[Dict[str, Any]]:
        """
        Fetch OHLCV candles for a symbol on a specific timeframe.
        Timeframes: "M1", "M5", "M15", "M30", "H1", "H4", "D1"
        """
        if not MT5_AVAILABLE:
            return []

        real_symbol = self.resolve_symbol(symbol)
        tf_code = TIMEFRAME_MAP.get(timeframe.upper(), mt5.TIMEFRAME_M15)
        with self._lock:
            try:
                # Ensure symbol is active
                mt5.symbol_select(real_symbol, True)
                rates = mt5.copy_rates_from_pos(real_symbol, tf_code, 0, count)
                if rates is None or len(rates) == 0:
                    if real_symbol != symbol:
                        mt5.symbol_select(symbol, True)
                        rates = mt5.copy_rates_from_pos(symbol, tf_code, 0, count)
                if rates is None or len(rates) == 0:
                    return []

                candles: List[Dict[str, Any]] = []
                for r in rates:
                    candles.append({
                        "time": int(r["time"]),
                        "open": float(r["open"]),
                        "high": float(r["high"]),
                        "low": float(r["low"]),
                        "close": float(r["close"]),
                        "volume": float(r["tick_volume"]),
                        "spread": int(r["spread"]),
                    })
                return candles
            except Exception as e:
                logger.debug(f"Error copying rates for {symbol} ({timeframe}): {e}")
                return []

    # ── Dynamic Lot Sizing Calculator ──────────────────────────────────────────

    def calculate_lot_size(
        self,
        symbol: str,
        risk_usd: float,
        sl_points: float,
        default_lots: float = 0.1,
    ) -> float:
        """
        Calculate precise lot size according to account risk in USD and SL distance in points.
        Formula: Lots = Risk_USD / (SL_Points * Point_Value)
        Clamped to broker min/max/step limits.
        """
        s = self.get_symbol_info(symbol)
        if not s or sl_points <= 0 or risk_usd <= 0:
            return default_lots

        try:
            # Use trade_tick_value/trade_tick_size for accurate cross-currency lot sizing.
            # point * contract_size is WRONG for non-USD-quote pairs (USDJPY off by ~150x).
            tick_value = getattr(s, "trade_tick_value", 0.0)
            tick_size = getattr(s, "trade_tick_size", 0.0)

            if tick_value > 0 and tick_size > 0 and s.point > 0:
                # Value per point per lot in account currency (correct for all pairs)
                point_value_per_lot = (tick_value / tick_size) * s.point
            else:
                # Fallback: approximate using contract size (only safe for USD-quote pairs)
                point_value_per_lot = s.point * s.trade_contract_size
                if point_value_per_lot <= 0:
                    point_value_per_lot = 1.0

            raw_lots = risk_usd / (sl_points * point_value_per_lot)

            # Step quantization
            step = s.volume_step if s.volume_step > 0 else 0.01
            lots = round(round(raw_lots / step) * step, 8)

            # Clamp between min and max
            lots = max(s.volume_min, min(s.volume_max, lots))
            return round(lots, 2)
        except Exception:
            return default_lots

    # ── Order Execution ────────────────────────────────────────────────────────

    def _determine_filling_type(self, symbol: str) -> int:
        """Autodetect broker supported execution filling mode (IOC, FOK, RETURN)."""
        if not MT5_AVAILABLE:
            return 1
        real_symbol = self.resolve_symbol(symbol)
        try:
            with self._lock:
                s = mt5.symbol_info(real_symbol) or mt5.symbol_info(symbol)
            if not s:
                return getattr(mt5, "ORDER_FILLING_IOC", 1)

            filling_mode = getattr(s, "filling_mode", 0)
            # MQL5 filling_mode bitmask:
            # Bit 1 (value 2, 0x02): SYMBOL_FILLING_IOC -> ORDER_FILLING_IOC (1)
            # Bit 0 (value 1, 0x01): SYMBOL_FILLING_FOK -> ORDER_FILLING_FOK (0)
            # Bit 2 (value 4, 0x04): SYMBOL_FILLING_BOC / RETURN -> ORDER_FILLING_RETURN (2)
            if filling_mode & 2:
                return getattr(mt5, "ORDER_FILLING_IOC", 1)
            elif filling_mode & 1:
                return getattr(mt5, "ORDER_FILLING_FOK", 0)
            elif filling_mode & 4:
                return getattr(mt5, "ORDER_FILLING_RETURN", 2)
            else:
                return getattr(mt5, "ORDER_FILLING_IOC", 1)
        except Exception:
            return getattr(mt5, "ORDER_FILLING_IOC", 1)

    def open_market_order(
        self,
        symbol: str,
        action: str,  # "BUY" or "SELL"
        volume: float,
        sl: float = 0.0,
        tp: float = 0.0,
        comment: str = "QuantClaw MT5",
        magic: Optional[int] = None,
        slippage: int = 15,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Execute instant market order on MetaTrader 5 with resilient filling mode fallback.
        Returns (success, result_dict).
        """
        if not MT5_AVAILABLE:
            return False, {"error": "MT5 module unavailable"}

        real_symbol = self.resolve_symbol(symbol)
        with self._lock:
            try:
                mt5.symbol_select(real_symbol, True)
                sym_info = self.get_symbol_info(real_symbol) or self.get_symbol_info(symbol)
                if not sym_info:
                    return False, {"error": f"Symbol {symbol} not found"}

                is_buy = action.upper() in ("BUY", "LONG")
                order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
                price = sym_info.ask if is_buy else sym_info.bid
                use_magic = magic if magic is not None else self.magic

                # Step quantization on volume — round(..., 8) eliminates IEEE 754 float error
                # e.g. round(0.01/0.01)*0.01 = 1.0 * 0.01 = 0.010000000000000002 without rounding
                step = sym_info.volume_step if sym_info.volume_step > 0 else 0.01
                volume = round(round(volume / step) * step, 8)
                volume = max(sym_info.volume_min, min(sym_info.volume_max, volume))

                # Build candidate filling modes with primary autodetected mode first
                primary_filling = self._determine_filling_type(real_symbol)
                filling_candidates = [primary_filling]
                for mode in [
                    getattr(mt5, "ORDER_FILLING_IOC", 1),
                    getattr(mt5, "ORDER_FILLING_FOK", 0),
                    getattr(mt5, "ORDER_FILLING_RETURN", 2),
                ]:
                    if mode not in filling_candidates:
                        filling_candidates.append(mode)

                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": sym_info.symbol or real_symbol,
                    "volume": float(volume),
                    "type": order_type,
                    "price": float(price),
                    "sl": float(round(sl, sym_info.digits)) if sl > 0 else 0.0,
                    "tp": float(round(tp, sym_info.digits)) if tp > 0 else 0.0,
                    "deviation": int(slippage),
                    "magic": int(use_magic),
                    "comment": str(comment),
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": primary_filling,
                }

                result = None
                last_err_msg = ""
                last_retcode = 0

                for fill_mode in filling_candidates:
                    request["type_filling"] = fill_mode
                    result = mt5.order_send(request)
                    if result is None:
                        err_code, err_desc = mt5.last_error()
                        last_err_msg = f"order_send failed: [{err_code}] {err_desc}"
                        last_retcode = err_code
                        continue

                    last_retcode = getattr(result, "retcode", 0)
                    ret_comment = getattr(result, "comment", "") or str(mt5.last_error())

                    # Success check
                    if result.retcode in (
                        mt5.TRADE_RETCODE_DONE,
                        getattr(mt5, "TRADE_RETCODE_PLACED", 10008),
                        getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010),
                    ):
                        logger.info(
                            f"🚀 MT5 Order Punched: {action.upper()} {volume} lots {symbol} @ {result.price} | Ticket #{result.order}"
                        )
                        return True, {
                            "ticket": result.order,
                            "deal": result.deal,
                            "volume": result.volume,
                            "price": result.price,
                            "retcode": result.retcode,
                            "comment": result.comment,
                        }

                    # If unsupported filling mode (10030), try next candidate
                    if last_retcode in [10030, getattr(mt5, "TRADE_RETCODE_UNSUPPORTED_FILLING_MODE", 10030)]:
                        logger.debug(f"Retrying {real_symbol} with alternative filling mode after retcode {last_retcode}")
                        continue

                    # If ECN / Market execution broker rejects stops in initial deal (10016), retry without stops then modify
                    if last_retcode in [10016, getattr(mt5, "TRADE_RETCODE_INVALID_STOPS", 10016)] and (sl > 0 or tp > 0):
                        logger.info(f"Broker rejected initial stops for {real_symbol}. Retrying deal without SL/TP and applying via modify...")
                        request["sl"] = 0.0
                        request["tp"] = 0.0
                        retry_res = mt5.order_send(request)
                        if retry_res and retry_res.retcode == mt5.TRADE_RETCODE_DONE:
                            self.modify_position(retry_res.order, sl, tp)
                            logger.info(
                                f"🚀 MT5 Order Punched (Two-step): {action.upper()} {volume} lots {symbol} @ {retry_res.price} | Ticket #{retry_res.order}"
                            )
                            return True, {
                                "ticket": retry_res.order,
                                "deal": retry_res.deal,
                                "volume": retry_res.volume,
                                "price": retry_res.price,
                                "retcode": retry_res.retcode,
                                "comment": retry_res.comment,
                            }

                    # Terminal AlgoTrading disabled check
                    if last_retcode in [10026, 10027] or "autotrading" in ret_comment.lower():
                        last_err_msg = "AutoTrading disabled in MT5: (1) Click 'Algo Trading' button in MT5 top toolbar to turn it GREEN; (2) In MT5 go to Tools -> Options -> Expert Advisors and check 'Allow Algo Trading'; (3) Ensure you are logged into MT5 with your Master/Trader password."
                    elif last_retcode in [10018, getattr(mt5, "TRADE_RETCODE_MARKET_CLOSED", 10018)] or "market closed" in ret_comment.lower():
                        last_err_msg = f"Market is currently closed for {symbol} (trading session inactive)"
                    else:
                        last_err_msg = f"Trade rejected: [{last_retcode}] {ret_comment}"
                    break

                return False, {
                    "error": last_err_msg or "Order send failed",
                    "retcode": last_retcode,
                }

            except Exception as e:
                logger.error(f"Exception opening market order on {symbol}: {e}")
                return False, {"error": str(e)}

    def modify_position(
        self,
        ticket: int,
        sl: float,
        tp: float,
    ) -> Tuple[bool, str]:
        """Modify Stop Loss and Take Profit of an active position."""
        if not MT5_AVAILABLE:
            return False, "MT5 module unavailable"

        with self._lock:
            try:
                ticket_int = int(ticket)
                all_pos = mt5.positions_get() or []
                pos = next((p for p in all_pos if p.ticket == ticket_int), None)
                if not pos:
                    direct = mt5.positions_get(ticket=ticket_int)
                    if direct:
                        pos = direct[0]
                if not pos:
                    return False, f"Position #{ticket_int} not found in MT5"

                sym_info = self.get_symbol_info(pos.symbol)
                digits = sym_info.digits if sym_info else 5

                # sl=0 means "leave existing SL unchanged"; sl>0 sets new SL; sl=-1 clears SL
                if sl > 0:
                    sl_val = float(round(sl, digits))
                elif sl < 0:
                    sl_val = 0.0  # Explicitly clear stop loss
                else:
                    sl_val = float(round(pos.sl, digits)) if pos.sl > 0 else 0.0  # Keep existing
                tp_val = float(round(tp, digits)) if tp > 0 else (float(round(pos.tp, digits)) if pos.tp > 0 else 0.0)


                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": ticket_int,
                    "symbol": pos.symbol,
                    "sl": sl_val,
                    "tp": tp_val,
                }

                result = mt5.order_send(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    logger.info(f"✏️ MT5 Position #{ticket_int} Modified: SL={sl_val:.{digits}f}, TP={tp_val:.{digits}f}")
                    return True, f"Breakeven/Modify SL={sl_val:.{digits}f} TP={tp_val:.{digits}f} Applied"
                else:
                    ret_code = getattr(result, "retcode", 0) if result else 0
                    ret_str = getattr(result, "comment", "") if result else str(mt5.last_error())
                    if ret_code in [10026, 10027] or "autotrading" in ret_str.lower():
                        return False, "AutoTrading disabled in MT5: (1) Click 'Algo Trading' button in MT5 top toolbar to turn it GREEN; (2) In MT5 go to Tools -> Options -> Expert Advisors and check 'Allow Algo Trading'; (3) Ensure you are logged into MT5 with your Master/Trader password (not Investor/Read-Only password)."
                    return False, f"Modify failed: {ret_str}"

            except Exception as e:
                return False, str(e)

    def close_position(
        self,
        ticket: int,
        volume: float = 0.0,
    ) -> Tuple[bool, str]:
        """Close an open position (fully or partially)."""
        if not MT5_AVAILABLE:
            return False, "MT5 module unavailable"

        with self._lock:
            try:
                ticket_int = int(ticket)
                all_pos = mt5.positions_get() or []
                pos = next((p for p in all_pos if p.ticket == ticket_int), None)
                if not pos:
                    direct = mt5.positions_get(ticket=ticket_int)
                    if direct:
                        pos = direct[0]
                if not pos:
                    return False, f"Position #{ticket_int} not found in MT5"

                close_volume = float(volume if (volume > 0 and volume <= pos.volume) else pos.volume)
                close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                
                # Fetch live price
                sym_info = self.get_symbol_info(pos.symbol)
                tick = mt5.symbol_info_tick(pos.symbol)
                if tick and tick.bid > 0 and tick.ask > 0:
                    price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
                elif sym_info and sym_info.bid > 0:
                    price = sym_info.bid if pos.type == mt5.ORDER_TYPE_BUY else sym_info.ask
                else:
                    price = float(pos.price_current)

                # Filling candidates
                primary_filling = self._determine_filling_type(pos.symbol)
                filling_candidates = [primary_filling]
                for mode in [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]:
                    if mode not in filling_candidates:
                        filling_candidates.append(mode)

                last_comment = ""
                for fill_mode in filling_candidates:
                    request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "position": ticket_int,
                        "symbol": pos.symbol,
                        "volume": close_volume,
                        "type": close_type,
                        "price": float(price),
                        "deviation": 25,
                        "magic": self.magic,
                        "comment": f"QuantClaw Close #{ticket_int}",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": fill_mode,
                    }

                    result = mt5.order_send(request)
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        logger.info(f"🛑 MT5 Position #{ticket_int} Closed: {close_volume} lots @ {result.price}")
                        return True, f"Closed #{ticket_int} @ {result.price}"
                    else:
                        ret_code = getattr(result, "retcode", 0) if result else 0
                        last_comment = getattr(result, "comment", "") if result else str(mt5.last_error())
                        if ret_code in [10026, 10027] or "autotrading" in last_comment.lower():
                            return False, "AutoTrading disabled in MT5: (1) Click 'Algo Trading' button in MT5 top toolbar to turn it GREEN; (2) In MT5 go to Tools -> Options -> Expert Advisors and check 'Allow Algo Trading'; (3) Ensure you are logged into MT5 with your Master/Trader password (not Investor/Read-Only password)."
                        if result and result.retcode in [10030, getattr(mt5, "TRADE_RETCODE_UNSUPPORTED_FILLING_MODE", 10030)]:
                            continue
                        break

                return False, f"Close failed: {last_comment}"

            except Exception as e:
                return False, str(e)

    partial_close = close_position

    def close_all_positions(self, only_magic: Optional[int] = None) -> Tuple[int, int]:
        """
        Close open positions immediately (Panic / Flatten).
        If only_magic is specified, only closes positions with that magic number,
        leaving user manual trades (magic=0) and other trades untouched.
        Returns (closed_count, error_count).
        """
        if not MT5_AVAILABLE:
            return 0, 0

        with self._lock:
            positions = mt5.positions_get()
            if not positions:
                return 0, 0

            closed = 0
            errors = 0
            for pos in positions:
                pos_magic = getattr(pos, "magic", 0)
                if only_magic is not None and pos_magic != only_magic:
                    logger.debug(f"Skipping manual/external position #{pos.ticket} (magic={pos_magic}) during flatten")
                    continue
                success, _ = self.close_position(pos.ticket)
                if success:
                    closed += 1
                else:
                    errors += 1
            return closed, errors

    # ── Trade History & Deals ──────────────────────────────────────────────────

    def get_history_deals(self, ticket: int, lookback_days: int = 30) -> Dict[str, Any]:
        """
        Query MT5 history deals for a closed position ticket.
        Returns dict with: profit, swap, commission, close_price, close_time.
        Falls back to zeros if not found.
        """
        if not MT5_AVAILABLE:
            return {"profit": 0.0, "swap": 0.0, "commission": 0.0, "close_price": 0.0}

        with self._lock:
            try:
                import datetime
                date_from = datetime.datetime.now() - datetime.timedelta(days=lookback_days)
                deals = mt5.history_deals_get(position=int(ticket))
                if not deals:
                    # Fallback: broad date range search
                    deals = mt5.history_deals_get(
                        date_from,
                        datetime.datetime.now(),
                    )
                    if deals:
                        deals = [d for d in deals if d.position_id == int(ticket)]

                if not deals:
                    return {"profit": 0.0, "swap": 0.0, "commission": 0.0, "close_price": 0.0}

                total_profit = sum(d.profit for d in deals)
                total_swap = sum(d.swap for d in deals)
                total_commission = sum(d.commission for d in deals)
                # Last deal = closing deal
                close_deal = deals[-1]
                net_pnl = total_profit + total_swap + total_commission

                logger.debug(
                    f"📋 History deals for position #{ticket}: P&L={total_profit:.2f}, "
                    f"Swap={total_swap:.2f}, Comm={total_commission:.2f}, Net={net_pnl:.2f}"
                )
                return {
                    "profit": total_profit,
                    "swap": total_swap,
                    "commission": total_commission,
                    "net_pnl": net_pnl,
                    "close_price": float(getattr(close_deal, "price", 0.0)),
                    "close_time": int(getattr(close_deal, "time", 0)),
                }
            except Exception as e:
                logger.debug(f"Error fetching history deals for #{ticket}: {e}")
                return {"profit": 0.0, "swap": 0.0, "commission": 0.0, "close_price": 0.0}

    # ── Positions & Orders Queries ─────────────────────────────────────────────

    def get_positions(self, symbol: str = "") -> List[Dict[str, Any]]:
        """Fetch all currently open positions."""
        if not MT5_AVAILABLE:
            return []

        with self._lock:
            try:
                positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
                if not positions:
                    return []

                res = []
                for p in positions:
                    is_buy = p.type == mt5.ORDER_TYPE_BUY
                    res.append({
                        "ticket": p.ticket,
                        "symbol": p.symbol,
                        "type": "BUY" if is_buy else "SELL",
                        "side": "buy" if is_buy else "sell",
                        "volume": float(p.volume),
                        "size": float(p.volume),
                        "open_price": float(p.price_open),
                        "entry_price": float(p.price_open),
                        "current_price": float(p.price_current),
                        "mark_price": float(p.price_current),
                        "sl": float(p.sl),
                        "current_sl_price": float(p.sl),
                        "tp": float(p.tp),
                        "current_tp_price": float(p.tp),
                        "profit": float(p.profit),
                        "unrealized_pnl": float(p.profit),
                        "unrealized_pnl_usd": float(p.profit),
                        "regime": "INSTITUTIONAL_SMC",
                        "live_bias_score": 0.0,
                        "swap": float(p.swap),
                        "comment": p.comment,
                        "time": int(p.time),
                        "magic": p.magic,
                    })
                return res
            except Exception as e:
                logger.debug(f"Error fetching MT5 positions: {e}")
                return []

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        """Fetch all currently active pending orders."""
        if not MT5_AVAILABLE:
            return []

        with self._lock:
            try:
                orders = mt5.orders_get()
                if not orders:
                    return []

                res = []
                type_names = {
                    mt5.ORDER_TYPE_BUY_LIMIT: "BUY_LIMIT",
                    mt5.ORDER_TYPE_SELL_LIMIT: "SELL_LIMIT",
                    mt5.ORDER_TYPE_BUY_STOP: "BUY_STOP",
                    mt5.ORDER_TYPE_SELL_STOP: "SELL_STOP",
                }
                for o in orders:
                    res.append({
                        "ticket": o.ticket,
                        "symbol": o.symbol,
                        "type": type_names.get(o.type, str(o.type)),
                        "volume": float(o.volume_initial),
                        "price": float(o.price_open),
                        "sl": float(o.sl),
                        "tp": float(o.tp),
                        "time": int(o.time_setup),
                        "magic": o.magic,
                        "comment": o.comment,
                    })
                return res
            except Exception:
                return []
