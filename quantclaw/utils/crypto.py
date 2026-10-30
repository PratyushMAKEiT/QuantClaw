# ==============================================================================
# quantclaw/utils/crypto.py — API Key Encryption At Rest
# ==============================================================================
"""
Handles encryption/decryption of sensitive API keys stored in config.json.
Uses Fernet symmetric encryption with a machine-specific key derived from
the Windows machine SID + a static salt.

NOTE: This is "encryption at rest" — it prevents casual inspection of the
config file but is NOT a secure vault. For production, consider Windows 
Credential Manager or a proper secrets manager.
"""

from __future__ import annotations

import base64
import hashlib
import os
import platform
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from quantclaw.config import get_app_data_dir


def _get_machine_key() -> bytes:
    """
    Derive a machine-specific encryption key.
    Uses hostname + OS info + a static salt as the seed.
    """
    seed_parts = [
        platform.node(),           # Machine hostname
        platform.machine(),        # CPU architecture
        os.environ.get("USERNAME", "default"),
        "QuantClaw-v1-salt-2024",  # Static application salt
    ]
    seed = "|".join(seed_parts).encode("utf-8")
    # Derive a 32-byte key using SHA-256, then base64-encode for Fernet
    key_bytes = hashlib.sha256(seed).digest()
    return base64.urlsafe_b64encode(key_bytes)


def _get_fernet() -> Fernet:
    """Get a Fernet instance with the machine-specific key."""
    return Fernet(_get_machine_key())


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a string value (e.g., an API key).
    Returns a base64-encoded encrypted string prefixed with 'ENC:'.
    """
    if not plaintext or plaintext.startswith("ENC:"):
        return plaintext  # Already encrypted or empty
    
    f = _get_fernet()
    encrypted = f.encrypt(plaintext.encode("utf-8"))
    return f"ENC:{encrypted.decode('utf-8')}"


def decrypt_value(encrypted: str) -> str:
    """
    Decrypt a previously encrypted value.
    If the value doesn't have the 'ENC:' prefix, returns it as-is (plaintext).
    """
    if not encrypted or not encrypted.startswith("ENC:"):
        return encrypted  # Not encrypted, return as-is
    
    try:
        f = _get_fernet()
        token = encrypted[4:].encode("utf-8")  # Strip 'ENC:' prefix
        return f.decrypt(token).decode("utf-8")
    except (InvalidToken, Exception):
        # If decryption fails (e.g., moved to different machine), return empty
        return ""


def is_encrypted(value: str) -> bool:
    """Check if a value is already encrypted."""
    return value.startswith("ENC:") if value else False
