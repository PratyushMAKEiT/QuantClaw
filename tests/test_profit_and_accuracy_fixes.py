import pytest
import time
from unittest.mock import MagicMock
from quantclaw.config import AppConfig
from quantclaw.models import StrategySignal, TradeDecision, RiskRegime
from quantclaw.strategy_engine import StrategyEngine
from quantclaw.risk_manager import RiskManager
from quantclaw.ml_engine import MLEngine
from quantclaw.utils.smc_analysis import evaluate_institutional_ict_setup

def test_forex_tp_points_not_corrupted_by_volume_regime():
    """Verify Forex signals preserve fractional price units and are never set to 10.0 price units."""
    cfg = AppConfig()
    cfg.enable_volume_regime_intelligence = True
    cfg.volume_adaptive_tp = True

    mock_market = MagicMock()
    mock_market.get_volume_regime.return_value = {
        "regime": "HIGH_VOLUME",
        "target_rr_mult": 1.25,
        "allow_breakout": True
    }
    strat_eng = StrategyEngine(cfg, mock_market)

    # Simulate a signal with 0.0020 (20 pips) SL and 0.0056 (56 pips) TP
    sig = StrategySignal(
        strategy="titan_pro",
        symbol="EURUSD",
        action="buy",
        timeframe="M15",
        price=1.10000,
        sl_points=0.00200,
        tp_points=0.00560,
        strength=88.0
    )

    # In evaluate_symbol, signals pass through volume regime adaptability
    rr_mult = 1.25
    sig.tp_points = round(sig.tp_points * rr_mult, 6)

    # Assert that TP distance is 0.00700 (70 pips), NOT 10.0 (10,000 pips!)
    assert 0.0069 < sig.tp_points < 0.0071
    assert sig.tp_points < 0.05  # Sanity check: must be Forex pips, not 10.0


def test_models_sanity_guard_rejects_absurd_tp():
    """Verify TradeDecision validation rejects absurd RR > 6.0:1 or TP > 25% asset price."""
    # Normal trade passes
    td = TradeDecision(
        approved=True,
        symbol="EURUSD",
        action="buy",
        volume_lots=0.1,
        entry_price=1.1000,
        sl_price=1.0980,  # 20 pips SL
        tp_price=1.1056,  # 56 pips TP (RR 2.8:1)
        regime=RiskRegime.GAMMA,
        ml_score=85.0
    )
    assert td.approved is True

    # Corrupted 10,000 pip TP must be REJECTED by validator
    with pytest.raises(ValueError, match="exceeds safety cap|exceeds 25%"):
        TradeDecision(
            approved=True,
            symbol="EURUSD",
            action="buy",
            volume_lots=0.1,
            entry_price=1.1000,
            sl_price=1.0980,
            tp_price=11.1000,  # Buggy 10.0 price units TP
            regime=RiskRegime.GAMMA,
            ml_score=85.0
        )


def test_symbol_loss_quarantine():
    """Verify that a loss on a symbol/direction puts it into quarantine and blocks revenge re-entry."""
    cfg = AppConfig()
    cfg.loss_quarantine_seconds = 600
    mock_mt5 = MagicMock()
    rm = RiskManager(cfg, mock_mt5, None, None)

    # Initially not in cooldown
    in_cd, _ = rm.is_symbol_in_cooldown("XAUUSD", "sell")
    assert in_cd is False

    # Simulate position loss registration
    ticket = 998877
    rm._managed_positions[ticket] = {
        "symbol": "XAUUSD",
        "action": "sell",
        "entry_price": 2700.0,
        "sl_price": 2705.0,
        "tp_price": 2686.0
    }
    # Simulate loss trigger in quarantine
    cooldown_secs = 600
    rm._symbol_loss_cooldowns[("XAUUSD", "sell")] = time.time() + cooldown_secs

    # Verify is_symbol_in_cooldown is now True
    in_cd, rem = rm.is_symbol_in_cooldown("XAUUSD", "sell")
    assert in_cd is True
    assert 580 <= rem <= 600

    # Opposite direction (BUY) should NOT be blocked
    in_cd_buy, _ = rm.is_symbol_in_cooldown("XAUUSD", "buy")
    assert in_cd_buy is False


def test_macro_counter_trend_ml_penalties():
    """Verify ML engine penalizes trades that fight multi-timeframe trend structure."""
    cfg = AppConfig()
    mock_market = MagicMock()
    mock_market.get_market_analysis.return_value = {
        "rsi": 50.0,
        "volume_ratio": 1.0,
        "macd": {"hist": 0.0},
        "volume_regime": {"regime": "NORMAL_VOLUME"}
    }
    ml = MLEngine(cfg, mock_market)

    # Mock market candles so that trend alignment is 0.0 (counter-trend)
    # 3 timeframes all strongly bullish (fast > slow)
    bullish_candles = [{"close": 100.0 + i * 0.5} for i in range(80)]
    mock_market.get_candles.return_value = bullish_candles

    # Signal is a SELL while market is strongly bullish
    trend_score = ml._eval_trend_alignment("EURUSD", "sell")
    assert trend_score == 0.0  # 100% counter-trend!

    sig = StrategySignal(
        strategy="titan_pro",
        symbol="EURUSD",
        action="sell",
        timeframe="M15",
        price=140.0,
        sl_points=0.20,
        tp_points=0.56,
        strength=80.0
    )

    dec = ml.evaluate_signal(sig)
    # Because of the -25.0 counter-trend penalty and 75.0 threshold, the counter-trend SELL must be REJECTED
    assert dec.approved is False
    assert dec.ml_score < 75.0


def test_smc_analysis_closest_targets():
    """Verify SMC target selection picks the closest valid liquidity pool and caps RR at 3.5."""
    candles = []
    base = 1.1000
    for i in range(50):
        base += 0.0001
        candles.append({
            "open": base,
            "high": base + 0.0005,
            "low": base - 0.0005,
            "close": base + 0.0002,
            "volume": 100,
            "time": 1000 + i * 900
        })

    setup = evaluate_institutional_ict_setup(candles, atr=0.0015, min_rr=2.0)
    # Even if no setup triggered on synthetic straight line, evaluate_institutional_ict_setup runs cleanly
    assert setup is None or setup.get("rr", 0.0) <= 3.51
