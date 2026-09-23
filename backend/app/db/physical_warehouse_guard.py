"""Database invariant, including Core/bulk writes which bypass service validation.

Historical rows remain readable. The defect stock circuit is explicitly retained;
marketplace bindings and normal document selectors require operational warehouses.
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import Connection, inspect

GUARD_ERROR = "physical_warehouse_required"


def _id_column(fk: Any) -> str | None:
    if "id" not in fk["referred_columns"]:
        return None
    return str(fk["constrained_columns"][fk["referred_columns"].index("id")])


def _trigger_name(column: str, parent: str) -> str:
    suffix = hashlib.sha256(parent.encode()).hexdigest()[:8]
    return f"wms_physical_{column}_{suffix}"


def _physical_parent(inspector: Any, parent: str) -> str | None:
    if parent == "warehouses":
        return "id"
    for fk in inspector.get_foreign_keys(parent):
        if fk["referred_table"] == "warehouses":
            return str(fk["constrained_columns"][0])
    return None


def install_guards(connection: Connection) -> None:
    inspector = inspect(connection)
    postgres = connection.dialect.name == "postgresql"
    if postgres:
        connection.exec_driver_sql("""
        CREATE OR REPLACE FUNCTION wms_physical_warehouse_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE ref uuid; wh uuid; tenant uuid; owner_tenant uuid; allowed boolean;
        BEGIN
          IF EXISTS (SELECT 1 FROM background_jobs WHERE id::text =
            current_setting('wms.warehouse_repair', true)
            AND job_type = 'physical_warehouse_repair' AND status = 'running')
          THEN RETURN NEW; END IF;
          ref := (to_jsonb(NEW)->>TG_ARGV[0])::uuid;
          IF ref IS NULL THEN RETURN NEW; END IF;
          IF TG_ARGV[1] = 'warehouses' THEN wh := ref;
          ELSE
            EXECUTE 'SELECT ' || quote_ident(TG_ARGV[4]) || ' FROM ' ||
              quote_ident(TG_ARGV[1]) || ' WHERE id=$1' INTO wh USING ref;
            -- An unmapped marketplace order may legitimately have no warehouse.
            IF wh IS NULL AND TG_ARGV[1] <> 'storage_locations' THEN RETURN NEW; END IF;
          END IF;
          SELECT tenant_id, (is_operational OR code = '__DEFECT__')
            INTO tenant, allowed FROM warehouses WHERE id = wh FOR SHARE;
          owner_tenant := (to_jsonb(NEW)->>'tenant_id')::uuid;
          IF owner_tenant IS NULL AND TG_NARGS > 2 THEN
            EXECUTE 'SELECT tenant_id FROM ' || quote_ident(TG_ARGV[2]) || ' WHERE id=$1'
              INTO owner_tenant USING (to_jsonb(NEW)->>TG_ARGV[3])::uuid;
          END IF;
          IF tenant IS DISTINCT FROM owner_tenant
             OR NOT COALESCE(allowed, false)
             OR (TG_TABLE_NAME = 'fbs_warehouse_bindings' AND NOT EXISTS
                 (SELECT 1 FROM warehouses WHERE id=wh AND is_operational)) THEN
            RAISE EXCEPTION 'physical_warehouse_required'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
        """)
        connection.exec_driver_sql("""
        CREATE OR REPLACE FUNCTION wms_reserved_warehouse_code() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          IF EXISTS (SELECT 1 FROM background_jobs WHERE id::text =
            current_setting('wms.warehouse_repair', true)
            AND job_type = 'physical_warehouse_repair' AND status = 'running')
          THEN RETURN NEW; END IF;
          IF lower(NEW.code) = 'fbs-wb' OR left(lower(NEW.code), 7) = 'fbs-wb-' THEN
            RAISE EXCEPTION 'warehouse_code_reserved' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER wms_reserved_warehouse_code BEFORE INSERT OR UPDATE OF code
        ON warehouses FOR EACH ROW EXECUTE FUNCTION wms_reserved_warehouse_code();
        """)
    for table in sorted(inspector.get_table_names()):
        installed: set[str] = set()
        owner_table, owner_column = "", ""
        if "tenant_id" not in {c["name"] for c in inspector.get_columns(table)}:
            parents = sorted(inspector.get_foreign_keys(table),
                             key=lambda fk: fk["referred_table"] == "products")
            for parent_fk in parents:
                parent_table = parent_fk["referred_table"]
                if parent_table in {"storage_locations", "warehouses"}:
                    continue
                if "tenant_id" in {c["name"] for c in inspector.get_columns(parent_table)}:
                    owner_table = parent_table
                    owner_column = _id_column(parent_fk) or ""
                    break
        for fk in inspector.get_foreign_keys(table):
            parent = fk["referred_table"]
            warehouse_column = _physical_parent(inspector, parent)
            if warehouse_column is None:
                continue
            column = _id_column(fk)
            if column is None:
                continue
            name = _trigger_name(column, parent)
            if name in installed:
                continue
            installed.add(name)
            if postgres:
                connection.exec_driver_sql(
                    f'CREATE TRIGGER "{name}" BEFORE INSERT OR UPDATE ON "{table}" '
                    "FOR EACH ROW EXECUTE FUNCTION wms_physical_warehouse_guard"
                    f"('{column}', '{parent}', '{owner_table}', '{owner_column}', "
                    f"'{warehouse_column}')"
                )
            else:
                wh = (
                    f'NEW."{column}"' if parent == "warehouses" else
                    f'(SELECT "{warehouse_column}" FROM "{parent}" WHERE id=NEW."{column}")'
                )
                allowed = (
                    "w.is_operational" if table == "fbs_warehouse_bindings" else
                    "(w.is_operational OR w.code='__DEFECT__')"
                )
                tenant = (
                    f'(SELECT tenant_id FROM "{owner_table}" WHERE id=NEW."{owner_column}")'
                    if owner_table else "NEW.tenant_id"
                )
                for operation in ("INSERT", "UPDATE"):
                    connection.exec_driver_sql(
                        f'CREATE TRIGGER "{table}_{name}_{operation}" '
                        f'BEFORE {operation} ON "{table}" '
                        f'WHEN NEW."{column}" IS NOT NULL AND {wh} IS NOT NULL AND NOT EXISTS '
                        f'(SELECT 1 FROM warehouses w WHERE w.id={wh} '
                        f'AND w.tenant_id={tenant} AND {allowed}) '
                        f"BEGIN SELECT RAISE(ABORT, '{GUARD_ERROR}'); END"
                    )


def remove_guards(connection: Connection) -> None:
    inspector = inspect(connection)
    for table in sorted(inspector.get_table_names()):
        for fk in inspector.get_foreign_keys(table):
            if _physical_parent(inspector, fk["referred_table"]) is not None:
                column = _id_column(fk)
                if column is None:
                    continue
                name = _trigger_name(column, fk["referred_table"])
                if connection.dialect.name == "postgresql":
                    connection.exec_driver_sql(f'DROP TRIGGER IF EXISTS "{name}" ON "{table}"')
                else:
                    for op in ("INSERT", "UPDATE"):
                        connection.exec_driver_sql(
                            f'DROP TRIGGER IF EXISTS "{table}_{name}_{op}"'
                        )
    if connection.dialect.name == "postgresql":
        connection.exec_driver_sql(
            "DROP TRIGGER IF EXISTS wms_reserved_warehouse_code ON warehouses; "
            "DROP FUNCTION IF EXISTS wms_physical_warehouse_guard(); "
            "DROP FUNCTION IF EXISTS wms_reserved_warehouse_code();"
        )
