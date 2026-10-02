"""WMS-641 R41: роль Postgres на каждого привязанного селлера, только чтение, строки только этого селлера.

Генератор SQL. Принцип fail closed:
  * доступны ТОЛЬКО таблицы из явного списка TABLES (новые таблицы автоматически не выдаются);
  * у каждой таблицы однозначный путь к селлеру: прямой seller_id, либо ссылка на родителя (документ,
    товар и т. п.), чья принадлежность селлеру выводится по seller_id; таблицы только с tenant_id и без
    пути (склады, ячейки, сотрудники, настройки) в список не входят;
  * выдаётся SELECT на явный список колонок без секретных (явный перечень + эвристика по именам);
  * на каждой таблице списка включается RLS и создаётся политика только для роли этого селлера
    (FORCE не нужен: владелец и postgres обходят RLS, приложение не затронуто);
  * общая роль wms_agent_ro (если есть) получает политику USING (true) на тех же таблицах, чтобы
    включённый RLS не лишил её прежнего доступа.
Роль LOGIN без пароля: вход только через локальный сокет внутри контейнера; NOINHERIT, не член ролей.
Реальная граница записи: у роли нет прав кроме SELECT и нет CREATE в схеме; default_transaction_read_only
и таймауты заданы дополнительно.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

SELLER_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
ROLE_PREFIX = "wms_agent_s_"
ROLE_RE = re.compile(r"^wms_agent_s_[0-9a-f]{32}$")
SHARED_RO_ROLE = "wms_agent_ro"


@dataclass(frozen=True)
class Table:
    name: str
    kind: str  # direct | via | all_present | self
    hops: tuple[tuple[str, str], ...] = ()  # (колонка этой таблицы, родительская таблица по id)
    seller_col: str = "seller_id"


def _direct(*names: str) -> list[Table]:
    return [Table(n, "direct") for n in names]


def _via(table: str, col: str, parent: str) -> Table:
    return Table(table, "via", ((col, parent),))


TABLES: list[Table] = [
    Table("sellers", "self"),  # собственная строка селлера: id = seller
    # --- прямой seller_id ---
    *_direct(
        "billing_invoices", "billing_invoices_v2", "billing_ledger_entries", "billing_profiles",
        "billing_run_issues", "billing_tariff_versions", "billing_tariff_versions_v2",
        "discrepancy_acts", "fbs_orders", "fbs_print_assets", "fbs_supplies", "fbs_warehouse_bindings",
        "fbs_wb_operations", "inbound_intake_requests", "inventory_counts", "inventory_movements",
        "kiz_reprints", "marketplace_unload_requests", "marking_code_events", "marking_code_imports",
        "marking_codes", "marking_pools", "marking_print_batches", "operation_facts",
        "outbound_shipment_requests", "print_templates", "product_barcodes", "product_marketplace_links",
        "product_tz_imports", "products", "seller_ozon_imported_cards", "seller_wildberries_imported_cards",
        "seller_wildberries_imported_supplies", "storage_measurements", "storage_statements",
        "withdrawal_documents", "withdrawal_items", "withdrawal_operations",
    ),
    # --- через родителя (строки документов, остатки по товару и т. п.) ---
    _via("billing_invoice_v2_lines", "invoice_id", "billing_invoices_v2"),
    _via("billing_invoice_v2_sources", "invoice_line_id", "billing_invoice_v2_lines"),
    _via("billing_ledger_lines", "ledger_entry_id", "billing_ledger_entries"),
    _via("discrepancy_act_lines", "act_id", "discrepancy_acts"),
    _via("fbs_order_products", "order_id", "fbs_orders"),
    _via("fbs_order_picks", "fbs_order_id", "fbs_orders"),
    _via("fbs_order_pick_events", "pick_id", "fbs_order_picks"),
    _via("fbs_order_product_picks", "order_product_id", "fbs_order_products"),
    _via("fbs_order_product_reservations", "order_product_id", "fbs_order_products"),
    _via("fbs_order_reservations", "fbs_order_id", "fbs_orders"),
    _via("fbs_order_markings", "order_id", "fbs_orders"),
    _via("fbs_packaging_fulfillments", "fbs_order_id", "fbs_orders"),
    _via("fbs_packing_box_items", "fbs_order_id", "fbs_orders"),
    _via("fbs_packing_boxes", "supply_id", "fbs_supplies"),
    _via("fbs_trbxes", "supply_id", "fbs_supplies"),
    _via("fbs_assembly_task_supplies", "supply_id", "fbs_supplies"),
    _via("fbs_shipment_reversal_ledger", "fbs_order_id", "fbs_orders"),
    _via("fbs_stock_sync_items", "binding_id", "fbs_warehouse_bindings"),
    _via("fbs_binding_stock_pools", "binding_id", "fbs_warehouse_bindings"),
    _via("wb_order_price_snapshots", "order_id", "fbs_orders"),
    _via("inbound_intake_boxes", "request_id", "inbound_intake_requests"),
    _via("inbound_intake_box_lines", "box_id", "inbound_intake_boxes"),
    _via("inbound_intake_cargo_places", "request_id", "inbound_intake_requests"),
    _via("inbound_intake_cargo_place_lines", "cargo_place_id", "inbound_intake_cargo_places"),
    _via("inbound_intake_distribution_lines", "request_id", "inbound_intake_requests"),
    _via("inbound_intake_lines", "request_id", "inbound_intake_requests"),
    _via("inbound_ozon_return_giveouts", "request_id", "inbound_intake_requests"),
    _via("inbound_ozon_return_items", "request_id", "inbound_intake_requests"),
    _via("inventory_balances", "product_id", "products"),
    _via("inventory_reservations", "product_id", "products"),
    _via("inventory_count_lines", "count_id", "inventory_counts"),
    _via("inventory_count_created_containers", "count_id", "inventory_counts"),
    _via("inventory_count_found_scans", "count_id", "inventory_counts"),
    _via("marketplace_unload_boxes", "request_id", "marketplace_unload_requests"),
    _via("marketplace_unload_box_lines", "box_id", "marketplace_unload_boxes"),
    _via("marketplace_unload_lines", "request_id", "marketplace_unload_requests"),
    _via("marketplace_unload_pick_allocations", "request_id", "marketplace_unload_requests"),
    _via("marketplace_unload_reservations", "product_id", "products"),
    _via("marking_code_import_files", "import_batch_id", "marking_code_imports"),
    _via("marking_pool_products", "pool_id", "marking_pools"),
    _via("marking_reprint_requests", "code_id", "marking_codes"),
    _via("operation_fact_lines", "operation_fact_id", "operation_facts"),
    _via("outbound_shipment_lines", "request_id", "outbound_shipment_requests"),
    # задача упаковки: все указанные родители (выгрузка и/или приёмка) обязаны быть этого селлера
    Table("packaging_tasks", "all_present", (("marketplace_unload_request_id", "marketplace_unload_requests"),
                                              ("inbound_intake_request_id", "inbound_intake_requests"))),
    _via("packaging_task_lines", "task_id", "packaging_tasks"),
    _via("packaging_task_events", "task_id", "packaging_tasks"),
    _via("pallets", "inbound_request_id", "inbound_intake_requests"),
    _via("warehouse_boxes", "inbound_request_id", "inbound_intake_requests"),
    _via("product_dimension_events", "product_id", "products"),
    _via("stock_directions", "product_id", "products"),
    _via("stock_monthly_snapshots", "product_id", "products"),
    _via("document_event", "product_id", "products"),
    _via("withdrawal_observations", "document_id", "withdrawal_documents"),
]
BY_NAME = {t.name: t for t in TABLES}

# Секретные колонки: явный перечень (ведущий, боевая база) + эвристика по именам (fail closed).
SECRET_COLUMNS: dict[str, set[str]] = {
    "users": {"password_hash"},
    "marketplace_accounts": {"secret_encrypted"},
    "print_connections": {"token_hash", "pairing_hash"},
    "withdrawal_documents": {"signature"},
    "withdrawal_operations": {"auth_challenge", "auth_signature_hash", "token_enc"},
    "developer_requests": {"lease_token"},
}
# Настройки сессии роли: ALTER ROLE ... SET при каждом ensure (идемпотентно) и те же значения шлюз
# навязывает СЕССИИ при подключении (options в строке подключения перекрывают настройки роли, поэтому даже
# изменённые роль-настройки в сессии не действуют).
SESSION_SETTINGS = (
    ("default_transaction_read_only", "on"),
    ("statement_timeout", "'20s'"),
    ("idle_in_transaction_session_timeout", "'30s'"),
    ("lock_timeout", "'3s'"),
    ("row_security", "on"),
    ("search_path", "public, pg_catalog"),
)
SECRET_NAME_RE = re.compile(
    r"(password|passwd|secret|token|signature|credential|api_key|apikey|cookie|private_key|"
    r"_enc$|_encrypted$|^auth_|hash$|challenge)", re.IGNORECASE)

SPEC_VERSION = hashlib.sha256(repr([(t.name, t.kind, t.hops, t.seller_col) for t in TABLES]).encode()
                              + repr(sorted((k, sorted(v)) for k, v in SECRET_COLUMNS.items())).encode()).hexdigest()[:12]


class SpecError(Exception):
    pass


def role_name(seller_id: str) -> str:
    seller_id = seller_id.strip().lower()
    if not SELLER_RE.match(seller_id):
        raise SpecError("seller id must be a UUID")
    return ROLE_PREFIX + seller_id.replace("-", "")


def seller_from_role(role: str) -> str:
    if not ROLE_RE.match(role):
        raise SpecError("bad role name")
    h = role[len(ROLE_PREFIX):]
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def is_secret(table: str, column: str) -> bool:
    return column in SECRET_COLUMNS.get(table, set()) or bool(SECRET_NAME_RE.search(column))


def _ident(name: str) -> str:
    if not IDENT_RE.match(name):
        raise SpecError(f"unsafe identifier {name!r}")
    return f'"{name}"'


def _path_columns(table: Table) -> set[str]:
    if table.kind == "direct":
        return {table.seller_col}
    if table.kind == "self":
        return {"id"}
    return {c for c, _ in table.hops}


def included_tables(catalog: dict[str, set[str]]) -> list[Table]:
    """Таблицы списка, реально существующие с нужными колонками (fail closed): путь к селлеру
    обязан целиком существовать, родитель — быть включённым и иметь id."""
    included: dict[str, Table] = {}
    changed = True
    while changed:
        changed = False
        for t in TABLES:
            if t.name in included or t.name not in catalog or not _path_columns(t) <= catalog[t.name]:
                continue
            if all(p in included and "id" in catalog[p] for _, p in t.hops):
                included[t.name] = t
                changed = True
    return [t for t in TABLES if t.name in included]


def _expr(table: Table, alias: str, seller: str, depth: int = 0) -> str:
    if table.kind == "direct":
        return f"{alias}.{_ident(table.seller_col)} = '{seller}'::uuid"
    if table.kind == "self":
        return f"{alias}.\"id\" = '{seller}'::uuid"

    def exists(col: str, parent: str, nxt: int) -> str:
        pa = f"p{nxt}"
        return (f"EXISTS (SELECT 1 FROM public.{_ident(parent)} {pa} WHERE {pa}.\"id\" = {alias}.{_ident(col)} "
                f"AND {_expr(BY_NAME[parent], pa, seller, nxt)})")

    if table.kind == "via":
        (col, parent), = table.hops
        return exists(col, parent, depth + 1)
    if table.kind == "all_present":
        parts = [f"({alias}.{_ident(c)} IS NULL OR {exists(c, p, depth + 1)})" for c, p in table.hops]
        anyset = " OR ".join(f"{alias}.{_ident(c)} IS NOT NULL" for c, _ in table.hops)
        return " AND ".join(parts) + f" AND ({anyset})"
    raise SpecError(table.kind)


def policy_expression(table: Table, seller: str) -> str:
    return _expr(table, _ident(table.name), seller)


def allowed_columns(table: str, columns: list[str], required: set[str]) -> list[str]:
    """Несекретные колонки; колонки пути нужны политике родителей и таблицы, их секретными не считаем."""
    return sorted(c for c in columns if c in required or not is_secret(table, c))


def _required_columns(table: Table) -> set[str]:
    return _path_columns(table) | {"id"}


@dataclass
class Catalog:
    columns: dict[str, list[str]]
    secdef_functions: list[str] = field(default_factory=list)  # oid::regprocedure
    shared_ro_exists: bool = False
    rls_enabled: set[str] = field(default_factory=set)  # таблицы списка, где relrowsecurity уже включён
    policies: set[tuple[str, str]] = field(default_factory=set)  # (таблица, политика) этого селлера и общая
    role_version: str = ""  # COMMENT ON ROLE: «wms-agent:<версия политик>:<версия прав>» или пусто


LOCK_TIMEOUT = "2s"
STATEMENT_TIMEOUT = "60s"
VERSION_PREFIX = "wms-agent:"
# Версия ПОЛИТИК зависит только от спецификации путей (меняется при выкладке нового списка): политики
# пересоздаются только тогда. Версия ПРАВ зависит ещё от колонок и функций в базе (миграции): меняются
# только гранты (они не берут блокировок таблиц) и создаются политики там, где их ещё нет.
POLICY_VERSION = hashlib.sha256(repr([(t.name, t.kind, t.hops, t.seller_col) for t in TABLES]).encode()
                                ).hexdigest()[:12]


def grant_version(catalog: Catalog) -> str:
    tables = included_tables({k: set(v) for k, v in catalog.columns.items()})
    blob = repr([
        sorted((t.name, sorted(catalog.columns[t.name])) for t in tables),
        sorted(catalog.secdef_functions), catalog.shared_ro_exists, SESSION_SETTINGS,
        sorted((k, sorted(v)) for k, v in SECRET_COLUMNS.items()),
    ])
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def target_version(catalog: Catalog) -> str:
    return f"{VERSION_PREFIX}{POLICY_VERSION}:{grant_version(catalog)}"


def stored_policy_version(catalog: Catalog) -> str | None:
    parts = catalog.role_version.split(":")
    return parts[1] if len(parts) == 3 and parts[0] + ":" == VERSION_PREFIX else None


def is_current(catalog: Catalog) -> bool:
    """Роль уже на текущей версии: тяжёлую часть (политики, права) повторять не нужно."""
    return catalog.role_version == target_version(catalog)


def _role_statements(role: str) -> list[str]:
    r = _ident(role)
    return [
        "DO $do$ BEGIN",
        f"  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN",
        f"    CREATE ROLE {r} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;",
        "  END IF;",
        "END $do$;",
        f"ALTER ROLE {r} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT "
        "CONNECTION LIMIT 8;",
        *[f"ALTER ROLE {r} SET {name} = {value};" for name, value in SESSION_SETTINGS],
    ]


def _begin() -> list[str]:
    # БЕЗ ожидания: ACCESS EXCLUSIVE не должен вставать в очередь за долгой транзакцией и вешать обычные
    # запросы WMS; при таймауте вся транзакция откатывается (одна транзакция), повтор позже.
    return ["BEGIN;", f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}';",
            f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}';"]


def render_role_sql(seller_id: str) -> str:
    """Лёгкая часть: роль и её настройки (ALTER ROLE не берёт табличных блокировок). Выполняется при каждом
    ensure, в том числе когда роль уже на текущей версии."""
    seller = seller_id.strip().lower()
    return "\n".join([*_begin(), *_role_statements(role_name(seller)), "COMMIT;"]) + "\n"


def render_sql(seller_id: str, catalog: Catalog) -> str:
    seller = seller_id.strip().lower()
    role = role_name(seller)
    r = _ident(role)
    tables = included_tables({k: set(v) for k, v in catalog.columns.items()})
    suffix = seller.replace("-", "")
    polname = "agent_" + suffix
    pol = _ident(polname)
    stored_pv = stored_policy_version(catalog)
    recreate = stored_pv is not None and stored_pv != POLICY_VERSION
    out = [
        f"-- WMS-641: доступ селлера {seller} (версия списка {SPEC_VERSION}); идемпотентно",
        *_begin(),
        *_role_statements(role),
        f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {r};",
        f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {r};",
        f"REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM {r};",
        f"REVOKE CREATE ON SCHEMA public FROM {r};",
        f"GRANT USAGE ON SCHEMA public TO {r};",
    ]
    for fn in catalog.secdef_functions:
        if not re.match(r"^[A-Za-z0-9_.\"(), ]+$", fn):
            raise SpecError(f"unsafe function signature {fn!r}")
        out.append(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC, {r};  -- SECURITY DEFINER")
    for t in tables:
        tb = f"public.{_ident(t.name)}"
        cols = allowed_columns(t.name, catalog.columns[t.name], _required_columns(t))
        cols = [c for c in cols if c in catalog.columns[t.name]]
        # ACCESS EXCLUSIVE (ENABLE RLS, CREATE/DROP POLICY) только там, где это действительно нужно
        if t.name not in catalog.rls_enabled:
            out.append(f"ALTER TABLE {tb} ENABLE ROW LEVEL SECURITY;")
        has_policy = (t.name, polname) in catalog.policies
        if has_policy and recreate:
            out.append(f"DROP POLICY {pol} ON {tb};")
        if not has_policy or recreate:
            out.append(f"CREATE POLICY {pol} ON {tb} AS PERMISSIVE FOR SELECT TO {r} "
                       f"USING ({policy_expression(t, seller)});")
        out.append(f"GRANT SELECT ({', '.join(_ident(c) for c in cols)}) ON {tb} TO {r};")
        if catalog.shared_ro_exists and (t.name, "agent_ro_all") not in catalog.policies:
            out.append(f"CREATE POLICY {_ident('agent_ro_all')} ON {tb} AS PERMISSIVE FOR SELECT "
                       f"TO {_ident(SHARED_RO_ROLE)} USING (true);")
    out.append(f"COMMENT ON ROLE {r} IS '{target_version(catalog)}';")
    out.append("COMMIT;")
    return "\n".join(out) + "\n"


PREFLIGHT_SQL = """\
SELECT 'col' AS kind, table_name AS a, column_name AS b FROM information_schema.columns
 WHERE table_schema = 'public' AND table_name = ANY (ARRAY[{tables}])
UNION ALL
SELECT 'secdef', p.oid::regprocedure::text, '' FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog', 'information_schema')
UNION ALL
SELECT 'ro', rolname, '' FROM pg_roles WHERE rolname = '{ro}'
UNION ALL
SELECT 'rls', c.relname, '' FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND c.relrowsecurity
   AND c.relname = ANY (ARRAY[{tables}])
UNION ALL
SELECT 'pol', c.relname, p.polname FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
 JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND p.polname IN ('agent_ro_all'{own_policy})
{role_version}ORDER BY 1, 2, 3;
"""


def preflight_sql(seller_id: str | None = None) -> str:
    """Состояние для решения «что делать»: колонки, функции, уже включённый RLS, уже созданные политики
    (общая и этого селлера) и версия роли. Только чтение каталога, табличных блокировок нет."""
    names = ", ".join(f"'{t.name}'" for t in TABLES)
    own, version = "", ""
    if seller_id is not None:
        seller = seller_id.strip().lower()
        role = role_name(seller)
        own = f", 'agent_{seller.replace('-', '')}'"
        version = (f"UNION ALL\nSELECT 'ver', coalesce(shobj_description(oid, 'pg_authid'), ''), '' "
                   f"FROM pg_roles WHERE rolname = '{role}'\n")
    return PREFLIGHT_SQL.format(tables=names, ro=SHARED_RO_ROLE, own_policy=own, role_version=version)


def parse_preflight(rows: list[list[str]]) -> Catalog:
    cat = Catalog(columns={})
    for kind, a, b in rows:
        if kind == "col":
            cat.columns.setdefault(a, []).append(b)
        elif kind == "secdef":
            cat.secdef_functions.append(a)
        elif kind == "ro":
            cat.shared_ro_exists = True
        elif kind == "rls":
            cat.rls_enabled.add(a)
        elif kind == "pol":
            cat.policies.add((a, b))
        elif kind == "ver":
            cat.role_version = a
    return cat
