"""Bounded client diagnostics in the existing server log; no persistent state."""
from __future__ import annotations

import json
import logging
import time
from threading import Lock

from pydantic_core import from_json

from app.models.user import User

logger = logging.getLogger(__name__)
MAX_BODY_BYTES = 16 * 1024
FIELD_LIMITS = {
    "message": 2000,
    "stack": 8000,
    "url": 1000,
    "screen": 300,
    "component": 500,
    "action": 300,
    "user_agent": 500,
    "app_build": 200,
}
_WINDOW_SECONDS = 60
_MAX_PER_WINDOW = 20
_counts: dict[tuple[str, str], tuple[float, int]] = {}
_lock = Lock()


def _allow(user: User) -> bool:
    now = time.monotonic()
    key = (str(user.tenant_id), str(user.id))
    with _lock:
        expired = [key for key, (start, _) in _counts.items() if now - start >= _WINDOW_SECONDS]
        for old in expired:
            del _counts[old]
        start, count = _counts.get(key, (now, 0))
        if count >= _MAX_PER_WINDOW:
            return False
        _counts[key] = (start, count + 1)
        return True


def _clip(value: str, limit: int) -> str:
    """Budget JSON-encoded UTF-8 bytes, including escapes, not Python characters."""
    result: list[str] = []
    size = 0
    for char in value:
        size += len(json.dumps(char, ensure_ascii=False).encode("utf-8", errors="replace")) - 2
        if size > limit:
            break
        result.append(char)
    return "".join(result)


def record_client_error(body: bytes, user: User) -> None:
    # The route also protects reading the stream. Reporting failures must never
    # break the operator's request, including failures of the logging handler.
    try:
        if not _allow(user):
            return
        # Preserve even an oversized first string without retaining an unlimited body.
        payload = from_json(
            body[:MAX_BODY_BYTES].decode("utf-8", errors="ignore"),
            allow_partial="trailing-strings",
        )
        if not isinstance(payload, dict):
            return
        fields: dict[str, str] = {}
        for name, limit in FIELD_LIMITS.items():
            value = payload.get(name, "")
            if not isinstance(value, str):
                value = ""
            if name == "stack":
                value = "\n".join(value.splitlines()[:40])
            fields[name] = _clip(value, limit)
        fields.update(tenant_id=str(user.tenant_id), user_id=str(user.id), role=user.role)
        # JSON escapes line breaks: one client report is exactly one log record.
        logger.error("client error %s", json.dumps(fields, ensure_ascii=False))
    except Exception:
        return
