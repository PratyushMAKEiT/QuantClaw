# QuantClaw v4 — Autonomous AI+ML Trading Bot

> A Windows desktop application (.exe) and backend server for autonomous crypto derivatives trading on Delta Exchange. Features native Python strategy engines (Eyes SME, OCC R5, Quant Way), SQLite-backed ML setup memory, real-time Binance public feeds, sentiment analysis, risk management, and a clean monitoring telemetry dashboard.

![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)
![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)
![FastAPI](https://img.shields.io/badge/Server-FastAPI-teal.svg)
![SQLite](https://img.shields.io/badge/Storage-SQLite-lightgrey.svg)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  QuantClaw v4                                               │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  MarketEngine                                         │  │
│  │  Binance WebSocket ──► Real-Time OHLCV Candle Buffers │  │
│  └──────────────────────────┬────────────────────────────┘  │
│                             │ on_candle_close               │
│  ┌──────────────────────────▼────────────────────────────┐  │
│  │  StrategyEngine (Eyes SME, OCC R5, Quant Way)         │  │
│  └──────────────────────────┬────────────────────────────┘  │
│                             │ signals + confluence          │
│  ┌──────────────────────────▼────────────────────────────┐  │
│  │  MLEngine + TradeJournal (SQLite Memory)              │  │
│  │  Borderline / News ──► Claude AIEngine                │  │
│  └──────────────────────────┬────────────────────────────┘  │
│                             │ confirmed trades              │
│  ┌──────────────────────────▼────────────────────────────┐  │
│  │  RiskManager (Alpha/Beta/Gamma regimes + 3% DL limit) │  │
│  │  ──► Delta Exchange (Orders, Positions, Balances)     │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Features

- **Autonomous Trading**: Executes trades 24/7 without manual intervention or third-party webhooks.
- **Verbatim Pine Strategies**: Eyes Smart Structure, OCC R5 SMMA crossover, and Quant Way liquidity sweeps ported to Python.
- **Enhanced ML Brain**: Persistent SQLite trade journal tracks historical win rate by setup fingerprint, boosting high-probability patterns.
- **Capital Protection**: Strict 3% daily loss circuit breaker with automatic disarm and emergency flatten hotkey (`Ctrl+Shift+E`).
- **Telemetry Dashboard**: Clean dark-mode dashboard showing equity curve, live signals feed, active positions, and full settings editor.
- **Mobile Android API**: `/api/mobile/*` REST endpoints ready for Android companion app.

   - **Delta Exchange**: Get keys from [delta.exchange](https://www.delta.exchange) → Profile → API Management
   - **Anthropic**: Get key from [console.anthropic.com](https://console.anthropic.com)
4. Click **SAVE**

### 5. Use the Built-in IDE

1. Open QuantClaw.exe — the IDE loads automatically
2. Press `/` to search and select a crypto pair (BTCUSDT, ETHUSDT, etc.)
3. Click **Pine Editor** tab → **My Scripts** to load your strategies:
   - `eyes_smart_structure_engine.pine`
   - `occ_r5_quantclaw.pine`
   - `quant_way.pine`
4. Click **Run Backtest** to see results
5. Enable **Auto-Execute Signals** + ensure bot is **ARMED** → signals fire live

> ⚠️ External TradingView webhooks are **permanently disabled**. All signals originate from the internal IDE only.

---

## Risk Regimes

| Regime | Condition | Behavior |
|--------|-----------|----------|
| **ALPHA** 🔴 | High risk / adverse | Instant execution, micro-margin stop (0.15%), full liquidation on adverse move |
| **BETA** 🟡 | Standard trade | Market entry, TP1 at 1:1 R:R (close 65%), move SL to break-even after TP1 |
| **GAMMA** 🟢 | High conviction trend | Scale out: 20% @ TP1, 30% @ TP2, 50% rides with ATR trailing stop |

---

## Hotkeys

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+E` | 🚨 Emergency flatten (close all positions) |
| `Ctrl+Shift+P` | Toggle ARM state (play/pause) |

---

## Project Structure

```
quantclaw/
├── __init__.py          # Package init
├── main.py              # Application entry point
├── server.py            # FastAPI webhook server
├── exchange.py          # Delta Exchange REST + WebSocket
├── ai_engine.py         # Anthropic Claude integration
├── risk_manager.py      # Alpha/Beta/Gamma position management
├── config.py            # Settings persistence
├── hotkeys.py           # Global Windows hotkeys
├── models.py            # Pydantic data models
├── gui/
│   ├── main_window.py   # Floating widget
│   ├── arm_button.py    # ARM toggle
│   ├── telemetry_hud.py # Live HUD
│   ├── settings_panel.py# Collapsible settings
│   └── styles.py        # Dark theme QSS
└── utils/
    ├── logger.py        # Structured logging
    └── crypto.py        # API key encryption
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/webhook-signal?token=X` | Internal IDE signal ingestion |
| `GET`  | `/health` | Health check |
| `GET`  | `/status` | Bot status & recent trades |
| `POST` | `/api/toggle-arm?armed=true` | Arm/disarm from IDE |
| `POST` | `/api/flatten` | Emergency flatten all |
| `GET`  | `/api/pine-scripts` | List Pine Scripts from disk |
| `GET`  | `/api/positions` | Live open positions |
| `POST` | `/api/close-position?product_id=N` | Close a specific position |

---

## Development

```bash
# Run tests
python -m pytest tests/ -v

# Run the app
python -m quantclaw.main

# Build exe
pyinstaller quantclaw.spec --noconfirm
```

---

## ⚠️ Disclaimer

This software is for **educational and research purposes only**. Trading cryptocurrencies involves significant risk. Use at your own risk. Always test on **testnet** first.
