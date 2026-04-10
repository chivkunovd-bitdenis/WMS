from __future__ import annotations

import bcrypt


def hash_password(plain: str) -> str:
    data = plain.encode("utf-8")
    hashed = bcrypt.hashpw(data, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
