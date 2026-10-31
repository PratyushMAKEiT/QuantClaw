# ==============================================================================
# quantclaw/server.py — FastAPI Backend & Telemetry Server (MetaTrader 5)
# ==============================================================================
"""
FastAPI REST API server for QuantClaw MT5.
Serves the local PyQt6 / browser Telemetry Dashboard and exposes high-performance
endpoints for MT5 account telemetry, positions, signals, trade journal, and settings hot-reload.
"""

from __future__ import annotations

import asyncio
import re
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request, Query, Depends, Security
from fastapi.security.api_key import APIKeyQuery
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from quantclaw.utils.logger import get_logger, get_recent_logs
from quantclaw.dashboard import get_dashboard_html
from quantclaw.strategy_tester import StrategyTester
from quantclaw.market_thinking import MarketThinkingEngine

logger = get_logger("server")


def create_app(
    config: Any,
    mt5_client: Any,
    market_engine: Any,
    strategy_engine: Any,
    ml_engine: Any,
    ai_engine: Any,
    risk_manager: Any,
    account_tracker: Any,
    trade_journal: Any,
    news_monitor: Any,
    on_settings_applied: Optional[Callable[[Dict[str, Any]], None]] = None,
    strategy_tester: Any = None,
    thinking_engine: Any = None,
) -> FastAPI:
    """Factory creating configured FastAPI app for MetaTrader 5."""

    app = FastAPI(title="QuantClaw MT5 Backend", version="v4.5")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.config = config
    app.state.mt5 = mt5_client
    app.state.market = market_engine
    app.state.strategy = strategy_engine
    app.state.ml = ml_engine
    app.state.ai = ai_engine
    app.state.risk = risk_manager
    app.state.account = account_tracker
    app.state.journal = trade_journal
    app.state.news = news_monitor
    app.state.on_settings_applied = on_settings_applied
    app.state.strategy_tester = strategy_tester or StrategyTester(config, mt5_client, market_engine)
    app.state.thinking_engine = thinking_engine or MarketThinkingEngine(config, market_engine, risk_manager)

    # In-memory log cache for dashboard terminal
    app.state.log_cache: List[str] = []

    async def _verify_token(token: str = Query(default="")):
        """Validate webhook token on all API calls."""
        if config.webhook_token and token != config.webhook_token:
            raise HTTPException(status_code=403, detail="Invalid or missing token")


    # ── UI Dashboard ───────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    @app.get("/dashboard", response_class=HTMLResponse)
    @app.get("/lasthopepanel", response_class=HTMLResponse)
    @app.get("/lasthopepanel/", response_class=HTMLResponse)
    @app.get("/lasthopepanel/dashboard", response_class=HTMLResponse)
    async def get_dashboard(request: Request):
        return HTMLResponse(content=get_dashboard_html(token=config.webhook_token, port=config.server_port))

    # ── Core Status & Telemetry ────────────────────────────────────────────────

    @app.get("/api/status")
    @app.get("/lasthopepanel/api/status")
    async def get_status():
        acc = account_tracker.get_live_state() if account_tracker else {}
        is_connected = bool(acc.get("connected", False))

        positions = []
        if mt5_client and is_connected:
            try:
                positions = await asyncio.to_thread(mt5_client.get_positions)
            except Exception:
                positions = []

        logs = get_recent_logs(80)
        diag = ml_engine.get_diagnostics() if ml_engine else {}
        headlines = news_monitor.get_headlines(limit=5) if news_monitor else []
        headline_titles = [h.get("title", "") if isinstance(h, dict) else str(h) for h in headlines]
        sentiment = news_monitor.get_global_sentiment() if news_monitor else 0.0

        daily_dd = account_tracker.get_daily_loss_pct() if account_tracker else 0.0

        # High-impact macro check
        high_impact = False
        if news_monitor and hasattr(news_monitor, "is_high_impact_window"):
            high_impact = bool(news_monitor.is_high_impact_window())

        # Regime from ML
        ml_score = diag.get("decision_score", 100.0)
        if ml_score >= 82:
            live_regime = "GAMMA"
        elif ml_score >= 68:
            live_regime = "BETA"
        else:
            live_regime = "ALPHA"

        # Thinking status
        if config.armed and config.enable_autonomous_trading:
            thinking = "24/7 Strategy Matrix Active — SCANNING"
        elif config.armed:
            thinking = "Armed — Manual Mode"
        else:
            thinking = "Disarmed — Standby"

        return {
            "status": "RUNNING",
            "active_profile": "MT5_PRO_MULTI_ENGINE",

            "account": acc,
            "positions": positions,
            "positions_count": len(positions),
            "total_trades": len(positions),
            "armed": config.armed,
            "connected": is_connected,
            "autonomous": config.enable_autonomous_trading,
            "autonomous_trading": config.enable_autonomous_trading,
            "autotrading_allowed": acc.get("trade_expert", False),
            "trade_allowed": acc.get("trade_allowed", False),
            "ml_diagnostics": diag,
            "recent_signals": strategy_engine.get_recent_signals() if strategy_engine else [],
            "macro_sentiment": sentiment,
            "news_sentiment": sentiment,
            "high_impact_macro": high_impact,
            "top_headlines": headline_titles,
            "news_headlines": headline_titles,
            "daily_drawdown_pct": round(daily_dd, 2),
            "margin_level": acc.get("margin_level", 0.0),
            "today_pnl": acc.get("today_pnl", 0.0),
            "session_pnl": acc.get("today_pnl", 0.0),
            "logs": logs,
            "recent_logs": logs,
            "regime": live_regime,
            "volume_regime": (market_engine.get_volume_regime(config.trade_symbols[0] if config.trade_symbols else "EURUSD").get("regime", "NORMAL_VOLUME") if market_engine and hasattr(market_engine, "get_volume_regime") else "NORMAL_VOLUME"),
            "thinking_status": thinking,
            "decision_score": ml_score,
            "decision_status": diag.get("decision_status", "Going smooth"),
            "login": acc.get("login", 0),
            "server": acc.get("server", "--"),
            "balance": acc.get("balance", 0.0),
            "equity": acc.get("equity", 0.0),
            "floating_pnl": acc.get("floating_pnl", 0.0),
            "currency": acc.get("currency", "USD"),
            "status_message": f"MT5 {'Connected' if is_connected else 'Disconnected'} | {len(positions)} Active Trades",
            "timestamp": time.time(),
        }



    @app.post("/api/arm", dependencies=[Depends(_verify_token)])
    @app.post("/api/toggle-arm", dependencies=[Depends(_verify_token)])
    @app.post("/lasthopepanel/api/arm")
    @app.post("/lasthopepanel/api/toggle-arm")
    async def post_arm(request: Request):
        try:
            new_state = None
            if "armed" in request.query_params:
                new_state = request.query_params["armed"].lower() in ["true", "1", "yes"]
            if new_state is None:
                try:
                    data = await request.json()
                    if "armed" in data:
                        new_state = bool(data["armed"])
                except Exception:
                    pass
            if new_state is None:
                new_state = not config.armed

            config.armed = new_state
            if new_state and risk_manager:
                risk_manager.reset_circuit_breaker()
            config.save()
            logger.info(f"Master State Changed: {'ARMED 🟢' if new_state else 'DISARMED 🔴'}")
            return {"success": True, "armed": config.armed}
        except Exception as e:
            return {"success": False, "error": str(e), "armed": config.armed}

    # ── MT5 Account, Positions & Orders ───────────────────────────────────────

    @app.post("/api/mt5/connect", dependencies=[Depends(_verify_token)])
    @app.post("/lasthopepanel/api/mt5/connect")
    async def post_mt5_connect(request: Request):
        if not mt5_client:
            return {"success": False, "error": "MT5 Client not initialized"}
        try:
            body = await request.json()
            login = int(body.get("login", config.mt5_login) or 0)
            password = body.get("password", config.mt5_password) or ""
            server = body.get("server", config.mt5_server) or ""
            path = body.get("path", config.mt5_path) or ""

            if "********" in password:
                password = config.mt5_password

            succ, msg = await asyncio.to_thread(
                mt5_client.connect, login=login, password=password, server=server, path=path
            )
            
            if succ:
                if login > 0:
                    config.mt5_login = login
                if password:
                    config.mt5_password = password
                if server:
                    config.mt5_server = server
                if path:
                    config.mt5_path = path
                config.save()

            if account_tracker:
                try:
                    await account_tracker.poll_account()
                except Exception:
                    pass
            
            # If successful, restart market polling for symbols
            if succ and market_engine:
                trade_syms = config.trade_symbols
                if isinstance(trade_syms, list):
                    symbols = [str(s).strip().upper() for s in trade_syms if str(s).strip()]
                elif isinstance(trade_syms, str):
                    symbols = [s.strip().upper() for s in trade_syms.split(",") if s.strip()]
                else:
                    symbols = []
                if not symbols:
                    symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "US30", "NAS100"]
                active_symbols = mt5_client.auto_discover_symbols(symbols) if hasattr(mt5_client, "auto_discover_symbols") else symbols
                if hasattr(market_engine, "set_symbols") and getattr(market_engine, "_running", False):
                    asyncio.create_task(market_engine.set_symbols(active_symbols))
                else:
                    asyncio.create_task(market_engine.start(active_symbols))


            return {"success": succ, "message": msg, "connected": mt5_client.is_connected()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/v4/account")
    @app.get("/api/mt5/account")
    @app.get("/lasthopepanel/api/v4/account")
    @app.get("/lasthopepanel/api/mt5/account")
    async def get_mt5_account():
        if not account_tracker:
            return {}
        await account_tracker.poll_account()
        return account_tracker.get_live_state()

    @app.get("/api/positions")
    @app.get("/api/mt5/positions")
    @app.get("/lasthopepanel/api/positions")
    @app.get("/lasthopepanel/api/mt5/positions")
    async def get_mt5_positions():
        if not mt5_client:
            return {"positions": [], "count": 0}
        try:
            positions = await asyncio.to_thread(mt5_client.get_positions)
            return {"positions": positions, "count": len(positions)}
        except Exception as e:
            return {"positions": [], "count": 0, "error": str(e)}

    @app.get("/api/mt5/orders")
    @app.get("/lasthopepanel/api/mt5/orders")
    async def get_mt5_orders():
        if not mt5_client:
            return {"orders": [], "count": 0}
        try:
            orders = await asyncio.to_thread(mt5_client.get_pending_orders)
            return {"orders": orders, "count": len(orders)}
        except Exception as e:
            return {"orders": [], "count": 0, "error": str(e)}

    @app.post("/api/close-position", dependencies=[Depends(_verify_token)])
    @app.post("/api/mt5/close-position")
    @app.post("/lasthopepanel/api/close-position")
    @app.post("/lasthopepanel/api/mt5/close-position")
    async def post_close_position(request: Request):
        try:
            ticket = 0
            if "ticket" in request.query_params:
                try:
                    ticket = int(request.query_params["ticket"])
                except Exception:
                    pass
            if not ticket:
                try:
                    data = await request.json()
                    ticket = int(data.get("ticket", 0))
                except Exception:
                    pass
            if not ticket:
                return {"success": False, "error": "Missing position ticket"}

            succ, msg = await asyncio.to_thread(mt5_client.close_position, ticket)
            return {"success": succ, "message": msg}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/mt5/breakeven")
    @app.post("/api/breakeven")
    @app.post("/lasthopepanel/api/mt5/breakeven")
    @app.post("/lasthopepanel/api/breakeven")
    async def post_breakeven(request: Request):
        try:
            ticket = 0
            if "ticket" in request.query_params:
                try:
                    ticket = int(request.query_params["ticket"])
                except Exception:
                    pass
            if not ticket:
                try:
                    data = await request.json()
                    ticket = int(data.get("ticket", 0))
                except Exception:
                    pass
            if not ticket:
                return {"success": False, "error": "Missing ticket"}

            # Get the position's open price first, then set SL to it (true breakeven)
            positions = await asyncio.to_thread(mt5_client.get_positions) if mt5_client else []
            pos = next((p for p in positions if p.get('ticket') == int(ticket)), None)
            if not pos:
                return {"success": False, "error": "Position not found"}
            entry_price = pos.get('open_price', 0.0)
            current_tp = pos.get('tp', 0.0)
            if entry_price <= 0:
                return {"success": False, "error": "Cannot determine entry price"}
            succ, msg = await asyncio.to_thread(mt5_client.modify_position, int(ticket), entry_price, current_tp)
            return {"success": succ, "message": msg}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/flatten", dependencies=[Depends(_verify_token)])
    @app.post("/api/mobile/flatten")
    @app.post("/api/mt5/flatten")
    @app.post("/lasthopepanel/api/flatten")
    @app.post("/lasthopepanel/api/mobile/flatten")
    @app.post("/lasthopepanel/api/mt5/flatten")
    async def post_flatten_all():
        if not mt5_client:
            return {"success": False, "message": "MT5 client unavailable", "closed_count": 0}
        bot_magic = int(getattr(config, "mt5_magic_number", 999111)) if getattr(config, "ignore_manual_trades", True) else None
        closed, errors = await asyncio.to_thread(mt5_client.close_all_positions, only_magic=bot_magic)
        return {
            "success": True,
            "message": f"Flatten complete ({closed} positions closed)",
            "closed_count": closed,
            "error_count": errors,
        }

    @app.post("/api/set-profile")
    @app.post("/lasthopepanel/api/set-profile")
    async def post_set_profile(request: Request):
        profile = request.query_params.get("profile", "MT5_PRO")
        return {"success": True, "profile_override": profile}

    # ── Signals, History & Market Feeds ───────────────────────────────────────

    @app.get("/api/v4/candles/{symbol}/{timeframe}")
    @app.get("/lasthopepanel/api/v4/candles/{symbol}/{timeframe}")
    async def get_candles_route(symbol: str, timeframe: str, limit: int = 100):
        if not market_engine:
            return {"candles": []}
        candles = market_engine.get_candles(symbol, timeframe, limit)
        return {"candles": candles, "symbol": symbol, "timeframe": timeframe}

    @app.get("/api/v4/signals")
    @app.get("/lasthopepanel/api/v4/signals")
    async def get_signals_route():
        if not strategy_engine:
            return {"signals": []}
        return {"signals": strategy_engine.get_recent_signals(50)}

    @app.get("/api/trades")
    @app.get("/lasthopepanel/api/trades")
    async def get_trades_route_android(limit: int = 30):
        if not trade_journal:
            return []
        trades = trade_journal.get_recent_trades(limit)
        formatted = []
        for t in trades:
            pnl = float(t.get("pnl_usd") or 0.0)
            formatted.append({
                "id": str(t.get("id") or t.get("ticket") or ""),
                "status": "CLOSED",
                "entry_price": float(t.get("entry_price") or 0.0),
                "quantity": float(t.get("volume") or t.get("lots") or 0.0),
                "received_at": float(t.get("open_time") or 0.0),
                "executed_at": float(t.get("open_time") or 0.0),
                "closed_at": float(t.get("close_time") or 0.0),
                "realized_pnl": pnl,
                "trading_fee_usd": float(t.get("commission") or 0.0),
                "delta_india_total_cost_usd": 0.0,
                "net_pnl_usd": pnl,
                "signal": {
                    "symbol": t.get("symbol", ""),
                    "action": t.get("action", "BUY")
                },
                "decision": {
                    "regime": t.get("strategy", "INSTITUTIONAL_SMC"),
                    "confidence": int(t.get("ml_score") or 85),
                    "reasoning": t.get("reason", "Strategy Signal")
                }
            })
        return formatted

    @app.get("/api/v4/journal")
    @app.get("/lasthopepanel/api/v4/journal")
    async def get_journal_route(limit: int = 30):
        if not trade_journal:
            return {"trades": []}
        trades = trade_journal.get_recent_trades(limit)
        return {"trades": trades}

    @app.get("/api/v4/performance")
    @app.get("/lasthopepanel/api/v4/performance")
    async def get_performance_route():
        """Return aggregated trading performance statistics from the journal."""
        if not trade_journal:
            return {"error": "Journal not available"}
        if hasattr(trade_journal, "get_performance_stats"):
            return trade_journal.get_performance_stats()
        # Fallback: compute from recent trades
        trades = trade_journal.get_recent_trades(200)
        if not trades:
            return {"total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "avg_rr": 0.0}
        wins = [t for t in trades if float(t.get("pnl_usd", 0)) > 0]
        losses = [t for t in trades if float(t.get("pnl_usd", 0)) <= 0]
        total_win = sum(float(t.get("pnl_usd", 0)) for t in wins)
        total_loss = abs(sum(float(t.get("pnl_usd", 0)) for t in losses))
        return {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
            "profit_factor": round(total_win / total_loss, 2) if total_loss > 0 else 0.0,
            "total_pnl": round(total_win - total_loss, 2),
            "avg_win": round(total_win / len(wins), 2) if wins else 0.0,
            "avg_loss": round(-total_loss / len(losses), 2) if losses else 0.0,
            "avg_rr": round((total_win / len(wins)) / (total_loss / len(losses)), 2) if wins and losses else 0.0,
        }

    @app.post("/api/mt5/order", dependencies=[Depends(_verify_token)])
    @app.post("/lasthopepanel/api/mt5/order")
    async def post_manual_order(request: Request):
        """Place a manual market order from the dashboard."""
        if not mt5_client:
            return {"success": False, "error": "MT5 not connected"}
        try:
            body = await request.json()
            symbol = str(body.get("symbol", "")).strip().upper()
            action = str(body.get("action", "")).strip().upper()
            lots = float(body.get("lots", 0.01))
            sl = float(body.get("sl", 0.0))
            tp = float(body.get("tp", 0.0))
            if not symbol or action not in ("BUY", "SELL"):
                return {"success": False, "error": "Invalid symbol or action (must be BUY or SELL)"}
            success, res = await asyncio.to_thread(
                mt5_client.open_market_order,
                symbol=symbol, action=action, volume=lots, sl=sl, tp=tp,
                comment="QuantClaw Manual", magic=int(getattr(config, "mt5_magic_number", 999111))
            )
            return {"success": success, "result": res}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/mt5/partial-close", dependencies=[Depends(_verify_token)])
    @app.post("/lasthopepanel/api/mt5/partial-close")
    async def post_partial_close(request: Request):
        """Close a specific volume of an open position."""
        if not mt5_client:
            return {"success": False, "error": "MT5 not connected"}
        try:
            body = await request.json()
            ticket = int(body.get("ticket", 0))
            volume = float(body.get("volume", 0.0))
            if not ticket or volume <= 0:
                return {"success": False, "error": "Invalid ticket or volume"}
            success, msg = await asyncio.to_thread(mt5_client.close_position, ticket, volume)
            return {"success": success, "message": msg}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/v4/equity-history")
    @app.get("/lasthopepanel/api/v4/equity-history")
    async def get_equity_history_route(days: int = 7):
        if not trade_journal:
            return {"history": []}
        history = trade_journal.get_equity_history(days)
        return {"history": history}

    @app.get("/api/v4/diagnostics")
    @app.get("/lasthopepanel/api/v4/diagnostics")
    async def get_diagnostics_route():
        if not ml_engine:
            return {}
        return ml_engine.get_diagnostics()

    @app.get("/api/v4/discussions")
    @app.get("/lasthopepanel/api/v4/discussions")
    async def get_discussions_route():
        if not ai_engine:
            return {"discussions": []}
        return {"discussions": ai_engine.get_recent_discussions()}

    @app.get("/api/v4/news")
    @app.get("/lasthopepanel/api/v4/news")
    async def get_news_route():
        if not news_monitor:
            return {"headlines": [], "global_score": 0.0, "global_sentiment": 0.0}
        sent = news_monitor.get_global_sentiment()
        return {
            "headlines": news_monitor.get_headlines(limit=15),
            "global_score": sent,
            "global_sentiment": sent,
            "high_impact_window": news_monitor.is_high_impact_window() if hasattr(news_monitor, "is_high_impact_window") else False,
        }


    @app.get("/api/v4/logs")
    @app.get("/lasthopepanel/api/v4/logs")
    async def get_logs_route(limit: int = 80):
        logs = get_recent_logs(limit)
        return {"logs": logs}

    # ── AI Thinking & Possibility Permutations ────────────────────────────────
    @app.get("/api/v4/thinking")
    @app.get("/lasthopepanel/api/v4/thinking")
    async def get_thinking_route(symbol: str = ""):
        te = getattr(app.state, "thinking_engine", None)
        if not te:
            return {"thinking": []}
        active_syms = config.get_active_symbols() if hasattr(config, "get_active_symbols") else config.trade_symbols
        syms_to_check = [symbol.strip().upper()] if symbol else active_syms[:8]
        data = await asyncio.to_thread(te.get_all_thinking, syms_to_check)
        return {"thinking": data, "count": len(data), "timestamp": time.time()}

    @app.get("/api/v4/thinking/permutations")
    @app.get("/lasthopepanel/api/v4/thinking/permutations")
    async def get_thinking_permutations_route(symbol: str = "EURUSD", timeframe: str = "M15"):
        te = getattr(app.state, "thinking_engine", None)
        if not te:
            return {"symbol": symbol, "narrative": "Initializing...", "permutations": []}
        return await asyncio.to_thread(te.generate_symbol_thinking, symbol.strip().upper(), timeframe)

    @app.get("/api/v4/thinking/summary")
    @app.get("/lasthopepanel/api/v4/thinking/summary")
    async def get_thinking_summary_route():
        te = getattr(app.state, "thinking_engine", None)
        if not te:
            return {"symbols": [], "in_trade_supervision": []}
        return await asyncio.to_thread(te.get_all_symbols_summary)

    # Strategy Tester / Time-Machine Optimizer
    @app.post("/api/v4/strategy-tester/run")
    @app.post("/api/v4/strategy-tester/tune")
    @app.post("/lasthopepanel/api/v4/strategy-tester/run")
    @app.post("/lasthopepanel/api/v4/strategy-tester/tune")
    async def run_strategy_tester_route(request: Request):
        st = getattr(app.state, "strategy_tester", None)
        if not st:
            return {"success": False, "error": "Strategy Tester not initialized"}
        try:
            body = await request.json()
        except Exception:
            body = {}
        symbol = str(body.get("symbol", config.trade_symbols[0] if config.trade_symbols else "EURUSD")).strip().upper()
        strategy = str(body.get("strategy", "titan_pro")).lower().replace(" ", "_")
        if "smc" in strategy:
            strategy = "smc_liquidity"
        else:
            strategy = "titan_pro"
        timeframe = str(body.get("timeframe", "M15"))
        bars = int(body.get("bars", 300))
        result = await asyncio.to_thread(st.run_permutation_optimizer, symbol, timeframe, strategy=strategy, bars=bars)
        return result

    @app.get("/api/v4/strategy-tester/results")
    @app.get("/api/v4/strategy-tester/status")
    @app.get("/lasthopepanel/api/v4/strategy-tester/results")
    @app.get("/lasthopepanel/api/v4/strategy-tester/status")
    async def get_strategy_tester_results_route():
        st = getattr(app.state, "strategy_tester", None)
        if not st:
            return {"results": {}, "status": "idle"}
        res = st.get_latest_results()
        return {"status": "ready", "results": res}

    # ── Settings Hot-Reload ───────────────────────────────────────────────────

    @app.get("/api/v4/settings")
    @app.get("/lasthopepanel/api/v4/settings")
    async def get_settings_route():
        cfg = config
        return {
            "mt5_login": cfg.mt5_login,
            "mt5_password": "********" if cfg.mt5_password else "",
            "mt5_server": cfg.mt5_server,
            "mt5_path": cfg.mt5_path,
            "mt5_magic_number": cfg.mt5_magic_number,
            "armed": cfg.armed,
            "enable_autonomous_trading": cfg.enable_autonomous_trading,
            "trade_sizing_mode": cfg.trade_sizing_mode,
            "risk_per_trade_pct": cfg.risk_per_trade_pct,
            "trade_symbols": cfg.trade_symbols,
            "symbol_quantities": cfg.symbol_quantities,
            "max_spread_points": cfg.max_spread_points,
            "strategy_smc_enabled": cfg.strategy_smc_enabled,
            "strategy_occ_r5_enabled": cfg.strategy_occ_r5_enabled,
            "strategy_eyes_sme_enabled": cfg.strategy_eyes_sme_enabled,
            "strategy_mean_rev_enabled": cfg.strategy_mean_rev_enabled,
            "strategy_quant_way_enabled": cfg.strategy_quant_way_enabled,
            "enable_ml_brain": cfg.enable_ml_brain,
            "ml_brain_min_execute_score": cfg.ml_brain_min_execute_score,
            "ml_brain_confluence_bonus": cfg.ml_brain_confluence_bonus,
            "anthropic_api_key": "********" if cfg.anthropic_api_key else "",
            "anthropic_model": cfg.anthropic_model,
            "daily_max_loss_pct": cfg.daily_max_loss_pct,
            "weekly_profit_target_pct": cfg.weekly_profit_target_pct,
            "max_concurrent_positions": cfg.max_concurrent_positions,
            "enable_partial_take_profit": cfg.enable_partial_take_profit,
            "enable_breakeven_trigger": cfg.enable_breakeven_trigger,
            "enable_trailing_stop": cfg.enable_trailing_stop,
            "stepped_trail_auto_mode": getattr(cfg, "stepped_trail_auto_mode", True),
            "enable_constant_trailing": getattr(cfg, "enable_constant_trailing", True),
            "enable_auto_pilot_tuning": getattr(cfg, "enable_auto_pilot_tuning", True),
            "enable_strategy_tester_autotune": getattr(cfg, "enable_strategy_tester_autotune", True),
            "server_port": cfg.server_port,
        }

    @app.post("/api/v4/settings", dependencies=[Depends(_verify_token)])
    @app.post("/lasthopepanel/api/v4/settings")
    async def update_settings_route(request: Request):
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        cfg = config
        applied = []
        filtered: Dict[str, Any] = {}

        SETTINGS_ALIASES = {
            'max_risk_usd': 'max_risk_usd_per_trade',
            'min_risk_usd': 'min_risk_usd_per_trade',
            'sizing_mode': 'trade_sizing_mode',
            'enable_titan_pro': 'strategy_titan_pro_enabled',
            'enable_smc': 'strategy_smc_enabled',
            'enable_occ_r5': 'strategy_occ_r5_enabled',
            'enable_eyes_sme': 'strategy_eyes_sme_enabled',
            'enable_mean_reversion': 'strategy_mean_rev_enabled',
            'enable_quant_way': 'strategy_quant_way_enabled',
            'enable_partial_tp': 'enable_partial_take_profit',
            'enable_breakeven': 'enable_breakeven_trigger',
            'news_filter_enabled': 'enable_news_filter',
            'enable_ai_validation': 'enable_ai_discussion',
        }

        ALLOWED_SETTINGS = {
            'mt5_login', 'mt5_password', 'mt5_server', 'mt5_path', 'mt5_portable',
            'mt5_timeout', 'mt5_magic_number',
            'armed', 'enable_autonomous_trading',
            'trade_sizing_mode', 'sizing_mode', 'risk_per_trade_pct', 'trade_symbols',
            'max_risk_usd_per_trade', 'max_risk_usd', 'min_risk_usd_per_trade', 'min_risk_usd',
            'target_risk_usd_override',
            'max_spread_points',
            'strategy_titan_pro_enabled', 'enable_titan_pro',
            'strategy_smc_enabled', 'enable_smc',
            'strategy_occ_r5_enabled', 'enable_occ_r5',
            'strategy_eyes_sme_enabled', 'enable_eyes_sme',
            'strategy_mean_rev_enabled', 'enable_mean_reversion',
            'strategy_quant_way_enabled', 'enable_quant_way',
            'enable_ml_brain', 'ml_brain_min_execute_score', 'ml_brain_confluence_bonus',
            'ml_brain_enable_memory',
            'anthropic_api_key', 'anthropic_model', 'anthropic_timeout_sec',
            'enable_ai_discussion', 'enable_ai_validation',
            'base_sl_pct', 'base_tp_pct',
            'enable_partial_take_profit', 'enable_partial_tp', 'partial_tp_ratio', 'partial_tp_close_pct',
            'enable_early_breakeven', 'early_breakeven_r_ratio', 'enable_soft_risk_reduction', 'soft_risk_reduction_r', 'soft_risk_target_r', 'commission_max_pct_of_tp',
            'enable_volume_regime_intelligence', 'volume_adaptive_tp', 'enable_stepped_trailing',
            'stepped_trail_zone1_r', 'stepped_trail_zone2_r', 'stepped_trail_zone3_r', 'stepped_trail_zone4_r', 'stepped_trail_zone5_r', 'stepped_trail_auto_mode', 'enable_constant_trailing', 'enable_auto_pilot_tuning', 'enable_strategy_tester_autotune',
            'enable_breakeven_trigger', 'enable_breakeven', 'breakeven_r_ratio',
            'enable_trailing_stop', 'trailing_stop_atr_mult', 'max_concurrent_positions',
            'daily_max_loss_pct', 'weekly_profit_target_pct', 'max_consecutive_losses',
            'enable_news_filter', 'news_filter_enabled', 'news_pause_min_before', 'news_pause_min_after',
            'server_port', 'webhook_token',
        }
        for k, v in data.items():
            if isinstance(v, str) and "********" in v:
                continue
            if k == "symbol_quantities" and isinstance(v, dict):
                cfg.symbol_quantities.update(v)
                applied.append("symbol_quantities")
                filtered["symbol_quantities"] = cfg.symbol_quantities
                continue
            target_key = SETTINGS_ALIASES.get(k, k)
            if (k in ALLOWED_SETTINGS or target_key in ALLOWED_SETTINGS) and hasattr(cfg, target_key):
                # FIX: Type-coerce values using field annotation before storing
                # Raw setattr with JSON strings (e.g. "1.5") into float fields causes TypeError in arithmetic
                try:
                    hints = cfg.__class__.__annotations__
                    expected_type = hints.get(target_key)
                    if expected_type is float or expected_type == "float":
                        v = float(v)
                    elif expected_type is int or expected_type == "int":
                        v = int(float(v))  # int(float()) handles "5.0" -> 5
                    elif expected_type is bool or expected_type == "bool":
                        if isinstance(v, str):
                            v = v.lower() in ('true', '1', 'yes', 'on', 't')
                        else:
                            v = bool(v)
                except (ValueError, TypeError, AttributeError):
                    pass  # Keep raw value if coercion fails
                setattr(cfg, target_key, v)
                applied.append(target_key)
                filtered[target_key] = v

        cfg.save()

        # Trigger live application re-configuration
        if hasattr(app.state, "on_settings_applied") and app.state.on_settings_applied:
            try:
                app.state.on_settings_applied(filtered)
            except Exception as cb_err:
                logger.error(f"Error applying settings callback: {cb_err}")

        logger.info(f"MT5 settings updated: {applied}")
        return {"success": True, "applied": applied}


    @app.get("/api/v4/health")
    @app.get("/lasthopepanel/api/v4/health")
    async def health_check():
        import time
        return {"status": "ok", "ts": time.time()}

    @app.get("/api/v4/improvements", tags=["improvements"])
    @app.get("/lasthopepanel/api/v4/improvements", tags=["improvements"], include_in_schema=False)
    async def get_improvements_route(limit: int = 20):
        """Get self-improvement suggestions generated from trade analysis."""
        suggestions = trade_journal.get_recent_suggestions(limit) if trade_journal else []
        # Also trigger a fresh on-demand analysis
        if trade_journal:
            try:
                fresh = await asyncio.to_thread(trade_journal.analyze_for_improvements)
                # Return live analysis merged with stored
                return {"suggestions": fresh + suggestions[:10], "total": len(fresh) + len(suggestions)}
            except Exception:
                pass
        return {"suggestions": suggestions, "total": len(suggestions)}

    @app.get("/api/v4/risk-status")
    @app.get("/lasthopepanel/api/v4/risk-status")
    async def get_risk_status():
        daily_loss_pct = account_tracker.get_daily_loss_pct() if account_tracker else 0.0
        acc_state = account_tracker.get_live_state() if account_tracker else {}
        circuit_broken = getattr(risk_manager, "_circuit_broken", False) if risk_manager else False
        consecutive_losses = getattr(risk_manager, "_consecutive_losses", 0) if risk_manager else 0
        return {
            "circuit_broken": circuit_broken,
            "daily_loss_pct": round(daily_loss_pct, 2),
            "daily_max_loss_pct": float(getattr(config, "daily_max_loss_pct", 3.0)),
            "consecutive_losses": consecutive_losses,
            "max_consecutive_losses": int(getattr(config, "max_consecutive_losses", 4)),
            "peak_equity": acc_state.get("peak_equity", 0.0),
            "max_drawdown_pct": acc_state.get("max_drawdown_pct", 0.0),
            "armed": config.armed,
        }

    @app.post("/api/v4/emergency-stop")
    @app.post("/lasthopepanel/api/v4/emergency-stop")
    async def emergency_stop():
        config.armed = False
        config.save()
        if mt5_client:
            bot_magic = int(getattr(config, "mt5_magic_number", 999111)) if getattr(config, "ignore_manual_trades", True) else None
            await asyncio.to_thread(mt5_client.close_all_positions, only_magic=bot_magic)
        return {"success": True}

    # ── Per-Symbol Enable/Disable Control ──────────────────────────────────────

    @app.get("/api/v4/symbols")
    @app.get("/lasthopepanel/api/v4/symbols")
    async def get_symbol_list():
        """
        Return all traded & available symbols with their enabled/disabled state.
        Discovers all symbols offered by connected MT5 broker + full portfolio targets.
        Powers the symbol toggle permissions in Settings tab.
        """
        all_syms_set = set()

        # 1. Configured trade_symbols
        cfg_syms = config.trade_symbols if isinstance(config.trade_symbols, list) else [
            s.strip() for s in str(config.trade_symbols).split(",") if s.strip()
        ]
        all_syms_set.update(cfg_syms)

        # 2. DEFAULT_PORTFOLIO_TARGETS from mt5_client
        if hasattr(mt5_client, "DEFAULT_PORTFOLIO_TARGETS"):
            all_syms_set.update(mt5_client.DEFAULT_PORTFOLIO_TARGETS)

        # 3. Discovered broker symbols
        if hasattr(mt5_client, "get_all_broker_symbols"):
            try:
                b_syms = mt5_client.get_all_broker_symbols()
                if b_syms:
                    all_syms_set.update(b_syms)
            except Exception:
                pass

        # 4. Any symbol previously saved in symbol_enabled
        if isinstance(config.symbol_enabled, dict):
            all_syms_set.update(config.symbol_enabled.keys())

        # Clean, prioritize & sort
        clean_list = [s.strip() for s in all_syms_set if s and s.strip()]
        
        PRIORITY_ORDER = [
            "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
            "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY",
            "XAUUSD", "XAGUSD",
            "BTCUSD", "ETHUSD", "SOLUSD", "LTCUSD",
            "US30", "DJIUSD", "NAS100", "NDXUSD", "SPX500", "GER40", "USOIL"
        ]
        def sort_key(sym: str):
            base = re.sub(r'[._][a-zA-Z0-9]*$', '', sym).rstrip('._').upper()
            if base in PRIORITY_ORDER:
                return (0, PRIORITY_ORDER.index(base), sym)
            return (1, 0, sym)

        sorted_symbols = sorted(clean_list, key=sort_key)

        symbol_items = [
            {
                "symbol": sym,
                "enabled": config.is_symbol_enabled(sym),
            }
            for sym in sorted_symbols
        ]

        return {
            "symbols": symbol_items,
            "active_count": len([s for s in symbol_items if s["enabled"]]),
            "total_count": len(symbol_items),
        }

    @app.post("/api/v4/symbols/toggle")
    @app.post("/lasthopepanel/api/v4/symbols/toggle")
    async def toggle_symbol(request: Request):
        """
        Enable or disable a specific symbol.
        Body: {"symbol": "EURUSD.f", "enabled": true}
        """
        try:
            data = await request.json()
            symbol = str(data.get("symbol", "")).strip()
            enabled = bool(data.get("enabled", True))
            if not symbol:
                return {"success": False, "error": "symbol required"}

            enabled_map = dict(config.symbol_enabled)
            enabled_map[symbol] = enabled
            
            # Sync base symbol and known aliases (e.g. NDXUSD <-> NAS100, DJIUSD <-> US30)
            base = re.sub(r'[._][a-zA-Z0-9]*$', '', symbol).rstrip('._').upper()
            enabled_map[base] = enabled
            ALIASES_MAP = {
                "NDXUSD": ["NAS100", "USTEC", "US100", "NASDAQ"],
                "NAS100": ["NDXUSD", "USTEC", "US100", "NASDAQ"],
                "DJIUSD": ["US30", "DJ30", "WS30", "WALLSTREET"],
                "US30": ["DJIUSD", "DJ30", "WS30", "WALLSTREET"],
                "SPXUSD": ["SPX500", "US500", "SP500"],
                "SPX500": ["SPXUSD", "US500", "SP500"],
                "DAXEUR": ["GER40", "DE40", "DAX"],
                "GER40": ["DAXEUR", "DE40", "DAX"],
                "GOLD": ["XAUUSD"],
                "XAUUSD": ["GOLD"],
                "SILVER": ["XAGUSD"],
                "XAGUSD": ["SILVER"],
                "WTIUSD": ["USOIL"],
                "USOIL": ["WTIUSD"],
            }
            if base in ALIASES_MAP:
                for a in ALIASES_MAP[base]:
                    enabled_map[a] = enabled

            config.symbol_enabled = enabled_map
            
            # Ensure symbol is in trade_symbols
            if symbol not in config.trade_symbols:
                config.trade_symbols.append(symbol)
            if base not in config.trade_symbols:
                config.trade_symbols.append(base)

            config.save()
            action = "ENABLED ✅" if enabled else "DISABLED 🔴"
            import logging
            logging.getLogger("server").info(f"[SYMBOL TOGGLE] {symbol} → {action}")
            return {
                "success": True,
                "symbol": symbol,
                "enabled": enabled,
                "active_symbols": config.get_active_symbols(),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/v4/symbols/batch")
    @app.post("/lasthopepanel/api/v4/symbols/batch")
    async def batch_set_symbols(request: Request):
        """
        Set enabled state for multiple symbols at once.
        Body: {"symbols": {"EURUSD.f": true, "BTCUSD.f": false, ...}}
        """
        try:
            data = await request.json()
            updates = data.get("symbols", {})
            if not isinstance(updates, dict):
                return {"success": False, "error": "symbols must be a dict"}
            enabled_map = dict(config.symbol_enabled)
            for sym, state in updates.items():
                enabled_map[str(sym).strip()] = bool(state)
            config.symbol_enabled = enabled_map
            config.save()
            return {
                "success": True,
                "active_symbols": config.get_active_symbols(),
                "total": len(config.trade_symbols),
                "active_count": len(config.get_active_symbols()),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/v4/market-calendar")
    @app.get("/lasthopepanel/api/v4/market-calendar")
    async def get_market_calendar():
        """Full market calendar status: sessions, swaps, holidays."""
        try:
            from quantclaw.market_calendar import MarketCalendar
            cal = MarketCalendar(mt5_client=mt5_client)
            # Update live swaps from MT5 if connected
            if mt5_client and mt5_client.is_connected():
                for sym in (config.trade_symbols if isinstance(config.trade_symbols, list) else config.trade_symbols.split(",")):
                    sym = sym.strip()
                    try:
                        info = mt5_client.get_symbol_info(sym)
                        if info and hasattr(info, 'swap_long'):
                            cal.update_live_swaps(sym, float(info.swap_long), float(info.swap_short))
                    except Exception:
                        pass
            return cal.get_full_status()
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/v4/session-status")
    @app.get("/lasthopepanel/api/v4/session-status")
    async def get_session_status():
        """Session scores for all monitored symbols."""
        try:
            from quantclaw.market_calendar import MarketCalendar
            cal = MarketCalendar()
            symbols = config.trade_symbols if isinstance(config.trade_symbols, list) else [s.strip() for s in config.trade_symbols.split(",")]
            return {
                "calendar": cal.get_full_status(),
                "symbols": {sym: cal.get_symbol_status(sym) for sym in symbols},
            }
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/v4/swap-rates")
    @app.get("/lasthopepanel/api/v4/swap-rates")
    async def get_swap_rates():
        """Swap rates for all monitored symbols, including live broker rates."""
        try:
            from quantclaw.market_calendar import MarketCalendar, SWAP_RATES
            cal = MarketCalendar()
            symbols = config.trade_symbols if isinstance(config.trade_symbols, list) else [s.strip() for s in config.trade_symbols.split(",")]
            result = {}
            for sym in symbols:
                import re as _re
                base = _re.sub(r'[._][a-zA-Z0-9]+$', '', sym).upper()
                # Try live rates from MT5
                live_long = 0.0
                live_short = 0.0
                if mt5_client and mt5_client.is_connected():
                    try:
                        info = mt5_client.get_symbol_info(sym)
                        if info and hasattr(info, 'swap_long'):
                            live_long = float(info.swap_long)
                            live_short = float(info.swap_short)
                            cal.update_live_swaps(sym, live_long, live_short)
                    except Exception:
                        pass
                table = SWAP_RATES.get(base, {"buy": 0.0, "sell": 0.0})
                tonight_mult = cal.get_swap_day_multiplier()
                result[sym] = {
                    "base": base,
                    "table_buy": table.get("buy", 0.0),
                    "table_sell": table.get("sell", 0.0),
                    "live_buy": live_long if live_long != 0 else table.get("buy", 0.0),
                    "live_sell": live_short if live_short != 0 else table.get("sell", 0.0),
                    "tonight_multiplier": tonight_mult,
                    "is_wednesday_3x": tonight_mult == 3,
                    "buy_cost_tonight": cal.get_swap_cost(sym, "buy", 1.0),
                    "sell_cost_tonight": cal.get_swap_cost(sym, "sell", 1.0),
                }
            return result
        except Exception as e:
            return {"error": str(e)}

    return app
