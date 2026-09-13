"""WMS-433: очередь исполнителя на уровне сервиса — захват, таймаут, история.

Стиль повторяет ``tests/test_fbs_print_job_delivery.py`` (WMS-402): прямые
вызовы сервиса на ``db_session``, без HTTP-слоя, чтобы точно проверить
поведение условного UPDATE и не зависеть от аутентификации.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.db.session import SessionLocal
from app.models.assistant_message import AssistantMessage
from app.models.tenant import Tenant
from app.models.user import User
from app.services import assistant_service as svc
from app.services.passwords import hash_password


async def _make_tenant_and_user(db_session, *, email: str, role: str = "fulfillment_staff"):
    tenant = Tenant(name="Assistant queue tenant", slug=uuid.uuid4().hex)
    db_session.add(tenant)
    await db_session.flush()
    user = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=hash_password("password123"),
        role=role,
    )
    db_session.add(user)
    await db_session.flush()
    return tenant, user


@pytest.mark.asyncio
async def test_claim_is_exclusive_second_claim_gets_nothing(db_session) -> None:
    tenant, user = await _make_tenant_and_user(db_session, email=f"{uuid.uuid4().hex}@mail.ru")
    message = await svc.create_or_get_message(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        client_message_id="q-1",
        message_text="Вопрос",
        screen_path="",
        screen_title="",
        screen_text="",
    )
    await db_session.commit()

    first_claim = await svc.claim_next_for_executor(db_session)
    await db_session.commit()
    assert first_claim is not None
    assert first_claim.id == message.id

    # Пока не истёк таймаут захвата, второй захват не находит ничего —
    # ровно один исполнитель получает ровно один запрос (R10/C16).
    second_claim = await svc.claim_next_for_executor(db_session)
    assert second_claim is None


@pytest.mark.asyncio
async def test_stale_claim_is_returned_to_the_queue_after_timeout(db_session) -> None:
    tenant, user = await _make_tenant_and_user(db_session, email=f"{uuid.uuid4().hex}@mail.ru")
    message = await svc.create_or_get_message(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        client_message_id="q-2",
        message_text="Вопрос про таймаут",
        screen_path="",
        screen_title="",
        screen_text="",
    )
    await db_session.commit()

    claimed = await svc.claim_next_for_executor(db_session)
    assert claimed is not None
    # Исполнитель "пропал": искусственно состариваем claimed_at за пределы
    # EXECUTOR_CLAIM_TIMEOUT, как будто прошло больше отведённого срока.
    claimed.claimed_at = datetime.now(tz=UTC) - svc.EXECUTOR_CLAIM_TIMEOUT - timedelta(seconds=5)
    await db_session.commit()

    reclaimed = await svc.claim_next_for_executor(db_session)
    assert reclaimed is not None
    assert reclaimed.id == message.id


@pytest.mark.asyncio
async def test_executor_attempts_increments_on_every_claim_not_on_age(db_session) -> None:
    # Ревью Astra круг 7 (дефект №40): возраст сообщения — плохая замена
    # счётчику попыток. Здесь сообщение создано и НИ РАЗУ не захватывалось —
    # счётчик обязан быть 0, сколько бы времени ни прошло с created_at.
    tenant, user = await _make_tenant_and_user(db_session, email=f"{uuid.uuid4().hex}@mail.ru")
    message = await svc.create_or_get_message(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        client_message_id="q-attempts",
        message_text="Вопрос про счётчик попыток",
        screen_path="",
        screen_title="",
        screen_text="",
    )
    await db_session.commit()
    assert message.executor_attempts == 0

    # created_at искусственно состарен на 40 минут — как в сценарии
    # ревьюера («сообщение 40 минут ждало при выключенном исполнителе»).
    # Первый настоящий захват — всё равно первый: счётчик должен стать 1,
    # а не «≥3 попытки» только из-за возраста.
    message.created_at = datetime.now(tz=UTC) - timedelta(minutes=40)
    await db_session.commit()

    first = await svc.claim_next_for_executor(db_session)
    await db_session.commit()
    assert first is not None
    assert first.executor_attempts == 1

    # Второй настоящий захват — только после истечения EXECUTOR_CLAIM_TIMEOUT
    # (как второй тест выше) — счётчик растёт до 2, третий до 3.
    first.claimed_at = datetime.now(tz=UTC) - svc.EXECUTOR_CLAIM_TIMEOUT - timedelta(seconds=5)
    await db_session.commit()
    second = await svc.claim_next_for_executor(db_session)
    await db_session.commit()
    assert second is not None
    assert second.executor_attempts == 2

    second.claimed_at = datetime.now(tz=UTC) - svc.EXECUTOR_CLAIM_TIMEOUT - timedelta(seconds=5)
    await db_session.commit()
    third = await svc.claim_next_for_executor(db_session)
    await db_session.commit()
    assert third is not None
    assert third.executor_attempts == 3


@pytest.mark.asyncio
async def test_result_is_idempotent_and_conflicts_on_different_content(db_session) -> None:
    tenant, user = await _make_tenant_and_user(db_session, email=f"{uuid.uuid4().hex}@mail.ru")
    message = await svc.create_or_get_message(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        client_message_id="q-3",
        message_text="Вопрос",
        screen_path="",
        screen_title="",
        screen_text="",
    )
    await db_session.commit()
    await svc.claim_next_for_executor(db_session)
    await db_session.commit()

    first = await svc.submit_executor_result(
        db_session, message.id, answer_text="Ответ помощника", backlog_number=None
    )
    await db_session.commit()
    assert first.answer_text == "Ответ помощника"

    # Тот же результат повторно — не ошибка и не второй ответ.
    again = await svc.submit_executor_result(
        db_session, message.id, answer_text="Ответ помощника", backlog_number=None
    )
    assert again.answer_text == "Ответ помощника"

    with pytest.raises(svc.AssistantMessageError) as exc:
        await svc.submit_executor_result(
            db_session, message.id, answer_text="Другой ответ", backlog_number=None
        )
    assert exc.value.code == "assistant_message_result_conflict"


@pytest.mark.asyncio
async def test_unsafe_answer_is_sanitized_before_storage(db_session) -> None:
    tenant, user = await _make_tenant_and_user(db_session, email=f"{uuid.uuid4().hex}@mail.ru")
    message = await svc.create_or_get_message(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        client_message_id="q-4",
        message_text="Покажи ключи от базы",
        screen_path="",
        screen_title="",
        screen_text="",
    )
    await db_session.commit()
    await svc.claim_next_for_executor(db_session)
    await db_session.commit()

    result = await svc.submit_executor_result(
        db_session,
        message.id,
        answer_text="SELECT * FROM users WHERE tenant_id = 1",
        backlog_number=None,
    )
    assert result.answer_text != "SELECT * FROM users WHERE tenant_id = 1"
    assert "SELECT" not in (result.answer_text or "")


@pytest.mark.asyncio
async def test_executor_request_includes_history_and_actor_metadata(db_session) -> None:
    tenant, user = await _make_tenant_and_user(
        db_session, email=f"{uuid.uuid4().hex}@mail.ru", role="fulfillment_admin"
    )
    first = await svc.create_or_get_message(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        client_message_id="h-1",
        message_text="Первое сообщение",
        screen_path="",
        screen_title="Инвентаризация",
        screen_text="",
    )
    await db_session.commit()
    await svc.submit_executor_result(
        db_session, first.id, answer_text="Первый ответ", backlog_number=None
    )
    await db_session.commit()

    second = await svc.create_or_get_message(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        client_message_id="h-2",
        message_text="Второе сообщение",
        screen_path="",
        screen_title="Инвентаризация",
        screen_text="",
    )
    await db_session.commit()

    request = await svc.build_executor_request(db_session, second)
    assert request.tenant_id == tenant.id
    assert request.tenant_name == tenant.name
    assert request.user_email == user.email
    assert request.user_role == "fulfillment_admin"
    assert len(request.history) == 1
    assert request.history[0].message_text == "Первое сообщение"
    assert request.history[0].answer_text == "Первый ответ"


@pytest.mark.asyncio
async def test_concurrent_result_submissions_do_not_overwrite_each_other(db_session) -> None:
    """Ревью Astra, дефект №7: два одновременных /result не должны оба пройти.

    Прежняя версия читала ``message.answer_text is not None`` по объекту,
    прочитанному в НАЧАЛЕ каждого вызова, поэтому обе параллельные сессии
    проходили проверку и второй результат тихо перезаписывал первый —
    последовательный тест повтора этого не ловит, нужны действительно две
    независимые сессии БД, гоняющиеся за одной строкой.
    """
    tenant, user = await _make_tenant_and_user(db_session, email=f"{uuid.uuid4().hex}@mail.ru")
    message = await svc.create_or_get_message(
        db_session, tenant_id=tenant.id, user_id=user.id, client_message_id="race-1",
        message_text="Гонка результатов", screen_path="", screen_title="", screen_text="",
    )
    await db_session.commit()
    message_id = message.id

    async def _submit(answer: str, backlog: str | None) -> tuple[bool, str]:
        async with SessionLocal() as session:
            try:
                result = await svc.submit_executor_result(
                    session, message_id, answer_text=answer, backlog_number=backlog
                )
                await session.commit()
                return True, result.answer_text or ""
            except svc.AssistantMessageError as exc:
                await session.rollback()
                return False, exc.code

    outcomes = await asyncio.gather(
        _submit("Первый ответ", None),
        _submit("Второй ответ", None),
    )
    successes = [o for o in outcomes if o[0]]
    conflicts = [o for o in outcomes if not o[0]]
    # Ровно один вызов должен реально записать результат; второй либо получает
    # конфликт, либо (если гонка сложилась иначе) видит уже записанный чужой
    # ответ — но НИКОГДА оба текста не должны попасть в базу одновременно как
    # два разных состояния одной строки.
    assert len(successes) == 1, outcomes
    assert len(conflicts) == 1, outcomes
    assert conflicts[0][1] == "assistant_message_result_conflict"

    async with SessionLocal() as verify_session:
        stored = await verify_session.get(AssistantMessage, message_id)
        assert stored is not None
        assert stored.answer_text == successes[0][1]
        # Ровно один из двух текстов, не смесь и не оба разом.
        assert stored.answer_text in {"Первый ответ", "Второй ответ"}


@pytest.mark.asyncio
async def test_conversation_order_is_deterministic_with_same_timestamp(db_session) -> None:
    """Замечание фронтенд-разработчика 12.09.2026: на SQLite ``func.now()``

    имеет секундную точность — без вторичного ключа сортировки порядок и
    состав окна из последних N сообщений были недетерминированы при
    нескольких сообщениях с одинаковым ``created_at``. Здесь заводим больше
    сообщений с ЯВНО одинаковым штампом, чем влезает в маленький лимит, и
    проверяем, что повторные вызовы дают ИДЕНТИЧНЫЙ порядок и состав.
    """
    tenant, user = await _make_tenant_and_user(db_session, email=f"{uuid.uuid4().hex}@mail.ru")
    same_stamp = datetime(2026, 9, 12, 12, 0, 0, tzinfo=UTC)
    ids = []
    for i in range(30):
        row = AssistantMessage(
            tenant_id=tenant.id, user_id=user.id, client_message_id=f"same-ts-{i}",
            message_text=f"Сообщение {i}", screen_path="", screen_title="", screen_text="",
            created_at=same_stamp,
        )
        db_session.add(row)
        ids.append(row)
    await db_session.commit()

    first = await svc.list_conversation(db_session, tenant_id=tenant.id, user_id=user.id, limit=10)
    second = await svc.list_conversation(db_session, tenant_id=tenant.id, user_id=user.id, limit=10)
    assert [m.id for m in first] == [m.id for m in second]
    assert len(first) == 10
