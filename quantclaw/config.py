# ==============================================================================
# quantclaw/config.py — Application Configuration & Settings (MetaTrader 5)
# ==============================================================================
"""
Handles all QuantClaw MT5 configuration:
  - MetaTrader 5 credentials and server settings
  - Multi-asset symbols & lot sizes (Forex, Gold, Crypto, Indices)
  - 24/7 Multi-Engine Strategy parameters
  - Self-Learning ML Brain & Claude AI parameters
  - Capital protection, dynamic trailing risk & circuit breakers

Settings are persisted to %APPDATA%/QuantClaw/config.json and loaded on startup.
"""

from __future__ import annotations

import json
import os

from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict


# ------------------------------------------------------------------------------
# PATHS
# ------------------------------------------------------------------------------

def get_app_data_dir() -> Path:
    """Get the QuantClaw application data directory (%APPDATA%/QuantClaw)."""
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    app_dir = Path(appdata) / "QuantClaw"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_config_path() -> Path:
    """Get the path to the config file."""
    return get_app_data_dir() / "config.json"


def get_trade_history_path() -> Path:
    """Get the path to the trades history file."""
    return get_app_data_dir() / "trades_history.json"


def get_ai_memory_path() -> Path:
    """Get the path to the AI learning memory file."""
    return get_app_data_dir() / "ai_memory.json"


def get_ml_weights_path() -> Path:
    """Get the path to the ML weights file."""
    return get_app_data_dir() / "ml_weights.json"


def get_local_project_data_dir() -> Path:
    """Get the local project data directory (LASTHOPE/data)."""
    base_dir = Path(__file__).resolve().parent.parent / "data"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def save_json_persisted(filename: str, data: Any) -> None:
    """Save JSON data atomically to both %APPDATA%/QuantClaw and LASTHOPE/data."""
    app_path = get_app_data_dir() / filename
    local_path = get_local_project_data_dir() / filename
    for p in (app_path, local_path):
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            import logging; logging.getLogger('config').critical(f'CRITICAL: Failed to save config to disk: {e}')


def load_json_persisted(filename: str, default: Any = None) -> Any:
    """Load JSON data from %APPDATA%/QuantClaw or local LASTHOPE/data fallback."""
    app_path = get_app_data_dir() / filename
    local_path = get_local_project_data_dir() / filename
    
    for p in (app_path, local_path):
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                import logging; logging.getLogger('config').error(f'Config JSON parse error: {e}')
            except Exception:
                pass
    return default if default is not None else {}


def get_log_dir() -> Path:
    """Get the directory for log files."""
    log_dir = get_app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


VERSION = "v4.5-MT5-PRO"


# ------------------------------------------------------------------------------
# CONFIGURATION DATACLASS
# ------------------------------------------------------------------------------

@dataclass
class AppConfig:
    """
    Complete QuantClaw MT5 application configuration.
    All fields have sensible defaults for instant 24/7 operation.
    """

    # ── MetaTrader 5 Connection ────────────────────────────────────────────
    mt5_login: int = 0                  # MT5 Account Number
    mt5_password: str = ""              # MT5 Account Password
    mt5_server: str = ""                # Broker Server Name (e.g. "Exness-Real2", "ICMarketsSC-Live", "MetaQuotes-Demo")
    mt5_path: str = ""                  # Optional custom path to terminal64.exe
    mt5_portable: bool = False          # Portable mode
    mt5_timeout: int = 60000            # Connection timeout ms
    mt5_magic_number: int = 999111      # Magic number for QuantClaw trades

    # ── Master Bot State ───────────────────────────────────────────────────
    armed: bool = False                 # Master Arm switch (LIVE execution)
    enable_autonomous_trading: bool = True # 24/7 Autonomous Market Scanning & Punching

    # ── Asset Classes & Multi-Symbol Sizing ────────────────────────────────
    trade_sizing_mode: str = "AutoRisk" # "AutoRisk" (% risk per trade) or "ManualLots"
    risk_per_trade_pct: float = 1.5     # Risk 1.5% of account equity per trade
    max_risk_usd_per_trade: float = 8.0 # Hard dollar risk ceiling per trade ($2-$10 calibrated for small accounts)
    min_risk_usd_per_trade: float = 2.0 # Minimum dollar risk floor per trade
    target_risk_usd_override: float = 0.0 # If > 0, fixed dollar risk override per trade (e.g. 5.0)
    trade_symbols: List[str] = field(default_factory=lambda: [
        'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD',
        'EURGBP', 'EURJPY', 'GBPJPY',
        'XAUUSD', 'XAGUSD',
        'US30', 'DJIUSD', 'NAS100', 'NDXUSD', 'SPX500', 'GER40', 'USOIL'
    ])
    # Per-symbol trading permission: only symbols ticked TRUE will be traded.
    # Any symbol in trade_symbols but NOT in this dict defaults to True (backwards-compat).
    symbol_enabled: Dict[str, bool] = field(default_factory=dict)
    symbol_quantities: Dict[str, float] = field(default_factory=lambda: {
        "EURUSD": 0.05,
        "GBPUSD": 0.05,
        "USDJPY": 0.05,
        "AUDUSD": 0.05,
        "USDCAD": 0.05,
        "USDCHF": 0.05,
        "XAUUSD": 0.01,
        "BTCUSD": 0.01,
        "ETHUSD": 0.01,
        "US30": 0.01,
        "DJIUSD": 0.01,
        "NAS100": 0.01,
        "NDXUSD": 0.01,
        "SPX500": 0.01,
        "GER40": 0.01,
    })
    max_spread_points: int = 40         # Maximum allowable spread to enter trade

    # ── 24/7 Multi-Engine Strategy Matrix ──────────────────────────────────
    strategy_titan_pro_enabled: bool = True # Titan Pro Institutional Order Flow & Liquidity Reversal
    strategy_smc_enabled: bool = True   # Smart Money Concepts & Liquidity Sweeps
    strategy_occ_r5_enabled: bool = True # Institutional Trend & Momentum (SMMA Cross)
    strategy_eyes_sme_enabled: bool = True # Eyes Smart Structure & ATR Impulse
    strategy_mean_rev_enabled: bool = False # Mean-Reversion & Volatility Snapper
    strategy_quant_way_enabled: bool = True # Quant Way Institutional Flow

    # Strategy Parameters
    titan_pro_swing_lookback: int = 15
    titan_pro_rr_ratio: float = 2.8
    smc_fvg_min_points: float = 5.0
    smc_swing_lookback: int = 5
    occ_r5_smma_period: int = 8
    eyes_sme_pivot_len: int = 5
    eyes_sme_atr_len: int = 7
    eyes_sme_impulse_factor: float = 1.5
    quant_way_ema_fast: int = 20
    quant_way_ema_slow: int = 50
    quant_way_vol_multiplier: float = 1.5
    scan_timeframes: str = "M1, M5, M15, M30, H1, H4, D1"

    # ── Self-Learning ML Brain ─────────────────────────────────────────────
    enable_ml_brain: bool = True
    ml_brain_min_execute_score: float = 75.0 # Score threshold to punch trade (0-100)
    ml_brain_confluence_bonus: float = 20.0  # Confluence bonus when 2+ strategies agree
    ml_brain_enable_memory: bool = True      # Learn from past winning/losing setup fingerprints
    
    # ── Claude AI Co-Pilot ─────────────────────────────────────────────────
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-20241022"
    anthropic_timeout_sec: float = 10.0
    enable_ai_discussion: bool = True        # 24/7 AI market briefing & trade audit

    # ── Dynamic Risk Management & Trade Protection ─────────────────────────
    base_sl_pct: float = 0.75                # Fallback SL % (if no structural SL)
    base_tp_pct: float = 2.80                # Fallback TP % (higher RR: 1:2.8+)
    # ── Volume Regime Intelligence & Stepped Trailing ──────────────────────
    enable_volume_regime_intelligence: bool = True # Adapts targets & trailing to low/normal/high/climax volume
    volume_adaptive_tp: bool = True                # Adjusts TP (1.8R low vol, 2.8R normal, 3.5R high vol)
    enable_stepped_trailing: bool = True           # 5-Zone stepped profit securing trailing engine
    stepped_trail_auto_mode: bool = True           # Sweet-spot dynamic triggers calibrated to ATR/Volume
    enable_constant_trailing: bool = True          # Bar-by-bar continuous Chandelier trailing behind runners
    enable_auto_pilot_tuning: bool = True          # Autonomous market scenario adaptation
    enable_strategy_tester_autotune: bool = True   # Background time-machine simulator parameter optimizer
    stepped_trail_zone1_r: float = 0.80            # Zone 1 trigger: Soft cushion (SL -> -0.25R)
    stepped_trail_zone2_r: float = 1.30            # Zone 2 trigger: Breakeven Plus (SL -> Entry + offset)
    stepped_trail_zone3_r: float = 1.80            # Zone 3 trigger: Bank 40% cash & Lock SL at +0.80R
    stepped_trail_zone4_r: float = 2.40            # Zone 4 trigger: Lock SL at +1.40R
    stepped_trail_zone5_r: float = 2.80            # Zone 5 trigger: High-water runner trail
    # ── Advanced Protective Shields & Sizing ──────────────────────────────
    loss_quarantine_seconds: int = 1200            # Post-loss quarantine per symbol/direction (20 mins)
    enable_early_invalidation_cut: bool = True     # Cut losses early at -0.30R to -0.50R if structure shifts against thesis
    invalidation_cut_min_r: float = -0.30          # Minimum adverse R required before early structural cut
    enable_expectancy_adaptive_sizing: bool = True # Fractional Kelly position sizing based on Strategy Tester Expectancy
    enable_weekend_gap_shield: bool = False        # Friday close protection against Sunday opening gaps
    friday_close_cutoff_hour_utc: int = 20         # Friday UTC hour after which entries are blocked and profits locked

    enable_partial_take_profit: bool = True  # Close 50% at 1.5R, let runner ride
    partial_tp_ratio: float = 1.5
    partial_tp_close_pct: float = 0.50
    enable_early_breakeven: bool = False    # Chokes winners into pennies; replaced by soft risk reduction
    early_breakeven_r_ratio: float = 0.45
    enable_soft_risk_reduction: bool = True # At +0.75R, moves SL to -0.25R (slashes 75% risk with 0.5R breathing room)
    soft_risk_reduction_r: float = 0.75
    soft_risk_target_r: float = -0.25
    enable_breakeven_trigger: bool = True   # Move SL to Entry + Spread at 1.2R gain
    breakeven_r_ratio: float = 1.2
    commission_max_pct_of_tp: float = 15.0  # Max allowable broker round-trip commission % of projected TP
    enable_trailing_stop: bool = True        # Trailing SL via ATR
    trailing_stop_atr_mult: float = 2.0
    max_concurrent_positions: int = 5

    # ── Circuit Breakers & Smart Recovery (Change 76) ──────────────────────
    daily_max_loss_pct: float = 5.0          # Max loss threshold
    weekly_profit_target_pct: float = 25.0   # Weekly target tracker (25% - 100%)
    max_consecutive_losses: int = 4          # Max consecutive losses before tactical pause
    disable_auto_disarm: bool = True         # Bot never disarms itself; stays armed to hunt profits
    loss_cooldown_seconds: int = 900         # 15-minute temporary tactical pause before auto-resuming (0 = continuous)
    ignore_manual_trades: bool = True        # Never touch, modify, or close user's manual MT5 trades

    # ── News & Session Filters ─────────────────────────────────────────────
    enable_news_filter: bool = True
    news_pause_min_before: int = 15          # Pause 15m before high-impact news
    news_pause_min_after: int = 15           # Pause 15m after high-impact news

    # ── God Brain & Market Intelligence (Change 74) ────────────────────────
    enable_session_filter: bool = True
    session_min_score: float = 20.0
    enable_swap_awareness: bool = True
    swap_close_threshold_pct: float = 50.0
    enable_eod_profit_lock: bool = False
    eod_lock_min_r: float = 0.5
    enable_partial_tp_ladder: bool = True
    partial_tp_stage1_r: float = 1.8
    partial_tp_stage1_pct: int = 40
    partial_tp_stage2_r: float = 2.8
    partial_tp_stage2_pct: int = 30
    monitor_cycle_seconds: float = 1.0
    enable_acceleration_trail: bool = True
    enable_htf_confluence_exit: bool = False
    adx_trend_threshold: float = 13.0
    trail_activation_r: float = 1.0
    trade_intelligence_enabled: bool = True

    # ── Server & Dashboard ─────────────────────────────────────────────────
    server_host: str = "0.0.0.0"
    server_port: int = 8080
    config_version: int = 3
    webhook_token: str = ""

    # ── Helpers ────────────────────────────────────────────────────────────

    def is_symbol_enabled(self, symbol: str) -> bool:
        """
        Check if a symbol is allowed to trade.
        Returns True if symbol_enabled dict is empty (all allowed) OR if the symbol is ticked ON.
        Checks raw symbol, stripped base symbol, and known aliases (e.g. NDXUSD <-> NAS100, DJIUSD <-> US30).
        """
        import re
        if not self.symbol_enabled:
            return True  # Empty dict = no per-symbol filtering = all allowed

        # 1. Direct exact match
        if symbol in self.symbol_enabled:
            return bool(self.symbol_enabled[symbol])

        # 2. Base symbol (strip broker suffix e.g. .f, .p, .raw, trailing dot)
        base = re.sub(r'[._][a-zA-Z0-9]*$', '', symbol).rstrip('._').upper()
        if base in self.symbol_enabled:
            return bool(self.symbol_enabled[base])

        # 3. Known Aliases (e.g. NAS100 <-> NDXUSD, US30 <-> DJIUSD)
        ALIASES_MAP = {
            "NDXUSD": "NAS100", "NAS100": "NDXUSD", "USTEC": "NAS100", "US100": "NAS100", "NASDAQ": "NAS100",
            "DJIUSD": "US30", "US30": "DJIUSD", "DJ30": "US30", "WS30": "US30", "WALLSTREET": "US30",
            "SPXUSD": "SPX500", "US500": "SPX500", "SP500": "SPX500",
            "DAXEUR": "GER40", "DE40": "GER40", "DAX": "GER40",
            "GOLD": "XAUUSD", "SILVER": "XAGUSD",
            "WTIUSD": "USOIL", "XTIUSD": "USOIL",
        }
        alias = ALIASES_MAP.get(base)
        if alias and alias in self.symbol_enabled:
            return bool(self.symbol_enabled[alias])
        if alias and alias.upper() in self.symbol_enabled:
            return bool(self.symbol_enabled[alias.upper()])

        # Not in dict at all — default to True
        return True

    def get_active_symbols(self) -> List[str]:
        """Return only trade_symbols that are ticked enabled."""
        return [s for s in self.trade_symbols if self.is_symbol_enabled(s)]

    def save(self) -> None:
        """Persist settings to disk atomically."""
        data = asdict(self)
        save_json_persisted("config.json", data)

    @classmethod
    def load(cls) -> AppConfig:
        """Load settings from disk or return defaults."""
        data = load_json_persisted("config.json", {})
        if not data or not isinstance(data, dict):
            cfg = cls()
            cfg.save()
            return cfg

        valid_fields = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        
        # Auto-decrypt any ENC: encrypted strings
        try:
            from quantclaw.utils.crypto import decrypt_value
            for k in ("anthropic_api_key", "mt5_password"):
                if k in filtered and isinstance(filtered[k], str) and filtered[k].startswith("ENC:"):
                    filtered[k] = decrypt_value(filtered[k])
        except Exception as e:
            import logging; logging.getLogger('config').critical(f'CRITICAL: Failed to save config to disk: {e}')

        cfg = cls(**filtered)
        if os.environ.get('QUANTCLAW_MT5_PASSWORD'):
            cfg.mt5_password = os.environ.get('QUANTCLAW_MT5_PASSWORD')
        if os.environ.get('QUANTCLAW_API_KEY'):
            cfg.anthropic_api_key = os.environ.get('QUANTCLAW_API_KEY')
        return cfg


    def update(self, **kwargs) -> None:
        """Update fields and save."""
        for k, v in kwargs.items():
            if hasattr(self, k):
                field_type = self.__annotations__.get(k)
                if field_type:
                    try:
                        if field_type == int:
                            v = int(v)
                        elif field_type == float:
                            v = float(v)
                        elif field_type == bool:
                            if isinstance(v, str):
                                v = v.lower() in ('true', '1', 't', 'y', 'yes')
                            else:
                                v = bool(v)
                        elif field_type == str:
                            v = str(v)
                    except (ValueError, TypeError):
                        pass
                setattr(self, k, v)
        self.save()


# Global config instance
config = AppConfig.load()
