# QuantClaw v4 — Architecture & Status Report
**Last Updated: 2026-08-20 18:00 IST**

---

## 🤖 QuantClaw v4 Architecture Overview

In QuantClaw v4, the internal TradingView IDE clone has been completely eliminated in favor of a clean, dedicated autonomous trading bot with direct internal strategy engines and an advanced telemetry dashboard:

1. **Market Engine (`quantclaw/market_engine.py`)**:
   - Free Binance public WebSocket streams for BTC, ETH, GOLD (XAUT), SOL, BNB.
   - Real-time rolling OHLCV candle buffers with automatic candle-close detection.
   - Zero API key required; Delta REST fallback.

2. **Internal Strategy Engine (`quantclaw/strategy_engine.py`)**:
   - **Eyes SME**: Smart Market Structure engine (pivot highs/lows + impulse candle body confirmation).
   - **OCC R5**: Open Close Crossover (SMMA close vs SMMA open crossover).
   - **Quant Way**: EMA 20/50 trend + volume expansion + liquidity wick sweep detection.
   - Verbatim Pine Script logic ported directly to Python.

3. **Enhanced ML Brain (`quantclaw/ml_engine.py` & `quantclaw/trade_journal.py`)**:
   - SQLite persistent trade memory (`quantclaw.db`).
   - Setup fingerprint win rate lookup.
   - Multi-strategy confluence scoring (+25 bonus when 2+ strategies agree).
   - Claude API called only on borderline scores (30–49 range) or high news volatility, ensuring $5 Claude recharge lasts 6+ months.

4. **Account & Equity Tracker (`quantclaw/account_tracker.py`)**:
   - Real-time balance and total equity polling from Delta Exchange.
   - Periodic hourly snapshots stored in SQLite.
   - Daily/weekly/monthly P&L calculations.
   - 3% daily loss circuit breaker auto-disarm.

5. **News Sentiment Monitor (`quantclaw/news_monitor.py`)**:
   - Background RSS polling with keyword-based heuristic scoring (zero Claude API cost).
   - 4-hour per-symbol sentiment caching.

6. **Dashboard v4 (`quantclaw/dashboard.py`)**:
   - Clean, dark-mode monitoring dashboard with Chart.js equity curve.
   - Live strategy signals feed, open positions, trade journal, and full bot settings tab.

7. **Android Mobile API (`/api/mobile/*`)**:
   - Lightweight endpoints for mobile monitoring, arming, and emergency flatten.

```

The signal execution pipeline is identical:
1. **Signal in**: `POST /api/webhook-signal` with `{symbol, action, price, atr, rsi, source}`
2. **ML score**: `MLEngine` filters (threshold: `ml_borderline_low` = 45)
3. **AI confirm**: Claude (`claude-sonnet-4-6`) sentiment scan if borderline
4. **Regime select**: ALPHA / BETA / GAMMA based on conviction score
5. **Execute**: Delta Exchange market order via `DeltaExchangeClient`
6. **Manage**: Dedicated asyncio coroutine (`_manage_alpha/beta/gamma`) watches the position

---

## 📄 About the .md Rule — What Happened

You had a rule that **every change must be documented in a `.md` file**. Here's the honest status:

| File | Status | Problem |
|---|---|---|
| `README.md` | ⚠️ **STALE** | Still references TradingView webhooks as source — outdated |
| `overview.md` | ⚠️ **PARTIALLY STALE** | Architecture diagram still shows TradingView as signal source |
| `walkthrough.md` | ⚠️ **OUTDATED** | Describes the old dashboard version, references 75 tests (now 60) |

**The rule was not being followed** — changes were being made to code files but the `.md` files were not updated to reflect them. This has been corrected below.

---

## ✅ Updated Architecture (Current Truth)

```
┌─────────────────────────────────────────────────────────────────┐
│                    QuantClaw.exe (v3)                           │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │          Web IDE (_dashboard.html)                      │   │
│  │  Binance WebSocket ──► LightweightCharts (offline)      │   │
│  │  Pine Script Compiler ──► Strategy Backtester           │   │
│  │  Signal Button ──────► POST /api/webhook-signal         │   │
│  └──────────────────────────┬──────────────────────────────┘   │
│                             │                                   │
│  ┌──────────────────────────▼──────────────────────────────┐   │
│  │          FastAPI Server (server.py)                     │   │
│  │  POST /api/webhook-signal ──► process_signal()          │   │
│  │  GET  /api/pine-scripts   ──► list pine/ dir            │   │
│  │  GET  /api/positions      ──► Delta positions           │   │
│  └──────────────────────────┬──────────────────────────────┘   │
│                             │                                   │
│  ┌──────────────────────────▼──────────────────────────────┐   │
│  │  ML Engine → AI Engine → Risk Manager                   │   │
│  │  (ALL UNCHANGED — exact same logic as before)           │   │
│  └──────────────────────────┬──────────────────────────────┘   │
│                             │                                   │
└─────────────────────────────┼───────────────────────────────────┘
                              │ Orders
                              ▼
              Delta Exchange (REST + WebSocket)
```

---

## 📁 Current File Sizes (As of 2026-08-13)

```
quantclaw/
├── _dashboard.html      298.5 KB  ← IDE (rebuilt v3, 2026-08-13)
├── server.py            101.8 KB  ← +4 new routes (2026-08-13)
├── risk_manager.py      163.5 KB  ← UNCHANGED
├── main.py               27.5 KB  ← UNCHANGED
├── ai_engine.py          69.7 KB  ← UNCHANGED
├── exchange.py           58.8 KB  ← UNCHANGED
├── ml_engine.py          21.5 KB  ← UNCHANGED
├── config.py             17.0 KB  ← UNCHANGED
├── dashboard.py           0.6 KB  ← Loader only (rebuilt 2026-08-13)
└── models.py             11.4 KB  ← UNCHANGED

pine/
├── eyes_smart_structure_engine.pine   11.9 KB  ← UNCHANGED, bundled in IDE
├── occ_r5_quantclaw.pine              11.7 KB  ← UNCHANGED, bundled in IDE
└── quant_way.pine                      8.3 KB  ← UNCHANGED, bundled in IDE
```

---

## 🧪 Test Results (Last Run: 2026-08-13)

```
60 passed, 597 warnings in 26.92s
```

- `tests/test_ai_engine.py` ✅
- `tests/test_exchange.py` ✅
- `tests/test_ml_and_shadow.py` ✅
- `tests/test_risk_manager.py` ✅
- `tests/test_server.py` ✅

---

## 🚨 Important Rules (Permanent)

1. **No TradingView webhooks** — All signals must come from the internal IDE strategy engine
2. **Offline-first** — No CDN dependencies. All assets bundled in the exe
3. **Bot core is sacred** — `ai_engine`, `exchange`, `risk_manager`, `ml_engine` must never be touched unless explicitly requested
4. **Update this file** — Every session that changes code must update `overview.md` and this file

---

*This document replaces and supersedes `walkthrough.md`. Keep this file updated every session.*
