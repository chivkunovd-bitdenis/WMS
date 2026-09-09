"""In-process rate limit for /auth/login (WMS-270).

Задача: не давать перебирать пароли и почты формой входа. Ограничение вводится
на входе — оператор не сможет отправить более чем N неуспешных попыток за окно
M секунд с одного IP и с одной пары (IP, почта). Успешный вход сбрасывает
счётчик той же пары.

Здесь намеренно нет ни отдельной таблицы, ни редиса. Хранится словарь в памяти
процесса. В боевом compose на API один экземпляр Uvicorn — этого достаточно
для защиты от перебора руками и скриптом. Если однажды понадобится масштабировать
за LB — заменим на общий счётчик, а поверхность останется той же.

Реализация — токен-бакет с фиксированным окном: держим deque моментов неуспехов
и, прежде чем принять новый запрос, отбрасываем всё, что старше окна.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

# Публичные ручки для тестов и настройки под окружение. Значения по умолчанию
# консервативные: 5 неуспехов за 60 секунд.
_DEFAULT_MAX_ATTEMPTS = int(os.environ.get("WMS_LOGIN_MAX_ATTEMPTS", "5"))
_DEFAULT_WINDOW_SECONDS = int(os.environ.get("WMS_LOGIN_WINDOW_SECONDS", "60"))


@dataclass
class _Config:
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS
    window_seconds: int = _DEFAULT_WINDOW_SECONDS


_config = _Config()
_lock = threading.Lock()
# Ключи хранятся раздельно: чистый IP и пара (IP, hashed_email).
# Хеширование почты — чтобы в памяти не гулял открытый email в структуре, которую
# отладчик мог бы вывести в лог.
_failures_ip: dict[str, deque[float]] = defaultdict(deque)
_failures_ip_email: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    """Клиентский IP. За прокси берём первый X-Forwarded-For, иначе адрес соединения.

    Для тестов ASGI request.client может быть None — тогда возвращаем "unknown",
    чтобы ключ был стабильным, а тест не падал на None.
    """
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",", 1)[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


def _email_key(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:16]


def _prune(dq: deque[float], now: float) -> None:
    horizon = now - _config.window_seconds
    while dq and dq[0] < horizon:
        dq.popleft()


def check_login_rate_limit(*, request: Request, email: str) -> None:
    """Проверить перед обработкой; 429 — если попыток слишком много.

    Проверяются оба ключа: суммарно с IP и отдельно на пару (IP, почта). Если
    любой превысил окно — отвечаем 429 с Retry-After. Само сообщение не выдаёт,
    существует ли аккаунт: срабатывает по числу попыток, не по успеху/провалу.
    """
    now = time.monotonic()
    ip = _client_ip(request)
    email_key = _email_key(email)
    with _lock:
        dq_ip = _failures_ip[ip]
        dq_pair = _failures_ip_email[(ip, email_key)]
        _prune(dq_ip, now)
        _prune(dq_pair, now)
        # Если по IP или по паре уже достигли лимита — ответ 429.
        if len(dq_ip) >= _config.max_attempts or len(dq_pair) >= _config.max_attempts:
            oldest = min(
                (dq_ip[0] if dq_ip else now),
                (dq_pair[0] if dq_pair else now),
            )
            retry_after = max(1, int(_config.window_seconds - (now - oldest)) + 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="too_many_attempts",
                headers={"Retry-After": str(retry_after)},
            )


def register_login_failure(*, request: Request, email: str) -> None:
    """Записать неуспешную попытку. Успех сбрасывает пару."""
    now = time.monotonic()
    ip = _client_ip(request)
    email_key = _email_key(email)
    with _lock:
        _failures_ip[ip].append(now)
        _failures_ip_email[(ip, email_key)].append(now)


def register_login_success(*, request: Request, email: str) -> None:
    """Сбросить счётчик пары (IP, почта) при успешном входе.

    Счётчик по чистому IP не трогаем: если с одного IP кто-то заходит успешно, а
    в фоне другой сеанс перебирает соседнюю почту, обнулять общий счётчик
    некорректно. Пара (IP, почта) — это тот, кто только что доказал знание пароля.
    """
    now = time.monotonic()
    ip = _client_ip(request)
    email_key = _email_key(email)
    with _lock:
        _prune(_failures_ip[ip], now)
        _failures_ip_email.pop((ip, email_key), None)


def reset_rate_limit_state() -> None:
    """Только для тестов: очистить счётчики между случаями."""
    with _lock:
        _failures_ip.clear()
        _failures_ip_email.clear()


def configure_for_tests(
    *, max_attempts: int | None = None, window_seconds: int | None = None
) -> None:
    """Только для тестов: временно поменять окно/лимит."""
    with _lock:
        if max_attempts is not None:
            _config.max_attempts = max_attempts
        if window_seconds is not None:
            _config.window_seconds = window_seconds


def get_config() -> tuple[int, int]:
    """Вернуть текущие (max_attempts, window_seconds) — для тестов и диагностики."""
    return _config.max_attempts, _config.window_seconds
