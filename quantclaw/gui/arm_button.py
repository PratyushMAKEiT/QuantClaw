# ==============================================================================
# quantclaw/gui/arm_button.py — Circular ARM Toggle Button
# ==============================================================================
"""
Large circular toggle button (80px diameter) that controls the armed/disarmed
state of the QuantClaw trading system.

States:
  DISARMED → Red glow, pause ⏸ icon, label shows 'DISARMED'
  ARMED    → Green glow with pulse animation, play ▶ icon, label shows 'ARMED ● LIVE'

The glow pulse uses QGraphicsOpacityEffect + QPropertyAnimation to cycle the
button opacity between 0.6 and 1.0 when armed, creating a breathing effect.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QPushButton, QVBoxLayout, QWidget, QLabel, QGraphicsOpacityEffect,
)
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, pyqtSignal, QByteArray,
)


# ==============================================================================
# ARM BUTTON WIDGET
# ==============================================================================

class ArmButton(QWidget):
    """
    Circular toggle button that arms/disarms the QuantClaw trading engine.

    Signals:
        armed_changed(bool): Emitted when the arm state changes via user click.

    Properties:
        is_armed (bool): Read-only property returning the current arm state.

    Usage:
        arm_btn = ArmButton()
        arm_btn.armed_changed.connect(on_arm_toggled)
    """

    # ── Signals ────────────────────────────────────────────────────────────
    armed_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # ── Internal State ─────────────────────────────────────────────────
        self._armed: bool = False

        # ── Build the UI ───────────────────────────────────────────────────
        self._setup_ui()

        # ── Setup Glow Animation ───────────────────────────────────────────
        self._setup_glow_animation()

        # ── Connect click ──────────────────────────────────────────────────
        self._button.clicked.connect(self._on_clicked)

        # ── Apply initial state ────────────────────────────────────────────
        self._apply_state()

    # ══════════════════════════════════════════════════════════════════════════
    # UI CONSTRUCTION
    # ══════════════════════════════════════════════════════════════════════════

    def _setup_ui(self) -> None:
        """Build the button + label vertical layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 4)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # ── Circular Button ────────────────────────────────────────────────
        self._button = QPushButton("⏸")
        self._button.setObjectName("armButton")
        self._button.setFixedSize(80, 80)
        self._button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._button.setToolTip("Click to arm/disarm the trading engine")

        # ── Status Label ───────────────────────────────────────────────────
        self._label = QLabel("DISARMED")
        self._label.setObjectName("armLabel")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ── Add to Layout (centered) ──────────────────────────────────────
        layout.addWidget(self._button, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._label, alignment=Qt.AlignmentFlag.AlignHCenter)

    # ══════════════════════════════════════════════════════════════════════════
    # GLOW ANIMATION SETUP
    # ══════════════════════════════════════════════════════════════════════════

    def _setup_glow_animation(self) -> None:
        """
        Create the QGraphicsOpacityEffect and QPropertyAnimation for the
        breathing glow pulse when armed.

        Animation: opacity cycles 0.6 → 1.0 → 0.6 in an infinite loop
        using InOutSine easing for smooth organic feel.
        """
        # Graphics opacity effect applied to the button
        self._opacity_effect = QGraphicsOpacityEffect(self._button)
        self._opacity_effect.setOpacity(1.0)
        self._button.setGraphicsEffect(self._opacity_effect)

        # Property animation targeting the effect's opacity
        self._glow_anim = QPropertyAnimation(
            self._opacity_effect,
            QByteArray(b"opacity"),
        )
        self._glow_anim.setDuration(1200)            # 1.2s per cycle
        self._glow_anim.setStartValue(0.6)            # Dim phase
        self._glow_anim.setEndValue(1.0)               # Full brightness
        self._glow_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._glow_anim.setLoopCount(-1)               # Infinite loop

    # ══════════════════════════════════════════════════════════════════════════
    # STATE MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════════

    @property
    def is_armed(self) -> bool:
        """Read-only property: whether the system is currently armed."""
        return self._armed

    def set_armed(self, armed: bool) -> None:
        """
        Programmatically set the arm state WITHOUT emitting the signal.
        Use this for restoring state from config or external updates.

        Args:
            armed: True to arm, False to disarm.
        """
        if self._armed == armed:
            return  # No change needed
        self._armed = armed
        self._apply_state()

    def _on_clicked(self) -> None:
        """Handle button click — toggle state and emit signal."""
        self._armed = not self._armed
        self._apply_state()
        self.armed_changed.emit(self._armed)

    def _apply_state(self) -> None:
        """
        Apply the visual state based on self._armed.
        Updates: button icon, objectName (for QSS), label text, and glow animation.
        """
        if self._armed:
            # ── ARMED STATE ────────────────────────────────────────────────
            self._button.setText("▶")
            self._button.setObjectName("armButtonArmed")
            self._label.setText("ARMED ● LIVE")
            # Use inline style on the label to color the dot green
            self._label.setStyleSheet(
                "color: #00E676; font-size: 11px; font-weight: 600; "
                "letter-spacing: 2px;"
            )
            # Start breathing glow animation
            self._glow_anim.start()
        else:
            # ── DISARMED STATE ─────────────────────────────────────────────
            self._button.setText("⏸")
            self._button.setObjectName("armButton")
            self._label.setText("DISARMED")
            # Reset label to default style (let QSS handle it)
            self._label.setStyleSheet("")
            # Stop glow animation and reset opacity to full
            self._glow_anim.stop()
            self._opacity_effect.setOpacity(1.0)

        # ── Force QSS Re-evaluation ────────────────────────────────────────
        # After changing objectName, Qt does not automatically re-apply
        # stylesheets. We must manually unpolish + polish the widget.
        self._button.style().unpolish(self._button)
        self._button.style().polish(self._button)
        self._button.update()
