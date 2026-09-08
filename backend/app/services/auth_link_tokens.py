"""Одноразовые ссылки из писем: приглашение и сброс пароля.

Никакой таблицы токенов здесь намеренно нет. Ссылка — это подписанный токен, в
который вложен отпечаток текущего пароля пользователя. Как только пароль сменён,
отпечаток перестаёт совпадать, и все выданные раньше ссылки становятся
недействительными. Одноразовость получается арифметикой, а не журналом, который
пришлось бы чистить и синхронизировать.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt

from app.core.settings import settings
from app.models.user import User

LinkPurpose = Literal["invite", "reset"]

_TOKEN_TYPE = "auth_link"


class AuthLinkError(Exception):
    pass


def _password_fingerprint(password_hash: str) -> str:
    """Короткий отпечаток пароля: сам хэш в токен не кладём."""
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


def create_auth_link_token(user: User, *, purpose: LinkPurpose) -> str:
    now = datetime.now(tz=UTC)
    payload: dict[str, Any] = {
        "typ": _TOKEN_TYPE,
        "purpose": purpose,
        "sub": str(user.id),
        "pwf": _password_fingerprint(user.password_hash),
        "iat": now,
        "exp": now + timedelta(hours=settings.auth_link_ttl_hours),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_auth_link_token(token: str) -> tuple[uuid.UUID, LinkPurpose, str]:
    """Разобрать токен. Бросает AuthLinkError на любой непорядок."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthLinkError("link_expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthLinkError("link_invalid") from exc

    if payload.get("typ") != _TOKEN_TYPE:
        raise AuthLinkError("link_invalid")
    purpose = payload.get("purpose")
    if purpose not in ("invite", "reset"):
        raise AuthLinkError("link_invalid")
    raw_sub = payload.get("sub")
    fingerprint = payload.get("pwf")
    if not isinstance(raw_sub, str) or not isinstance(fingerprint, str):
        raise AuthLinkError("link_invalid")
    try:
        user_id = uuid.UUID(raw_sub)
    except ValueError as exc:
        raise AuthLinkError("link_invalid") from exc
    return user_id, purpose, fingerprint


def fingerprint_matches(user: User, fingerprint: str) -> bool:
    return _password_fingerprint(user.password_hash) == fingerprint


def build_link(token: str, *, base_url: str, seller_portal: bool) -> str:
    """Собрать адрес страницы, на которую ведёт письмо.

    Селлер работает в своём портале на `/seller/`, сотрудник фулфилмента — в
    корневом. Ссылка должна вести сразу в нужный, иначе человек упирается в чужой
    экран входа.
    """
    root = base_url.rstrip("/")
    prefix = "/seller" if seller_portal else ""
    return f"{root}{prefix}/set-password?token={token}"
