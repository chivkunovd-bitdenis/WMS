from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import require_ff_or_seller_with_permission, require_fulfillment_admin
from app.core.settings import settings
from app.db.session import get_db
from app.models.billing import BillingTariffVersionV2
from app.models.storage_measurement import StorageMeasurement
from app.models.storage_statement import StorageStatement
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services import background_job_service as job_svc
from app.services.background_job_service import JOB_TYPE_STORAGE_MEASUREMENT_REBUILD
from app.services.billing_tariff_matrix_service import get_tariff_matrix
from app.services.staff_packaging_billing_service import kopecks_to_rub_str
from app.services.staff_permissions_service import PERM_INVENTORY
from app.services.storage_measurement_service import (
    MOSCOW,
    StorageMeasurementError,
    month_bounds,
    previous_month,
)
from app.services.storage_statement_service import (
    StorageNightCharge,
    StorageStatementError,
    create_storage_tariff,
    get_storage_ledger_rows,
    get_storage_ledger_rows_batch,
    get_storage_night_charges_batch,
    get_storage_statement_for_print,
    normalize_storage_tariff_amount,
)

router = APIRouter(prefix="/operations/storage", tags=["storage"])
require_storage_access = require_ff_or_seller_with_permission(PERM_INVENTORY)


class StorageRebuildBody(BaseModel):
    year: int | None = None
    month: int | None = None
    warehouse_id: uuid.UUID | None = None


class StorageRebuildOut(BaseModel):
    id: str
    status: str


class StorageStatementOut(BaseModel):
    id: uuid.UUID
    status: str
    fixed_at: str | None
    period_start: str
    period_end: str
    seller_id: uuid.UUID
    warehouse_id: uuid.UUID
    seller_name: str | None = None
    warehouse_name: str | None = None
    measurements: list[dict[str, object]]
    # Пусто, когда ночных начислений за период нет: экран показывает прочерк, а
    # не ноль. Ноль означал бы «хранение бесплатно», и это неправда.
    total_liter_days: str | None
    total_amount: str | None
    problem_count: int


class StorageStatementsOut(BaseModel):
    tariff_configured: bool
    tariff_revision: int
    warehouses: list[dict[str, object]]
    statements: list[StorageStatementOut]


StorageTariffAmount = Annotated[
    Decimal,
    Field(gt=0),
    AfterValidator(normalize_storage_tariff_amount),
]


class SellerExceptionBody(BaseModel):
    seller_id: uuid.UUID
    amount: StorageTariffAmount
    valid_from: date


class TariffCreateBody(BaseModel):
    revision: int = Field(ge=0)
    amount: StorageTariffAmount
    valid_from: date
    seller_exception: SellerExceptionBody | None = None


class TariffVersionOut(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID | None
    seller_id: uuid.UUID | None
    amount: str
    valid_from: str


class TariffCreateOut(BaseModel):
    warehouse_tariff: TariffVersionOut
    seller_exception: TariffVersionOut | None = None
    tariff_revision: int


def _public_dimension_source(source: str | None) -> str | None:
    if source is None:
        return None
    aliases: dict[str, str] = {
        "wb": "wildberries",
        "container_override": "container",
        "container": "container",
    }
    return aliases.get(source, source)


def _rate_snapshot(value: object) -> str:
    """Keep meaningful precision while displaying ordinary rates as money."""
    rendered = format(Decimal(str(value)), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if "." not in rendered:
        return f"{rendered}.00"
    whole, fraction = rendered.split(".", 1)
    return f"{whole}.{fraction.ljust(2, '0')}"


def _matrix_date_in_moscow(value: datetime) -> str:
    """SQLite drops tzinfo from V2 datetimes; persisted values are UTC instants."""
    local = (
        value.replace(tzinfo=UTC).astimezone(MOSCOW)
        if value.tzinfo is None
        else value.astimezone(MOSCOW)
    )
    return local.date().isoformat()


def _dimensions_mm(row: StorageMeasurement) -> list[int] | None:
    """Габариты, по которым посчитан объём: из обмера, иначе из карточки товара."""
    source = row.dimension_event if row.dimension_event is not None else row.product
    sides = (source.length_mm, source.width_mm, source.height_mm)
    if any(side is None for side in sides):
        return None
    return [int(side) for side in sides if side is not None]


def _statement_out(
    statement: StorageStatement, rows: list[StorageMeasurement]
) -> StorageStatementOut:
    """Операционная часть расчёта: что за товар, какой коробки и сколько лежало.

    Литро-дни и деньги сюда не попадают: их даёт ночное начисление, и добавляет
    их :func:`_apply_night_charges` (или, у документов, зафиксированных до
    перехода, снимок проводок).
    """
    problem_count = sum(row.status == "missing_dimensions" for row in rows)
    return StorageStatementOut(
        id=statement.id,
        status=statement.status,
        fixed_at=statement.fixed_at.isoformat() if statement.fixed_at else None,
        period_start=statement.period_start.isoformat(),
        period_end=statement.period_end.isoformat(),
        seller_id=statement.seller_id,
        warehouse_id=statement.warehouse_id,
        seller_name=statement.seller.name,
        warehouse_name=statement.warehouse.name,
        measurements=[
            {
                "product_id": row.product_id,
                "sku": row.product.sku_code,
                "product_name": row.product.name,
                "seller_article": row.product.wb_vendor_code,
                # Габариты и штуко-дни отвечают на два вопроса кладовщика:
                # «что это за коробка» и «сколько её лежало за месяц».
                "dimensions_mm": _dimensions_mm(row),
                "quantity_days": str(row.quantity_days),
                "volume_liters": (
                    str(row.dimension_event.volume_liters)
                    if row.dimension_event is not None
                    and row.dimension_event.volume_liters is not None
                    else str(row.product.volume_liters)
                    if row.product.volume_liters is not None
                    else None
                ),
                "dimensions_source": _public_dimension_source(
                    row.dimension_event.source
                    if row.dimension_event is not None
                    else row.product.dimensions_source
                ),
                "liter_days": None,
                "rate_snapshot": None,
                "amount": None,
                "status": row.status,
                "source_type": "storage_measurement",
            }
            for row in rows
        ],
        total_liter_days=None,
        total_amount=None,
        problem_count=problem_count,
    )


def _print_measurements(
    rows: list[StorageMeasurement], ledger: list[Any]
) -> list[dict[str, object]]:
    """Build printable SKU rows from the fixed document and its ledger snapshot."""
    ledger_by_source_id = {entry.source_id: entry for entry in ledger}
    return [
        {
            "product_id": row.product_id,
            "sku": row.product.sku_code,
            "product_name": row.product.name,
            "seller_article": row.product.wb_vendor_code,
            "dimensions_mm": _dimensions_mm(row),
            "quantity_days": str(row.quantity_days),
            "volume_liters": str(
                row.dimension_event.volume_liters
                if row.dimension_event is not None
                else row.product.volume_liters
            )
            if (row.dimension_event is not None and row.dimension_event.volume_liters is not None)
            or row.product.volume_liters is not None
            else None,
            "dimensions_source": (
                row.dimension_event.source
                if row.dimension_event is not None
                else row.product.dimensions_source
            ),
            # The printable document mirrors the immutable financial event.
            # A tariff that starts mid-month can charge fewer liter-days than
            # the operational measurement calculated for the whole month.
            "liter_days": str(ledger_by_source_id[row.id].quantity),
            "source_type": ledger_by_source_id[row.id].source_type,
            "service_code": ledger_by_source_id[row.id].service_code,
            "unit": ledger_by_source_id[row.id].unit,
            "rate_snapshot": kopecks_to_rub_str(int(ledger_by_source_id[row.id].rate or 0)),
            "amount": kopecks_to_rub_str(int(ledger_by_source_id[row.id].amount or 0)),
        }
        for row in rows
        if row.id in ledger_by_source_id
    ]


def _apply_ledger_snapshot(
    output: StorageStatementOut,
    rows: list[StorageMeasurement],
    ledger: list[Any],
) -> None:
    output.measurements = _print_measurements(rows, ledger)
    output.total_liter_days = str(
        sum((Decimal(str(entry.quantity)) for entry in ledger), Decimal(0))
    )
    output.total_amount = kopecks_to_rub_str(sum(int(entry.amount or 0) for entry in ledger))


def _apply_night_charges(
    output: StorageStatementOut,
    rows: list[StorageMeasurement],
    charges: dict[uuid.UUID, StorageNightCharge],
) -> None:
    """Показать то, что начислила ночь, а не пересчитать хранение заново.

    Ставка в строке — фактическая: начисленные деньги, делённые на начисленные
    литро-дни. Она расходится с заведённой в тарифе, если ставку меняли внутри
    месяца или часть суток прошла без тарифа, и тогда «ставка на литро-дни» в
    печатной форме сходится с суммой, а не спорит с ней.

    Товар без начислений остаётся с прочерками: обмера не было или ночь ещё не
    считала эти сутки. Придуманный ноль скрыл бы и то, и другое.
    """
    total_liter_days = Decimal(0)
    total_kopecks: int | None = None
    charged = False
    for public_row, measurement in zip(output.measurements, rows, strict=True):
        charge = charges.get(measurement.product_id)
        if charge is None:
            continue
        charged = True
        public_row["liter_days"] = str(charge.liter_days)
        total_liter_days += charge.liter_days
        if charge.amount_kopecks is None:
            continue
        public_row["amount"] = kopecks_to_rub_str(charge.amount_kopecks)
        total_kopecks = (total_kopecks or 0) + charge.amount_kopecks
        if charge.liter_days > 0:
            public_row["rate_snapshot"] = _rate_snapshot(
                (
                    Decimal(charge.amount_kopecks) / Decimal(100) / charge.liter_days
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            )
    if charged:
        output.total_liter_days = str(total_liter_days)
    if total_kopecks is not None:
        output.total_amount = kopecks_to_rub_str(total_kopecks)


@router.get("/statements", response_model=StorageStatementsOut)
async def list_statements(
    user: Annotated[User, Depends(require_storage_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    year: int | None = None,
    month: int | None = None,
    warehouse_id: uuid.UUID | None = None,
) -> StorageStatementsOut:
    """Show one calendar month's storage drafts without producing money."""
    if (year is None) != (month is None):
        raise HTTPException(status_code=422, detail="year_and_month_required_together")
    try:
        period_start, period_end = (
            month_bounds(year, month)
            if year is not None and month is not None
            else previous_month()
        )
    except StorageMeasurementError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if period_start > datetime.now(MOSCOW).date().replace(day=1):
        raise HTTPException(status_code=422, detail="future_month")

    warehouse_query = (
        select(Warehouse)
        .where(
            Warehouse.tenant_id == user.tenant_id,
            Warehouse.is_operational.is_(True),
        )
        .order_by(Warehouse.name, Warehouse.id)
    )
    all_operational_warehouses = list(
        (await session.scalars(warehouse_query)).all()
    )
    operational_ids = {
        warehouse.id for warehouse in all_operational_warehouses
    }
    warehouses = [
        warehouse
        for warehouse in all_operational_warehouses
        if warehouse_id is None or warehouse.id == warehouse_id
    ]

    statement_query = (
        select(StorageStatement)
        .options(
            joinedload(StorageStatement.seller),
            joinedload(StorageStatement.warehouse),
        )
        .where(
            StorageStatement.tenant_id == user.tenant_id,
            StorageStatement.period_start == period_start,
            StorageStatement.period_end == period_end,
            StorageStatement.warehouse_id.in_(operational_ids or {uuid.UUID(int=0)}),
        )
        .order_by(StorageStatement.created_at, StorageStatement.id)
    )
    if user.role == "fulfillment_seller":
        statement_query = statement_query.where(StorageStatement.seller_id == user.seller_id)
    statements = list((await session.scalars(statement_query)).unique().all())

    measurement_query = (
        select(StorageMeasurement)
        .options(
            joinedload(StorageMeasurement.product),
            joinedload(StorageMeasurement.dimension_event),
        )
        .where(
            StorageMeasurement.tenant_id == user.tenant_id,
            StorageMeasurement.period_start == period_start,
            StorageMeasurement.period_end == period_end,
            StorageMeasurement.warehouse_id.in_(operational_ids or {uuid.UUID(int=0)}),
        )
        .order_by(StorageMeasurement.product_id)
    )
    if user.role == "fulfillment_seller":
        measurement_query = measurement_query.where(StorageMeasurement.seller_id == user.seller_id)
    rows_by_scope: dict[tuple[uuid.UUID, uuid.UUID], list[StorageMeasurement]] = {}
    for row in (await session.scalars(measurement_query)).all():
        rows_by_scope.setdefault((row.seller_id, row.warehouse_id), []).append(row)

    matrix = await get_tariff_matrix(session, tenant_id=user.tenant_id)
    period_start_at = datetime.combine(period_start, datetime.min.time(), MOSCOW)
    period_end_at = datetime.combine(period_end, datetime.max.time(), MOSCOW)
    tariff_configured = bool(
        await session.scalar(
            select(BillingTariffVersionV2.id).where(
                BillingTariffVersionV2.tenant_id == user.tenant_id,
                BillingTariffVersionV2.service_code == "storage",
                BillingTariffVersionV2.unit == "liter_day",
                BillingTariffVersionV2.enabled.is_(True),
                BillingTariffVersionV2.employee_user_id.is_(None),
                BillingTariffVersionV2.product_id.is_(None),
                BillingTariffVersionV2.valid_from_at < period_end_at,
                or_(
                    BillingTariffVersionV2.valid_to_at.is_(None),
                    BillingTariffVersionV2.valid_to_at > period_start_at,
                ),
                (
                    or_(
                        BillingTariffVersionV2.seller_id.is_(None),
                        BillingTariffVersionV2.seller_id == user.seller_id,
                    )
                    if user.role == "fulfillment_seller"
                    else BillingTariffVersionV2.seller_id.is_(None)
                ),
            )
        )
    )
    rows_by_statement = {
        statement.id: rows_by_scope.get(
            (statement.seller_id, statement.warehouse_id),
            [],
        )
        for statement in statements
    }
    fixed_statements = [
        statement for statement in statements if statement.status == "fixed"
    ]
    ledger_by_statement = await get_storage_ledger_rows_batch(
        session,
        user.tenant_id,
        fixed_statements,
        rows_by_statement,
    )
    # Деньги и литро-дни на экране — это ночные начисления за выбранный месяц.
    # Фильтр по складу отбирает только то, что видно, и на цифры не влияет:
    # каждая строка начисления уже принадлежит своему складу и товару.
    charges_by_statement = await get_storage_night_charges_batch(
        session,
        user.tenant_id,
        statements,
        rows_by_statement,
    )

    statement_outputs: list[StorageStatementOut] = []
    for statement in statements:
        if warehouse_id is not None and statement.warehouse_id != warehouse_id:
            continue
        rows = rows_by_statement[statement.id]
        output = _statement_out(statement, rows)
        if statement.status == "fixed":
            ledger = ledger_by_statement.get(statement.id, [])
            _apply_ledger_snapshot(output, rows, ledger)
        else:
            _apply_night_charges(output, rows, charges_by_statement.get(statement.id, {}))
        statement_outputs.append(output)

    return StorageStatementsOut(
        tariff_configured=tariff_configured,
        tariff_revision=matrix.revision,
        warehouses=[{"id": warehouse.id, "name": warehouse.name} for warehouse in warehouses],
        statements=statement_outputs,
    )


@router.post("/tariffs", response_model=TariffCreateOut, status_code=status.HTTP_201_CREATED)
async def create_tariff(
    body: TariffCreateBody,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TariffCreateOut:
    """Create a storage rate for a warehouse; optionally add a seller override atomically.

    Only ``fulfillment_admin`` can configure tariffs.  If a seller exception is
    supplied, both the common warehouse tariff and the seller override are
    written in a single database transaction — a failure on either INSERT leaves
    no partial state.
    """
    seller_ex = (
        (
            body.seller_exception.seller_id,
            body.seller_exception.amount,
            body.seller_exception.valid_from,
        )
        if body.seller_exception is not None
        else None
    )
    try:
        wh_tariff, sel_tariff, tariff_revision = await create_storage_tariff(
            session,
            user.tenant_id,
            body.amount,
            body.valid_from,
            body.revision,
            seller_ex,
        )
    except StorageStatementError as exc:
        code = str(exc)
        raise HTTPException(
            status_code=(
                422
                if code
                in {
                    "tariff_amount_must_be_positive",
                    "tariff_amount_out_of_range",
                    "tariff_valid_from_in_past",
                    "billing_tariff_matrix_rate_invalid",
                }
                else 404
                if code in {"seller_not_found", "billing_tariff_matrix_seller_not_found"}
                else 409
            ),
            detail=code,
        ) from exc

    seller_exception_out: TariffVersionOut | None = None
    if sel_tariff is not None and body.seller_exception is not None:
        seller_exception_out = TariffVersionOut(
            id=sel_tariff.id,
            warehouse_id=None,
            seller_id=body.seller_exception.seller_id,
            amount=kopecks_to_rub_str(sel_tariff.rate),
            valid_from=_matrix_date_in_moscow(sel_tariff.valid_from_at),
        )

    return TariffCreateOut(
        warehouse_tariff=TariffVersionOut(
            id=wh_tariff.id,
            warehouse_id=None,
            seller_id=None,
            amount=kopecks_to_rub_str(wh_tariff.rate),
            valid_from=_matrix_date_in_moscow(wh_tariff.valid_from_at),
        ),
        seller_exception=seller_exception_out,
        tariff_revision=tariff_revision,
    )


# Пересчёт черновиков — не ручная операция и не деньги: он только обновляет
# витрину экрана хранения. Кнопки «Сформировать за месяц» больше нет — экран
# дёргает пересчёт сам после внесения обмера, а по ночам это делает задача
# начисления. Деньги за хранение пишет только она.
@router.post(
    "/measurements/rebuild", response_model=StorageRebuildOut, status_code=status.HTTP_202_ACCEPTED
)
async def rebuild_storage(
    body: StorageRebuildBody,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(require_storage_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StorageRebuildOut:
    if (body.year is None) != (body.month is None):
        raise HTTPException(status_code=422, detail="year_and_month_required_together")
    try:
        period_start, _ = (
            month_bounds(body.year, body.month)
            if body.year is not None and body.month is not None
            else previous_month()
        )
    except StorageMeasurementError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if period_start > datetime.now(MOSCOW).date().replace(day=1):
        raise HTTPException(status_code=422, detail="future_month")
    payload = {
        k: v
        for k, v in {
            "year": body.year,
            "month": body.month,
            "warehouse_id": str(body.warehouse_id) if body.warehouse_id else None,
        }.items()
        if v is not None
    }
    if user.role == "fulfillment_seller":
        payload["seller_id"] = str(user.seller_id)
    job = await job_svc.create_pending_job(
        session, user.tenant_id, job_type=JOB_TYPE_STORAGE_MEASUREMENT_REBUILD, payload_json=payload
    )
    if settings.celery_broker_url:
        from app.tasks.background_jobs import run_storage_measurement_rebuild_task

        run_storage_measurement_rebuild_task.delay(str(job.id))
    else:
        background_tasks.add_task(job_svc.run_storage_measurement_rebuild_job, job.id)
    return StorageRebuildOut(id=str(job.id), status=job.status)


@router.get("/statements/{statement_id}/print", response_model=StorageStatementOut)
async def print_statement(
    statement_id: uuid.UUID,
    user: Annotated[User, Depends(require_storage_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StorageStatementOut:
    try:
        statement, rows = await get_storage_statement_for_print(
            session, user.tenant_id, statement_id
        )
        if user.role == "fulfillment_seller" and user.seller_id != statement.seller_id:
            raise StorageStatementError("not_found")
    except StorageStatementError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    out = _statement_out(statement, rows)
    if statement.status == "fixed":
        # Документ, зафиксированный до перехода на ночное начисление, печатается
        # ровно теми цифрами, которые тогда ушли в проводки.
        ledger = await get_storage_ledger_rows(session, user.tenant_id, statement.id)
        _apply_ledger_snapshot(out, rows, ledger)
        return out
    # Печать берёт те же ночные начисления, что и список: одна бумага — одни
    # цифры. Если ночь по товару ещё не проходила, в строке стоит прочерк, но
    # обмеры, габариты и объёмы печатаются — оператору они нужны и без денег.
    charges = await get_storage_night_charges_batch(
        session,
        user.tenant_id,
        [statement],
        {statement.id: rows},
    )
    _apply_night_charges(out, rows, charges.get(statement.id, {}))
    return out
