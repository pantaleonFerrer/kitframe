from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from kitframe.settings import Settings


def _key(settings: Settings) -> bytes:
    raw = base64.b64decode(settings.app_encryption_key)
    if len(raw) != 32:
        raise RuntimeError("APP_ENCRYPTION_KEY must be 32 bytes base64")
    return raw


def encrypt_token(settings: Settings, token: str) -> bytes:
    key = _key(settings)
    nonce = os.urandom(12)
    aes = AESGCM(key)
    ct = aes.encrypt(nonce, token.encode("utf-8"), None)
    # key_id=1 | nonce | ciphertext
    return b"\x01" + nonce + ct


def decrypt_token(settings: Settings, blob: bytes) -> str:
    key = _key(settings)
    nonce, ct = blob[1:13], blob[13:]
    aes = AESGCM(key)
    return aes.decrypt(nonce, ct, None).decode("utf-8")
