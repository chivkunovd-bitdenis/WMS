"""Fernet helpers for encrypting integration secrets at rest."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.settings import settings


def _fernet_key_material() -> bytes:
    raw = settings.wms_secrets_fernet_key
    if raw:
        return raw.encode("utf-8")
    digest = hashlib.sha256(settings.jwt_secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def get_fernet() -> Fernet:
    return Fernet(_fernet_key_material())


def encrypt_secret(plain: str) -> str:
    return get_fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(cipher_text: str) -> str:
    return get_fernet().decrypt(cipher_text.encode("ascii")).decode("utf-8")
