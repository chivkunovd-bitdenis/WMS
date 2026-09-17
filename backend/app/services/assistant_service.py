"""WMS-433: переписка с AI-помощником и очередь для локального исполнителя.

Устройство очереди намеренно повторяет ``fbs_print_job_service`` (WMS-402):
атомарный захват условным ``UPDATE ... WHERE`` и идемпотентный приём
результата. Отличие — исполнитель здесь один на все тенанты (см.
``app/api/deps.require_assistant_executor``: доступ по общему секрету, а не по
пользовательскому JWT), поэтому захват не фильтруется по тенанту, а таймаут
захвата возвращает запрос в очередь: печать WMS-402 таймаута не делает
(потерянная квитанция там требует ручного решения человека), а здесь по R10
это обязательное требование — пользователь не должен зависнуть только потому,
что агент забрал запрос и не ответил вовремя.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.models.assistant_message import (
    MESSAGE_TEXT_MAX_CHARS,
    SCREEN_PATH_MAX_CHARS,
    SCREEN_TEXT_MAX_CHARS,
    SCREEN_TITLE_MAX_CHARS,
    AssistantMessage,
)
from app.models.tenant import Tenant
from app.models.user import User
from app.services.assistant_safety import sanitize_answer

# R10: «в установленный срок» — конкретное число выбирает разработчик.
#
# Приёмка 13.09.2026, дефект 2 (R7, R22; C19): прежние 3 минуты были МЕНЬШЕ
# собственного бюджета CLI (``DEFAULT_MODEL_TIMEOUT_SEC`` в
# tools/assistant-agent/wms_assistant_agent.py, было 300 с) — захват истекал
# и запрос уходил на повторный захват ДО того, как claude -p успевал честно
# провалиться сам. На «тяжёлом» вопросе это давало бессрочный повтор одного
# и того же таймаута: три запуска из ~22 реальных прогонов исполнителя
# упёрлись в «claude -p не ответил за 300 с», пользователь бессрочно видел
# «Готовлю ответ» (реальный прогон, docs/requirements/WMS-433.md, раздел 8).
#
# Ревью Astra круг 7 (дефект №41): первое исправление — 12 минут — тоже не
# покрывало полный цикл. Подменой длительностей реальных git-команд ревью
# получило 837 с (два fetch по 119 с + модель 599 с) ещё ДО записи карточки,
# то есть больше 12 минут. Формула здесь — явная, по составу худшего случая
# ОДНОГО цикла (все числа — таймауты реальных подпроцессов в этом же файле):
#   600 с модель (DEFAULT_MODEL_TIMEOUT_SEC)
# + 120 с x2 — fetch кода и fetch бэклога (по одному на каждый checkout)
# +  60 с — push карточки в origin
# +  60 с — checkout (детач на ref/ветку)
# ------------------------------------------------------------------
# = 960 с, плюс запас на мелкие команды (ls-tree/show/add/commit — по 15-30 с
# каждая, но их сумма даже при полном провале каждой не главная часть
# бюджета) и на поиск номера карточки (после дефекта №41(a) сведён к
# нескольким пакетным git-вызовам, доли секунды на реальном репозитории с
# 822 ветками — измерено, не предположение) — округляем 960 с вверх до 20
# минут (1200 с), а не до 16, чтобы оставить настоящий запас, а не считать
# впритык. Держать ``DEFAULT_MODEL_TIMEOUT_SEC`` МЕНЬШЕ этого значения с
# запасом — обязательное условие, а не совпадение: иначе захват снова
# истекает раньше отказа CLI. Дополнительная, независимая защита от того же
# класса дефекта — общий дедлайн цикла внутри исполнителя (см. докстринг
# ``_cycle_deadline`` в tools/assistant-agent/wms_assistant_agent.py):
# даже если это число когда-нибудь снова окажется мало, исполнитель сам
# остановится, не дожидаясь истечения захвата, и просто не отправит
# результат — запрос корректно вернётся в очередь.
EXECUTOR_CLAIM_TIMEOUT = timedelta(minutes=20)
# Столько ожидающих/просроченных строк сервис просматривает за один вызов
# /next — как _CLAIM_SCAN_LIMIT в fbs_print_job_service, чисто чтобы не
# вычитывать неограниченную очередь разом.
_CLAIM_SCAN_LIMIT = 100
# R11: «последние сообщения» — сколько прошлых ходов этого пользователя
# получает исполнитель вместе с новым сообщением, чтобы не терять контекст
# уточняющих вопросов.
EXECUTOR_HISTORY_LIMIT = 10


def tenant_assistant_enabled(tenant_slug: str | None) -> bool:
    """WMS-433/R23: включён ли AI-помощник тенанту с этим slug.

    Источник истины — один: список ``settings.assistant_enabled_tenant_slugs``
    (переменная окружения ``WMS_ASSISTANT_ENABLED_TENANTS``). Используется и
    здесь (гейт пользовательских ручек ``/assistant/messages`` в ``deps.py``),
    и в ``/auth/me`` (поле ``assistant_enabled``) — второго источника истины
    на фронте нет, признак повторяет уже существующий образец тенантских
    флагов (``address_storage_enabled`` и т.п.).
    """
    enabled_slugs = settings.assistant_enabled_tenant_slugs
    if enabled_slugs is None:
        return True
    if not tenant_slug:
        return False
    return tenant_slug.strip().lower() in enabled_slugs


class AssistantMessageError(RuntimeError):
    def __init__(self, code: str, *, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _truncate(value: str | None, limit: int) -> str:
    text = (value or "").strip()
    return text[:limit]


def _single_line(value: str | None, limit: int) -> str:
    """Схлопнуть переносы строк в пробелы и обрезать до предела.

    Для ``screen_title`` — R6 прямо требует «одной строкой» («Экран:
    Инвентаризация ИНВ-000124»), а не только это подразумевает. Ревью Astra
    круг 3 (дефект №28) показало и техническую причину: сервер сохранял
    переносы как есть, и многострочный screen_title, вставленный в карточку
    бэклога, мог подделать начало нового Markdown-заголовка `## WMS-...`.
    Нормализация здесь — это ремонт также и для фронта (он не единственный
    отправитель тела запроса), а НЕ единственная защита: экранирование самой
    карточки в tools/assistant-agent — вторая, независимая линия.
    """
    return " ".join((value or "").split())[:limit]


async def create_or_get_message(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    client_message_id: str,
    message_text: str,
    screen_path: str,
    screen_title: str,
    screen_text: str,
) -> AssistantMessage:
    """Отправить сообщение; повтор с тем же ``client_message_id`` — не дубль (R21).

    Сообщение и контекст экрана обрезаются до серверных пределов здесь же
    (R6/C20): предел действует независимо от того, что прислал браузер.
    """
    client_message_id = client_message_id.strip()
    if not client_message_id:
        raise AssistantMessageError(
            "client_message_id_required", message="Не передан идентификатор сообщения."
        )
    message_text = _truncate(message_text, MESSAGE_TEXT_MAX_CHARS)
    if not message_text:
        raise AssistantMessageError("message_text_required", message="Сообщение пустое.")

    existing = await session.scalar(
        select(AssistantMessage).where(
            AssistantMessage.user_id == user_id,
            AssistantMessage.client_message_id == client_message_id,
        )
    )
    if existing is not None:
        return _existing_or_conflict(existing, tenant_id=tenant_id, message_text=message_text)

    row = AssistantMessage(
        tenant_id=tenant_id,
        user_id=user_id,
        client_message_id=client_message_id,
        message_text=message_text,
        screen_path=_truncate(screen_path, SCREEN_PATH_MAX_CHARS),
        screen_title=_single_line(screen_title, SCREEN_TITLE_MAX_CHARS),
        screen_text=_truncate(screen_text, SCREEN_TEXT_MAX_CHARS),
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raced = await session.scalar(
            select(AssistantMessage).where(
                AssistantMessage.user_id == user_id,
                AssistantMessage.client_message_id == client_message_id,
            )
        )
        if raced is None:
            raise
        return _existing_or_conflict(raced, tenant_id=tenant_id, message_text=message_text)
    return row


def _existing_or_conflict(
    row: AssistantMessage, *, tenant_id: uuid.UUID, message_text: str
) -> AssistantMessage:
    if row.tenant_id != tenant_id or row.message_text != message_text:
        raise AssistantMessageError(
            "assistant_message_conflict",
            message="Этот идентификатор сообщения уже занят другим текстом.",
        )
    return row


async def list_conversation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    limit: int = 500,
) -> list[AssistantMessage]:
    """Своя переписка целиком (R5), от старых к новым, с потолком на выдачу.

    Замечание фронтенд-разработчика 12.09.2026: на SQLite ``func.now()``
    имеет секундную точность, и при нескольких сообщениях в одну секунду
    сортировка только по ``created_at`` не детерминирована — какие именно
    500 строк попадут в выдачу и в каком порядке, могло меняться от запроса к
    запросу (воспроизведено на 242 сообщениях с одним и тем же штампом:
    первым в выдаче оказывалось то 78-е, то произвольное другое). ``id`` как
    вторичный ключ не восстанавливает истинный хронологический порядок серии
    с одинаковым ``created_at`` (UUID не привязан ко времени), зато делает
    ОДИН И ТОТ ЖЕ запрос стабильным между вызовами — то, что здесь нужно.
    """
    rows = await session.scalars(
        select(AssistantMessage)
        .where(AssistantMessage.tenant_id == tenant_id, AssistantMessage.user_id == user_id)
        .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id.desc())
        .limit(limit)
    )
    return list(reversed(rows.all()))


async def claim_next_for_executor(session: AsyncSession) -> AssistantMessage | None:
    """Выдать исполнителю один запрос: новый или просроченный по таймауту (R10).

    Исполнитель обслуживает все тенанты одним секретом, поэтому фильтра по
    tenant_id здесь нет — это единственное отличие от ``claim_next_print_job``.
    Условный UPDATE по ``claimed_at`` не даёт двум одновременным агентам
    забрать одну и ту же строку: второй UPDATE не найдёт её в нужном
    состоянии и получит ноль изменённых строк.
    """
    now = datetime.now(tz=UTC)
    stale_before = now - EXECUTOR_CLAIM_TIMEOUT
    candidates = (
        await session.scalars(
            select(AssistantMessage)
            .where(
                AssistantMessage.answer_text.is_(None),
                (AssistantMessage.claimed_at.is_(None))
                | (AssistantMessage.claimed_at < stale_before),
            )
            # id — вторичный ключ по той же причине, что и в list_conversation
            # выше: у SQLite секундная точность created_at, без тай-брейкера
            # порядок сканирования очереди не детерминирован.
            .order_by(AssistantMessage.created_at, AssistantMessage.id)
            .limit(_CLAIM_SCAN_LIMIT)
        )
    ).all()
    for candidate in candidates:
        # Условие повторяет то, что мы только что прочитали (NULL или
        # устаревший claimed_at) — если между чтением и записью другой агент
        # успел захватить строку, само условие этого не пропустит.
        stmt = (
            update(AssistantMessage)
            .where(
                AssistantMessage.id == candidate.id,
                AssistantMessage.answer_text.is_(None),
                (AssistantMessage.claimed_at.is_(None))
                | (AssistantMessage.claimed_at < stale_before),
            )
            # Дефект №40: счётчик попыток растёт в ТОЙ ЖЕ условной записи, что
            # и сам захват — атомарно и без отдельного второго запроса,
            # ровно на каждый настоящий захват (включая повторные после
            # истёкшего таймаута), а не на что-то ещё.
            .values(claimed_at=now, executor_attempts=AssistantMessage.executor_attempts + 1)
            .execution_options(synchronize_session=False)
        )
        result = await session.execute(stmt)
        if getattr(result, "rowcount", 0) != 1:
            continue
        await session.refresh(candidate)
        return candidate
    return None


async def _history_for(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    exclude_id: uuid.UUID,
    before: datetime,
    limit: int,
) -> list[AssistantMessage]:
    # Почему не просто "created_at < before": на SQLite ``server_default=func.now()``
    # рендерится в голый ``CURRENT_TIMESTAMP`` (секундная точность, без дробной
    # части), а Python-datetime, который сюда приходит как ``before``, диалект
    # SQLite биндит со строкой вида ``...:35.000000`` (дробная часть всегда).
    # Строковое сравнение тогда трактует более короткую (уже сохранённую)
    # строку как «меньшую», даже если это ТА ЖЕ секунда — то есть текущее
    # сообщение проходило бы фильтр как «предыдущее самому себе». Задача
    # реальная: два сообщения в одну и ту же секунду — обычная ситуация при
    # быстрой отправке. Поэтому исключаем текущее сообщение по id явно, а не
    # только по времени, и берём ``<=``, чтобы не потерять действительно более
    # раннее сообщение с тем же округлением до секунды.
    rows = await session.scalars(
        select(AssistantMessage)
        .where(
            AssistantMessage.tenant_id == tenant_id,
            AssistantMessage.user_id == user_id,
            AssistantMessage.id != exclude_id,
            AssistantMessage.created_at <= before,
        )
        # id — тот же тай-брейкер, что и в list_conversation/claim_next_for_executor
        # выше, для той же причины (секундная точность created_at на SQLite).
        .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id.desc())
        .limit(limit)
    )
    return list(reversed(rows.all()))


@dataclass(frozen=True)
class ExecutorRequest:
    """Полезная нагрузка, которую видит локальный исполнитель по /next."""

    message: AssistantMessage
    # Ревью Astra круг 2 (дефект №15): фильтр кандидатов дедупа по одному
    # только tenant_name смешивал две разные организации с одинаковым
    # названием. tenant_id уже есть на самом сообщении (колонка модели) —
    # отдельного запроса не нужно, просто отдаём его исполнителю тоже.
    tenant_id: uuid.UUID
    tenant_name: str
    user_email: str
    user_role: str
    history: list[AssistantMessage]
    code_version: str | None


async def build_executor_request(
    session: AsyncSession, message: AssistantMessage
) -> ExecutorRequest:
    """Собрать контекст для исполнителя: кто спрашивает, история, версия кода.

    Роль и тенант исполнитель получает отсюда (из БД по сохранённым
    ``tenant_id``/``user_id``), а не из текста сообщения — это то же самое
    требование R6 «сервер берёт их из сессии, а не из того, что прислал
    браузер», применённое на шаге выдачи исполнителю.
    """
    tenant = await session.get(Tenant, message.tenant_id)
    user = await session.get(User, message.user_id)
    history = await _history_for(
        session,
        tenant_id=message.tenant_id,
        user_id=message.user_id,
        exclude_id=message.id,
        before=message.created_at,
        limit=EXECUTOR_HISTORY_LIMIT,
    )
    return ExecutorRequest(
        message=message,
        tenant_id=message.tenant_id,
        tenant_name=tenant.name if tenant is not None else "",
        user_email=user.email if user is not None else "",
        user_role=user.role if user is not None else "",
        history=history,
        code_version=(settings.assistant_deploy_version or "").strip() or None,
    )


async def get_message_for_executor(
    session: AsyncSession, message_id: uuid.UUID
) -> AssistantMessage:
    """Найти запрос, выданный исполнителю (без привязки к тенанту пользователя:

    исполнитель работает по общему секрету на все тенанты).

    Всегда перечитывает объект из БД (``session.refresh``), а не отдаёт то,
    что уже лежит в identity map сессии: единственный вызывающий —
    ``submit_executor_result`` — использует эту функцию сразу после
    условного ``UPDATE ... WHERE answer_text IS NULL`` с
    ``synchronize_session=False`` (см. его докстринг), который сознательно
    не трогает Python-объекты в памяти. Без принудительного refresh здесь
    возвращалось бы устаревшее значение ``answer_text`` того же самого
    объекта, который уже лежал в identity map (например после
    ``claim_next_for_executor``) — ровно так это и проявилось в тесте
    ``test_result_is_idempotent_and_conflicts_on_different_content``.
    """
    message = await session.get(AssistantMessage, message_id)
    if message is None:
        raise AssistantMessageError(
            "assistant_message_not_found", message="Запрос помощника не найден."
        )
    await session.refresh(message)
    return message


async def submit_executor_result(
    session: AsyncSession,
    message_id: uuid.UUID,
    *,
    answer_text: str,
    backlog_number: str | None,
) -> AssistantMessage:
    """Принять ответ исполнителя. Повтор с тем же результатом — не дубль (R10).

    Технический фильтр (R17) применяется здесь: то, что не прошло проверку, в
    ``answer_text`` не попадает — вместо него сохраняется безопасная замена.

    Ревью Astra (дефект №7, `docs/reviews/2026-09-12-wms433/astra-review-part1.md`):
    прежняя версия проверяла ``message.answer_text is not None`` по уже
    прочитанному в память объекту, а затем писала безусловным присваиванием —
    двое одновременных исполнителей (второй уже опрашивает после того, как
    таймаут вернул задание в очередь и его успел забрать кто-то ещё, либо
    просто двойной локальный запуск) оба проходили проверку и второй
    результат тихо перезаписывал первый. Условный `UPDATE ... WHERE
    answer_text IS NULL` — тот же приём, что и в `claim_next_for_executor`:
    только ОДИН конкурентный вызов реально меняет строку, что бы ни
    показывало предварительное чтение.
    """
    safe_answer = sanitize_answer(answer_text)
    backlog_number = (backlog_number or "").strip() or None
    answered_at = datetime.now(tz=UTC)

    stmt = (
        update(AssistantMessage)
        .where(AssistantMessage.id == message_id, AssistantMessage.answer_text.is_(None))
        .values(answer_text=safe_answer, answered_at=answered_at, backlog_number=backlog_number)
        .execution_options(synchronize_session=False)
    )
    result = await session.execute(stmt)
    if getattr(result, "rowcount", 0) == 1:
        return await get_message_for_executor(session, message_id)

    # Либо сообщения нет вовсе, либо ответ уже кем-то записан (нами же при
    # повторе или конкурентным исполнителем) — читаем текущее состояние и
    # различаем «тот же результат повторно» от настоящего конфликта.
    message = await get_message_for_executor(session, message_id)
    if message.answer_text == safe_answer and message.backlog_number == backlog_number:
        return message
    raise AssistantMessageError(
        "assistant_message_result_conflict",
        message="Ответ на этот запрос уже сохранён с другим содержимым.",
    )


def message_is_waiting(message: AssistantMessage) -> bool:
    """Единственное вычисляемое состояние ожидания — по решению аналитика 4.1."""
    return message.answer_text is None


def message_out(message: AssistantMessage) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "message_text": message.message_text,
        "screen_title": message.screen_title,
        "created_at": message.created_at.isoformat(),
        "answer_text": message.answer_text,
        "answered_at": message.answered_at.isoformat() if message.answered_at else None,
        "backlog_number": message.backlog_number,
        "waiting": message_is_waiting(message),
    }
