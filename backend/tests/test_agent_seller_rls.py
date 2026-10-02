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
