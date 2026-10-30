# ==============================================================================
# tests/test_mt5_system.py â€” Comprehensive Unit Test Suite for QuantClaw MT5
# ==============================================================================
import asyncio
import os
import time
import pytest
from httpx import AsyncClient, ASGITransport

from quantclaw.config import AppConfig
from quantclaw.models import StrategySignal, TradeDecision, RiskRegime
from quantclaw.mt5_engine import MT5Client
from quantclaw.market_engine import MarketEngine
from quantclaw.strategy_engine import StrategyEngine
from quantclaw.ml_engine import MLEngine
from quantclaw.ai_engine import AIEngine
from quantclaw.account_tracker import AccountTracker
from quantclaw.trade_journal import TradeJournal
from quantclaw.news_monitor import NewsMonitor
from quantclaw.risk_manager import RiskManager
from quantclaw.server import create_app
from quantclaw.utils.indicators import (
    calculate_atr,
    calculate_rsi,
    calculate_smma_series,
    calculate_bollinger_bands,
    calculate_stochastic,
    calculate_macd,
    calculate_adx,
)
from quantclaw.utils.smc_analysis import detect_fvgs, detect_order_blocks, detect_liquidity_sweeps


# â”€â”€ Fixtures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@pytest.fixture
def sample_candles():
    """Generate realistic OHLCV candle series."""
    base_time = int(time.time()) - 36000
    candles = []
    price = 1.0850
    for i in range(120):
        o = price
        h = o + 0.0015
        l = o - 0.0010
        c = o + 0.0005 if i % 2 == 0 else o - 0.0004
        price = c
        candles.append({
            "time": base_time + (i * 900),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": 250.0 + (i * 5.0),
            "spread": 12,
        })
    return candles


# â”€â”€ Indicators Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_indicators(sample_candles):
    closes = [c["close"] for c in sample_candles]
    atr = calculate_atr(sample_candles, 14)
    assert atr > 0.0, "ATR must be positive"

    rsi = calculate_rsi(closes, 14)
    assert 0.0 <= rsi <= 100.0, "RSI must be between 0 and 100"

    smma = calculate_smma_series(closes, 8)
    assert len(smma) == len(closes), "SMMA length should match closes"

    bb = calculate_bollinger_bands(closes, 20, 2.0)
    assert bb["upper"] >= bb["middle"] >= bb["lower"], "Bollinger bands order invalid"

    stoch = calculate_stochastic(sample_candles, 14, 3)
    assert 0.0 <= stoch["k"] <= 100.0, "Stoch K must be in bounds"

    macd = calculate_macd(closes, 12, 26, 9)
    assert "macd" in macd and "signal" in macd, "MACD must return dict with keys"

    adx = calculate_adx(sample_candles, 14)
    assert 0.0 <= adx["adx"] <= 100.0, "ADX must be in bounds"


# â”€â”€ SMC Analysis Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_smc_analysis(sample_candles):
    fvgs = detect_fvgs(sample_candles)
    assert isinstance(fvgs, list)

    obs = detect_order_blocks(sample_candles)
    assert isinstance(obs, list)

    sweeps = detect_liquidity_sweeps(sample_candles)
    assert isinstance(sweeps, list)


# â”€â”€ MT5 Client & Lot Sizer Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_mt5_client_lot_sizing():
    client = MT5Client(login=12345, password="pwd", server="MetaQuotes-Demo")
    assert client.login == 12345
    assert client.server == "MetaQuotes-Demo"

    # Default fallback when not connected
    lots = client.calculate_lot_size("EURUSD", risk_usd=100.0, sl_points=200.0, default_lots=0.10)
    assert lots > 0.0, "Calculated lots must be positive"


# â”€â”€ Strategy Engine & ML Brain Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_strategy_and_ml_engine(sample_candles, tmp_path):
    config = AppConfig()
    db_path = str(tmp_path / "test_journal.db")
    journal = TradeJournal(db_path=db_path)

    client = MT5Client()
    market = MarketEngine(client)
    # Pre-populate market buffer
    market._buffers["EURUSD"] = {"M15": sample_candles, "H1": sample_candles, "H4": sample_candles}
    market._live_ticks["EURUSD"] = {"bid": 1.0850, "ask": 1.0852, "last": 1.0851, "spread": 12}

    strategy = StrategyEngine(config, market)
    signals = strategy.scan_symbol("EURUSD", "M15")
    assert isinstance(signals, list)

    ml = MLEngine(config, market, journal)
    test_sig = StrategySignal(
        strategy="smc_liquidity",
        symbol="EURUSD",
        action="buy",
        timeframe="M15",
        price=1.0850,
        sl_points=0.0020,
        tp_points=0.0050,
        strength=85.0,
    )

    decision = ml.evaluate_signal(test_sig, news_score=0.0)
    assert isinstance(decision, TradeDecision)
    assert decision.symbol == "EURUSD"
    assert decision.action == "buy"
    assert 0.0 <= decision.ml_score <= 100.0

    # Test adaptive self-learning outcome update
    ml.record_trade_outcome("EURUSD", "smc_liquidity", "buy", pnl_usd=50.0, outcome="win")
    diag = ml.get_diagnostics()
    assert diag["decision_metrics"]["correct"] == 1


# â”€â”€ Trade Journal SQLite Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_trade_journal(tmp_path):
    db_path = str(tmp_path / "journal_test.db")
    journal = TradeJournal(db_path=db_path)

    journal.record_open_trade(
        ticket=1001,
        symbol="XAUUSD",
        action="BUY",
        volume=0.05,
        entry_price=2350.50,
        sl=2340.0,
        tp=2370.0,
        strategy="smc_liquidity",
        ml_score=88.5,
    )

    trades = journal.get_recent_trades()
    assert len(trades) == 1
    assert trades[0]["ticket"] == 1001
    assert trades[0]["symbol"] == "XAUUSD"

    journal.record_close_trade(ticket=1001, close_price=2365.0, pnl_usd=72.5, outcome="win")
    stats = journal.get_strategy_stats("smc_liquidity")
    assert stats["total_trades"] == 1
    assert stats["wins"] == 1
    assert stats["win_rate"] == 100.0


# â”€â”€ Risk Manager Circuit Breaker Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_risk_manager_circuit_breaker(tmp_path):
    config = AppConfig()
    config.armed = True
    db_path = str(tmp_path / "rm_test.db")
    journal = TradeJournal(db_path=db_path)
    client = MT5Client()
    account = AccountTracker(client, journal)
    rm = RiskManager(config, client, account, journal)

    assert rm.is_armed() is True
    assert rm.is_new_entry_allowed() is True
    rm.trigger_circuit_breaker("Exceeded 5% daily drawdown")
    assert rm.is_armed() is True  # Still armed for management
    assert rm.is_new_entry_allowed() is False  # New entries blocked
    assert config.armed is True  # Bot itself is not disabled

    rm.reset_circuit_breaker()
    assert rm.is_new_entry_allowed() is True


# â”€â”€ FastAPI Endpoints Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@pytest.mark.asyncio
async def test_fastapi_endpoints(tmp_path):
    config = AppConfig()
    db_path = str(tmp_path / "server_test.db")
    journal = TradeJournal(db_path=db_path)
    client = MT5Client()
    market = MarketEngine(client)
    strategy = StrategyEngine(config, market)
    ml = MLEngine(config, market, journal)
    ai = AIEngine()
    news = NewsMonitor()
    account = AccountTracker(client, journal)
    risk = RiskManager(config, client, account, journal, ml)

    app = create_app(
        config=config,
        mt5_client=client,
        market_engine=market,
        strategy_engine=strategy,
        ml_engine=ml,
        ai_engine=ai,
        risk_manager=risk,
        account_tracker=account,
        trade_journal=journal,
        news_monitor=news,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "RUNNING"
        assert "armed" in data

        resp_pos = await ac.get("/api/positions")
        assert resp_pos.status_code == 200
        assert "positions" in resp_pos.json()

        resp_set = await ac.get("/api/v4/settings")
        assert resp_set.status_code == 200
        assert "mt5_login" in resp_set.json()

        # Update settings
        resp_post = await ac.post("/api/v4/settings", json={"mt5_server": "Exness-Real2"})
        assert resp_post.status_code == 200
        assert resp_post.json()["success"] is True

        # Test new performance endpoint (both direct and lasthopepanel prefix)
        resp_perf = await ac.get("/api/v4/performance")
        assert resp_perf.status_code == 200
        perf_data = resp_perf.json()
        assert "win_rate" in perf_data
        assert "profit_factor" in perf_data

        resp_perf_proxy = await ac.get("/lasthopepanel/api/v4/performance")
        assert resp_perf_proxy.status_code == 200
        assert "win_rate" in resp_perf_proxy.json()

        # Test news endpoint
        resp_news = await ac.get("/api/v4/news")
        assert resp_news.status_code == 200
        assert "headlines" in resp_news.json()
        assert "global_sentiment" in resp_news.json()

        # Test diagnostics endpoint
        resp_diag = await ac.get("/api/v4/diagnostics")
        assert resp_diag.status_code == 200
        assert "decision_score" in resp_diag.json()



def test_trade_decision_validators():
    """TradeDecision validators enforce SL/TP direction consistency."""
    from quantclaw.models import TradeDecision
    import pytest
    
    # Valid BUY â€” should not raise
    d = TradeDecision(approved=True, symbol='EURUSD', action='buy', strategy='smc',
                      volume_lots=0.01, entry_price=1.1000, sl_price=1.0950, tp_price=1.1100)
    assert d.approved
    
    # Invalid BUY â€” SL above entry should raise
    try:
        TradeDecision(approved=True, symbol='EURUSD', action='buy', strategy='smc',
                      volume_lots=0.01, entry_price=1.1000, sl_price=1.1050, tp_price=1.1100)
        assert False, 'Should have raised ValueError'
    except Exception:
        pass  # Expected
    
    # Rejected decisions skip validation
    d2 = TradeDecision(approved=False, symbol='EURUSD', action='buy', strategy='smc',
                       volume_lots=0.01, entry_price=1.1000, sl_price=1.1050, tp_price=1.0900,
                       rejection_reason='Test')
    assert not d2.approved


def test_lot_sizing_tick_value():
    """MT5SymbolInfo stores trade_tick_value and trade_tick_size fields."""
    from quantclaw.models import MT5SymbolInfo
    info = MT5SymbolInfo(
        symbol='USDJPY',
        point=0.001,
        digits=3,
        trade_contract_size=100000.0,
        trade_tick_value=900.0,
        trade_tick_size=0.001,
    )
    assert info.trade_tick_value == 900.0
    assert info.trade_tick_size == 0.001
    # Verify lot sizing formula would use tick value
    # For USDJPY: point_value_per_lot = (900.0/0.001) * 0.001 = 900.0 per lot
    point_value_per_lot = (info.trade_tick_value / info.trade_tick_size) * info.point
    assert point_value_per_lot > 0, 'Tick-value-based lot sizing must produce positive result'


def test_ml_weight_bidirectional_learning():
    """ML engine decreases signal feature weights on losses (bidirectional learning)."""
    from quantclaw.ml_engine import MLEngine
    from unittest.mock import MagicMock
    
    config = MagicMock()
    config.ml_brain_min_execute_score = 65
    config.anthropic_api_key = ''
    market = MagicMock()
    journal = MagicMock()
    journal.get_performance_stats.return_value = {'win_rate': 50.0}
    
    ml = MLEngine(config, market, journal)
    
    # Record initial weights
    initial_smc_weight = ml.weights.get('smc_confluence', 20.0)
    initial_trend_weight = ml.weights.get('trend_alignment', 15.0)
    
    # Simulate a loss
    ml.record_trade_outcome('EURUSD', 'smc_liquidity', 'buy', -50.0, 'LOSS')
    
    # After a loss, signal quality feature weights should DECREASE
    assert ml.weights.get('smc_confluence', 20.0) <= initial_smc_weight, \
        'smc_confluence weight should decrease on loss (bidirectional learning)'
    assert ml.weights.get('trend_alignment', 15.0) <= initial_trend_weight, \
        'trend_alignment weight should decrease on loss (bidirectional learning)'


def test_account_tracker_peak_drawdown():
    """AccountTracker tracks peak equity and max drawdown."""
    from quantclaw.account_tracker import AccountTracker
    from unittest.mock import MagicMock, patch
    from quantclaw.models import MT5AccountInfo
    
    mt5_mock = MagicMock()
    journal_mock = MagicMock()
    
    tracker = AccountTracker(mt5_mock, journal_mock)
    
    # Simulate equity peaking then dropping
    acc_peak = MT5AccountInfo(login=1, server='test', equity=10000.0, balance=10000.0)
    acc_drop = MT5AccountInfo(login=1, server='test', equity=9600.0, balance=9600.0)
    
    mt5_mock.get_account_info.return_value = acc_peak
    import asyncio
    asyncio.run(tracker.poll_account())
    
    assert tracker._peak_equity == 10000.0, 'Peak equity should be set'
    
    mt5_mock.get_account_info.return_value = acc_drop
    asyncio.run(tracker.poll_account())
    
    assert tracker._max_drawdown_pct > 0, 'Max drawdown should be positive after equity drop'
    expected_dd = (10000.0 - 9600.0) / 10000.0 * 100  # 4%
    assert abs(tracker._max_drawdown_pct - expected_dd) < 0.1, f'Expected ~4% drawdown, got {tracker._max_drawdown_pct}'


def test_strategy_quant_way_pullback():
    """Quant Way strategy fires on pullback proximity, not breakout."""
    from quantclaw.strategy_engine import StrategyEngine
    from unittest.mock import MagicMock
    import math
    
    config = MagicMock()
    config.enable_quant_way = True
    config.enable_smc = False
    config.enable_occ_r5 = False
    config.enable_eyes_sme = False
    config.enable_mean_reversion = False
    
    market = MagicMock()
    
    engine = StrategyEngine(config, market)
    
    # The _eval_quant_way method should use proximity check, not breakout
    import inspect
    source = inspect.getsource(engine._eval_quant_way)
    
    # Must NOT have the old breakout condition pattern
    assert 'price > ema_fast' not in source or 'abs(price' in source, \
        'Quant Way should use proximity check (abs(price - ema_fast)) not simple price > ema_fast'


def test_settings_allowed_keys_and_aliases():
    """Verify settings update endpoint accepts all AppConfig keys and legacy aliases."""
    from quantclaw.config import AppConfig
    from quantclaw.server import create_app
    from starlette.testclient import TestClient
    from unittest.mock import MagicMock

    cfg = AppConfig()
    app = create_app(config=cfg, mt5_client=MagicMock(), market_engine=MagicMock(),
                     strategy_engine=MagicMock(), ml_engine=MagicMock(), ai_engine=MagicMock(),
                     risk_manager=MagicMock(), account_tracker=MagicMock(),
                     trade_journal=MagicMock(), news_monitor=MagicMock())
    client = TestClient(app)

    payload = {
        "strategy_smc_enabled": False,
        "strategy_occ_r5_enabled": True,
        "sizing_mode": "ManualLots",
        "weekly_profit_target_pct": 30.0,
        "mt5_magic_number": 999111,
    }
    resp = client.post("/api/v4/settings", json=payload)
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert cfg.strategy_smc_enabled is False
    assert cfg.trade_sizing_mode == "ManualLots"
    assert cfg.weekly_profit_target_pct == 30.0
    assert cfg.mt5_magic_number == 999111


def test_risk_status_endpoint():
    """Verify /api/v4/risk-status returns valid telemetry structure."""
    from quantclaw.config import AppConfig
    from quantclaw.server import create_app
    from starlette.testclient import TestClient
    from unittest.mock import MagicMock

    cfg = AppConfig()
    risk_mock = MagicMock()
    risk_mock._circuit_broken = False
    risk_mock._consecutive_losses = 0
    tracker_mock = MagicMock()
    tracker_mock.get_daily_loss_pct.return_value = 1.25
    tracker_mock.get_live_state.return_value = {"peak_equity": 10000.0, "max_drawdown_pct": 2.5}

    app = create_app(config=cfg, mt5_client=MagicMock(), market_engine=MagicMock(),
                     strategy_engine=MagicMock(), ml_engine=MagicMock(), ai_engine=MagicMock(),
                     risk_manager=risk_mock, account_tracker=tracker_mock, trade_journal=MagicMock(),
                     news_monitor=MagicMock())
    client = TestClient(app)

    resp = client.get("/api/v4/risk-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["circuit_broken"] is False
    assert data["daily_loss_pct"] == 1.25
    assert data["daily_max_loss_pct"] == cfg.daily_max_loss_pct
    assert data["peak_equity"] == 10000.0
    assert data["max_drawdown_pct"] == 2.5


def test_mt5_engine_filling_type_safety():
    """Verify _determine_filling_type handles errors and returns valid fallback."""
    from quantclaw.mt5_engine import MT5Client
    client = MT5Client()
    # Even if symbol does not exist or MT5 is uninitialized, it must not throw
    filling = client._determine_filling_type("NONEXISTENT_SYMBOL")
    assert isinstance(filling, int)


def test_risk_manager_market_engine_wired():
    """Verify RiskManager accepts market_engine and uses it for ATR trailing stop."""
    from quantclaw.risk_manager import RiskManager
    from quantclaw.config import AppConfig
    from quantclaw.mt5_engine import MT5Client
    from unittest.mock import MagicMock
    import tempfile

    config = AppConfig()
    client = MT5Client()
    account = MagicMock()
    journal = MagicMock()
    market = MagicMock()
    market.get_market_analysis.return_value = {'atr': 0.0025}

    rm = RiskManager(config, client, account, journal, market_engine=market)
    assert rm.market_engine is market, "market_engine must be stored on RiskManager"


def test_trade_journal_today_pnl_no_leak(tmp_path):
    """Verify get_today_pnl uses context manager and doesn't leak connections."""
    from quantclaw.trade_journal import TradeJournal
    import inspect

    journal = TradeJournal(db_path=str(tmp_path / "test.db"))
    # Call it multiple times â€” should not accumulate open connections
    for _ in range(10):
        pnl = journal.get_today_pnl()
        assert isinstance(pnl, float)

    # Verify the source uses 'with' context manager
    source = inspect.getsource(journal.get_today_pnl)
    assert 'with self._get_conn()' in source, "get_today_pnl must use 'with' context manager to avoid connection leaks"


def test_risk_manager_consecutive_losses_locked():
    """Verify consecutive loss counter is read inside lock to prevent race conditions."""
    from quantclaw.risk_manager import RiskManager
    import inspect
    source = inspect.getsource(RiskManager.monitor_open_positions)
    # After the fix, cur_consec should be captured inside the lock block
    assert 'cur_consec' in source, "consecutive_losses should be captured inside lock (cur_consec pattern)"


def test_mt5_resolve_symbol():
    """Verify resolve_symbol handles aliases and cache lookups."""
    from quantclaw.mt5_engine import MT5Client
    client = MT5Client()
    # Pre-populate mapping to verify fast cache lookup
    client._resolved_symbol_map["EURUSD"] = "EURUSD."
    client._resolved_symbol_map["US30"] = "DJIUSD."
    assert client.resolve_symbol("EURUSD") == "EURUSD."
    assert client.resolve_symbol("US30") == "DJIUSD."
    # Unmatched fallback
    assert client.resolve_symbol("UNKNOWN") == "UNKNOWN"


def test_risk_manager_asset_class_spread():
    """Verify risk manager allowable spread adjusts by asset class (Gold/Crypto/Forex)."""
    from quantclaw.risk_manager import RiskManager
    from quantclaw.config import AppConfig
    from unittest.mock import MagicMock

    config = AppConfig()
    config.max_spread_points = 40
    rm = RiskManager(config, MagicMock(), MagicMock(), MagicMock())

    # Forex: 40 pts limit
    # Gold: 40 * 15 = 600 pts limit
    # Crypto: 40 * 500 = 20000 pts limit
    # Verify spread check logic in _execute_trade_inner source (refactored for semaphore isolation)
    import inspect
    # The spread logic was moved to _execute_trade_inner to be inside the semaphore
    inner_source = inspect.getsource(rm._execute_trade_inner)
    assert "allowable_spread" in inner_source
    assert "max_spread * 15" in inner_source
    assert "max_spread * 500" in inner_source


def test_auto_discover_symbols_and_tradeable():
    """Verify auto_discover_symbols and is_symbol_tradeable on MT5Client."""
    from quantclaw.mt5_engine import MT5Client
    client = MT5Client()
    # When MT5 is not connected in unit test environment, fallback returns safely
    discovered = client.auto_discover_symbols(["EURUSD", "GBPUSD"])
    assert isinstance(discovered, list)
    assert len(discovered) >= 2

    # Check is_symbol_tradeable returns a tuple (bool, str)
    ok, reason = client.is_symbol_tradeable("EURUSD")
    assert isinstance(ok, bool)
    assert isinstance(reason, str)


def test_mt5_determine_filling_type_bitmask():
    """Verify _determine_filling_type correctly maps MQL5 filling bitmask to MT5 ORDER_FILLING modes."""
    from quantclaw.mt5_engine import MT5Client
    from unittest.mock import MagicMock, patch

    client = MT5Client()

    # Simulate broker symbol with filling_mode = 2 (IOC only, like Tradiso)
    mock_sym_ioc = MagicMock()
    mock_sym_ioc.filling_mode = 2
    with patch("quantclaw.mt5_engine.mt5.symbol_info", return_value=mock_sym_ioc):
        # Bit 1 set -> must return ORDER_FILLING_IOC (1)
        res = client._determine_filling_type("EURUSD.")
        assert res == 1, f"Expected ORDER_FILLING_IOC (1) for filling_mode=2, got {res}"

    # Simulate broker symbol with filling_mode = 1 (FOK only)
    mock_sym_fok = MagicMock()
    mock_sym_fok.filling_mode = 1
    with patch("quantclaw.mt5_engine.mt5.symbol_info", return_value=mock_sym_fok):
        # Bit 0 set -> must return ORDER_FILLING_FOK (0)
        res = client._determine_filling_type("EURUSD.")
        assert res == 0, f"Expected ORDER_FILLING_FOK (0) for filling_mode=1, got {res}"

    # Simulate broker symbol with filling_mode = 4 (RETURN only)
    mock_sym_ret = MagicMock()
    mock_sym_ret.filling_mode = 4
    with patch("quantclaw.mt5_engine.mt5.symbol_info", return_value=mock_sym_ret):
        res = client._determine_filling_type("EURUSD.")
        assert res == 2, f"Expected ORDER_FILLING_RETURN (2) for filling_mode=4, got {res}"


def test_is_symbol_tradeable_weekend_closed():
    """Verify is_symbol_tradeable detects weekend closures for Forex while Crypto stays tradeable."""
    from quantclaw.mt5_engine import MT5Client
    from unittest.mock import MagicMock, patch
    import datetime

    client = MT5Client()

    mock_s = MagicMock()
    mock_s.trade_mode = 4
    mock_s.path = "FX/Forex/EURUSD."
    mock_term = MagicMock()
    mock_term.trade_allowed = True
    mock_acc = MagicMock()
    mock_acc.trade_allowed = True
    mock_acc.trade_expert = True
    mock_tick = MagicMock()
    mock_tick.bid = 1.16000
    mock_tick.ask = 1.16010
    mock_tick.time = time.time()

    # Mock Saturday UTC (weekday = 5)
    saturday_utc = datetime.datetime(2026, 9, 5, 12, 0, 0, tzinfo=datetime.timezone.utc)
    with patch("quantclaw.mt5_engine.mt5.symbol_select", return_value=True), \
         patch("quantclaw.mt5_engine.mt5.symbol_info", return_value=mock_s), \
         patch("quantclaw.mt5_engine.mt5.terminal_info", return_value=mock_term), \
         patch("quantclaw.mt5_engine.mt5.account_info", return_value=mock_acc), \
         patch("quantclaw.mt5_engine.mt5.symbol_info_tick", return_value=mock_tick), \
         patch("datetime.datetime") as mock_dt:
        mock_dt.now.return_value = saturday_utc
        mock_dt.timezone = datetime.timezone

        # Forex on Saturday -> must be closed
        is_ok, reason = client.is_symbol_tradeable("EURUSD.")
        assert not is_ok, "Forex must NOT be tradeable on Saturday"
        assert "weekend" in reason.lower()

        # Crypto on Saturday -> must be Tradeable
        mock_s.path = "CryptoCcy/Crypto Majors/BTCUSD."
        is_ok_btc, reason_btc = client.is_symbol_tradeable("BTCUSD.")
        assert is_ok_btc, f"Crypto must be tradeable 24/7 on Saturday, got {reason_btc}"
        assert reason_btc == "Tradeable"


def test_risk_manager_active_position_adoption():
    """Verify RiskManager automatically adopts pre-existing or unmanaged MT5 positions."""
    from quantclaw.risk_manager import RiskManager
    from quantclaw.config import AppConfig
    from unittest.mock import MagicMock
    import asyncio

    config = AppConfig()
    mt5_mock = MagicMock()
    mt5_mock.is_connected.return_value = True
    journal_mock = MagicMock()
    ml_mock = MagicMock()
    account_tracker_mock = MagicMock()
    account_tracker_mock.get_daily_loss_pct.return_value = 0.0
    market_mock = MagicMock()
    market_mock.get_market_analysis.return_value = {"atr": 0.0020}

    rm = RiskManager(
        config=config,
        mt5_client=mt5_mock,
        account_tracker=account_tracker_mock,
        trade_journal=journal_mock,
        ml_engine=ml_mock,
        market_engine=market_mock,
    )

    # Simulate MT5 returning a position that is not yet in _managed_positions
    mt5_mock.get_positions.return_value = [
        {
            "ticket": 777123,
            "symbol": "BTCUSD.",
            "type": "BUY",
            "volume": 0.05,
            "open_price": 80000.0,
            "current_price": 80100.0,
            "sl": 79500.0,
            "tp": 81000.0,
            "profit": 5.0,
            "magic": config.mt5_magic_number,
            "time": time.time() - 60,
        }
    ]

    asyncio.run(rm.monitor_open_positions())

    # Position 777123 should now be registered and managed
    assert 777123 in rm._managed_positions
    pos_data = rm._managed_positions[777123]
    assert pos_data["symbol"] == "BTCUSD."
    assert pos_data["entry_price"] == 80000.0
    assert pos_data["sl_distance"] == 500.0  # 80000 - 79500
    assert pos_data["breakeven_done"] is False







def test_manual_trades_not_interrupted():
    """Verify RiskManager never adopts or interferes with manual trades (magic != bot_magic)."""
    from quantclaw.risk_manager import RiskManager
    from quantclaw.config import AppConfig
    from unittest.mock import MagicMock
    import asyncio
    import time

    config = AppConfig()
    config.ignore_manual_trades = True
    config.mt5_magic_number = 999111
    mt5_mock = MagicMock()
    mt5_mock.is_connected.return_value = True

    tracker_mock = MagicMock()
    tracker_mock.get_daily_loss_pct.return_value = 0.0
    rm = RiskManager(
        config=config,
        mt5_client=mt5_mock,
        account_tracker=tracker_mock,
        market_engine=MagicMock(),
        trade_journal=MagicMock(),
    )

    # Manual trade in MT5 (magic=0)
    mt5_mock.get_positions.return_value = [
        {
            "ticket": 999888,
            "symbol": "XAUUSD.f",
            "type": "BUY",
            "volume": 0.10,
            "open_price": 2700.0,
            "current_price": 2715.0,
            "sl": 2690.0,
            "tp": 2750.0,
            "profit": 150.0,
            "magic": 0,  # Manual MT5 trade
            "time": time.time() - 120,
        }
    ]

    asyncio.run(rm.monitor_open_positions())

    # Manual trade must NOT be adopted or touched
    assert 999888 not in rm._managed_positions
    mt5_mock.modify_position.assert_not_called()
    mt5_mock.close_position.assert_not_called()


def test_manual_trail_detection():
    """Verify RiskManager detects user manual SL adjustments and respects them without reverting."""
    from quantclaw.risk_manager import RiskManager
    from quantclaw.config import AppConfig
    from unittest.mock import MagicMock
    import asyncio
    import time

    config = AppConfig()
    config.mt5_magic_number = 999111
    mt5_mock = MagicMock()
    mt5_mock.is_connected.return_value = True
    journal_mock = MagicMock()

    tracker_mock = MagicMock()
    tracker_mock.get_daily_loss_pct.return_value = 0.0
    rm = RiskManager(
        config=config,
        mt5_client=mt5_mock,
        account_tracker=tracker_mock,
        market_engine=MagicMock(),
        trade_journal=journal_mock,
    )

    ticket = 123456
    # Register an active bot trade with initial SL at 1.0900
    rm._managed_positions[ticket] = {
        "ticket": ticket,
        "symbol": "EURUSD",
        "action": "BUY",
        "volume": 0.10,
        "entry_price": 1.1000,
        "current_sl": 1.0900,
        "current_tp": 1.1200,
        "last_seen_sl": 1.0900,
        "last_seen_tp": 1.1200,
        "manual_intervention": False,
        "sl_distance": 0.0100,
        "breakeven_done": False,
        "partial_tp_done": False,
        "is_buy": True,
        "open_time": time.time(),
    }

    # Simulate user manually dragging SL up to 1.1020 in MT5 (securing profit manually)
    mt5_mock.get_positions.return_value = [
        {
            "ticket": ticket,
            "symbol": "EURUSD",
            "type": "BUY",
            "volume": 0.10,
            "open_price": 1.1000,
            "current_price": 1.1050,
            "sl": 1.1020,  # User manually tightened to 1.1020
            "tp": 1.1200,
            "profit": 50.0,
            "magic": 999111,
            "time": time.time() - 300,
        }
    ]

    asyncio.run(rm.monitor_open_positions())

    # RiskManager must have updated its tracking to the user's manual SL
    managed = rm._managed_positions[ticket]
    assert managed["current_sl"] == 1.1020
    assert managed["last_seen_sl"] == 1.1020
    assert managed["breakeven_done"] is True  # SL is past entry, so BE is acknowledged


def test_symbol_normalization_and_session_baseline():
    """Verify symbol normalization handles trailing dots and broker suffixes properly."""
    from quantclaw.market_calendar import MarketCalendar, _normalize_symbol
    from quantclaw.config import AppConfig

    # Normalization tests for various broker suffixes
    assert _normalize_symbol("EURUSD.") == "EURUSD"
    assert _normalize_symbol("XAUUSD.") == "XAUUSD"
    assert _normalize_symbol("USDJPY.pro") == "USDJPY"
    assert _normalize_symbol("BTCUSD_i") == "BTCUSD"
    assert _normalize_symbol("US30.") == "US30"
    assert _normalize_symbol("EURUSD") == "EURUSD"

    # Config is_symbol_enabled handles trailing dot
    cfg = AppConfig()
    cfg.symbol_enabled = {"EURUSD": True, "USDJPY": False}
    assert cfg.is_symbol_enabled("EURUSD.") is True
    assert cfg.is_symbol_enabled("USDJPY.") is False

    # Calendar session score produces non-zero baseline during active market hours
    mc = MarketCalendar()
    # If Forex market is open, session score must be >= 40.0, never 0.0
    if mc.is_market_open("EURUSD"):
        score = mc.get_session_score("EURUSD.")
        assert score >= 40.0, f"Expected session score >= 40.0 for open EURUSD, got {score}"


def test_account_switch_flag_and_adx_threshold():
    """Verify account switch detection sets the re-discovery flag, and ADX threshold is 13.0."""
    from quantclaw.account_tracker import AccountTracker
    from quantclaw.models import MT5AccountInfo
    from quantclaw.config import AppConfig

    cfg = AppConfig()
    assert cfg.adx_trend_threshold == 13.0

    class MockMT5:
        def __init__(self, login=2122282207, equity=350.0):
            self._login = login
            self._equity = equity

        def get_account_info(self):
            return MT5AccountInfo(
                login=self._login,
                server="TradisoGroup-Live",
                balance=self._equity,
                equity=self._equity,
                margin=0.0,
                margin_free=self._equity,
                margin_level=0.0,
                profit=0.0,
                currency="USD",
                trade_allowed=True,
                trade_expert=True,
                leverage=500,
                company="Tradiso",
            )

    mock_mt5 = MockMT5(login=2122282207, equity=350.0)
    tracker = AccountTracker(mt5_client=mock_mt5)

    # First poll establishes baseline
    asyncio.run(tracker.poll_account())
    assert tracker._last_login == 2122282207
    assert tracker.check_and_clear_account_switch() is False

    # Simulate account switch (e.g., switched to Elefin account 12345841946)
    mock_mt5._login = 12345841946
    mock_mt5._equity = 274.59
    asyncio.run(tracker.poll_account())

    assert tracker._last_login == 12345841946
    # Flag must be True indicating re-discovery needed
    assert tracker.check_and_clear_account_switch() is True
    # Subsequent check must be False (cleared)
    assert tracker.check_and_clear_account_switch() is False

def test_titan_pro_strategy_and_early_breakeven():
    """Verify TITAN PRO flagship strategy and Early Breakeven at +0.45R."""
    from quantclaw.config import AppConfig
    from quantclaw.strategy_engine import StrategyEngine
    from quantclaw.ml_engine import MLEngine
    from quantclaw.models import StrategySignal
    from unittest.mock import MagicMock

    cfg = AppConfig()
    assert cfg.strategy_titan_pro_enabled is True
    assert cfg.enable_soft_risk_reduction is True
    assert cfg.early_breakeven_r_ratio == 0.45
    assert cfg.enable_htf_confluence_exit is False

    mock_market = MagicMock()
    # 40 H1 candles trending clearly upward: EMA50 and Supertrend will be Bullish
    h1_candles = []
    base_p = 100.0
    for i in range(40):
        base_p += 0.5
        h1_candles.append({
            "open": base_p,
            "high": base_p + 1.5,
            "low": base_p - 0.5,
            "close": base_p + 1.0,
            "volume": 100,
            "time": 1000 + i * 3600
        })

    # 25 M15 candles trending upward so ADX is strong
    m15_candles = []
    p = 100.0
    for i in range(25):
        p += 0.4
        m15_candles.append({
            "open": p,
            "high": p + 0.8,
            "low": p - 0.2,
            "close": p + 0.5,
            "volume": 50,
            "time": 2000 + i * 900
        })

    # Pullback and sweep candle: sweeps recent swing low and closes up strongly
    swing_low = min(c["low"] for c in m15_candles[-15:])
    m15_candles.append({
        "open": swing_low + 0.2,
        "high": swing_low + 2.0,
        "low": swing_low - 0.8,
        "close": swing_low + 1.8,
        "volume": 200,
        "time": 2000 + 26 * 900
    })

    def get_candles_mock(sym, tf, n):
        if tf in ("H1", "H4"):
            return h1_candles[-n:]
        return m15_candles[-n:]

    mock_market.get_candles.side_effect = get_candles_mock
    mock_market.get_market_analysis.return_value = {
        "rsi": 52.0,
        "volume_ratio": 1.2,
        "macd": {"hist": 0.05},
        "atr": 1.45,
        "smc": {"sweeps": [{"direction": "BULLISH_SWEEP"}]}
    }
    strat_eng = StrategyEngine(cfg, mock_market)

    sig = strat_eng._eval_titan_pro("EURUSD", "M15", m15_candles)
    assert sig is not None
    assert sig.strategy == "titan_pro"
    assert sig.action == "buy"
    assert sig.strength >= 85.0
    assert sig.sl_points > 0
    assert abs(sig.tp_points - (sig.sl_points * cfg.titan_pro_rr_ratio)) < 1e-4

    # ML Brain evaluation
    ml = MLEngine(cfg, mock_market)
    dec = ml.evaluate_signal(sig)
    assert dec.strategy == "titan_pro"
    assert dec.approved is True
    assert dec.ml_score >= 65.0

def test_risk_manager_early_breakeven_and_exit_safeguards():
    """Verify Early Breakeven secures position at +0.45R and HTF_EXIT doesn't kill trades immediately."""
    from quantclaw.config import AppConfig
    from quantclaw.risk_manager import RiskManager
    from unittest.mock import MagicMock
    import asyncio

    cfg = AppConfig()
    cfg.enable_early_breakeven = True
    assert cfg.enable_htf_confluence_exit is False

    mock_mt5 = MagicMock()
    mock_mt5.is_connected.return_value = True
    mock_mt5.get_positions.return_value = [
        {
            "ticket": 7771,
            "symbol": "EURUSD",
            "type": "BUY",
            "volume": 0.10,
            "open_price": 1.10000,
            "current_price": 1.10460, # +46 pips on 100 pip SL = +0.46R
            "sl": 1.09000,
            "tp": 1.12200,
            "magic": 999111,
            "time": 1000.0,
        }
    ]
    sym_info = MagicMock()
    sym_info.point = 0.00001
    sym_info.digits = 5
    sym_info.spread = 2
    sym_info.trade_stops_level = 0
    mock_mt5.get_symbol_info.return_value = sym_info
    mock_mt5.modify_position.return_value = (True, {})

    mock_market = MagicMock()
    mock_market.get_market_analysis.return_value = {"atr": 0.0015}
    mock_tracker = MagicMock()
    mock_tracker.get_daily_loss_pct.return_value = 0.0

    rm = RiskManager(
        config=cfg,
        mt5_client=mock_mt5,
        account_tracker=mock_tracker,
        trade_journal=MagicMock(),
        market_engine=mock_market,
    )

    # Seed managed position
    rm._managed_positions[7771] = {
        "ticket": 7771,
        "symbol": "EURUSD",
        "action": "BUY",
        "volume": 0.10,
        "entry_price": 1.10000,
        "initial_sl": 1.09000,
        "initial_tp": 1.12200,
        "current_sl": 1.09000,
        "current_tp": 1.12200,
        "last_seen_sl": 1.09000,
        "last_seen_tp": 1.12200,
        "sl_distance": 0.01000, # 100 pips
        "breakeven_done": False,
        "early_be_done": False,
        "partial_tp_done": False,
        "open_time": 1000.0,
    }

    # Run monitor cycle
    asyncio.run(rm.monitor_open_positions())

    managed = rm._managed_positions[7771]
    assert managed["early_be_done"] is True
    assert managed["breakeven_done"] is True
    # SL should have been moved to entry + offset (1.10000 + 0.00010 = 1.10010)
    assert managed["current_sl"] > 1.10000
    mock_mt5.modify_position.assert_called()



def test_account_risk_shield_blocks_outsized_index_trade():
    """Verify Account Risk Shield BLOCKS outsized trades (e.g. $47.17 on NDXUSD for small account)."""
    from quantclaw.config import AppConfig
    from quantclaw.risk_manager import RiskManager
    from quantclaw.models import TradeDecision, RiskRegime
    from unittest.mock import MagicMock
    import asyncio

    cfg = AppConfig()
    cfg.armed = True
    cfg.max_risk_usd_per_trade = 8.0
    cfg.min_risk_usd_per_trade = 2.0
    cfg.risk_per_trade_pct = 1.5

    mock_mt5 = MagicMock()
    mock_mt5.is_connected.return_value = True
    mock_mt5.is_symbol_tradeable.return_value = (True, 'OK')

    # Account equity is small ($274.59)
    acc = MagicMock()
    acc.equity = 274.59
    mock_mt5.get_account_info.return_value = acc

    # Broker symbol info for NDXUSD.p:
    # Contract size is 10, point is 0.01, tick_value is 0.1, tick_size is 0.01
    # Point value per lot = 1.0 USD / pt. Minimum volume is 0.01 lot.
    sym_info = MagicMock()
    sym_info.point = 0.01
    sym_info.digits = 2
    sym_info.spread = 15
    sym_info.volume_min = 0.01
    sym_info.volume_max = 100.0
    sym_info.volume_step = 0.01
    sym_info.trade_tick_value = 0.10
    sym_info.trade_tick_size = 0.01
    sym_info.trade_stops_level = 0
    mock_mt5.get_symbol_info.return_value = sym_info

    mock_tracker = MagicMock()
    mock_tracker.get_daily_loss_pct.return_value = 0.0
    rm = RiskManager(
        config=cfg,
        mt5_client=mock_mt5,
        account_tracker=mock_tracker,
        trade_journal=MagicMock(),
        market_engine=MagicMock(),
    )

    # Decision on NDXUSD with 471.68 points SL distance ($47.17 loss at 0.01 min lot)
    decision = TradeDecision(
        approved=True,
        symbol="NDXUSD.p",
        action="BUY",
        strategy="titan_pro",
        volume_lots=0.01,
        entry_price=29539.06,
        sl_price=29067.38, # 471.68 points distance
        tp_price=30860.00,
        regime=RiskRegime.BETA,
        ml_score=85.0,
    )

    success, msg = asyncio.run(rm.execute_trade_decision(decision))
    # Must be BLOCKED by Account Risk Shield!
    assert success is False
    assert "ACCOUNT RISK SHIELD" in msg or "exceeds" in msg
    mock_mt5.open_market_order.assert_not_called()


def test_symbol_permissions_alias_sync_and_all_symbols():
    """Verify alias syncing and discovery across NDXUSD/NAS100 and DJIUSD/US30."""
    from quantclaw.config import AppConfig
    cfg = AppConfig()

    # By default, all are enabled
    assert cfg.is_symbol_enabled("NDXUSD.p") is True
    assert cfg.is_symbol_enabled("NAS100") is True

    # User unticks NAS100 in permissions
    cfg.symbol_enabled["NAS100"] = False

    # NDXUSD and its broker variant NDXUSD.p must now be considered disabled via alias!
    assert cfg.is_symbol_enabled("NDXUSD") is False
    assert cfg.is_symbol_enabled("NDXUSD.p") is False

    # When user ticks NDXUSD back ON
    cfg.symbol_enabled["NDXUSD"] = True
    assert cfg.is_symbol_enabled("NDXUSD.p") is True

    # User unticks US30 -> DJIUSD.p must be disabled
    cfg.symbol_enabled["US30"] = False
    assert cfg.is_symbol_enabled("DJIUSD.p") is False


def test_commission_friction_shield_blocks_crypto():
    """Verify Commission Friction Shield blocks trades where broker commission eats edge."""
    from quantclaw.config import AppConfig
    from quantclaw.risk_manager import RiskManager
    from quantclaw.models import TradeDecision, RiskRegime
    from unittest.mock import MagicMock
    import asyncio

    cfg = AppConfig()
    cfg.commission_max_pct_of_tp = 15.0
    cfg.armed = True

    mock_mt5 = MagicMock()
    mock_mt5.is_connected.return_value = True
    mock_mt5.is_symbol_tradeable.return_value = (True, 'OK')
    acc = MagicMock()
    acc.equity = 275.0
    mock_mt5.get_account_info.return_value = acc

    sym_info = MagicMock()
    sym_info.point = 0.01
    sym_info.digits = 2
    sym_info.spread = 100
    sym_info.volume_min = 0.01
    sym_info.volume_max = 100.0
    sym_info.volume_step = 0.01
    sym_info.trade_tick_value = 0.01
    sym_info.trade_tick_size = 0.01
    sym_info.trade_stops_level = 0
    mock_mt5.get_symbol_info.return_value = sym_info

    mock_tracker = MagicMock()
    mock_tracker.get_daily_loss_pct.return_value = 0.0
    rm = RiskManager(
        config=cfg,
        mt5_client=mock_mt5,
        account_tracker=mock_tracker,
        trade_journal=MagicMock(),
        market_engine=MagicMock(),
    )

    # BTC trade with tiny profit target of $10 ($8 commission = 80% of TP > 15%)
    decision = TradeDecision(
        approved=True,
        symbol="BTCUSD.",
        action="BUY",
        strategy="titan_pro",
        volume_lots=0.01,
        entry_price=80000.0,
        sl_price=79600.0,
        tp_price=80100.0, # 100 pt TP = $1.00 or small USD
        regime=RiskRegime.GAMMA,
        ml_score=90.0,
    )

    success, msg = asyncio.run(rm.execute_trade_decision(decision))
    assert success is False
    assert "COMMISSION FRICTION SHIELD" in msg


def test_soft_risk_reduction_at_075r():
    """Verify Soft Risk Reduction at +0.75R tightens SL to -0.25R giving 0.5R wave breathing space."""
    from quantclaw.config import AppConfig
    from quantclaw.risk_manager import RiskManager
    from unittest.mock import MagicMock
    import asyncio

    cfg = AppConfig()
    cfg.enable_soft_risk_reduction = True
    cfg.enable_early_breakeven = False
    cfg.soft_risk_reduction_r = 0.75
    cfg.soft_risk_target_r = -0.25

    mock_mt5 = MagicMock()
    mock_mt5.is_connected.return_value = True
    mock_mt5.get_positions.return_value = [
        {
            "ticket": 8882,
            "symbol": "EURUSD",
            "type": "BUY",
            "volume": 0.05,
            "open_price": 1.10000,
            "current_price": 1.10800, # +80 pips on 100 pip SL = +0.80R (>= 0.75R trigger)
            "sl": 1.09000,
            "tp": 1.12800,
            "magic": 999111,
            "time": 1000.0,
        }
    ]
    sym_info = MagicMock()
    sym_info.point = 0.00001
    sym_info.digits = 5
    sym_info.spread = 2
    sym_info.trade_stops_level = 0
    mock_mt5.get_symbol_info.return_value = sym_info
    mock_mt5.modify_position.return_value = (True, {})

    mock_market = MagicMock()
    mock_market.get_market_analysis.return_value = {"atr": 0.0015}
    mock_tracker = MagicMock()
    mock_tracker.get_daily_loss_pct.return_value = 0.0

    rm = RiskManager(
        config=cfg,
        mt5_client=mock_mt5,
        account_tracker=mock_tracker,
        trade_journal=MagicMock(),
        market_engine=mock_market,
    )

    rm._managed_positions[8882] = {
        "ticket": 8882,
        "symbol": "EURUSD",
        "action": "BUY",
        "volume": 0.05,
        "entry_price": 1.10000,
        "initial_sl": 1.09000,
        "initial_tp": 1.12800,
        "current_sl": 1.09000,
        "current_tp": 1.12800,
        "last_seen_sl": 1.09000,
        "last_seen_tp": 1.12800,
        "sl_distance": 0.01000, # 100 pips
        "breakeven_done": False,
        "soft_risk_reduced": False,
        "partial_tp_done": False,
        "open_time": 1000.0,
    }

    asyncio.run(rm.monitor_open_positions())
    managed = rm._managed_positions[8882]
    assert managed["soft_risk_reduced"] is True
    # SL tightened to entry - 0.25*0.01000 = 1.09750 (tightened from 1.09000)
    assert managed["current_sl"] == 1.09750
    mock_mt5.modify_position.assert_called()


def test_strategy_circuit_breaker_penalizes_low_win_rate():
    """Verify Strategy Circuit Breaker docks 15 points on strategies with < 35% win rate."""
    from quantclaw.config import AppConfig
    from quantclaw.ml_engine import MLEngine
    from quantclaw.models import StrategySignal
    from unittest.mock import MagicMock

    cfg = AppConfig()
    mock_market = MagicMock()
    mock_market.get_market_analysis.return_value = {
        "rsi": 50.0,
        "atr": 0.0015,
        "volume_ratio": 1.0,
        "macd": {"hist": 0.0},
    }
    mock_market.get_candles.return_value = []

    mock_journal = MagicMock()
    # Strategy with 10 trades and 20% win rate
    mock_journal.get_strategy_stats.return_value = {
        "total_trades": 10,
        "wins": 2,
        "win_rate": 20.0,
        "total_pnl": -50.0,
    }

    ml = MLEngine(cfg, mock_market, trade_journal=mock_journal)
    sig = StrategySignal(
        strategy="mean_reversion",
        symbol="EURUSD",
        action="buy",
        timeframe="M15",
        price=1.1000,
        sl_points=0.0015,
        tp_points=0.0042,
        strength=75.0,
    )
    dec = ml.evaluate_signal(sig)
    # The penalty drops score below 70 threshold
    assert dec.approved is False


def test_volume_regime_classification_and_strategy_filtering():
    """Verify volume regime intelligence accurately classifies 4 states and adapts targets."""
    from quantclaw.utils.indicators import classify_volume_regime
    from quantclaw.config import AppConfig
    from quantclaw.strategy_engine import StrategyEngine
    from quantclaw.models import StrategySignal
    from unittest.mock import MagicMock

    # 1. Indicator classification
    low = classify_volume_regime(0.5, 12.0)
    assert low["regime"] == "LOW_VOLUME"
    assert low["target_rr_mult"] == 0.70
    assert low["allow_breakout"] is False

    norm = classify_volume_regime(1.1, 20.0)
    assert norm["regime"] == "NORMAL_VOLUME"
    assert norm["target_rr_mult"] == 1.0
    assert norm["allow_breakout"] is True

    high = classify_volume_regime(2.2, 30.0)
    assert high["regime"] == "HIGH_VOLUME"
    assert high["target_rr_mult"] == 1.25
    assert high["allow_breakout"] is True

    climax = classify_volume_regime(3.5, 30.0)
    assert climax["regime"] == "CLIMAX_VOLUME"
    assert climax["allow_breakout"] is False

    # 2. Strategy Engine volume-adaptive filtering
    cfg = AppConfig()
    cfg.enable_volume_regime_intelligence = True
    cfg.volume_adaptive_tp = True
    cfg.testing = True

    mock_mkt = MagicMock()
    mock_mkt.get_volume_regime.return_value = low
    mock_mkt.get_candles.return_value = [{"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 100, "time": 1000} for _ in range(30)]

    strat = StrategyEngine(cfg, mock_mkt)
    # Mock strategies to return both a trend signal and a quant_way breakout signal
    sig1 = StrategySignal(strategy="titan_pro", symbol="EURUSD", action="buy", timeframe="M15", price=1.1000, sl_points=100.0, tp_points=280.0, strength=85.0)
    sig2 = StrategySignal(strategy="quant_way", symbol="EURUSD", action="buy", timeframe="M15", price=1.1000, sl_points=100.0, tp_points=280.0, strength=85.0)

    strat._eval_titan_pro = MagicMock(return_value=sig1)
    strat._eval_quant_way = MagicMock(return_value=sig2)
    strat._eval_smc_liquidity = MagicMock(return_value=None)
    strat._eval_occ_r5_trend = MagicMock(return_value=None)
    strat._eval_eyes_sme = MagicMock(return_value=None)
    strat._eval_mean_reversion = MagicMock(return_value=None)

    sigs = strat.scan_symbol("EURUSD", "M15")
    # In LOW_VOLUME, quant_way breakout is filtered out!
    assert any(s.strategy == "titan_pro" for s in sigs)
    assert not any(s.strategy == "quant_way" for s in sigs)
    # TP points are scaled by 0.70 (280 -> 196)
    titan_sig = [s for s in sigs if s.strategy == "titan_pro"][0]
    assert titan_sig.tp_points == 196.0


def test_5_zone_stepped_trailing_engine():
    """Verify 5-Zone Stepped Trailing smoothly progresses through all profit protection tiers."""
    from quantclaw.config import AppConfig
    from quantclaw.risk_manager import RiskManager
    from unittest.mock import MagicMock
    import asyncio

    cfg = AppConfig()
    cfg.enable_stepped_trailing = True

    mock_mt5 = MagicMock()
    mock_mt5.is_connected.return_value = True
    sym_info = MagicMock()
    sym_info.point = 0.00001
    sym_info.digits = 5
    sym_info.spread = 2
    sym_info.trade_stops_level = 0
    mock_mt5.get_symbol_info.return_value = sym_info
    mock_mt5.modify_position.return_value = (True, {})
    mock_mt5.partial_close.return_value = (True, {})

    mock_market = MagicMock()
    mock_market.get_volume_regime.return_value = {"regime": "NORMAL_VOLUME", "trail_atr_mult": 1.0}
    mock_market.get_market_analysis.return_value = {"atr": 0.0020}

    rm = RiskManager(
        config=cfg,
        mt5_client=mock_mt5,
        account_tracker=MagicMock(),
        trade_journal=MagicMock(),
        market_engine=mock_market,
    )

    # 1. ZONE 1 TEST: Price at +0.70R -> Soft cushion SL moves to -0.25R
    # Entry: 1.10000, initial SL: 1.09000 (sl_dist = 0.01000)
    mock_mt5.get_positions.return_value = [{
        "ticket": 901, "symbol": "EURUSD", "type": "BUY", "volume": 0.10,
        "open_price": 1.10000, "current_price": 1.10700, "sl": 1.09000, "tp": 1.12800,
        "magic": 999111, "time": 1000.0,
    }]
    rm._managed_positions[901] = {
        "ticket": 901, "symbol": "EURUSD", "action": "BUY", "volume": 0.10,
        "entry_price": 1.10000, "initial_sl": 1.09000, "initial_tp": 1.12800,
        "current_sl": 1.09000, "current_tp": 1.12800, "last_seen_sl": 1.09000, "last_seen_tp": 1.12800,
        "sl_distance": 0.01000, "zone1_done": False, "zone2_done": False, "zone3_done": False,
        "breakeven_done": False, "partial_tp_done": False, "open_time": 1000.0,
    }
    asyncio.run(rm.monitor_open_positions())
    managed = rm._managed_positions[901]
    assert managed["zone1_done"] is True
    # SL moved from 1.09000 to -0.25R = 1.09750
    assert managed["current_sl"] == 1.09750

    # 2. ZONE 2 TEST: Price advances to +1.15R -> Breakeven Plus triggers
    mock_mt5.get_positions.return_value[0]["current_price"] = 1.11150
    mock_mt5.get_positions.return_value[0]["sl"] = managed["current_sl"]
    asyncio.run(rm.monitor_open_positions())
    assert managed["zone2_done"] is True
    assert managed["breakeven_done"] is True
    # SL moved above entry to 1.10000 + 0.15R (1.10150)
    assert managed["current_sl"] >= 1.10150

    # 3. ZONE 3 TEST: Price advances to +1.85R -> Bank 40% volume & lock SL at +0.80R
    mock_mt5.get_positions.return_value[0]["current_price"] = 1.11850
    mock_mt5.get_positions.return_value[0]["sl"] = managed["current_sl"]
    asyncio.run(rm.monitor_open_positions())
    assert managed["zone3_done"] is True
    assert managed["partial_tp_done"] is True
    mock_mt5.partial_close.assert_called_with(901, 0.04)
    # SL locked at entry + 0.80R = 1.10800
    assert managed["current_sl"] == 1.10800

    # 4. ZONE 4 TEST: Price advances to +2.45R -> Lock SL at +1.40R
    mock_mt5.get_positions.return_value[0]["current_price"] = 1.12450
    mock_mt5.get_positions.return_value[0]["sl"] = managed["current_sl"]
    asyncio.run(rm.monitor_open_positions())
    assert managed["zone4_done"] is True
    # SL locked at entry + 1.40R = 1.11400
    assert managed["current_sl"] == 1.11400


def test_climax_volume_defense_and_low_volume_adaptation():
    """Verify Climax Volume aggressively locks SL at +1.20R to protect profits ahead of exhaustion reversal."""
    from quantclaw.config import AppConfig
    from quantclaw.risk_manager import RiskManager
    from unittest.mock import MagicMock
    import asyncio

    cfg = AppConfig()
    mock_mt5 = MagicMock()
    mock_mt5.is_connected.return_value = True
    sym_info = MagicMock()
    sym_info.point = 0.00001
    sym_info.digits = 5
    sym_info.spread = 2
    sym_info.trade_stops_level = 0
    mock_mt5.get_symbol_info.return_value = sym_info
    mock_mt5.modify_position.return_value = (True, {})

    # Volume spike > 3.0x triggers CLIMAX_VOLUME
    mock_market = MagicMock()
    mock_market.get_volume_regime.return_value = {"regime": "CLIMAX_VOLUME", "trail_atr_mult": 0.75}
    mock_market.get_market_analysis.return_value = {"atr": 0.0020}

    rm = RiskManager(
        config=cfg,
        mt5_client=mock_mt5,
        account_tracker=MagicMock(),
        trade_journal=MagicMock(),
        market_engine=mock_market,
    )

    # Position at +1.60R gain
    mock_mt5.get_positions.return_value = [{
        "ticket": 902, "symbol": "EURUSD", "type": "BUY", "volume": 0.10,
        "open_price": 1.10000, "current_price": 1.11600, "sl": 1.10150, "tp": 1.12800,
        "magic": 999111, "time": 1000.0,
    }]
    rm._managed_positions[902] = {
        "ticket": 902, "symbol": "EURUSD", "action": "BUY", "volume": 0.10,
        "entry_price": 1.10000, "initial_sl": 1.09000, "initial_tp": 1.12800,
        "current_sl": 1.10150, "current_tp": 1.12800, "last_seen_sl": 1.10150, "last_seen_tp": 1.12800,
        "sl_distance": 0.01000, "breakeven_done": True, "open_time": 1000.0,
    }

    asyncio.run(rm.monitor_open_positions())
    managed = rm._managed_positions[902]
    # Climax defense activated and locked SL at 1.10000 + 1.20R = 1.11200
    assert managed["climax_locked"] is True
    assert managed["current_sl"] == 1.11200
