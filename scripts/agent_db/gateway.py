#!/usr/bin/env python3
"""WMS-641: шлюз для forced command единственного ssh-ключа агента-диспетчера (запускается на сервере).

В authorized_keys ключ агента привязан к этой программе (no-pty, no-port-forwarding, ...). Из
SSH_ORIGINAL_COMMAND принимается РОВНО одна из трёх форм, всё остальное отклоняется:

  sql wms_agent_s_<32 hex>      psql под этой ролью, SQL из stdin, ответ CSV в stdout
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seller_access as sa  # noqa: E402

DEFAULT_BASE = ["docker", "exec", "-i", "wms_prod-db-1", "psql"]
SQL_RE = re.compile(r"^sql (wms_agent_s_[0-9a-f]{32})$")
ENSURE_RE = re.compile(r"^ensure-seller ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")
FIND_RE = re.compile(r"^find-seller ([0-9A-Za-zА-Яа-яЁё .,'\"«»()+&/_-]{2,80})$")
FIND_SQL = (
    "SELECT s.id AS seller_id, s.name AS seller_name, s.tenant_id, t.name AS tenant_name "
    "FROM sellers s JOIN tenants t ON t.id = s.tenant_id "
    "WHERE s.name ILIKE '%' || :'q' || '%' ORDER BY s.name, t.name LIMIT 10;\n"
)


class Refused(Exception):
    pass


def psql_argv(user: str, extra: list[str] | None = None, env: dict[str, str] | None = None) -> list[str]:
    env = env if env is not None else dict(os.environ)
    base = json.loads(env["AGENT_DB_PSQL"]) if env.get("AGENT_DB_PSQL") else list(DEFAULT_BASE)
    db = env.get("AGENT_DB_NAME", "wms")
    return [*base, "-U", user, "-d", db, "-X", "-v", "ON_ERROR_STOP=1", *(extra or [])]


def run_psql(user: str, stdin: str, extra: list[str] | None = None,
             env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(psql_argv(user, extra, env), input=stdin, capture_output=True, text=True, timeout=120)


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def ensure_seller(seller: str, env: dict[str, str] | None = None) -> str:
    seller = seller.lower()
    res = run_psql("postgres", f"SELECT 1 FROM sellers WHERE id = '{seller}'::uuid;\n", ["-tA"], env)
    if res.returncode != 0 or res.stdout.strip() != "1":
        raise Refused("seller not found")
    pre = run_psql("postgres", sa.preflight_sql(), ["--csv"], env)
    if pre.returncode != 0:
        raise Refused("preflight failed")
    rows = list(csv.reader(io.StringIO(pre.stdout)))[1:]
    catalog = sa.parse_preflight([r for r in rows if len(r) == 3])
    sql = sa.render_sql(seller, catalog)
    applied = run_psql("postgres", sql, ["-q"], env)
    if applied.returncode != 0:
        raise Refused("apply failed: " + applied.stderr.strip()[:300])
    count = len(sa.included_tables({k: set(v) for k, v in catalog.columns.items()}))
    return f"ok role={sa.role_name(seller)} tables={count} spec={sa.SPEC_VERSION}"


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
            data = stdin if stdin is not None else sys.stdin.read()
            res = run_psql(m.group(1), data, ["--csv"], env)
            sys.stdout.write(res.stdout)
            sys.stderr.write(res.stderr)
            return res.returncode
        if (m := ENSURE_RE.match(command)):
            print(ensure_seller(m.group(1), env))
            return 0
        if (m := FIND_RE.match(command)):
            sys.stdout.write(find_seller(m.group(1), env))
            return 0
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
