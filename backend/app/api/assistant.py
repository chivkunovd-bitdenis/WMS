"""WMS-433: чат с AI-помощником — пользовательские ручки и очередь исполнителя.

Пользовательские ручки (``/assistant/messages``) требуют обычный JWT портала
ФФ (``require_ff_portal_member`` — тот же уровень доступа, что и у «Базы
знаний»: любой сотрудник тенанта, без отдельной настройки прав, R20). Ручки
исполнителя (``/assistant/executor/*``) требуют серверный секрет
(``require_assistant_executor``) и не принимают пользовательский JWT — они не
привязаны к тенанту, потому что один исполнитель обслуживает все тенанты.

Контракт для фронта: ``POST /assistant/messages`` отправляет сообщение
(идемпотентно по ``client_message_id``), ``GET /assistant/messages`` отдаёт
всю переписку пользователя. Готовность ответа — поле ``waiting`` (``true``,
пока ``answer_text`` пуст); фронт узнаёт о готовности периодическим опросом
``GET /assistant/messages`` (в проекте нет вебсокетов/SSE — тот же подход,
что уже согласован для чата WMS-397: «сервер хранит сообщения, клиент
опрашивает»).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_assistant_executor, require_ff_portal_member
from app.db.session import get_db
from app.models.assistant_message import (
    CLIENT_MESSAGE_ID_MAX_CHARS,
    MESSAGE_TEXT_MAX_CHARS,
    SCREEN_PATH_MAX_CHARS,
    SCREEN_TITLE_MAX_CHARS,
)
from app.models.user import User
from app.services import assistant_service as svc

router = APIRouter(prefix="/assistant", tags=["assistant"])

_NOT_FOUND_CODES = frozenset({"assistant_message_not_found"})
_CONFLICT_CODES = frozenset(
    {"assistant_message_conflict", "assistant_message_result_conflict"}
)


def _raise_assistant_http(exc: svc.AssistantMessageError) -> None:
    detail = {"code": exc.code, "message": exc.message}
    if exc.code in _NOT_FOUND_CODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if exc.code in _CONFLICT_CODES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


class AssistantMessageCreateBody(BaseModel):
    # Клиент генерирует один раз на нажатие «Отправить» (например uuid4).
    # Повтор с тем же значением после потери ответа не создаёт вторую строку
    # в ленте (R21).
    client_message_id: str = Field(min_length=1, max_length=CLIENT_MESSAGE_ID_MAX_CHARS)
    message_text: str = Field(min_length=1, max_length=MESSAGE_TEXT_MAX_CHARS)
    # R6: «слишком большой текст экрана обрезается … сообщение всё равно
    # отправляется» — отправку по длине текста экрана отклонять нельзя.
    # Обрезка до SCREEN_TEXT_MAX_CHARS происходит в сервисе (create_or_get_message);
    # предел здесь — не бизнес-правило, а защита от откровенно избыточного
    # тела запроса (на порядок больше типичного дампа текста страницы).
    screen_path: str = Field(default="", max_length=SCREEN_PATH_MAX_CHARS)
    screen_title: str = Field(default="", max_length=SCREEN_TITLE_MAX_CHARS)
    screen_text: str = Field(default="", max_length=500_000)


class AssistantMessageOut(BaseModel):
    id: str
    message_text: str
    screen_title: str
    created_at: str
    answer_text: str | None
    answered_at: str | None
    backlog_number: str | None
    waiting: bool


class AssistantConversationOut(BaseModel):
    messages: list[AssistantMessageOut]


@router.post("/messages", response_model=AssistantMessageOut, status_code=status.HTTP_201_CREATED)
async def send_assistant_message(
    body: AssistantMessageCreateBody,
    user: Annotated[User, Depends(require_ff_portal_member)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AssistantMessageOut:
    try:
        message = await svc.create_or_get_message(
            session,
            tenant_id=user.tenant_id,
            user_id=user.id,
            client_message_id=body.client_message_id,
            message_text=body.message_text,
            screen_path=body.screen_path,
            screen_title=body.screen_title,
            screen_text=body.screen_text,
        )
    except svc.AssistantMessageError as exc:
        _raise_assistant_http(exc)
    await session.commit()
    return AssistantMessageOut(**svc.message_out(message))


@router.get("/messages", response_model=AssistantConversationOut)
async def get_assistant_conversation(
    user: Annotated[User, Depends(require_ff_portal_member)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AssistantConversationOut:
    rows = await svc.list_conversation(session, tenant_id=user.tenant_id, user_id=user.id)
    return AssistantConversationOut(
        messages=[AssistantMessageOut(**svc.message_out(r)) for r in rows]
    )


# --- Очередь исполнителя -----------------------------------------------------


class AssistantExecutorHistoryItemOut(BaseModel):
    message_text: str
    screen_title: str
    answer_text: str | None
    created_at: str
    # Номер карточки этого хода, если она есть. Решение аналитика 4.3
    # (уточнено 12.09.2026): дедуп определяет исполнитель — модель сравнивает
    # новое сообщение с коротким списком карточек этого же тенанта из чата
    # (см. /executor/next) и с номерами из этой истории, а не по факту
    # «в истории уже есть какой-то номер» (это было первой, технически
    # дефектной версией дедупа — см. docs/reviews/2026-09-12-wms433/).
    backlog_number: str | None


class AssistantExecutorRequestOut(BaseModel):
    id: str
    # Ревью Astra круг 2 (дефект №15): фильтр кандидатов дедупа по одному
    # tenant_name смешивал две организации с одинаковым названием —
    # исполнитель сравнивает по tenant_id, tenant_name остаётся только для
    # текста карточки, которую видит владелец.
    tenant_id: str
    tenant_name: str
    user_email: str
    user_role: str
    message_text: str
    screen_path: str
    screen_title: str
    screen_text: str
    created_at: str
    history: list[AssistantExecutorHistoryItemOut]
    # None — бэк не знает версию сборки (R9): исполнитель берёт вершину
    # etalon и фиксирует это сам в своём служебном результате.
    code_version: str | None
    # Дефект №40: настоящий счётчик захватов этого сообщения (растёт в
    # claim_next_for_executor на каждый, включая этот). Заменяет собой
    # возраст сообщения как признак «сколько раз уже пробовали» — возраст
    # ошибочно считал попыткой время простоя выключенного исполнителя.
    executor_attempts: int


class AssistantExecutorNextOut(BaseModel):
    request: AssistantExecutorRequestOut | None


def _executor_request_out(req: svc.ExecutorRequest) -> AssistantExecutorRequestOut:
    return AssistantExecutorRequestOut(
        id=str(req.message.id),
        tenant_id=str(req.tenant_id),
        tenant_name=req.tenant_name,
        user_email=req.user_email,
        user_role=req.user_role,
        message_text=req.message.message_text,
        screen_path=req.message.screen_path,
        screen_title=req.message.screen_title,
        screen_text=req.message.screen_text,
        created_at=req.message.created_at.isoformat(),
        history=[
            AssistantExecutorHistoryItemOut(
                message_text=h.message_text,
                screen_title=h.screen_title,
                answer_text=h.answer_text,
                created_at=h.created_at.isoformat(),
                backlog_number=h.backlog_number,
            )
            for h in req.history
        ],
        code_version=req.code_version,
        executor_attempts=req.message.executor_attempts,
    )


@router.post(
    "/executor/next",
    response_model=AssistantExecutorNextOut,
    dependencies=[Depends(require_assistant_executor)],
)
async def claim_next_assistant_request(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AssistantExecutorNextOut:
    message = await svc.claim_next_for_executor(session)
    await session.commit()
    if message is None:
        return AssistantExecutorNextOut(request=None)
    executor_request = await svc.build_executor_request(session, message)
    return AssistantExecutorNextOut(request=_executor_request_out(executor_request))


class AssistantExecutorResultBody(BaseModel):
    answer_text: str = Field(min_length=1, max_length=MESSAGE_TEXT_MAX_CHARS)
    # WMS-NNN, если разбор признан багом/пользовательской историей и карточка
    # уже записана исполнителем (R15). Само создание карточки в бэклог здесь
    # не происходит — это делает скрипт исполнителя git-коммитом в свою ветку,
    # WMS только сохраняет присланный номер, чтобы показать его в ленте.
    backlog_number: str | None = Field(default=None, max_length=16)


class AssistantExecutorResultOut(BaseModel):
    id: str
    answer_text: str
    backlog_number: str | None


@router.post(
    "/executor/{message_id}/result",
    response_model=AssistantExecutorResultOut,
    dependencies=[Depends(require_assistant_executor)],
)
async def submit_assistant_executor_result(
    message_id: uuid.UUID,
    body: AssistantExecutorResultBody,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AssistantExecutorResultOut:
    try:
        message = await svc.submit_executor_result(
            session,
            message_id,
            answer_text=body.answer_text,
            backlog_number=body.backlog_number,
        )
    except svc.AssistantMessageError as exc:
        _raise_assistant_http(exc)
    await session.commit()
    return AssistantExecutorResultOut(
        id=str(message.id),
        answer_text=message.answer_text or "",
        backlog_number=message.backlog_number,
    )
