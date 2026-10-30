# ==============================================================================
# quantclaw/gui/settings_panel.py — Collapsible Settings Panel
# ==============================================================================
"""
Animated collapsible settings panel for the QuantClaw trading widget.

Sections:
  1. API KEYS      — Delta & Anthropic API credentials (masked, with show/hide)
  2. TRADE CONFIG  — Quantity, symbol, SL/TP percentages
  3. RISK PARAMS   — Alpha/Beta/Gamma regime parameters
  4. SERVER        — Port, webhook token, testnet toggle

Features:
  - Smooth slide-open/close animation using QPropertyAnimation on maximumHeight
  - Save button emits settings_changed(dict) signal
  - Flatten All (danger) button emits flatten_requested() signal
  - load_config() / get_config_dict() for bi-directional config sync
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QDoubleSpinBox, QSpinBox, QCheckBox, QPushButton, QFrame,
    QScrollArea, QComboBox,
)
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, pyqtSignal, QByteArray,
)

from quantclaw.config import AppConfig


def normalize_symbol(sym: str) -> str:
    s = sym.upper().strip()
    mapping = {
        "XAUUSD": "XAUTUSD.P",
        "XAUUSD.P": "XAUTUSD.P",
        "XAUTUSD": "XAUTUSD.P",
        "XAUTUSD.P": "XAUTUSD.P",
        "PAXGUSDT": "XAUTUSD.P",
        "PAXGUSDT.P": "XAUTUSD.P",
        "PAXG_USDT": "XAUTUSD.P",
        "BTCUSD": "BTCUSD.P",
        "BTCUSD.P": "BTCUSD.P",
        "BTCUSDT": "BTCUSD.P",
        "BTC_USDT": "BTCUSD.P",
        "ETHUSD": "ETHUSD.P",
        "ETHUSD.P": "ETHUSD.P",
        "ETHUSDT": "ETHUSD.P",
        "ETH_USDT": "ETHUSD.P",
    }
    if s in mapping:
        return mapping[s]
    if s.endswith(".P"):
        return s
    return s + ".P"


# ==============================================================================
# SETTINGS PANEL
# ==============================================================================

# Height constants for settings panel
COLLAPSED_HEIGHT = 0
NORMAL_HEIGHT = 440
MAXIMIZED_HEIGHT = 620


class SettingsPanel(QWidget):
    """
    Collapsible settings panel with smooth height animation.

    Signals:
        settings_changed(dict): Emitted on save with all current values.
        flatten_requested():    Emitted when the Flatten All button is clicked.
        maximized_changed(bool): Emitted when the maximize/restore button is toggled.

    Usage:
        panel = SettingsPanel()
        panel.load_config(app_config)
        panel.settings_changed.connect(on_settings_saved)
        panel.flatten_requested.connect(on_flatten_all)
    """

    # ── Signals ────────────────────────────────────────────────────────────
    settings_changed = pyqtSignal(dict)
    flatten_requested = pyqtSignal()
    maximized_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # ── Internal State ─────────────────────────────────────────────────
        self._expanded: bool = False
        self._maximized: bool = False

        # ── Build the UI ───────────────────────────────────────────────────
        self._setup_ui()

        # ── Setup Expand/Collapse Animation ────────────────────────────────
        self._setup_animation()

    # ══════════════════════════════════════════════════════════════════════════
    # UI CONSTRUCTION
    # ══════════════════════════════════════════════════════════════════════════

    def _setup_ui(self) -> None:
        """Build the toggle button and collapsible content area."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 4, 0, 0)
        main_layout.setSpacing(4)

        # ── Toggle Button & Maximize Button ────────────────────────────────
        toggle_layout = QHBoxLayout()
        toggle_layout.setSpacing(4)
        toggle_layout.setContentsMargins(0, 0, 0, 0)

        self._toggle_btn = QPushButton("⚙ SETTINGS ▼")
        self._toggle_btn.setObjectName("settingsToggle")
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle_panel)
        
        self._max_toggle_btn = QPushButton("⤢")
        self._max_toggle_btn.setObjectName("settingsMaxToggle")
        self._max_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._max_toggle_btn.setToolTip("Maximize Settings Panel")
        self._max_toggle_btn.setFixedWidth(40)
        self._max_toggle_btn.setEnabled(False)  # Only enabled when settings is expanded
        self._max_toggle_btn.clicked.connect(self._toggle_maximized)
        
        toggle_layout.addWidget(self._toggle_btn)
        toggle_layout.addWidget(self._max_toggle_btn)
        main_layout.addLayout(toggle_layout)

        # ── Content Widget (starts collapsed) ──────────────────────────────
        self._content_widget = QFrame()
        self._content_widget.setObjectName("settingsPanel")
        self._content_widget.setMaximumHeight(0)  # Start collapsed
        
        # Outer layout for the collapsible panel
        outer_layout = QVBoxLayout(self._content_widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Scroll Area for the settings fields
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        # Scroll widget containing all actual fields
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(scroll_widget)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(6)

        # ── Section 1: API KEYS ────────────────────────────────────────────
        content_layout.addWidget(self._create_section_header("API KEYS"))

        self._delta_key_input, delta_key_toggle = self._create_api_key_row(
            "Delta API Key"
        )
        content_layout.addLayout(
            self._create_widget_row_layout(
                "Delta API Key", self._delta_key_input, delta_key_toggle
            )
        )

        self._delta_secret_input, delta_secret_toggle = self._create_api_key_row(
            "Delta API Secret"
        )
        content_layout.addLayout(
            self._create_widget_row_layout(
                "Delta API Secret", self._delta_secret_input, delta_secret_toggle
            )
        )

        self._anthropic_key_input, anthropic_key_toggle = self._create_api_key_row(
            "Anthropic API Key"
        )
        content_layout.addLayout(
            self._create_widget_row_layout(
                "Anthropic API Key", self._anthropic_key_input, anthropic_key_toggle
            )
        )

        # ── Section 2: TRADE CONFIG ────────────────────────────────────────
        content_layout.addWidget(self._create_section_header("TRADE CONFIG"))

        self._trade_sizing_mode_combo = QComboBox()
        self._trade_sizing_mode_combo.addItems(["USD", "Contracts"])
        self._trade_sizing_mode_combo.currentTextChanged.connect(self._on_sizing_mode_changed)
        content_layout.addLayout(
            self._create_labeled_row("Sizing Mode", self._trade_sizing_mode_combo)
        )

        self._trade_qty_spin = QDoubleSpinBox()
        self._trade_qty_spin.setRange(0.01, 100000.0)
        self._trade_qty_spin.setSingleStep(10.0)
        self._trade_qty_spin.setDecimals(2)
        self._trade_qty_spin.setValue(100.0)
        self._trade_qty_spin.setPrefix("$ ")
        content_layout.addLayout(
            self._create_labeled_row("Trade Quantity", self._trade_qty_spin)
        )

        self._override_qty_checkbox = QCheckBox("Override Qty from Webhook")
        self._override_qty_checkbox.setToolTip("Allow quantity in TradingView alerts to override configured Trade Quantity.")
        content_layout.addWidget(self._override_qty_checkbox)

        self._product_symbol_input = QLineEdit("BTCUSD.P")
        content_layout.addLayout(
            self._create_labeled_row("Product Symbol", self._product_symbol_input)
        )

        self._trade_symbols_input = QLineEdit("BTCUSD.P, XAUTUSD.P, ETHUSD.P")
        self._trade_symbols_input.setPlaceholderText("e.g. BTCUSD.P, XAUTUSD.P, ETHUSD.P")
        self._trade_symbols_input.setToolTip("Comma-separated list of symbols to monitor and trade")
        self._trade_symbols_input.editingFinished.connect(self._on_symbols_editing_finished)
        content_layout.addLayout(
            self._create_labeled_row("Active Symbols", self._trade_symbols_input)
        )

        # Dynamic Symbol Quantities Container
        self._symbol_qty_container = QWidget()
        self._symbol_qty_layout = QVBoxLayout(self._symbol_qty_container)
        self._symbol_qty_layout.setContentsMargins(0, 0, 0, 0)
        self._symbol_qty_layout.setSpacing(6)
        content_layout.addWidget(self._symbol_qty_container)
        self._symbol_qty_spins: dict[str, QDoubleSpinBox] = {}

        self._base_sl_spin = QDoubleSpinBox()
        self._base_sl_spin.setRange(0.01, 50.0)
        self._base_sl_spin.setSingleStep(0.1)
        self._base_sl_spin.setDecimals(2)
        self._base_sl_spin.setValue(1.0)
        self._base_sl_spin.setSuffix(" %")
        content_layout.addLayout(
            self._create_labeled_row("Base SL %", self._base_sl_spin)
        )

        self._base_tp_spin = QDoubleSpinBox()
        self._base_tp_spin.setRange(0.01, 50.0)
        self._base_tp_spin.setSingleStep(0.1)
        self._base_tp_spin.setDecimals(2)
        self._base_tp_spin.setValue(2.0)
        self._base_tp_spin.setSuffix(" %")
        content_layout.addLayout(
            self._create_labeled_row("Base TP %", self._base_tp_spin)
        )

        self._min_ai_confidence_spin = QSpinBox()
        self._min_ai_confidence_spin.setRange(0, 100)
        self._min_ai_confidence_spin.setSingleStep(5)
        self._min_ai_confidence_spin.setValue(0)
        self._min_ai_confidence_spin.setSuffix(" %")
        content_layout.addLayout(
            self._create_labeled_row("Min AI Confidence", self._min_ai_confidence_spin)
        )

        # ── Section 3: RISK PARAMS ─────────────────────────────────────────
        content_layout.addWidget(self._create_section_header("RISK PARAMS"))

        self._alpha_margin_spin = QDoubleSpinBox()
        self._alpha_margin_spin.setRange(0.01, 5.0)
        self._alpha_margin_spin.setSingleStep(0.01)
        self._alpha_margin_spin.setDecimals(2)
        self._alpha_margin_spin.setValue(0.15)
        self._alpha_margin_spin.setSuffix(" %")
        content_layout.addLayout(
            self._create_labeled_row("Alpha Micro-Margin %", self._alpha_margin_spin)
        )

        self._beta_tp1_spin = QDoubleSpinBox()
        self._beta_tp1_spin.setRange(0.5, 0.8)
        self._beta_tp1_spin.setSingleStep(0.05)
        self._beta_tp1_spin.setDecimals(2)
        self._beta_tp1_spin.setValue(0.65)
        content_layout.addLayout(
            self._create_labeled_row("Beta TP1 Size %", self._beta_tp1_spin)
        )

        self._gamma_tp1_spin = QDoubleSpinBox()
        self._gamma_tp1_spin.setRange(0.1, 10.0)
        self._gamma_tp1_spin.setSingleStep(0.1)
        self._gamma_tp1_spin.setDecimals(1)
        self._gamma_tp1_spin.setValue(1.5)
        self._gamma_tp1_spin.setSuffix(" ×")
        content_layout.addLayout(
            self._create_labeled_row("Gamma TP1 ATR×", self._gamma_tp1_spin)
        )

        self._gamma_tp2_spin = QDoubleSpinBox()
        self._gamma_tp2_spin.setRange(0.1, 20.0)
        self._gamma_tp2_spin.setSingleStep(0.1)
        self._gamma_tp2_spin.setDecimals(1)
        self._gamma_tp2_spin.setValue(3.0)
        self._gamma_tp2_spin.setSuffix(" ×")
        content_layout.addLayout(
            self._create_labeled_row("Gamma TP2 ATR×", self._gamma_tp2_spin)
        )

        self._gamma_trail_spin = QDoubleSpinBox()
        self._gamma_trail_spin.setRange(0.1, 10.0)
        self._gamma_trail_spin.setSingleStep(0.1)
        self._gamma_trail_spin.setDecimals(1)
        self._gamma_trail_spin.setValue(1.5)
        self._gamma_trail_spin.setSuffix(" ×")
        content_layout.addLayout(
            self._create_labeled_row("Gamma Trail ATR×", self._gamma_trail_spin)
        )

        # Circuit breaker — capital protection
        self._max_losses_spin = QSpinBox()
        self._max_losses_spin.setRange(0, 50)
        self._max_losses_spin.setValue(4)
        self._max_losses_spin.setToolTip(
            "Auto-disarm the bot after this many consecutive losing trades (0 = disabled)"
        )
        content_layout.addLayout(
            self._create_labeled_row("Max Consec. Losses", self._max_losses_spin)
        )

        self._max_daily_loss_spin = QDoubleSpinBox()
        self._max_daily_loss_spin.setRange(0.0, 1000000.0)
        self._max_daily_loss_spin.setDecimals(2)
        self._max_daily_loss_spin.setSingleStep(10.0)
        self._max_daily_loss_spin.setPrefix("$ ")
        self._max_daily_loss_spin.setValue(0.0)
        self._max_daily_loss_spin.setToolTip(
            "Auto-disarm after session realized loss reaches this $ amount (0 = disabled)"
        )
        content_layout.addLayout(
            self._create_labeled_row("Max Daily Loss", self._max_daily_loss_spin)
        )

        # ── Section 4: SERVER ──────────────────────────────────────────────
        content_layout.addWidget(self._create_section_header("SERVER"))

        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(80)
        content_layout.addLayout(
            self._create_labeled_row("Port", self._port_spin)
        )

        self._webhook_token_input = QLineEdit()
        self._webhook_token_input.setPlaceholderText("Optional webhook auth token")
        content_layout.addLayout(
            self._create_labeled_row("Webhook Token", self._webhook_token_input)
        )

        self._delta_region_combo = QComboBox()
        self._delta_region_combo.addItems(["Global", "India"])
        content_layout.addLayout(
            self._create_labeled_row("Delta Region", self._delta_region_combo)
        )

        self._indicators_timeframe_combo = QComboBox()
        self._indicators_timeframe_combo.addItems(["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"])
        content_layout.addLayout(
            self._create_labeled_row("Indicator Timeframe", self._indicators_timeframe_combo)
        )

        self._testnet_checkbox = QCheckBox("Use Testnet (recommended for testing)")
        self._testnet_checkbox.setChecked(True)
        content_layout.addWidget(self._testnet_checkbox)

        self._auto_ngrok_checkbox = QCheckBox("Auto-launch Ngrok tunnel on startup")
        self._auto_ngrok_checkbox.setChecked(True)
        content_layout.addWidget(self._auto_ngrok_checkbox)

        self._static_ip_input = QLineEdit()
        self._static_ip_input.setPlaceholderText("Optional static IP for Delta API whitelist (leave blank to auto-detect)")
        content_layout.addLayout(
            self._create_labeled_row("Static Whitelisted IP", self._static_ip_input)
        )

        # ── Action Buttons ─────────────────────────────────────────────────
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        self._save_btn = QPushButton("💾 SAVE CONFIG")
        self._save_btn.setObjectName("saveButton")
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.clicked.connect(self._on_save_clicked)

        self._flatten_btn = QPushButton("⚠ FLATTEN ALL POSITIONS")
        self._flatten_btn.setObjectName("dangerButton")
        self._flatten_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._flatten_btn.setToolTip(
            "Emergency close ALL open positions immediately"
        )
        self._flatten_btn.clicked.connect(self._on_flatten_clicked)

        button_layout.addWidget(self._save_btn)
        button_layout.addWidget(self._flatten_btn)
        content_layout.addLayout(button_layout)

        # Connect scroll widget and scroll area
        self._scroll_area.setWidget(scroll_widget)
        outer_layout.addWidget(self._scroll_area)

        # ── Add content to main layout ─────────────────────────────────────
        main_layout.addWidget(self._content_widget)

    # ══════════════════════════════════════════════════════════════════════════
    # ANIMATION SETUP
    # ══════════════════════════════════════════════════════════════════════════

    def _setup_animation(self) -> None:
        """
        Create the QPropertyAnimation for smooth expand/collapse.
        Animates the 'maximumHeight' property of the content widget.
        """
        self._animation = QPropertyAnimation(
            self._content_widget,
            QByteArray(b"maximumHeight"),
        )
        self._animation.setDuration(300)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animation.valueChanged.connect(self._on_animation_value_changed)

    def _on_animation_value_changed(self, value: int) -> None:
        """Resize the top-level window and update content minimum height to match the animation value."""
        self._content_widget.setMinimumHeight(value)
        win = self.window()
        if win is not None:
            win.adjustSize()

    # ══════════════════════════════════════════════════════════════════════════
    # TOGGLE EXPAND / COLLAPSE
    # ══════════════════════════════════════════════════════════════════════════

    def _toggle_panel(self) -> None:
        """Toggle the settings panel between expanded and collapsed states."""
        self._expanded = not self._expanded

        if self._expanded:
            # ── Expanding ──────────────────────────────────────────────────
            self._toggle_btn.setText("⚙ SETTINGS ▲")
            self._max_toggle_btn.setEnabled(True)
            self._animation.setStartValue(self._content_widget.height())
            self._animation.setEndValue(NORMAL_HEIGHT)
            self._animation.start()
        else:
            # ── Collapsing ─────────────────────────────────────────────────
            if self._maximized:
                self._toggle_maximized()  # Restore to left panel first

            self._toggle_btn.setText("⚙ SETTINGS ▼")
            self._max_toggle_btn.setEnabled(False)
            self._animation.setStartValue(self._content_widget.height())
            self._animation.setEndValue(COLLAPSED_HEIGHT)
            self._animation.start()

    def _toggle_maximized(self) -> None:
        """Toggle between normal expanded height and maximized height."""
        if not self._expanded:
            return

        self._maximized = not self._maximized

        if self._maximized:
            self._max_toggle_btn.setText("⤡")
            self._max_toggle_btn.setToolTip("Restore Settings Panel")
            
            # Stop animation and emit signal to move the widget right
            self._animation.stop()
            self.maximized_changed.emit(True)
        else:
            self._max_toggle_btn.setText("⤢")
            self._max_toggle_btn.setToolTip("Maximize Settings Panel")
            
            # Stop animation and emit signal to restore widget left
            self._animation.stop()
            self.maximized_changed.emit(False)
            
            # Animate height back to normal on the left
            self._animation.setStartValue(self._content_widget.height())
            self._animation.setEndValue(NORMAL_HEIGHT)
            self._animation.start()

    def take_content_widget(self) -> QWidget | None:
        """Remove and return the settings content widget so it can be moved to the side panel."""
        if self._content_widget is not None:
            self.layout().removeWidget(self._content_widget)
            return self._content_widget
        return None

    def restore_content_widget(self, widget: QWidget) -> None:
        """Restore the settings content widget back to this panel's layout."""
        self._content_widget = widget
        self.layout().addWidget(self._content_widget)
        # Reset constraints so animation can drive height on the left
        self._content_widget.setMinimumHeight(0)
        self._content_widget.setMaximumHeight(NORMAL_HEIGHT)
        if self._expanded:
            self._content_widget.show()
        else:
            self._content_widget.hide()

    # ══════════════════════════════════════════════════════════════════════════
    # HELPER: SECTION HEADERS
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _create_section_header(text: str) -> QLabel:
        """
        Create a styled section header label.

        Args:
            text: Section title text (e.g. 'API KEYS').

        Returns:
            QLabel with objectName 'settingsSection'.
        """
        label = QLabel(text)
        label.setObjectName("settingsSection")
        return label

    # ══════════════════════════════════════════════════════════════════════════
    # HELPER: LABELED ROW
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _create_labeled_row(label_text: str, widget: QWidget) -> QHBoxLayout:
        """
        Create a horizontal row with a label on the left and a widget on the right.

        Args:
            label_text: The field label text.
            widget:     The input widget (QLineEdit, QSpinBox, etc.).

        Returns:
            QHBoxLayout containing the label and widget.
        """
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(label_text)
        label.setFixedWidth(140)
        row.addWidget(label)
        row.addWidget(widget)
        return row

    # ══════════════════════════════════════════════════════════════════════════
    # HELPER: API KEY ROW WITH SHOW/HIDE TOGGLE
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _create_api_key_row(label_text: str) -> tuple[QLineEdit, QPushButton]:
        """
        Create an API key QLineEdit with password echo mode and a
        toggle button to show/hide the key.

        Args:
            label_text: Label for tooltip context.

        Returns:
            Tuple of (QLineEdit input field, QPushButton show/hide toggle).
        """
        line_edit = QLineEdit()
        line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        line_edit.setPlaceholderText(f"Enter {label_text}")

        # Eye toggle button to reveal / hide the key
        toggle_btn = QPushButton("👁")
        toggle_btn.setFixedWidth(32)
        toggle_btn.setToolTip(f"Show/Hide {label_text}")
        toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        # Connect toggle behavior (closure captures line_edit)
        def _toggle_echo() -> None:
            if line_edit.echoMode() == QLineEdit.EchoMode.Password:
                line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            else:
                line_edit.setEchoMode(QLineEdit.EchoMode.Password)

        toggle_btn.clicked.connect(_toggle_echo)
        return line_edit, toggle_btn

    @staticmethod
    def _create_widget_row_layout(
        label_text: str,
        line_edit: QLineEdit,
        toggle_btn: QPushButton,
    ) -> QHBoxLayout:
        """
        Create a full API key row with label, input, and show/hide toggle.

        Args:
            label_text: Field label.
            line_edit:  The password QLineEdit.
            toggle_btn: The show/hide QPushButton.

        Returns:
            QHBoxLayout with label, input, and toggle button.
        """
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(label_text)
        label.setFixedWidth(140)
        row.addWidget(label)
        row.addWidget(line_edit)
        row.addWidget(toggle_btn)
        return row

    # ══════════════════════════════════════════════════════════════════════════
    # CONFIG LOADING / EXTRACTION
    # ══════════════════════════════════════════════════════════════════════════

    def load_config(self, config: AppConfig) -> None:
        """
        Populate all input fields from an AppConfig instance.

        Args:
            config: The AppConfig dataclass containing current settings.
        """
        # API Keys
        self._delta_key_input.setText(config.delta_api_key)
        self._delta_secret_input.setText(config.delta_api_secret)
        self._anthropic_key_input.setText(config.anthropic_api_key)

        # Trade Config
        sizing_mode = getattr(config, "trade_sizing_mode", "USD")
        mode_idx = self._trade_sizing_mode_combo.findText(sizing_mode)
        if mode_idx >= 0:
            self._trade_sizing_mode_combo.setCurrentIndex(mode_idx)
        self._on_sizing_mode_changed(sizing_mode)

        self._trade_qty_spin.setValue(config.trade_quantity_usd)
        self._override_qty_checkbox.setChecked(getattr(config, "override_qty_from_webhook", False))
        self._product_symbol_input.setText(config.product_symbol)
        self._trade_symbols_input.setText(config.trade_symbols)

        # Load dynamic symbol quantities
        symbol_q = getattr(config, "symbol_quantities", {})
        self._update_symbol_qty_widgets(symbol_q)

        self._base_sl_spin.setValue(config.base_sl_pct)
        self._base_tp_spin.setValue(config.base_tp_pct)
        self._min_ai_confidence_spin.setValue(getattr(config, "min_ai_confidence", 0))

        # Risk Params
        self._alpha_margin_spin.setValue(config.alpha_micro_margin_pct)
        self._beta_tp1_spin.setValue(config.beta_tp1_close_pct)
        self._gamma_tp1_spin.setValue(config.gamma_tp1_atr_mult)
        self._gamma_tp2_spin.setValue(config.gamma_tp2_atr_mult)
        self._gamma_trail_spin.setValue(config.gamma_trail_atr_mult)

        # Circuit breaker
        self._max_losses_spin.setValue(getattr(config, "max_consecutive_losses", 4))
        self._max_daily_loss_spin.setValue(getattr(config, "max_daily_loss_usd", 0.0))

        # Server
        self._port_spin.setValue(config.server_port)
        self._webhook_token_input.setText(config.webhook_token)
        self._testnet_checkbox.setChecked(config.delta_use_testnet)
        self._auto_ngrok_checkbox.setChecked(getattr(config, "auto_launch_ngrok", True))
        self._static_ip_input.setText(getattr(config, "static_whitelisted_ip", "") or "")

        # Region & Timeframe
        region_idx = self._delta_region_combo.findText(config.delta_region)
        if region_idx >= 0:
            self._delta_region_combo.setCurrentIndex(region_idx)
        timeframe_idx = self._indicators_timeframe_combo.findText(config.indicators_timeframe)
        if timeframe_idx >= 0:
            self._indicators_timeframe_combo.setCurrentIndex(timeframe_idx)

    def get_config_dict(self) -> dict:
        """
        Extract current values from all input fields as a dictionary.

        Returns:
            Dict with keys matching AppConfig field names.
        """
        return {
            # API Keys
            "delta_api_key": self._delta_key_input.text(),
            "delta_api_secret": self._delta_secret_input.text(),
            "anthropic_api_key": self._anthropic_key_input.text(),
            # Trade Config
            "trade_sizing_mode": self._trade_sizing_mode_combo.currentText(),
            "trade_quantity_usd": self._trade_qty_spin.value(),
            "override_qty_from_webhook": self._override_qty_checkbox.isChecked(),
            "symbol_quantities": {s: spin.value() for s, spin in self._symbol_qty_spins.items()} if hasattr(self, "_symbol_qty_spins") else {},
            "product_symbol": self._product_symbol_input.text(),
            "trade_symbols": self._trade_symbols_input.text(),
            "base_sl_pct": self._base_sl_spin.value(),
            "base_tp_pct": self._base_tp_spin.value(),
            "min_ai_confidence": self._min_ai_confidence_spin.value(),
            # Risk Params
            "alpha_micro_margin_pct": self._alpha_margin_spin.value(),
            "beta_tp1_close_pct": self._beta_tp1_spin.value(),
            "gamma_tp1_atr_mult": self._gamma_tp1_spin.value(),
            "gamma_tp2_atr_mult": self._gamma_tp2_spin.value(),
            "gamma_trail_atr_mult": self._gamma_trail_spin.value(),
            "max_consecutive_losses": self._max_losses_spin.value(),
            "max_daily_loss_usd": self._max_daily_loss_spin.value(),
            # Server
            "server_port": self._port_spin.value(),
            "webhook_token": self._webhook_token_input.text(),
            "delta_use_testnet": self._testnet_checkbox.isChecked(),
            "delta_region": self._delta_region_combo.currentText(),
            "indicators_timeframe": self._indicators_timeframe_combo.currentText(),
            "auto_launch_ngrok": self._auto_ngrok_checkbox.isChecked(),
            "static_whitelisted_ip": self._static_ip_input.text().strip(),
        }

    # ══════════════════════════════════════════════════════════════════════════
    # BUTTON HANDLERS
    # ══════════════════════════════════════════════════════════════════════════

    def _on_save_clicked(self) -> None:
        """Handle save button click — extract config and emit signal."""
        config_dict = self.get_config_dict()
        self.settings_changed.emit(config_dict)

    def _on_flatten_clicked(self) -> None:
        """Handle flatten button click — emit the danger signal."""
        self.flatten_requested.emit()

    def _on_sizing_mode_changed(self, mode: str) -> None:
        """Update prefix/suffix and step size of the trade quantity spinbox based on sizing mode."""
        if mode == "USD":
            self._trade_qty_spin.setPrefix("$ ")
            self._trade_qty_spin.setSuffix("")
            self._trade_qty_spin.setSingleStep(10.0)
        else:
            self._trade_qty_spin.setPrefix("")
            self._trade_qty_spin.setSuffix(" Contracts")
            self._trade_qty_spin.setSingleStep(1.0)

        # Update dynamic spinboxes
        if hasattr(self, "_symbol_qty_spins") and self._symbol_qty_spins:
            for spin in self._symbol_qty_spins.values():
                if mode == "USD":
                    spin.setPrefix("$ ")
                    spin.setSuffix("")
                    spin.setSingleStep(10.0)
                else:
                    spin.setPrefix("")
                    spin.setSuffix(" Contracts")
                    spin.setSingleStep(1.0)

    def _on_symbols_editing_finished(self) -> None:
        """Handle active symbols text finished editing — update dynamic inputs."""
        # Save current dynamic values before rebuilding, so we don't lose the user's edits
        current_vals = {}
        if hasattr(self, "_symbol_qty_spins") and self._symbol_qty_spins:
            for s, spin in self._symbol_qty_spins.items():
                current_vals[s] = spin.value()
        self._update_symbol_qty_widgets(current_vals)

    def _update_symbol_qty_widgets(self, symbol_quantities_dict: Optional[dict] = None) -> None:
        """Dynamically generate quantity spinboxes for each normalized active symbol."""
        # Clean up existing layout
        while self._symbol_qty_layout.count() > 0:
            item = self._symbol_qty_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                # Clean up sub-layouts
                sub_layout = item.layout()
                while sub_layout.count() > 0:
                    sub_item = sub_layout.takeAt(0)
                    sub_widget = sub_item.widget()
                    if sub_widget:
                        sub_widget.deleteLater()

        self._symbol_qty_spins = {}

        symbols_str = self._trade_symbols_input.text()
        symbols = [s.strip().upper() for s in symbols_str.split(",") if s.strip()]
        
        mode = self._trade_sizing_mode_combo.currentText()

        for s in symbols:
            # Normalize symbol name (e.g., BTCUSD -> BTCUSD.P)
            norm_s = normalize_symbol(s)

            # Avoid duplicate rows for same normalized symbol
            if norm_s in self._symbol_qty_spins:
                continue

            spin = QDoubleSpinBox()
            spin.setRange(0.01, 100000.0)
            spin.setDecimals(2)
            
            # Format based on mode
            if mode == "USD":
                spin.setPrefix("$ ")
                spin.setSuffix("")
                spin.setSingleStep(10.0)
                default_val = 100.0
            else:
                spin.setPrefix("")
                spin.setSuffix(" Contracts")
                spin.setSingleStep(1.0)
                default_val = 4.0

            # Set value from dict, else use default_val
            val = default_val
            if symbol_quantities_dict and norm_s in symbol_quantities_dict:
                val = float(symbol_quantities_dict[norm_s])
            elif symbol_quantities_dict and s in symbol_quantities_dict:
                val = float(symbol_quantities_dict[s])
            
            spin.setValue(val)
            self._symbol_qty_spins[norm_s] = spin
            
            # Add row to layout
            self._symbol_qty_layout.addLayout(
                self._create_labeled_row(f"{norm_s} Quantity", spin)
            )
        
        # Adjust window size to fit newly added/removed widgets
        win = self.window()
        if win is not None:
            win.adjustSize()
