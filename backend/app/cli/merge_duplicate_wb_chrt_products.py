"""Merge duplicate WB products for one tenant and seller after safety checks.

Dry-run is the default. ``--apply`` requires ``--expected-pairs`` and processes
each duplicate chrtID atomically. Product references are discovered from live
database foreign-key metadata, not maintained as a partial hard-coded list.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, cast

from sqlalchemy import Uuid, bindparam, inspect, or_, select, text
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrderProduct
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_reservation import InventoryReservation
from app.models.product import Product
from app.models.seller import Seller


@dataclass(frozen=True)
class ProductReference:
    table: str
    column: str


@dataclass
class PairReport:
    chrt_id: int
    keeper_id: str
    duplicate_id: str
    status: str
    reason: str | None = None
    references_before: dict[str, int] = field(default_factory=dict)
    references_moved: dict[str, int] = field(default_factory=dict)


def _discover_product_references(sync_connection: object) -> list[ProductReference]:
    inspector = cast(Inspector, inspect(sync_connection))
    references: set[tuple[str, str]] = set()
    for table_name in inspector.get_table_names():
        for foreign_key in inspector.get_foreign_keys(table_name):
            if foreign_key.get("referred_table") != "products":
                continue
            referred = list(foreign_key.get("referred_columns") or [])
            constrained = list(foreign_key.get("constrained_columns") or [])
            for index, referred_column in enumerate(referred):
                if referred_column == "id" and index < len(constrained):
                    references.add((table_name, constrained[index]))
    return [
        ProductReference(table=table, column=column)
        for table, column in sorted(references)
    ]


async def discover_product_references(session: AsyncSession) -> list[ProductReference]:
    connection = await session.connection()
    return await connection.run_sync(_discover_product_references)


def _quoted(session: AsyncSession, identifier: str) -> str:
    return session.get_bind().dialect.identifier_preparer.quote(identifier)


async def _reference_counts(
    session: AsyncSession,
    references: list[ProductReference],
    product_id: uuid.UUID,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for reference in references:
        table = _quoted(session, reference.table)
        column = _quoted(session, reference.column)
        count = int(
            await session.scalar(
                text(f"SELECT count(*) FROM {table} WHERE {column} = :product_id").bindparams(
                    bindparam("product_id", type_=Uuid(as_uuid=True))
                ),
                {"product_id": product_id},
            )
            or 0
        )
        if count:
            counts[f"{reference.table}.{reference.column}"] = count
    return counts


async def _safety_reason(
    session: AsyncSession,
    product_ids: tuple[uuid.UUID, uuid.UUID],
    references: list[ProductReference],
) -> str | None:
    balance_count = int(
        await session.scalar(
            select(text("count(*)"))
            .select_from(InventoryBalance)
            .where(
                InventoryBalance.product_id.in_(product_ids),
                or_(
                    InventoryBalance.quantity != 0,
                    InventoryBalance.quantity_unpacked != 0,
                    InventoryBalance.quantity_packed != 0,
                ),
            )
        )
        or 0
    )
    if balance_count:
        return "nonzero_inventory_balance"
    reservation_count = int(
        await session.scalar(
            select(text("count(*)"))
            .select_from(InventoryReservation)
            .where(InventoryReservation.product_id.in_(product_ids))
        )
        or 0
    )
    if reservation_count:
        return "inventory_reservations_present"
    fbs_reserved_count = int(
        await session.scalar(
            select(text("count(*)"))
            .select_from(FbsOrderProduct)
            .where(
                FbsOrderProduct.product_id.in_(product_ids),
                FbsOrderProduct.reserved_quantity > 0,
            )
        )
        or 0
    )
    if fbs_reserved_count:
        return "fbs_product_reservations_present"
    for product_id in product_ids:
        reference_counts = await _reference_counts(session, references, product_id)
        if any("reservation" in key for key in reference_counts):
            return "product_reservations_present"
        if any("pick" in key for key in reference_counts):
            return "product_picks_present"
    movement_count = int(
        await session.scalar(
            select(text("count(*)"))
            .select_from(InventoryMovement)
            .where(InventoryMovement.product_id.in_(product_ids))
        )
        or 0
    )
    if movement_count:
        return "inventory_movements_present"
    return None


async def _merge_pair(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    chrt_id: int,
    references: list[ProductReference],
    apply: bool,
) -> PairReport:
    products = list(
        (
            await session.execute(
                select(Product)
                .where(
                    Product.tenant_id == tenant_id,
                    Product.seller_id == seller_id,
                    Product.wb_chrt_id == chrt_id,
                )
                .order_by(Product.created_at, Product.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if len(products) != 2:
        placeholder = str(products[0].id) if products else ""
        return PairReport(
            chrt_id=chrt_id,
            keeper_id=placeholder,
            duplicate_id="",
            status="skipped",
            reason=f"expected_two_products_found_{len(products)}",
        )
    keeper, duplicate = products
    report = PairReport(
        chrt_id=chrt_id,
        keeper_id=str(keeper.id),
        duplicate_id=str(duplicate.id),
        status="eligible" if not apply else "pending",
    )
    reason = await _safety_reason(
        session, (keeper.id, duplicate.id), references
    )
    report.references_before = await _reference_counts(session, references, duplicate.id)
    if reason is not None:
        report.status = "skipped"
        report.reason = reason
        return report
    if not apply:
        return report

    try:
        for reference in references:
            table = _quoted(session, reference.table)
            column = _quoted(session, reference.column)
            result = await session.execute(
                text(
                    f"UPDATE {table} SET {column} = :keeper_id "
                    f"WHERE {column} = :duplicate_id"
                ).bindparams(
                    bindparam("keeper_id", type_=Uuid(as_uuid=True)),
                    bindparam("duplicate_id", type_=Uuid(as_uuid=True)),
                ),
                {"keeper_id": keeper.id, "duplicate_id": duplicate.id},
            )
            moved = int(cast(Any, result).rowcount or 0)
            if moved:
                report.references_moved[
                    f"{reference.table}.{reference.column}"
                ] = moved
        remaining = await _reference_counts(session, references, duplicate.id)
        if remaining:
            raise ValueError("references_remain_after_update")
        await session.delete(duplicate)
        await session.flush()
        await session.commit()
    except (IntegrityError, ValueError) as exc:
        await session.rollback()
        report.status = "skipped"
        report.reason = type(exc).__name__
        report.references_moved = {}
        return report
    report.status = "merged"
    return report


async def run_merge(
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    apply: bool,
    expected_pairs: int | None,
) -> dict[str, object]:
    if apply and expected_pairs is None:
        raise ValueError("--apply requires --expected-pairs")
    async with SessionLocal() as session:
        seller = await session.get(Seller, seller_id)
        if seller is None or seller.tenant_id != tenant_id:
            raise ValueError("seller_not_found_in_tenant")
        duplicate_rows = (
            await session.execute(
                select(Product.wb_chrt_id)
                .where(
                    Product.tenant_id == tenant_id,
                    Product.seller_id == seller_id,
                    Product.wb_chrt_id.is_not(None),
                )
                .group_by(Product.wb_chrt_id)
                .having(text("count(*) > 1"))
                .order_by(Product.wb_chrt_id)
            )
        ).scalars()
        chrt_ids = [int(value) for value in duplicate_rows if value is not None]
        references = await discover_product_references(session)
        await session.rollback()

    if apply and len(chrt_ids) != expected_pairs:
        raise ValueError(
            f"expected {expected_pairs} duplicate pairs, found {len(chrt_ids)}"
        )

    pair_reports: list[PairReport] = []
    for chrt_id in chrt_ids:
        async with SessionLocal() as session:
            pair_reports.append(
                await _merge_pair(
                    session,
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    chrt_id=chrt_id,
                    references=references,
                    apply=apply,
                )
            )
            if not apply:
                await session.rollback()

    verification: list[dict[str, object]] = []
    async with SessionLocal() as session:
        for pair_report in pair_reports:
            remaining_ids = list(
                (
                    await session.execute(
                        select(Product.id).where(
                            Product.tenant_id == tenant_id,
                            Product.seller_id == seller_id,
                            Product.wb_chrt_id == pair_report.chrt_id,
                        )
                    )
                ).scalars()
            )
            duplicate_uuid = (
                uuid.UUID(pair_report.duplicate_id)
                if pair_report.duplicate_id
                else None
            )
            verification.append(
                {
                    "chrt_id": pair_report.chrt_id,
                    "remaining_product_ids": [str(value) for value in remaining_ids],
                    "duplicate_product_exists": (
                        duplicate_uuid in remaining_ids
                        if duplicate_uuid is not None
                        else None
                    ),
                    "duplicate_references_remaining": (
                        await _reference_counts(session, references, duplicate_uuid)
                        if duplicate_uuid is not None
                        else {}
                    ),
                }
            )

    return {
        "mode": "apply" if apply else "dry-run",
        "tenant_id": str(tenant_id),
        "seller_id": str(seller_id),
        "duplicate_chrt_ids_found": len(chrt_ids),
        "foreign_key_references_discovered": [asdict(item) for item in references],
        "pairs": [asdict(item) for item in pair_reports],
        "verification": verification,
        "merged": sum(item.status == "merged" for item in pair_reports),
        "eligible": sum(item.status == "eligible" for item in pair_reports),
        "skipped": sum(item.status == "skipped" for item in pair_reports),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=uuid.UUID, required=True)
    parser.add_argument("--seller-id", type=uuid.UUID, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-pairs", type=int)
    args = parser.parse_args()
    result = asyncio.run(
        run_merge(
            tenant_id=args.tenant_id,
            seller_id=args.seller_id,
            apply=args.apply,
            expected_pairs=args.expected_pairs,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
