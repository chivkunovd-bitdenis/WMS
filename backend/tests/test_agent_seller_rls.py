# ruff: noqa: E501
"""WMS-641 R41-R42, C38-C39: граница данных в самой базе (роль на селлера + RLS) на временной PostgreSQL.

Поднимается отдельный временный кластер (initdb в временном каталоге, свой сокет и порт); боевая и
рабочие базы не затрагиваются. Нет бинарников PostgreSQL: тесты пропускаются."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "agent_db"))
import gateway  # noqa: E402
import seller_access as sa  # noqa: E402

CANDIDATE_BINS = [os.environ.get("PG_BIN", ""), "/opt/homebrew/opt/postgresql@16/bin",
                  "/opt/homebrew/opt/postgresql@17/bin", "/usr/lib/postgresql/16/bin",
                  "/usr/lib/postgresql/17/bin", "/usr/lib/postgresql/15/bin"]
ENV = {**os.environ, "LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"}


def find_bin() -> str | None:
    for candidate in CANDIDATE_BINS:
        if candidate and Path(candidate, "initdb").exists():
            return candidate
    found = shutil.which("initdb")
    return str(Path(found).parent) if found else None


PG_BIN = find_bin()
pytestmark = pytest.mark.skipif(PG_BIN is None, reason="needs PostgreSQL binaries (initdb)")


class Cluster:
    def __init__(self, bin_dir: str) -> None:
        self.bin = bin_dir
        self.dir = Path(tempfile.mkdtemp(prefix="wms-rls-"))
        self.sock = self.dir / "sock"
        self.sock.mkdir()
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        self.port = probe.getsockname()[1]
        probe.close()
        self.run([f"{bin_dir}/initdb", "-D", str(self.dir / "data"), "-A", "trust", "-U", "postgres",
                  "--locale=en_US.UTF-8", "-E", "UTF8", "--wal-segsize=1"])
        self.run([f"{bin_dir}/pg_ctl", "-D", str(self.dir / "data"), "-o",
                  f"-p {self.port} -k {self.sock} -c listen_addresses='' -c fsync=off "
                  "-c max_wal_size=32MB -c min_wal_size=4MB -c shared_buffers=16MB", "-l", str(self.dir / "log"),
                  "-w", "start"])
        self.run([f"{bin_dir}/createdb", "-h", str(self.sock), "-p", str(self.port), "-U", "postgres", "wms"])

    @staticmethod
    def run(argv: list[str]) -> None:
        subprocess.run(argv, check=True, capture_output=True, env=ENV)

    def stop(self) -> None:
        subprocess.run([f"{self.bin}/pg_ctl", "-D", str(self.dir / "data"), "-m", "immediate", "stop"],
                       capture_output=True, env=ENV)
        shutil.rmtree(self.dir, ignore_errors=True)

    def psql_base(self) -> list[str]:
        return [f"{self.bin}/psql", "-h", str(self.sock), "-p", str(self.port)]

    def q(self, role: str, sql: str, *flags: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([*self.psql_base(), "-U", role, "-d", "wms", "-X", "-tA", "-F", "|", "-v", "ON_ERROR_STOP=1", *flags],
                              input=sql, capture_output=True, text=True, env=ENV, timeout=120)

    def gateway_env(self) -> dict[str, str]:
        return {**ENV, "AGENT_DB_PSQL": json.dumps(self.psql_base()), "AGENT_DB_NAME": "wms"}


class Seeder:
    """Универсальный посев: проверки внешних ключей выключены, значения подбираются по типам колонок."""

    def __init__(self, cluster: Cluster) -> None:
        import psycopg

        self.conn = psycopg.connect(f"host={cluster.sock} port={cluster.port} dbname=wms user=postgres", autocommit=True)
        self.conn.execute("SET session_replication_role = replica")
        self.counter = 0
        self.meta: dict[str, list[tuple[str, str, bool, bool, str]]] = {}

    def columns(self, table: str) -> list[tuple[str, str, bool, bool, str]]:
        if table not in self.meta:
            rows = self.conn.execute(
                "SELECT a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull, a.atthasdef, t.typtype "
                "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_type t ON t.oid = a.atttypid "
                "WHERE c.relname = %s AND c.relnamespace = 'public'::regnamespace AND a.attnum > 0 "
                "AND NOT a.attisdropped AND a.attgenerated = ''", (table,)).fetchall()
            self.meta[table] = [(r[0], r[1], r[2], r[3], r[4]) for r in rows]
        return self.meta[table]

    def value(self, table: str, name: str, typ: str, kind: str) -> str:
        self.counter += 1
        base = typ.split("(")[0]
        if kind == "e":
            label = self.conn.execute("SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                                      "WHERE format_type(t.oid, NULL) = %s ORDER BY enumsortorder LIMIT 1",
                                      (typ,)).fetchone()
            assert label, typ
            return str(label[0])
        if base == "uuid":
            return str(uuid.uuid4())
        if base in ("text", "character varying", "character"):
            return f"{name[:8]}-{self.counter}"[: max(int(typ.split("(")[1].rstrip(")")) if "(" in typ else 99, 1)]
        if base in ("integer", "bigint", "smallint"):
            return str(self.counter % 30000)
        if base in ("numeric", "double precision", "real"):
            return "1"
        if base == "boolean":
            return "false"
        if base.startswith("timestamp"):
            return "2026-10-02 12:00:00"
        if base == "date":
            return "2026-10-02"
        if base in ("jsonb", "json"):
            return "{}"
        if typ.endswith("[]"):
            return "{}"
        if base == "bytea":
            return "\\x00"
        if base.startswith("interval"):
            return "0 seconds"
        raise AssertionError(f"unsupported type {typ} for {table}.{name}")

    def insert(self, table: str, **given: Any) -> str:
        cols, vals, casts = [], [], []
        for name, typ, notnull, hasdef, kind in self.columns(table):
            if name in given:
                v = given[name]
            elif name == "id" and typ == "uuid":
                v = str(uuid.uuid4())
            elif notnull and not hasdef:
                v = self.value(table, name, typ, kind)
            else:
                continue
            cols.append(f'"{name}"')
            vals.append(None if v is None else str(v))
            casts.append(f"%s::{typ}")
        sql = f'INSERT INTO public."{table}" ({", ".join(cols)}) VALUES ({", ".join(casts)}) RETURNING '
        sql += '"id"::text' if any(c[0] == "id" for c in self.columns(table)) else "1::text"
        row = self.conn.execute(sql, vals).fetchone()
        assert row is not None
        return str(row[0])


class World:
    def __init__(self, cluster: Cluster) -> None:
        self.cluster = cluster
        self.seed = Seeder(cluster)
        s = self.seed
        self.tenants = {"T1": s.insert("tenants", name="Фулфилмент 1", slug="t1"),
                        "T2": s.insert("tenants", name="Фулфилмент 2", slug="t2")}
        # S1 и S2 в одном фулфилменте, S3 в другом, S1b с тем же названием, что S1, в другом фулфилменте
        self.sellers = {
            "S1": (s.insert("sellers", tenant_id=self.tenants["T1"], name="ИП Иванов"), self.tenants["T1"]),
            "S2": (s.insert("sellers", tenant_id=self.tenants["T1"], name="ИП Петров"), self.tenants["T1"]),
            "S3": (s.insert("sellers", tenant_id=self.tenants["T2"], name="ИП Сидоров"), self.tenants["T2"]),
            "S1b": (s.insert("sellers", tenant_id=self.tenants["T2"], name="ИП Иванов"), self.tenants["T2"]),
        }
        self.rows: dict[str, dict[str, list[str]]] = {}
        self.cache: dict[tuple[str, str], str] = {}
        for tag in self.sellers:
            for t in sa.TABLES:
                if t.kind != "self":
                    self.rows.setdefault(t.name, {}).setdefault(tag, [])
        for tag in self.sellers:
            for t in sa.TABLES:
                if t.kind == "self":
                    continue
                for variant in range(2):
                    self.build(t.name, tag, variant, top=True)
        self.conflict_rows: list[tuple[str, str]] = []
        self.ghosts()

    def build(self, table: str, tag: str, variant: int, top: bool = False) -> str:
        spec = sa.BY_NAME[table]
        seller_id, tenant_id = self.sellers[tag]
        given: dict[str, Any] = {}
        if "tenant_id" in {c[0] for c in self.seed.columns(table)}:
            given["tenant_id"] = tenant_id
        if spec.kind == "direct":
            given[spec.seller_col] = seller_id
        else:
            for col, parent in spec.hops:
                key = (parent, tag + str(variant))
                if key not in self.cache:
                    self.cache[key] = self.build(parent, tag, variant)
                given[col] = self.cache[key]
        new_id = self.seed.insert(table, **given)
        self.rows[table][tag].append(new_id)  # учитываем и промежуточных родителей
        return new_id

    def ghosts(self) -> None:
        """Строки без пути к селлеру (родитель не существует): не видны никому."""
        self.ghost_counts: dict[str, int] = {}
        for t in sa.TABLES:
            if t.kind not in ("via", "all_present"):
                continue
            given = {col: str(uuid.uuid4()) for col, _ in t.hops}
            if "tenant_id" in {c[0] for c in self.seed.columns(t.name)}:
                given["tenant_id"] = self.tenants["T1"]
            self.seed.insert(t.name, **given)
            self.ghost_counts[t.name] = 1
        # конфликт: задача упаковки с выгрузкой S1 и приёмкой S2 не видна ни тому, ни другому
        s1, s2 = self.sellers["S1"][0], self.sellers["S2"][0]
        mu = self.seed.insert("marketplace_unload_requests", seller_id=s1, tenant_id=self.tenants["T1"])
        ib = self.seed.insert("inbound_intake_requests", seller_id=s2, tenant_id=self.tenants["T1"])
        self.rows["marketplace_unload_requests"]["S1"].append(mu)
        self.rows["inbound_intake_requests"]["S2"].append(ib)
        self.conflict_task = self.seed.insert("packaging_tasks", tenant_id=self.tenants["T1"],
                                              marketplace_unload_request_id=mu, inbound_intake_request_id=ib)
        # задача без обоих родителей: не видна никому
        self.orphan_task = self.seed.insert("packaging_tasks", tenant_id=self.tenants["T1"])

    def role(self, tag: str) -> str:
        return sa.role_name(self.sellers[tag][0])


@pytest.fixture(scope="module")
def cluster() -> Iterator[Cluster]:
    assert PG_BIN
    c = Cluster(PG_BIN)
    try:
        yield c
    finally:
        c.stop()


@pytest.fixture(scope="module")
def world(cluster: Cluster) -> World:
    import importlib
    import pkgutil

    from sqlalchemy import create_engine

    import app.models
    from app.models.base import Base

    for mod in pkgutil.iter_modules(app.models.__path__):
        importlib.import_module(f"app.models.{mod.name}")
    engine = create_engine(f"postgresql+psycopg://postgres@/wms?host={cluster.sock}&port={cluster.port}")
    Base.metadata.create_all(engine)
    engine.dispose()
    # Для посева: проверочные и уникальные ограничения не нужны (значения подбираются автоматически).
    prep = cluster.q("postgres", """
        DO $$ DECLARE r record; BEGIN
          FOR r IN SELECT conrelid::regclass AS t, conname FROM pg_constraint
                   WHERE connamespace = 'public'::regnamespace AND contype IN ('c', 'u', 'x') LOOP
            EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I CASCADE', r.t, r.conname);
          END LOOP;
          FOR r IN SELECT i.indexrelid::regclass AS ix FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid
                   WHERE c.relnamespace = 'public'::regnamespace AND i.indisunique AND NOT i.indisprimary
                         AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid = i.indexrelid) LOOP
            EXECUTE format('DROP INDEX %s CASCADE', r.ix);
          END LOOP;
        END $$;
        CREATE ROLE wms_agent_ro LOGIN NOSUPERUSER;
        GRANT SELECT ON ALL TABLES IN SCHEMA public TO wms_agent_ro;
        CREATE FUNCTION public.leak_all_products() RETURNS bigint LANGUAGE sql SECURITY DEFINER
          AS $f$ SELECT count(*) FROM public.products $f$;
        CREATE VIEW public.v_all_products AS SELECT id, seller_id FROM public.products;
    """)
    assert prep.returncode == 0, prep.stderr
    w = World(cluster)
    for tag in w.sellers:
        res = subprocess.run([sys.executable, str(ROOT / "scripts" / "agent_db" / "gateway.py")],
                             env={**cluster.gateway_env(), "SSH_ORIGINAL_COMMAND": f"ensure-seller {w.sellers[tag][0]}"},
                             capture_output=True, text=True)
        assert res.returncode == 0 and res.stdout.startswith("ok role="), res.stderr
    return w


def ids_by_table(cluster: Cluster, role: str, tables: list[str]) -> dict[str, list[str]]:
    sql = " UNION ALL ".join(f"SELECT '{t}', \"id\"::text FROM {t}" for t in tables)
    res = cluster.q(role, sql + " ORDER BY 1, 2;")
    assert res.returncode == 0, res.stderr
    out: dict[str, list[str]] = {t: [] for t in tables}
    for line in res.stdout.splitlines():
        t, i = line.split("|")
        out[t].append(i)
    return out


def tables_with_id(world: World, tables: list[str]) -> list[str]:
    return [t for t in tables if any(c[0] == "id" for c in world.seed.columns(t))]


def allowed(world: World) -> list[str]:
    return [t.name for t in sa.TABLES]


# ------------------------------------------------------------------------------ спецификация и политики
def test_spec_matches_models_and_has_no_cycles() -> None:
    import importlib
    import pkgutil

    import app.models
    from app.models.base import Base

    for mod in pkgutil.iter_modules(app.models.__path__):
        importlib.import_module(f"app.models.{mod.name}")
    tables = Base.metadata.tables
    for t in sa.TABLES:
        assert t.name in tables, t.name
        cols = tables[t.name].columns
        for col in sa._path_columns(t):
            assert col in cols, (t.name, col)
        for col, parent in t.hops:
            fks = [fk.column.table.name for fk in cols[col].foreign_keys]
            assert parent in fks, (t.name, col, parent, fks)  # путь повторяет настоящий внешний ключ
            assert "id" in tables[parent].columns
        if t.kind == "direct":
            targets = {fk.column.table.name for fk in cols[t.seller_col].foreign_keys}
            assert targets <= {"sellers", "products", "withdrawal_operations", "withdrawal_documents"}, targets
    seen: set[str] = set()

    def walk(name: str, stack: tuple[str, ...]) -> None:
        assert name not in stack, f"цикл {(*stack, name)}"
        for _, parent in sa.BY_NAME[name].hops:
            walk(parent, (*stack, name))
        seen.add(name)

    for t in sa.TABLES:
        walk(t.name, ())
    for table, secrets in sa.SECRET_COLUMNS.items():
        if table in tables:
            for col in secrets:
                assert col in tables[table].columns, (table, col)


def test_every_listed_table_gets_rls_and_exactly_one_policy_for_the_role(cluster: Cluster, world: World) -> None:
    role = world.role("S1")
    res = cluster.q("postgres", f"SELECT tablename, roles::text FROM pg_policies WHERE policyname = 'agent_{role[12:]}' "
                                "ORDER BY 1;")
    rows = dict(line.split("|") for line in res.stdout.splitlines())
    assert set(rows) == set(allowed(world)) - {"sellers"} | {"sellers"}
    assert all(v == f"{{{role}}}" for v in rows.values())
    rls = cluster.q("postgres", "SELECT relname FROM pg_class WHERE relrowsecurity AND relnamespace = 'public'::regnamespace")
    assert set(rls.stdout.split()) >= set(allowed(world))
    # таблицы вне списка RLS не получили и роли недоступны
    assert not (set(rls.stdout.split()) - set(allowed(world)))


def test_role_attributes_are_minimal(cluster: Cluster, world: World) -> None:
    role = world.role("S1")
    res = cluster.q("postgres", f"SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls, rolinherit, "
                                f"rolcanlogin, rolconnlimit FROM pg_roles WHERE rolname = '{role}'")
    assert res.stdout.strip() == "f|f|f|f|f|f|t|8"
    conf = cluster.q("postgres", f"SELECT unnest(setconfig) FROM pg_db_role_setting s JOIN pg_roles r ON r.oid = s.setrole "
                                 f"WHERE r.rolname = '{role}'").stdout
    for needle in ("default_transaction_read_only=on", "statement_timeout=20s", "row_security=on"):
        assert needle in conf
    members = cluster.q("postgres", f"SELECT count(*) FROM pg_auth_members WHERE member = '{role}'::regrole").stdout.strip()
    assert members == "0"


# ------------------------------------------------------------------------------ C38: чужих строк нет нигде
@pytest.mark.parametrize("tag", ["S1", "S2", "S3", "S1b"])
def test_each_role_sees_exactly_its_own_rows_in_every_allowed_table(cluster: Cluster, world: World, tag: str) -> None:
    tables = tables_with_id(world, [t for t in allowed(world) if t != "sellers"])
    got = ids_by_table(cluster, world.role(tag), tables)
    for t in tables:
        expected = sorted(world.rows[t][tag])
        assert got[t] == expected, (tag, t, got[t], expected)
    own = cluster.q(world.role(tag), "SELECT id::text FROM sellers").stdout.split()
    assert own == [world.sellers[tag][0]]  # собственная строка, чужих селлеров нет (в том числе того же фулфилмента)
    tail = [t for t in allowed(world) if t not in tables and t != "sellers"]
    for t in tail:  # таблицы без id (редкие листья) сверяются по количеству
        count = int(cluster.q(world.role(tag), f"SELECT count(*) FROM {t}").stdout.strip())
        assert count == len(world.rows[t][tag]), (tag, t, count)


def test_conflicting_and_orphan_rows_are_visible_to_nobody(cluster: Cluster, world: World) -> None:
    for tag in world.sellers:
        ids = cluster.q(world.role(tag), "SELECT id::text FROM packaging_tasks").stdout.split()
        assert world.conflict_task not in ids and world.orphan_task not in ids
        for t in world.ghost_counts:
            visible = int(cluster.q(world.role(tag), f"SELECT count(*) FROM {t}").stdout.strip())
            assert visible == len(world.rows[t][tag]), (tag, t)  # призрачные строки не добавились


def test_tables_outside_the_list_and_secret_columns_are_denied(cluster: Cluster, world: World) -> None:
    from app.models.base import Base

    role = world.role("S1")
    listed = set(allowed(world))
    others = sorted(t for t in Base.metadata.tables if t not in listed)
    assert {"users", "tenants", "warehouses", "storage_locations", "marketplace_accounts", "notifications",
            "seller_marking_credentials", "seller_wildberries_credentials", "print_connections"} <= set(others)
    script = "\n".join(f"SELECT 1 FROM {t} LIMIT 1;" for t in others)
    res = cluster.q(role, script, "-v", "ON_ERROR_STOP=0")
    assert res.stderr.count("permission denied") == len(others), res.stderr
    assert not res.stdout.strip()  # ни одной строки
    secrets = [(t, c) for t in sa.TABLES for c in world.seed.meta.get(t.name, [])
               if sa.is_secret(t.name, c[0]) and c[0] not in sa._required_columns(t)]
    named = [(t.name, c) for t in sa.TABLES for c in sa.SECRET_COLUMNS.get(t.name, set())]
    assert ("withdrawal_documents", "signature") in named and ("withdrawal_operations", "token_enc") in named
    probe = [f"SELECT {c} FROM {t} LIMIT 1;" for t, c in named]
    probe += [f"SELECT \"{c[0]}\" FROM {t.name} LIMIT 1;" for t, c in secrets]
    res = cluster.q(role, "\n".join(probe), "-v", "ON_ERROR_STOP=0")
    assert res.stderr.count("permission denied") == len(probe), res.stderr
    star = cluster.q(role, "SELECT * FROM withdrawal_documents", "-v", "ON_ERROR_STOP=0")
    assert "permission denied" in star.stderr  # SELECT * по таблице с секретной колонкой запрещён


# ------------------------------------------------------------------------------ обходы
def total_products(world: World) -> int:
    return sum(len(v) for v in world.rows["products"].values())


def only_own(world: World, tag: str, out: str) -> bool:
    others = [v[0] for k, v in world.sellers.items() if k != tag]
    return not any(o in out for o in others)


def test_where_join_union_subquery_aggregate_never_show_foreign_rows(cluster: Cluster, world: World) -> None:
    role = world.role("S1")
    s1, s2, s3 = (world.sellers[k][0] for k in ("S1", "S2", "S3"))
    queries = [
        f"SELECT count(*) FROM products WHERE seller_id = '{s2}'",
        f"SELECT count(*) FROM products WHERE seller_id <> '{s1}'",
        "SELECT count(*) FROM products p JOIN inventory_balances b ON b.product_id = p.id WHERE p.seller_id <> "
        f"'{s1}'",
        f"SELECT count(*) FROM (SELECT seller_id FROM products UNION ALL SELECT seller_id FROM fbs_orders) x "
        f"WHERE seller_id IN ('{s2}', '{s3}')",
        f"SELECT count(*) FROM inventory_balances WHERE product_id IN (SELECT id FROM products WHERE seller_id = '{s2}')",
        f"SELECT count(*) FROM fbs_order_products WHERE order_id IN (SELECT id FROM fbs_orders WHERE seller_id = '{s2}')",
        f"SELECT count(*) FROM fbs_order_pick_events e JOIN fbs_order_picks p ON p.id = e.pick_id JOIN fbs_orders o "
        f"ON o.id = p.fbs_order_id WHERE o.seller_id = '{s3}'",
        f"WITH x AS (SELECT * FROM products) SELECT count(*) FROM x WHERE seller_id = '{s2}'",
        f"SELECT count(*) FROM products WHERE EXISTS (SELECT 1 FROM sellers WHERE id = '{s2}')",
        f"SELECT count(*) FROM sellers WHERE id IN ('{s2}', '{s3}')",
        f"SELECT count(*) FROM products WHERE seller_id = '{s2}' UNION ALL SELECT count(*) FROM fbs_orders "
        f"WHERE seller_id = '{s2}'",
        "SELECT sum(1) FILTER (WHERE seller_id <> '" + s1 + "') FROM products",
    ]
    for sql in queries:
        res = cluster.q(role, sql)
        assert res.returncode == 0, (sql, res.stderr)
        assert set(res.stdout.split()) <= {"0", ""} or "FILTER" in sql, (sql, res.stdout)
    # «OR true» возвращает всё видимое роли, то есть только строки селлера 1
    wide = cluster.q(role, f"SELECT count(*), count(*) FILTER (WHERE seller_id = '{s1}') FROM products WHERE seller_id = "
                           f"'{s2}' OR true").stdout.strip().split("|")
    assert wide[0] == wide[1] == str(len(world.rows["products"]["S1"]))
    # без фильтра: ровно строки селлера 1
    rows = cluster.q(role, "SELECT DISTINCT seller_id::text FROM products").stdout.split()
    assert rows == [s1]
    both = cluster.q(role, "SELECT DISTINCT seller_id::text FROM (SELECT seller_id FROM products UNION SELECT seller_id "
                           "FROM fbs_orders UNION SELECT seller_id FROM inventory_movements) x").stdout.split()
    assert both == [s1]


@pytest.mark.parametrize("sql, needle", [
    ("SET ROLE postgres", "permission denied"),
    ("SET ROLE {other}", "permission denied"),
    ("SET SESSION AUTHORIZATION postgres", "permission denied"),
    ("SELECT set_config('role', 'postgres', false)", "permission denied"),
    ("RESET ROLE; SET ROLE wms_agent_ro", "permission denied"),
    ("SELECT pg_read_file('/etc/passwd')", "permission denied"),
    ("SELECT lo_import('/etc/passwd')", "permission denied"),
    ("COPY products TO '/tmp/leak.csv'", "permission denied"),
    ("COPY products TO PROGRAM 'id'", "permission denied"),
    ("SELECT * FROM pg_authid", "permission denied"),
    ("SELECT public.leak_all_products()", "permission denied"),
    ("SELECT * FROM public.v_all_products", "permission denied"),
    ("INSERT INTO products (id) VALUES (gen_random_uuid())", "permission denied"),
    ("UPDATE products SET id = id", "permission denied"),
    ("DELETE FROM products", "permission denied"),
    ("TRUNCATE products", "permission denied"),
    ("CREATE TABLE public.leak (a int)", "permission denied"),
    ("DROP TABLE products", "must be owner"),
    ("ALTER TABLE products DISABLE ROW LEVEL SECURITY", "must be owner"),
    ("DROP POLICY agent_{hex} ON products", "must be owner"),
    ("GRANT SELECT ON products TO PUBLIC", "permission denied"),
    ("ALTER ROLE {me} BYPASSRLS", "permission denied"),
    ("ALTER ROLE {me} SUPERUSER", "permission denied"),
    ("CREATE ROLE evil", "permission denied"),
    ("SET default_transaction_read_only = off; INSERT INTO products (id) VALUES (gen_random_uuid())",
     "permission denied"),
    ("BEGIN READ WRITE; DELETE FROM products; COMMIT", "permission denied"),
    ("SELECT dblink('x', 'y')", "does not exist"),
])
def test_escape_and_write_attempts_fail(cluster: Cluster, world: World, sql: str, needle: str) -> None:
    sql = sql.format(other=world.role("S2"), me=world.role("S1"), hex=world.role("S1")[12:])
    plain = cluster.q(world.role("S1"), sql, "-v", "ON_ERROR_STOP=1")
    assert plain.returncode != 0 and (needle in plain.stderr or "read-only transaction" in plain.stderr), (
        sql, plain.stderr)
    # с выключенной настройкой read-only отказывают сами права
    bare = "BEGIN READ WRITE" in sql or "default_transaction_read_only" in sql
    strict = cluster.q(world.role("S1"), sql if bare else f"SET default_transaction_read_only = off; {sql}",
                       "-v", "ON_ERROR_STOP=1")
    assert strict.returncode != 0 and needle in strict.stderr, (sql, strict.stderr, strict.stdout)
    # после попытки данные и граница целы
    assert cluster.q("postgres", "SELECT count(*) FROM products").stdout.strip() == str(total_products(world))


@pytest.mark.parametrize("sql", [
    "INSERT INTO products (id) VALUES (gen_random_uuid())", "UPDATE products SET id = id", "DELETE FROM products",
    "TRUNCATE products", "CREATE TABLE public.leak (a int)", "CREATE SCHEMA leak", "CREATE FUNCTION public.f() RETURNS int "
    "LANGUAGE sql AS 'select 1'", "INSERT INTO inventory_balances (id) VALUES (gen_random_uuid())",
    "UPDATE sellers SET name = 'x'", "DELETE FROM fbs_orders",
])
def test_writes_are_denied_by_privileges_even_when_the_read_only_setting_is_switched_off(
    cluster: Cluster, world: World, sql: str
) -> None:
    """Настоящая граница записи: у роли нет прав, а не только настройки сессии."""
    res = cluster.q(world.role("S1"), f"SET default_transaction_read_only = off; BEGIN READ WRITE; {sql}; COMMIT;",
                    "-v", "ON_ERROR_STOP=1")
    assert res.returncode != 0 and "permission denied" in res.stderr, (sql, res.stderr)


def test_row_security_cannot_be_switched_off_to_widen_the_view(cluster: Cluster, world: World) -> None:
    role = world.role("S1")
    for prefix in ("SET row_security = off;", "SELECT set_config('row_security', 'off', false);",
                   "SET default_transaction_read_only = off; SET row_security = off;"):
        res = cluster.q(role, f"{prefix} SELECT DISTINCT seller_id::text FROM products;", "-v", "ON_ERROR_STOP=0")
        shown = set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", res.stdout))
        assert shown <= {world.sellers["S1"][0]} and world.sellers["S2"][0] not in res.stdout


def test_temp_tables_do_not_shadow_or_widen(cluster: Cluster, world: World) -> None:
    role = world.role("S1")
    blocked = cluster.q(role, "CREATE TEMP TABLE products (id uuid, seller_id uuid)")
    assert blocked.returncode != 0 and "read-only transaction" in blocked.stderr
    res = cluster.q(role, "SET default_transaction_read_only = off; CREATE TEMP TABLE products (id uuid, seller_id uuid); "
                          "SELECT count(*) FROM pg_temp.products; SELECT count(*) FROM public.products;")
    assert res.returncode == 0, res.stderr
    assert res.stdout.split()[-2:] == ["0", str(len(world.rows["products"]["S1"]))]  # своя пустая; в public только селлер 1


def test_postgres_and_shared_role_keep_their_access(cluster: Cluster, world: World) -> None:
    total = str(total_products(world))
    assert cluster.q("postgres", "SELECT count(*) FROM products").stdout.strip() == total  # RLS приложение не затрагивает
    assert cluster.q("wms_agent_ro", "SELECT count(*) FROM products").stdout.strip() == total  # общая роль цела


def test_catalog_and_security_definer_functions_are_not_a_leak(cluster: Cluster, world: World) -> None:
    role = world.role("S1")
    secdef = cluster.q("postgres", "SELECT p.oid::regprocedure::text FROM pg_proc p JOIN pg_namespace n ON n.oid = "
                                   "p.pronamespace WHERE p.prosecdef AND n.nspname = 'public'").stdout.split()
    assert secdef == ["leak_all_products()"]
    # контроль: без отзыва функция показывает ВСЕ строки (проверяется суперпользователем, не ролью агента)
    assert cluster.q("postgres", "SELECT public.leak_all_products()").stdout.strip() == str(total_products(world))
    res = cluster.q(role, "SELECT public.leak_all_products()")
    assert res.returncode != 0 and "permission denied" in res.stderr
    assert cluster.q(role, "SELECT current_setting('is_superuser')").stdout.strip() == "off"


# ------------------------------------------------------------------------------ C39: остаток
def test_stock_by_article_is_only_the_sellers_own(cluster: Cluster, world: World) -> None:
    s = world.seed
    names = {}
    for tag, qty in (("S1", 5), ("S2", 700)):
        sid, tid = world.sellers[tag]
        pid = s.insert("products", tenant_id=tid, seller_id=sid, name="Общий артикул", sku_code="ART-1")
        s.insert("inventory_balances", tenant_id=tid, product_id=pid, quantity=qty)
        names[tag] = pid
    role = world.role("S1")
    res = cluster.q(role, "SELECT p.sku_code, sum(b.quantity)::int FROM products p JOIN inventory_balances b ON b.product_id = "
                          "p.id WHERE p.sku_code = 'ART-1' GROUP BY p.sku_code")
    assert res.stdout.strip() == "ART-1|5"  # чужие 700 не суммируются
    total = cluster.q(role, "SELECT coalesce(sum(quantity), 0)::int FROM inventory_balances").stdout.strip()
    own = sum(1 for _ in world.rows["inventory_balances"]["S1"]) + 5
    assert int(total) >= 5 and cluster.q("postgres", "SELECT sum(quantity)::int FROM inventory_balances").stdout.strip() != total
    assert own >= 5


# ------------------------------------------------------------------------------ идемпотентность и новые таблицы
def test_ensure_is_idempotent_and_new_tables_are_not_granted_automatically(cluster: Cluster, world: World) -> None:
    env = cluster.gateway_env()
    before = cluster.q("postgres", "SELECT count(*) FROM pg_policies").stdout.strip()
    sid = world.sellers["S1"][0]
    again = gateway.ensure_seller(sid, env)
    assert again.startswith("ok role=") and cluster.q("postgres", "SELECT count(*) FROM pg_policies").stdout.strip() == before
    cluster.q("postgres", "CREATE TABLE public.brand_new (id uuid, seller_id uuid); INSERT INTO public.brand_new "
                          f"VALUES (gen_random_uuid(), '{sid}')")
    gateway.ensure_seller(sid, env)
    res = cluster.q(world.role("S1"), "SELECT * FROM brand_new")
    assert res.returncode != 0 and "permission denied" in res.stderr  # новая таблица не в списке: закрыта
    cluster.q("postgres", "DROP TABLE public.brand_new")


def test_missing_table_or_column_in_the_database_is_skipped_not_guessed() -> None:
    cat = sa.Catalog(columns={"products": ["id", "seller_id", "name"], "fbs_orders": ["id", "name"],
                              "fbs_order_products": ["id", "order_id"], "inventory_balances": ["id", "product_id"]})
    sql = sa.render_sql(str(uuid.uuid4()), cat)
    assert 'ON public."products"' in sql and 'ON public."inventory_balances"' in sql
    assert '"fbs_orders"' not in sql  # нет seller_id: таблица исключена
    assert '"fbs_order_products"' not in sql  # родитель исключён: потомок тоже
    assert "BYPASSRLS" not in sql.replace("NOBYPASSRLS", "")


def test_generator_validates_inputs_and_hides_secret_names() -> None:
    for bad in ("", "x", "1111", "11111111-1111-1111-1111-11111111111", "11111111-1111-1111-1111-1111111111111", "'; drop",
                "ZZZZZZZZ-1111-1111-1111-111111111111"):
        with pytest.raises(sa.SpecError):
            sa.role_name(bad)
    with pytest.raises(sa.SpecError):
        sa.seller_from_role("wms_agent_s_xyz")
    sid = "0b8da5d8-f43a-42f5-a2ec-43173ea844bd"
    assert sa.seller_from_role(sa.role_name(sid)) == sid
    cols = ["id", "seller_id", "password_hash", "api_key", "x_token", "name", "signature", "auth_challenge",
            "marker_enc", "title"]
    assert sa.allowed_columns("anything", cols, {"id", "seller_id"}) == ["id", "name", "seller_id", "title"]  # порядок детерминирован (сортировка)
    cat = sa.Catalog(columns={"products": cols}, secdef_functions=["public.f(); DROP TABLE x"])
    with pytest.raises(sa.SpecError):
        sa.render_sql(sid, cat)


# ------------------------------------------------------------------------------ шлюз
def run_gateway(cluster: Cluster, command: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "agent_db" / "gateway.py")],
                          env={**cluster.gateway_env(), "SSH_ORIGINAL_COMMAND": command}, input=stdin,
                          capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("command", [
    "", "ls", "sql wms_agent_ro", "sql postgres", "sql wms_agent_s_XYZ", "sql wms_agent_s_" + "a" * 31,
    "sql wms_agent_s_" + "a" * 33, "sql wms_agent_s_" + "a" * 32 + " extra", "sql wms_agent_s_" + "a" * 32 + "; ls",
    "ensure-seller", "ensure-seller xyz", "ensure-seller 11111111-1111-1111-1111-111111111111; ls",
    "find-seller", "find-seller a", "find-seller " + "я" * 81, "find-seller x'; DROP TABLE sellers;--",
    "find-seller a%", "find-seller `id`", "find-seller $(id)", "find-seller a\\b", "bash -c id",
    "sql  wms_agent_s_" + "a" * 32, "SQL wms_agent_s_" + "a" * 32, "find-seller\tabc",
])
def test_gateway_refuses_everything_but_the_three_forms(cluster: Cluster, world: World, command: str) -> None:
    res = run_gateway(cluster, command, "SELECT 1")
    assert res.returncode == 2 and "refused" in res.stderr and res.stdout == ""


def test_gateway_sql_runs_under_the_sellers_role_and_returns_csv(cluster: Cluster, world: World) -> None:
    sid = world.sellers["S1"][0]
    res = run_gateway(cluster, f"sql {world.role('S1')}", "SELECT DISTINCT seller_id FROM products")
    assert res.returncode == 0 and res.stdout.strip().splitlines() == ["seller_id", sid]
    denied = run_gateway(cluster, f"sql {world.role('S1')}", "SELECT * FROM users")
    assert denied.returncode != 0 and "permission denied" in denied.stderr
    other = run_gateway(cluster, f"sql {world.role('S1')}", "SET ROLE postgres")
    assert other.returncode != 0


def test_gateway_find_seller_is_injection_safe_and_shows_both_same_name_candidates(cluster: Cluster, world: World) -> None:
    res = run_gateway(cluster, "find-seller Иванов")
    rows = list(csv.DictReader(io.StringIO(res.stdout)))
    assert res.returncode == 0 and {r["seller_id"] for r in rows} == {world.sellers["S1"][0], world.sellers["S1b"][0]}
    assert {r["tenant_name"] for r in rows} == {"Фулфилмент 1", "Фулфилмент 2"}
    assert [r for r in csv.DictReader(io.StringIO(run_gateway(cluster, "find-seller Несуществующий").stdout))] == []
    odd = run_gateway(cluster, "find-seller O'Brien \"x\" (ИП)")
    assert odd.returncode == 0 and "seller_id" in odd.stdout  # кавычки — данные, не SQL
    underscore = run_gateway(cluster, "find-seller И_ан")  # символ подстановки _ экранирован: совпадений нет
    assert [r for r in csv.DictReader(io.StringIO(underscore.stdout))] == []
    assert cluster.q("postgres", "SELECT count(*) FROM sellers").stdout.strip() == "4"  # ничего не удалено


def test_gateway_ensure_unknown_seller_is_refused(cluster: Cluster, world: World) -> None:
    res = run_gateway(cluster, f"ensure-seller {uuid.uuid4()}")
    assert res.returncode == 3 and "seller not found" in res.stderr
    assert cluster.q("postgres", "SELECT count(*) FROM pg_roles WHERE rolname LIKE 'wms_agent_s_%'").stdout.strip() == "4"


# ------------------------------------------------------------------------------ круг 8: N3 метакоманды psql
def sql_via_gateway(cluster: Cluster, world: World, stdin: str, tag: str = "S1",
                    extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {**cluster.gateway_env(), "SSH_ORIGINAL_COMMAND": f"sql {world.role(tag)}", **(extra_env or {})}
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "agent_db" / "gateway.py")], env=env, input=stdin,
                          capture_output=True, text=True, timeout=120)


def test_psql_meta_commands_never_reach_psql_through_the_gateway(cluster: Cluster, world: World, tmp_path: Path) -> None:
    marker = tmp_path / "SHELL_MARKER"
    attempts = [
        f"\\! touch {marker}",
        f"\\! touch {marker}\n",
        "\\connect wms postgres\nSELECT current_user, count(*) FROM sellers;",
        "\\c wms postgres\nSELECT current_user;",
        "SELECT 1\n\\gexec",
        "SELECT 'touch " + str(marker) + "' AS c \\gexec",
        "SELECT 1; \\! id",
        f"\\copy (select 1) to program 'touch {marker}'",
        "\\set VERBOSITY terse\nSELECT 1",
        "\\o /tmp/agent_probe_out\nSELECT 1",
        "SELECT E'\\n'",   # обратный слеш запрещён и в литерале
        "SELECT '\\'",
        "SELECT 1 \\g",
        "\\\\! id",
        "select 1\r\n\\! id",
    ]
    for stdin in attempts:
        res = sql_via_gateway(cluster, world, stdin)
        assert res.returncode == 3 and res.stderr.startswith("refused:"), (stdin, res.stderr)
        assert res.stdout == "", stdin
    assert not marker.exists()  # shell не запускался
    assert not Path("/tmp/agent_probe_out").exists()


def test_gateway_passes_the_query_by_dash_c_so_input_cannot_become_a_meta_command(cluster: Cluster, world: World) -> None:
    """Даже 'второй слой' (psql -c) получает только проверенную строку: проверяем, что штатные запросы идут."""
    ok = sql_via_gateway(cluster, world, "SELECT 1 AS n")
    assert ok.returncode == 0 and ok.stdout.splitlines() == ["n", "1"]
    multi = sql_via_gateway(cluster, world, "SELECT 1; SELECT 2")
    assert multi.returncode == 3 and "only one statement" in multi.stderr
    for bad in ("DELETE FROM products", "SET ROLE postgres", "SELECT pg_read_file('/etc/passwd')", "SELECT 1 -- x",
                "COPY products TO PROGRAM 'id'", "EXPLAIN ANALYZE SELECT 1", "SELECT * FROM products FOR UPDATE",
                "", "   ", "SELECT " + "x" * 9000):
        res = sql_via_gateway(cluster, world, bad)
        assert res.returncode == 3 and res.stdout == "", (bad[:40], res.stderr)


def test_non_utf8_and_oversized_stdin_are_refused_without_running_psql(cluster: Cluster, world: World) -> None:
    env = {**cluster.gateway_env(), "SSH_ORIGINAL_COMMAND": f"sql {world.role('S1')}"}
    gw = str(ROOT / "scripts" / "agent_db" / "gateway.py")
    bad = subprocess.run([sys.executable, gw], env=env, input=b"SELECT '\xff\xfe'", capture_output=True, timeout=60)
    assert bad.returncode == 3 and bad.stdout == b""
    big = subprocess.run([sys.executable, gw], env=env, input=b"SELECT " + b"1," * 200_000, capture_output=True, timeout=60)
    assert big.returncode == 3 and big.stdout == b""


def test_gateway_contract_matches_the_client_validator_on_one_corpus() -> None:
    sys.path.insert(0, str(ROOT / "tools" / "support_agent"))
    try:
        from support_agent import prod_sql as client
    finally:
        sys.path.pop(0)
    import sql_contract as server

    corpus = [
        "SELECT 1", "select * from t where a = 'x;y' and b = '--no'", "  SELECT 1;  ", "with a as (select 1) select * from a",
        "EXPLAIN select 1", "(select 1) union all (select 2)", "select $$a;b$$", "select 'it''s'",
        "insert into t values (1)", "update t set a=1", "delete from t", "drop table t", "copy t to '/tmp/x'",
        "select 1; select 2", "select 1 -- c", "select 1 /* c */", "explain analyze select 1", "select 1 into t",
        "select pg_read_file('/etc/passwd')", "select lo_import('x')", "select set_config('a','b',false)",
        "select nextval('s')", "select * from t for update", "\\! id", "select '\\'", "select E'\\n'",
        "\\connect wms postgres", "select 1\n\\gexec", "set role postgres", "", " ", "select 'a", 'select "a',
        "select $a$ x", "select 1\x00", "do $$ begin end $$", "call p()", "select pg_sleep(1)", "select dblink('a','b')",
        "with x as (delete from t returning *) select * from x", "values (1)", "table t", "show all",
        "SELECT 1 AS a$$; SELECT 2 AS b$$", "SELECT 1 AS a$tag$; COMMIT; SELECT 2 AS b$tag$", "select $1", "select '$'",
        'select "a$b" from t', "select $$a;b$$", "explain select 1 as a$$; commit; select 2 as b$$", "select 'a;b'",
    ]
    for sql in corpus:
        try:
            client.validate_sql(sql)
            client_ok = True
        except client.SqlRefused:
            client_ok = False
        try:
            server.validate_sql(sql)
            server_ok = True
        except server.SqlRefused:
            server_ok = False
        assert client_ok == server_ok, sql
    for text in ('ERROR:  22P02: invalid input syntax for type integer: "A"\nLOCATION: x', 'ERROR:  42703: column "f" does not exist',
                 "ERROR:  23505: duplicate key\nDETAIL: Key (a)=(S)", "psql: error: connection failed", ""):
        assert client.sanitize_error(text) == server.sanitize_error(text), text


# ------------------------------------------------------------------------------ круг 8: N2 бюджет вывода
def fake_psql(tmp_path: Path, body: str) -> dict[str, str]:
    script = tmp_path / "fake_psql.py"
    script.write_text("import sys\n" + body, encoding="utf-8")
    return {"AGENT_DB_PSQL": json.dumps([sys.executable, str(script)])}


def test_big_stdout_is_cut_by_budget_and_the_next_query_still_works(cluster: Cluster, world: World) -> None:
    import time

    started = time.time()
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "agent_db" / "gateway.py")],
                         env={**cluster.gateway_env(), "SSH_ORIGINAL_COMMAND": f"sql {world.role('S1')}"},
                         input=b"SELECT repeat('x', 8388608) AS big", capture_output=True, timeout=120)
    assert res.returncode == 125  # тот же код, что клиент трактует как «вывод оборван»
    assert 0 < len(res.stdout) <= 256 * 1024 and res.stdout.startswith(b"big\n")
    assert time.time() - started < 60
    nxt = sql_via_gateway(cluster, world, "SELECT 1 AS n")
    assert nxt.returncode == 0 and nxt.stdout.splitlines() == ["n", "1"]


def test_multibyte_field_is_cut_on_a_character_boundary(cluster: Cluster, world: World) -> None:
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "agent_db" / "gateway.py")],
                         env={**cluster.gateway_env(), "SSH_ORIGINAL_COMMAND": f"sql {world.role('S1')}"},
                         input="SELECT repeat('ю', 1000000) AS big".encode(), capture_output=True, timeout=120)
    assert res.returncode == 125
    text = res.stdout.decode("utf-8")  # не падает: ни одного разрезанного символа
    assert set(text.splitlines()[1]) == {"ю"} and len(res.stdout) <= 256 * 1024


def test_big_stderr_is_discarded_and_the_error_is_sanitised(tmp_path: Path, cluster: Cluster, world: World) -> None:
    env = fake_psql(tmp_path, "sys.stderr.write('ERROR:  22P02: invalid input syntax for type integer: \"SECRET_VALUE\"\\n'"
                              " + 'DETAIL: ' + 'y' * 3_000_000 + '\\n')\nsys.exit(3)\n")
    res = sql_via_gateway(cluster, world, "SELECT 1", extra_env=env)
    assert res.returncode == 3 and res.stdout == ""
    assert "SECRET_VALUE" not in res.stderr and res.stderr.startswith("22P02:") and len(res.stderr) < 400


def test_gateway_run_bounded_kills_a_silent_process_on_timeout() -> None:
    import gateway

    rc, out, _ = gateway.run_bounded([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1)
    assert rc == 124 and out == b""


def test_gateway_run_bounded_does_not_hang_on_a_noisy_stderr_and_cuts_stdout() -> None:
    import gateway

    code = "import sys; sys.stderr.write('e' * 2000000); sys.stdout.write('o' * 2000000)"
    rc, out, err = gateway.run_bounded([sys.executable, "-c", code], max_out=1000, max_err=500, timeout=30)
    assert rc == 125 and len(out) == 1000 and len(err) <= 500


# ------------------------------------------------------------------------------ круг 8: N1, текст ошибки без значений
def test_error_text_returned_by_the_gateway_has_no_data_values(cluster: Cluster, world: World) -> None:
    res = sql_via_gateway(cluster, world, "SELECT name::integer FROM sellers")
    assert res.returncode == 1 and res.stdout == ""  # код psql при ошибке запроса
    assert res.stderr.strip().startswith("22P02:") and "Иванов" not in res.stderr and "«…»" in res.stderr
    syntax = sql_via_gateway(cluster, world, "SELECT 1 FROM")
    assert syntax.stderr.startswith("42601:")
    denied = sql_via_gateway(cluster, world, "SELECT * FROM users")
    assert denied.stderr.startswith("42501:") and "permission denied for table users" in denied.stderr


# ------------------------------------------------------------------------------ круг 9: N4 и глубокая защита сессии
DOLLAR_TRICKS = [
    "SELECT 1 AS a$$; SELECT 2 AS b$$",
    "SELECT 1 AS a$tag$; SELECT 2 AS b$tag$",
    "EXPLAIN SELECT 1 AS a$$; COMMIT; SET default_transaction_read_only=off; "
    "ALTER ROLE CURRENT_USER SET statement_timeout=0; SELECT 2 AS b$$",
    "EXPLAIN SELECT 1 AS a$x$; COMMIT; ALTER ROLE CURRENT_USER SET statement_timeout=0; SELECT 2 AS b$x$",
    "SELECT $1", "SELECT '$'", "SELECT $$x$$", 'SELECT "a$b" FROM products', "SELECT 1 AS a$",
]


@pytest.mark.parametrize("sql", DOLLAR_TRICKS)
def test_any_dollar_sign_is_refused_before_psql_and_nothing_is_executed(cluster: Cluster, world: World, sql: str) -> None:
    res = sql_via_gateway(cluster, world, sql)
    assert res.returncode == 3 and "dollar sign" in res.stderr and res.stdout == ""
    settings = cluster.q("postgres", f"SELECT array_to_string(setconfig, ',') FROM pg_db_role_setting s "
                         f"JOIN pg_roles r ON r.oid = s.setrole WHERE r.rolname = '{world.role('S1')}'").stdout
    assert "statement_timeout=20s" in settings and "default_transaction_read_only=on" in settings


@pytest.mark.parametrize("sql", ["SELECT 1 AS a; SELECT 2 AS b", "EXPLAIN SELECT 1; COMMIT", "SELECT 1;;SELECT 2",
                                 "SELECT 'x'; SET default_transaction_read_only=off", "COMMIT", "ALTER ROLE CURRENT_USER SET statement_timeout=0"])
def test_second_statement_in_any_form_is_refused(cluster: Cluster, world: World, sql: str) -> None:
    res = sql_via_gateway(cluster, world, sql)
    assert res.returncode == 3 and res.stdout == ""


def test_normal_select_with_explain_still_work_and_a_semicolon_in_a_string_is_data(cluster: Cluster, world: World) -> None:
    assert sql_via_gateway(cluster, world, "SELECT 'a;b' AS x").stdout.splitlines() == ["x", "a;b"]
    assert sql_via_gateway(cluster, world, "WITH a AS (SELECT 1 AS n) SELECT n FROM a").stdout.splitlines() == ["n", "1"]
    explain = sql_via_gateway(cluster, world, "EXPLAIN SELECT id FROM products")
    assert explain.returncode == 0 and "QUERY PLAN" in explain.stdout
    assert sql_via_gateway(cluster, world, "SELECT 1 AS n;").stdout.splitlines() == ["n", "1"]  # один завершающий ;


def test_session_settings_override_a_tampered_role_and_ensure_restores_the_role(cluster: Cluster, world: World) -> None:
    role = world.role("S1")
    probe = ("SELECT current_setting('statement_timeout') AS t, current_setting('default_transaction_read_only') AS ro, "
             "current_setting('lock_timeout') AS l, current_setting('row_security') AS rs, current_setting('search_path') AS sp")
    cluster.q("postgres", f"ALTER ROLE {role} SET statement_timeout = 0; ALTER ROLE {role} SET default_transaction_read_only = off; "
                          f"ALTER ROLE {role} SET lock_timeout = 0; ALTER ROLE {role} SET search_path = pg_catalog;")
    # доказательство чувствительности: прямое подключение роли видит испорченные значения
    raw = cluster.q(role, probe)
    assert raw.returncode == 0 and raw.stdout.strip().startswith("0|off|0|")
    # через шлюз сессия навязывает свои значения поверх настроек роли
    res = sql_via_gateway(cluster, world, probe)
    rows = list(csv.DictReader(io.StringIO(res.stdout)))
    assert res.returncode == 0 and rows == [{"t": "20s", "ro": "on", "l": "3s", "rs": "on", "sp": "public,pg_catalog"}]
    write = sql_via_gateway(cluster, world, "SELECT 1 INTO TEMP TABLE x")  # запись по-прежнему закрыта
    assert write.returncode == 3
    # ensure при каждом вызове выставляет настройки роли заново
    again = run_gateway(cluster, f"ensure-seller {world.sellers['S1'][0]}")
    assert again.returncode == 0
    fixed = cluster.q(role, probe)
    assert fixed.stdout.strip().startswith("20s|on|3s|on|")


def test_gateway_session_guard_uses_a_connection_string_not_the_environment() -> None:
    argv = gateway.psql_argv("wms_agent_s_" + "a" * 32, ["-c", "SELECT 1"], {"AGENT_DB_PSQL": '["docker", "exec", "-i", "c", "psql"]'},
                             session_guard=True)
    target = argv[argv.index("-d") + 1]
    assert target.startswith("dbname=wms options='") and "default_transaction_read_only=on" in target
    assert "statement_timeout=20s" in target and "idle_in_transaction_session_timeout=30s" in target
    assert "-e" not in argv and "PGOPTIONS" not in " ".join(argv)  # не зависит от передачи окружения в docker exec
    with pytest.raises(ValueError):
        gateway.psql_argv("x", None, {"AGENT_DB_NAME": "wms options='-c x'"}, session_guard=True)


# ------------------------------------------------------------------------------ блокировки ensure-seller
class Holder:
    """Параллельная сессия с открытой транзакцией, держащей ACCESS EXCLUSIVE на таблице."""

    def __init__(self, cluster: Cluster, table: str = "products") -> None:
        import psycopg

        self.conn = psycopg.connect(f"host={cluster.sock} port={cluster.port} dbname=wms user=postgres")
        self.conn.execute(f"LOCK TABLE public.{table} IN ACCESS EXCLUSIVE MODE")

    def release(self) -> None:
        self.conn.rollback()
        self.conn.close()


def new_seller(world: World) -> str:
    return world.seed.insert("sellers", tenant_id=world.tenants["T1"], name="ИП Новый")


def role_policies(cluster: Cluster, role: str) -> list[str]:
    out = cluster.q("postgres", f"SELECT p.oid::text FROM pg_policy p WHERE '{role}'::regrole = ANY (p.polroles) ORDER BY p.oid")
    return [x for x in out.stdout.split() if x]


def role_comment(cluster: Cluster, role: str) -> str:
    return cluster.q("postgres", f"SELECT coalesce(shobj_description(oid, 'pg_authid'), '') FROM pg_roles WHERE rolname = '{role}'").stdout.strip()


def test_repeat_ensure_on_the_current_version_takes_no_table_locks(cluster: Cluster, world: World) -> None:
    import time

    sid = world.sellers["S1"][0]
    role = world.role("S1")
    first = run_gateway(cluster, f"ensure-seller {sid}")
    assert first.returncode == 0 and "state=unchanged" in first.stdout  # фикстура уже применила эту версию
    assert role_comment(cluster, role).startswith("wms-agent:")
    holder = Holder(cluster)
    try:
        started = time.time()
        again = run_gateway(cluster, f"ensure-seller {sid}")
        elapsed = time.time() - started
    finally:
        holder.release()
    assert again.returncode == 0 and "state=unchanged" in again.stdout
    assert elapsed < 1.5, elapsed  # без ожидания блокировки, которую держит другая транзакция


def test_first_ensure_waits_about_two_seconds_then_rolls_back_without_partial_policies(cluster: Cluster, world: World) -> None:
    import time

    sid = new_seller(world)
    role = sa.role_name(sid)
    holder = Holder(cluster)
    try:
        started = time.time()
        res = run_gateway(cluster, f"ensure-seller {sid}")
        elapsed = time.time() - started
    finally:
        holder.release()
    assert res.returncode == 3 and "lock timeout" in res.stderr and "retry later" in res.stderr
    assert 1.5 < elapsed < 15, elapsed  # lock_timeout 2 с, а не бесконечное ожидание
    assert cluster.q("postgres", f"SELECT count(*) FROM pg_roles WHERE rolname = '{role}'").stdout.strip() == "0"
    assert cluster.q("postgres", "SELECT count(*) FROM pg_policy WHERE polname = 'agent_" + sid.replace("-", "") + "'").stdout.strip() == "0"
    # после снятия блокировки повтор проходит
    ok = run_gateway(cluster, f"ensure-seller {sid}")
    assert ok.returncode == 0 and "state=applied" in ok.stdout
    n = int(re.search(r"tables=(\d+)", ok.stdout).group(1))  # type: ignore[union-attr]
    assert len(role_policies(cluster, role)) == n and n > 80
    assert role_comment(cluster, role) != ""


def test_other_queries_are_not_queued_behind_a_blocked_ensure(cluster: Cluster, world: World) -> None:
    """ACCESS EXCLUSIVE, ожидающий за долгой транзакцией, вешал бы очередь обычных запросов: теперь он снимается за 2 с."""
    import subprocess as sp
    import time

    sid = new_seller(world)
    reader = Holder(cluster)
    reader.conn.rollback()
    reader.conn.execute("SELECT count(*) FROM public.products")  # долгая транзакция читателя (ACCESS SHARE)
    try:
        proc = sp.Popen([sys.executable, str(ROOT / "scripts" / "agent_db" / "gateway.py")],
                        env={**cluster.gateway_env(), "SSH_ORIGINAL_COMMAND": f"ensure-seller {sid}"},
                        stdout=sp.PIPE, stderr=sp.PIPE, text=True)
        time.sleep(1.0)
        started = time.time()
        other = cluster.q("postgres", "SELECT count(*) FROM products")  # обычный запрос не должен зависнуть
        waited = time.time() - started
        proc.communicate(timeout=30)
    finally:
        reader.release()
    assert other.returncode == 0 and waited < 1.5, waited
    assert proc.returncode == 3  # ensure не дождался и откатился


def test_policies_are_recreated_only_when_the_policy_version_changes(cluster: Cluster, world: World) -> None:
    sid = world.sellers["S2"][0]
    role = world.role("S2")
    before = role_policies(cluster, role)
    pv, gv = sa.POLICY_VERSION, role_comment(cluster, role).split(":")[2]
    # изменилась только версия прав (миграция добавила колонку): политики те же, права пересчитаны
    cluster.q("postgres", f"COMMENT ON ROLE {role} IS 'wms-agent:{pv}:000000000000'")
    holder = Holder(cluster)  # любая табличная блокировка не мешает: политик и ENABLE RLS не трогаем
    try:
        res = run_gateway(cluster, f"ensure-seller {sid}")
    finally:
        holder.release()
    assert res.returncode == 0 and "state=applied" in res.stdout
    assert role_policies(cluster, role) == before and role_comment(cluster, role) == f"wms-agent:{pv}:{gv}"
    # изменилась версия политик (новый список путей): политики пересоздаются
    cluster.q("postgres", f"COMMENT ON ROLE {role} IS 'wms-agent:oldpolicy000:{gv}'")
    res = run_gateway(cluster, f"ensure-seller {sid}")
    assert res.returncode == 0 and "state=applied" in res.stdout
    after = role_policies(cluster, role)
    assert len(after) == len(before) and after != before  # другие oid: пересозданы
    assert role_comment(cluster, role) == f"wms-agent:{pv}:{gv}"


def test_role_settings_are_reapplied_on_every_ensure_even_when_current(cluster: Cluster, world: World) -> None:
    role = world.role("S3")
    cluster.q("postgres", f"ALTER ROLE {role} SET statement_timeout = 0")
    res = run_gateway(cluster, f"ensure-seller {world.sellers['S3'][0]}")
    assert res.returncode == 0 and "state=unchanged" in res.stdout
    assert cluster.q(role, "SELECT current_setting('statement_timeout')").stdout.strip() == "20s"


def test_rendered_script_has_lock_and_statement_timeouts_first() -> None:
    sql = sa.render_sql("11111111-2222-3333-4444-555555555555", sa.Catalog(columns={"products": ["id", "seller_id"]}))
    lines = sql.splitlines()
    begin = lines.index("BEGIN;")
    assert lines[begin + 1] == "SET LOCAL lock_timeout = '2s';" and lines[begin + 2] == "SET LOCAL statement_timeout = '60s';"
    role_only = sa.render_role_sql("11111111-2222-3333-4444-555555555555")
    assert "ENABLE ROW LEVEL SECURITY" not in role_only and "POLICY" not in role_only and "SET LOCAL lock_timeout" in role_only


def test_enable_rls_and_policies_are_emitted_only_where_missing() -> None:
    seller = "11111111-2222-3333-4444-555555555555"
    pol = "agent_" + seller.replace("-", "")
    cat = sa.Catalog(columns={"products": ["id", "seller_id"], "fbs_orders": ["id", "seller_id"]},
                     rls_enabled={"products"}, policies={("products", pol)})
    sql = sa.render_sql(seller, cat)
    assert 'ALTER TABLE public."products" ENABLE' not in sql and 'ALTER TABLE public."fbs_orders" ENABLE' in sql
    assert f'CREATE POLICY "{pol}" ON public."products"' not in sql and f'CREATE POLICY "{pol}" ON public."fbs_orders"' in sql
    assert "DROP POLICY" not in sql
    old = sa.Catalog(columns=cat.columns, rls_enabled={"products"}, policies={("products", pol)},
                     role_version="wms-agent:other:xxxx")
    assert f'DROP POLICY "{pol}" ON public."products"' in sa.render_sql(seller, old)
