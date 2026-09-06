"""Отправка писем: приглашение в систему и сброс пароля.

Почта настраивается переменными окружения. Пока `WMS_SMTP_HOST` пуст, письма
никуда не уходят — ссылка пишется в лог. Так код можно выкатить на боевой сервер
до того, как заведён ящик, и ничего не сломается.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.header import Header
from email.message import EmailMessage
from email.utils import formataddr

from app.core.settings import settings

logger = logging.getLogger(__name__)


def mail_configured() -> bool:
    return bool(settings.smtp_host.strip() and settings.smtp_user.strip())


def _sender() -> str:
    address = (settings.mail_from or settings.smtp_user).strip()
    name = settings.mail_from_name.strip()
    if not name:
        return address
    return formataddr((str(Header(name, "utf-8")), address))


def _build(to: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _sender()
    message["To"] = to
    message.set_content(body)
    return message


def send_email_sync(*, to: str, subject: str, body: str) -> bool:
    """Отправить письмо. Возвращает True, если письмо ушло.

    Никогда не бросает исключение наружу: недоступная почта не должна ронять
    запрос оператора. Неудача пишется в лог и возвращается False.
    """
    if not mail_configured():
        logger.warning(
            "mail_not_configured: письмо не отправлено, to=%s subject=%s body=%s",
            to,
            subject,
            body,
        )
        return False

    message = _build(to, subject, body)
    host = settings.smtp_host.strip()
    port = settings.smtp_port
    timeout = settings.smtp_timeout_sec
    context = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=timeout, context=context) as smtp:
                smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as smtp:
                smtp.starttls(context=context)
                smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
    except Exception:
        logger.exception("mail_send_failed: to=%s subject=%s", to, subject)
        return False
    logger.info("mail_sent: to=%s subject=%s", to, subject)
    return True


async def send_email(*, to: str, subject: str, body: str) -> bool:
    """Асинхронная обёртка.

    Отправка идёт в отдельном потоке: у API один процесс, и секунда ожидания
    почтового сервера в главном цикле останавливает работу всего склада.
    """
    return await asyncio.to_thread(send_email_sync, to=to, subject=subject, body=body)
