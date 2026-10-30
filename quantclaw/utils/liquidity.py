# ==============================================================================
# quantclaw/utils/liquidity.py — Liquidity Sweep & Orderbook Cluster Analyzer
# ==============================================================================
import time
from typing import Optional, Dict, Any, List
from quantclaw.models import SweepEvent, LiquidityAnalysis

class LiquidityAnalyzer:
    def __init__(self) -> None:
        pass

    def analyze_orderbook(self, orderbook: Dict[str, Any]) -> LiquidityAnalysis:
        """
        Analyzes the L2 orderbook to find pending order walls/clusters
        and determine institutional footprint.
        """
        try:
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])
            
            # Find largest size levels
            max_bid_size = 0.0
            max_bid_price = 0.0
            total_bid_depth = 0.0
            for b in bids[:15]:  # Look at top 15 levels
                try:
                    price = float(b[0] if isinstance(b, list) else b.get("price", 0))
                    size = float(b[1] if isinstance(b, list) else b.get("size", 0))
                    total_bid_depth += size
                    if size > max_bid_size:
                        max_bid_size = size
                        max_bid_price = price
                except (ValueError, TypeError, IndexError):
                    continue

            max_ask_size = 0.0
            max_ask_price = 0.0
            total_ask_depth = 0.0
            for a in asks[:15]:
                try:
                    price = float(a[0] if isinstance(a, list) else a.get("price", 0))
                    size = float(a[1] if isinstance(a, list) else a.get("size", 0))
                    total_ask_depth += size
                    if size > max_ask_size:
                        max_ask_size = size
                        max_ask_price = price
                except (ValueError, TypeError, IndexError):
                    continue

            # Determine institutional footprint (if a level size is > 300% of average depth)
            avg_bid_size = total_bid_depth / max(1, len(bids[:15]))
            avg_ask_size = total_ask_depth / max(1, len(asks[:15]))
            
            inst_footprint = (max_bid_size > avg_bid_size * 3.0) or (max_ask_size > avg_ask_size * 3.0)
            
            # Liquidity score based on depth imbalance (bids vs asks depth)
            total_depth = total_bid_depth + total_ask_depth
            liq_score = (total_bid_depth / total_depth) if total_depth > 0 else 0.5

            return LiquidityAnalysis(
                sweep_detected=False,
                sweep_direction=None,
                sweep_strength=0.0,
                pending_cluster_above=max_ask_price,
                pending_cluster_below=max_bid_price,
                institutional_footprint=inst_footprint,
                liquidity_score=liq_score
            )
        except Exception:
            return LiquidityAnalysis(sweep_detected=False)

    def detect_sweep_in_progress(
        self,
        candles: List[Dict[str, Any]],
        current_price: float
    ) -> Optional[SweepEvent]:
        """
        Detects if a liquidity sweep is currently happening or just completed.
        A sweep = price breaking a recent high/low (stop hunt) + immediate reversal wick.
        """
        try:
            if not candles or len(candles) < 20:
                return None

            # Get high/low of the last 15 candles excluding the current one
            lookback = candles[-16:-1]
            highs = [float(c.get("high", 0.0)) for c in lookback]
            lows = [float(c.get("low", 0.0)) for c in lookback]

            recent_high = max(highs)
            recent_low = min(lows)

            last_c = candles[-1]
            high = float(last_c.get("high", 0.0))
            low = float(last_c.get("low", 0.0))
            close = float(last_c.get("close", 0.0))
            open_p = float(last_c.get("open", 0.0))

            body = abs(close - open_p)
            # Fix: use max(1e-8, body) instead of max(1.0, body)
            # max(1.0, body) kills Forex pip-scale bodies (0.00020 -> strength=0.0002)
            body_safe = max(1e-8, body)

            # 1. Bearish Sweep: candle WICK spiked above recent_high and reversed
            # Check wick (not current_price) to catch completed sweeps
            if high > recent_high:
                upper_wick = high - max(open_p, close)
                if upper_wick > body * 1.5:
                    return SweepEvent(
                        direction="BEARISH_SWEEP",  # Swept buy stops, turning bearish
                        price=high,
                        strength=min(1.0, upper_wick / body_safe),
                        timestamp=time.time()
                    )

            # 2. Bullish Sweep: candle WICK dipped below recent_low and reversed
            if low < recent_low:
                lower_wick = min(open_p, close) - low
                if lower_wick > body * 1.5:
                    return SweepEvent(
                        direction="BULLISH_SWEEP",  # Swept sell stops, turning bullish
                        price=low,
                        strength=min(1.0, lower_wick / body_safe),
                        timestamp=time.time()
                    )
        except Exception:
            pass

        return None
