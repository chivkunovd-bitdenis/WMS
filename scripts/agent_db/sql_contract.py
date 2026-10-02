"""WMS-641: серверная проверка SQL-контракта шлюза (python 3.9+, только стандартная библиотека).

Это ВТОРАЯ, независимая от агента проверка: шлюз не доверяет ничему, что пришло по ssh. Правила те же,
что у клиента агента (tools/support_agent/support_agent/prod_sql.py), тест сверяет их по общему набору:
один оператор SELECT/WITH/EXPLAIN (без ANALYZE), без обратного слеша (метакоманды psql: shell, \\connect,
\\copy ... PROGRAM, \\gexec), без комментариев, без точки с запятой внутри, без опасных слов и функций.
Заодно здесь очистка текста серверной ошибки от значений данных."""

from __future__ import annotations

import re

MAX_SQL_CHARS = 8500  # клиент ограничивает запрос 8000 символов, потом оборачивает его в подзапрос
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
    pass


def mask_literals(sql: str) -> str:
    """Строки и кавычные идентификаторы заменяются заглушками; комментарии и обратный слеш запрещены."""
    if "\\" in sql:
        raise SqlRefused("backslash is not allowed")
    out = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if sql.startswith("--", i) or sql.startswith("/*", i):
            raise SqlRefused("comments are not allowed")
        if ch in "'\"":
            j = i + 1
            while True:
                if j >= n:
                    raise SqlRefused("unclosed quote")
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
                    raise SqlRefused("unclosed dollar quote")
                out.append("''")
                i = end + len(tag)
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def validate_sql(sql: str) -> str:
    """Нормализованный запрос (без хвостового `;`) или SqlRefused."""
    if not isinstance(sql, str) or not sql.strip():
        raise SqlRefused("empty query")
    if len(sql) > MAX_SQL_CHARS:
        raise SqlRefused("query too long")
    if any(ord(c) < 32 and c not in "\n\t\r" for c in sql):
        raise SqlRefused("control characters are not allowed")
    query = sql.strip()
    while query.endswith(";"):
        query = query[:-1].rstrip()
    masked = mask_literals(query)
    if ";" in masked:
        raise SqlRefused("only one statement is allowed")
    words = masked.split()
    first = (words[0] if words else "").lower().lstrip("(")
    if first not in ALLOWED_FIRST:
        raise SqlRefused("query must start with SELECT, WITH or EXPLAIN")
    if FORBIDDEN_RE.search(masked):
        raise SqlRefused("forbidden keyword")
    if FORBIDDEN_FUNCS.search(masked):
        raise SqlRefused("forbidden function")
    if LOCKING_RE.search(masked):
        raise SqlRefused("locking clauses are not allowed")
    return query


_ERR_RE = re.compile(r"^(?:psql: )?(?:error|fatal):\s+([0-9A-Z]{5}):\s*(.*)$", re.IGNORECASE)
_QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")
MAX_ERROR_CHARS = 240


def sanitize_error(text: str) -> str:
    """Текст серверной ошибки без значений данных: только первая строка. Для класса 42 (синтаксис,
    имена, права) сообщение оставляется (в нём только идентификаторы и фрагменты самого запроса),
    для остальных классов (данные, ограничения) кавычечные фрагменты заменяются на «…»: именно в них
    сервер печатает прочитанные значения. DETAIL/CONTEXT/HINT/QUERY отбрасываются."""
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
    first = next((ln for ln in lines if re.match(r"^(psql: )?(error|fatal)", ln, re.IGNORECASE)),
                 lines[0] if lines else "")
    match = _ERR_RE.match(first)
    if match:
        state, message = match.group(1), match.group(2)
        if not state.startswith("42"):
            message = _QUOTED.sub("«…»", message)
        return f"{state}: {message}"[:MAX_ERROR_CHARS]
    return _QUOTED.sub("«…»", first)[:MAX_ERROR_CHARS]
