from __future__ import annotations

import bcrypt


def hash_password(plain: str) -> str:
    data = plain.encode("utf-8")
    # bcrypt only uses first 72 bytes; longer inputs can raise.
    if len(data) > 72:
        data = data[:72]
    hashed = bcrypt.hashpw(data, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
