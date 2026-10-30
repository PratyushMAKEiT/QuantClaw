# ==============================================================================
# tests/test_smc_analysis.py — SMC Analysis Unit Tests
# ==============================================================================
import unittest
from unittest.mock import MagicMock
import pytest
import time

from quantclaw.utils.smc_analysis import (
    detect_fvgs,
    detect_order_blocks,
    detect_sweeps,
    calculate_liquidity_heatmap,
    analyze_smc_setup
)
from quantclaw.risk_manager import RiskManager


def test_detect_fvgs():
    # Setup 3 candles with a bullish FVG
    candles = [
        {"open": 100, "high": 102, "low": 98, "close": 101, "time": 1000},
        {"open": 101, "high": 106, "low": 101, "close": 105, "time": 1005},
        {"open": 105, "high": 108, "low": 104, "close": 107, "time": 1010}
    ]
    # Gap is between high of candle 0 (102) and low of candle 2 (104) -> size 2.0
    fvgs = detect_fvgs(candles)
    assert len(fvgs) == 1
    assert fvgs[0]["type"] == "BULLISH"
    assert fvgs[0]["top"] == 104
    assert fvgs[0]["bottom"] == 102
    assert fvgs[0]["mitigated"] is False

    # Mitigate the FVG in next candle
    candles.append({"open": 107, "high": 109, "low": 101, "close": 102, "time": 1015})
    fvgs = detect_fvgs(candles)
    assert len(fvgs) == 1
    assert fvgs[0]["mitigated"] is True


def test_detect_order_blocks():
    # Setup bullish OB: a bearish candle followed by 3 strong upward candles
    candles = [
        {"open": 100, "high": 100, "low": 100, "close": 100},  # seed history
        {"open": 100, "high": 100, "low": 100, "close": 100},
        {"open": 100, "high": 100, "low": 100, "close": 100},
        {"open": 100, "high": 100, "low": 100, "close": 100},
        {"open": 102, "high": 103, "low": 99, "close": 100, "time": 1000},  # Bearish candle
        {"open": 100, "high": 105, "low": 100, "close": 104, "time": 1005},  # Expansion 1
        {"open": 104, "high": 109, "low": 104, "close": 108, "time": 1010},  # Expansion 2
        {"open": 108, "high": 113, "low": 108, "close": 112, "time": 1015}   # Expansion 3
    ]
    obs = detect_order_blocks(candles)
    assert len(obs) == 1
    assert obs[0]["type"] == "BULLISH"
    assert obs[0]["top"] == 102
    assert obs[0]["bottom"] == 99


def test_detect_sweeps():
    # Setup range of 5 candles with highest high of 105 and lowest low of 95
    candles = [
        {"open": 100, "high": 102, "low": 98, "close": 100},
        {"open": 100, "high": 105, "low": 97, "close": 101},
        {"open": 101, "high": 103, "low": 95, "close": 98},
        {"open": 98, "high": 102, "low": 96, "close": 101},
        {"open": 101, "high": 104, "low": 99, "close": 102},
        # Latest sweeps BSL (spikes above 105 to 107 but closes at 103)
        {"open": 102, "high": 107, "low": 101, "close": 103}
    ]
    sweeps = detect_sweeps(candles, period=5)
    assert sweeps["swept_bsl"] is True
    assert sweeps["swept_ssl"] is False


def test_calculate_liquidity_heatmap():
    orderbook = {
        "bids": [[99.0, 10], [98.0, 50], [97.0, 20]],
        "asks": [[101.0, 15], [102.0, 40], [103.0, 10]]
    }
    # Within 2% of 100: all bids and asks are inside range
    heatmap = calculate_liquidity_heatmap(orderbook, mark_price=100.0, range_pct=2.0)
    assert heatmap["bid_liquidity_usd"] > 0
    assert heatmap["ask_liquidity_usd"] > 0
    # Top buy pool should be 98.0 (highest size 50)
    assert heatmap["buy_liquidity_pools"][0] == 98.0
    # Top sell pool should be 102.0 (highest size 40)
    assert heatmap["sell_liquidity_pools"][0] == 102.0




def test_analyze_smc_setup_htf_trend():
    """Verify analyze_smc_setup calculates and integrates HTF SMA-5 trend check."""
    candles_5m = [
        {"open": 100, "high": 102, "low": 98, "close": 101, "time": 1000},
        {"open": 101, "high": 103, "low": 99, "close": 102, "time": 1005},
        {"open": 102, "high": 104, "low": 100, "close": 103, "time": 1010},
    ]
    
    # Rising 1h candles -> SMA-5 = (10+11+12+13+15)/5 = 12.2, latest is 15 > 12.2 -> BULLISH trend (+0.15 bias)
    candles_1h_bullish = [
        {"close": 10},
        {"close": 11},
        {"close": 12},
        {"close": 13},
        {"close": 15},
    ]
    
    # Falling 1h candles -> BEARISH trend (-0.15 bias)
    candles_1h_bearish = [
        {"close": 15},
        {"close": 14},
        {"close": 13},
        {"close": 12},
        {"close": 10},
    ]
    
    setup_bullish = analyze_smc_setup(candles_5m, candles_1h_bullish)
    setup_bearish = analyze_smc_setup(candles_5m, candles_1h_bearish)
    
    # setup_bullish bias_score should be higher than setup_bearish bias_score by exactly 0.30
    assert abs((setup_bullish["bias_score"] - setup_bearish["bias_score"]) - 0.30) < 1e-6


def test_evaluate_institutional_ict_setup():
    from quantclaw.utils.smc_analysis import evaluate_institutional_ict_setup
    candles = [{'open': 100, 'high': 102, 'low': 99, 'close': 100, 'time': i*60} for i in range(12)]
    # Established swing low at 97.0
    candles.append({'open': 99, 'high': 100, 'low': 97.0, 'close': 99, 'time': 1200})
    candles.extend([{'open': 100, 'high': 102, 'low': 98.5, 'close': 101, 'time': (13+i)*60} for i in range(4)])
    # SSL Sweep: spikes below 97.0 to 96.0, closes back up at 98.5
    candles.append({'open': 99, 'high': 101, 'low': 96.0, 'close': 98.5, 'time': 1800})
    # Strong bullish displacement candle creating a bullish FVG
    candles.append({'open': 98.5, 'high': 103, 'low': 98.0, 'close': 102.5, 'time': 1900})
    candles.append({'open': 102.5, 'high': 104, 'low': 102.0, 'close': 103.5, 'time': 2000})
    # Retest back into discount zone
    candles.append({'open': 103.5, 'high': 104, 'low': 99.5, 'close': 100.5, 'time': 2100})

    setup = evaluate_institutional_ict_setup(candles, atr=1.5, min_rr=2.0)
    assert setup is not None
    assert setup["action"] == "buy"
    assert setup["sl_price"] < setup["entry_price"]
    assert setup["tp_price"] > setup["entry_price"]
    assert setup["rr"] >= 2.0
    assert setup["setup_type"] == "ICT_BULLISH_REVERSAL"


def test_news_monitor_is_news_blocked():
    from quantclaw.news_monitor import NewsMonitor
    nm = NewsMonitor()
    # Mock high-impact news in cache
    nm._cache["EURUSD"] = {
        "score": -0.4,
        "cached_at": time.time(),
        "headlines": [
            {"title": "Breaking: US CPI Inflation Surges Beyond Expectations", "summary": "Federal Reserve may hike", "time": time.time() - 300}
        ]
    }
    blocked, reason = nm.is_news_blocked("EURUSD")
    assert blocked is True
    assert "CPI" in reason or "High-impact" in reason

    # Normal calm symbol
    nm._cache["GBPUSD"] = {
        "score": 0.1,
        "cached_at": time.time(),
        "headlines": [
            {"title": "London weather pleasant today", "summary": "No market impact", "time": time.time() - 300}
        ]
    }
    blocked_gbp, _ = nm.is_news_blocked("GBPUSD")
    assert blocked_gbp is False

