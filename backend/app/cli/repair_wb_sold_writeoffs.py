"""WMS-503: repair explicitly reviewed historical WB sold write-offs, once.

No discovery predicate is used to select writes. Prepare takes reviewed ledger IDs,
freezes their inventory evidence, and apply requires the exact manifest SHA256.
This maintenance command deliberately does not publish stock to a marketplace.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.base import Base
from app.models.document_event import DocumentEvent
from app.models.fbs_order import FbsOrder
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_count import InventoryCount, InventoryCountLine
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.storage_location import StorageLocation

REPAIR_TYPE = "fbs_shipment"
REPAIR_NAMESPACE = uuid.UUID("f36e8ad0-5afc-4b52-b2fd-e4d142e50300")
CUTOFF = datetime(2026, 9, 5, tzinfo=UTC)
START = datetime(2026, 9, 1, tzinfo=UTC)
SOURCE_MODES = {"forced_negative", "manual_pick", "sorting_loose", "storage_loose"}


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ledger_id: uuid.UUID
    action: Literal["restore", "absorbed_by_inventory_count"] = "restore"
    evidence: str = Field(min_length=20)
    count_line_id: uuid.UUID | None = None
    packed_quantity: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def check_action(self) -> Selection:
        if self.action == "absorbed_by_inventory_count":
            if self.count_line_id is None or self.packed_quantity:
                raise ValueError("absorbed rows require count_line_id and no packed restoration")
        elif self.count_line_id is not None:
            raise ValueError("restore rows cannot name an absorbing count")
        return self


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: Literal["WMS-503"] = "WMS-503"
    version: Literal[1] = 1
    selections: list[Selection] = Field(min_length=1)
    snapshot: dict[str, Any]

    @model_validator(mode="after")
    def check_unique(self) -> Manifest:
        ids = [row.ledger_id for row in self.selections]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate ledger_id")
        return self


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def manifest_sha256(manifest: Manifest) -> str:
    return hashlib.sha256(canonical(manifest.model_dump(mode="json")).encode()).hexdigest()


def _row(row: Base) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in inspect(type(row)).columns:
        value = getattr(row, column.key)
        if isinstance(value, uuid.UUID):
            value = str(value)
        elif isinstance(value, datetime):
            value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
            value = value.isoformat()
        elif isinstance(value, date):
            value = value.isoformat()
        result[column.key] = value
    return result


def _time(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def reversal_id(ledger_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(REPAIR_NAMESPACE, f"WMS-503:{ledger_id}")


def audit_id(ledger_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(REPAIR_NAMESPACE, f"WMS-503:audit:{ledger_id}")


async def snapshot(session: AsyncSession, selections: list[Selection]) -> dict[str, Any]:
    ids = [selection.ledger_id for selection in selections]
    ledgers = list(
        (
            await session.scalars(
                select(FbsShipmentReversalLedger)
                .where(FbsShipmentReversalLedger.id.in_(ids))
                .order_by(FbsShipmentReversalLedger.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    if len(ledgers) != len(ids):
        raise ValueError("selected ledger missing or duplicated")
    product_ids = sorted({row.product_id for row in ledgers}, key=str)
    order_ids = [row.fbs_order_id for row in ledgers]
    orders = list(
        (
            await session.scalars(
                select(FbsOrder)
                .where(FbsOrder.id.in_(order_ids))
                .order_by(FbsOrder.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    supply_ids = [row.supply_id for row in orders if row.supply_id is not None]
    result: dict[str, Any] = {
        "ledgers": [_row(row) for row in ledgers],
        "orders": [_row(row) for row in orders],
    }
    for name, model, clause in (
        ("products", Product, Product.id.in_(product_ids)),
        ("balances", InventoryBalance, InventoryBalance.product_id.in_(product_ids)),
        ("movements", InventoryMovement, InventoryMovement.product_id.in_(product_ids)),
        ("counts", InventoryCountLine, InventoryCountLine.product_id.in_(product_ids)),
        ("supplies", FbsSupply, FbsSupply.id.in_(supply_ids)),
    ):
        rows = (
            await session.scalars(
                select(model)
                .where(clause)
                .order_by(model.id)
                .execution_options(populate_existing=True)
            )
        ).all()
        result[name] = [_row(row) for row in rows]
    counts = (
        await session.scalars(
            select(InventoryCount)
            .where(InventoryCount.id.in_([uuid.UUID(row["count_id"]) for row in result["counts"]]))
            .order_by(InventoryCount.id)
            .execution_options(populate_existing=True)
        )
    ).all()
    result["count_documents"] = [_row(row) for row in counts]
    return result


async def prepare(session: AsyncSession, selections: list[Selection]) -> Manifest:
    manifest = Manifest(selections=selections, snapshot=await snapshot(session, selections))
    await _validate(session, manifest)
    return manifest


async def _validate(session: AsyncSession, manifest: Manifest) -> None:
    for choice in manifest.selections:
        ledger = await session.get(FbsShipmentReversalLedger, choice.ledger_id)
        if ledger is None:
            raise ValueError("ledger missing")
        order = await session.get(FbsOrder, ledger.fbs_order_id)
        movement = await session.get(InventoryMovement, ledger.shipment_movement_id)
        product = await session.get(Product, ledger.product_id)
        location = await session.get(StorageLocation, ledger.storage_location_id)
        if order is None or movement is None or product is None or location is None:
            raise ValueError(f"incomplete references: {ledger.id}")
        if ledger.reversed_at is not None or ledger.reversal_movement_id is not None:
            raise ValueError(f"already reversed before this repair: {ledger.id}")
        if not (
            ledger.tenant_id
            == order.tenant_id
            == movement.tenant_id
            == product.tenant_id
            == location.tenant_id
            and ledger.product_id == order.product_id == movement.product_id
            and order.seller_id == product.seller_id == movement.seller_id
            and ledger.storage_location_id == movement.storage_location_id
            and location.warehouse_id == movement.warehouse_id
            and ledger.container_id == movement.container_id
            and ledger.container_kind == movement.container_kind
        ):
            raise ValueError(f"tenant/seller/product/source mismatch: {ledger.id}")
        if not (
            order.marketplace == "wb"
            and movement.movement_type == "fbs_shipment"
            and movement.actor_user_id is None
            and ledger.written_off_by_user_id is None
            and ledger.wb_operation_id is None
            and ledger.quantity == 1
            and movement.quantity_delta == -1
            and START <= _time(movement.created_at) < CUTOFF
            and _time(ledger.created_at) == _time(movement.created_at)
            and ledger.written_off_at is not None
            and ledger.source_mode in SOURCE_MODES
        ):
            raise ValueError(f"not a historical automatic unit: {ledger.id}")
        if choice.packed_quantity > ledger.quantity:
            raise ValueError("packed restoration exceeds shipment")
        later_counts = list(
            (
                await session.execute(
                    select(InventoryCountLine, InventoryCount)
                    .join(InventoryCount, InventoryCount.id == InventoryCountLine.count_id)
                    .where(
                        InventoryCount.tenant_id == ledger.tenant_id,
                        InventoryCount.status == "posted",
                        InventoryCount.posted_at > movement.created_at,
                        InventoryCountLine.actual_quantity.is_not(None),
                        InventoryCountLine.posted_delta.is_not(None),
                        InventoryCountLine.product_id == ledger.product_id,
                        InventoryCountLine.storage_location_id == ledger.storage_location_id,
                        InventoryCountLine.container_kind == ledger.container_kind,
                        InventoryCountLine.container_id == ledger.container_id,
                    )
                )
            ).all()
        )
        if choice.action == "restore" and later_counts:
            raise ValueError(f"later physical recount requires absorption review: {ledger.id}")
        if order.supply_id is not None:
            supply = await session.get(FbsSupply, order.supply_id)
            if supply is None or supply.tenant_id != ledger.tenant_id:
                raise ValueError("invalid supply scope")
            if (
                choice.action == "restore"
                and supply.source == "wms"
                and supply.delivered_at is not None
            ):
                raise ValueError(
                    f"locally delivered supply needs separate investigation: {ledger.id}"
                )
        if choice.action == "absorbed_by_inventory_count":
            line = await session.get(InventoryCountLine, choice.count_line_id)
            count = await session.get(InventoryCount, line.count_id) if line else None
            if not (
                line is not None
                and count is not None
                and count.tenant_id == ledger.tenant_id
                and count.status == "posted"
                and count.posted_at is not None
                and _time(count.posted_at) > _time(movement.created_at)
                and _time(count.created_at) > _time(movement.created_at)
                and line.actual_quantity is not None
                and line.posted_delta is not None
                and line.posted_delta == line.actual_quantity - line.expected_quantity
                and line.product_id == ledger.product_id
                and line.storage_location_id == ledger.storage_location_id
                and line.container_kind == ledger.container_kind
                and line.container_id == ledger.container_id
            ):
                raise ValueError(f"no matching completed physical recount: {ledger.id}")


async def _lock(session: AsyncSession, manifest: Manifest) -> None:
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        await session.execute(text("SET LOCAL statement_timeout = '60s'"))
    product_ids = [uuid.UUID(row["id"]) for row in manifest.snapshot["products"]]
    await session.execute(
        select(Product.id).where(Product.id.in_(product_ids)).order_by(Product.id).with_for_update()
    )
    ids = [choice.ledger_id for choice in manifest.selections]
    await session.execute(
        select(FbsShipmentReversalLedger.id)
        .where(FbsShipmentReversalLedger.id.in_(ids))
        .order_by(FbsShipmentReversalLedger.id)
        .with_for_update()
    )
    await session.execute(
        select(InventoryBalance.id)
        .where(InventoryBalance.product_id.in_(product_ids))
        .order_by(InventoryBalance.id)
        .with_for_update()
    )
    for model, rows in (
        (FbsOrder, manifest.snapshot["orders"]),
        (FbsSupply, manifest.snapshot["supplies"]),
        (InventoryCount, manifest.snapshot["count_documents"]),
        (InventoryCountLine, manifest.snapshot["counts"]),
    ):
        row_ids = [uuid.UUID(row["id"]) for row in rows]
        await session.execute(
            select(model.id).where(model.id.in_(row_ids)).order_by(model.id).with_for_update()
        )


async def repair(
    session: AsyncSession, manifest: Manifest, *, expected_sha256: str, apply: bool = False
) -> dict[str, Any]:
    """Caller owns transaction; exceptions must roll it back, including partial writes."""
    digest = manifest_sha256(manifest)
    if digest != expected_sha256:
        raise ValueError("manifest SHA256 mismatch")
    await _lock(session, manifest)
    current = await snapshot(session, manifest.selections)
    current_ledgers = {row["id"]: row for row in current["ledgers"]}
    completed = []
    for choice in manifest.selections:
        row = current_ledgers[str(choice.ledger_id)]
        if row["reversed_at"] is None:
            completed.append(False)
            continue
        audit = await session.get(DocumentEvent, audit_id(choice.ledger_id))
        if audit is None or audit.payload_json.get("manifest_sha256") != digest:
            raise ValueError("ledger reversed without this manifest's audit record")
        expected_id = str(reversal_id(choice.ledger_id)) if choice.action == "restore" else None
        if row["reversal_movement_id"] != expected_id:
            raise ValueError("ledger reversed by another operation")
        if choice.action == "restore":
            inverse = await session.get(InventoryMovement, uuid.UUID(expected_id))
            if inverse is None or not (
                inverse.quantity_delta == row["quantity"]
                and inverse.movement_type == REPAIR_TYPE
                and str(inverse.tenant_id) == row["tenant_id"]
                and str(inverse.product_id) == row["product_id"]
                and str(inverse.storage_location_id) == row["storage_location_id"]
                and str(inverse.transfer_group_id) == str(choice.ledger_id)
                and inverse.container_kind == row["container_kind"]
                and (str(inverse.container_id) if inverse.container_id else None)
                == row["container_id"]
            ):
                raise ValueError("existing correction does not match manifest")
        completed.append(True)
    if all(completed):
        return {"status": "already_applied", "sha256": digest, "ledgers": len(completed)}
    if any(completed):
        raise ValueError("partially applied manifest requires investigation")
    if canonical(current) != canonical(manifest.snapshot):
        raise ValueError("inventory evidence changed since manifest preparation")
    await _validate(session, manifest)
    balance_changes: dict[uuid.UUID, tuple[InventoryBalance, int, int]] = {}
    for choice in manifest.selections:
        if choice.action != "restore":
            continue
        ledger = await session.get(FbsShipmentReversalLedger, choice.ledger_id)
        assert ledger is not None
        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == ledger.tenant_id,
                InventoryBalance.product_id == ledger.product_id,
                InventoryBalance.storage_location_id == ledger.storage_location_id,
                InventoryBalance.container_kind == ledger.container_kind,
                InventoryBalance.container_id == ledger.container_id,
            )
        )
        if (
            balance is None
            or balance.quantity != balance.quantity_unpacked + balance.quantity_packed
        ):
            raise ValueError("missing or inconsistent balance requires investigation")
        movement_total = sum(
            row["quantity_delta"]
            for row in current["movements"]
            if row["tenant_id"] == str(balance.tenant_id)
            and row["product_id"] == str(balance.product_id)
            and row["storage_location_id"] == str(balance.storage_location_id)
            and row["container_kind"] == balance.container_kind
            and row["container_id"] == (str(balance.container_id) if balance.container_id else None)
        )
        if movement_total != balance.quantity:
            raise ValueError("balance/journal mismatch; possible previous silent repair")
        _, unpacked, packed = balance_changes.get(balance.id, (balance, 0, 0))
        balance_changes[balance.id] = (
            balance,
            unpacked + ledger.quantity - choice.packed_quantity,
            packed + choice.packed_quantity,
        )
    result: dict[str, Any] = {
        "status": "applied" if apply else "checked",
        "sha256": digest,
        "restored_units": sum(u + p for _, u, p in balance_changes.values()),
        "absorbed_units": sum(
            c.action == "absorbed_by_inventory_count" for c in manifest.selections
        ),
        "balances": [
            {
                "id": str(b.id),
                "before": b.quantity,
                "after": b.quantity + u + p,
                "unpacked_delta": u,
                "packed_delta": p,
            }
            for b, u, p in balance_changes.values()
        ],
    }
    if not apply:
        return result
    now = datetime.now(UTC)
    for choice in manifest.selections:
        ledger = await session.get(FbsShipmentReversalLedger, choice.ledger_id)
        assert ledger is not None
        ledger.reversed_at = now
        if choice.action == "restore":
            original = await session.get(InventoryMovement, ledger.shipment_movement_id)
            assert original is not None
            inverse = InventoryMovement(
                id=reversal_id(ledger.id),
                tenant_id=original.tenant_id,
                product_id=original.product_id,
                seller_id=original.seller_id,
                storage_location_id=original.storage_location_id,
                warehouse_id=original.warehouse_id,
                reporting_dimensions_legacy=original.reporting_dimensions_legacy,
                container_kind=original.container_kind,
                container_id=original.container_id,
                quantity_delta=ledger.quantity,
                movement_type=REPAIR_TYPE,
                transfer_group_id=ledger.id,
                actor_user_id=None,
                created_at=now,
            )
            session.add(inverse)
            await session.flush()
            ledger.reversal_movement_id = inverse.id
        session.add(
            DocumentEvent(
                id=audit_id(ledger.id),
                tenant_id=ledger.tenant_id,
                document_type="fbs_order",
                document_id=ledger.fbs_order_id,
                event_type="data_changed",
                source="system",
                actor_user_id=None,
                product_id=ledger.product_id,
                qty=ledger.quantity if choice.action == "restore" else 0,
                occurred_at=now,
                idempotency_key=f"WMS-503:{ledger.id}",
                payload_json={
                    "task": "WMS-503",
                    "manifest_sha256": digest,
                    "selection": choice.model_dump(mode="json"),
                    "original_movement_id": str(ledger.shipment_movement_id),
                    "reversal_movement_id": (
                        str(ledger.reversal_movement_id) if ledger.reversal_movement_id else None
                    ),
                },
            )
        )
    for balance, unpacked, packed in balance_changes.values():
        balance.quantity += unpacked + packed
        balance.quantity_unpacked += unpacked
        balance.quantity_packed += packed
        balance.updated_at = now
    await session.flush()
    return result


async def _main(args: argparse.Namespace) -> dict[str, Any]:
    async with SessionLocal() as session, session.begin():
        if args.prepare:
            selections = [
                Selection.model_validate(row) for row in json.loads(Path(args.prepare).read_text())
            ]
            manifest = await prepare(session, selections)
            Path(args.output).write_text(
                json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
            )
            return {
                "status": "prepared",
                "sha256": manifest_sha256(manifest),
                "manifest": args.output,
            }
        manifest = Manifest.model_validate_json(Path(args.manifest).read_text())
        return await repair(session, manifest, expected_sha256=args.sha256, apply=args.apply)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", help="JSON of independently reviewed Selection rows")
    group.add_argument("--manifest")
    parser.add_argument("--output")
    parser.add_argument("--sha256")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.prepare and (not args.output or args.apply):
        parser.error("--prepare requires --output and disallows --apply")
    if args.manifest and not args.sha256:
        parser.error("--manifest requires --sha256")
    print(json.dumps(asyncio.run(_main(args)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
