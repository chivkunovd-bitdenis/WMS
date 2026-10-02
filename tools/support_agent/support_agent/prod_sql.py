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
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

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
DOLLAR_TAG = re.compile(r"\$([A-Za-z_][A-Za-z_0-9]*)?\$")


class SqlRefused(Exception):
    """Запрос отклонён клиентом до отправки на сервер."""


def mask_literals(sql: str) -> str:
    """Заменяет строки и кавычные идентификаторы заглушками; комментарии и обратный слеш запрещены."""
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
        if ch == "$":
            match = DOLLAR_TAG.match(sql, i)
            if match:
                tag = match.group(0)
                end = sql.find(tag, match.end())
                if end < 0:
                    raise SqlRefused("незакрытая долларовая строка")
                out.append("''")
                i = end + len(tag)
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
    rows = list(csv.reader(io.StringIO(text)))
    note = ""
    if len(rows) > row_limit + 1:  # заголовок + row_limit строк
        rows = rows[: row_limit + 1]
        note = f"\n# вывод обрезан: показано {row_limit} строк, уточните запрос (WHERE, LIMIT)"
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    result = buf.getvalue()
    if len(result.encode("utf-8")) > max_bytes:
        result = result.encode("utf-8")[:max_bytes].decode("utf-8", "ignore")
        note = f"\n# вывод обрезан по размеру ({max_bytes} байт), уточните запрос"
    return result + note


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


Runner = Callable[[list[str], str, int], tuple[int, str, str]]


def default_runner(argv: list[str], stdin: str, timeout: int) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return 127, "", "ssh not found"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    return proc.returncode, proc.stdout, proc.stderr


def ssh_argv(cfg: ProdSqlSettings) -> list[str]:
    argv = [cfg.ssh_bin, "-F", "/dev/null", "-i", str(Path(cfg.ssh_key_path).expanduser()),
            "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ClearAllForwardings=yes", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=10",
            "-o", "ServerAliveCountMax=2", "-T"]
    if cfg.known_hosts:
        argv += ["-o", f"UserKnownHostsFile={Path(cfg.known_hosts).expanduser()}"]
    return [*argv, f"{cfg.ssh_user}@{cfg.ssh_host}"]


def run_query(cfg: ProdSqlSettings, sql: str, runner: Runner = default_runner) -> str:
    """Проверенный запрос -> CSV (с лимитами). Ошибки возвращаются исключением SqlRefused/RuntimeError."""
    query, first = validate_sql(sql)
    stdin = wrap_limit(query, first, cfg.row_limit) + "\n"
    rc, out, err = runner(ssh_argv(cfg), stdin, cfg.timeout_sec)
    if rc == 124:
        raise RuntimeError(f"запрос не уложился в {cfg.timeout_sec} с")
    if rc != 0:
        # текст ошибки сервера (psql) полезен аналитику; секретов в нём нет, но длину ограничиваем
        raise RuntimeError(f"ошибка запроса (код {rc}): {(err or out).strip()[:400]}")
    return truncate_csv(out, cfg.row_limit, cfg.max_bytes)
