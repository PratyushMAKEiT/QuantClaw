# Master Build Prompt for Antigravity

## How to use this document

Don't paste this whole file in as one task. Antigravity works best in Plan mode, where it drafts a plan artifact before writing code, and its agents can drive a real browser to test what they build — so feed it **one phase at a time** (Section 12 has all six), let it finish, browser-test the result yourself, and only then hand it the next phase. Before you start, fill in the two placeholders used throughout: `[PLATFORM_NAME]` (your product's name) and `[SCRIPT_NAME]` (the name of your custom scripting language, e.g. "FlowScript" or "ChartLang").

This is **not** a request to copy TradingView's logo, brand assets, source code, or Pine Script itself — everything below is an original system inspired by the *category* of product TradingView is, built on legally clean open-source and free-tier foundations.

---

## 1. Mission statement

Build **[PLATFORM_NAME]**, a professional-grade, multi-asset financial charting and algorithmic-trading web application. It must include: real-time interactive charts, a custom scripting language for writing indicators and strategies, a strategy backtesting engine, live streaming market data, a price/indicator alert system, a symbol screener, and live order execution at real brokers using the user's own API keys. Original branding, original UI, original scripting-language syntax throughout.

---

## 2. Tech stack

- **Frontend:** React 18 + TypeScript + Vite. Zustand for state. Tailwind CSS for layout. Monaco Editor for the script editor.
- **Charting engine:** `lightweight-charts` (npm package, by TradingView, Apache-2.0, free for commercial use) as the rendering core for candles/lines/bars, extended with a custom canvas overlay layer for drawing tools, multi-pane indicators, and replay mode. Note: the Apache-2.0 license requires displaying the library's attribution notice and a link to tradingview.com somewhere in the app (e.g. an "About" or "Credits" page) — keep this requirement in the build.
- **Backend:** Node.js + TypeScript, NestJS for the REST + WebSocket API.
- **Real-time transport:** WebSocket gateway (Socket.IO or native `ws`) streaming ticks/candles to connected clients.
- **Database:** PostgreSQL with the TimescaleDB extension for OHLCV time-series data. Redis for pub/sub, caching, and rate limiting.
- **Script sandboxing:** `isolated-vm` (or equivalent V8 isolate sandbox) on the server for running backtests; Web Workers on the client for live/interactive script execution. This is not optional — see Section 8's security requirements.
- **Infra:** Docker Compose for local dev, `.env`-based config, Prisma (or Knex) for DB migrations.

---

## 3. System architecture

Data flows in one direction, with a feedback path for orders:

1. **Data & broker APIs** (external) — crypto exchange REST/WebSocket APIs, a stock market-data provider, and broker APIs (Alpaca, and crypto exchanges via CCXT).
2. **Ingestion & broker layer** — normalizes incoming ticks/candles into one internal format and publishes them to Redis pub/sub; also hosts the broker-adapter layer that places/cancels/tracks orders.
3. **Database** — TimescaleDB stores historical OHLCV bars; Redis holds the live pub/sub channel, session cache, and rate-limit counters.
4. **Script & backtest engine** — runs indicator/strategy scripts bar-by-bar, either live (reading from Redis) or historically (reading from TimescaleDB) inside the sandbox described above.
5. **Frontend** — the chart UI, script editor, backtest report viewer, watchlists, alerts, and order tickets. Talks to the backend over REST (historical data, script CRUD) and WebSocket (live ticks, order/fill updates).

Live order placement flows the opposite direction: Frontend → Backend API → Broker adapter → real broker, with fill confirmations streamed back over the same WebSocket connection.

---

## 4. Charting engine — full feature spec

- **Chart types:** candlestick, OHLC bar, line, area, baseline, Heikin Ashi, Renko, Line Break, Kagi, Point & Figure.
- **Timeframes:** 1s/5s/10s/30s (where data allows), 1m/3m/5m/15m/30m/45m, 1H/2H/3H/4H/6H/12H, 1D/1W/1M, plus a custom range picker.
- **Drawing tools:** trendline, horizontal/vertical/ray/extended lines, parallel channel, pitchfork, Fibonacci retracement/extension/fan/arcs/time-zones, Gann fan and box, rectangle, ellipse, triangle, arrows, text notes, a price-range and date-range measuring tool, freehand brush, icons/emojis.
- **Layouts:** single, 2x1, 2x2, 3x1, and 2x3 grid layouts, each pane independently able to hold a different symbol/timeframe/indicator set, with an option to sync crosshair and/or symbol across panes.
- **Symbol search & watchlists:** fuzzy autocomplete search, multiple named watchlists, a market-overview strip, a hotlist widget (top gainers/losers/most active).
- **Replay mode:** step through historical bars one at a time (play/pause/speed controls) to practice reading a chart or manually test a strategy idea without waiting for real time to pass.
- **Chart settings:** dark/light theme, gridline density, custom per-series colors, session breaks marked on intraday charts, extended-hours toggle for equities.

Performance target: stay interactive (smooth pan/zoom) with 10,000+ candles on screen — use canvas virtualization, not DOM nodes, for anything rendered per-bar.

---

## 5. Custom scripting language — "[SCRIPT_NAME]"

A bar-by-bar scripting language for writing indicators and strategies, conceptually similar to other charting DSLs (Pine Script, thinkScript, NinjaScript) in that scripts execute once per bar with access to that bar's OHLCV — but with its own original syntax, name, and standard library. Two script "kinds":

- **Indicator scripts** — compute and plot values; can render as an overlay on the price pane or in a separate pane below.
- **Strategy scripts** — everything an indicator script can do, plus the ability to place simulated or live orders during a backtest or live run.

**Execution model:** automatic per-bar variables (`open`, `high`, `low`, `close`, `volume`, `time`, `bar_index`); series-based data types so referencing a prior bar's value is a first-class operation (e.g. `close[1]` for the previous bar's close); simple types (`float`, `int`, `bool`, `string`, `color`) plus `array` and, as a stretch goal, `matrix`.

**Core built-in function families to implement:**
- Technical analysis: `ta.sma()`, `ta.ema()`, `ta.wma()`, `ta.rsi()`, `ta.macd()`, `ta.stoch()`, `ta.atr()`, `ta.bb()` (Bollinger Bands), `ta.vwap()`, `ta.highest()`, `ta.lowest()`, `ta.crossover()`, `ta.crossunder()`.
- Plotting: `plot()`, `plotshape()`, `plotchar()`, `hline()`, `bgcolor()`, `fill()`.
- Inputs (rendered as UI controls on the indicator's settings panel): `input.int()`, `input.float()`, `input.bool()`, `input.source()`, `input.color()`.
- Alerts: `alertcondition()`.
- Strategy-only: `strategy.entry()`, `strategy.close()`, `strategy.exit()`, `strategy.cancel()`, with parameters for position size, stop loss, and take profit.

**Example indicator script (illustrative syntax — invent your own keywords/casing):**
```
indicator("Simple RSI", overlay=false)
length = input.int(14, "RSI length")
rsiValue = ta.rsi(close, length)
plot(rsiValue, color=color.purple)
hline(70, color=color.red)
hline(30, color=color.green)
alertcondition(ta.crossunder(rsiValue, 30), title="RSI oversold")
```

**Example strategy script:**
```
strategy("MA crossover", initial_capital=10000)
fast = ta.ema(close, 9)
slow = ta.ema(close, 21)
if ta.crossover(fast, slow)
    strategy.entry("long", strategy.long)
if ta.crossunder(fast, slow)
    strategy.close("long")
```

**Editor requirements:** Monaco-based, with a custom TextMate grammar for syntax highlighting, autocomplete sourced from the built-in function signatures, inline error squiggles from a real-time parser (not just on save), and an "Add to chart" action.

**Security requirement (non-negotiable):** scripts are arbitrary user-authored code and must be sandboxed — no filesystem access, no network access, and hard CPU/memory/execution-time limits, enforced via `isolated-vm` on the server and a strictly-scoped Web Worker with a locked-down CSP on the client.

**Ship these built-in indicators out of the box** (re-implemented natively in [SCRIPT_NAME] — do not copy implementation source from TradingView):
- *Trend:* SMA, EMA, WMA, VWMA, Hull MA, DEMA, TEMA, Ichimoku Cloud, SuperTrend, Parabolic SAR, ADX/DMI, Aroon, linear regression line and channel.
- *Momentum/oscillators:* RSI, Stochastic %K/%D, Stochastic RSI, MACD, CCI, Williams %R, Momentum, Rate of Change, Awesome Oscillator, TRIX, Ultimate Oscillator.
- *Volatility:* Bollinger Bands, ATR, Keltner Channels, Donchian Channels, standard deviation, historical volatility.
- *Volume:* volume histogram, OBV, session and anchored VWAP, Volume Profile (fixed-range and visible-range), Chaikin Money Flow, Accumulation/Distribution, Money Flow Index.
- *Support/resistance:* pivot points (Standard, Fibonacci, Camarilla, Woodie, DeMark), auto-drawn Fibonacci retracement.
- *Pattern recognition:* a candlestick-pattern engine covering doji, engulfing, hammer, shooting star, morning/evening star, harami, and three white soldiers / three black crows.
- *Other:* Zig Zag, Gann tools, rolling correlation, beta vs. a benchmark symbol.

---

## 6. Strategy backtesting engine

**Inputs:** symbol, timeframe, date range, initial capital, position sizing mode (fixed quantity, % of equity, fixed $, or risk-based), commission model (fixed per trade, per share, or percentage), slippage model.

**Simulation rules:** process historical bars sequentially through the strategy script; fill orders realistically (limit orders only fill once price actually reaches the level; stops trigger on touch); support pyramiding limits and a max-position-size cap.

**Performance report must include:** net profit ($ and %), gross profit/loss, max drawdown ($ and %), buy-and-hold comparison, Sharpe ratio, Sortino ratio, profit factor, win rate, average win/loss, largest win/loss, total number of trades, average bars held per trade, an equity curve chart, a drawdown chart, and a full trade list (entry/exit price and time, P&L, run-up, drawdown per trade) exportable to CSV.

**Strategy optimizer:** let the user define a parameter range (e.g. MA length from 5 to 50), run a grid search across combinations, rank by a chosen metric, and show results as a heatmap.

**Paper trading mode:** run a strategy live against real-time data with simulated fills against a virtual balance — this is the bridge between backtesting and connecting a real broker.

---

## 7. Market data layer

- **Crypto:** connect directly to exchange public WebSocket/REST APIs (Binance, Coinbase, Kraken, Bybit, etc.) for free real-time and historical OHLCV. No licensing hurdle — these are public endpoints designed for this.
- **Equities/ETFs:** use a licensed market-data API such as Alpaca's Market Data API, Polygon.io, Twelve Data, or Finnhub. Free/low-cost tiers typically give delayed or IEX-only real-time data; full consolidated-tape (SIP) real-time data from NYSE/NASDAQ requires a paid subscription through the provider — that licensing is handled by the provider, not something to build around.
- **Forex:** OANDA's API or a forex-focused data provider such as Twelve Data.
- Run a historical backfill job per symbol/timeframe into TimescaleDB, then merge in live updates incrementally so historical and live data live in the same tables.

---

## 8. Broker integration — live trading

**Design a common adapter interface** so any broker can be plugged in later without touching the rest of the app:

```typescript
interface IBrokerAdapter {
  connect(credentials: BrokerCredentials): Promise<void>;
  getAccount(): Promise<AccountInfo>;
  getPositions(): Promise<Position[]>;
  getOrders(): Promise<Order[]>;
  placeOrder(order: OrderRequest): Promise<Order>;
  cancelOrder(orderId: string): Promise<void>;
  streamFills(onFill: (fill: Fill) => void): void;
}
```

**Build two concrete, real implementations** as reference adapters:
1. **Alpaca** (US stocks, ETFs, options) — API key + secret auth; use the paper-trading endpoint by default so orders can be tested with fake money, with live trading behind an explicit opt-in using the same API shape.
2. **Crypto exchanges via CCXT** — an open-source library (MIT license) giving one unified interface across 100+ real exchanges (Binance, Coinbase, Kraken, Bybit, OKX, and more); it's non-custodial and client-side, meaning the user's API keys and funds are only ever talked to directly, never routed through a third party. The user supplies their own key/secret per exchange.

**Order types:** market, limit, stop, stop-limit, trailing stop. **Time-in-force:** day, GTC, IOC, FOK.

**Security requirements (must-have):**
- Encrypt broker API keys at rest (AES-256 with a KMS-managed key); never log them.
- Per-user isolation of stored credentials.
- Require the user to explicitly enable "live" mode, with a persistent, unmissable UI indicator distinguishing paper from live at all times.
- A hard confirmation dialog before the very first live order.
- Onboarding docs that tell users to scope their broker API keys to trading only (disable withdrawal permissions where the broker allows it).

Adding a new broker later (Interactive Brokers, Tradovate, OANDA, etc.) means writing one more class that implements `IBrokerAdapter` — that's the extensibility path, rather than trying to hard-code every broker on day one.

---

## 9. Alerts engine

- **Trigger types:** price crossing a level, an indicator condition (e.g. RSI < 30), a drawn line being touched, a strategy order fill.
- **Delivery channels:** in-app notification, outbound webhook (so the alert can trigger an external bot or automation), email, browser push.
- **Management UI:** create/edit/pause/delete alerts, plus a log of alerts that have fired.

---

## 10. Screener

A filterable, sortable table of symbols with real-time updating rows. Filters should include price, % change, volume, market cap, and technical conditions (e.g. "RSI below 30", "price above 50-day MA", or a condition written in a [SCRIPT_NAME] snippet). Users can save filter presets and add screener results straight to a watchlist.

---

## 11. UI/UX requirements

A professional, dark-themed fintech interface with its own original visual identity (color palette, logo, type) — not a reproduction of TradingView's specific branded assets. Standard layout convention: left-side toolbar for drawing tools, right sidebar for watchlist/symbol details, bottom panel for the script editor and backtest report, top toolbar for symbol search, timeframe, indicators, alerts, and layout controls. Full keyboard shortcuts for common actions. Desktop-first, but usable on tablet widths.

---

## 12. Non-functional requirements

- **Performance:** 60fps chart interaction even with large datasets; keep all script execution off the UI thread via Web Workers.
- **Testing:** unit tests for every indicator's math against known reference values; integration tests for each broker adapter against that broker's sandbox/paper environment; end-to-end tests (Playwright) for core chart interactions.
- **Security:** script sandboxing (see Section 5), input sanitization, JWT auth with refresh tokens, per-endpoint rate limiting, HTTPS everywhere, dependency vulnerability scanning.
- **Observability:** structured logging, error tracking (e.g. Sentry), a basic metrics dashboard.
- **Deployment:** every service Dockerized, `docker-compose.yml` for local dev, environment-based config, migration tooling for schema changes.

---

## 13. Recommended build order — feed these to Antigravity one at a time

1. **Charting core.** Historical candlestick/line/bar rendering via `lightweight-charts`, pan/zoom, multiple timeframes, basic drawing tools. *Done when:* you can load a symbol, switch timeframes, and draw a trendline on 5,000+ historical candles with no lag.
2. **Scripting language + indicators.** The [SCRIPT_NAME] interpreter, the Monaco editor, and 20-30 core indicators from Section 5's list running live on the chart. *Done when:* a user can write a custom script, hit "Add to chart," and see it plot correctly, and 20+ built-ins work out of the box.
3. **Backtesting engine.** Historical strategy simulation and the full performance report from Section 6. *Done when:* running a strategy script over a date range produces an equity curve, a trade list, and correct Sharpe/drawdown numbers you can spot-check by hand on a small sample.
4. **Live market data.** WebSocket streaming from a crypto exchange and a stock data provider. *Done when:* the chart and any live indicators update in real time without a page refresh.
5. **Broker connection + paper trading.** The `IBrokerAdapter` interface, Alpaca paper trading first, then a crypto exchange via CCXT. *Done when:* a strategy can place, fill, and close a paper trade end-to-end, visible in an order/position UI.
6. **Alerts, screener & hardening.** Alerts engine, screener, watchlists, layouts, then a full security pass — before ever flipping on real-money trading. *Done when:* the security checklist in Section 12 is fully checked off and a live order requires the explicit confirmation flow from Section 8.

---

## 14. Definition-of-done checklist

- [ ] 6+ chart types render correctly with smooth pan/zoom at 10,000+ candles
- [ ] [SCRIPT_NAME] interpreter runs a script bar-by-bar with correct series/history semantics (`close[1]` etc. behave correctly)
- [ ] 20+ built-in indicators ship out of the box and match known reference values in unit tests
- [ ] Backtester produces a correct equity curve and trade list on a known test strategy
- [ ] Live WebSocket data updates charts and running indicators without a refresh
- [ ] Alpaca paper trading round-trip (place → fill → close) works end-to-end
- [ ] At least one CCXT-backed exchange round-trip works end-to-end
- [ ] Broker API keys are encrypted at rest and never appear in logs
- [ ] Live-trading mode requires explicit opt-in and shows a persistent paper/live indicator
- [ ] Script execution is fully sandboxed (verified with a deliberately malicious test script that tries filesystem/network access and is blocked)

---

## 15. Legal & safety notes to keep in the product

This is a personal-use tool that connects to the user's own brokerage/exchange accounts via their own API keys — it is not itself a broker-dealer or exchange, and shouldn't behave like one. Include a clear risk disclaimer screen before live trading can be enabled. If this platform is ever opened up for other people to trade through, that crosses into financial regulation (broker-dealer rules, KYC/AML) that varies by jurisdiction — treat that as a "consult a lawyer" item, not an engineering task.
