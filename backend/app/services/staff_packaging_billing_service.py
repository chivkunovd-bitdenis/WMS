from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_STAFF
from app.models.packaging_task import STATUS_DONE, PackagingTask
from app.models.user import User

MSK = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True)
class StaffPackagingBillingTotals:
    units_packed: int
    earned_kopecks: int


def rub_to_kopecks(rate_rub: Decimal) -> int:
    kopecks = (rate_rub * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(kopecks)


def kopecks_to_rub_str(kopecks: int) -> str:
    whole = kopecks // 100
    frac = abs(kopecks) % 100
    return f"{whole}.{frac:02d}"


def month_bounds_msk(year: int, month: int) -> tuple[datetime, datetime]:
    start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=MSK)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=MSK)
    else:
        end_local = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=MSK)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def parse_billing_month(value: str) -> tuple[int, int]:
    parts = value.strip().split("-", 1)
    if len(parts) != 2:
        raise ValueError("invalid_month")
    year = int(parts[0])
    month = int(parts[1])
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise ValueError("invalid_month")
    return year, month


def current_billing_month_msk() -> str:
    now = datetime.now(MSK)
    return f"{now.year:04d}-{now.month:02d}"


async def finalize_task_billing(
    session: AsyncSession,
    task: PackagingTask,
    *,
    completed_by_user_id: uuid.UUID,
) -> None:
    if task.status != STATUS_DONE:
        return
    if task.completed_by_user_id is not None:
        return
    units = sum(int(ln.qty_packed_in_task) for ln in task.lines)
    user = await session.get(User, completed_by_user_id)
    rate = int(user.packaging_rate_kopecks) if user is not None else 0
    task.completed_by_user_id = completed_by_user_id
    task.completed_at = datetime.now(UTC)
    task.billing_units_packed = units
    task.billing_rate_kopecks = rate
    task.billing_earned_kopecks = units * rate


async def aggregate_staff_billing(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    staff_user_ids: list[uuid.UUID],
    billing_month: str,
) -> dict[uuid.UUID, StaffPackagingBillingTotals]:
    if not staff_user_ids:
        return {}
    year, month = parse_billing_month(billing_month)
    start_utc, end_utc = month_bounds_msk(year, month)
    stmt = (
        select(
            PackagingTask.completed_by_user_id,
            func.coalesce(func.sum(PackagingTask.billing_units_packed), 0),
            func.coalesce(func.sum(PackagingTask.billing_earned_kopecks), 0),
        )
        .where(
            PackagingTask.tenant_id == tenant_id,
            PackagingTask.status == STATUS_DONE,
            PackagingTask.completed_by_user_id.in_(staff_user_ids),
            PackagingTask.completed_at >= start_utc,
            PackagingTask.completed_at < end_utc,
        )
        .group_by(PackagingTask.completed_by_user_id)
    )
    rows = (await session.execute(stmt)).all()
    out: dict[uuid.UUID, StaffPackagingBillingTotals] = {
        uid: StaffPackagingBillingTotals(units_packed=0, earned_kopecks=0)
        for uid in staff_user_ids
    }
    for user_id, units, earned in rows:
        if user_id is None:
            continue
        out[user_id] = StaffPackagingBillingTotals(
            units_packed=int(units),
            earned_kopecks=int(earned),
        )
    return out


async def update_staff_packaging_rate(
    session: AsyncSession,
    *,
    acting_user: User,
    staff_user_id: uuid.UUID,
    rate_rub: Decimal,
) -> User:
    if acting_user.role != FULFILLMENT_ADMIN:
        raise PermissionError("forbidden")
    if rate_rub < 0:
        raise ValueError("invalid_rate")
    user = await session.get(User, staff_user_id)
    if user is None or user.tenant_id != acting_user.tenant_id:
        raise LookupError("user_not_found")
    if user.role != FULFILLMENT_STAFF:
        raise PermissionError("not_staff_user")
    user.packaging_rate_kopecks = rub_to_kopecks(rate_rub)
    await session.commit()
    await session.refresh(user)
    return user
