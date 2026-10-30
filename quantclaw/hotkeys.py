# ==============================================================================
# quantclaw/hotkeys.py — Global Windows Hotkey Handler
# ==============================================================================
"""
Registers global Windows hotkeys that work even when QuantClaw is not focused.

Hotkeys:
  Ctrl+Shift+E → Flatten all positions (emergency kill switch)
  Ctrl+Shift+P → Toggle ARM state (play/pause)

Uses the `keyboard` library for global hooks. Runs in a background thread
and communicates with the PyQt6 GUI via thread-safe signals.
"""

from __future__ import annotations

import threading
from typing import Optional, Callable

from quantclaw.utils.logger import get_logger

logger = get_logger("hotkeys")


class GlobalHotkeys:
    """
    Manages global Windows keyboard shortcuts.
    
    These hotkeys work system-wide — even when QuantClaw is minimized
    or another window is focused. Essential for emergency flatten.
    """

    def __init__(
        self,
        on_flatten: Optional[Callable[[], None]] = None,
        on_toggle_arm: Optional[Callable[[], None]] = None,
    ):
        """
        Args:
            on_flatten: Callback for Ctrl+Shift+E (flatten all positions)
            on_toggle_arm: Callback for Ctrl+Shift+P (toggle arm state)
        """
        self.on_flatten = on_flatten
        self.on_toggle_arm = on_toggle_arm
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._keyboard = None

    def start(self):
        """Start listening for global hotkeys in a background thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._listen,
            daemon=True,
            name="QuantClaw-Hotkeys",
        )
        self._thread.start()
        logger.info("⌨️  Global hotkeys registered: Ctrl+Shift+E (flatten), Ctrl+Shift+P (arm toggle)")

    def _listen(self):
        """Internal: register hotkeys and block on listener."""
        try:
            import keyboard

            # ── Ctrl+Shift+E → Emergency Flatten ──────────────────────────
            keyboard.add_hotkey(
                "ctrl+shift+e",
                self._handle_flatten,
                suppress=False,  # Don't block the key from other apps
            )

            # ── Ctrl+Shift+P → Toggle ARM State ──────────────────────────
            keyboard.add_hotkey(
                "ctrl+shift+p",
                self._handle_toggle_arm,
                suppress=False,
            )

            # Block this thread until stop() is called
            keyboard.wait()

        except ImportError:
            logger.warning(
                "⚠️  'keyboard' library not installed. Global hotkeys disabled. "
                "Install with: pip install keyboard"
            )
        except Exception as e:
            logger.error(f"Hotkey listener error: {e}")

    def _handle_flatten(self):
        """Handle Ctrl+Shift+E: Flatten all positions."""
        logger.warning("🚨 HOTKEY: Ctrl+Shift+E → FLATTEN ALL")
        if self.on_flatten:
            try:
                self.on_flatten()
            except Exception as e:
                logger.error(f"Flatten callback error: {e}")

    def _handle_toggle_arm(self):
        """Handle Ctrl+Shift+P: Toggle ARM state."""
        logger.info("⌨️  HOTKEY: Ctrl+Shift+P → TOGGLE ARM")
        if self.on_toggle_arm:
            try:
                self.on_toggle_arm()
            except Exception as e:
                logger.error(f"Toggle ARM callback error: {e}")

    def stop(self):
        """Stop listening for hotkeys and clean up."""
        self._running = False
        try:
            import keyboard
            keyboard.unhook_all()
        except Exception:
            pass
        logger.info("⌨️  Global hotkeys unregistered")
