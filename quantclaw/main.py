# ==============================================================================
# quantclaw/main.py — QuantClaw MT5 Main Application Entry Point
# ==============================================================================
"""
QuantClaw MetaTrader 5 Autonomous System Entry Point.
Orchestrates the startup of all subsystems:

  1. Load persistent configuration (%APPDATA%/QuantClaw/config.json)
  2. Initialize the MetaTrader 5 connector (MT5Client)
  3. Initialize SQLite Trade Journal & Account Tracker
  4. Initialize 24/7 Market Engine & 5-Engine Strategy Matrix
  5. Initialize Self-Learning ML Brain & Claude AI Co-Pilot
  6. Initialize Risk & Position Lifecycle Manager
  7. Start FastAPI Telemetry Server in background daemon thread
  8. Launch PyQt6 Fullscreen WebEngine Dashboard
  9. Manage clean shutdown
"""

import sys
import io

# ── Safe Stdout/Stderr fallback for PyInstaller windowed apps ──────────────────
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()

import asyncio
import logging
import multiprocessing
import os
import threading
import time
from typing import Any, Dict, List, Optional
import uvicorn

# ── Clean Qt WebEngine flags for packaged EXE (safe sandbox disable without breaking rasterizer) ──
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox --disable-gpu-sandbox"
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

if getattr(sys, "frozen", False):
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    for cand in [
        os.path.join(base_dir, "PyQt6", "Qt6", "bin", "QtWebEngineProcess.exe"),
        os.path.join(base_dir, "_internal", "PyQt6", "Qt6", "bin", "QtWebEngineProcess.exe"),
        os.path.join(os.path.dirname(sys.executable), "_internal", "PyQt6", "Qt6", "bin", "QtWebEngineProcess.exe"),
    ]:
        if os.path.exists(cand):
            os.environ["QTWEBENGINEPROCESS_PATH"] = cand
            break



# ── PyQt6 Imports ──────────────────────────────────────────────────────────────
from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

# ── QuantClaw MT5 Subsystems ──────────────────────────────────────────────────
from quantclaw.config import AppConfig
from quantclaw.models import StrategySignal
from quantclaw.mt5_engine import MT5Client
from quantclaw.trade_journal import TradeJournal
from quantclaw.account_tracker import AccountTracker
from quantclaw.market_engine import MarketEngine
from quantclaw.strategy_engine import StrategyEngine
from quantclaw.ml_engine import MLEngine
from quantclaw.ai_engine import AIEngine
from quantclaw.news_monitor import NewsMonitor
from quantclaw.risk_manager import RiskManager
from quantclaw.server import create_app
from quantclaw.strategy_tester import StrategyTester
from quantclaw.market_thinking import MarketThinkingEngine
from quantclaw.utils.logger import setup_logger, get_logger

logger = get_logger("main")


# ==============================================================================
# SERVER RUNNER (BACKGROUND DAEMON)
# ==============================================================================

class ServerRunner:
    """Runs Uvicorn FastAPI server in a background thread."""

    def __init__(self, app: Any, host: str = "0.0.0.0", port: int = 80) -> None:
        self.app = app
        self.host = host
        self.port = port
        self.server: Optional[uvicorn.Server] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        cfg = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_config=None,  # Prevent uvicorn isatty crash in windowed GUI mode
            access_log=False,
        )
        self.server = uvicorn.Server(cfg)
        self._thread = threading.Thread(target=self.server.run, daemon=True, name="QuantClaw-Server")
        self._thread.start()
        logger.info(f"🌐 Telemetry Server running at http://localhost:{self.port}")

    def stop(self) -> None:
        if self.server:
            self.server.should_exit = True


# ==============================================================================
# FULLSCREEN WEB ENGINE WINDOW
# ==============================================================================

class FullscreenWebWindow(QMainWindow):
    """Hosts the QuantClaw MT5 Telemetry & Control Dashboard in full-screen."""

    def __init__(self, url: str, config: AppConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._url = url

        self.setWindowTitle("QuantClaw MT5 — Autonomous AI+ML Trading System")
        self.setMinimumSize(1024, 680)
        self.resize(1360, 850)

        self._browser = QWebEngineView()
        settings = self._browser.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)


        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._browser)
        self.setCentralWidget(central)

        self._retry_count = 0
        self._browser.loadFinished.connect(self._on_load_finished)
        self._browser.setUrl(QUrl(self._url))

    def _on_load_finished(self, ok: bool) -> None:
        if not ok and self._retry_count < 10:
            self._retry_count += 1
            logger.warning(f"Dashboard failed to load on attempt {self._retry_count}, retrying in 1s...")
            QTimer.singleShot(1000, lambda: self._browser.setUrl(QUrl(self._url)))
        elif ok:
            self._retry_count = 0
            logger.info("✅ Dashboard loaded successfully in WebEngine.")

    def keyPressEvent(self, event) -> None:
        """Allow F5 or Ctrl+R to reload dashboard."""
        from PyQt6.QtCore import Qt
        if event.key() == Qt.Key.Key_F5 or (event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_R):
            self._browser.reload()
        else:
            super().keyPressEvent(event)



# ==============================================================================
# QUANTCLAW MT5 APPLICATION COORDINATOR
# ==============================================================================

class QuantClawMT5App:
    """Master Application Coordinator."""

    def __init__(self) -> None:
        setup_logger()
        try:
            logger.info("Initializing QuantClaw MT5 Autonomous System...")

            # 1. Load Configuration
            self.config = AppConfig.load()

            # 2. MT5 Client
            self.mt5 = MT5Client(
                login=self.config.mt5_login,
                password=self.config.mt5_password,
                server=self.config.mt5_server,
                path=self.config.mt5_path,
                portable=self.config.mt5_portable,
                timeout=self.config.mt5_timeout,
                magic=self.config.mt5_magic_number,
            )

            # 3. SQLite Trade Journal & Account Tracker
            self.journal = TradeJournal()
            self.account_tracker = AccountTracker(self.mt5, self.journal)

            # 4. Market & Strategy Engines
            self.market = MarketEngine(self.mt5)
            self.strategy = StrategyEngine(self.config, self.market)

            # 5. ML Brain & Claude AI
            self.ml = MLEngine(self.config, self.market, self.journal)
            self.ai = AIEngine(
                api_key=self.config.anthropic_api_key,
                model=self.config.anthropic_model,
            )

            # 6. Global News Monitor
            self.news = NewsMonitor()

            # 7. Risk Manager
            self.risk = RiskManager(
                config=self.config,
                mt5_client=self.mt5,
                account_tracker=self.account_tracker,
                trade_journal=self.journal,
                ml_engine=self.ml,
                market_engine=self.market,
                news_monitor=self.news,
            )

            # 8. Wire Event Pipelines
            self.strategy.subscribe(self._on_strategy_signal)
            self.market.subscribe(self.strategy.on_candle_close)

            # 8b. Autonomous Strategy Tester & Live Thinking Brain
            self.strategy_tester = StrategyTester(config=self.config, mt5_client=self.mt5, market_engine=self.market)
            self.strategy.strategy_tester = self.strategy_tester
            self.thinking = MarketThinkingEngine(config=self.config, market_engine=self.market, risk_manager=self.risk, mt5_client=self.mt5)

            # 9. FastAPI Telemetry Server
            self.fastapi_app = create_app(
                config=self.config,
                mt5_client=self.mt5,
                market_engine=self.market,
                strategy_engine=self.strategy,
                ml_engine=self.ml,
                ai_engine=self.ai,
                risk_manager=self.risk,
                account_tracker=self.account_tracker,
                trade_journal=self.journal,
                news_monitor=self.news,
                on_settings_applied=self._on_settings_applied,
                strategy_tester=self.strategy_tester,
                thinking_engine=self.thinking,
            )
            self.server_runner = ServerRunner(
                app=self.fastapi_app,
                host=self.config.server_host,
                port=self.config.server_port,
            )

            # Background loop reference
            self._async_loop: Optional[asyncio.AbstractEventLoop] = None

        except Exception as e:
            logger.critical(f"FATAL ERROR during initialization: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _on_strategy_signal(self, signal: StrategySignal) -> None:
        """Handle incoming strategy signal from any of the 5 engines."""
        if not self.config.enable_autonomous_trading:
            return

        # Fast-exit if bot is disarmed: prevents CPU waste and phantom "APPROVED" logs
        if not self.config.armed:
            return

        # Per-symbol permission check — only trade symbols the user has ticked ON
        if not self.config.is_symbol_enabled(signal.symbol):
            logger.debug(f"🚫 [SYMBOL DISABLED] Skipping signal for {signal.symbol} — not ticked in settings")
            return

        # Pre-check: Ensure symbol market is open and tradeable before evaluating
        is_tradeable, reason = self.mt5.is_symbol_tradeable(signal.symbol)
        if not is_tradeable:
            logger.debug(f"⏳ [MARKET INACTIVE] Skipping signal for {signal.symbol}: {reason}")
            return

        # Calendar gate: is this a good time to trade this symbol?
        from quantclaw.market_calendar import MarketCalendar
        _cal = MarketCalendar()
        if not _cal.is_market_open(signal.symbol):
            logger.debug(f"🗓 [MARKET CLOSED] {signal.symbol} market is closed right now")
            return

        # Check News Shield: Block new trade if high-impact economic news is active
        if getattr(self.config, "enable_news_filter", True) and hasattr(self.news, "is_news_blocked"):
            is_blocked, news_reason = self.news.is_news_blocked(signal.symbol)
            if is_blocked:
                logger.warning(f"📰 [NEWS SHIELD] Blocking signal on {signal.symbol}: {news_reason}")
                return

        # 1. Score with ML Brain
        news_sentiment = self.news.get_sentiment(signal.symbol)
        decision = self.ml.evaluate_signal(signal, news_sentiment)

        logger.info(
            f"🧠 [ML EVAL] {signal.symbol} {signal.action.upper()} | {signal.strategy.upper()} | "
            f"Score: {decision.ml_score:.1f}/100 -> {'APPROVED 🟢' if decision.approved else 'REJECTED 🔴'}"
        )

        if not decision.approved:
            return

        # Block signal if ANY open position exists on this symbol (same OR opposite direction)
        # Prevents: duplicate same-direction positions AND conflicting hedge positions
        # On prop firm netting accounts, an opposite trade partially closes/flips the existing one.
        open_positions = self.risk.get_all_active_positions()
        import re as _re
        _sym_clean = lambda s: _re.sub(r'[\._][a-zA-Z0-9]*$', '', str(s)).rstrip('._').upper()
        dec_sym_base = _sym_clean(decision.symbol)
        existing_on_symbol = [
            p for p in open_positions
            if _sym_clean(p.get('symbol', '')) == dec_sym_base
        ]
        if existing_on_symbol:
            logger.debug(
                f"⏸ [POSITION EXISTS] Skipping {decision.symbol} {decision.action.upper()} "
                f"— already have {len(existing_on_symbol)} open position(s) on this symbol"
            )
            return

        # 2. Execute on MT5 via Risk Manager
        if self._async_loop and self._async_loop.is_running():
            logger.info(f"🚀 [ORDER DISPATCH] Punching trade on MT5 for {decision.symbol} ({decision.action})...")
            asyncio.run_coroutine_threadsafe(
                self.risk.execute_trade_decision(decision), self._async_loop
            )


    def _on_settings_applied(self, settings: Dict[str, Any]) -> None:
        """Called when settings are updated from the web dashboard."""
        logger.info(f"⚙️ Settings reloaded: {list(settings.keys())}")
        if "mt5_login" in settings or "mt5_password" in settings or "mt5_server" in settings:
            # Check if already connected to desired account to avoid unnecessary reconnects
            acc = self.mt5.get_account_info()
            desired_login = int(self.config.mt5_login or 0)
            if acc and acc.login == desired_login and desired_login > 0:
                logger.info(f"Already connected to Account #{desired_login}, skipping reconnect.")
            else:
                def _reconnect():
                    try:
                        self.mt5.connect(
                            login=self.config.mt5_login,
                            password=self.config.mt5_password,
                            server=self.config.mt5_server,
                            path=self.config.mt5_path,
                        )
                    except Exception as e:
                        logger.error(f'Failed to reconnect MT5: {e}')
                threading.Thread(target=_reconnect, daemon=True).start()

        if "anthropic_api_key" in settings:
            self.ai.update_api_key(self.config.anthropic_api_key)

    def start_background_tasks(self) -> None:
        """Start async background event loop for Market & Risk engines."""
        def _runner():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._async_loop = loop

            # Initial MT5 connection
            self.mt5.connect()

            # Parse active symbols safely (supports List[str] or comma-separated str)
            trade_syms = self.config.trade_symbols
            if isinstance(trade_syms, list):
                raw_symbols = [str(s).strip().upper() for s in trade_syms if str(s).strip()]
            elif isinstance(trade_syms, str):
                raw_symbols = [s.strip().upper() for s in trade_syms.split(",") if s.strip()]
            else:
                raw_symbols = []

            # Ask MT5 to auto-discover and match available symbols on the connected broker
            symbols = self.mt5.auto_discover_symbols(raw_symbols) if hasattr(self.mt5, "auto_discover_symbols") else raw_symbols
            if not symbols:
                symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "US30", "NAS100"]

            async def _main_tasks():
                await self.market.start(symbols)
                news_task = asyncio.create_task(self.news.run())
                news_task.add_done_callback(lambda t: logger.error(f'News task ended: {t.exception()}') if not t.cancelled() and t.exception() else None)

                # Self-improvement analysis task (runs every 2 hours)
                async def _run_improvement_analysis():
                    while True:
                        try:
                            await asyncio.sleep(7200)  # Every 2 hours
                            if self.journal:
                                suggestions = await asyncio.to_thread(self.journal.analyze_for_improvements)
                                if suggestions:
                                    await asyncio.to_thread(self.journal.save_improvement_suggestions, suggestions)
                                    logger.info(f"🔍 [SELF-IMPROVEMENT] Generated {len(suggestions)} improvement insights:")
                                    for s in suggestions[:5]:  # Log top 5 to dashboard log
                                        priority_emoji = {'HIGH': '🔴', 'MEDIUM': '🟡', 'LOW': '🟢'}.get(s['priority'], '📋')
                                        logger.warning(f"{priority_emoji} [UPDATE NEEDED] {s['suggestion']}")
                        except Exception as e:
                            logger.debug(f"Improvement analysis error: {e}")
                
                improve_task = asyncio.create_task(_run_improvement_analysis())
                improve_task.add_done_callback(
                    lambda t: logger.error(f'Improvement task ended: {t.exception()}') 
                    if not t.cancelled() and t.exception() else None
                )

                # Run initial improvement analysis on startup (after 30s warmup)
                async def _startup_analysis():
                    await asyncio.sleep(30)
                    try:
                        if self.journal:
                            suggestions = await asyncio.to_thread(self.journal.analyze_for_improvements)
                            if suggestions:
                                await asyncio.to_thread(self.journal.save_improvement_suggestions, suggestions)
                                logger.info("🔍 [STARTUP ANALYSIS] Bot self-improvement suggestions:")
                                for s in suggestions:
                                    priority_emoji = {'HIGH': '🔴', 'MEDIUM': '🟡', 'LOW': '🟢'}.get(s['priority'], '📋')
                                    logger.warning(f"{priority_emoji} [UPDATE NEEDED] {s['suggestion']}")
                    except Exception as e:
                        logger.debug(f"Startup analysis error: {e}")
                asyncio.create_task(_startup_analysis())

                # Autonomous Strategy Tester / Permutation Auto-Tuning (runs every 30 mins)
                async def _run_strategy_tester_autotune():
                    await asyncio.sleep(45)
                    while True:
                        try:
                            if getattr(self.config, 'enable_strategy_tester_autotune', True) and symbols:
                                for test_sym in symbols[:5]:
                                    if not self.config.is_symbol_enabled(test_sym):
                                        continue
                                    res = await asyncio.to_thread(self.strategy_tester.run_permutation_optimizer, test_sym, "M15", 300)
                                    best = res.get("best_permutation")
                                    if best and best.get("expectancy", 0) > 0.1:
                                        optimal_lookback = best.get("lookback")
                                        optimal_rr = best.get("rr")
                                        logger.info(
                                            f"[AUTONOMOUS AUTO-TUNE] Applied optimal parameters for {test_sym}: "
                                            f"Lookback={optimal_lookback}, Target R:R={optimal_rr}R, Expectancy=+{best.get('expectancy')}R, WinRate={best.get('win_rate')}%, PF={best.get('profit_factor')}"
                                        )
                                        if test_sym == symbols[0]:
                                            self.config.titan_pro_swing_lookback = optimal_lookback
                                            self.config.titan_pro_rr_ratio = optimal_rr
                                            if getattr(self.config, 'stepped_trail_auto_mode', True):
                                                self.config.stepped_trail_zone3_r = optimal_rr
                                            self.config.save_to_json()
                        except Exception as e:
                            logger.debug(f"Strategy tester background error: {e}")
                        await asyncio.sleep(1800)

                tester_task = asyncio.create_task(_run_strategy_tester_autotune())
                tester_task.add_done_callback(
                    lambda t: logger.error(f'Strategy tester task ended: {t.exception()}') 
                    if not t.cancelled() and t.exception() else None
                )

                scan_ticker = 0
                while True:
                    try:
                        # ── Network Guardian & Auto-Recovery ───────────────────
                        if not self.mt5.is_connected():
                            logger.warning("⚠️ [NETWORK GUARDIAN] MT5 connection interrupted. Waiting for network and attempting auto-recovery...")
                            reconnected = False
                            for attempt in range(1, 4):
                                ok, msg = await asyncio.to_thread(self.mt5.reconnect, 1)
                                if ok:
                                    logger.info(f"✅ [NETWORK RECOVERED] Connection restored ({msg})! Resynchronizing positions and recovering trade control.")
                                    reconnected = True
                                    break
                                await asyncio.sleep(2.0)
                            if not reconnected:
                                await asyncio.sleep(3.0)
                                continue

                        await self.account_tracker.poll_account()
                        # Re-discover symbols if account switched (broker may use different symbol names)
                        if self.account_tracker.check_and_clear_account_switch():
                            self.risk.reset_circuit_breaker()  # Clear any pause caused by prior account differences
                            logger.warning("\U0001f504 [SYMBOL REDISCOVERY] Account switched — re-discovering symbols for new broker...")
                            raw_symbols_for_rediscovery = self.config.trade_symbols
                            if isinstance(raw_symbols_for_rediscovery, list):
                                raw_for_rediscovery = [str(s).strip().upper() for s in raw_symbols_for_rediscovery if str(s).strip()]
                            elif isinstance(raw_symbols_for_rediscovery, str):
                                raw_for_rediscovery = [s.strip().upper() for s in raw_symbols_for_rediscovery.split(",") if s.strip()]
                            else:
                                raw_for_rediscovery = []
                            new_symbols = self.mt5.auto_discover_symbols(raw_for_rediscovery) if hasattr(self.mt5, "auto_discover_symbols") else raw_for_rediscovery
                            if new_symbols:
                                symbols[:] = new_symbols  # Update in-place so the scan loop uses new symbols
                                logger.info(f"\u2705 [SYMBOL REDISCOVERY] New symbol list: {new_symbols}")
                                await self.market.set_symbols(new_symbols)  # Update market engine with new symbols
                        await self.risk.monitor_open_positions()

                        scan_ticker += 1
                        if scan_ticker % 5 == 0:
                            acc = self.account_tracker.get_live_state()
                            status_str = "ARMED 🟢" if self.config.armed else "DISARMED 🔴"
                            logger.info(
                                f"📡 [SCAN 24/7] State: {status_str} | Equity: ${acc.get('equity', 0):.2f} | "
                                f"Monitoring: {len(symbols)} active pairs ({', '.join(symbols[:3])}...)"
                            )
                            # Strategy Matrix Scan: run in thread pool to avoid blocking the event loop
                            # (21 scans × 5 strategies = 105 CPU-bound calculations previously blocked
                            # monitor_open_positions and execute_trade_decision coroutines)
                            if self.config.armed and self.config.enable_autonomous_trading:
                                def _do_strategy_scan():
                                    for sym in symbols:
                                        # Skip symbols the user has disabled in settings
                                        if not self.config.is_symbol_enabled(sym):
                                            continue
                                        is_tradeable, reason = self.mt5.is_symbol_tradeable(sym)
                                        if not is_tradeable:
                                            logger.debug(f"Skipping scan for {sym}: {reason}")
                                            continue
                                        try:
                                            self.strategy.scan_symbol(sym, "M15")
                                            self.strategy.scan_symbol(sym, "M5")
                                            self.strategy.scan_symbol(sym, "H1")
                                        except Exception as scan_err:
                                            logger.debug(f"Periodic scan error for {sym}: {scan_err}")
                                asyncio.create_task(asyncio.to_thread(_do_strategy_scan))

                    except Exception as e:
                        logger.error(f"Monitor loop exception: {e}", exc_info=True)
                    await asyncio.sleep(float(getattr(self.config, 'monitor_cycle_seconds', 1.0)))


            try:
                loop.run_until_complete(_main_tasks())
            except Exception as e:
                logger.debug(f"Async loop terminated: {e}")
            finally:
                loop.close()

        t = threading.Thread(target=_runner, daemon=True, name="QuantClaw-AsyncEngine")
        t.start()

    def run(self) -> None:
        """Launch the application."""
        # 1. Initialize Qt Application early on main thread
        app = QApplication.instance() or QApplication(sys.argv)

        # 2. Start backend server
        self.server_runner.start()

        # 3. Wait for server to bind and respond before opening browser
        port = self.config.server_port
        import urllib.request
        logger.info(f"⏳ Waiting for telemetry server on http://127.0.0.1:{port}...")
        for attempt in range(25):
            app.processEvents()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v4/health", timeout=0.3) as r:
                    if r.status == 200:
                        logger.info(f"✅ Telemetry server online on port {port}")
                        break
            except Exception:
                time.sleep(0.15)
                app.processEvents()

        # 4. Start 24/7 background market & risk loops
        self.start_background_tasks()

        # 5. Launch PyQt6 Fullscreen WebEngine
        url = f"http://127.0.0.1:{port}/dashboard"
        window = FullscreenWebWindow(url=url, config=self.config)
        window.show()

        try:
            sys.exit(app.exec())
        finally:
            self.server_runner.stop()
            if hasattr(self, 'market') and self.market:
                try:
                    self.market._running = False  # Signal stop without async teardown
                    if self.market._poll_task:
                        self.market._poll_task.cancel()
                except Exception:
                    pass
            self.mt5.disconnect()


def main():
    multiprocessing.freeze_support()
    app = QuantClawMT5App()
    app.run()


if __name__ == "__main__":
    main()

