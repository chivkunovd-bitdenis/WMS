"""Bounded per-process login throttling, charged before authentication (WMS-270).

Failures and in-flight attempts share a per-client sliding window. A successful
login removes only its own attempt. Request.client comes from the ASGI server;
proxy headers must be resolved there using explicitly trusted proxy addresses.
"""
from __future__ import annotations

import math
import os
import threading
import time
from collections import deque
from contextlib import suppress
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

_DEFAULT_MAX_ATTEMPTS = max(1, int(os.environ.get("WMS_LOGIN_MAX_ATTEMPTS", "5")))
_DEFAULT_WINDOW_SECONDS = max(1, int(os.environ.get("WMS_LOGIN_WINDOW_SECONDS", "60")))
_MAX_CLIENTS = 10_000


@dataclass
class _Config:
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS
    window_seconds: int = _DEFAULT_WINDOW_SECONDS


_config = _Config()
_lock = threading.Lock()
_attempts: dict[str, deque[float]] = {}


def _client_ip(request: Request) -> str:
    # Never trust a caller-supplied X-Forwarded-For at the application layer.
    return request.client.host if request.client is not None else "unknown"


def _prune(attempts: deque[float], now: float) -> None:
    horizon = now - _config.window_seconds
    while attempts and attempts[0] <= horizon:
        attempts.popleft()


def _reject(retry_after: float) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="too_many_attempts",
        headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
    )


def check_login_rate_limit(*, request: Request, email: str) -> None:
    """Reserve an attempt atomically before DB/password work, including bursts."""
    ip = _client_ip(request)
    with _lock:
        now = time.monotonic()
        attempts = _attempts.get(ip)
        if attempts is None:
            # New clients cannot grow memory indefinitely. Expired clients are
            # reclaimed, but active limits are never evicted to admit an attacker.
            for key in list(_attempts):
                _prune(_attempts[key], now)
                if not _attempts[key]:
                    del _attempts[key]
            if len(_attempts) >= _MAX_CLIENTS:
                _reject(_config.window_seconds)
            attempts = deque()
            _attempts[ip] = attempts
        _prune(attempts, now)
        if len(attempts) >= _config.max_attempts:
            _reject(_config.window_seconds - (now - attempts[0]))
        attempts.append(now)
        request.state.wms_login_ticket = (ip, now)


def register_login_success(*, request: Request, email: str) -> None:
    """Remove this successful attempt without resetting other failures/in-flight work."""
    ticket = getattr(request.state, "wms_login_ticket", None)
    if ticket is None:
        return
    ip, occurred_at = ticket
    with _lock:
        attempts = _attempts.get(ip)
        if attempts is not None:
            _prune(attempts, time.monotonic())
            with suppress(ValueError):
                attempts.remove(occurred_at)
            if not attempts:
                _attempts.pop(ip, None)
        request.state.wms_login_ticket = None


def reset_rate_limit_state() -> None:
    """Test isolation only."""
    with _lock:
        _attempts.clear()


def configure_for_tests(
    *, max_attempts: int | None = None, window_seconds: int | None = None,
) -> None:
    with _lock:
        if max_attempts is not None:
            _config.max_attempts = max(1, max_attempts)
        if window_seconds is not None:
            _config.window_seconds = max(1, window_seconds)


def get_config() -> tuple[int, int]:
    return _config.max_attempts, _config.window_seconds
