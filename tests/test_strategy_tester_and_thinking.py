import pytest
from unittest.mock import MagicMock
from quantclaw.strategy_tester import StrategyTester
from quantclaw.market_thinking import MarketThinkingEngine
from quantclaw.config import AppConfig

def test_strategy_tester_backtest_and_optimizer():
    mock_mt5 = MagicMock()
    mock_mt5.is_connected.return_value = True

    # Generate 100 sample bars
    bars = []
    base_price = 1.1000
    for i in range(100):
        o = base_price + (i % 5) * 0.0005
        h = o + 0.0010
        l = o - 0.0010
        c = o + 0.0002
        bars.append({"open": o, "high": h, "low": l, "close": c, "volume": 100, "time": i * 900})

    mock_mkt = MagicMock()
    mock_mkt.get_candles.return_value = bars

    cfg = AppConfig()
    tester = StrategyTester(config=cfg, mt5_client=mock_mt5, market_engine=mock_mkt)

    # 1. Backtest single strategy simulation
    res = tester.run_backtest_simulation("EURUSD", bars, "titan_pro")
    assert "win_rate" in res
    assert "total_trades" in res
    assert "profit_factor" in res
    assert "expectancy" in res

    # 2. Run permutation grid search optimizer
    opt_res = tester.run_permutation_optimizer("EURUSD", "M15", bars=50)
    assert "best_permutation" in opt_res
    assert "permutations" in opt_res
    assert len(opt_res["permutations"]) > 0
    best = opt_res["best_permutation"]
    assert "lookback" in best
    assert "rr" in best

def test_market_thinking_narrative_and_permutations():
    mock_mt5 = MagicMock()
    mock_mt5.is_connected.return_value = True

    bars = []
    base = 1.1000
    for i in range(50):
        bars.append({"open": base, "high": base + 0.0008, "low": base - 0.0004, "close": base + 0.0003, "volume": 120, "time": i * 900})

    mock_mkt = MagicMock()
    mock_mkt.get_candles.return_value = bars
    mock_mkt.get_volume_regime.return_value = {"regime": "HIGH_VOLUME"}

    mock_risk = MagicMock()
    mock_risk._managed_positions = {}

    cfg = AppConfig()
    engine = MarketThinkingEngine(config=cfg, market_engine=mock_mkt, risk_manager=mock_risk, mt5_client=mock_mt5)

    perms_data = engine.generate_symbol_thinking("EURUSD", "M15")
    assert perms_data["symbol"] == "EURUSD"
    assert "narrative" in perms_data
    assert len(perms_data["narrative"]) > 10
    assert len(perms_data["permutations"]) >= 3

    for p in perms_data["permutations"]:
        assert 0 <= p["probability"] <= 100

def test_market_thinking_in_trade_supervision():
    mock_mt5 = MagicMock()
    mock_mt5.is_connected.return_value = True
    mock_mkt = MagicMock()
    mock_risk = MagicMock()

    # Simulate an open position in profit
    mock_risk._managed_positions = {
        101: {
            "ticket": 101,
            "symbol": "EURUSD",
            "action": "BUY",
            "entry_price": 1.1000,
            "sl_distance": 0.0020,
            "strategy": "titan_pro",
            "zone3_done": True,
            "zone2_done": True,
            "zone1_done": True,
            "breakeven_done": True,
            "active": True,
        }
    }
    mock_mt5.get_positions.return_value = [
        {"ticket": 101, "symbol": "EURUSD", "type": "BUY", "open_price": 1.1000, "current_price": 1.1030}
    ]

    cfg = AppConfig()
    engine = MarketThinkingEngine(config=cfg, market_engine=mock_mkt, risk_manager=mock_risk, mt5_client=mock_mt5)
    summary = engine.get_all_symbols_summary(["EURUSD"])

    assert "in_trade_supervision" in summary
    assert len(summary["in_trade_supervision"]) == 1
    t = summary["in_trade_supervision"][0]
    assert t["ticket"] == 101
    assert t["current_r"] == 1.5
    assert t["live_win_prob"] >= 75
    assert "SWEET-SPOT" in t["setup_health"] or "RUNNER" in t["setup_health"]

@pytest.mark.asyncio
async def test_early_invalidation_cut_and_trade_classification():
    from quantclaw.risk_manager import RiskManager
    from quantclaw.trade_journal import TradeJournal
    from quantclaw.models import TradeDecision, RiskRegime
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    journal = TradeJournal(db_path=db_path)
    mock_mt5 = MagicMock()
    mock_mt5.is_connected.return_value = True
    mock_tracker = MagicMock()
    mock_tracker.get_daily_loss_pct.return_value = 0.0

    cfg = AppConfig()
    cfg.testing = True
    cfg.enable_early_invalidation_cut = True
    cfg.invalidation_cut_min_r = -0.30

    risk = RiskManager(config=cfg, mt5_client=mock_mt5, account_tracker=mock_tracker, trade_journal=journal)

    # 1. Test position adoption with invalidation price
    ticket = 8881
    entry = 1.1000
    sl = 1.0960 # 40 points SL
    inv_p = 1.0985 # Invalidation level

    # Pre-record open trade in journal
    journal.record_open_trade(
        ticket=ticket,
        symbol="EURUSD",
        action="BUY",
        volume=0.10,
        entry_price=entry,
        sl=sl,
        tp=1.1100,
        strategy="titan_pro",
        ml_score=85.0
    )

    risk._managed_positions[ticket] = {
        "ticket": ticket,
        "symbol": "EURUSD",
        "action": "BUY",
        "entry_price": entry,
        "initial_sl": sl,
        "current_sl": sl,
        "sl_distance": 0.0040,
        "invalidation_price": inv_p,
        "breakeven_done": False,
        "volume": 0.10,
    }

    # Simulate position dropped to 1.0980 (R = -0.50, breaches inv_p 1.0985)
    mock_mt5.get_positions.return_value = [
        {"ticket": ticket, "symbol": "EURUSD", "type": "BUY", "open_price": entry, "current_price": 1.0980, "sl": sl, "tp": 1.1100, "volume": 0.10, "profit": -2.0}
    ]

    await risk.monitor_open_positions()

    # Verify close_position was called early to preserve capital
    mock_mt5.close_position.assert_called_with(ticket, 0.10)
    assert risk._managed_positions[ticket].get("struct_cut_done") is True

    # 2. Simulate position closure in MT5 and verify post-trade classification
    mock_mt5.get_positions.return_value = []
    mock_mt5.get_history_deals.return_value = {"net_pnl": -2.0, "close_price": 1.0980}

    await risk.monitor_open_positions()

    # Query journal to verify outcome_tag
    trades = journal.get_recent_trades(limit=5)
    assert len(trades) >= 1
    t = [tr for tr in trades if tr["ticket"] == ticket][0]
    assert t["outcome_tag"] == "STRUCTURE_INVALIDATED"
    assert "Early loss cut" in t["review_notes"]

@pytest.mark.asyncio
async def test_expectancy_adaptive_sizing_and_weekend_gap_shield():
    from quantclaw.risk_manager import RiskManager
    from quantclaw.models import TradeDecision, RiskRegime
    from unittest.mock import AsyncMock

    mock_mt5 = MagicMock()
    mock_mt5.is_connected.return_value = True
    mock_mt5.is_symbol_tradeable.return_value = (True, "OK")
    mock_mt5.get_positions.return_value = []
    mock_tracker = MagicMock()
    mock_tracker.get_daily_loss_pct.return_value = 0.0
    mock_journal = MagicMock()
    
    mock_acc = MagicMock()
    mock_acc.equity = 300.0
    mock_acc.balance = 300.0
    mock_mt5.get_account_info.return_value = mock_acc

    sym_info = MagicMock()
    sym_info.point = 0.00001
    sym_info.spread = 10
    sym_info.trade_tick_value = 1.0
    sym_info.trade_tick_size = 0.00001
    sym_info.volume_min = 0.01
    sym_info.volume_max = 100.0
    sym_info.volume_step = 0.01
    mock_mt5.get_symbol_info.return_value = sym_info
    mock_mt5.open_market_order.return_value = (True, {'ticket': 9999, 'price': 1.1000})

    mock_tester = MagicMock()
    # High expectancy
    mock_tester.get_optimal_params.return_value = {"expectancy": 0.85, "profit_factor": 2.2, "lookback": 15, "rr": 2.8}

    cfg = AppConfig()
    cfg.armed = True
    cfg.testing = True
    cfg.enable_expectancy_adaptive_sizing = True
    cfg.enable_session_filter = False
    cfg.enable_news_filter = False

    risk = RiskManager(config=cfg, mt5_client=mock_mt5, account_tracker=mock_tracker, trade_journal=mock_journal)
    risk.strategy_tester = mock_tester

    decision = TradeDecision(
        approved=True,
        symbol="EURUSD",
        action="BUY",
        strategy="titan_pro",
        volume_lots=0.10,
        entry_price=1.1000,
        sl_price=1.0960,
        tp_price=1.1112,
        regime=RiskRegime.BETA,
        ml_score=85.0,
    )

    ok, msg = await risk.execute_trade_decision(decision)
    assert ok is True
    # Verify order was placed with valid volume
    call_args = mock_mt5.open_market_order.call_args[1]
    assert call_args['symbol'] == "EURUSD"
    assert call_args['action'] == "BUY"
    assert call_args['volume'] > 0
