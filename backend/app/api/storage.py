from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import require_ff_or_seller_with_permission, require_fulfillment_admin
from app.core.settings import settings
from app.db.session import get_db
from app.models.billing import BillingTariffVersion
from app.models.storage_measurement import StorageMeasurement
from app.models.storage_statement import StorageStatement
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services import background_job_service as job_svc
from app.services.background_job_service import JOB_TYPE_STORAGE_MEASUREMENT_REBUILD
from app.services.staff_packaging_billing_service import kopecks_to_rub_str
from app.services.staff_permissions_service import PERM_INVENTORY
from app.services.storage_measurement_service import (
    MOSCOW,
    StorageMeasurementError,
    month_bounds,
    previous_month,
)
from app.services.storage_statement_service import (
    StorageStatementError,
    create_storage_tariff,
    fix_storage_statement,
    get_fixed_storage_statement,
    get_storage_draft_pricing,
    get_storage_ledger_rows,
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
    total_liter_days: str
    total_amount: str
    problem_count: int


class StorageStatementsOut(BaseModel):
    tariff_configured: bool
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
    warehouse_id: uuid.UUID
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
    recalculated_statements: list[StorageStatementOut] = Field(default_factory=list)


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


def _statement_out(
    statement: StorageStatement, rows: list[StorageMeasurement]
) -> StorageStatementOut:
    total_liter_days = sum((Decimal(str(row.liter_days)) for row in rows), Decimal(0))
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
                "seller_article": row.product.wb_vendor_code,
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
                "liter_days": str(row.liter_days),
                "rate_snapshot": None,
                "amount": None,
                "status": row.status,
                "source_type": "storage_measurement",
            }
            for row in rows
        ],
        total_liter_days=str(total_liter_days),
        total_amount="0",
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
            "seller_article": row.product.wb_vendor_code,
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


def _apply_draft_pricing(
    output: StorageStatementOut,
    rows: list[StorageMeasurement],
    pricing: dict[uuid.UUID, tuple[Decimal, Decimal, BillingTariffVersion]],
) -> None:
    """Attach a freshly calculated tariff preview without publishing ledger rows."""
    total_quantity = Decimal(0)
    total_amount = Decimal(0)
    for public_row, measurement in zip(output.measurements, rows, strict=True):
        row_pricing = pricing.get(measurement.id)
        if row_pricing is None:
            continue
        quantity, amount, tariff = row_pricing
        effective_rate = amount / quantity if quantity else Decimal(tariff.amount) / Decimal(100)
        public_row["liter_days"] = str(quantity)
        public_row["rate_snapshot"] = _rate_snapshot(effective_rate)
        public_row["amount"] = str(amount)
        total_quantity += quantity
        total_amount += amount
    output.total_liter_days = str(total_quantity)
    output.total_amount = str(total_amount)


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
    if warehouse_id is not None:
        warehouse_query = warehouse_query.where(Warehouse.id == warehouse_id)
    warehouses = list((await session.scalars(warehouse_query)).all())
    operational_ids = {warehouse.id for warehouse in warehouses}

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

    tariff_warehouse_ids = set(
        (
            await session.scalars(
                select(BillingTariffVersion.warehouse_id).where(
                    BillingTariffVersion.tenant_id == user.tenant_id,
                    BillingTariffVersion.warehouse_id.in_(operational_ids or {uuid.UUID(int=0)}),
                    BillingTariffVersion.service_code == "storage_liter_day",
                    BillingTariffVersion.unit == "liter_day",
                    BillingTariffVersion.valid_from <= period_end,
                    or_(
                        BillingTariffVersion.valid_to.is_(None),
                        BillingTariffVersion.valid_to >= period_start,
                    ),
                    (
                        or_(
                            BillingTariffVersion.seller_id.is_(None),
                            BillingTariffVersion.seller_id == user.seller_id,
                        )
                        if user.role == "fulfillment_seller"
                        else BillingTariffVersion.seller_id.is_(None)
                    ),
                )
            )
        ).all()
    )
    tariff_configured = bool(operational_ids) and tariff_warehouse_ids == operational_ids
    statement_outputs: list[StorageStatementOut] = []
    for statement in statements:
        rows = rows_by_scope.get((statement.seller_id, statement.warehouse_id), [])
        output = _statement_out(statement, rows)
        if statement.status == "fixed":
            ledger = await get_storage_ledger_rows(session, user.tenant_id, statement.id)
            _apply_ledger_snapshot(output, rows, ledger)
        elif priceable_rows := [row for row in rows if row.status == "calculated"]:
            try:
                pricing = await get_storage_draft_pricing(session, statement, priceable_rows)
            except StorageStatementError as exc:
                if str(exc) != "tariff_not_found":
                    raise
            else:
                _apply_draft_pricing(output, rows, pricing)
        statement_outputs.append(output)

    return StorageStatementsOut(
        tariff_configured=tariff_configured,
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
        wh_tariff, sel_tariff, repriced_drafts = await create_storage_tariff(
            session,
            user.tenant_id,
            body.warehouse_id,
            body.amount,
            body.valid_from,
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
                    "warehouse_not_operational",
                }
                else 404
                if code in {"warehouse_not_found", "seller_not_found"}
                else 409
            ),
            detail=code,
        ) from exc

    seller_exception_out: TariffVersionOut | None = None
    if sel_tariff is not None and body.seller_exception is not None:
        seller_exception_out = TariffVersionOut(
            id=sel_tariff.id,
            warehouse_id=body.warehouse_id,
            seller_id=body.seller_exception.seller_id,
            amount=kopecks_to_rub_str(sel_tariff.amount),
            valid_from=sel_tariff.valid_from.isoformat(),
        )

    recalculated_statements: list[StorageStatementOut] = []
    for draft in repriced_drafts:
        output = _statement_out(draft.statement, draft.measurements)
        _apply_draft_pricing(output, draft.measurements, draft.pricing)
        recalculated_statements.append(output)

    return TariffCreateOut(
        warehouse_tariff=TariffVersionOut(
            id=wh_tariff.id,
            warehouse_id=body.warehouse_id,
            seller_id=None,
            amount=kopecks_to_rub_str(wh_tariff.amount),
            valid_from=wh_tariff.valid_from.isoformat(),
        ),
        seller_exception=seller_exception_out,
        recalculated_statements=recalculated_statements,
    )


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


@router.post("/statements/{statement_id}/fix", response_model=StorageStatementOut)
async def fix_statement(
    statement_id: uuid.UUID,
    user: Annotated[User, Depends(require_storage_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StorageStatementOut:
    if user.role != "fulfillment_admin":
        raise HTTPException(status_code=403, detail="forbidden")
    tenant_id = user.tenant_id
    try:
        statement = await fix_storage_statement(session, tenant_id, statement_id)
        statement, rows = await get_fixed_storage_statement(session, tenant_id, statement_id)
    except StorageStatementError as exc:
        code = str(exc)
        raise HTTPException(
            status_code=(
                409
                if code
                in {
                    "already_fixed",
                    "missing_dimensions",
                    "not_editable",
                    "period_not_closed",
                    "tariff_not_found",
                }
                else 422
                if code
                in {
                    "ledger_quantity_out_of_range",
                    "ledger_rate_out_of_range",
                    "ledger_amount_out_of_range",
                }
                else 404
            ),
            detail=code,
        ) from exc
    out = _statement_out(statement, rows)
    ledger = await get_storage_ledger_rows(session, tenant_id, statement_id)
    _apply_ledger_snapshot(out, rows, ledger)
    return out


@router.get("/statements/{statement_id}/print", response_model=StorageStatementOut)
async def print_statement(
    statement_id: uuid.UUID,
    user: Annotated[User, Depends(require_storage_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StorageStatementOut:
    try:
        statement, rows = await get_fixed_storage_statement(session, user.tenant_id, statement_id)
        if user.role == "fulfillment_seller" and user.seller_id != statement.seller_id:
            raise StorageStatementError("not_found")
    except StorageStatementError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    out = _statement_out(statement, rows)
    ledger = await get_storage_ledger_rows(session, user.tenant_id, statement.id)
    _apply_ledger_snapshot(out, rows, ledger)
    return out
