# QuantClaw MT5 — Transformation & System Walkthrough

## Overview
QuantClaw has been completely rebuilt as an **autonomous 24/7 AI+ML Multi-Asset Trading System powered exclusively by MetaTrader 5 (MT5)**.

All legacy Delta Exchange and TradingView webhook dependencies have been permanently removed. The bot connects directly to MetaTrader 5 via the official Python bridge to trade **Forex Majors/Minors, Metals (Gold / XAUUSD), Crypto (BTCUSD, ETHUSD), and Indices (US30, NAS100, SPX500)** with institutional precision.

---

## Key Subsystems & Capabilities

### 1. Direct MetaTrader 5 Engine (`quantclaw/mt5_engine.py`)
- **Direct Terminal Integration**: Seamlessly communicates with any installed MT5 broker terminal (Exness, IC Markets, FTMO, Deriv, XM, MetaQuotes Demo, etc.).
- **Dynamic Lot Sizer**: Automatically calculates lot sizes based on account equity, risk % per trade, and stop loss distance in points/pips (`Lots = Risk_USD / (SL_Points * Point_Value)`).
- **Execution Engine**: Direct execution of Market Deals and Pending Orders with automated filling mode autodetection (`IOC`, `FOK`, `RETURN`).
- **Position Modification**: Real-time Stop Loss & Take Profit adjustments, Breakeven triggers, and partial closes.

### 2. 24/7 Multi-Engine Strategy Matrix (`quantclaw/strategy_engine.py`)
Runs 5 institutional strategies in parallel across multi-timeframe candle feeds (M1, M5, M15, M30, H1, H4, D1):
1. **SMC Liquidity & Order Block Engine**: Captures session liquidity sweeps at Asian/London/NY extremes, confirmed by market structure shifts (CHoCH/BOS) and Fair Value Gap (FVG) retests.
2. **Institutional Trend & Momentum (OCC R5)**: Fast SMMA crossover aligned with higher-timeframe trend filters (H4/H1 EMA 50/200).
3. **Eyes Smart Structure Pro**: Dynamic pivot breakout with ATR impulse expansion candles.
4. **Mean-Reversion & Squeeze Snapper**: Multi-timeframe RSI + Stochastic divergence at Bollinger Band extremes (%B < 0.05 / %B > 0.95).
5. **Quant Way Institutional Flow**: EMA 20/50 pullback with volume multiplier explosion and rejection wick sweeps.

### 3. Self-Learning ML Brain (`quantclaw/ml_engine.py`)
- **10-Feature Vector Real-Time Scorer**: Evaluates Trend alignment, SMC structure, Liquidity sweeps, Momentum, Volatility regime, Spread efficiency, Session timing, News risk, Multi-strategy confluence (+20 bonus), and Bayesian win-rate memory.
- **Autonomous Execution Barrier**: Generates 0–100 conviction score; punches trade when score >= threshold (default 65).
- **Adaptive Weight Learning**: Automatically refines feature weights and threshold boundaries based on closed trade results stored in SQLite.

### 4. Claude AI Co-Pilot & 24/7 Market Discussion (`quantclaw/ai_engine.py`)
- Deep reasoning via Claude Sonnet 4.6 / 3.7 / 3.5 for tactical validation and continuous market discussion.
- **100% Autonomous Fallback**: If offline or no API key is provided, the local ML Brain operates seamlessly with zero downtime.

### 5. Risk Management & Circuit Breakers (`quantclaw/risk_manager.py`)
- **Dynamic Breakeven**: Moves SL to entry price + spread buffer once trade reaches 1.0R profit.
- **Partial Take Profit**: Closes 50% volume at 1.5R, lets remainder ride with trailing stop to 3.0R–5.0R.
- **3% Daily Max Loss Circuit Breaker**: Automatically disarms the bot and blocks entries if daily drawdown limit is reached.
- **Spread Guard**: Rejects trade execution if broker spread exceeds threshold during news spikes.

### 6. MetaTrader 5 Telemetry Dashboard (`quantclaw/dashboard.py`)
- **Live MT5 Account HUD**: Balance ($), Equity ($), Free Margin ($), Margin Level %, Floating P&L ($), Today P&L ($).
- **MT5 Open Positions Table**: Symbol, Ticket, Type (BUY/SELL), Volume (Lots), Entry, Current, SL, TP, Floating P&L, Quick Close & Breakeven buttons.
- **Interactive Chart.js Equity Curve**: 7D / 30D / 90D capital growth tracking.
- **Live Streaming Terminal Console**: Real-time event log with color-coded status tags.
- **4-Tab Settings Editor**: MT5 Credentials, Lot Sizes & Sizing Mode, Strategy Toggles, Risk Limits & ML Thresholds.

---

## Verification & Test Results
- **Unit Test Suite**: `tests/test_mt5_system.py` + `tests/test_smc_analysis.py` -> **12/12 Tests Passing (100%)** ✅
- **Standalone Binary**: Rebuilt `dist/QuantClaw.exe` with PyInstaller.
