# ==============================================================================
# quantclaw/utils/session_analyzer.py — Timezone-Aware Session Performance Analyzer
# ==============================================================================
import datetime
from typing import Dict, Any, List

class SessionAnalyzer:
    SESSIONS = {
        "ASIA": (datetime.time(0, 0), datetime.time(8, 0)),
        "LONDON": (datetime.time(8, 0), datetime.time(16, 0)),
        "NY": (datetime.time(13, 0), datetime.time(21, 0)),
        "OVERLAP": (datetime.time(13, 0), datetime.time(16, 0))
    }

    def __init__(self, timezone_offset: float = 0.0) -> None:
        """
        Initialize with a timezone offset in hours relative to UTC.
        Default is 0.0 (UTC).
        """
        self.timezone_offset = timezone_offset

    def get_current_session(self) -> str:
        """
        Returns the active trading session name.
        Checks for OVERLAP first since it's the highest volume.
        """
        # Get current time in UTC + offset
        now = datetime.datetime.now(datetime.timezone.utc)
        if self.timezone_offset != 0.0:
            now = now + datetime.timedelta(hours=self.timezone_offset)
        
        current_time = now.time()

        # Check OVERLAP first
        overlap_start, overlap_end = self.SESSIONS["OVERLAP"]
        if overlap_start <= current_time < overlap_end:
            return "OVERLAP"

        # Check other sessions
        for name in ["NY", "LONDON", "ASIA"]:
            start, end = self.SESSIONS[name]
            # Handle cross-day sessions if any (though ours are within 24h)
            if start <= end:
                if start <= current_time < end:
                    return name
            else:
                if current_time >= start or current_time < end:
                    return name

        return "OFF_HOURS"

    def get_session_stats(self, trades_history: List[Dict[str, Any]], session_name: str) -> Dict[str, Any]:
        """
        Calculate win rate and performance metrics for a specific session.
        """
        session_trades = []
        for t in trades_history:
            # Check if trade matches session
            # If trade has a recorded session key, use it. Otherwise guess from execution time.
            t_sess = t.get("session")
            if not t_sess:
                exec_time = t.get("executed_at")
                if exec_time:
                    dt = datetime.datetime.fromtimestamp(exec_time, datetime.timezone.utc)
                    # Simple heuristic: map UTC hour to session
                    hour = dt.hour
                    if 13 <= hour < 16:
                        t_sess = "OVERLAP"
                    elif 13 <= hour < 21:
                        t_sess = "NY"
                    elif 8 <= hour < 16:
                        t_sess = "LONDON"
                    elif 0 <= hour < 8:
                        t_sess = "ASIA"
                    else:
                        t_sess = "OFF_HOURS"
            
            if t_sess == session_name:
                session_trades.append(t)

        total_trades = len(session_trades)
        wins = [t for t in session_trades if t.get("realized_pnl", 0.0) > 0.0]
        win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 50.0
        avg_pnl = (sum(t.get("realized_pnl", 0.0) for t in session_trades) / total_trades) if total_trades > 0 else 0.0

        recommendation = "TRADE_NORMALLY"
        if total_trades >= 5:
            if win_rate < 30.0:
                recommendation = "SKIP_SESSION"
            elif win_rate < 45.0:
                recommendation = "REDUCE_SIZE"

        return {
            "session": session_name,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "avg_pnl": avg_pnl,
            "recommendation": recommendation
        }

    def get_session_context_for_prompt(self, trades_history: List[Dict[str, Any]]) -> str:
        """
        Format session context for injection into Claude prompts.
        """
        current_sess = self.get_current_session()
        stats = self.get_session_stats(trades_history, current_sess)
        
        context = (
            f"Trading Session Context:\n"
            f"- Current Active Session: {current_sess}\n"
            f"- Session Win Rate: {stats['win_rate']:.1f}% ({stats['total_trades']} trades)\n"
            f"- Session Recommendation: {stats['recommendation']}\n"
        )
        return context
