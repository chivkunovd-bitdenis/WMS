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
from app.models.product_dimension_event import ProductDimensionEvent
from app.models.seller import Seller


@dataclass(frozen=True)
class ProductReference:
    table: str
    column: str


@dataclass(frozen=True)
class ProductReferenceUniqueRule:
    table: str
    column: str
    constraint: str
    columns: tuple[str, ...]
    policy: str


@dataclass(frozen=True)
class ReferenceConflict:
    table: str
    column: str
    constraint: str
    policy: str


@dataclass
class PairReport:
    chrt_id: int
    keeper_id: str
    duplicate_id: str
    status: str
    reason: str | None = None
    references_before: dict[str, int] = field(default_factory=dict)
    references_moved: dict[str, int] = field(default_factory=dict)
    unique_conflicts: list[dict[str, str]] = field(default_factory=list)


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


def _discover_product_reference_unique_rules(
    sync_connection: object,
) -> list[ProductReferenceUniqueRule]:
    inspector = cast(Inspector, inspect(sync_connection))
    references = _discover_product_references(sync_connection)
    rules: set[tuple[str, str, str, tuple[str, ...], str]] = set()
    for reference in references:
        candidates = [
            *inspector.get_unique_constraints(reference.table),
            *(
                index
                for index in inspector.get_indexes(reference.table)
                if index.get("unique")
            ),
        ]
        for candidate in candidates:
            raw_columns = cast(list[object], candidate.get("column_names") or [])
            columns = tuple(str(value) for value in raw_columns if value is not None)
            if reference.column not in columns:
                continue
            constraint = str(candidate.get("name") or "unnamed_unique_constraint")
            policy = (
                "merge_dimension_history"
                if reference.table == "product_dimension_events"
                else "skip_pair"
            )
            rules.add(
                (
                    reference.table,
                    reference.column,
                    constraint,
                    columns,
                    policy,
                )
            )
    return [
        ProductReferenceUniqueRule(*values)
        for values in sorted(rules)
    ]


async def discover_product_references(session: AsyncSession) -> list[ProductReference]:
    connection = await session.connection()
    return await connection.run_sync(_discover_product_references)


async def discover_product_reference_unique_rules(
    session: AsyncSession,
) -> list[ProductReferenceUniqueRule]:
    connection = await session.connection()
    return await connection.run_sync(_discover_product_reference_unique_rules)


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


def _constraint_name_from_integrity_error(
    exc: IntegrityError,
    *,
    reference: ProductReference,
    unique_rules: list[ProductReferenceUniqueRule],
) -> str:
    original = getattr(exc, "orig", None)
    diagnostic = getattr(original, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    if constraint_name:
        return str(constraint_name)

    message = str(original or exc)
    marker = "UNIQUE constraint failed:"
    failed_columns: set[str] = set()
    if marker in message:
        failed_columns = {
            part.strip().split(".")[-1]
            for part in message.split(marker, 1)[1].split(",")
            if part.strip()
        }
    candidates = [
        rule
        for rule in unique_rules
        if rule.table == reference.table and rule.column == reference.column
    ]
    if failed_columns:
        exact = [rule for rule in candidates if set(rule.columns) == failed_columns]
        if len(exact) == 1:
            return exact[0].constraint
    if len(candidates) == 1:
        return candidates[0].constraint
    return "database_unique_constraint"


async def _probe_reference_conflicts(
    session: AsyncSession,
    *,
    references: list[ProductReference],
    unique_rules: list[ProductReferenceUniqueRule],
    keeper_id: uuid.UUID,
    duplicate_id: uuid.UUID,
) -> list[ReferenceConflict]:
    """Try the real reference UPDATE per table, rolling every probe back."""
    conflicts: list[ReferenceConflict] = []
    for reference in references:
        if reference.table == "product_dimension_events":
            continue
        table = _quoted(session, reference.table)
        column = _quoted(session, reference.column)
        savepoint = await session.begin_nested()
        try:
            await session.execute(
                text(
                    f"UPDATE {table} SET {column} = :keeper_id "
                    f"WHERE {column} = :duplicate_id"
                ).bindparams(
                    bindparam("keeper_id", type_=Uuid(as_uuid=True)),
                    bindparam("duplicate_id", type_=Uuid(as_uuid=True)),
                ),
                {"keeper_id": keeper_id, "duplicate_id": duplicate_id},
            )
        except IntegrityError as exc:
            await savepoint.rollback()
            conflicts.append(
                ReferenceConflict(
                    table=reference.table,
                    column=reference.column,
                    constraint=_constraint_name_from_integrity_error(
                        exc,
                        reference=reference,
                        unique_rules=unique_rules,
                    ),
                    policy="skip_pair",
                )
            )
        else:
            await savepoint.rollback()
    return conflicts


async def _merge_dimension_events(
    session: AsyncSession,
    *,
    keeper_id: uuid.UUID,
    duplicate_id: uuid.UUID,
) -> int:
    """Preserve every event while keeping dimension uniqueness valid."""
    keeper_events = list(
        (
            await session.execute(
                select(ProductDimensionEvent).where(
                    ProductDimensionEvent.product_id == keeper_id
                )
            )
        )
        .scalars()
        .all()
    )
    duplicate_events = list(
        (
            await session.execute(
                select(ProductDimensionEvent)
                .where(ProductDimensionEvent.product_id == duplicate_id)
                .order_by(ProductDimensionEvent.observed_at, ProductDimensionEvent.id)
            )
        )
        .scalars()
        .all()
    )
    keeper_has_applied = any(event.applied for event in keeper_events)
    keeper_wb_fingerprints = {
        event.fingerprint for event in keeper_events if event.source == "wb"
    }
    for event in duplicate_events:
        if event.applied:
            if keeper_has_applied:
                event.applied = False
            else:
                keeper_has_applied = True
        if event.source == "wb":
            if event.fingerprint in keeper_wb_fingerprints:
                event.source = "wb_merged_history"
            else:
                keeper_wb_fingerprints.add(event.fingerprint)
        event.product_id = keeper_id
    await session.flush()
    return len(duplicate_events)


async def _merge_pair(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    chrt_id: int,
    references: list[ProductReference],
    unique_rules: list[ProductReferenceUniqueRule],
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
    conflicts = await _probe_reference_conflicts(
        session,
        references=references,
        unique_rules=unique_rules,
        keeper_id=keeper.id,
        duplicate_id=duplicate.id,
    )
    if conflicts:
        report.status = "skipped"
        report.unique_conflicts = [asdict(conflict) for conflict in conflicts]
        first = conflicts[0]
        report.reason = f"unique_conflict:{first.table}:{first.constraint}"
        return report
    if not apply:
        return report

    try:
        moved_dimensions = await _merge_dimension_events(
            session,
            keeper_id=keeper.id,
            duplicate_id=duplicate.id,
        )
        if moved_dimensions:
            report.references_moved[
                "product_dimension_events.product_id"
            ] = moved_dimensions
        for reference in references:
            if reference.table == "product_dimension_events":
                continue
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
        if isinstance(exc, IntegrityError):
            report.reason = "unexpected_integrity_error_after_preflight"
        else:
            report.reason = str(exc)
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
        unique_rules = await discover_product_reference_unique_rules(session)
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
                    unique_rules=unique_rules,
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
        "unique_reference_rules": [asdict(item) for item in unique_rules],
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
