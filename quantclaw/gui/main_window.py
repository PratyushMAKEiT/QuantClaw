# ==============================================================================
# quantclaw/gui/main_window.py — Floating Widget Main Window
# ==============================================================================
"""
The primary QuantClaw window — a frameless, always-on-top, translucent floating
widget that serves as the control center for the trading engine.

Architecture:
  ┌──────────────────────────────┐
  │  Title Bar (draggable)       │  ← QUANTCLAW + minimize/close
  ├──────────────────────────────┤
  │  ARM Button (centered)       │  ← 80px circular toggle
  ├──────────────────────────────┤
  │  Telemetry HUD               │  ← PnL, Status, Regime, Connections, Log
  ├──────────────────────────────┤
  │  Settings Panel (collapsible)│  ← API keys, trade config, risk params
  └──────────────────────────────┘

Features:
  - Frameless window with custom drag-to-move title bar
  - Always-on-top with translucent background
  - System tray icon with context menu (Show/Hide, Arm/Disarm, Quit)
  - Close → minimize to tray (with first-time confirmation dialog)
  - Window position saved/restored to/from AppConfig
  - All signals forwarded from child widgets for external controller binding
"""

import json
import time

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSystemTrayIcon, QMenu, QApplication,
    QMessageBox, QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QTimer
from PyQt6.QtGui import QIcon, QAction, QMouseEvent, QPixmap, QPainter, QColor

from quantclaw.gui.styles import MAIN_STYLESHEET, COLORS
from quantclaw.gui.arm_button import ArmButton
from quantclaw.gui.telemetry_hud import TelemetryHUD
from quantclaw.gui.settings_panel import SettingsPanel
from quantclaw.config import AppConfig, get_update_proposal_path
from quantclaw.models import TradeStatus, RiskRegime, Position


# ==============================================================================
# DRAGGABLE TITLE BAR
# ==============================================================================

class _DraggableTitleBar(QFrame):
    """
    Custom title bar that enables drag-to-move on the parent window.

    Overrides mousePressEvent and mouseMoveEvent to calculate drag offset
    and reposition the parent QMainWindow accordingly.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_pos: QPoint | None = None

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        """Capture the initial drag position on left-button press."""
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            # Store the global cursor position at press time
            self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        """
        Move the parent window by the delta between current and stored
        cursor positions during a left-button drag.
        """
        if (
            event is not None
            and self._drag_pos is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            # Calculate how far the cursor has moved since last event
            current_pos = event.globalPosition().toPoint()
            delta = current_pos - self._drag_pos
            self._drag_pos = current_pos

            # Move the parent window by the delta
            parent_window = self.window()
            if parent_window is not None:
                parent_window.move(parent_window.pos() + delta)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        """Clear the drag position on mouse release."""
        self._drag_pos = None
        super().mouseReleaseEvent(event)


# ==============================================================================
# MAIN WINDOW
# ==============================================================================

class QuantClawWindow(QMainWindow):
    """
    Frameless, always-on-top floating widget for the QuantClaw trading engine.

    Signals:
        arm_state_changed(bool): Forwarded from ArmButton's armed_changed.
        flatten_all_signal():    Forwarded from SettingsPanel's flatten_requested.
        settings_changed(dict):  Forwarded from SettingsPanel's settings_changed.

    Usage:
        config = AppConfig.load()
        window = QuantClawWindow(config)
        window.show()
    """

    # ── Signals ────────────────────────────────────────────────────────────
    arm_state_changed = pyqtSignal(bool)
    flatten_all_signal = pyqtSignal()
    settings_changed = pyqtSignal(dict)
    status_update_signal = pyqtSignal(object)
    positions_update_signal = pyqtSignal(list)
    web_arm_toggle_signal = pyqtSignal(bool)
    health_check_requested = pyqtSignal()
    close_position_signal = pyqtSignal(int)
    breakeven_position_signal = pyqtSignal(int)

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # ── Store Config ───────────────────────────────────────────────────
        self._config = config

        # ── First-close flag (for tray minimization dialog) ────────────────
        self._close_confirmed: bool = False

        # ── Window Flags ───────────────────────────────────────────────────
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # ── Fixed Width ────────────────────────────────────────────────────
        self.setFixedWidth(420)

        # ── Apply QSS Stylesheet ───────────────────────────────────────────
        self.setStyleSheet(MAIN_STYLESHEET)

        # ── Build the UI ───────────────────────────────────────────────────
        self._setup_ui()

        # ── Setup System Tray ──────────────────────────────────────────────
        self._setup_tray_icon()

        # ── Connect Child Signals ──────────────────────────────────────────
        self._connect_signals()

        # ── Load Config into Settings Panel ────────────────────────────────
        self._settings_panel.load_config(self._config)

        # ── Restore Window Position ────────────────────────────────────────
        self.move(self._config.window_x, self._config.window_y)

    # ══════════════════════════════════════════════════════════════════════════
    # UI CONSTRUCTION
    # ══════════════════════════════════════════════════════════════════════════

    def _setup_ui(self) -> None:
        """Build the complete window layout: title bar + content area."""
        # ── Central Widget ─────────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Title Bar ──────────────────────────────────────────────────────
        self._title_bar = _DraggableTitleBar()
        self._title_bar.setObjectName("titleBar")
        title_bar_layout = QHBoxLayout(self._title_bar)
        title_bar_layout.setContentsMargins(12, 4, 8, 4)
        title_bar_layout.setSpacing(4)

        # Title label (left side)
        title_label = QLabel("QUANTCLAW")
        title_label.setObjectName("titleLabel")
        title_bar_layout.addWidget(title_label)

        # Spacer pushes buttons to the right
        title_bar_layout.addStretch()

        # Minimize button
        minimize_btn = QPushButton("—")
        minimize_btn.setObjectName("titleBarBtn")
        minimize_btn.setFixedSize(28, 24)
        minimize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        minimize_btn.setToolTip("Minimize")
        minimize_btn.clicked.connect(self.showMinimized)

        # Health Check button
        health_btn = QPushButton("🔍")
        health_btn.setObjectName("titleBarBtn")
        health_btn.setFixedSize(28, 24)
        health_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        health_btn.setToolTip("Run Diagnostics Health Check")
        health_btn.clicked.connect(self.health_check_requested.emit)

        # Close button
        close_btn = QPushButton("✕")
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(28, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Close to tray")
        close_btn.clicked.connect(self.close)

        title_bar_layout.addWidget(health_btn)
        title_bar_layout.addWidget(minimize_btn)
        title_bar_layout.addWidget(close_btn)

        main_layout.addWidget(self._title_bar)

        # ── Content Area (scrollable) ──────────────────────────────────────
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(6, 6, 6, 6)
        content_layout.setSpacing(6)

        # Scroll area wrapping the left column for small-screen support
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.setObjectName("mainScrollArea")

        # Left Column Widget (Main Widget Panel) — inside scroll area
        self._left_col = QWidget()
        self._left_col.setObjectName("leftColumn")
        left_layout = QVBoxLayout(self._left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        # ARM Button (centered)
        self._arm_button = ArmButton()
        left_layout.addWidget(
            self._arm_button, alignment=Qt.AlignmentFlag.AlignHCenter
        )

        # Version Label (embedded date)
        from quantclaw.config import VERSION
        self._version_label = QLabel(VERSION)
        self._version_label.setObjectName("versionLabel")
        self._version_label.setStyleSheet(
            "color: rgba(100, 120, 160, 160); font-size: 10px; font-weight: bold; "
            "font-family: 'Segoe UI'; margin-top: -2px; margin-bottom: 4px;"
        )
        left_layout.addWidget(
            self._version_label, alignment=Qt.AlignmentFlag.AlignHCenter
        )

        # Separator line
        separator = QFrame()
        separator.setObjectName("separator")
        separator.setFixedHeight(1)
        left_layout.addWidget(separator)

        # Telemetry HUD
        self._telemetry_hud = TelemetryHUD()
        self._telemetry_hud.set_position_action_callbacks(
            on_close=self.close_position_signal.emit,
            on_be=self.breakeven_position_signal.emit,
        )
        left_layout.addWidget(self._telemetry_hud)

        # Settings Panel
        self._settings_panel = SettingsPanel()
        left_layout.addWidget(self._settings_panel)

        # Put left column inside scroll area
        self._scroll_area.setWidget(self._left_col)
        content_layout.addWidget(self._scroll_area)

        # Right Column Widget (Settings Panel when maximized)
        self._right_col = QWidget()
        self._right_col.setObjectName("settingsPanelRight")
        self._right_col.setStyleSheet(
            "background-color: rgba(20, 22, 35, 220); "
            "border: 1px solid rgba(60, 70, 100, 100); "
            "border-radius: 8px;"
        )
        right_layout = QVBoxLayout(self._right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self._right_col.hide()  # Hidden by default

        content_layout.addWidget(self._right_col)

        main_layout.addWidget(content)

        # ── Set max height based on screen geometry ────────────────────────
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            self.setMaximumHeight(available.height() - 40)

        # ── AI Update Proposal Check Timer ─────────────────────────────────
        self._last_alert_timestamp = 0.0
        self._last_alert_real_time = 0.0
        self._proposal_timer = QTimer(self)
        self._proposal_timer.timeout.connect(self._check_update_proposals)
        self._proposal_timer.start(600000)  # Check every 10 minutes
        QTimer.singleShot(3000, self._check_update_proposals)  # Initial check in 3s

    # ══════════════════════════════════════════════════════════════════════════
    # SYSTEM TRAY ICON
    # ══════════════════════════════════════════════════════════════════════════

    def _setup_tray_icon(self) -> None:
        """
        Create a system tray icon with a context menu.

        The icon is a small cyan circle rendered programmatically (no external
        icon file needed). The context menu provides Show/Hide, Arm/Disarm,
        and Quit options.
        """
        # ── Create a simple cyan circle icon ───────────────────────────────
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor(0, 0, 0, 0))  # Transparent background
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(COLORS["accent_cyan"]))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, 24, 24)
        painter.end()
        icon = QIcon(pixmap)

        # ── System Tray Icon ───────────────────────────────────────────────
        self._tray_icon = QSystemTrayIcon(icon, self)
        self._tray_icon.setToolTip("QuantClaw — Trading Engine")

        # ── Context Menu ───────────────────────────────────────────────────
        tray_menu = QMenu()

        # Show / Hide action
        self._show_hide_action = QAction("Hide", self)
        self._show_hide_action.triggered.connect(self._toggle_visibility)
        tray_menu.addAction(self._show_hide_action)

        # Arm / Disarm action
        self._arm_disarm_action = QAction("Arm", self)
        self._arm_disarm_action.triggered.connect(self._toggle_arm_from_tray)
        tray_menu.addAction(self._arm_disarm_action)

        tray_menu.addSeparator()

        # Quit action
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        tray_menu.addAction(quit_action)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _toggle_visibility(self) -> None:
        """Toggle the main window between visible and hidden."""
        if self.isVisible():
            self.hide()
            self._show_hide_action.setText("Show")
        else:
            self.show()
            self.activateWindow()
            self._show_hide_action.setText("Hide")

    def _toggle_arm_from_tray(self) -> None:
        """Toggle the arm state from the tray icon context menu."""
        new_state = not self._arm_button.is_armed
        self._arm_button.set_armed(new_state)
        self.arm_state_changed.emit(new_state)
        self._update_tray_arm_text()

    def _update_tray_arm_text(self) -> None:
        """Update the tray context menu arm/disarm text to match current state."""
        if self._arm_button.is_armed:
            self._arm_disarm_action.setText("Disarm")
        else:
            self._arm_disarm_action.setText("Arm")

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle tray icon double-click to toggle window visibility."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_visibility()

    # ══════════════════════════════════════════════════════════════════════════
    # SIGNAL FORWARDING
    # ══════════════════════════════════════════════════════════════════════════

    def _connect_signals(self) -> None:
        """Wire up child widget signals to this window's forwarding signals."""
        # Arm button → arm_state_changed
        self._arm_button.armed_changed.connect(self._on_arm_changed)

        # Settings panel → settings_changed, flatten_all_signal, and maximized_changed
        self._settings_panel.settings_changed.connect(self.settings_changed.emit)
        self._settings_panel.flatten_requested.connect(self.flatten_all_signal.emit)
        self._settings_panel.maximized_changed.connect(self._on_settings_maximized)

    def _on_arm_changed(self, armed: bool) -> None:
        """Handle arm button toggle — forward signal and update tray text."""
        self.arm_state_changed.emit(armed)
        self._update_tray_arm_text()

    def set_armed(self, armed: bool) -> None:
        """Programmatically set the ARM state of the window from the controller."""
        self._arm_button.blockSignals(True)
        self._arm_button.set_armed(armed)
        self._arm_button.blockSignals(False)
        self._update_tray_arm_text()

    def _on_settings_maximized(self, maximized: bool) -> None:
        """Handle Settings Panel maximize/minimize signal to resize window horizontally."""
        if maximized:
            # 1. Take settings content widget from SettingsPanel and place in right column layout
            content_widget = self._settings_panel.take_content_widget()
            if content_widget is not None:
                self._right_col.layout().addWidget(content_widget)
                # Force height to MAXIMIZED_HEIGHT when on the right
                from quantclaw.gui.settings_panel import MAXIMIZED_HEIGHT
                content_widget.setFixedHeight(MAXIMIZED_HEIGHT)
                content_widget.show()

            # 2. Show right column
            self._right_col.show()

            # 3. Expand window width to 800px
            self.setFixedWidth(800)
        else:
            # 1. Hide right column
            self._right_col.hide()

            # 2. Move settings content widget back to SettingsPanel
            layout = self._right_col.layout()
            if layout.count() > 0:
                item = layout.takeAt(0)
                if item is not None and item.widget() is not None:
                    widget = item.widget()
                    self._settings_panel.restore_content_widget(widget)

            # 3. Shrink window width back to 420px
            self.setFixedWidth(420)

        # 4. Adjust window height to match layout size hint
        self.adjustSize()

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC FORWARDING METHODS (delegate to TelemetryHUD)
    # ══════════════════════════════════════════════════════════════════════════

    def update_pnl(self, value: float) -> None:
        """Forward PnL update to the telemetry HUD.

        Args:
            value: Current session PnL in USD.
        """
        self._telemetry_hud.update_pnl(value)

    def update_status(self, status: TradeStatus, message: str) -> None:
        """Forward trade status update to the telemetry HUD.

        Args:
            status:  TradeStatus enum value.
            message: Human-readable status message.
        """
        self._telemetry_hud.update_status(status, message)

    def update_regime(self, regime: RiskRegime) -> None:
        """Forward risk regime update to the telemetry HUD.

        Args:
            regime: Current RiskRegime (ALPHA/BETA/GAMMA) or None.
        """
        self._telemetry_hud.update_regime(regime)

    def update_positions(self, positions: list[Position]) -> None:
        """Forward active positions update to the telemetry HUD.

        Args:
            positions: List of Position objects.
        """
        self._telemetry_hud.update_positions(positions)

    def set_connection(self, service: str, online: bool) -> None:
        """Forward connection status update to the telemetry HUD.

        Args:
            service: Service name ('Delta', 'Claude', or 'Webhook').
            online:  True for connected, False for disconnected.
        """
        self._telemetry_hud.set_connection(service, online)

    def add_log(self, message: str) -> None:
        """Forward a log entry to the telemetry HUD trade log.

        Args:
            message: The log message text.
        """
        self._telemetry_hud.add_log_entry(message)

    # ══════════════════════════════════════════════════════════════════════════
    # CLOSE EVENT → MINIMIZE TO TRAY
    # ══════════════════════════════════════════════════════════════════════════

    def closeEvent(self, event) -> None:
        """
        Override close event to minimize to tray instead of quitting.

        On first close: shows a confirmation dialog asking the user
        whether to minimize to tray or quit entirely.
        Subsequent closes: always minimize to tray.
        """
        if not self._close_confirmed:
            # ── First Close: Ask the User ──────────────────────────────────
            reply = QMessageBox.question(
                self,
                "Minimize to Tray?",
                "Minimize QuantClaw to the system tray instead of closing?\n"
                "(The trading engine will continue running in the background.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if reply == QMessageBox.StandardButton.No:
                # User wants to actually quit
                self._tray_icon.hide()
                event.accept()
                QApplication.quit()
                return

            # User chose to minimize — remember for next time
            self._close_confirmed = True

        # ── Minimize to Tray ───────────────────────────────────────────────
        event.ignore()
        self.hide()
        self._show_hide_action.setText("Show")
        self._tray_icon.showMessage(
            "QuantClaw",
            "Running in background. Double-click tray icon to restore.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,  # Show for 2 seconds
        )

    # ══════════════════════════════════════════════════════════════════════════
    # WINDOW POSITION PERSISTENCE
    # ══════════════════════════════════════════════════════════════════════════

    def moveEvent(self, event) -> None:
        """Save window position to config whenever the window is moved."""
        super().moveEvent(event)
        pos = self.pos()
        self._config.window_x = pos.x()
        self._config.window_y = pos.y()
        # Note: actual save to disk is deferred to avoid excessive I/O.
        # The controller should call config.save() on app exit.

    def _check_update_proposals(self) -> None:
        """
        Check if the AI has generated a new system update proposal.
        Alerts the user in the trade log twice a day (every 12 hours) or when a new proposal is created.
        """
        try:
            proposal_path = get_update_proposal_path()
            if not proposal_path.exists():
                return

            with open(proposal_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            prop_timestamp = float(data.get("timestamp", 0.0))
            current_real_time = time.time()

            # Alert if:
            # 1. This is a brand new proposal (timestamp is newer than what we last alerted)
            # OR
            # 2. It has been more than 12 hours (43200 seconds) since we last logged the alert (satisfying twice a day)
            is_new_proposal = prop_timestamp > self._last_alert_timestamp
            is_time_for_re_alert = (current_real_time - self._last_alert_real_time) >= 43200

            if is_new_proposal or is_time_for_re_alert:
                summary = data.get("summary", "New optimization recommendations available.")
                self.add_log(f"📢 AI UPGRADE: {summary}")
                self.add_log("📢 Tell Antigravity 'Show me the latest update proposal' to apply it.")
                
                # Update tracking states
                self._last_alert_timestamp = prop_timestamp
                self._last_alert_real_time = current_real_time
        except Exception as e:
            import logging
            logging.getLogger("quantclaw").debug(f"Failed to check AI update proposals: {e}")
