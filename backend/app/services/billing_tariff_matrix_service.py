from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal, TypedDict, cast
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.billing import (
    BillingTariffMatrixConfig,
    BillingTariffServiceState,
    BillingTariffVersionV2,
)
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.user import User

MOSCOW = ZoneInfo("Europe/Moscow")

# Хранение живёт в общей матрице вместе с остальными услугами: держать его
# на отдельном экране означало единственную услугу с другим местом настройки.
MATRIX_SERVICE_CODES = (
    "inbound",
    "marketplace_outbound",
    "packing",
    "return",
    "storage",
    "fbs_order",
)
STORAGE_SERVICE_CODE = "storage"
# Сборка заказа FBS считается за штуку товара, а не за заказ: у Wildberries в
# заказе всегда одна штука, а у Ozon будет иначе, и ставка «за заказ» там соврёт.
FBS_ORDER_SERVICE_CODE = "fbs_order"
EMPLOYEE_SERVICE_CODES = ("inbound", "picking", "marketplace_outbound", "return")
MAX_TARIFF_RATE_KOPECKS = 2_147_483_647


class BillingTariffMatrixError(ValueError):
    pass


async def ensure_disabled_tariff_matrix(
    session: AsyncSession, *, tenant: Tenant
) -> BillingTariffMatrixConfig:
    """Create the durable disabled baseline as part of a Tenant transaction."""
    if tenant.id is None:
        await session.flush()
    existing = await session.scalar(
        select(BillingTariffMatrixConfig)
        .where(BillingTariffMatrixConfig.tenant_id == tenant.id)
        .options(selectinload(BillingTariffMatrixConfig.service_states))
    )
    if existing is not None:
        # Матрица уже есть, но список услуг мог расшириться после её создания
        # (так пришло хранение). Без дозаполнения у давнего арендатора новая
        # услуга просто не появилась бы на экране, и он не понял бы почему.
        known = {state.service_code for state in existing.service_states}
        missing = [code for code in MATRIX_SERVICE_CODES if code not in known]
        if missing:
            existing.service_states.extend(
                BillingTariffServiceState(
                    tenant_id=tenant.id, service_code=service_code, enabled=False
                )
                for service_code in missing
            )
            await session.flush()
        return existing
    config = BillingTariffMatrixConfig(tenant_id=tenant.id)
    config.service_states = [
        BillingTariffServiceState(tenant_id=tenant.id, service_code=service_code, enabled=False)
        for service_code in MATRIX_SERVICE_CODES
    ]
    session.add(config)
    try:
        await session.flush()
    except IntegrityError:
        # A concurrent bootstrap won the unique tenant row.  Its matrix is the
        # only valid result; never leave a silent missing configuration behind.
        existing = await session.scalar(
            select(BillingTariffMatrixConfig)
            .where(BillingTariffMatrixConfig.tenant_id == tenant.id)
            .options(selectinload(BillingTariffMatrixConfig.service_states))
        )
        if existing is None:
            raise
        return cast(BillingTariffMatrixConfig, existing)
    return config


async def get_tariff_matrix(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> BillingTariffMatrixConfig:
    config = await session.scalar(
        select(BillingTariffMatrixConfig)
        .where(BillingTariffMatrixConfig.tenant_id == tenant_id)
        .options(selectinload(BillingTariffMatrixConfig.service_states))
    )
    if config is None:
        raise BillingTariffMatrixError("billing_tariff_matrix_config_missing")
    return config


async def list_tariff_matrix_versions(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> list[BillingTariffVersionV2]:
    return list(
        (
            await session.scalars(
                select(BillingTariffVersionV2)
                .where(BillingTariffVersionV2.tenant_id == tenant_id)
                .order_by(
                    BillingTariffVersionV2.service_code,
                    BillingTariffVersionV2.employee_user_id,
                    BillingTariffVersionV2.seller_id,
                    BillingTariffVersionV2.product_id,
                    BillingTariffVersionV2.valid_from_at,
                )
            )
        ).all()
    )


class TariffVersionDraft(TypedDict):
    seller_id: uuid.UUID | None
    product_id: uuid.UUID | None
    employee_user_id: uuid.UUID | None
    service_code: str
    unit: str
    enabled: bool
    rate: int
    valid_from_at: datetime
    valid_to_at: datetime | None


TariffField = Literal[
    "seller_id",
    "product_id",
    "employee_user_id",
    "service_code",
    "unit",
    "valid_from_at",
    "valid_to_at",
]


def _field(draft: TariffVersionDraft | BillingTariffVersionV2, name: TariffField) -> object:
    return draft[name] if isinstance(draft, dict) else getattr(draft, name)


def _utc_field(
    draft: TariffVersionDraft | BillingTariffVersionV2,
    name: Literal["valid_from_at", "valid_to_at"],
) -> datetime | None:
    return _as_utc(cast(datetime | None, _field(draft, name)))


def _scope_key(draft: TariffVersionDraft | BillingTariffVersionV2) -> tuple[object, ...]:
    return (
        _field(draft, "seller_id"),
        _field(draft, "product_id"),
        _field(draft, "employee_user_id"),
        _field(draft, "service_code"),
    )


def _is_stored_unchanged(
    draft: TariffVersionDraft, rows: list[BillingTariffVersionV2]
) -> bool:
    """Ставку прислали ровно такой, какой она уже лежит в базе.

    Экран тарифов присылает обратно весь список версий, включая давно
    закрытые. Без этой проверки арендатор, у которого когда-то была ставка
    «за документ», не смог бы сохранить матрицу вообще: собственная история
    ломала бы ему валидацию единицы.
    """
    return any(
        _scope_key(row) == _scope_key(draft)
        and _as_utc(row.valid_from_at) == _as_utc(draft["valid_from_at"])
        and _as_utc(row.valid_to_at) == _as_utc(draft["valid_to_at"])
        and row.unit == draft["unit"]
        and row.enabled == draft["enabled"]
        and row.rate == draft["rate"]
        for row in rows
    )


def _same_version(draft: TariffVersionDraft, row: BillingTariffVersionV2) -> bool:
    return (
        row.unit == draft["unit"]
        and row.enabled == draft["enabled"]
        and row.rate == draft["rate"]
        and _as_utc(row.valid_from_at) == draft["valid_from_at"]
        and _as_utc(row.valid_to_at) == draft["valid_to_at"]
    )


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _interval_overlaps(
    *, start: datetime, end: datetime | None, other_start: datetime, other_end: datetime | None
) -> bool:
    return (end is None or other_start < end) and (other_end is None or start < other_end)


async def save_tariff_matrix(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    revision: int,
    services: dict[str, bool],
    versions: list[TariffVersionDraft],
) -> BillingTariffMatrixConfig:
    if any(
        draft["rate"] < 0 or draft["rate"] > MAX_TARIFF_RATE_KOPECKS
        for draft in versions
    ):
        raise BillingTariffMatrixError("billing_tariff_matrix_rate_invalid")
    # Serialize every matrix stream through its tenant, including an empty one.
    # Locking just the config/versions leaves two initial saves free to accept the
    # same revision and create overlapping intervals.
    tenant = await session.scalar(
        select(Tenant).where(Tenant.id == tenant_id).with_for_update()
    )
    if tenant is None:
        raise BillingTariffMatrixError("billing_tariff_matrix_tenant_not_found")
    config = await get_tariff_matrix(session, tenant_id=tenant_id)
    if config.revision != revision:
        raise BillingTariffMatrixError("billing_tariff_matrix_stale_revision")
    if set(services) != set(MATRIX_SERVICE_CODES):
        raise BillingTariffMatrixError("billing_tariff_matrix_services_incomplete")
    current_versions = await list_tariff_matrix_versions(session, tenant_id=tenant_id)
    normalized_versions: list[TariffVersionDraft] = []
    for draft in versions:
        product: Product | None = None
        employee_scope = draft["employee_user_id"] is not None
        if draft["service_code"] not in (
            EMPLOYEE_SERVICE_CODES if employee_scope else MATRIX_SERVICE_CODES
        ):
            raise BillingTariffMatrixError("billing_tariff_matrix_service_invalid")
        # Единица привязана к природе услуги: хранение считается за литро-день,
        # всё остальное — за штуку. Разрешить хранению «за штуку» значит
        # соврать в расчёте, а не просто нарушить формат.
        #
        # Выбора «за документ» больше нет: склад принимает и отгружает штуки, а
        # не бумажки, и ставка за документ врала тем сильнее, чем крупнее был
        # документ. Старые версии со «за документ» остаются в истории и
        # продолжают читаться — их можно прислать обратно неизменными, но
        # завести новую такую ставку нельзя.
        if draft["service_code"] == STORAGE_SERVICE_CODE:
            if draft["unit"] != "liter_day":
                raise BillingTariffMatrixError("billing_tariff_matrix_storage_unit_invalid")
        elif draft["service_code"] == FBS_ORDER_SERVICE_CODE:
            if draft["unit"] != "item":
                raise BillingTariffMatrixError("billing_tariff_matrix_fbs_unit_invalid")
        elif draft["unit"] != "item" and not _is_stored_unchanged(draft, current_versions):
            raise BillingTariffMatrixError("billing_tariff_matrix_unit_invalid")
        if employee_scope and (draft["seller_id"] is not None or draft["product_id"] is not None):
            raise BillingTariffMatrixError("billing_tariff_matrix_employee_scope_invalid")
        if employee_scope and draft["unit"] != "item":
            raise BillingTariffMatrixError("billing_tariff_matrix_employee_unit_invalid")
        if draft["product_id"] is not None:
            if draft["unit"] != "item" or draft["seller_id"] is None:
                raise BillingTariffMatrixError("billing_tariff_matrix_product_scope_invalid")
            product = await session.scalar(
                select(Product).where(
                    Product.id == draft["product_id"], Product.tenant_id == tenant_id
                )
            )
            if product is None:
                raise BillingTariffMatrixError("billing_tariff_matrix_product_not_found")
        if draft["seller_id"] is not None:
            seller = await session.scalar(
                select(Seller).where(Seller.id == draft["seller_id"], Seller.tenant_id == tenant_id)
            )
            if seller is None:
                raise BillingTariffMatrixError("billing_tariff_matrix_seller_not_found")
            if (
                draft["product_id"] is not None
                and product is not None
                and product.seller_id != seller.id
            ):
                raise BillingTariffMatrixError("billing_tariff_matrix_product_seller_mismatch")
        if draft["employee_user_id"] is not None:
            user = await session.scalar(
                select(User).where(
                    User.id == draft["employee_user_id"], User.tenant_id == tenant_id
                )
            )
            if user is None:
                raise BillingTariffMatrixError("billing_tariff_matrix_employee_not_found")
        if draft["valid_from_at"].tzinfo is None or (
            draft["valid_to_at"] is not None and draft["valid_to_at"] <= draft["valid_from_at"]
        ):
            raise BillingTariffMatrixError("billing_tariff_matrix_interval_invalid")
        normalized_versions.append(
            {
                **draft,
                "valid_from_at": draft["valid_from_at"].astimezone(UTC),
                "valid_to_at": (
                    draft["valid_to_at"].astimezone(UTC)
                    if draft["valid_to_at"] is not None
                    else None
                ),
            }
        )

    for draft in normalized_versions:
        if draft["product_id"] is None:
            continue
        all_versions: list[BillingTariffVersionV2 | TariffVersionDraft] = [
            *current_versions,
            *normalized_versions,
        ]
        matching_common: list[BillingTariffVersionV2 | TariffVersionDraft] = [
            row
            for row in all_versions
            if (
                _field(row, "seller_id") is None
                and _field(row, "product_id") is None
                and _field(row, "employee_user_id") is None
                and _field(row, "service_code") == draft["service_code"]
                and cast(datetime, _utc_field(row, "valid_from_at")) <= draft["valid_from_at"]
                and (
                    _utc_field(row, "valid_to_at") is None
                    or cast(datetime, _utc_field(row, "valid_to_at")) > draft["valid_from_at"]
                )
            )
        ]
        if (
            matching_common
            and _field(
                max(
                    matching_common,
                    key=lambda row: cast(datetime, _utc_field(row, "valid_from_at")),
                ),
                "unit",
            )
            != "item"
        ):
            raise BillingTariffMatrixError("billing_tariff_matrix_product_requires_item")

    changed = False
    for draft in normalized_versions:
        stream = [row for row in current_versions if _scope_key(row) == _scope_key(draft)]
        same_start = [row for row in stream if _as_utc(row.valid_from_at) == draft["valid_from_at"]]
        if same_start:
            if len(same_start) == 1 and _same_version(draft, same_start[0]):
                continue
            raise BillingTariffMatrixError("billing_tariff_matrix_interval_overlap")
        overlaps = [
            row
            for row in stream
            if _interval_overlaps(
                start=draft["valid_from_at"],
                end=draft["valid_to_at"],
                other_start=cast(datetime, _as_utc(row.valid_from_at)),
                other_end=_as_utc(row.valid_to_at),
            )
        ]
        if overlaps:
            predecessor = overlaps[0] if len(overlaps) == 1 else None
            first_future_start = min(cast(datetime, _as_utc(row.valid_from_at)) for row in overlaps)
            inserted_before = (
                draft["valid_from_at"] < first_future_start and draft["valid_to_at"] is None
            )
            if inserted_before:
                # A browser edit uses the current Moscow minute.  If the loaded
                # tariff starts later, insert this new version before it rather
                # than silently moving the operator's effective time forward.
                draft["valid_to_at"] = first_future_start
            else:
                if (
                    predecessor is None
                    or predecessor.valid_to_at is not None
                    or cast(datetime, _as_utc(predecessor.valid_from_at)) >= draft["valid_from_at"]
                    or draft["valid_to_at"] is not None
                ):
                    raise BillingTariffMatrixError("billing_tariff_matrix_interval_overlap")
                predecessor.valid_to_at = draft["valid_from_at"]
        created = BillingTariffVersionV2(tenant_id=tenant_id, **draft)
        session.add(created)
        current_versions.append(created)
        changed = True

    states = {state.service_code: state for state in config.service_states}
    for service_code, enabled in services.items():
        if states[service_code].enabled != enabled:
            states[service_code].enabled = enabled
            changed = True
    # Начисления не создаются, пока у арендатора не проставлена дата начала
    # биллинга. Раньше её ставил только старый путь создания тарифа, а через
    # матрицу — единственный экран, которым пользуются, — она оставалась пустой,
    # и работа склада не стоила ничего: ставки заданы, а денег ноль.
    if normalized_versions and tenant.billing_enabled_from is None:
        tenant.billing_enabled_from = min(
            draft["valid_from_at"].astimezone(MOSCOW).date() for draft in normalized_versions
        )
        changed = True
    if changed:
        config.revision += 1
    await session.flush()
    return config
