# ==============================================================================
# quantclaw/trade_journal.py â€” SQLite Trade Journal & Memory Engine (MT5)
# ==============================================================================
"""
SQLite-backed persistent trade journal and equity memory engine for MT5.
Stores:
  - MT5 executed trades & outcomes (ticket, symbol, action, lots, pnl, R:R, strategy)
  - Hourly & daily equity snapshots for 7D/30D/90D growth curves
  - Setup fingerprints for Bayesian ML self-learning
"""

from __future__ import annotations

import datetime
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from quantclaw.utils.logger import get_logger
from quantclaw.config import get_app_data_dir

logger = get_logger("trade_journal")


class TradeJournal:
    """SQLite trade journal & memory database manager for QuantClaw MT5."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        if not db_path:
            self.db_path = str(get_app_data_dir() / "quantclaw_mt5.db")
        else:
            self.db_path = db_path

        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local SQLite connection (reused per thread, not created per-call)."""
        import threading
        if not hasattr(self, '_tls'):
            self._tls = threading.local()
        if not hasattr(self._tls, 'conn') or self._tls.conn is None:
            self._tls.conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
            self._tls.conn.row_factory = sqlite3.Row
            self._tls.conn.execute("PRAGMA journal_mode=WAL")  # WAL mode: concurrent reads with writes
            self._tls.conn.execute("PRAGMA synchronous=NORMAL")  # Faster without full fsync risk
        return self._tls.conn


    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._get_conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                ticket INTEGER PRIMARY KEY,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                volume REAL NOT NULL,
                entry_price REAL NOT NULL,
                close_price REAL DEFAULT 0.0,
                sl REAL DEFAULT 0.0,
                tp REAL DEFAULT 0.0,
                pnl_usd REAL DEFAULT 0.0,
                strategy TEXT DEFAULT '',
                ml_score REAL DEFAULT 0.0,
                outcome TEXT DEFAULT 'pending',
                open_time REAL NOT NULL,
                close_time REAL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS equity_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                date_str TEXT NOT NULL,
                equity REAL NOT NULL,
                balance REAL NOT NULL,
                floating_pnl REAL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS ai_discussions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                symbol TEXT NOT NULL,
                text TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_trades_open_time ON trades(open_time);
            CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);
            CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
            CREATE INDEX IF NOT EXISTS idx_equity_timestamp ON equity_snapshots(timestamp);

            CREATE TABLE IF NOT EXISTS trade_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp REAL NOT NULL,
                price REAL DEFAULT 0.0,
                r_multiple REAL DEFAULT 0.0,
                details TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS improvement_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                category TEXT NOT NULL,
                suggestion TEXT NOT NULL,
                priority TEXT DEFAULT 'MEDIUM',
                data TEXT DEFAULT '{}',
                shown INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_events_ticket ON trade_events(ticket);
            CREATE INDEX IF NOT EXISTS idx_events_symbol ON trade_events(symbol);
            CREATE INDEX IF NOT EXISTS idx_events_type ON trade_events(event_type);
            """)
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN rr_achieved REAL DEFAULT 0.0")
            except Exception:
                pass

            # Backfill strategy names from trade_events if trades table contains regime comments (e.g. 'QuantClaw [BETA]')
            try:
                import json
                cur = conn.cursor()
                cur.execute('''
                    SELECT t.ticket, e.details
                    FROM trades t
                    JOIN trade_events e ON t.ticket = e.ticket
                    WHERE e.event_type = 'OPEN' AND (t.strategy LIKE 'QuantClaw [%' OR t.strategy = '' OR t.strategy IS NULL)
                ''')
                updates = []
                for row in cur.fetchall():
                    ticket, details_str = row
                    try:
                        d = json.loads(details_str)
                        st = d.get('strategy', '')
                        if st and not st.startswith('QuantClaw'):
                            updates.append((st, ticket))
                    except Exception:
                        pass
                if updates:
                    conn.executemany("UPDATE trades SET strategy = ? WHERE ticket = ?", updates)
                    conn.commit()
            except Exception:
                pass


    # â”€â”€ Trades Logging â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def record_open_trade(
        self,
        ticket: int,
        symbol: str,
        action: str,
        volume: float,
        entry_price: float,
        sl: float = 0.0,
        tp: float = 0.0,
        strategy: str = "",
        ml_score: float = 0.0,
    ) -> None:
        """Record newly opened MT5 position."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO trades 
                    (ticket, symbol, action, volume, entry_price, sl, tp, strategy, ml_score, outcome, open_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
                    """,
                    (ticket, symbol, action, volume, entry_price, sl, tp, strategy, ml_score, time.time()),
                )
        except Exception as e:
            logger.debug(f"Error recording trade open: {e}")

    def record_close_trade(
        self,
        ticket: int,
        close_price: float,
        pnl_usd: float,
        outcome: str = "win",
    ) -> None:
        """Update closed MT5 position with final P&L."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    UPDATE trades 
                    SET close_price = ?, pnl_usd = ?, outcome = ?, close_time = ?
                    WHERE ticket = ?
                    """,
                    (close_price, pnl_usd, outcome, time.time(), ticket),
                )
        except Exception as e:
            logger.debug(f"Error recording trade close: {e}")

    def get_recent_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch list of completed or open trades."""
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM trades ORDER BY open_time DESC LIMIT ?", (limit,)
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def get_strategy_stats(self, strategy: str) -> Dict[str, Any]:
        """Fetch win-rate, total trades, and total PnL for a strategy."""
        try:
            with self._get_conn() as conn:
                clean_strat = strategy.lower().replace("strategy_", "").strip()
                rows = conn.execute(
                    "SELECT outcome, pnl_usd FROM trades WHERE LOWER(strategy) LIKE ? AND outcome != 'open'",
                    (f"%{clean_strat}%",),
                ).fetchall()
                total = len(rows)
                wins = sum(1 for r in rows if str(r[0]).lower() == 'win' or (r[1] and float(r[1]) > 0.0))
                total_pnl = sum(float(r[1] or 0.0) for r in rows)
                win_rate = (wins / total * 100.0) if total > 0 else 0.0
                return {"total_trades": total, "wins": wins, "win_rate": win_rate, "total_pnl": total_pnl}
        except Exception:
            return {"total_trades": 0, "wins": 0, "win_rate": 0.0, "total_pnl": 0.0}


    def get_open_trades(self) -> List[Dict[str, Any]]:
        """Fetch list of open trades."""
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM trades WHERE close_time IS NULL OR close_time = 0 ORDER BY open_time DESC"
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    # â”€â”€ Equity Snapshots â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def record_equity_snapshot(self, equity: float, balance: float, floating_pnl: float = 0.0) -> None:
        """Record periodic equity snapshot (deduplicated by hour)."""
        now = time.time()
        date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:00")
        try:
            with self._get_conn() as conn:
                latest = conn.execute(
                    "SELECT date_str FROM equity_snapshots ORDER BY id DESC LIMIT 1"
                ).fetchone()
                if latest and latest[0] == date_str:
                    # Update existing hour in-place
                    conn.execute(
                        "UPDATE equity_snapshots SET equity = ?, balance = ?, floating_pnl = ? WHERE date_str = ?",
                        (equity, balance, floating_pnl, date_str),
                    )
                else:
                    conn.execute(
                        "INSERT INTO equity_snapshots (timestamp, date_str, equity, balance, floating_pnl) VALUES (?, ?, ?, ?, ?)",
                        (now, date_str, equity, balance, floating_pnl),
                    )
        except Exception as e:
            logger.debug(f"Error recording equity snapshot: {e}")

    def get_equity_history(self, days: int = 7) -> List[Dict[str, Any]]:
        """Fetch historical equity curve data points."""
        cutoff = time.time() - (days * 86400)
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    "SELECT date_str as date, equity, balance, floating_pnl FROM equity_snapshots WHERE timestamp >= ? ORDER BY id ASC",
                    (cutoff,),
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    # â”€â”€ Performance Analytics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def get_performance_stats(self) -> Dict[str, Any]:
        """Return comprehensive portfolio performance metrics."""
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    "SELECT pnl_usd, strategy, symbol, action, ml_score FROM trades WHERE outcome != 'open' ORDER BY open_time DESC LIMIT 10000"
                ).fetchall()

            if not rows:
                return {"total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "avg_rr": 0.0}

            pnls = [float(r["pnl_usd"]) for r in rows]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p < 0]
            total_win = sum(wins) if wins else 0.0
            total_loss = abs(sum(losses)) if losses else 0.0

            # Max consecutive win/loss streaks
            max_win_streak = max_loss_streak = cur_win = cur_loss = 0
            for p in pnls:
                if p > 0:
                    cur_win += 1; cur_loss = 0
                    max_win_streak = max(max_win_streak, cur_win)
                else:
                    cur_loss += 1; cur_win = 0
                    max_loss_streak = max(max_loss_streak, cur_loss)

            # Per-symbol breakdown
            symbol_pnl: Dict[str, float] = {}
            for r in rows:
                sym = r["symbol"]
                symbol_pnl[sym] = symbol_pnl.get(sym, 0.0) + float(r["pnl_usd"])
            best_symbol = max(symbol_pnl, key=symbol_pnl.get) if symbol_pnl else "--"
            worst_symbol = min(symbol_pnl, key=symbol_pnl.get) if symbol_pnl else "--"

            return {
                "total_trades": len(pnls),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": round(len(wins) / len(pnls) * 100, 1),
                "profit_factor": round(total_win / total_loss, 2) if total_loss > 0 else float("inf"),
                "total_pnl": round(total_win - total_loss, 2),
                "avg_win": round(total_win / len(wins), 2) if wins else 0.0,
                "avg_loss": round(-total_loss / len(losses), 2) if losses else 0.0,
                "avg_rr": round((total_win / max(1, len(wins))) / (total_loss / max(1, len(losses))), 2) if wins and losses else 0.0,
                "max_win_streak": max_win_streak,
                "max_loss_streak": max_loss_streak,
                "best_symbol": best_symbol,
                "worst_symbol": worst_symbol,
                "symbol_pnl": {k: round(v, 2) for k, v in symbol_pnl.items()},
            }
        except Exception as e:
            logger.debug(f"Error computing performance stats: {e}")
            return {"total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "avg_rr": 0.0}

    # â”€â”€ AI Discussion Persistence â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def save_discussion(self, symbol: str, text: str) -> None:
        """Persist an AI discussion entry to SQLite."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO ai_discussions (timestamp, symbol, text) VALUES (?, ?, ?)",
                    (time.time(), symbol, text),
                )
                # Purge old discussions (keep last 200)
                conn.execute(
                    "DELETE FROM ai_discussions WHERE rowid < (SELECT MIN(id) FROM (SELECT id FROM ai_discussions ORDER BY id DESC LIMIT 200))"
                )
        except Exception as e:
            logger.debug(f"Error saving AI discussion: {e}")

    def get_discussions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent AI discussions from SQLite."""
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    "SELECT timestamp, symbol, text FROM ai_discussions ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []


    def get_today_pnl(self) -> float:
        """Get today's realized closed P&L."""
        import datetime
        today = datetime.date.today().isoformat()
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT SUM(pnl_usd) FROM trades WHERE DATE(close_time, 'unixepoch') = ? AND close_time > 0",
                    (today,)
                ).fetchone()
                return float(row[0] or 0.0)
        except Exception:
            return 0.0

    def log_trade_event(
        self,
        ticket: int,
        symbol: str,
        event_type: str,
        price: float = 0.0,
        r_multiple: float = 0.0,
        details: dict = None,
    ) -> None:
        """Log granular trade lifecycle event for self-improvement analysis."""
        import json
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO trade_events (ticket, symbol, event_type, timestamp, price, r_multiple, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (ticket, symbol, event_type, time.time(), price, r_multiple, json.dumps(details or {})),
                )
        except Exception as e:
            logger.debug(f"Error logging trade event: {e}")

    def get_trade_events(self, ticket: int) -> list:
        """Get all events for a specific trade ticket."""
        import json
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM trade_events WHERE ticket = ? ORDER BY timestamp", (ticket,)
                ).fetchall()
                result = []
                for r in rows:
                    d = dict(r)
                    try:
                        d['details'] = json.loads(d.get('details', '{}'))
                    except Exception:
                        d['details'] = {}
                    result.append(d)
                return result
        except Exception:
            return []

    def analyze_for_improvements(self) -> list:
        """
        Analyze trade history to generate improvement suggestions.
        Returns list of suggestion dicts with category, suggestion, priority.
        Called periodically by the bot to generate self-improvement insights.
        """
        import json
        suggestions = []
        try:
            conn = self._get_conn()
            
            # 1. Check for patterns where BE was not triggered before loss
            be_miss_losses = conn.execute("""
                SELECT t.ticket, t.symbol, t.strategy, t.pnl_usd,
                       COUNT(e.id) as be_events
                FROM trades t
                LEFT JOIN trade_events e ON t.ticket = e.ticket AND e.event_type = 'BE_TRIGGERED'
                WHERE t.outcome = 'loss' AND t.pnl_usd < -20
                AND t.close_time > ?
                GROUP BY t.ticket
                HAVING be_events = 0
                LIMIT 20
            """, (time.time() - 7*86400,)).fetchall()
            
            if len(be_miss_losses) >= 3:
                avg_loss = sum(abs(r['pnl_usd']) for r in be_miss_losses) / len(be_miss_losses)
                suggestions.append({
                    'category': 'BREAKEVEN',
                    'suggestion': f'ðŸ“Š IMPROVEMENT NEEDED: {len(be_miss_losses)} trades in last 7 days closed at loss (avg ${avg_loss:.0f}) WITHOUT hitting breakeven. Consider lowering breakeven_r_ratio from current value to trigger BE faster.',
                    'priority': 'HIGH',
                    'data': {'count': len(be_miss_losses), 'avg_loss': avg_loss}
                })

            # 2. Check for strategy win rates
            strategy_stats = conn.execute("""
                SELECT strategy,
                       COUNT(*) as total,
                       SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as wins,
                       AVG(pnl_usd) as avg_pnl
                FROM trades
                WHERE close_time > ? AND outcome != 'open'
                GROUP BY strategy
                HAVING total >= 5
                ORDER BY wins * 1.0 / total ASC
            """, (time.time() - 30*86400,)).fetchall()
            
            for row in strategy_stats:
                wr = row['wins'] / row['total'] * 100
                if wr < 40:
                    suggestions.append({
                        'category': 'STRATEGY',
                        'suggestion': f'ðŸ“‰ IMPROVEMENT NEEDED: Strategy [{row["strategy"]}] has {wr:.0f}% win rate over {row["total"]} trades (avg P&L: ${row["avg_pnl"]:.2f}). Consider disabling or adjusting parameters.',
                        'priority': 'HIGH' if wr < 30 else 'MEDIUM',
                        'data': {'strategy': row['strategy'], 'win_rate': wr, 'total': row['total']}
                    })
                elif wr > 65:
                    suggestions.append({
                        'category': 'STRATEGY',
                        'suggestion': f'â­ PERFORMING WELL: Strategy [{row["strategy"]}] has {wr:.0f}% win rate over {row["total"]} trades. Consider increasing position size or priority for this setup.',
                        'priority': 'LOW',
                        'data': {'strategy': row['strategy'], 'win_rate': wr, 'total': row['total']}
                    })

            # 3. Check for best/worst performing symbols
            symbol_stats = conn.execute("""
                SELECT symbol,
                       COUNT(*) as total,
                       SUM(pnl_usd) as total_pnl,
                       AVG(pnl_usd) as avg_pnl,
                       SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as wins
                FROM trades
                WHERE close_time > ? AND outcome != 'open'
                GROUP BY symbol
                HAVING total >= 3
                ORDER BY total_pnl ASC
            """, (time.time() - 30*86400,)).fetchall()

            for row in symbol_stats:
                if row['total_pnl'] < -50:
                    wr = row['wins'] / row['total'] * 100
                    suggestions.append({
                        'category': 'SYMBOL',
                        'suggestion': f'ðŸ”´ IMPROVEMENT NEEDED: {row["symbol"]} is losing ${abs(row["total_pnl"]):.0f} total over {row["total"]} trades ({wr:.0f}% WR). Consider removing from trade_symbols or adjusting spread filter.',
                        'priority': 'HIGH',
                        'data': {'symbol': row['symbol'], 'total_pnl': row['total_pnl'], 'win_rate': wr}
                    })

            # 4. Check partial TP effectiveness
            ptp_analysis = conn.execute("""
                SELECT 
                    COUNT(DISTINCT t.ticket) as total_with_ptp,
                    AVG(t.pnl_usd) as avg_pnl_with_ptp
                FROM trades t
                INNER JOIN trade_events e ON t.ticket = e.ticket AND e.event_type = 'PARTIAL_TP'
                WHERE t.close_time > ?
            """, (time.time() - 30*86400,)).fetchone()
            
            no_ptp_analysis = conn.execute("""
                SELECT 
                    COUNT(DISTINCT t.ticket) as total_without_ptp,
                    AVG(t.pnl_usd) as avg_pnl_without_ptp
                FROM trades t
                WHERE t.close_time > ? AND t.outcome != 'open'
                AND t.ticket NOT IN (
                    SELECT DISTINCT ticket FROM trade_events WHERE event_type = 'PARTIAL_TP'
                )
            """, (time.time() - 30*86400,)).fetchone()

            if ptp_analysis and no_ptp_analysis:
                ptp_avg = ptp_analysis['avg_pnl_with_ptp'] or 0
                no_ptp_avg = no_ptp_analysis['avg_pnl_without_ptp'] or 0
                if no_ptp_avg > ptp_avg and ptp_analysis['total_with_ptp'] >= 5:
                    suggestions.append({
                        'category': 'PARTIAL_TP',
                        'suggestion': f'ðŸ’¡ IMPROVEMENT: Trades WITHOUT partial TP avg ${no_ptp_avg:.2f} vs WITH partial TP avg ${ptp_avg:.2f}. Consider raising partial_tp_ratio â€” you may be exiting too early.',
                        'priority': 'MEDIUM',
                        'data': {'with_ptp': ptp_avg, 'without_ptp': no_ptp_avg}
                    })

            # 5. Check for time-of-day patterns
            time_analysis = conn.execute("""
                SELECT 
                    CAST(strftime('%H', datetime(open_time, 'unixepoch')) AS INTEGER) as hour,
                    COUNT(*) as total,
                    SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as wins,
                    AVG(pnl_usd) as avg_pnl
                FROM trades
                WHERE close_time > ? AND outcome != 'open'
                GROUP BY hour
                HAVING total >= 3
                ORDER BY avg_pnl ASC
                LIMIT 3
            """, (time.time() - 30*86400,)).fetchall()

            for row in time_analysis:
                if row['avg_pnl'] < -10:
                    wr = row['wins'] / row['total'] * 100
                    suggestions.append({
                        'category': 'TIMING',
                        'suggestion': f'ðŸ• IMPROVEMENT: Hour {row["hour"]:02d}:00 UTC has worst performance: ${row["avg_pnl"]:.2f} avg P&L, {wr:.0f}% WR over {row["total"]} trades. Consider avoiding this session.',
                        'priority': 'MEDIUM',
                        'data': {'hour': row['hour'], 'avg_pnl': row['avg_pnl'], 'win_rate': wr}
                    })

            # 6. Check for manual intervention learning patterns
            manual_interventions = conn.execute("""
                SELECT 
                    COUNT(DISTINCT e.ticket) as total_manual,
                    SUM(CASE WHEN t.outcome = 'win' THEN 1 ELSE 0 END) as wins,
                    AVG(t.pnl_usd) as avg_pnl
                FROM trade_events e
                INNER JOIN trades t ON e.ticket = t.ticket
                WHERE e.event_type IN ('MANUAL_SL_ADJUST', 'MANUAL_TP_ADJUST')
                AND t.close_time > ?
            """, (time.time() - 30*86400,)).fetchone()

            if manual_interventions and manual_interventions['total_manual'] >= 3:
                m_total = manual_interventions['total_manual']
                m_wr = (manual_interventions['wins'] or 0) / m_total * 100
                m_avg = manual_interventions['avg_pnl'] or 0.0
                if m_wr >= 55.0:
                    suggestions.append({
                        'category': 'MANUAL_ADAPTATION',
                        'suggestion': f'🧠 INTEL: Manual adjustments have a {m_wr:.0f}% win rate (avg ${m_avg:.2f} over {m_total} trades). The bot is actively adapting and respecting user trail & target levels.',
                        'priority': 'LOW',
                        'data': {'total_manual': m_total, 'win_rate': m_wr, 'avg_pnl': m_avg}
                    })

        except Exception as e:
            logger.debug(f"Error in improvement analysis: {e}")

        return suggestions

    def save_improvement_suggestions(self, suggestions: list) -> None:
        """Persist improvement suggestions to DB."""
        import json
        try:
            with self._get_conn() as conn:
                for s in suggestions:
                    conn.execute(
                        "INSERT INTO improvement_suggestions (timestamp, category, suggestion, priority, data) VALUES (?, ?, ?, ?, ?)",
                        (time.time(), s['category'], s['suggestion'], s.get('priority', 'MEDIUM'), json.dumps(s.get('data', {})))
                    )
        except Exception as e:
            logger.debug(f"Error saving suggestions: {e}")

    def get_recent_suggestions(self, limit: int = 20) -> list:
        """Get most recent improvement suggestions for dashboard display."""
        import json
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM improvement_suggestions ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                ).fetchall()
                result = []
                for r in rows:
                    d = dict(r)
                    try:
                        d['data'] = json.loads(d.get('data', '{}'))
                    except Exception:
                        d['data'] = {}
                    result.append(d)
                return result
        except Exception:
            return []

    def get_open_volume(self, ticket: int) -> float:
        """Get the original open volume for a trade ticket (for restart amnesia fix)."""
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT volume FROM trades WHERE ticket = ?", (ticket,)
                ).fetchone()
                return float(row[0]) if row else 0.0
        except Exception:
            return 0.0
