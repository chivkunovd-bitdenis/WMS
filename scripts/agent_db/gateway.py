#!/usr/bin/env python3
"""WMS-641: шлюз для forced command единственного ssh-ключа агента-диспетчера (запускается на сервере).

В authorized_keys ключ агента привязан к этой программе (no-pty, no-port-forwarding, ...). Из
SSH_ORIGINAL_COMMAND принимается РОВНО одна из трёх форм, всё остальное отклоняется:

  sql wms_agent_s_<32 hex>      SQL из stdin, ответ CSV в stdout: до запуска psql SQL ПРОВЕРЯЕТСЯ здесь же
                                (один SELECT/WITH/EXPLAIN, ни одного обратного слеша: метакоманды psql
                                \\!, \\connect, \\copy, \\gexec невозможны), запрос передаётся ключом -c;
                                вывод читается потоком с бюджетом, текст ошибки очищается от значений
  ensure-seller <uuid>          идемпотентно создать/обновить роль и политики селлера (под postgres)
  find-seller <строка>          кандидаты по названию (фиксированный запрос, строка — переменная psql)

Общая роль wms_agent_ro через шлюз недоступна. Настройки: AGENT_DB_PSQL (JSON-массив базовой команды psql,
по умолчанию docker exec -i wms_prod-db-1 psql), AGENT_DB_NAME (по умолчанию wms).
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seller_access as sa  # noqa: E402
import sql_contract as sc  # noqa: E402

DEFAULT_BASE = ["docker", "exec", "-i", "wms_prod-db-1", "psql"]
SQL_RE = re.compile(r"^sql (wms_agent_s_[0-9a-f]{32})$")
ENSURE_RE = re.compile(r"^ensure-seller ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")
FIND_RE = re.compile(r"^find-seller ([0-9A-Za-zА-Яа-яЁё .,'\"«»()+&/_-]{2,80})$")
FIND_SQL = (
    "SELECT s.id AS seller_id, s.name AS seller_name, s.tenant_id, t.name AS tenant_name "
    "FROM sellers s JOIN tenants t ON t.id = s.tenant_id "
    "WHERE s.name ILIKE '%' || :'q' || '%' ORDER BY s.name, t.name LIMIT 10;\n"
)


MAX_STDOUT = 256 * 1024  # бюджеты вывода запроса sql: сверх этого psql останавливается
MAX_STDERR = 8 * 1024
SQL_TIMEOUT_SEC = 45
MAX_STDIN_CHARS = sc.MAX_SQL_CHARS + 1
OUTPUT_TRUNCATED_RC = 125  # то же значение, что у клиента агента: «вывод превысил бюджет, процесс остановлен»
TIMEOUT_RC = 124


class Refused(Exception):
    pass


DB_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,63}$")


def session_options() -> str:
    """Значения настроек роли селлера, навязываемые сессии при подключении."""
    return " ".join(f"-c {name}={value.strip(chr(39)).replace(', ', ',').replace(' ', '')}"
                    for name, value in sa.SESSION_SETTINGS)


def psql_argv(user: str, extra: list[str] | None = None, env: dict[str, str] | None = None,
              session_guard: bool = False) -> list[str]:
    """session_guard: база задаётся строкой подключения с options: настройки сессии (только чтение, таймауты,
    row_security, search_path) перекрывают настройки роли, даже если их изменили через ALTER ROLE. Строка
    подключения не зависит от того, как базовая команда (docker exec) передаёт окружение."""
    env = env if env is not None else dict(os.environ)
    base = json.loads(env["AGENT_DB_PSQL"]) if env.get("AGENT_DB_PSQL") else list(DEFAULT_BASE)
    db = env.get("AGENT_DB_NAME", "wms")
    if not DB_NAME_RE.match(db):
        raise ValueError("bad database name")
    target = f"dbname={db} options='{session_options()}'" if session_guard else db
    return [*base, "-U", user, "-d", target, "-X", "-v", "ON_ERROR_STOP=1", *(extra or [])]


def run_psql(user: str, stdin: str, extra: list[str] | None = None,
             env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(psql_argv(user, extra, env), input=stdin, capture_output=True, text=True, timeout=120)


def run_bounded(argv: list[str], max_out: int = MAX_STDOUT, max_err: int = MAX_STDERR,
                timeout: int = SQL_TIMEOUT_SEC) -> tuple[int, bytes, bytes]:
    """Запускает команду, читая stdout/stderr потоком с бюджетом байтов. Превышение stdout останавливает
    процесс: вывод усекается до бюджета, код выхода OUTPUT_TRUNCATED_RC. Лишний stderr отбрасывается
    (канал вычитывается, процесс не зависает). Таймаут даёт код 124."""
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = bytearray(), bytearray()
    over = threading.Event()

    def pump(stream, buf: bytearray, limit: int, kill_on_overflow: bool) -> None:  # type: ignore[no-untyped-def]
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
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return TIMEOUT_RC, b"", b"timeout"
    for t in threads:
        t.join(timeout=5)
    return (OUTPUT_TRUNCATED_RC if over.is_set() else proc.returncode), bytes(out), bytes(err)


def _emit(stream, text: str) -> None:  # type: ignore[no-untyped-def]
    """Вывод в UTF-8 независимо от локали forced command."""
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        buffer.write(text.encode("utf-8"))
        buffer.flush()
    else:
        stream.write(text)
        stream.flush()


def read_stdin_sql() -> str:
    raw = sys.stdin.buffer.read(MAX_STDIN_CHARS * 4 + 1)
    if len(raw) > MAX_STDIN_CHARS * 4:
        raise sc.SqlRefused("query too long")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise sc.SqlRefused("query is not valid utf-8") from None


def run_sql(role: str, data: str, env: dict[str, str] | None = None) -> int:
    """Ветка sql: проверка контракта ДО psql; psql получает запрос ключом -c, не из ввода."""
    query = sc.validate_sql(data)  # SqlRefused -> отказ (код 3), psql не запускается
    argv = psql_argv(role, ["--csv", "-v", "VERBOSITY=verbose", "-c", query], env, session_guard=True)
    rc, out, err = run_bounded(argv)
    if rc not in (0, OUTPUT_TRUNCATED_RC):
        # ошибка запроса: модели уходит только очищенная первая строка, частичный вывод отбрасывается
        _emit(sys.stderr, sc.sanitize_error(err.decode("utf-8", "replace")) + "\n")
        return rc
    _emit(sys.stdout, out.decode("utf-8", "ignore"))  # обрезка по границе символа, не по байту
    return rc


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _apply(sql: str, env: dict[str, str] | None) -> None:
    """Транзакция DDL под postgres: любой сбой (в том числе lock_timeout) откатывает её целиком."""
    applied = run_psql("postgres", sql, ["-q"], env)
    if applied.returncode != 0:
        err = applied.stderr
        if "lock timeout" in err or "55P03" in err:
            raise Refused("busy: lock timeout, nothing was changed, retry later")
        if "statement timeout" in err or "57014" in err:
            raise Refused("busy: statement timeout, nothing was changed, retry later")
        raise Refused("apply failed: " + err.strip().splitlines()[0][:200] if err.strip() else "apply failed")


def ensure_seller(seller: str, env: dict[str, str] | None = None) -> str:
    """Идемпотентно. Роль уже на текущей версии: только дешёвая проверка и ALTER ROLE SET (без табличных
    блокировок). Версия сменилась или роли нет: одна транзакция с lock_timeout 2 с, откат целиком при сбое."""
    seller = seller.lower()
    res = run_psql("postgres", f"SELECT 1 FROM sellers WHERE id = '{seller}'::uuid;\n", ["-tA"], env)
    if res.returncode != 0 or res.stdout.strip() != "1":
        raise Refused("seller not found")
    pre = run_psql("postgres", sa.preflight_sql(seller), ["--csv"], env)
    if pre.returncode != 0:
        raise Refused("preflight failed")
    rows = list(csv.reader(io.StringIO(pre.stdout)))[1:]
    catalog = sa.parse_preflight([r for r in rows if len(r) == 3])
    count = len(sa.included_tables({k: set(v) for k, v in catalog.columns.items()}))
    if sa.is_current(catalog, seller):
        _apply(sa.render_role_sql(seller), env)
        state = "unchanged"
    else:
        _apply(sa.render_sql(seller, catalog), env)
        state = "applied"
    return f"ok role={sa.role_name(seller)} tables={count} spec={sa.SPEC_VERSION} state={state}"


def find_seller(query: str, env: dict[str, str] | None = None) -> str:
    res = run_psql("postgres", FIND_SQL, ["--csv", "-v", f"q={escape_like(query)}"], env)
    if res.returncode != 0:
        raise Refused("search failed")
    return res.stdout


def main(env: dict[str, str] | None = None, stdin: str | None = None) -> int:
    env = env if env is not None else dict(os.environ)
    command = env.get("SSH_ORIGINAL_COMMAND", "")
    try:
        if (m := SQL_RE.match(command)):
            data = stdin if stdin is not None else read_stdin_sql()
            return run_sql(m.group(1), data, env)
        if (m := ENSURE_RE.match(command)):
            print(ensure_seller(m.group(1), env))
            return 0
        if (m := FIND_RE.match(command)):
            sys.stdout.write(find_seller(m.group(1), env))
            return 0
    except sc.SqlRefused as exc:
        sys.stderr.write(f"refused: {exc}\n")
        return 3
    except Refused as exc:
        sys.stderr.write(f"refused: {exc}\n")
        return 3
    except (subprocess.SubprocessError, OSError, ValueError, sa.SpecError):
        sys.stderr.write("gateway error\n")
        return 4
    sys.stderr.write("refused: command not allowed\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
