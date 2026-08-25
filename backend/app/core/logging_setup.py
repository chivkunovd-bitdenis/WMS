"""Лог исходящих HTTP-вызовов к маркетплейсам."""

from __future__ import annotations

import logging

from app.core.settings import settings


def setup_outbound_http_logging() -> None:
    """Пишет в лог каждый исходящий вызов: метод, адрес, код ответа.

    Нужен, чтобы можно было доказать, что WMS отправляла в WB и когда. Журнал
    операций (`fbs_wb_operations`) ведёт само приложение и показывает только
    штатный путь; этот лог снимается уровнем ниже — самим HTTP-клиентом, и
    поэтому ловит вызовы в обход журнала.

    Токен уходит в заголовке Authorization и в лог не попадает: httpx печатает
    только строку запроса и статус ответа, без заголовков и без тела.
    """
    httpx_logger = logging.getLogger("httpx")
    if not settings.log_outbound_http:
        httpx_logger.setLevel(logging.WARNING)
        return
    httpx_logger.setLevel(logging.INFO)
    # Логи uvicorn и celery идут через свои обработчики; свой добавляем только
    # когда наследовать нечего, иначе строки задвоятся.
    if not httpx_logger.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        httpx_logger.addHandler(handler)
