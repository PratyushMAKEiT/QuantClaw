# ==============================================================================
# quantclaw/gui/styles.py — Dark Glassmorphic QSS Theme
# ==============================================================================
"""
Complete Qt StyleSheet (QSS) for the QuantClaw floating widget.
Design language:
  - Dark glassmorphic background (deep navy/charcoal with translucency)
  - Cyan (#00E5FF) primary accent with electric purple (#B388FF) secondary
  - Neon glow borders on interactive elements
  - Segoe UI font family (Windows native)
  - Smooth transitions and hover states
"""

# ── Color Palette ──────────────────────────────────────────────────────────────
COLORS = {
    "bg_primary":     "rgba(10, 10, 20, 235)",      # Main window background
    "bg_secondary":   "rgba(20, 22, 35, 220)",      # Card backgrounds
    "bg_input":       "rgba(12, 14, 25, 250)",      # Input field background
    "bg_hover":       "rgba(30, 35, 55, 200)",      # Hover state
    "border":         "rgba(60, 70, 100, 100)",      # Subtle borders
    "border_focus":   "#00E5FF",                     # Cyan focus ring
    "accent_cyan":    "#00E5FF",                     # Primary accent
    "accent_purple":  "#B388FF",                     # Secondary accent
    "text_primary":   "#E8EAED",                     # Main text
    "text_secondary": "#9AA0A6",                     # Muted text
    "text_dim":       "#5F6368",                     # Very muted text
    "success":        "#00E676",                     # Green — profit / armed
    "danger":         "#FF5252",                     # Red — loss / danger
    "warning":        "#FFD740",                     # Yellow — caution
    "regime_alpha":   "#FF5252",                     # Alpha = red
    "regime_beta":    "#FFD740",                     # Beta = yellow
    "regime_gamma":   "#00E676",                     # Gamma = green
}

# ── Main Stylesheet ───────────────────────────────────────────────────────────

MAIN_STYLESHEET = f"""
/* ═══════════════════════════════════════════════════════════════════════════
   GLOBAL
   ═══════════════════════════════════════════════════════════════════════════ */

* {{
    font-family: "Segoe UI", "Inter", sans-serif;
    color: {COLORS["text_primary"]};
    outline: none;
}}

QMainWindow {{
    background-color: {COLORS["bg_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 12px;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   TITLE BAR
   ═══════════════════════════════════════════════════════════════════════════ */

#titleBar {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(0, 229, 255, 30),
        stop:1 rgba(179, 136, 255, 30));
    border-bottom: 1px solid {COLORS["border"]};
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
    padding: 4px 8px;
    min-height: 32px;
}}

#titleLabel {{
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 2px;
    color: {COLORS["accent_cyan"]};
}}

#titleBarBtn {{
    background: transparent;
    border: none;
    color: {COLORS["text_secondary"]};
    font-size: 14px;
    padding: 4px 8px;
    border-radius: 4px;
}}

#titleBarBtn:hover {{
    background: {COLORS["bg_hover"]};
    color: {COLORS["text_primary"]};
}}

#closeBtn:hover {{
    background: {COLORS["danger"]};
    color: white;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   CARDS (Telemetry HUD panels)
   ═══════════════════════════════════════════════════════════════════════════ */

#hudCard {{
    background-color: {COLORS["bg_secondary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 6px 10px;
}}

#hudCard:hover {{
    border-color: rgba(0, 229, 255, 60);
}}

#hudCardLabel {{
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.5px;
    color: {COLORS["text_secondary"]};
    text-transform: uppercase;
}}

#hudCardValue {{
    font-size: 20px;
    font-weight: 700;
    color: {COLORS["text_primary"]};
}}

#pnlPositive {{
    color: {COLORS["success"]};
    font-size: 20px;
    font-weight: 700;
}}

#pnlNegative {{
    color: {COLORS["danger"]};
    font-size: 20px;
    font-weight: 700;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   ARM BUTTON
   ═══════════════════════════════════════════════════════════════════════════ */

#armButton {{
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
        stop:0 rgba(255, 82, 82, 80),
        stop:1 rgba(255, 82, 82, 20));
    border: 3px solid {COLORS["danger"]};
    border-radius: 40px;
    min-width: 80px;
    min-height: 80px;
    max-width: 80px;
    max-height: 80px;
    font-size: 28px;
    color: {COLORS["danger"]};
}}

#armButton:hover {{
    border-color: {COLORS["text_primary"]};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
        stop:0 rgba(255, 82, 82, 120),
        stop:1 rgba(255, 82, 82, 40));
}}

#armButtonArmed {{
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
        stop:0 rgba(0, 230, 118, 80),
        stop:1 rgba(0, 230, 118, 20));
    border: 3px solid {COLORS["success"]};
    border-radius: 40px;
    min-width: 80px;
    min-height: 80px;
    max-width: 80px;
    max-height: 80px;
    font-size: 28px;
    color: {COLORS["success"]};
}}

#armButtonArmed:hover {{
    border-color: {COLORS["text_primary"]};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
        stop:0 rgba(0, 230, 118, 120),
        stop:1 rgba(0, 230, 118, 40));
}}

#armLabel {{
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 2px;
    color: {COLORS["text_secondary"]};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   REGIME BADGES
   ═══════════════════════════════════════════════════════════════════════════ */

#regimeAlpha {{
    background: rgba(255, 82, 82, 40);
    border: 1px solid {COLORS["regime_alpha"]};
    border-radius: 6px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 700;
    color: {COLORS["regime_alpha"]};
    letter-spacing: 1px;
}}

#regimeBeta {{
    background: rgba(255, 215, 64, 40);
    border: 1px solid {COLORS["regime_beta"]};
    border-radius: 6px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 700;
    color: {COLORS["regime_beta"]};
    letter-spacing: 1px;
}}

#regimeGamma {{
    background: rgba(0, 230, 118, 40);
    border: 1px solid {COLORS["regime_gamma"]};
    border-radius: 6px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 700;
    color: {COLORS["regime_gamma"]};
    letter-spacing: 1px;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   SETTINGS PANEL
   ═══════════════════════════════════════════════════════════════════════════ */

#settingsToggle {{
    background: transparent;
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 6px 16px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    color: {COLORS["text_secondary"]};
}}

#settingsToggle:hover {{
    border-color: {COLORS["accent_cyan"]};
    color: {COLORS["accent_cyan"]};
    background: rgba(0, 229, 255, 15);
}}

#settingsMaxToggle {{
    background: transparent;
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 4px;
    font-size: 14px;
    font-weight: 600;
    color: {COLORS["text_secondary"]};
}}

#settingsMaxToggle:hover {{
    border-color: {COLORS["accent_cyan"]};
    color: {COLORS["accent_cyan"]};
    background: rgba(0, 229, 255, 15);
}}

#settingsMaxToggle:disabled {{
    border-color: {COLORS["border"]};
    color: {COLORS["text_dim"]};
    background: transparent;
}}

#settingsPanel {{
    background-color: {COLORS["bg_secondary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 12px;
}}

#settingsSection {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.5px;
    color: {COLORS["accent_purple"]};
    padding-top: 8px;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   INPUT FIELDS
   ═══════════════════════════════════════════════════════════════════════════ */

QLineEdit {{
    background-color: {COLORS["bg_input"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
    color: {COLORS["text_primary"]};
    selection-background-color: rgba(0, 229, 255, 60);
}}

QLineEdit:focus {{
    border-color: {COLORS["border_focus"]};
    background-color: rgba(0, 229, 255, 8);
}}

QLineEdit:disabled {{
    color: {COLORS["text_dim"]};
    background-color: rgba(30, 30, 40, 200);
}}

QDoubleSpinBox, QSpinBox {{
    background-color: {COLORS["bg_input"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
    color: {COLORS["text_primary"]};
}}

QDoubleSpinBox:focus, QSpinBox:focus {{
    border-color: {COLORS["border_focus"]};
}}

QLabel {{
    font-size: 11px;
    color: {COLORS["text_secondary"]};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   BUTTONS
   ═══════════════════════════════════════════════════════════════════════════ */

QPushButton {{
    background-color: rgba(0, 229, 255, 20);
    border: 1px solid {COLORS["accent_cyan"]};
    border-radius: 6px;
    padding: 8px 20px;
    font-size: 12px;
    font-weight: 600;
    color: {COLORS["accent_cyan"]};
}}

QPushButton:hover {{
    background-color: rgba(0, 229, 255, 40);
    border-color: {COLORS["text_primary"]};
    color: {COLORS["text_primary"]};
}}

QPushButton:pressed {{
    background-color: rgba(0, 229, 255, 60);
}}

#dangerButton {{
    background-color: rgba(255, 82, 82, 20);
    border: 1px solid {COLORS["danger"]};
    color: {COLORS["danger"]};
}}

#dangerButton:hover {{
    background-color: rgba(255, 82, 82, 50);
    color: white;
}}

#saveButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(0, 229, 255, 40),
        stop:1 rgba(179, 136, 255, 40));
    border: 1px solid {COLORS["accent_cyan"]};
    font-weight: 700;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   STATUS INDICATORS (connection dots)
   ═══════════════════════════════════════════════════════════════════════════ */

#statusDotOnline {{
    color: {COLORS["success"]};
    font-size: 10px;
}}

#statusDotOffline {{
    color: {COLORS["danger"]};
    font-size: 10px;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   TRADE LOG (scrollable list)
   ═══════════════════════════════════════════════════════════════════════════ */

#tradeLog {{
    background-color: {COLORS["bg_input"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 6px;
    font-size: 11px;
    font-family: "Cascadia Code", "Consolas", monospace;
    color: {COLORS["text_secondary"]};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   SCROLLBARS
   ═══════════════════════════════════════════════════════════════════════════ */

QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {COLORS["border"]};
    border-radius: 3px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background: {COLORS["accent_cyan"]};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    height: 0;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   CHECKBOX / TOGGLE
   ═══════════════════════════════════════════════════════════════════════════ */

QCheckBox {{
    font-size: 11px;
    color: {COLORS["text_secondary"]};
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {COLORS["border"]};
    border-radius: 4px;
    background: {COLORS["bg_input"]};
}}

QCheckBox::indicator:checked {{
    background: {COLORS["accent_cyan"]};
    border-color: {COLORS["accent_cyan"]};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   TOOLTIPS
   ═══════════════════════════════════════════════════════════════════════════ */

QToolTip {{
    background-color: {COLORS["bg_secondary"]};
    border: 1px solid {COLORS["accent_cyan"]};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 11px;
    color: {COLORS["text_primary"]};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   SEPARATOR
   ═══════════════════════════════════════════════════════════════════════════ */

#separator {{
    background-color: {COLORS["border"]};
    max-height: 1px;
    min-height: 1px;
    margin: 4px 0;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   TABLE WIDGET (Active Positions)
   ═══════════════════════════════════════════════════════════════════════════ */

QTableWidget {{
    background-color: transparent;
    border: none;
    gridline-color: rgba(60, 70, 100, 40);
    font-size: 11px;
}}

QHeaderView::section {{
    background-color: rgba(20, 22, 35, 120);
    color: #9AA0A6;
    padding: 4px;
    border: none;
    border-bottom: 1px solid rgba(60, 70, 100, 80);
    font-weight: bold;
    font-size: 10px;
    text-transform: uppercase;
}}

QTableWidget::item {{
    padding: 4px;
    border-bottom: 1px solid rgba(60, 70, 100, 40);
    background-color: transparent;
    color: #E8EAED;
}}

QTableWidget::item:selected {{
    background-color: rgba(0, 229, 255, 30);
    color: #E8EAED;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN SCROLL AREA
   ═══════════════════════════════════════════════════════════════════════════ */

#mainScrollArea {{
    background: transparent;
    border: none;
}}

#mainScrollArea > QWidget > QWidget {{
    background: transparent;
}}

#leftColumn {{
    background: transparent;
}}

#mainScrollArea QScrollBar:vertical {{
    background: rgba(20, 22, 35, 100);
    width: 6px;
    border-radius: 3px;
    margin: 2px 0;
}}

#mainScrollArea QScrollBar::handle:vertical {{
    background: rgba(0, 229, 255, 80);
    min-height: 30px;
    border-radius: 3px;
}}

#mainScrollArea QScrollBar::handle:vertical:hover {{
    background: rgba(0, 229, 255, 140);
}}

#mainScrollArea QScrollBar::add-line:vertical,
#mainScrollArea QScrollBar::sub-line:vertical {{
    height: 0;
    background: none;
}}
"""

# ── Status Message Colors ──────────────────────────────────────────────────────

STATUS_COLORS = {
    "AI_CONFIRMING":  COLORS["warning"],
    "AI_REJECTED":    COLORS["danger"],
    "AI_TIMEOUT":     COLORS["danger"],
    "EXECUTING":      COLORS["accent_cyan"],
    "ACTIVE":         COLORS["success"],
    "PARTIAL_CLOSE":  COLORS["accent_purple"],
    "CLOSED":         COLORS["text_secondary"],
    "ERROR":          COLORS["danger"],
    "PENDING":        COLORS["text_dim"],
}
