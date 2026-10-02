"""MCP-сервер `sql_query` (stdio, только стандартная библиотека): чтение боевой базы для аналитиков.

Процесс доверенный: только он видит ключ ssh. Модель получает лишь текст CSV или отказ."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

try:  # запуск как скрипта (-I -S) и как модуля
    from prod_sql import ProdSqlSettings, SqlRefused, run_query  # type: ignore[import-not-found]
except ImportError:
    from .prod_sql import ProdSqlSettings, SqlRefused, run_query

PROTOCOL = "2024-11-05"
TOOL = {
    "name": "sql_query",
    "description": (
        "Один SQL-запрос к боевой базе WMS ТОЛЬКО НА ЧТЕНИЕ (SELECT, WITH или EXPLAIN без ANALYZE). "
        "Без комментариев и точки с запятой внутри. Результат — CSV, число строк ограничено."
    ),
    "inputSchema": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]},
}


LOG_PATH: str | None = None


def record_success() -> None:
    """Доверенный след успешного чтения базы: агент по нему (а не по словам модели) узнаёт, что
    результаты SQL могли попасть в разбор обращения (N1)."""
    if LOG_PATH:
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write("ok\n")
        except OSError:
            pass


def handle(settings: ProdSqlSettings, message: dict[str, Any]) -> dict[str, Any] | None:
    method, msg_id = message.get("method"), message.get("id")
    if msg_id is None:
        return None
    if method == "initialize":
        result: dict[str, Any] = {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                                  "serverInfo": {"name": "wms-proddb", "version": "1"}}
    elif method == "tools/list":
        result = {"tools": [TOOL]}
    elif method == "tools/call":
        params = message.get("params") or {}
        if params.get("name") != "sql_query":
            text, is_error = f"неизвестный инструмент {params.get('name')}", True
        else:
            try:
                sql = str((params.get("arguments") or {}).get("sql", ""))
                text, is_error = run_query(settings, sql), False
                record_success()
            except SqlRefused as exc:
                text, is_error = f"ОТКАЗ: {exc}", True
            except RuntimeError as exc:
                text, is_error = f"ОШИБКА: {exc}", True
            except Exception as exc:  # любая другая ошибка не должна ронять сервер
                text, is_error = f"ОШИБКА: внутренняя ошибка обработки ({type(exc).__name__})", True
        result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "method not found"}}
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def serve(settings: ProdSqlSettings) -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        message: Any = None
        try:
            message = json.loads(line)
            reply = handle(settings, message)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        except Exception:  # обработчик упал: отвечаем ошибкой и продолжаем обслуживание
            msg_id = message.get("id") if isinstance(message, dict) else None
            reply = ({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32603, "message": "internal error"}}
                     if msg_id is not None else None)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ssh-host", required=True)
    parser.add_argument("--ssh-user", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--known-hosts", default="")
    parser.add_argument("--ssh-bin", default="ssh")
    parser.add_argument("--row-limit", type=int, default=200)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-bytes", type=int, default=60_000)
    parser.add_argument("--log", default="")
    parser.add_argument("--db-role", required=True)
    a = parser.parse_args()
    global LOG_PATH
    LOG_PATH = a.log or None
    serve(ProdSqlSettings(a.ssh_host, a.ssh_user, a.key, a.known_hosts, a.row_limit, a.timeout, a.max_bytes,
                          a.ssh_bin, a.db_role))


if __name__ == "__main__":
    main()
