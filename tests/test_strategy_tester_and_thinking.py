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
