"""Чтение боевой базы для аналитиков (только SELECT), WMS-641 В4.

Сервер сам read-only (роль wms_agent_ro), но клиент не пропускает DML, DDL, COPY, метакоманды psql,
несколько операторов и комментарии. Запрос уходит по ssh с отдельным ключом; на сервере forced command
выполняет ровно:

    docker exec -i wms_prod-db-1 psql -U wms_agent_ro -d wms -X -v ON_ERROR_STOP=1 --csv

и читает SQL со stdin; ответ — CSV в stdout. Клиент: `ssh -i <ключ> -o BatchMode=yes -o IdentitiesOnly=yes
user@host` и SQL в stdin.
"""

from __future__ import annotations

import csv
import io
import re
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_SQL_CHARS = 8000
ALLOWED_FIRST = ("select", "with", "explain")
FORBIDDEN_WORDS = (
    "insert update delete merge drop alter create truncate grant revoke copy call do execute prepare "
    "deallocate vacuum reindex cluster lock set reset listen notify unlisten comment refresh analyze "
    "analyse into begin commit rollback savepoint release discard load import security reassign owned "
    "checkpoint abort start end"
).split()
FORBIDDEN_RE = re.compile(r"\b(" + "|".join(FORBIDDEN_WORDS) + r")\b", re.IGNORECASE)
FORBIDDEN_FUNCS = re.compile(
    r"\b(pg_read_\w*|pg_ls_\w*|pg_stat_file|pg_terminate_backend|pg_cancel_backend|pg_reload_conf|"
    r"pg_rotate_logfile|pg_sleep\w*|pg_advisory\w*|pg_logical\w*|pg_create\w*|pg_drop\w*|pg_replication\w*|"
    r"pg_switch_wal|pg_promote|lo_\w+|dblink\w*|set_config|nextval|setval|txid_\w*)\b", re.IGNORECASE)
LOCKING_RE = re.compile(r"\bfor\s+(no\s+key\s+update|update|share|key\s+share)\b", re.IGNORECASE)


class SqlRefused(Exception):
    """Запрос отклонён клиентом до отправки на сервер."""


def mask_literals(sql: str) -> str:
    """Заменяет строки ('' экранируется удвоением) и кавычные идентификаторы заглушками; комментарии,
    обратный слеш и любой символ $ запрещены (долларовые строки, `a$$` в идентификаторах и параметры
    аналитику не нужны, а через них прятались `;` и запрещённые слова)."""
    if "$" in sql:
        raise SqlRefused("символ $ запрещён (долларовые строки и параметры)")
    if "\\" in sql:
        raise SqlRefused("обратный слеш (метакоманды psql, escape-строки) запрещён")
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch == "\\":
            raise SqlRefused("обратный слеш (метакоманды psql) запрещён")
        if sql.startswith("--", i) or sql.startswith("/*", i):
            raise SqlRefused("комментарии в запросе запрещены")
        if ch in "'\"":
            j = i + 1
            while True:
                if j >= n:
                    raise SqlRefused("незакрытая кавычка")
                if sql[j] == ch:
                    if j + 1 < n and sql[j + 1] == ch:
                        j += 2
                        continue
                    break
                j += 1
            out.append("''" if ch == "'" else '"x"')
            i = j + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def validate_sql(sql: str) -> tuple[str, str]:
    """(нормализованный запрос без хвостового `;`, первое ключевое слово) или SqlRefused."""
    if not isinstance(sql, str) or not sql.strip():
        raise SqlRefused("пустой запрос")
    if len(sql) > MAX_SQL_CHARS:
        raise SqlRefused(f"запрос длиннее {MAX_SQL_CHARS} символов")
    if any(ord(c) < 32 and c not in "\n\t\r" for c in sql):
        raise SqlRefused("управляющие символы в запросе запрещены")
    query = sql.strip()
    while query.endswith(";"):
        query = query[:-1].rstrip()
    masked = mask_literals(query)
    if ";" in masked:
        raise SqlRefused("допустим один оператор (точка с запятой внутри запрещена)")
    words = masked.split()
    first = (words[0] if words else "").lower().lstrip("(")
    if first not in ALLOWED_FIRST:
        raise SqlRefused("запрос должен начинаться с SELECT, WITH или EXPLAIN")
    bad = FORBIDDEN_RE.search(masked)
    if bad:
        raise SqlRefused(f"слово {bad.group(1).upper()} запрещено (только чтение)")
    func = FORBIDDEN_FUNCS.search(masked)
    if func:
        raise SqlRefused(f"функция {func.group(1)} запрещена")
    if LOCKING_RE.search(masked):
        raise SqlRefused("блокирующие конструкции FOR UPDATE/SHARE запрещены")
    return query, first


def wrap_limit(query: str, first: str, row_limit: int) -> str:
    """SELECT/WITH оборачиваются в подзапрос с LIMIT на единицу больше: так видно, что вывод обрезан."""
    if first == "explain":
        return query
    return f"SELECT * FROM (\n{query}\n) AS _agent_q LIMIT {int(row_limit) + 1}"


def truncate_csv(text: str, row_limit: int, max_bytes: int) -> str:
    """Режет по строкам и размеру. Длинное поле не роняет разбор: лимит поля поднимается до размера
    уже ограниченного вывода, а любая ошибка разбора даёт обрезку по размеру с пометкой."""
    note = ""
    try:
        csv.field_size_limit(max(len(text) + 1, 131072))
        rows = list(csv.reader(io.StringIO(text)))
        if len(rows) > row_limit + 1:  # заголовок + row_limit строк
            rows = rows[: row_limit + 1]
            note = f"\n# вывод обрезан: показано {row_limit} строк, уточните запрос (WHERE, LIMIT)"
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(rows)
        result = buf.getvalue()
    except (csv.Error, MemoryError):
        result, note = text, "\n# CSV не разобран полностью, вывод обрезан по размеру"
    if len(result.encode("utf-8")) > max_bytes:
        result = result.encode("utf-8")[:max_bytes].decode("utf-8", "ignore")
        note = f"\n# вывод обрезан по размеру ({max_bytes} байт), уточните запрос"
    return result + note


SELLER_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
ROLE_RE = re.compile(r"^wms_agent_[st]_[0-9a-f]{32}$")


def role_for_seller(seller_id: str) -> str:
    """Роль Postgres селлера (R41). Общая роль wms_agent_ro обращениям клиентов не выдаётся (R42)."""
    seller_id = str(seller_id).strip().lower()
    if not SELLER_RE.match(seller_id):
        raise SqlRefused("некорректный идентификатор селлера")
    return "wms_agent_s_" + seller_id.replace("-", "")


def role_for_tenant(tenant_id: str) -> str:
    """Роль фулфилмента (чат владельца с ФФ: видны все селлеры этого тенанта)."""
    tenant_id = str(tenant_id).strip().lower()
    if not SELLER_RE.match(tenant_id):
        raise SqlRefused("некорректный идентификатор фулфилмента")
    return "wms_agent_t_" + tenant_id.replace("-", "")


def role_for_scope(level: str, scope_id: str) -> str:
    """Роль по уровню привязки: tenant (фулфилмент) или seller (селлер)."""
    return role_for_tenant(scope_id) if level == "tenant" else role_for_seller(scope_id)


@dataclass
class ProdSqlSettings:
    ssh_host: str
    ssh_user: str
    ssh_key_path: str
    known_hosts: str = ""
    row_limit: int = 200
    timeout_sec: int = 30
    max_bytes: int = 60_000
    ssh_bin: str = "ssh"
    db_role: str = ""  # роль селлера обращения; задаёт доверенный код при запуске сервера, не модель


Runner = Callable[[list[str], str, int], tuple[int, str, str]]
OUTPUT_TRUNCATED_RC = 125  # вывод превысил бюджет байтов, процесс остановлен
STDERR_BUDGET = 8_000


def default_runner(
    argv: list[str], stdin: str, timeout: int, max_out: int = 200_000, max_err: int = STDERR_BUDGET
) -> tuple[int, str, str]:
    """Потоковое чтение с бюджетом байтов: stdout сверх бюджета останавливает процесс (код 125),
    лишний stderr отбрасывается (канал при этом вычитывается, процесс не зависает)."""
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        return 127, "", "ssh not found"
    out, err = bytearray(), bytearray()
    over = threading.Event()

    def pump(stream: Any, buf: bytearray, limit: int, kill_on_overflow: bool) -> None:
        while True:
            chunk = stream.read1(8192)
            if not chunk:
                return
            room = limit - len(buf)
            if room > 0:
                buf.extend(chunk[:room])
            if len(chunk) > room and kill_on_overflow:
                over.set()
                proc.kill()
                return

    threads = [threading.Thread(target=pump, args=(proc.stdout, out, max_out, True), daemon=True),
               threading.Thread(target=pump, args=(proc.stderr, err, max_err, False), daemon=True)]
    for t in threads:
        t.start()
    try:
        assert proc.stdin is not None
        proc.stdin.write(stdin.encode("utf-8"))
        proc.stdin.close()
    except (BrokenPipeError, OSError):
        pass
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return 124, "", "timeout"
    for t in threads:
        t.join(timeout=5)
    rc = OUTPUT_TRUNCATED_RC if over.is_set() else proc.returncode
    return rc, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def ssh_argv(cfg: ProdSqlSettings, remote_command: str | None = None) -> list[str]:
    argv = [cfg.ssh_bin, "-F", "/dev/null", "-i", str(Path(cfg.ssh_key_path).expanduser()),
            "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ClearAllForwardings=yes", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=10",
            "-o", "ServerAliveCountMax=2", "-T"]
    if cfg.known_hosts:
        argv += ["-o", f"UserKnownHostsFile={Path(cfg.known_hosts).expanduser()}"]
    target = f"{cfg.ssh_user}@{cfg.ssh_host}"
    # Шлюз на сервере принимает ровно `sql <роль>`, `ensure-seller <uuid>` или `find-seller <строка>`.
    return [*argv, target, remote_command] if remote_command else [*argv, target]


_ERR_RE = re.compile(r"^(?:psql: )?(?:error|fatal):\s+([0-9A-Z]{5}):\s*(.*)$", re.IGNORECASE)
_QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")


def sanitize_error(text: str) -> str:
    """Текст серверной ошибки без значений данных (повтор серверной очистки шлюза на случай старого шлюза):
    только первая строка; для класса 42 сообщение остаётся, для остальных кавычечные фрагменты (там
    сервер печатает прочитанные значения) заменяются на «…»."""
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
    first = next((ln for ln in lines if re.match(r"^(psql: )?(error|fatal)", ln, re.IGNORECASE)),
                 lines[0] if lines else "")
    match = _ERR_RE.match(first)
    if match:
        state, message = match.group(1), match.group(2)
        if not state.startswith("42"):
            message = _QUOTED.sub("«…»", message)
        return f"{state}: {message}"[:240]
    return _QUOTED.sub("«…»", first)[:240]


def run_query(cfg: ProdSqlSettings, sql: str, runner: Runner | None = None,
              on_send: Callable[[], None] | None = None) -> str:
    """Проверенный запрос -> CSV (с лимитами). Ошибки возвращаются исключением SqlRefused/RuntimeError.
    on_send вызывается ПОСЛЕ проверки и ДО отправки запроса на сервер (след обращения к базе, N1)."""
    if not ROLE_RE.match(cfg.db_role):
        raise SqlRefused("доступ к базе не выдан: у обращения нет привязанного селлера")
    query, first = validate_sql(sql)
    stdin = wrap_limit(query, first, cfg.row_limit) + "\n"
    budget = cfg.max_bytes * 2 + 4096
    if on_send is not None:
        on_send()  # если след записать нельзя, запрос не уходит (исключение)

    def default(argv: list[str], text: str, timeout: int) -> tuple[int, str, str]:
        return default_runner(argv, text, timeout, max_out=budget)

    rc, out, err = (runner or default)(ssh_argv(cfg, f"sql {cfg.db_role}"), stdin, cfg.timeout_sec)
    if rc == 124:
        raise RuntimeError(f"запрос не уложился в {cfg.timeout_sec} с")
    if rc == OUTPUT_TRUNCATED_RC:
        cut = truncate_csv(out, cfg.row_limit, cfg.max_bytes)
        return cut + "\n# вывод оборван: ответ сервера слишком большой"
    if rc != 0:
        # аналитику возвращается только очищенная первая строка ошибки: значения данных в ней не нужны
        raise RuntimeError(f"ошибка запроса (код {rc}): {sanitize_error(err or out)}")
    return truncate_csv(out, cfg.row_limit, cfg.max_bytes)
