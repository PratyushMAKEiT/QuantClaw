# ==============================================================================
# quantclaw/utils/logger.py — Structured Logging
# ==============================================================================
"""
Centralized logging for QuantClaw.
  - Console output with color-coded levels
  - File output to %APPDATA%/QuantClaw/logs/quantclaw.log
  - Rotating log files (5MB max, 3 backups)
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from quantclaw.config import get_log_dir


# Custom log format with timestamps and module context
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-18s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(
    name: str = "quantclaw",
    level: int = logging.DEBUG,
    log_to_file: bool = True,
) -> logging.Logger:
    """
    Create and configure a logger instance.
    
    Args:
        name: Logger name (use module name for context, e.g. 'quantclaw.exchange')
        level: Minimum log level
        log_to_file: Whether to also write to file
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    class SafeStreamWrapper:
        def __init__(self, stream):
            self.stream = stream
        def write(self, data):
            if self.stream is None:
                return
            try:
                self.stream.write(data)
            except UnicodeEncodeError:
                encoding = getattr(self.stream, 'encoding', 'ascii') or 'ascii'
                try:
                    self.stream.write(data.encode(encoding, errors='replace').decode(encoding))
                except Exception:
                    pass
            except Exception:
                pass
        def flush(self):
            if self.stream is None:
                return
            try:
                self.stream.flush()
            except Exception:
                pass

    # ── Console Handler ────────────────────────────────────────────────
    console_handler = logging.StreamHandler(SafeStreamWrapper(sys.stdout))
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ── File Handler (Rotating) ────────────────────────────────────────
    if log_to_file:
        try:
            log_file = get_log_dir() / f"{name.replace('.', '_')}.log"
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=5 * 1024 * 1024,  # 5 MB
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except (PermissionError, OSError) as e:
            logger.warning(f"Could not set up file logging: {e}")

    return logger


# ── In-Memory Global Log Buffer for Web Dashboard & Bot Terminal ────────────
LOG_MEMORY_BUFFER: List[str] = []
MAX_MEMORY_LOGS = 500


class MemoryLogHandler(logging.Handler):
    """Pipes formatted logs into the in-memory buffer for real-time dashboard viewing."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            LOG_MEMORY_BUFFER.append(msg)
            if len(LOG_MEMORY_BUFFER) > MAX_MEMORY_LOGS:
                LOG_MEMORY_BUFFER.pop(0)
        except Exception:
            pass


def get_recent_logs(limit: int = 100) -> List[str]:
    """Retrieve the most recent log lines from memory buffer."""
    return list(LOG_MEMORY_BUFFER[-limit:])


# Pre-configured loggers for each module
def get_logger(module: str) -> logging.Logger:
    """Get a logger for a specific QuantClaw module."""
    logger = setup_logger(f"quantclaw.{module}")
    # Ensure MemoryLogHandler is attached
    if not any(isinstance(h, MemoryLogHandler) for h in logger.handlers):
        mem_handler = MemoryLogHandler()
        mem_handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s | %(levelname)-5s | %(message)s", datefmt="%H:%M:%S")
        mem_handler.setFormatter(formatter)
        logger.addHandler(mem_handler)
    return logger
