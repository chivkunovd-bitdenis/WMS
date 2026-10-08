#!/usr/bin/env python3
"""WMS-705: export a read-only production snapshot, apply it only on staging.

Export runs locally with SSH access; apply runs in the Railway WMS container.
No database URL or password is accepted as an argument. Apply reads a JSON
envelope from stdin: {"snapshot": <export JSON>, "passwords": {slug: password}}.
Passwords exist only in memory and are never returned by this program.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import os
import re
import subprocess
import sys
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ID = "c28e681d-4535-4c96-ac97-c7b600a7f8e4"
STAGING_ENVIRONMENT_ID = "58a08b66-1290-45a2-8737-e3d7408389e5"
STAGING_POSTGRES_HOST = "postgres.railway.internal"
SOURCES = {
    "82b36645-8662-497f-9631-a0743994632c": ("stage-artmaks", "ArtMaks — тест"),
    "5fbf633c-3ea9-4c29-b5f5-f549b122bcae": ("stage-imperiya-lvova", "Империя Львова — тест"),
    "d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe": ("stage-avpack", "AV Pack — тест"),
}
KEEP_FBS = {"fbs_warehouse_bindings", "fbs_binding_stock_pools"}
KEEP_MARKING = {"marking_pools", "marking_pool_products"}
EXCLUDED = {
    "alembic_version", "operation_fact_cutover", "marketplace_accounts",
    "seller_marking_credentials", "seller_wildberries_credentials",
    "print_connections", "background_jobs", "notifications", "assistant_messages",
    "developer_requests", "document_event", "document_events", "ff_staff_permissions",
    "seller_staff_permissions",
    "seller_shop_delegations", "wb_order_price_snapshots", "kiz_reprints",
    "billing_invoice_v2_idempotency",
}
SECRET_NAME = re.compile(r"password|secret|token|api_key|encrypted|credential", re.I)
UUID_TEXT = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$", re.I)
EMAIL_TEXT = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)

# Only schema information is fetched; no account/credential value is selected.
SCHEMA_SQL = """
SELECT json_build_object(
 'revision',(SELECT version_num FROM public.alembic_version),
 'tables',(SELECT json_object_agg(table_name,columns) FROM (
   SELECT table_name,json_agg(json_build_object(
    'name',column_name,'type',udt_name,'nullable',is_nullable='YES')
    ORDER BY ordinal_position) columns
   FROM information_schema.columns WHERE table_schema='public'
   GROUP BY table_name) x),
 'constraints',(SELECT json_agg(json_build_object(
   'table',c.relname,'kind',co.contype,'name',co.conname,
   'columns',(SELECT json_agg(a.attname ORDER BY k.ord)
     FROM unnest(co.conkey) WITH ORDINALITY k(attnum,ord)
     JOIN pg_attribute a ON a.attrelid=co.conrelid AND a.attnum=k.attnum),
   'parent',p.relname,
   'parent_columns',(SELECT json_agg(a.attname ORDER BY k.ord)
     FROM unnest(co.confkey) WITH ORDINALITY k(attnum,ord)
     JOIN pg_attribute a ON a.attrelid=co.confrelid AND a.attnum=k.attnum)))
  FROM pg_constraint co JOIN pg_class c ON c.oid=co.conrelid
  JOIN pg_namespace n ON n.oid=c.relnamespace
  LEFT JOIN pg_class p ON p.oid=co.confrelid
  WHERE n.nspname='public' AND co.contype IN ('p','f','u')),
 'unique_indexes',(SELECT json_agg(json_build_object(
   'table',c.relname,'name',idx.relname,
   'definition',pg_get_indexdef(i.indexrelid),
   'columns',(SELECT json_agg(a.attname ORDER BY k.ord)
     FROM unnest(i.indkey) WITH ORDINALITY k(attnum,ord)
     LEFT JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=k.attnum
     WHERE k.ord <= i.indnkeyatts)))
  FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
  JOIN pg_class idx ON idx.oid=i.indexrelid
  JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='public' AND i.indisunique));
"""


class CloneError(Exception):
    """A diagnostic containing only schema names or counts, never row values."""


def ident(value: str) -> str:
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z_0-9]*", value):
        raise CloneError("Invalid SQL identifier")
    return '"' + value + '"'


def literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def excluded(table: str) -> bool:
    return (
        table in EXCLUDED or table.startswith(("zz_", "wms_ops_backup_"))
        or "_bak_" in table or table.startswith("withdrawal_")
        or (table.startswith("marking_") and table not in KEEP_MARKING)
        or (table.startswith("fbs_") and table not in KEEP_FBS)
    )


def source_query(sql: str) -> list[Any]:
    command = ["ssh", "-o", "BatchMode=yes", "root@sellerfocus.pro",
               "docker exec -i wms_prod-db-1 psql -U postgres -d wms "
               "-X -q -A -t -v ON_ERROR_STOP=1"]
    sql = "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n" + sql + "\nROLLBACK;"
    proc = subprocess.run(command, input=sql, text=True, capture_output=True, check=False)
    if proc.returncode:
        # psql error details may contain an offending row or credential.
        raise CloneError(f"Read-only source query failed (exit {proc.returncode})")
    try:
        return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    except (ValueError, TypeError) as exc:
        raise CloneError("Source did not return valid JSON") from exc


def constraints(schema: dict[str, Any], kind: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in schema["constraints"]:
        if item["kind"] == kind:
            result[item["table"]].append(item)
    return result


def selection_queries(schema: dict[str, Any]) -> dict[str, str]:
    """Choose children through declared ownership; never follow an FK outward."""
    allowed = {t for t in schema["tables"] if not excluded(t)}
    fks = constraints(schema, "f")
    direct = {}
    owners = {}
    for table in sorted(allowed):
        names = {c["name"] for c in schema["tables"][table]}
        if table == "tenants":
            direct[table] = "id"
        elif "tenant_id" in names:
            direct[table] = "tenant_id"
    pending = allowed - direct.keys()
    known = set(direct)
    while pending:
        additions = {}
        for table in sorted(pending):
            routes = [fk for fk in fks[table]
                      if fk["parent"] in known and fk["parent"] != "users"]
            if routes:
                additions[table] = routes
        if not additions:
            raise CloneError("No tenant ownership route: " + ", ".join(sorted(pending)))
        owners.update(additions)
        known.update(additions)
        pending -= additions.keys()

    def predicate(table: str, alias: str, depth: int) -> str:
        if table in direct:
            return f"{alias}.{ident(direct[table])}=:tenant_id::uuid"
        routes = []
        for number, fk in enumerate(owners[table]):
            parent_alias = f"p{depth}_{number}"
            join = " AND ".join(
                f"{parent_alias}.{ident(pc)}={alias}.{ident(cc)}"
                for cc, pc in zip(fk["columns"], fk["parent_columns"], strict=True))
            parent = fk["parent"]
            routes.append(f"EXISTS (SELECT 1 FROM public.{ident(parent)} {parent_alias} "
                          f"WHERE {join} AND ({predicate(parent, parent_alias, depth + 1)}))")
        return " OR ".join(routes)

    return {table: predicate(table, "t", 0) for table in sorted(allowed)}


def export_snapshot(destination: Path) -> None:
    if destination.exists():
        raise CloneError("Snapshot destination already exists")
    schema = source_query(SCHEMA_SQL)[0]
    selections = selection_queries(schema)
    statements = [SCHEMA_SQL]
    for tenant_id in SOURCES:
        for table, predicate in sorted(selections.items()):
            predicate = predicate.replace(":tenant_id", literal(tenant_id))
            # Account names, contacts, source hashes and passwords never leave source.
            if table == "users":
                projection = "json_build_object('id',t.id,'tenant_id',t.tenant_id," \
                             "'seller_id',t.seller_id,'role',t.role)"
            else:
                names = [c["name"] for c in schema["tables"][table]]
                sensitive = [name for name in names if SECRET_NAME.search(name)]
                # This is a calculation cache key, not an authentication secret.
                sensitive = [name for name in sensitive if name != "storage_calculation_token"]
                if sensitive:
                    raise CloneError(f"Unreviewed credential column in {table}: "
                                     + ", ".join(sensitive))
                projection = "to_jsonb(t)"
            statements.append(
                f"SELECT json_build_object('source',{literal(tenant_id)},"
                f"'table',{literal(table)},'row',{projection}) "
                f"FROM public.{ident(table)} t WHERE ({predicate});"
            )
    exported = source_query("\n".join(statements))
    if exported[0] != schema:
        raise CloneError("Source schema changed before snapshot")
    snapshot: dict[str, Any] = {"format": 1, "schema": schema, "tenants": {}}
    for tenant_id in SOURCES:
        snapshot["tenants"][tenant_id] = {table: [] for table in selections}
    for item in exported[1:]:
        snapshot["tenants"][item["source"]][item["table"]].append(item["row"])
    for data in snapshot["tenants"].values():
        if len(data["tenants"]) != 1:
            raise CloneError("Source tenant missing or duplicated")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb") as zipped:
        zipped.write(json.dumps(snapshot, ensure_ascii=False).encode())
    print(json.dumps({"snapshot": str(destination), "counts": {
        SOURCES[tenant][0]: {table: len(rows) for table, rows in data.items()}
        for tenant, data in snapshot["tenants"].items()
    }}, ensure_ascii=False))


def transform(snapshot: dict[str, Any], passwords: dict[str, str], hash_password: Any
              ) -> dict[str, list[dict[str, Any]]]:
    schema = snapshot["schema"]
    pks = constraints(schema, "p")
    fks = constraints(schema, "f")
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source, data in snapshot["tenants"].items():
        if source not in SOURCES:
            raise CloneError("Unexpected source tenant")
        slug, name = SOURCES[source]
        password = passwords.get(slug)
        if not isinstance(password, str) or len(password) < 16:
            raise CloneError("Supply a new password of at least 16 characters for each slug")
        target = uuid.uuid4()
        mapping = {source: str(target)}
        for table, rows in data.items():
            if excluded(table):
                raise CloneError(f"Excluded table present in snapshot: {table}")
            if len(pks[table]) != 1 or pks[table][0]["columns"] != ["id"]:
                raise CloneError(f"Unsupported primary key in {table}")
            for row in rows:
                old = row["id"]
                if not isinstance(old, str) or not UUID_TEXT.fullmatch(old):
                    raise CloneError(f"Non-UUID identity in {table}")
                mapping[old] = str(uuid.uuid5(target, old))
        source_users = {row["id"]: row for row in data.get("users", [])}
        # Historical actions can refer to system operators from another tenant.
        # Copy no cross-tenant user: create an anonymous local actor for each id.
        for table, rows in data.items():
            for fk in fks[table]:
                if fk["parent"] == "users" and fk["parent_columns"] == ["id"]:
                    for row in rows:
                        old = row.get(fk["columns"][0])
                        if old is not None:
                            mapping.setdefault(old, str(uuid.uuid5(target, old)))
                            source_users.setdefault(old, {"id": old, "role": "fulfillment_staff"})

        def rewrite(
            value: Any,
            _mapping: dict[str, str] = mapping,
            _target: uuid.UUID = target,
        ) -> Any:
            if isinstance(value, str) and UUID_TEXT.fullmatch(value):
                return _mapping.get(value, str(uuid.uuid5(_target, value)))
            if isinstance(value, str):
                return EMAIL_TEXT.sub("test-account@example.test", value)
            if isinstance(value, list):
                return [rewrite(v, _mapping, _target) for v in value]
            if isinstance(value, dict):
                return {k: rewrite(v, _mapping, _target) for k, v in value.items()
                        if not SECRET_NAME.search(k)
                        and k.lower() not in {
                            "cis_code", "kiz", "email", "user_email", "actor_email"
                        }}
            return value

        for table, rows in data.items():
            if table == "users":
                continue
            column_types = {c["name"]: c["type"] for c in schema["tables"][table]}
            for original in rows:
                row = {}
                for column, value in original.items():
                    if column_types[column] == "uuid" and value is not None:
                        row[column] = mapping.get(value, str(uuid.uuid5(target, value)))
                    elif column_types[column] in {"json", "jsonb", "_uuid"}:
                        row[column] = rewrite(value)
                    else:
                        # Real SKU/barcode strings stay scan-compatible, even
                        # when a barcode happens to look like a UUID.
                        row[column] = EMAIL_TEXT.sub("test-account@example.test", value) \
                            if isinstance(value, str) else value
                if "tenant_id" in row and row["tenant_id"] != str(target):
                    raise CloneError(f"Cross-tenant source row in {table}")
                if table == "tenants":
                    row.update(id=str(target), slug=slug, name=name, subscription_paid_until=None)
                if table == "fbs_warehouse_bindings":
                    row.update(stock_sync_enabled=False, lease_until=None,
                               last_sync_status=None, last_sync_at=None, last_error_code=None)
                if "actor_name_snapshot" in row:
                    row["actor_name_snapshot"] = "Тестовый сотрудник"
                result[table].append(row)
        actor_hash = hash_password(os.urandom(32).hex())
        for old, actor in source_users.items():
            role = actor.get("role", "fulfillment_staff")
            if role not in {"fulfillment_staff", "fulfillment_seller", "fulfillment_admin"}:
                role = "fulfillment_staff"
            result["users"].append({
                "id": mapping[old], "tenant_id": str(target),
                "seller_id": rewrite(actor.get("seller_id")), "email": None,
                "full_name": "Тестовый сотрудник", "job_title": None,
                "password_hash": actor_hash, "must_set_password": True,
                "can_manage_seller_shops": False, "role": role,
                "packaging_rate_kopecks": 0,
            })
        result["users"].append({
            "id": str(uuid.uuid4()), "tenant_id": str(target), "seller_id": None,
            "email": slug + "@example.test", "full_name": "Тестовый администратор",
            "job_title": None, "password_hash": hash_password(password),
            "must_set_password": False, "can_manage_seller_shops": True,
            "role": "fulfillment_admin", "packaging_rate_kopecks": 0,
        })
    return result


def preflight(schema: dict[str, Any], rows: dict[str, list[dict[str, Any]]]
              ) -> tuple[list[str], dict[str, set[str]]]:
    """Validate complete FK closure, defer only nullable cycle-breaking links."""
    fks = constraints(schema, "f")
    deferred: dict[str, set[str]] = defaultdict(set)
    dependencies: dict[str, set[str]] = {table: set() for table in rows}
    required: dict[str, set[str]] = {table: set() for table in rows}
    parent_keys: dict[tuple[str, tuple[str, ...]], set[tuple[Any, ...]]] = {}
    for table, records in rows.items():
        columns = {c["name"]: c for c in schema["tables"][table]}
        for fk in fks[table]:
            key = (fk["parent"], tuple(fk["parent_columns"]))
            if key not in parent_keys:
                parent_keys[key] = {
                    tuple(r.get(c) for c in fk["parent_columns"])
                    for r in rows.get(fk["parent"], [])}
            present = False
            for record in records:
                values = tuple(record.get(c) for c in fk["columns"])
                if all(v is not None for v in values):
                    present = True
                    if values not in parent_keys[key]:
                        raise CloneError(
                            f"Missing FK closure: {table}.{fk['name']} -> {fk['parent']}"
                        )
            if not present:
                continue
            nullable = [c for c in fk["columns"] if columns[c]["nullable"]]
            dependencies[table].add(fk["parent"])
            if not nullable:
                required[table].add(fk["parent"])
        for record in records:
            if record.keys() - columns.keys():
                raise CloneError(f"Unknown snapshot column in {table}")
    order = []
    while dependencies:
        ready = sorted(t for t, deps in dependencies.items() if not deps)
        if not ready:
            ready = sorted(t for t in dependencies if not required[t])[:1]
            if not ready:
                raise CloneError("Required FK cycle: " + ", ".join(sorted(dependencies)))
            table = ready[0]
            cols = {c["name"]: c for c in schema["tables"][table]}
            for fk in fks[table]:
                if fk["parent"] in dependencies[table]:
                    deferred[table].update(c for c in fk["columns"] if cols[c]["nullable"])
        order.extend(ready)
        for table in ready:
            del dependencies[table]
        for deps in dependencies.values():
            deps.difference_update(ready)
        for deps in required.values():
            deps.difference_update(ready)
    return order, deferred


async def apply_snapshot(envelope: dict[str, Any]) -> None:
    # Run with backend on PYTHONPATH inside the existing staging WMS container.
    from sqlalchemy import text

    from app.core.settings import settings
    from app.db.session import engine
    from app.services.marking_label_artifact_service import build_datamatrix_label_pdf
    from app.services.passwords import hash_password

    if (
        settings.app_env != "staging"
        or os.environ.get("RAILWAY_PROJECT_ID") != PROJECT_ID
        or os.environ.get("RAILWAY_ENVIRONMENT_ID") != STAGING_ENVIRONMENT_ID
    ):
        raise CloneError("Apply requires the known Railway staging project and APP_ENV=staging")
    if engine.dialect.name != "postgresql":
        raise CloneError("PostgreSQL staging is required")
    if engine.url.host != STAGING_POSTGRES_HOST:
        raise CloneError("Apply requires the private Postgres service in the staging environment")
    snapshot = envelope.get("snapshot", {})
    if snapshot.get("format") != 1 or set(snapshot.get("tenants", {})) != set(SOURCES):
        raise CloneError("Snapshot must contain exactly the three authorized tenants")
    rows = transform(snapshot, envelope.get("passwords", {}), hash_password)
    # Reserved zero GTIN, TEST serial and deliberately invalid crypto tail make
    # these warehouse scanning examples unusable as real issued marking codes.
    # Build their print artifact through the same encoder used by the app.
    for tenant in rows["tenants"]:
        stocked = {r["product_id"] for r in rows.get("inventory_balances", [])
                   if r["tenant_id"] == tenant["id"] and r.get("quantity", 0) > 0}
        products_by_seller: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for product in rows.get("products", []):
            if product["tenant_id"] == tenant["id"] and product.get("seller_id"):
                products_by_seller[product["seller_id"]].append(product)
        if not products_by_seller:
            raise CloneError("No seller-owned product for synthetic marking")
        for seller_id, products in products_by_seller.items():
            pool_id = str(uuid.uuid4())
            rows["marking_pools"].append({
                "id": pool_id, "tenant_id": tenant["id"], "seller_id": seller_id,
                "gtin": "00000000000000", "title": "ТЕСТ — не настоящие КИЗы",})
            linked = [product for product in products if product["id"] in stocked] or products[:1]
            for product in linked:
                rows["marking_pool_products"].append({
                    "id": str(uuid.uuid4()), "tenant_id": tenant["id"],
                    "pool_id": pool_id, "product_id": product["id"],})
            # Enough local codes for repeated daily FBS test batches without
            # making a scan reuse one serial after its first application.
            for _ in range(100):
                serial = "TEST" + uuid.uuid4().hex[:9]
                cis = "010000000000000021" + serial + "\x1d91TEST\x1d92NOTREAL"
                pdf = build_datamatrix_label_pdf(cis)
                rows["marking_codes"].append({
                    "id": str(uuid.uuid4()), "tenant_id": tenant["id"],
                    "seller_id": seller_id, "pool_id": pool_id, "product_id": None,
                    "cis_code": cis, "source": "pool", "gtin": "00000000000000",
                    "serial": serial, "crypto_tail": "91TEST\x1d92NOTREAL",
                    "status": "available", "label_artifact_pdf": "\\x" + pdf.hex(),
                    "label_artifact_required": True,})
    order, deferred = preflight(snapshot["schema"], rows)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT pg_advisory_xact_lock(70520261008)"))
        target_schema = (await conn.execute(text(SCHEMA_SQL))).scalar_one()
        source_schema = snapshot["schema"]
        if target_schema["revision"] != source_schema["revision"]:
            raise CloneError("Source/staging schema revision differs")
        for table in rows:
            if target_schema["tables"].get(table) != source_schema["tables"][table]:
                raise CloneError(f"Source/staging columns differ: {table}")
            for kind in ("p", "f", "u"):
                # Constraint names and definitions must match the inspected source.
                left = constraints(source_schema, kind)[table]
                right = constraints(target_schema, kind)[table]
                if sorted(left, key=lambda v: v["name"]) != sorted(right, key=lambda v: v["name"]):
                    raise CloneError(f"Source/staging constraints differ: {table}")
        # Preflight every identity and every unique index before persistent writes.
        # A unique index is isolated when it includes any remapped UUID column.
        # For other indexes, evaluate its actual key against incoming records.
        for table, records in rows.items():
            if not records:
                continue
            table_name = "public." + ident(table)
            for offset in range(0, len(records), 500):
                batch = json.dumps(records[offset:offset + 500], ensure_ascii=False)
                collision = (await conn.execute(text(
                    f"SELECT EXISTS(SELECT 1 FROM {table_name} t JOIN "
                    f"jsonb_populate_recordset(NULL::{table_name},CAST(:batch AS jsonb)) x "
                    "ON t.id=x.id)"), {"batch": batch})).scalar_one()
                if collision:
                    raise CloneError(f"Target identity collision in {table}")
            for index in target_schema["unique_indexes"]:
                if index["table"] != table:
                    continue
                columns = index["columns"]
                if any(c is None for c in columns):
                    # A direct remapped UUID key isolates existing expression
                    # indexes too (for example product+location+container).
                    uuid_keys = {c["name"] for c in source_schema["tables"][table]
                                 if c["type"] == "uuid"}
                    if not any(c in uuid_keys for c in columns if c is not None):
                        raise CloneError(f"Unreviewed global expression index: {index['name']}")
                    continue
                if "tenant_id" in columns or "id" in columns:
                    continue
                join = " AND ".join(f"t.{ident(c)}=x.{ident(c)}" for c in columns)
                for offset in range(0, len(records), 500):
                    batch = json.dumps(records[offset:offset + 500], ensure_ascii=False)
                    collision = (await conn.execute(text(
                        f"SELECT EXISTS(SELECT 1 FROM {table_name} t JOIN "
                        f"jsonb_populate_recordset(NULL::{table_name},CAST(:batch AS jsonb)) x "
                        f"ON {join})"), {"batch": batch})).scalar_one()
                    if collision:
                        raise CloneError(f"Target unique collision in {table}.{index['name']}")
        for table in order:
            records = rows[table]
            if not records:
                continue
            table_name = "public." + ident(table)
            # Synthetic rows omit server-default fields; keep their column
            # signature separate from copied rows so defaults really execute.
            groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
            for record in records:
                names = tuple(c["name"] for c in source_schema["tables"][table]
                              if c["name"] in record)
                groups[names].append(record)
            for names, grouped in groups.items():
                cols = ",".join(ident(c) for c in names)
                for offset in range(0, len(grouped), 500):
                    batch_rows = [{**r, **{c: None for c in deferred[table]}}
                                  for r in grouped[offset:offset + 500]]
                    await conn.execute(text(
                        f"INSERT INTO {table_name} ({cols}) SELECT {cols} FROM "
                        f"jsonb_populate_recordset(NULL::{table_name},CAST(:batch AS jsonb))"),
                        {"batch": json.dumps(batch_rows, ensure_ascii=False)})
        for table, columns in deferred.items():
            if not columns or not rows[table]:
                continue
            table_name = "public." + ident(table)
            assignments = ",".join(f"{ident(c)}=x.{ident(c)}" for c in sorted(columns))
            for offset in range(0, len(rows[table]), 500):
                await conn.execute(text(
                    f"UPDATE {table_name} t SET {assignments} FROM "
                    f"jsonb_populate_recordset(NULL::{table_name},CAST(:batch AS jsonb)) x "
                    "WHERE t.id=x.id"),
                    {"batch": json.dumps(rows[table][offset:offset + 500], ensure_ascii=False)})
        # The commit is one atomic operation for all three tenants.
    await engine.dispose()
    print(json.dumps({"created": [
        {"id": row["id"], "slug": row["slug"], "admin_email": row["slug"] + "@example.test"}
        for row in rows["tenants"]
    ], "counts": {table: len(records) for table, records in rows.items()}}, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="Read-only source export to a private gzip file")
    export.add_argument("--output", type=Path, required=True)
    sub.add_parser("apply", help="Apply stdin envelope inside the staging WMS container")
    args = parser.parse_args()
    try:
        if args.command == "export":
            export_snapshot(args.output)
        else:
            asyncio.run(apply_snapshot(json.load(sys.stdin)))
        return 0
    except CloneError as exc:
        print(str(exc), file=sys.stderr)
    except ModuleNotFoundError as exc:
        # The missing module name is useful for deployment diagnostics and
        # cannot contain database or row values.
        print(
            f"Clone failed (module unavailable: {exc.name or 'unknown'}); "
            "transaction rolled back if uncommitted",
            file=sys.stderr,
        )
    except Exception as exc:
        # Suppress all DB/driver exceptions: SQLAlchemy can include bound data.
        print(f"Clone failed ({type(exc).__name__}); transaction rolled back if uncommitted",
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
