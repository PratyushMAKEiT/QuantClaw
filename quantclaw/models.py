# ==============================================================================
# quantclaw/models.py - Core Data Models (MetaTrader 5 Autonomous Engine)
# ==============================================================================
"""
Pydantic data models for QuantClaw MT5's 24/7 autonomous pipeline.
These models define data contracts between all system components:
  MT5 Terminal <-> Market Engine <-> Strategy Matrix <-> ML Brain <-> Claude AI <-> Risk Manager
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


# ------------------------------------------------------------------------------
# ENUMS
# ------------------------------------------------------------------------------

class TradeAction(str, Enum):
    """Trade direction."""
    BUY = "buy"
    SELL = "sell"


class RiskRegime(str, Enum):
    """The 3-tier risk classification system."""
    ALPHA = "ALPHA"  # Scalp / Tight micro-stop
    BETA = "BETA"    # Standard trade (1:1 R:R partial close + breakeven)
    GAMMA = "GAMMA"  # High conviction trend runner (scale out & trail remainder)


class MarketRegime(str, Enum):
    """Market regime classification."""
    TREND_BULL = "TREND_BULL"
    TREND_BEAR = "TREND_BEAR"
    CHOP_RANGE = "CHOP_RANGE"
    NEWS_VOLATILE = "NEWS_VOLATILE"
    LOW_VOL_ACCUM = "LOW_VOL_ACCUM"
    BREAKOUT = "BREAKOUT"


class TradeStatus(str, Enum):
    """Lifecycle status of a trade."""
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


# ------------------------------------------------------------------------------
# METATRADER 5 MODELS
# ------------------------------------------------------------------------------

class MT5AccountInfo(BaseModel):
    """Live account telemetry from MetaTrader 5."""
    login: int
    server: str
    currency: str = "USD"
    leverage: int = 100
    balance: float = 0.0
    equity: float = 0.0
    margin: float = 0.0
    margin_free: float = 0.0
    margin_level: float = 0.0
    profit: float = 0.0
    trade_allowed: bool = True
    trade_expert: bool = True
    company: str = ""


class MT5SymbolInfo(BaseModel):
    """Symbol specifications and live pricing from MT5."""
    symbol: str
    path: str = ""
    description: str = ""
    point: float = 0.00001
    digits: int = 5
    spread: int = 0
    trade_contract_size: float = 100000.0
    # CRITICAL: tick value/size for correct cross-currency lot sizing.
    # Must be populated from mt5.symbol_info().trade_tick_value/.trade_tick_size.
    # Without these, lot sizing for USDJPY/XAUUSD/BTCUSD/US30/NAS100 is wrong by up to 150x.
    trade_tick_value: float = 0.0
    trade_tick_size: float = 0.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    stops_level: int = 0
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0


class MT5Position(BaseModel):
    """Open position record in MT5."""
    ticket: int
    symbol: str
    type: str  # "BUY" or "SELL"
    side: str  # "buy" or "sell"
    volume: float
    open_price: float
    current_price: float
    sl: float = 0.0
    tp: float = 0.0
    profit: float = 0.0
    swap: float = 0.0
    comment: str = ""
    open_time: int = 0
    magic: int = 999111


class MT5Order(BaseModel):
    """Pending order in MT5."""
    ticket: int
    symbol: str
    type: str  # "BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP"
    volume: float
    price: float
    sl: float = 0.0
    tp: float = 0.0
    open_time: int = 0
    magic: int = 999111
    comment: str = ""


# ------------------------------------------------------------------------------
# SMC & LIQUIDITY MODELS
# ------------------------------------------------------------------------------

class SweepEvent(BaseModel):
    """Detected liquidity sweep event."""
    direction: str  # "BULLISH_SWEEP" or "BEARISH_SWEEP"
    price: float
    strength: float = 0.0
    timestamp: float = 0.0


class LiquidityAnalysis(BaseModel):
    """Liquidity snapshot analysis."""
    sweep_detected: bool = False
    sweep_direction: Optional[str] = None
    sweep_strength: float = 0.0
    liquidity_score: float = 0.0
    pending_cluster_above: float = 0.0
    pending_cluster_below: float = 0.0
    institutional_footprint: bool = False


class FairValueGap(BaseModel):
    """Fair Value Gap (Imbalance) structure."""
    direction: str  # "BULLISH" or "BEARISH"
    top: float
    bottom: float
    midpoint: float
    mitigated: bool = False
    timeframe: str = "M15"
    timestamp: float = 0.0


class OrderBlock(BaseModel):
    """Institutional Order Block."""
    direction: str  # "BULLISH" or "BEARISH"
    top: float
    bottom: float
    high_volume: bool = True
    mitigated: bool = False
    timeframe: str = "M15"
    timestamp: float = 0.0


# ------------------------------------------------------------------------------
# STRATEGY SIGNALS & ML CONFLUENCE
# ------------------------------------------------------------------------------

class StrategySignal(BaseModel):
    """A signal emitted by one of the 5 strategy engines."""
    strategy: str  # "smc_liquidity", "occ_r5_trend", "eyes_sme", "mean_reversion", "quant_way"
    symbol: str
    action: str  # "buy" or "sell"
    timeframe: str
    price: float
    sl_points: float = 0.0
    tp_points: float = 0.0
    strength: float = 50.0  # 0 to 100
    invalidation_price: Optional[float] = None
    timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TradeDecision(BaseModel):
    """Final decision produced by ML Brain + AI Co-Pilot."""
    approved: bool
    symbol: str
    action: str
    strategy: str = ""          # Which strategy generated this signal
    volume_lots: float
    entry_price: float
    sl_price: float
    tp_price: float
    invalidation_price: Optional[float] = None
    expectancy_score: Optional[float] = None
    regime: RiskRegime = RiskRegime.BETA
    ml_score: float = 0.0
    confluence_count: int = 0   # Fixed: was 1, making single signals appear confirmed
    rejection_reason: str = ""
    ai_commentary: str = ""

    @field_validator("ml_score")
    @classmethod
    def validate_ml_score(cls, v: float) -> float:
        """ML score must be in range 0-100."""
        return max(0.0, min(100.0, v))

    @field_validator("volume_lots")
    @classmethod
    def validate_volume(cls, v: float) -> float:
        """Volume must be strictly positive and sane (not a fat-finger enormous lot)."""
        if v <= 0:
            raise ValueError(f"volume_lots must be strictly positive, got {v}")
        if v > 1000.0:
            raise ValueError(f"volume_lots={v} is unreasonably large (max 1000 lots)")
        return v

    @model_validator(mode="after")
    def validate_sl_tp_direction(self) -> "TradeDecision":
        """Validate SL/TP sides are correct for BUY/SELL direction.
        Only enforced on approved decisions with all prices set.
        """
        if not self.approved:
            return self
        if self.sl_price <= 0 or self.tp_price <= 0 or self.entry_price <= 0:
            return self
        action = self.action.upper()
        if action == "BUY":
            if self.sl_price >= self.entry_price:
                raise ValueError(
                    f"BUY: sl_price ({self.sl_price}) must be below entry_price ({self.entry_price})"
                )
            if self.tp_price <= self.entry_price:
                raise ValueError(
                    f"BUY: tp_price ({self.tp_price}) must be above entry_price ({self.entry_price})"
                )
        elif action == "SELL":
            if self.sl_price <= self.entry_price:
                raise ValueError(
                    f"SELL: sl_price ({self.sl_price}) must be above entry_price ({self.entry_price})"
                )
            if self.tp_price >= self.entry_price:
                raise ValueError(
                    f"SELL: tp_price ({self.tp_price}) must be below entry_price ({self.entry_price})"
                )

        # Failsafe sanity guard: Reject absurd/corrupted SL or TP distances
        sl_dist = abs(self.entry_price - self.sl_price)
        tp_dist = abs(self.entry_price - self.tp_price)
        if sl_dist > 0 and (tp_dist / sl_dist) > 6.0:
            raise ValueError(
                f"Abnormal TP distance ({tp_dist:.5f}) vs SL distance ({sl_dist:.5f}) - RR {tp_dist/sl_dist:.1f}:1 exceeds safety cap (6.0:1)"
            )
        if tp_dist > self.entry_price * 0.25:
            raise ValueError(
                f"Abnormal TP distance ({tp_dist:.5f}) exceeds 25% of asset price ({self.entry_price})"
            )
        return self


# ------------------------------------------------------------------------------
# RISK & PROTECTION PARAMETERS
# NOTE: RiskParams is documentation only. The running system reads directly
# from AppConfig via RiskManager. Changes here do NOT affect runtime behaviour.
# ------------------------------------------------------------------------------

class RiskParams(BaseModel):
    """Parameters for RiskManager position management.
    [Documentation only - AppConfig fields are the authoritative source at runtime]
    """
    max_risk_pct_per_trade: float = 1.5
    daily_max_loss_pct: float = 3.0
    weekly_profit_target_pct: float = 25.0
    max_concurrent_positions: int = 5
    enable_partial_tp: bool = True
    enable_breakeven: bool = True
    breakeven_r_trigger: float = 1.0
    partial_tp_r_trigger: float = 1.5
    partial_tp_close_pct: float = 0.50
    trailing_stop_atr_mult: float = 2.0
    max_spread_points: int = 40
