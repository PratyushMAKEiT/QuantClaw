# ==============================================================================
# quantclaw/gui/telemetry_hud.py — Live Telemetry Display
# ==============================================================================
"""
Real-time telemetry heads-up display for the QuantClaw trading widget.

Cards (top to bottom):
  1. SESSION P&L     — Current session profit/loss with color-coded value
  2. TRADE STATUS    — Last trade status with animated ellipsis for confirming
  3. RISK REGIME     — Current regime badge (Alpha/Beta/Gamma)
  4. CONNECTIONS     — Delta / Claude / Webhook online/offline dots
  5. TRADE LOG       — Scrollable log with timestamped entries (newest first)

All data is updated via public methods called from the main window, which
receives events from the backend engine thread.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QPushButton,
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation
from PyQt6.QtGui import QColor

from quantclaw.gui.styles import COLORS, STATUS_COLORS
from quantclaw.models import TradeStatus, RiskRegime, Position, OrderSide
from quantclaw.utils.logger import get_logger

logger = get_logger("gui.hud")


# ==============================================================================
# TELEMETRY HUD
# ==============================================================================

class TelemetryHUD(QWidget):
    """
    Live telemetry heads-up display showing system status at a glance.

    Public API:
        update_pnl(value)             — Update the P&L card
        update_status(status, msg)    — Update the trade status card
        update_regime(regime)         — Update the risk regime badge
        set_connection(service, bool) — Toggle a connection dot
        add_log_entry(msg)            — Prepend a timestamped log entry
    """

    # ── Maximum log lines before oldest entries are trimmed ─────────────────
    _MAX_LOG_LINES: int = 50

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # ── Internal State ─────────────────────────────────────────────────
        self._ellipsis_timer: Optional[QTimer] = None
        self._ellipsis_count: int = 0
        self._ellipsis_base_text: str = ""
        self._log_lines: list[str] = []

        # ── Build the UI ───────────────────────────────────────────────────
        self._setup_ui()

    # ══════════════════════════════════════════════════════════════════════════
    # UI CONSTRUCTION
    # ══════════════════════════════════════════════════════════════════════════

    def _setup_ui(self) -> None:
        """Assemble the vertical stack of telemetry cards."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(4)

        # ── 1. PnL Card ───────────────────────────────────────────────────
        pnl_card, pnl_layout = self._create_card("SESSION P&L")
        self._pnl_value_label = QLabel("$0.00")
        self._pnl_value_label.setObjectName("hudCardValue")
        self._pnl_value_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        pnl_layout.addWidget(self._pnl_value_label)
        layout.addWidget(pnl_card)

        # ── 2. Status Card ────────────────────────────────────────────────
        status_card, status_layout = self._create_card("TRADE STATUS")
        self._status_value_label = QLabel("IDLE")
        self._status_value_label.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 13px; font-weight: 700;"
        )
        self._status_value_label.setWordWrap(True)
        self._status_value_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        status_layout.addWidget(self._status_value_label)
        layout.addWidget(status_card)

        # ── 3. Regime Card ────────────────────────────────────────────────
        regime_card, regime_layout = self._create_card("RISK REGIME")
        self._regime_badge = QLabel("—")
        self._regime_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._regime_badge.setFixedHeight(28)
        regime_layout.addWidget(self._regime_badge)
        layout.addWidget(regime_card)

        # ── 3b. Active Positions Table Card ────────────────────────────────
        positions_card, positions_layout = self._create_card("ACTIVE POSITIONS")
        self._positions_table = QTableWidget(0, 8)
        self._positions_table.setHorizontalHeaderLabels(["Symbol", "Side", "Size", "PnL", "Regime", "Bias", "SL / TP", "Actions"])
        self._positions_table.verticalHeader().setVisible(False)
        self._positions_table.setShowGrid(False)
        self._positions_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._positions_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._positions_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._positions_table.setFixedHeight(120)
        self._positions_table.setStyleSheet("background-color: transparent;")
        
        header = self._positions_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        
        positions_layout.addWidget(self._positions_table)
        layout.addWidget(positions_card)

        # ── 4. Connection Indicators ──────────────────────────────────────
        conn_card, conn_layout = self._create_card("CONNECTIONS")
        conn_row = QHBoxLayout()
        conn_row.setSpacing(16)
        self._connection_dots: dict[str, QLabel] = {}
        for service in ("Delta", "Claude", "Webhook"):
            dot_container = QHBoxLayout()
            dot_container.setSpacing(3)
            # Service name label
            name_label = QLabel(service)
            name_label.setStyleSheet(
                f"color: {COLORS['text_secondary']}; font-size: 10px;"
            )
            # Dot indicator label
            dot_label = QLabel("●")
            dot_label.setObjectName("statusDotOffline")  # Default: offline
            dot_container.addWidget(name_label)
            dot_container.addWidget(dot_label)
            conn_row.addLayout(dot_container)
            self._connection_dots[service] = dot_label
        conn_layout.addLayout(conn_row)
        layout.addWidget(conn_card)

        # ── 5. Trade Log ──────────────────────────────────────────────────
        log_card = QFrame()
        log_card.setObjectName("hudCard")
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(8, 5, 8, 5)
        log_layout.setSpacing(3)

        # Custom header with expand button
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        header_label = QLabel("TRADE LOG")
        header_label.setObjectName("hudCardLabel")
        header_layout.addWidget(header_label)

        self._log_expand_btn = QPushButton("▼")
        self._log_expand_btn.setToolTip("Expand Trade Log")
        self._log_expand_btn.setStyleSheet(
            "QPushButton { font-weight: bold; font-size: 10px; max-width: 24px; max-height: 18px; padding: 0px; margin: 0px; border: none; background: transparent; color: #8F9CAE; }"
            "QPushButton:hover { color: #52a3ff; }"
        )
        self._log_expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._log_expand_btn.clicked.connect(self._toggle_log_expand)
        header_layout.addWidget(self._log_expand_btn)

        log_layout.addLayout(header_layout)

        self._trade_log = QTextEdit()
        self._trade_log.setObjectName("tradeLog")
        self._trade_log.setReadOnly(True)
        self._trade_log.setMaximumHeight(110)
        self._trade_log.setPlaceholderText("No trades yet…")
        log_layout.addWidget(self._trade_log)
        layout.addWidget(log_card)

        # Setup animation for trade log height
        self._log_expanded = False
        self._log_animation = QPropertyAnimation(self._trade_log, b"maximumHeight")
        self._log_animation.setDuration(250)
        self._log_animation.valueChanged.connect(self._on_log_animation_changed)

    # ══════════════════════════════════════════════════════════════════════════
    # HELPER: CARD FACTORY
    # ══════════════════════════════════════════════════════════════════════════

    def _create_card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        """
        Create a styled HUD card with a title header.

        Args:
            title: The card's header text (e.g. 'SESSION P&L').

        Returns:
            Tuple of (QFrame card, QVBoxLayout inner_layout) so callers
            can add their own content widgets to the card.
        """
        card = QFrame()
        card.setObjectName("hudCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 5, 8, 5)
        card_layout.setSpacing(3)

        # Header label (small, uppercase, muted)
        header = QLabel(title)
        header.setObjectName("hudCardLabel")
        card_layout.addWidget(header)

        return card, card_layout

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC API: PnL
    # ══════════════════════════════════════════════════════════════════════════

    def update_pnl(self, value: float) -> None:
        """
        Update the session P&L display.

        Positive values are shown green with '+$' prefix.
        Negative values are shown red with '-$' prefix.
        Zero is shown neutral as '$0.00'.

        Args:
            value: Current session PnL in USD.
        """
        if value > 0:
            text = f"+${value:,.2f}"
            obj_name = "pnlPositive"
        elif value < 0:
            text = f"-${abs(value):,.2f}"
            obj_name = "pnlNegative"
        else:
            text = "$0.00"
            obj_name = "hudCardValue"  # Neutral color

        self._pnl_value_label.setText(text)
        self._pnl_value_label.setObjectName(obj_name)

        # Force QSS re-evaluation after objectName change
        self._pnl_value_label.style().unpolish(self._pnl_value_label)
        self._pnl_value_label.style().polish(self._pnl_value_label)
        self._pnl_value_label.update()

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC API: TRADE STATUS
    # ══════════════════════════════════════════════════════════════════════════

    def update_status(self, status: TradeStatus, message: str) -> None:
        """
        Update the trade status card with the current status and message.

        If the status is AI_CONFIRMING, starts an animated ellipsis timer
        that cycles dots every 400ms for visual feedback while waiting.
        All other statuses stop the timer.

        Args:
            status:  TradeStatus enum value.
            message: Human-readable status message.
        """
        # ── Resolve color from STATUS_COLORS ───────────────────────────────
        color = STATUS_COLORS.get(status.value, COLORS["text_secondary"])

        # ── Handle animated ellipsis for AI_CONFIRMING ─────────────────────
        if status == TradeStatus.AI_CONFIRMING:
            self._ellipsis_base_text = message.rstrip(".")
            self._ellipsis_count = 0
            self._status_value_label.setText(self._ellipsis_base_text)
            self._start_ellipsis_timer()
        else:
            self._stop_ellipsis_timer()
            self._status_value_label.setText(message)

        # ── Apply color via inline style ───────────────────────────────────
        self._status_value_label.setStyleSheet(
            f"color: {color}; font-size: 13px; font-weight: 700;"
        )

    def _start_ellipsis_timer(self) -> None:
        """Start the dot-cycling timer for AI confirming animation."""
        if self._ellipsis_timer is not None:
            return  # Already running
        self._ellipsis_timer = QTimer(self)
        self._ellipsis_timer.setInterval(400)  # 400ms per dot change
        self._ellipsis_timer.timeout.connect(self._cycle_ellipsis)
        self._ellipsis_timer.start()

    def _stop_ellipsis_timer(self) -> None:
        """Stop the dot-cycling timer if running."""
        if self._ellipsis_timer is not None:
            self._ellipsis_timer.stop()
            self._ellipsis_timer.deleteLater()
            self._ellipsis_timer = None
            self._ellipsis_count = 0

    def _cycle_ellipsis(self) -> None:
        """
        Cycle through dot states: '' → '.' → '..' → '...' → '' → ...
        Updates the status label text each tick.
        """
        self._ellipsis_count = (self._ellipsis_count + 1) % 4
        dots = "." * self._ellipsis_count
        self._status_value_label.setText(f"{self._ellipsis_base_text}{dots}")

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC API: RISK REGIME
    # ══════════════════════════════════════════════════════════════════════════

    def update_regime(self, regime: RiskRegime | None) -> None:
        """
        Update the risk regime badge display.

        Args:
            regime: Current RiskRegime (ALPHA/BETA/GAMMA) or None for no regime.
        """
        if regime is None:
            self._regime_badge.setText("—")
            self._regime_badge.setObjectName("")  # No special styling
        elif regime == RiskRegime.ALPHA:
            self._regime_badge.setText("ALPHA")
            self._regime_badge.setObjectName("regimeAlpha")
        elif regime == RiskRegime.BETA:
            self._regime_badge.setText("BETA")
            self._regime_badge.setObjectName("regimeBeta")
        elif regime == RiskRegime.GAMMA:
            self._regime_badge.setText("GAMMA")
            self._regime_badge.setObjectName("regimeGamma")

        # Force QSS re-evaluation after objectName change
        self._regime_badge.style().unpolish(self._regime_badge)
        self._regime_badge.style().polish(self._regime_badge)
        self._regime_badge.update()

    def update_positions(self, positions: list[Position]) -> None:
        """
        Update the Active Positions table with the latest positions.

        Args:
            positions: List of Position objects.
        """
        logger.debug("HUD updating positions table with %d rows", len(positions))
        self._positions_table.setRowCount(len(positions))

        for i, pos in enumerate(positions):
            # 1. Symbol
            sym_item = QTableWidgetItem(pos.symbol)
            sym_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._positions_table.setItem(i, 0, sym_item)

            # 2. Side
            side_text = "LONG" if pos.side == OrderSide.BUY else "SHORT"
            side_item = QTableWidgetItem(side_text)
            side_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            side_color = COLORS["success"] if pos.side == OrderSide.BUY else COLORS["danger"]
            side_item.setForeground(QColor(side_color))
            self._positions_table.setItem(i, 1, side_item)

            # 3. Size
            size_item = QTableWidgetItem(f"{pos.size:.4f}")
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._positions_table.setItem(i, 2, size_item)

            # 4. PnL
            pnl = pos.unrealized_pnl
            pnl_usd = getattr(pos, "unrealized_pnl_usd", 0.0) or 0.0
            pnl_usd_sign = "+" if pnl_usd >= 0 else "-"
            pnl_text = f"{pnl:+.2f}% ({pnl_usd_sign}${abs(pnl_usd):.2f})"
            pnl_item = QTableWidgetItem(pnl_text)
            pnl_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            pnl_color = COLORS["success"] if pnl > 0 else (COLORS["danger"] if pnl < 0 else COLORS["text_secondary"])
            pnl_item.setForeground(QColor(pnl_color))
            self._positions_table.setItem(i, 3, pnl_item)

            # 5. Regime
            regime_text = pos.regime.value if pos.regime else "—"
            regime_item = QTableWidgetItem(regime_text)
            regime_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if pos.regime == RiskRegime.ALPHA:
                regime_item.setForeground(QColor(COLORS["regime_alpha"]))
            elif pos.regime == RiskRegime.BETA:
                regime_item.setForeground(QColor(COLORS["regime_beta"]))
            elif pos.regime == RiskRegime.GAMMA:
                regime_item.setForeground(QColor(COLORS["regime_gamma"]))
            else:
                regime_item.setForeground(QColor(COLORS["text_dim"]))
            self._positions_table.setItem(i, 4, regime_item)

            # 6. Bias
            bias = getattr(pos, "live_bias_score", 0.0)
            bias_text = f"{bias:+.2f}"
            bias_item = QTableWidgetItem(bias_text)
            bias_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            bias_color = COLORS["success"] if bias > 0.1 else (COLORS["danger"] if bias < -0.1 else COLORS["text_secondary"])
            bias_item.setForeground(QColor(bias_color))
            self._positions_table.setItem(i, 5, bias_item)

            # 7. SL / TP
            sl = getattr(pos, "current_sl_price", None)
            tp = getattr(pos, "current_tp_price", None)
            sl_str = f"${sl:.2f}" if sl is not None else "--"
            tp_str = f"${tp:.2f}" if tp is not None else "--"
            sltp_text = f"S:{sl_str} | T:{tp_str}"
            sltp_item = QTableWidgetItem(sltp_text)
            sltp_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            sltp_item.setForeground(QColor(COLORS["text_secondary"]))
            self._positions_table.setItem(i, 6, sltp_item)

            # 8. Action Buttons (Close & Breakeven)
            ticket = getattr(pos, "ticket", 0) or getattr(pos, "id", 0)
            if not ticket and isinstance(pos, dict):
                ticket = pos.get("ticket", 0) or pos.get("id", 0)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 1, 2, 1)
            action_layout.setSpacing(4)

            btn_close = QPushButton("✕")
            btn_close.setToolTip(f"Close Position #{ticket}")
            btn_close.setStyleSheet("background-color: #ef4444; color: white; border-radius: 3px; font-weight: bold; font-size: 10px; max-width: 24px; max-height: 18px; padding: 0px;")
            btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
            
            btn_be = QPushButton("BE")
            btn_be.setToolTip(f"Set Breakeven for #{ticket}")
            btn_be.setStyleSheet("background-color: #0284c7; color: white; border-radius: 3px; font-weight: bold; font-size: 9px; max-width: 24px; max-height: 18px; padding: 0px;")
            btn_be.setCursor(Qt.CursorShape.PointingHandCursor)

            if ticket:
                t_int = int(ticket)
                btn_close.clicked.connect(lambda _, t=t_int: self._trigger_close_pos(t))
                btn_be.clicked.connect(lambda _, t=t_int: self._trigger_be_pos(t))

            action_layout.addWidget(btn_close)
            action_layout.addWidget(btn_be)
            self._positions_table.setCellWidget(i, 7, action_widget)

        self._positions_table.resizeColumnsToContents()

    def set_position_action_callbacks(self, on_close=None, on_be=None) -> None:
        """Register callbacks for Close and BE actions from HUD."""
        self._on_close_cb = on_close
        self._on_be_cb = on_be

    def _trigger_close_pos(self, ticket: int) -> None:
        if hasattr(self, "_on_close_cb") and self._on_close_cb:
            self._on_close_cb(ticket)

    def _trigger_be_pos(self, ticket: int) -> None:
        if hasattr(self, "_on_be_cb") and self._on_be_cb:
            self._on_be_cb(ticket)

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC API: CONNECTION INDICATORS
    # ══════════════════════════════════════════════════════════════════════════

    def set_connection(self, service: str, online: bool) -> None:
        """
        Update a connection indicator dot.

        Args:
            service: Service name — one of 'Delta', 'Claude', 'Webhook'.
            online:  True for connected (green), False for disconnected (red).
        """
        dot_label = self._connection_dots.get(service)
        if dot_label is None:
            return  # Unknown service, ignore

        # Switch objectName to trigger QSS color change
        obj_name = "statusDotOnline" if online else "statusDotOffline"
        dot_label.setObjectName(obj_name)

        # Force QSS re-evaluation
        dot_label.style().unpolish(dot_label)
        dot_label.style().polish(dot_label)
        dot_label.update()

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC API: TRADE LOG
    # ══════════════════════════════════════════════════════════════════════════

    def add_log_entry(self, message: str) -> None:
        """
        Prepend a timestamped log entry to the trade log.

        Format: [HH:MM:SS] message
        Newest entries appear at the top. Log is trimmed to _MAX_LOG_LINES.

        Args:
            message: The log message text (timestamp is added automatically).
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"

        # Prepend to internal list (newest first)
        self._log_lines.insert(0, entry)

        # Trim to max lines
        if len(self._log_lines) > self._MAX_LOG_LINES:
            self._log_lines = self._log_lines[:self._MAX_LOG_LINES]

        # Update the text edit with all lines
        self._trade_log.setPlainText("\n".join(self._log_lines))

        # Ensure cursor is at the top (newest entry visible)
        cursor = self._trade_log.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        self._trade_log.setTextCursor(cursor)

    # ══════════════════════════════════════════════════════════════════════════
    # PRIVATE ANIMATION METHODS
    # ══════════════════════════════════════════════════════════════════════════

    def _toggle_log_expand(self) -> None:
        """Toggle the trade log widget height between collapsed (110px) and expanded (280px)."""
        if self._log_expanded:
            self._log_expanded = False
            self._log_expand_btn.setText("▼")
            self._log_animation.setStartValue(self._trade_log.height())
            self._log_animation.setEndValue(110)
            self._log_animation.start()
        else:
            self._log_expanded = True
            self._log_expand_btn.setText("▲")
            self._log_animation.setStartValue(self._trade_log.height())
            self._log_animation.setEndValue(280)
            self._log_animation.start()

    def _on_log_animation_changed(self, value: int) -> None:
        """Adjust maximum height constraint of the widget and resize main window."""
        self._trade_log.setMaximumHeight(value)
        # Smoothly trigger window resize if it exists
        win = self.window()
        if win:
            win.adjustSize()
