from __future__ import annotations

import secrets
import uuid
from typing import Literal

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER, FULFILLMENT_STAFF
from app.core.settings import settings
from app.models.document_event import (
    DOCUMENT_TYPE_STAFF_USER,
    EVENT_STAFF_USER_CREATED,
    SOURCE_USER,
)
from app.models.ff_staff_permissions import FfStaffPermissions
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.auth_link_tokens import (
    AuthLinkError,
    build_link,
    create_auth_link_token,
    decode_auth_link_token,
    fingerprint_matches,
)
from app.services.billing_tariff_matrix_service import ensure_disabled_tariff_matrix
from app.services.document_event_service import (
    record_document_event_safely,
)
from app.services.mailer import send_email
from app.services.passwords import hash_password, verify_password
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.tokens import create_access_token

DEFAULT_WAREHOUSE_NAME = "Основной"
DEFAULT_WAREHOUSE_CODE = "main"


class AuthError(Exception):
    pass


async def register_fulfillment(
    session: AsyncSession,
    *,
    organization_name: str,
    slug: str,
    admin_email: str,
    password: str,
) -> tuple[User, Tenant]:
    tenant = Tenant(name=organization_name, slug=slug.strip().lower())
    user = User(
        tenant=tenant,
        email=admin_email.strip().lower(),
        password_hash=hash_password(password),
        must_set_password=False,
        role=FULFILLMENT_ADMIN,
        seller_id=None,
    )
    session.add(tenant)
    session.add(user)
    try:
        await session.flush()
        await ensure_disabled_tariff_matrix(session, tenant=tenant)
        # WMS-062: у новой организации всегда есть один «Основной» склад.
        # Форма приёмки/отгрузки в UI и мобильный ТСД падали на пустом списке
        # складов, поэтому склад создаётся в той же транзакции, что и tenant.
        warehouse = Warehouse(
            tenant_id=tenant.id,
            name=DEFAULT_WAREHOUSE_NAME,
            code=DEFAULT_WAREHOUSE_CODE,
        )
        session.add(warehouse)
        await session.flush()
        await get_or_create_sorting_location(session, tenant.id, warehouse.id)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AuthError("slug_or_email_taken") from exc
    await session.refresh(user)
    await session.refresh(tenant)
    return user, tenant


# WMS-270. Постоянный «пустой» хеш для веток, где реального пользователя нет
# или пароль ещё не задан. Мы всё равно прогоняем bcrypt: если пропустить его,
# по времени ответа снаружи легко отличить «такой почты нет» от «пароль неверен»,
# и это оракул для перебора почт. Значение зашивается один раз при старте.
_DUMMY_PASSWORD_HASH = hash_password("wms-270-dummy-timing-guard")


async def login(session: AsyncSession, *, email: str, password: str) -> tuple[User, str]:
    """Единая проверка входа без утечки состояния аккаунта.

    Любой отказ уходит одинаковым `AuthError("invalid_credentials")`: нет такой
    почты, не задан пароль, аккаунт заблокирован, неверный пароль — снаружи всё
    выглядит одинаково. Так входная форма перестаёт работать оракулом для
    перебора адресов и обнаружения аккаунтов с несозданным паролем (WMS-270).
    """
    stmt = select(User).where(User.email == email.strip().lower())
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    # Всегда считаем bcrypt: это выравнивает время ответа для «нет пользователя»
    # и «пароль неверен». Без этого таймингом можно перебирать почты.
    if user is None or user.must_set_password:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        raise AuthError("invalid_credentials")
    if not verify_password(password, user.password_hash):
        raise AuthError("invalid_credentials")
    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        seller_id=user.seller_id,
    )
    return user, token


async def _email_taken(session: AsyncSession, email: str) -> bool:
    stmt = select(User).where(User.email == email.strip().lower())
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def create_seller_with_account(
    session: AsyncSession,
    *,
    acting_user: User,
    name: str,
    email: str,
    password: str | None,
) -> tuple[Seller, User]:
    if acting_user.role != FULFILLMENT_ADMIN:
        raise AuthError("forbidden")
    email_norm = email.strip().lower()
    if await _email_taken(session, email_norm):
        raise AuthError("email_taken")
    if password and password.strip():
        password_hash = hash_password(password)
        must_set_password = False
    else:
        password_hash = hash_password(secrets.token_urlsafe(64))
        must_set_password = True
    seller = Seller(tenant_id=acting_user.tenant_id, name=name.strip())
    user = User(
        tenant_id=acting_user.tenant_id,
        seller=seller,
        email=email_norm,
        password_hash=password_hash,
        must_set_password=must_set_password,
        role=FULFILLMENT_SELLER,
    )
    session.add(seller)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AuthError("email_taken") from exc
    await session.refresh(seller)
    await session.refresh(user)
    return seller, user


async def create_seller_user(
    session: AsyncSession,
    *,
    acting_user: User,
    seller_id: uuid.UUID,
    email: str,
    password: str | None,
) -> User:
    if acting_user.role != FULFILLMENT_ADMIN:
        raise AuthError("forbidden")
    seller = await session.get(Seller, seller_id)
    if seller is None or seller.tenant_id != acting_user.tenant_id:
        raise AuthError("seller_not_found")
    if password and password.strip():
        password_hash = hash_password(password)
        must_set_password = False
    else:
        password_hash = hash_password(secrets.token_urlsafe(64))
        must_set_password = True
    user = User(
        tenant_id=acting_user.tenant_id,
        seller_id=seller_id,
        email=email.strip().lower(),
        password_hash=password_hash,
        must_set_password=must_set_password,
        role=FULFILLMENT_SELLER,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AuthError("email_taken") from exc
    await session.refresh(user)
    return user


async def create_staff_user(
    session: AsyncSession,
    *,
    acting_user: User,
    email: str,
    password: str | None,
) -> User:
    if acting_user.role not in (FULFILLMENT_ADMIN, FULFILLMENT_STAFF):
        raise AuthError("forbidden")
    if password and password.strip():
        password_hash = hash_password(password)
        must_set_password = False
    else:
        password_hash = hash_password(secrets.token_urlsafe(64))
        must_set_password = True
    user = User(
        tenant_id=acting_user.tenant_id,
        seller_id=None,
        email=email.strip().lower(),
        password_hash=password_hash,
        must_set_password=must_set_password,
        role=FULFILLMENT_STAFF,
    )
    session.add(user)
    try:
        await session.flush()
        perms = FfStaffPermissions(user_id=user.id)
        session.add(perms)
        # WMS-325: точка создания FF-сотрудника — сразу с набором прав (все False
        # по умолчанию). Пишем в тот же document_event с acting_user + after.
        await record_document_event_safely(
            session,
            tenant_id=user.tenant_id,
            document_type=DOCUMENT_TYPE_STAFF_USER,
            document_id=user.id,
            event_type=EVENT_STAFF_USER_CREATED,
            source=SOURCE_USER,
            actor_user_id=acting_user.id,
            payload_json={
                "role": "fulfillment_staff",
                "target_user_id": str(user.id),
                "acting_user_id": str(acting_user.id),
                "email": user.email,
                "before": None,
                "after": {
                    "settings": False,
                    "mp_shipments": False,
                    "reception": False,
                    "cells": False,
                    "inventory": False,
                    "packaging": False,
                    "shift_lead": False,
                },
            },
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AuthError("email_taken") from exc
    await session.refresh(user)
    return user


async def set_initial_password(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> User:
    stmt = select(User).where(User.email == email.strip().lower())
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthError("invalid_credentials")
    if user.role not in (FULFILLMENT_SELLER, FULFILLMENT_STAFF):
        raise AuthError("forbidden")
    if not user.must_set_password:
        raise AuthError("password_already_set")
    user.password_hash = hash_password(password)
    user.must_set_password = False
    await session.commit()
    await session.refresh(user)
    return user


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


_INVITE_SUBJECT = "Доступ в складскую систему"
_RESET_SUBJECT = "Восстановление пароля в складской системе"


def _invite_body(link: str, hours: int) -> str:
    return (
        "Здравствуйте!\n\n"
        "Для вас создан личный кабинет в складской системе.\n"
        "Чтобы задать пароль и войти, откройте ссылку:\n\n"
        f"{link}\n\n"
        f"Ссылка действует {hours} ч. Если вы её не запрашивали — просто удалите письмо.\n"
    )


def _reset_body(link: str, hours: int) -> str:
    return (
        "Здравствуйте!\n\n"
        "Кто-то запросил восстановление пароля для вашего кабинета.\n"
        "Чтобы задать новый пароль, откройте ссылку:\n\n"
        f"{link}\n\n"
        f"Ссылка действует {hours} ч. Если это были не вы — просто удалите письмо, "
        "текущий пароль останется прежним.\n"
    )


async def send_auth_link(
    user: User,
    *,
    purpose: Literal["invite", "reset"],
    base_url: str,
) -> bool:
    """Отправить письмо со ссылкой. Возвращает True, если письмо ушло."""
    token = create_auth_link_token(user, purpose=purpose)
    link = build_link(
        token,
        base_url=base_url,
        seller_portal=user.role == FULFILLMENT_SELLER,
    )
    hours = settings.auth_link_ttl_hours
    if purpose == "invite":
        subject, body = _INVITE_SUBJECT, _invite_body(link, hours)
    else:
        subject, body = _RESET_SUBJECT, _reset_body(link, hours)
    return await send_email(to=user.email, subject=subject, body=body)


async def request_password_reset(
    session: AsyncSession,
    *,
    email: str,
    base_url: str,
    background_tasks: BackgroundTasks | None = None,
) -> None:
    """Отправить ссылку сброса, если такой пользователь есть.

    Наружу ничего не сообщаем ни в каком случае: иначе форма превращается в
    проверялку «есть ли такая почта в системе».
    """
    stmt = select(User).where(User.email == email.strip().lower())
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        return
    if background_tasks is not None:
        # Ответ уходит сразу: человек не должен ждать почтовый сервер.
        background_tasks.add_task(
            send_auth_link, user, purpose="reset", base_url=base_url
        )
        return
    await send_auth_link(user, purpose="reset", base_url=base_url)


async def set_password_by_link(
    session: AsyncSession,
    *,
    token: str,
    password: str,
) -> tuple[User, str]:
    """Задать пароль по ссылке из письма — и для приглашения, и для сброса."""
    try:
        user_id, _purpose, fingerprint = decode_auth_link_token(token)
    except AuthLinkError as exc:
        raise AuthError(exc.args[0] if exc.args else "link_invalid") from exc
    # Serialize link consumption and recheck the latest password fingerprint.
    user = await session.get(User, user_id, with_for_update=True, populate_existing=True)
    if user is None:
        raise AuthError("link_invalid")
    if not fingerprint_matches(user, fingerprint):
        # Пароль уже сменили — значит ссылка отработала или устарела.
        raise AuthError("link_used")
    user.password_hash = hash_password(password)
    user.must_set_password = False
    await session.commit()
    await session.refresh(user)
    access_token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        seller_id=user.seller_id,
    )
    return user, access_token
