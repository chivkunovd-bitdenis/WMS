"""Recursive physical warehouse invariant for ORM and direct SQL writers."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Connection, Engine, event, inspect, text

GUARD_ERROR = "physical_warehouse_required"


def register_sqlite_defect_function(engine: Engine) -> None:
    """Bind ``wms_defect_allowed`` to every DBAPI connection this engine opens.

    SQLite user-defined functions live on the raw connection object, not in
    the database file. ``install_guards`` registers the function on whatever
    connection is active at the moment it runs, which is enough for a single
    migration or an isolated test, but a shared engine's pool can and does
    hand out a *different* physical connection later -- normal once a
    handful of sessions or a background task interleave, and it does not
    depend on ``pytest -n``. That other connection never saw
    ``create_function`` and the guard trigger then fails with
    ``no such function: wms_defect_allowed`` even though the trigger DDL
    itself is stored in the database file and still fires correctly.
    Hooking the pool's ``connect`` event covers every connection the engine
    ever opens, in any order, regardless of test order or worker count.
    """
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def _register_wms_defect_allowed(dbapi_connection: Any, connection_record: Any) -> None:
        info = connection_record.info
        dbapi_connection.create_function(
            "wms_defect_allowed", 1,
            lambda tenant: info.get("wms_defect_tenant") == str(tenant),
        )


def physical_graph(connection: Connection) -> dict[str, list[tuple[str, str]]]:
    inspector = inspect(connection)
    all_edges: dict[str, set[tuple[str, str]]] = {}
    for table in inspector.get_table_names():
        edges = all_edges.setdefault(table, set())
        for fk in inspector.get_foreign_keys(table):
            if "id" in fk["referred_columns"]:
                index = fk["referred_columns"].index("id")
                edges.add((fk["constrained_columns"][index], fk["referred_table"]))
    included = {"warehouses"}
    while True:
        expanded = included | {table for table, edges in all_edges.items()
                               if any(parent in included for _, parent in edges)}
        if expanded == included:
            break
        included = expanded
    return {table: sorted((column, parent) for column, parent in all_edges[table]
                          if parent in included) for table in sorted(included)}


def _paths(graph: dict[str, list[tuple[str, str]]], table: str,
           visited: frozenset[str] = frozenset()) -> list[list[tuple[str, str]]]:
    if table == "warehouses":
        return [[]]
    return [[edge, *rest] for edge in graph[table] if edge[1] not in visited | {table}
            for rest in _paths(graph, edge[1], visited | {table})]


def install_guards(connection: Connection) -> None:
    graph = physical_graph(connection)
    inspector = inspect(connection)
    if connection.dialect.name == "postgresql":
        graph_json = json.dumps(graph).replace("'", "''")
        connection.execute(text("""
        CREATE OR REPLACE FUNCTION wms_check_physical_record(
          relation text, record jsonb, owner uuid, seen jsonb, root_relation text
        ) RETURNS jsonb LANGUAGE plpgsql AS $$
        DECLARE graph jsonb := '__GRAPH__'; edge jsonb; parent jsonb; ref uuid;
          identity text; row_tenant uuid; code text;
        BEGIN
          IF record IS NULL THEN RETURN seen; END IF;
          identity := relation || ':' || (record->>'id');
          row_tenant := (record->>'tenant_id')::uuid;
          owner := COALESCE(owner, (seen->>'__owner')::uuid, row_tenant);
          IF owner IS NOT NULL AND row_tenant IS NOT NULL AND owner <> row_tenant THEN
            RAISE EXCEPTION 'physical_warehouse_required' USING ERRCODE = '23514';
          END IF;
          IF seen ? identity THEN RETURN seen; END IF;
          seen := seen || jsonb_build_object(identity, true, '__owner', owner);
          IF relation = 'warehouses' THEN
            code := lower(record->>'code');
            IF code = 'fbs-wb' OR left(code, 7) = 'fbs-wb-' OR
              (code = '__defect__' AND (
                root_relation = 'fbs_warehouse_bindings' OR
                current_setting('wms.defect_tenant', true) IS DISTINCT FROM owner::text
              )) OR (code <> '__defect__' AND NOT (record->>'is_operational')::boolean) THEN
              RAISE EXCEPTION 'physical_warehouse_required' USING ERRCODE = '23514';
            END IF;
            RETURN seen;
          END IF;
          FOR edge IN SELECT value FROM jsonb_array_elements(graph->relation) LOOP
            ref := (record->>(edge->>0))::uuid;
            IF ref IS NULL THEN CONTINUE; END IF;
            EXECUTE 'SELECT to_jsonb(p) FROM ' || quote_ident(edge->>1) ||
              ' p WHERE id=$1 FOR SHARE' INTO parent USING ref;
            seen := wms_check_physical_record(edge->>1, parent, owner, seen, root_relation);
          END LOOP;
          RETURN seen;
        END $$;
        """.replace("__GRAPH__", graph_json)))
        connection.execute(text("""
        CREATE OR REPLACE FUNCTION wms_physical_warehouse_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          IF EXISTS (SELECT 1 FROM background_jobs WHERE id::text =
            current_setting('wms.warehouse_repair', true)
            AND job_type='physical_warehouse_repair' AND status='running')
          THEN RETURN NEW; END IF;
          PERFORM wms_check_physical_record(
            TG_TABLE_NAME, to_jsonb(NEW), NULL, '{}', TG_TABLE_NAME);
          RETURN NEW;
        END $$;
        CREATE OR REPLACE FUNCTION wms_reserved_warehouse_code() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          IF EXISTS (SELECT 1 FROM background_jobs WHERE id::text =
            current_setting('wms.warehouse_repair', true)
            AND job_type='physical_warehouse_repair' AND status='running')
          THEN RETURN NEW; END IF;
          IF lower(NEW.code)='fbs-wb' OR left(lower(NEW.code),7)='fbs-wb-' OR
            (TG_OP='UPDATE' AND (lower(OLD.code)='fbs-wb' OR
             left(lower(OLD.code),7)='fbs-wb-')) THEN
            RAISE EXCEPTION 'warehouse_code_reserved' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER wms_reserved_warehouse_code BEFORE INSERT OR UPDATE OF code, is_operational
        ON warehouses FOR EACH ROW EXECUTE FUNCTION wms_reserved_warehouse_code();
        """))
        for table in graph:
            if table != "warehouses":
                connection.exec_driver_sql(
                    f'CREATE TRIGGER wms_physical_graph BEFORE INSERT OR UPDATE ON "{table}" '
                    "FOR EACH ROW EXECUTE FUNCTION wms_physical_warehouse_guard()"
                )
        return

    # SQLite test guards cover all acyclic ancestry paths. Production uses the
    # recursive function with a visited-record set, including cyclic FK graphs.
    info = connection.info
    raw: Any = connection.connection.dbapi_connection
    raw.create_function("wms_defect_allowed", 1,
                        lambda tenant: info.get("wms_defect_tenant") == str(tenant))
    columns = {t: {c["name"] for c in inspector.get_columns(t)} for t in graph}
    for table in graph:
        if table == "warehouses":
            continue
        clauses = []
        for path in _paths(graph, table):
            first_column, first_table = path[0]
            joins = f'"{first_table}" p0'
            owners = ["NEW.tenant_id"] if "tenant_id" in columns[table] else []
            for i, (_, parent) in enumerate(path):
                if "tenant_id" in columns[parent]:
                    owners.append(f"p{i}.tenant_id")
                if i:
                    joins += f' JOIN "{parent}" p{i} ON p{i}.id=p{i-1}."{path[i][0]}"'
            wh = f"p{len(path)-1}"
            tenant = owners[0]
            invalid = " OR ".join(f"{o} IS NOT {wh}.tenant_id" for o in owners)
            defect = "0" if table == "fbs_warehouse_bindings" else f"wms_defect_allowed({tenant})"
            clauses.append(
                f'EXISTS (SELECT 1 FROM {joins} WHERE p0.id=NEW."{first_column}" AND ('
                f"{invalid} OR lower({wh}.code)='fbs-wb' OR lower({wh}.code) LIKE 'fbs-wb-%' "
                f"OR (lower({wh}.code)='__defect__' AND NOT {defect}) "
                f"OR (lower({wh}.code)<>'__defect__' AND NOT {wh}.is_operational)))"
            )
        for operation in ("INSERT", "UPDATE"):
            connection.exec_driver_sql(
                f'CREATE TRIGGER "{table}_wms_physical_{operation}" BEFORE {operation} '
                f'ON "{table}" WHEN ' + " OR ".join(clauses)
                + f" BEGIN SELECT RAISE(ABORT, '{GUARD_ERROR}'); END"
            )


def remove_guards(connection: Connection) -> None:
    if connection.dialect.name == "postgresql":
        rows = connection.execute(text("""
          SELECT c.relname, t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
          WHERE NOT t.tgisinternal AND (t.tgname LIKE 'wms_physical_%'
            OR t.tgname='wms_reserved_warehouse_code')
        """)).all()
        for table, name in rows:
            connection.exec_driver_sql(f'DROP TRIGGER "{name}" ON "{table}"')
        connection.exec_driver_sql(
            "DROP FUNCTION IF EXISTS wms_physical_warehouse_guard(); "
            "DROP FUNCTION IF EXISTS wms_check_physical_record(text,jsonb,uuid,jsonb,text); "
            "DROP FUNCTION IF EXISTS wms_reserved_warehouse_code();"
        )
    else:
        rows = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE '%wms_physical_%'"
        ).all()
        for (name,) in rows:
            connection.exec_driver_sql(f'DROP TRIGGER "{name}"')
