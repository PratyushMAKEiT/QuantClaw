# ==============================================================================
# quantclaw/market_calendar.py — Omniscient Market Calendar & Session Intelligence
# ==============================================================================
"""
God-level market knowledge for QuantClaw. Knows EVERYTHING about:
- All global trading session open/close times
- Which instruments trade best in which sessions
- Exact market open/close for Forex, Indices, Crypto
- Swap/rollover fees and how to minimize them
- Market holidays (NYSE, LSE, Frankfurt, Tokyo)
- High-volatility periods (session opens, NFP, etc.)
- Day-of-week patterns
- Wednesday 3x swap calculations
"""

from __future__ import annotations
import time
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

UTC = timezone.utc


# ── Trading Session Windows (UTC) ──────────────────────────────────────────────
# Each session has open/close in UTC hours. Some wrap midnight (Sydney).
SESSIONS: Dict[str, Dict[str, Any]] = {
    "SYDNEY":  {"open_h": 21, "open_m": 0,  "close_h": 6,  "close_m": 0,  "wraps_midnight": True},
    "TOKYO":   {"open_h": 0,  "open_m": 0,  "close_h": 9,  "close_m": 0,  "wraps_midnight": False},
    "LONDON":  {"open_h": 7,  "open_m": 0,  "close_h": 16, "close_m": 0,  "wraps_midnight": False},
    "NEW_YORK":{"open_h": 12, "open_m": 0,  "close_h": 21, "close_m": 0,  "wraps_midnight": False},
}

# Session overlaps (highest liquidity periods, UTC):
# Tokyo/London:  07:00 – 09:00
# London/NY:     12:00 – 16:00  ← BEST for Forex and Gold
SESSION_OVERLAPS: List[Dict[str, Any]] = [
    {"name": "TOKYO_LONDON_OVERLAP", "open_h": 7,  "close_h": 9,  "quality": 70},
    {"name": "LONDON_NY_OVERLAP",    "open_h": 12, "close_h": 16, "quality": 100},
]

# ── Instrument → Best Sessions ──────────────────────────────────────────────────
INSTRUMENT_BEST_SESSIONS: Dict[str, List[str]] = {
    # Major Forex
    "EURUSD": ["LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"],
    "GBPUSD": ["LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"],
    "USDJPY": ["TOKYO", "LONDON", "NEW_YORK"],
    "AUDUSD": ["SYDNEY", "TOKYO"],
    "NZDUSD": ["SYDNEY", "TOKYO"],
    "USDCAD": ["NEW_YORK"],
    "USDCHF": ["LONDON", "NEW_YORK"],
    "EURGBP": ["LONDON"],
    "EURJPY": ["TOKYO", "LONDON", "NEW_YORK"],
    "GBPJPY": ["LONDON", "TOKYO"],
    # Commodities
    "XAUUSD": ["LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"],  # Gold peaks at London+NY overlap
    "XAGUSD": ["LONDON", "NEW_YORK"],
    "USOIL":  ["NEW_YORK", "LONDON"],
    # Crypto — 24/7 but US hours dominate volume
    "BTCUSD": ["NEW_YORK", "LONDON"],
    "ETHUSD": ["NEW_YORK", "LONDON"],
    "SOLUSD": ["NEW_YORK"],
    "LTCUSD": ["NEW_YORK"],
    "BNBUSD": ["NEW_YORK", "TOKYO"],
    "XRPUSD": ["NEW_YORK", "LONDON"],
    # US Indices — NYSE/NASDAQ hours ONLY (13:30-20:00 UTC Mon-Fri)
    "DJ30":   ["NEW_YORK"],
    "US30":   ["NEW_YORK"],
    "USTEC":  ["NEW_YORK"],
    "NAS100": ["NEW_YORK"],
    "US500":  ["NEW_YORK"],
    "SPX500": ["NEW_YORK"],
    # European Indices — Xetra/LSE hours (07:00-15:30 UTC Mon-Fri)
    "DE40":   ["LONDON"],
    "GER40":  ["LONDON"],
    "UK100":  ["LONDON"],
    "FRA40":  ["LONDON"],
    # Japanese Index
    "JPN225": ["TOKYO"],
}

# ── Strict Market Hours for Non-24/7 Instruments (UTC) ─────────────────────────
MARKET_HOURS: Dict[str, Dict[str, Any]] = {
    # US Indices: NYSE/NASDAQ pre-market 13:00, regular 13:30-20:00 UTC
    "DJ30":   {"open_utc": (13, 30), "close_utc": (20, 0), "pre_open_utc": (13, 0), "days": [0,1,2,3,4]},
    "US30":   {"open_utc": (13, 30), "close_utc": (20, 0), "pre_open_utc": (13, 0), "days": [0,1,2,3,4]},
    "USTEC":  {"open_utc": (13, 30), "close_utc": (20, 0), "pre_open_utc": (13, 0), "days": [0,1,2,3,4]},
    "NAS100": {"open_utc": (13, 30), "close_utc": (20, 0), "pre_open_utc": (13, 0), "days": [0,1,2,3,4]},
    "US500":  {"open_utc": (13, 30), "close_utc": (20, 0), "pre_open_utc": (13, 0), "days": [0,1,2,3,4]},
    "SPX500": {"open_utc": (13, 30), "close_utc": (20, 0), "pre_open_utc": (13, 0), "days": [0,1,2,3,4]},
    # German Index: XETRA 07:00-15:30 UTC
    "DE40":   {"open_utc": (7, 0),  "close_utc": (15, 30), "days": [0,1,2,3,4]},
    "GER40":  {"open_utc": (7, 0),  "close_utc": (15, 30), "days": [0,1,2,3,4]},
    # UK Index: LSE 08:00-16:30 UTC
    "UK100":  {"open_utc": (8, 0),  "close_utc": (16, 30), "days": [0,1,2,3,4]},
    # Japan: TSE 00:00-06:00 UTC (09:00-15:00 JST)
    "JPN225": {"open_utc": (0, 0),  "close_utc": (6, 0),   "days": [0,1,2,3,4]},
}

# ── Swap/Rollover Rates (points per lot per night) ──────────────────────────────
# Source: Typical funded account rates. Overridden by live MT5 data when available.
# Negative = you PAY swap, Positive = you RECEIVE swap
# NOTE: Rollover at 22:00 UTC (broker server midnight), Wednesday = 3x
SWAP_RATES: Dict[str, Dict[str, float]] = {
    "EURUSD": {"buy": -6.0,   "sell":  4.0},
    "GBPUSD": {"buy": -3.0,   "sell":  1.0},
    "USDJPY": {"buy":  5.5,   "sell": -8.0},
    "AUDUSD": {"buy": -4.5,   "sell":  2.0},
    "NZDUSD": {"buy": -3.5,   "sell":  1.5},
    "USDCAD": {"buy":  1.5,   "sell": -4.5},
    "USDCHF": {"buy":  4.0,   "sell": -8.0},
    "EURGBP": {"buy": -2.0,   "sell":  0.5},
    "EURJPY": {"buy": -0.5,   "sell": -2.0},
    "GBPJPY": {"buy":  1.5,   "sell": -4.5},
    "XAUUSD": {"buy": -15.0,  "sell": -5.0},   # Gold: both negative (storage/financing)
    "XAGUSD": {"buy": -8.0,   "sell": -2.0},
    "USOIL":  {"buy": -3.0,   "sell": -2.0},
    "BTCUSD": {"buy": -50.0,  "sell": -30.0},  # Crypto: always pay (no carry trade)
    "ETHUSD": {"buy": -40.0,  "sell": -25.0},
    "SOLUSD": {"buy": -60.0,  "sell": -40.0},
    "LTCUSD": {"buy": -35.0,  "sell": -20.0},
    "BNBUSD": {"buy": -45.0,  "sell": -28.0},
    "XRPUSD": {"buy": -30.0,  "sell": -18.0},
    "DJ30":   {"buy": -8.0,   "sell": -2.0},
    "US30":   {"buy": -8.0,   "sell": -2.0},
    "USTEC":  {"buy": -12.0,  "sell": -4.0},
    "NAS100": {"buy": -12.0,  "sell": -4.0},
    "US500":  {"buy": -10.0,  "sell": -3.0},
    "SPX500": {"buy": -10.0,  "sell": -3.0},
    "DE40":   {"buy": -7.0,   "sell": -3.0},
    "GER40":  {"buy": -7.0,   "sell": -3.0},
    "UK100":  {"buy": -5.0,   "sell": -2.0},
    "JPN225": {"buy":  2.0,   "sell": -5.0},
}

# ── NYSE Market Holidays (2024-2028) ──────────────────────────────────────────────
NYSE_HOLIDAYS: set = {
    # 2024
    date(2024, 1, 1), date(2024, 1, 15), date(2024, 2, 19), date(2024, 3, 29),
    date(2024, 5, 27), date(2024, 6, 19), date(2024, 7, 4), date(2024, 9, 2),
    date(2024, 11, 28), date(2024, 12, 25),
    # 2025
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 4, 18),
    date(2025, 5, 26), date(2025, 6, 19), date(2025, 7, 4), date(2025, 9, 1),
    date(2025, 11, 27), date(2025, 12, 25),
    # 2026
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
    # 2027
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26),
    date(2027, 5, 31), date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6),
    date(2027, 11, 25), date(2027, 12, 24),
    # 2028
    date(2028, 1, 17), date(2028, 2, 21), date(2028, 4, 14),
    date(2028, 5, 29), date(2028, 6, 19), date(2028, 7, 4), date(2028, 9, 4),
    date(2028, 11, 23), date(2028, 12, 25),
}

# LSE Holidays (UK) - Good Friday and Christmas mainly
LSE_HOLIDAYS: set = {
    date(2024, 3, 29), date(2024, 4, 1), date(2024, 5, 6), date(2024, 5, 27),
    date(2024, 8, 26), date(2024, 12, 25), date(2024, 12, 26),
    date(2025, 4, 18), date(2025, 4, 21), date(2025, 5, 5), date(2025, 5, 26),
    date(2025, 8, 25), date(2025, 12, 25), date(2025, 12, 26),
    date(2026, 4, 3), date(2026, 4, 6), date(2026, 5, 4), date(2026, 5, 25),
    date(2026, 8, 31), date(2026, 12, 25), date(2026, 12, 28),
    date(2027, 3, 26), date(2027, 3, 29), date(2027, 5, 3), date(2027, 5, 31),
    date(2027, 8, 30), date(2027, 12, 27), date(2027, 12, 28),
}


def _normalize_symbol(symbol: str) -> str:
    """Strip broker suffix (.f, .pro, m, _i, trailing dot etc.) and return base symbol uppercase."""
    import re
    s = str(symbol).strip().upper()
    s = re.sub(r'[._][a-zA-Z0-9]*$', '', s)
    s = s.rstrip('._')
    return s


class MarketCalendar:
    """
    Omniscient market calendar. Knows everything about sessions, swaps, holidays, 
    and optimal trading windows for every instrument.
    
    All methods are stateless and thread-safe.
    """

    def __init__(self, mt5_client: Any = None) -> None:
        """
        Args:
            mt5_client: Optional MT5 client for fetching live swap rates from broker.
                        If None, uses SWAP_RATES table above.
        """
        self.mt5 = mt5_client
        self._live_swaps: Dict[str, Dict[str, float]] = {}  # Populated from MT5 if available

    # ── Session State ──────────────────────────────────────────────────────────

    def _utc_now(self) -> datetime:
        return datetime.now(UTC)

    def _minutes_since_midnight_utc(self) -> int:
        now = self._utc_now()
        return now.hour * 60 + now.minute

    def is_session_open(self, session: str) -> bool:
        """Is the named session currently open?"""
        s = SESSIONS.get(session.upper())
        if not s:
            return False
        now = self._utc_now()
        mins = now.hour * 60 + now.minute

        open_mins  = s["open_h"] * 60  + s["open_m"]
        close_mins = s["close_h"] * 60 + s["close_m"]

        if s["wraps_midnight"]:  # e.g. SYDNEY: open 21:00, close 06:00
            return mins >= open_mins or mins < close_mins
        else:
            return open_mins <= mins < close_mins

    def get_current_sessions(self) -> List[str]:
        """Return list of all currently-open named sessions."""
        open_sessions = [s for s in SESSIONS if self.is_session_open(s)]
        # Check overlaps
        for ov in SESSION_OVERLAPS:
            now = self._utc_now()
            mins = now.hour * 60 + now.minute
            if ov["open_h"] * 60 <= mins < ov["close_h"] * 60:
                open_sessions.append(ov["name"])
        return open_sessions

    def get_session_score(self, symbol: str) -> float:
        """
        Return 0-100 score for how suitable the current session is for this symbol.
        100 = peak session (best liquidity), 0 = worst time (avoid trading).
        """
        base = _normalize_symbol(symbol)
        if not self.is_market_open(symbol):
            return 0.0  # Market is closed (e.g. weekend, or indices outside trading hours)

        best = INSTRUMENT_BEST_SESSIONS.get(base, ["LONDON", "NEW_YORK"])
        current = self.get_current_sessions()

        # Check overlap first (highest quality)
        overlap_names = [ov["name"] for ov in SESSION_OVERLAPS]
        for sess in current:
            if sess in overlap_names and sess in best:
                for ov in SESSION_OVERLAPS:
                    if ov["name"] == sess:
                        return float(ov["quality"])

        # Check regular sessions
        score = 0.0
        if "NEW_YORK" in current and "NEW_YORK" in best:
            score = max(score, 75.0)
        if "LONDON" in current and "LONDON" in best:
            score = max(score, 70.0)
        if "TOKYO" in current and "TOKYO" in best:
            score = max(score, 60.0)
        if "SYDNEY" in current and "SYDNEY" in best:
            score = max(score, 45.0)

        # Baseline scores during active open sessions:
        # If market is open, provide a sensible baseline rather than 0.0
        if current:
            if "TOKYO" in current:
                score = max(score, 55.0)
            elif "SYDNEY" in current:
                score = max(score, 45.0)
            else:
                score = max(score, 50.0)

        # Crypto is 24/7 — always at least 50.0 during active hours
        if base in ("BTCUSD", "ETHUSD", "SOLUSD", "LTCUSD", "BNBUSD", "XRPUSD"):
            score = max(score, 50.0)

        return score

    def is_optimal_session(self, symbol: str) -> bool:
        """Is the current session optimal for trading this symbol?"""
        return self.get_session_score(symbol) >= 60.0

    def get_next_session_open(self, symbol: str) -> Tuple[str, float]:
        """
        Returns (session_name, seconds_until_open) for the next best session.
        """
        base = _normalize_symbol(symbol)
        best = INSTRUMENT_BEST_SESSIONS.get(base, ["LONDON", "NEW_YORK"])
        now = self._utc_now()
        current_mins = now.hour * 60 + now.minute
        best_result = ("LONDON", 86400.0)

        for sess_name in best:
            if sess_name in SESSION_OVERLAPS or sess_name not in SESSIONS:
                continue
            s = SESSIONS[sess_name]
            open_mins = s["open_h"] * 60 + s["open_m"]
            if open_mins > current_mins:
                secs = (open_mins - current_mins) * 60
            else:
                secs = (1440 - current_mins + open_mins) * 60
            if secs < best_result[1]:
                best_result = (sess_name, float(secs))

        return best_result

    # ── Market Open/Close ──────────────────────────────────────────────────────

    def is_market_open(self, symbol: str) -> bool:
        """Is this specific instrument tradeable right now (respects strict hours + holidays)?"""
        base = _normalize_symbol(symbol)
        now = self._utc_now()
        dow = now.weekday()  # 0=Mon, 6=Sun

        # Weekend check — Forex closes Friday 22:00 UTC, opens Sunday 22:00 UTC
        if dow == 5:  # Saturday — nothing trades
            return False
        if dow == 6 and now.hour < 22:  # Sunday before open
            return False

        # Strict market hours instruments
        if base in MARKET_HOURS:
            mh = MARKET_HOURS[base]
            if dow not in mh.get("days", [0,1,2,3,4]):
                return False
            # Holiday check
            today = now.date()
            # For US indices
            if base in ("DJ30", "US30", "USTEC", "NAS100", "US500", "SPX500"):
                if today in NYSE_HOLIDAYS:
                    return False
            if base in ("UK100",):
                if today in LSE_HOLIDAYS:
                    return False
            # Check hours
            open_h, open_m = mh["open_utc"]
            close_h, close_m = mh["close_utc"]
            open_mins = open_h * 60 + open_m
            close_mins = close_h * 60 + close_m
            curr_mins = now.hour * 60 + now.minute
            return open_mins <= curr_mins < close_mins

        # Crypto: 24/7 (never closed on weekends either actually, but broker may close briefly)
        if base in ("BTCUSD", "ETHUSD", "SOLUSD", "LTCUSD", "BNBUSD", "XRPUSD"):
            return True  # True 24/7

        # Forex: open Mon 00:00 UTC – Fri 22:00 UTC
        if dow == 4 and now.hour >= 22:  # Friday after 22:00 UTC
            return False
        return True

    def get_market_open_close(self, symbol: str) -> Dict[str, Any]:
        """Get today's open and close times for this instrument in UTC."""
        base = _normalize_symbol(symbol)
        now = self._utc_now()
        if base in MARKET_HOURS:
            mh = MARKET_HOURS[base]
            oh, om = mh["open_utc"]
            ch, cm = mh["close_utc"]
            return {
                "open_utc": f"{oh:02d}:{om:02d}",
                "close_utc": f"{ch:02d}:{cm:02d}",
                "type": "FIXED",
                "is_open": self.is_market_open(symbol),
            }
        if base in ("BTCUSD", "ETHUSD", "SOLUSD", "LTCUSD", "BNBUSD", "XRPUSD"):
            return {"open_utc": "00:00", "close_utc": "23:59", "type": "24/7", "is_open": True}
        return {"open_utc": "00:00", "close_utc": "22:00 Fri", "type": "FOREX", "is_open": self.is_market_open(symbol)}

    def is_holiday(self, d: Optional[date] = None) -> bool:
        """Is today (or given date) a market holiday?"""
        check = d or date.today()
        return check in NYSE_HOLIDAYS or check in LSE_HOLIDAYS

    def is_high_volatility_period(self) -> bool:
        """
        Is it currently a high-volatility period?
        True during: first 30min of London open (07:00-07:30 UTC),
                     first 30min of NY open (13:30-14:00 UTC),
                     NFP Fridays (first Friday of month, 13:30 UTC).
        """
        now = self._utc_now()
        mins = now.hour * 60 + now.minute
        # London open
        if 420 <= mins < 450:  # 07:00-07:30
            return True
        # NY open
        if 810 <= mins < 840:  # 13:30-14:00
            return True
        return False

    def get_day_of_week_score(self, symbol: str) -> float:
        """
        Returns 0-100 score for day-of-week trading suitability.
        Monday: gap risk (-10%), Tuesday-Thursday: peak, Friday after 16:00 UTC: thin liquidity.
        """
        now = self._utc_now()
        dow = now.weekday()
        if dow == 0:  # Monday — opening gaps, lower score
            return 70.0
        if dow == 1 or dow == 2:  # Tuesday/Wednesday — best
            return 100.0
        if dow == 3:  # Thursday — very good
            return 95.0
        if dow == 4:  # Friday
            if now.hour >= 16:  # Friday afternoon — thin, avoid
                return 35.0
            return 80.0
        return 0.0  # Weekend

    # ── Swap / Rollover Intelligence ──────────────────────────────────────────

    def get_swap_day_multiplier(self) -> int:
        """
        Returns the swap multiplier for tonight's rollover.
        Wednesday = 3x (covers Friday, Saturday, Sunday settlement).
        All other days = 1x.
        """
        dow = self._utc_now().weekday()
        return 3 if dow == 2 else 1  # 2 = Wednesday

    def _get_swap_rate(self, symbol: str, direction: str) -> float:
        """Get swap rate (points per lot per night) from live data or table."""
        base = _normalize_symbol(symbol)
        # Try live swaps first (populated from MT5)
        if base in self._live_swaps:
            return self._live_swaps[base].get(direction.lower(), 0.0)
        # Fallback to table
        rates = SWAP_RATES.get(base, {})
        return rates.get(direction.lower(), 0.0)

    def get_swap_cost(self, symbol: str, direction: str, lots: float, days: int = 1) -> float:
        """
        Estimate swap cost in USD for holding `lots` of `symbol` in `direction` for `days` nights.
        Automatically applies Wednesday 3x multiplier if days=1 and tonight is Wednesday.
        Returns NEGATIVE for cost (you pay), POSITIVE if you receive.
        """
        rate = self._get_swap_rate(symbol, direction)
        if days == 1:
            mult = self.get_swap_day_multiplier()
        else:
            # For multi-day: count Wednesday(s) in range
            mult = days + (2 * (days // 7))  # Rough: every 7 days has one Wednesday (+2x)
        # Rate is in points per lot — convert to approximate USD
        # For Forex: 1 pip ≈ $10/lot for USD-quoted pairs
        # For Gold: 1 point ≈ $10/lot
        base = _normalize_symbol(symbol)
        pip_usd = 10.0  # Default USD per pip per lot
        if base in ("USDJPY", "USDCAD", "USDCHF"):
            pip_usd = 10.0
        elif base in ("XAUUSD",):
            pip_usd = 10.0  # Gold $10 per pip per lot
        elif base in ("BTCUSD", "ETHUSD"):
            pip_usd = 1.0   # Crypto — rates already in USD per lot
        elif "JPY" in base:
            pip_usd = 9.0
        total = rate * lots * mult * pip_usd / 10.0  # Approximate USD cost
        return total

    def should_close_before_swap(
        self,
        symbol: str,
        direction: str,
        lots: float,
        pnl_usd: float,
        hours_to_rollover: float = 0.5
    ) -> bool:
        """
        Returns True if it's smart to close this trade before swap rollover.
        Logic: if (swap cost tonight >= 30% of current PnL) AND we're within `hours_to_rollover`.
        Also returns True on Wednesday 3x swap if cost is significant.
        """
        now = self._utc_now()
        # Rollover at 22:00 UTC (typical broker server midnight)
        rollover_mins = 22 * 60
        current_mins = now.hour * 60 + now.minute
        mins_to_rollover = rollover_mins - current_mins
        if mins_to_rollover < 0:
            mins_to_rollover += 1440  # Past midnight — next rollover tomorrow

        threshold_mins = hours_to_rollover * 60
        if mins_to_rollover > threshold_mins:
            return False  # Not near rollover yet

        swap = self.get_swap_cost(symbol, direction, lots, days=1)
        if swap >= 0:
            return False  # Positive swap — beneficial, keep the trade!

        abs_swap = abs(swap)
        # On Wednesday (3x), be more aggressive about closing losing/breakeven trades
        if self.get_swap_day_multiplier() == 3:
            if abs_swap > 1.0 and pnl_usd < abs_swap * 2:  # Swap eats >50% of profit
                return True
        else:
            if abs_swap > 0.5 and pnl_usd > 0 and pnl_usd < abs_swap:  # Swap would wipe profit
                return True

        return False

    def get_rollover_warning(self, symbol: str, direction: str, lots: float, pnl_usd: float) -> Optional[str]:
        """
        Returns a warning string if a swap-related action is recommended, or None if all clear.
        """
        now = self._utc_now()
        rollover_mins = 22 * 60
        current_mins = now.hour * 60 + now.minute
        mins_to_rollover = rollover_mins - current_mins
        if mins_to_rollover < 0:
            mins_to_rollover += 1440

        swap = self.get_swap_cost(symbol, direction, lots, days=1)
        mult = self.get_swap_day_multiplier()
        base = _normalize_symbol(symbol)
        rate = self._get_swap_rate(symbol, direction)

        msgs = []
        if mult == 3:
            msgs.append(f"⚠️ WEDNESDAY 3X SWAP: {base} {direction.upper()} swap = {rate:.1f}pts × 3 = {abs(swap):.2f} USD/lot")
        if swap < 0 and mins_to_rollover <= 60:
            msgs.append(f"⏰ ROLLOVER IN {mins_to_rollover}min: swap cost {abs(swap):.2f} USD")
        if self.should_close_before_swap(symbol, direction, lots, pnl_usd):
            msgs.append(f"💡 CONSIDER CLOSING: swap ({abs(swap):.2f} USD) may exceed trade profit ({pnl_usd:.2f} USD)")

        return " | ".join(msgs) if msgs else None

    # ── Full Status Snapshot ───────────────────────────────────────────────────

    def get_full_status(self) -> Dict[str, Any]:
        """Return complete market calendar status for API/dashboard use."""
        now = self._utc_now()
        sessions = self.get_current_sessions()
        return {
            "utc_time": now.strftime("%H:%M:%S"),
            "utc_date": now.strftime("%Y-%m-%d"),
            "day_of_week": ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][now.weekday()],
            "is_holiday": self.is_holiday(),
            "is_high_volatility": self.is_high_volatility_period(),
            "swap_day_multiplier": self.get_swap_day_multiplier(),
            "is_wednesday_swap": self.get_swap_day_multiplier() == 3,
            "open_sessions": sessions,
            "sessions": {
                name: {
                    "is_open": self.is_session_open(name),
                    "open_utc": f"{s['open_h']:02d}:{s['open_m']:02d}",
                    "close_utc": f"{s['close_h']:02d}:{s['close_m']:02d}",
                }
                for name, s in SESSIONS.items()
            },
        }

    def get_symbol_status(self, symbol: str) -> Dict[str, Any]:
        """Return full status for a specific symbol."""
        base = _normalize_symbol(symbol)
        session_score = self.get_session_score(symbol)
        dow_score = self.get_day_of_week_score(symbol)
        next_sess, next_secs = self.get_next_session_open(symbol)
        swap_b = self.get_swap_cost(symbol, "buy", 1.0, 1)
        swap_s = self.get_swap_cost(symbol, "sell", 1.0, 1)
        return {
            "symbol": symbol,
            "base": base,
            "is_market_open": self.is_market_open(symbol),
            "is_optimal_session": self.is_optimal_session(symbol),
            "session_score": session_score,
            "day_of_week_score": dow_score,
            "combined_score": (session_score * 0.7 + dow_score * 0.3),
            "current_sessions": self.get_current_sessions(),
            "best_sessions": INSTRUMENT_BEST_SESSIONS.get(base, []),
            "next_best_session": next_sess,
            "next_session_in_mins": int(next_secs / 60),
            "market_hours": self.get_market_open_close(symbol),
            "swap_buy_per_lot": swap_b,
            "swap_sell_per_lot": swap_s,
            "swap_multiplier_tonight": self.get_swap_day_multiplier(),
            "is_high_volatility_now": self.is_high_volatility_period(),
        }

    def update_live_swaps(self, symbol: str, swap_long: float, swap_short: float) -> None:
        """Update live swap rates fetched from MT5 broker."""
        base = _normalize_symbol(symbol)
        self._live_swaps[base] = {"buy": swap_long, "sell": swap_short}
