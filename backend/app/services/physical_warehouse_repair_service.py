"""Manifest based reclassification of legacy marketplace warehouses (WMS-516).

No new stock movement is recorded: the stock already exists. Every changed FK is
recorded, and deletions retain their original row for guarded rollback. Operational
commands run in one transaction; the caller commits both data and job status.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import (
    Connection,
    Date,
    DateTime,
    Numeric,
    Table,
    UniqueConstraint,
    Uuid,
    case,
    delete,
    func,
    insert,
    inspect,
    literal_column,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import ColumnElement, TextClause

from app.models import Base
from app.models.background_job import BackgroundJob

JOB_TYPE = "physical_warehouse_repair"
Row = dict[str, Any]


class WarehouseRepairError(Exception):
    pass


def _json(value: Any) -> Any:
    if isinstance(value, (uuid.UUID, date, datetime, Decimal)):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json(v) for v in value]
    return value


def _typed(table: Table, values: Row) -> Row:
    result = dict(values)
    for key, value in result.items():
        if value is None:
            continue
        kind = table.c[key].type
        if isinstance(kind, Uuid):
            result[key] = uuid.UUID(str(value))
        elif isinstance(kind, DateTime):
            result[key] = datetime.fromisoformat(str(value))
        elif isinstance(kind, Date):
            result[key] = date.fromisoformat(str(value))
        elif isinstance(kind, Numeric):
            result[key] = Decimal(str(value))
    return result


def _refs(table: Table, parent: str) -> list[str]:
    return sorted(fk.parent.name for fk in table.foreign_keys if fk.column.table.name == parent)


def _tables() -> list[Table]:
    included = {"warehouses"}
    while True:
        expanded = included | {
            t.name for t in Base.metadata.tables.values()
            if any(fk.column.table.name in included for fk in t.foreign_keys)
        }
        if expanded == included:
            break
        included = expanded
    included |= {"products", "stock_directions", "product_marketplace_links"}
    return [Base.metadata.tables[name] for name in sorted(included)]


async def _lock(session: AsyncSession) -> None:
    # Whole-table locks are deliberate maintenance locks: they also fence SQL
    # writers which do not take the service's warehouse/advisory locks. READs
    # remain possible and see the previous committed graph via MVCC.
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(text("SET LOCAL lock_timeout = '10s'"))
        names = ', '.join(f'"{t.name}"' for t in _tables())
        await session.execute(text(f"LOCK TABLE {names} IN SHARE ROW EXCLUSIVE MODE"))
    # Refuse an unrecognised deployed FK rather than letting CASCADE delete it.
    connection = await session.connection()

    def check_schema(sync_connection: Any) -> None:
        from app.db.physical_warehouse_guard import physical_graph

        inspector = inspect(sync_connection)
        graph = physical_graph(sync_connection)
        if set(graph) - {t.name for t in _tables()}:
            raise WarehouseRepairError("unrecognised_physical_descendant")
        for name, edges in graph.items():
            graph_table = Base.metadata.tables[name]
            known_edges = {
                (fk.parent.name, fk.column.table.name)
                for fk in graph_table.foreign_keys if fk.column.name == "id"
            }
            if set(edges) - known_edges:
                raise WarehouseRepairError(f"unrecognised_physical_fk:{name}")
        for name in inspector.get_table_names():
            for fk in inspector.get_foreign_keys(name):
                if fk["referred_table"] not in {"warehouses", "storage_locations"}:
                    continue
                table = Base.metadata.tables.get(name)
                if table is None or fk["constrained_columns"] != [
                    c for c in _refs(table, fk["referred_table"])
                    if c in fk["constrained_columns"]
                ]:
                    raise WarehouseRepairError(f"unrecognised_physical_fk:{name}")

    await connection.run_sync(check_schema)


async def _snapshot(
    session: AsyncSession, tenant_id: uuid.UUID, source: uuid.UUID, target: uuid.UUID | None,
) -> dict[str, list[Row]]:
    warehouse_ids = [source] + ([target] if target else [])
    tables = _tables()
    rows_by_table: dict[str, dict[str, Row]] = {t.name: {} for t in tables}
    extras = {"products", "stock_directions", "product_marketplace_links"}
    while True:
        changed = False
        for table in tables:
            predicates: list[ColumnElement[bool]] = []
            if table.name == "warehouses":
                predicates = [table.c.id.in_(warehouse_ids)]
            elif table.name in extras:
                predicates = [table.c.tenant_id == tenant_id]
            else:
                for fk in table.foreign_keys:
                    parent = fk.column.table.name
                    if fk.column.name != "id" or parent in extras or parent not in rows_by_table:
                        continue
                    ids = [uuid.UUID(key) for key in rows_by_table[parent]]
                    if ids:
                        predicates.append(fk.parent.in_(ids))
            if not predicates:
                continue
            rows = (await session.execute(select(table).where(or_(*predicates)))).mappings().all()
            for row in rows:
                encoded = _json(dict(row))
                key = encoded["id"]
                if key not in rows_by_table[table.name]:
                    rows_by_table[table.name][key] = encoded
                    changed = True
        if not changed:
            break
    return {name: sorted(rows.values(), key=lambda r: r["id"])
            for name, rows in rows_by_table.items()}


def _fingerprint(snapshot: dict[str, list[Row]]) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


def _summary(snapshot: dict[str, list[Row]]) -> Row:
    products = {p["id"]: p for p in snapshot["products"]}
    locations = {loc["id"]: loc for loc in snapshot["storage_locations"]}
    totals: dict[str, Row] = {}
    for balance in snapshot["inventory_balances"]:
        product = products.get(balance["product_id"], {})
        seller = product.get("seller_id")
        warehouse = locations[balance["storage_location_id"]]["warehouse_id"]
        key = f'{warehouse}/{seller}/{balance["product_id"]}'
        row = totals.setdefault(key, {
            "warehouse_id": warehouse, "seller_id": seller,
            "product_id": balance["product_id"], "on_hand": 0,
            "boxed": 0, "loose": 0,
        })
        quantity = balance["quantity"]
        row["on_hand"] += quantity
        row["boxed" if balance["container_id"] else "loose"] += quantity
    reserved = {
        name: sum(int(row.get("quantity", 0)) for row in snapshot.get(name, []))
        for name in ("inventory_reservations", "fbs_order_reservations",
                     "fbs_order_product_reservations", "marketplace_unload_reservations")
    }
    return {
        "references": {k: len(v) for k, v in snapshot.items() if k != "products"},
        "stock": list(totals.values()), "reserved_by_table": reserved,
        "on_hand": sum(row["on_hand"] for row in totals.values()),
        "container_rows": len(snapshot.get("warehouse_boxes", [])),
    }


async def _summary_with_free(
    session: AsyncSession, tenant_id: uuid.UUID, snapshot: dict[str, list[Row]],
) -> Row:
    from app.services.fbs_stock_availability_service import fbs_stock_breakdown_by_product

    summary = _summary(snapshot)
    for warehouse in snapshot["warehouses"]:
        stock = [row for row in summary["stock"] if row["warehouse_id"] == warehouse["id"]]
        breakdown = await fbs_stock_breakdown_by_product(
            session, tenant_id, uuid.UUID(warehouse["id"]),
            [uuid.UUID(row["product_id"]) for row in stock],
        )
        for row in stock:
            value = breakdown[uuid.UUID(row["product_id"])]
            row["reserved"] = value.reserved
            row["free"] = value.free
    return summary


def _plan(
    snapshot: dict[str, list[Row]], tenant: str, source: str, target: str | None,
) -> tuple[list[Row], list[str]]:
    blockers: list[str] = []
    warehouses = {w["id"]: w for w in snapshot["warehouses"]}
    old, new = warehouses.get(source), warehouses.get(target or "")
    if not old or old["tenant_id"] != tenant:
        blockers.append("source_not_found_in_tenant")
    elif old["is_operational"] or not (
        old["code"].lower() == "fbs-wb" or old["code"].lower().startswith("fbs-wb-")
        or old["name"].lower() == "fbs wb" or old["name"].lower().startswith("fbs wb ")
    ):
        blockers.append("source_is_not_legacy_marketplace_warehouse")
    if (not new or not new["is_operational"] or new["tenant_id"] != tenant or source == target
            or new["code"].lower() in {"__defect__", "fbs-wb"}
            or new["code"].lower().startswith("fbs-wb-")):
        blockers.append("physical_target_required: provide explicit mapping if multiple warehouses")
    for name, rows in snapshot.items():
        if any(r.get("tenant_id", tenant) != tenant for r in rows):
            blockers.append(f"cross_tenant_reference:{name}")
        owned_products = {p["id"] for p in snapshot["products"]}
        if any(r.get("product_id") and r["product_id"] not in owned_products for r in rows):
            blockers.append(f"cross_tenant_product:{name}")
    if blockers:
        return [], blockers

    locations = snapshot["storage_locations"]
    source_locations = [loc for loc in locations if loc["warehouse_id"] == source]
    target_locations = {loc["code"]: loc for loc in locations if loc["warehouse_id"] == target}
    location_map: dict[str, str] = {}
    removed_locations: set[str] = set()
    for loc in source_locations:
        collision = target_locations.get(loc["code"])
        if collision:
            if loc["code"] != "__SORTING__" or collision["deleted_at"] is not None:
                blockers.append(f'location_code_collision:{loc["id"]}')
            else:
                location_map[loc["id"]] = collision["id"]
                removed_locations.add(loc["id"])
        else:
            location_map[loc["id"]] = loc["id"]

    patches: list[Row] = []
    deleted_balances: set[str] = set()
    projected: dict[str, list[Row]] = {}
    for table in _tables():
        name = table.name
        projected[name] = []
        for row in snapshot[name]:
            if name == "warehouses" and row["id"] == source:
                continue
            if name == "storage_locations" and row["id"] in removed_locations:
                continue
            new_row = dict(row)
            for column in _refs(table, "warehouses"):
                if row[column] == source:
                    new_row[column] = target
            for column in _refs(table, "storage_locations"):
                if row[column] in location_map:
                    new_row[column] = location_map[row[column]]
            projected[name].append(new_row)

    # Merge only identical physical stock dimensions; seller is product ownership.
    balances: dict[tuple[Any, ...], Row] = {}
    for row in sorted(projected["inventory_balances"], key=lambda r: (
        r["storage_location_id"] in removed_locations, r["id"],
    )):
        key = (row["storage_location_id"], row["product_id"], row["container_id"])
        existing = balances.get(key)
        if existing:
            if existing["container_kind"] != row["container_kind"]:
                blockers.append(f'container_kind_collision:{row["id"]}')
            for quantity in ("quantity", "quantity_unpacked", "quantity_packed"):
                existing[quantity] += row[quantity]
            deleted_balances.add(row["id"])
        else:
            balances[key] = row
    projected["inventory_balances"] = list(balances.values())

    for table in _tables():
        # Never silently merge two historical invoices, supplies or measurements.
        unique_sets = [list(c.columns.keys()) for c in table.constraints
                       if isinstance(c, UniqueConstraint)]
        for columns in unique_sets:
            seen: set[tuple[Any, ...]] = set()
            for row in projected[table.name]:
                key = tuple(row[c] for c in columns)
                if None in key:
                    continue
                if key in seen:
                    blockers.append(f'unique_collision:{table.name}:{",".join(columns)}')
                seen.add(key)
        before = {row["id"]: row for row in snapshot[table.name]}
        after = {row["id"]: row for row in projected[table.name]}
        for row_id, row in before.items():
            if row_id not in after:
                patches.append({"table": table.name, "id": row_id, "delete": row})
            elif row != after[row_id]:
                changed = {key: after[row_id][key] for key in row if row[key] != after[row_id][key]}
                # SQLAlchemy's automatic updated_at=now() is not part of a
                # reclassification. Preserve original document/event times.
                changed.update({c.name: row[c.name] for c in table.c if c.onupdate is not None})
                patches.append({"table": table.name, "id": row_id, "after": changed,
                                "before": {key: row[key] for key in changed}})
    return patches, sorted(set(blockers))


def _physical_quantities(snapshot: dict[str, list[Row]]) -> dict[tuple[Any, ...], tuple[int, ...]]:
    result: dict[tuple[Any, ...], tuple[int, ...]] = {}
    for row in snapshot["inventory_balances"]:
        key = (row["tenant_id"], row["product_id"], row["container_kind"], row["container_id"])
        before = result.get(key, (0, 0, 0))
        quantities = (row["quantity"], row["quantity_unpacked"], row["quantity_packed"])
        result[key] = tuple(a + b for a, b in zip(before, quantities, strict=True))
    return result


def _deployed_indexes(connection: Connection, table_name: str) -> list[Row]:
    return [dict(index) for index in inspect(connection).get_indexes(table_name)]


async def _index_blockers(session: AsyncSession, patches: list[Row]) -> list[str]:
    """Evaluate each actual SQL partial/expression index on the projected rows.

    PostgreSQL evaluates its own predicate and NULL semantics; no approximate
    Python interpretation of a partial index is used.
    """
    blockers = []
    for name in sorted({p["table"] for p in patches}):
        table = Base.metadata.tables[name]
        connection = await session.connection()
        deployed_indexes = await connection.run_sync(_deployed_indexes, name)
        known_indexes = {index.name for index in table.indexes}
        for deployed in deployed_indexes:
            if deployed.get("unique") and not deployed.get("duplicates_constraint") and (
                deployed["name"] not in known_indexes
            ):
                blockers.append(f"unrecognised_unique_index:{name}:{deployed['name']}")
        changes = [p for p in patches if p["table"] == name]
        deleted = [uuid.UUID(p["id"]) for p in changes if "delete" in p]
        columns = []
        for column in table.c:
            replacements = [
                (table.c.id == uuid.UUID(p["id"]), _typed(table, p["after"])[column.name])
                for p in changes if column.name in p.get("after", {})
            ]
            columns.append((case(*replacements, else_=column) if replacements else column)
                           .label(column.name))
        projected = select(*columns).where(table.c.id.not_in(deleted)).cte("projected")
        for index in table.indexes:
            if not index.unique:
                continue
            def replace(element: Any, source: Table = table, cte: Any = projected) -> Any:
                if getattr(element, "table", None) is source:
                    return cte.c[element.name]
                return None

            expressions = [
                literal_column(expression.text) if isinstance(expression, TextClause)
                else visitors.replacement_traverse(
                    cast(ColumnElement[Any], expression), {}, cast(Any, replace))
                for expression in index.expressions
            ]
            dialect_options = index.dialect_options[session.get_bind().dialect.name]
            predicate = dialect_options.get("where")
            stmt = select(*expressions).select_from(projected)
            if predicate is not None:
                stmt = stmt.where(visitors.replacement_traverse(
                    cast(ColumnElement[bool], predicate), {}, cast(Any, replace)))
            if not dialect_options.get("nulls_not_distinct", False):
                stmt = stmt.where(*(expression.is_not(None) for expression in expressions))
            stmt = stmt.group_by(*expressions).having(func.count() > 1).limit(1)
            if (await session.execute(stmt)).first() is not None:
                blockers.append(f"unique_index_collision:{name}:{index.name}")
    return blockers


async def prepare(
    session: AsyncSession, *, run_id: uuid.UUID, tenant_id: uuid.UUID,
    source_id: uuid.UUID, target_id: uuid.UUID | None = None,
) -> Row:
    await _lock(session)
    existing = await session.get(BackgroundJob, run_id)
    if existing:
        if existing.job_type != JOB_TYPE or existing.tenant_id != tenant_id or (
            existing.payload_json or {}
        ).get("source_id") != str(source_id) or (
            target_id is not None
            and (existing.payload_json or {}).get("target_id") != str(target_id)
        ):
            raise WarehouseRepairError("run_id_scope_conflict")
        return report(existing)
    warehouses = Base.metadata.tables["warehouses"]
    if target_id is None:
        ids = list((await session.scalars(select(warehouses.c.id).where(
            warehouses.c.tenant_id == tenant_id, warehouses.c.is_operational.is_(True),
            func.lower(warehouses.c.code).not_in(["__defect__", "fbs-wb"]),
            ~func.lower(warehouses.c.code).like("fbs-wb-%"),
        ))).all())
        if len(ids) == 1:
            target_id = ids[0]
    snapshot = await _snapshot(session, tenant_id, source_id, target_id)
    patches, blockers = _plan(snapshot, str(tenant_id), str(source_id), str(target_id))
    if not blockers:
        blockers.extend(await _index_blockers(session, patches))
    job = BackgroundJob(
        id=run_id, tenant_id=tenant_id, job_type=JOB_TYPE,
        status="blocked" if blockers else "prepared",
        payload_json={
            "source_id": str(source_id), "target_id": str(target_id) if target_id else None,
            "fingerprint": _fingerprint(snapshot), "patches": patches,
            "before": await _summary_with_free(session, tenant_id, snapshot), "blockers": blockers,
        },
    )
    session.add(job)
    await session.flush()
    return report(job)


def report(job: BackgroundJob) -> Row:
    payload = job.payload_json or {}
    # Do not print original rows: only IDs, counts and quantities leave this service.
    return {
        "run_id": str(job.id), "tenant_id": str(job.tenant_id), "status": job.status,
        "source_id": payload.get("source_id"), "target_id": payload.get("target_id"),
        "fingerprint": payload.get("fingerprint"), "before": payload.get("before"),
        "blockers": payload.get("blockers", []), "result": job.result_json,
    }


async def _load(session: AsyncSession, run_id: uuid.UUID) -> BackgroundJob:
    job = await session.scalar(select(BackgroundJob).where(
        BackgroundJob.id == run_id, BackgroundJob.job_type == JOB_TYPE,
    ).with_for_update().execution_options(populate_existing=True))
    if job is None:
        raise WarehouseRepairError("run_not_found")
    return job


async def _repair_mode(session: AsyncSession, run_id: uuid.UUID) -> None:
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(text("SELECT set_config('wms.warehouse_repair', :run, true)"),
                              {"run": str(run_id)})


async def apply(session: AsyncSession, run_id: uuid.UUID) -> Row:
    await _lock(session)
    job = await _load(session, run_id)
    if job.status == "completed":
        return report(job)
    if job.status != "prepared":
        raise WarehouseRepairError(f"run_not_prepared:{job.status}")
    payload = job.payload_json or {}
    source, target = uuid.UUID(payload["source_id"]), uuid.UUID(payload["target_id"])
    snapshot = await _snapshot(session, job.tenant_id, source, target)
    if _fingerprint(snapshot) != payload["fingerprint"]:
        job.status = "stale"
        job.result_json = {"blocker": "snapshot_changed: prepare a new run",
                           "current": _summary(snapshot), "fingerprint": _fingerprint(snapshot)}
        await session.flush()
        return report(job)
    job.status = "running"
    await session.flush()
    await _repair_mode(session, run_id)
    patches = payload["patches"]
    # Delete colliding balance rows first, then update the surviving rows. FK
    # locations and warehouse deletion wait until all references have moved.
    for patch in patches:
        if "delete" in patch and patch["table"] == "inventory_balances":
            table = Base.metadata.tables[patch["table"]]
            await session.execute(delete(table).where(table.c.id == uuid.UUID(patch["id"])))
    for patch in patches:
        if "after" in patch:
            table = Base.metadata.tables[patch["table"]]
            await session.execute(update(table).where(table.c.id == uuid.UUID(patch["id"]))
                                  .values(**_typed(table, patch["after"])))
    for name in ("storage_locations", "warehouses"):
        for patch in patches:
            if patch["table"] == name and "delete" in patch:
                table = Base.metadata.tables[name]
                await session.execute(delete(table).where(table.c.id == uuid.UUID(patch["id"])))
    after = await _snapshot(session, job.tenant_id, source, target)
    before_summary, after_summary = _summary(snapshot), _summary(after)
    if _physical_quantities(snapshot) != _physical_quantities(after) or (
        before_summary["reserved_by_table"] != after_summary["reserved_by_table"]
    ):
        raise WarehouseRepairError("quantity_conservation_failed")
    job.status = "completed"
    source_locations = {loc["id"] for loc in snapshot["storage_locations"]
                        if loc["warehouse_id"] == str(source)}
    affected_products = sorted({row["product_id"] for row in snapshot["inventory_balances"]
                               if row["storage_location_id"] in source_locations
                               and row["quantity"] != 0})
    job.result_json = {
        "after": await _summary_with_free(session, job.tenant_id, after),
        "fingerprint": _fingerprint(after),
        "publication": "pending_existing_rules" if affected_products else "not_needed",
        "product_ids": affected_products,
    }
    await session.flush()
    return report(job)


async def verify(session: AsyncSession, run_id: uuid.UUID) -> Row:
    job = await _load(session, run_id)
    payload = job.payload_json or {}
    snapshot = await _snapshot(
        session, job.tenant_id, uuid.UUID(payload["source_id"]),
        uuid.UUID(payload["target_id"]) if payload.get("target_id") else None,
    )
    result = report(job)
    result["current"] = await _summary_with_free(session, job.tenant_id, snapshot)
    result["matches_committed_snapshot"] = (
        _fingerprint(snapshot) == (job.result_json or {}).get("fingerprint")
    )
    result["source_exists"] = any(w["id"] == payload["source_id"] for w in snapshot["warehouses"])
    return result


async def rollback(session: AsyncSession, run_id: uuid.UUID) -> Row:
    await _lock(session)
    job = await _load(session, run_id)
    if job.status == "rolled_back":
        return report(job)
    if job.status != "completed":
        raise WarehouseRepairError("only_completed_run_can_be_rolled_back")
    if (job.result_json or {}).get("publication_started"):
        raise WarehouseRepairError("rollback_blocked_after_publication: use forward reconciliation")
    payload = job.payload_json or {}
    source, target = uuid.UUID(payload["source_id"]), uuid.UUID(payload["target_id"])
    current = await _snapshot(session, job.tenant_id, source, target)
    if _fingerprint(current) != (job.result_json or {}).get("fingerprint"):
        raise WarehouseRepairError("rollback_blocked_by_later_changes: reconcile manifest")
    job.status = "running"
    await session.flush()
    await _repair_mode(session, run_id)
    patches = payload["patches"]
    for name in ("warehouses", "storage_locations"):
        for patch in patches:
            if patch["table"] == name and "delete" in patch:
                table = Base.metadata.tables[name]
                await session.execute(insert(table).values(**_typed(table, patch["delete"])))
    for patch in patches:
        if "before" in patch:
            table = Base.metadata.tables[patch["table"]]
            await session.execute(update(table).where(table.c.id == uuid.UUID(patch["id"]))
                                  .values(**_typed(table, patch["before"])))
    for patch in patches:
        if patch["table"] == "inventory_balances" and "delete" in patch:
            table = Base.metadata.tables[patch["table"]]
            await session.execute(insert(table).values(**_typed(table, patch["delete"])))
    restored = await _snapshot(session, job.tenant_id, source, target)
    if _fingerprint(restored) != payload["fingerprint"]:
        raise WarehouseRepairError("rollback_manifest_mismatch")
    job.status = "rolled_back"
    await session.flush()
    return report(job)
