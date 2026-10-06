"""WMS-433: минимальное хранилище переписки с AI-помощником.

Одна строка — один ход пользователя и (когда готов) ответ на него. Отдельной
таблицы очереди нет и не нужна: очередь для исполнителя — это тот же набор
строк, отфильтрованный по `answered_at IS NULL`, а «выдано агенту» — это
`claimed_at`, которое сервис сбрасывает по таймауту (см.
``app/services/assistant_service.py``). Явного поля статуса нет по решению
аналитика (документ требований WMS-433, 4.1): «состояние запроса — одно поле,
вычисляемое из наличия ответа и захвата исполнителем» — здесь это
``answered_at`` и ``claimed_at``, второй сущности не заводим.

``BackgroundJob`` сюда не переиспользован сознательно: у него нет автора
сообщения (только тенант), а общий ``GET /operations/background-jobs/{id}``
отдаёт ``payload_json``/``result_json`` любому пользователю тенанта без
проверки авторства (см. ``app/api/background_jobs.get_background_job``) — это
прямо нарушает R5 (переписка видна только автору). Заводить отдельное
исключение в общей ручке ради этого типа сложнее и рискованнее, чем одна
маленькая выделенная таблица с собственными эндпоинтами (``app/api/assistant.py``),
которые с самого начала фильтруют по ``user_id``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# R6/C20: сообщение пользователя и видимый текст экрана обрезаются до этих
# пределов на сервере, а не только на клиенте — иначе пользовательская правка
# фронта могла бы обойти ограничение. Числа выбраны с запасом над проверкой
# C20 (сообщение 5000 символов, экран с несколькими сотнями строк таблицы).
MESSAGE_TEXT_MAX_CHARS = 8_000
SCREEN_TEXT_MAX_CHARS = 20_000
SCREEN_TITLE_MAX_CHARS = 256
SCREEN_PATH_MAX_CHARS = 512
CLIENT_MESSAGE_ID_MAX_CHARS = 128
BACKLOG_NUMBER_MAX_CHARS = 16


class AssistantMessage(Base):
    """Один ход переписки: сообщение пользователя + контекст экрана + ответ."""

    __tablename__ = "assistant_messages"
    __table_args__ = (
        # R21: тот же клиентский идентификатор от того же пользователя не
        # создаёт вторую строку — обработка идемпотентна на уровне БД, а не
        # только на уровне сервиса (защищает и от гонки двух одновременных
        # повторов отправки).
        UniqueConstraint(
            "user_id", "client_message_id", name="uq_assistant_messages_user_client_message_id"
        ),
        Index("ix_assistant_messages_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    client_message_id: Mapped[str] = mapped_column(
        String(CLIENT_MESSAGE_ID_MAX_CHARS), nullable=False
    )
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    screen_path: Mapped[str] = mapped_column(
        String(SCREEN_PATH_MAX_CHARS), nullable=False, default=""
    )
    screen_title: Mapped[str] = mapped_column(
        String(SCREEN_TITLE_MAX_CHARS), nullable=False, default=""
    )
    screen_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Захват исполнителем очереди. NULL — ожидает; заполнено и не устарело —
    # выдано агенту; устарело (см. EXECUTOR_CLAIM_TIMEOUT в сервисе) — снова
    # доступно для захвата, даже если answered_at всё ещё пусто (R10).
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Ревью Astra круг 7 (дефект №40): возраст сообщения — плохая замена
    # счётчику попыток (сообщение, 40 минут ждавшее ВЫКЛЮЧЕННОГО исполнителя,
    # выглядело «старым» уже на первой реальной попытке). Настоящий счётчик:
    # растёт на КАЖДЫЙ захват (тем же условным UPDATE, что и claimed_at —
    # см. claim_next_for_executor), независимо от того, чем закончилась
    # обработка. Это не второй источник состояния «ожидает ли сообщение
    # ответа» (им по-прежнему остаётся только ``answer_text IS NULL``, решение
    # аналитика 4.1) — это техническая защита от бесконечного повтора одного
    # и того же провала (R10/R22): исполнитель использует значение, чтобы
    # после нескольких подряд неудачных вызовов модели перестать молча
    # повторять попытку и отправить честный запасной ответ.
    executor_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Ответ, УЖЕ прошедший техническую проверку (R17): исходный текст
    # исполнителя сюда не попадает, если проверка его отклонила — см.
    # app/services/assistant_safety.py. Поэтому отдельного «сырого» поля для
    # ответа исполнителя в таблице нет и не должно быть.
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    backlog_number: Mapped[str | None] = mapped_column(
        String(BACKLOG_NUMBER_MAX_CHARS), nullable=True
    )
