"""WMS-641 В4: чтение боевой базы аналитиками. Реального ssh и боевой базы в тестах нет (подделка ssh)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from support_agent import prod_sql, prompts, sandbox
from support_agent.prod_sql import (
    ProdSqlSettings,
    SqlRefused,
    run_query,
    ssh_argv,
    truncate_csv,
    validate_sql,
    wrap_limit,
)

SELLER = "11111111-2222-3333-4444-555555555555"
ROLE = "wms_agent_s_11111111222233334444555555555555"
SERVER = Path(__file__).resolve().parents[1] / "support_agent" / "prod_sql_mcp.py"


@pytest.mark.parametrize("sql, first", [
    ("SELECT 1", "select"),
    ("select * from t where a = 'x;y' and b = '--no'", "select"),
    ("  SELECT 1;  ", "select"),
    ("with a as (select 1 as n) select * from a", "with"),
    ("EXPLAIN select 1", "explain"),
    ("explain (costs off, format text) select * from t", "explain"),
    ("select 'a;b' as x", "select"),
    ("select \"update\", updated_at, created_at::date from t", "select"),
    ("select 'it''s' as q", "select"),
    ("(select 1) union all (select 2)", "select"),
    ("select count(*) from orders where status = 'insert'", "select"),
])
def test_valid_read_only_queries_pass(sql: str, first: str) -> None:
    query, kind = validate_sql(sql)
    assert kind == first and not query.endswith(";")


@pytest.mark.parametrize("sql", [
    "insert into t values (1)", "update t set a=1", "delete from t", "drop table t", "create table x(a int)",
    "alter table t add column b int", "truncate t", "grant all on t to x", "revoke all on t from x",
    "copy t to '/tmp/x'", "copy (select 1) to program 'id'", "call p()", "do $$ begin end $$",
    "select 1; select 2", "select 1;select 2", "select 1\n;\nselect 2", "select 1; drop table t",
    "select 1 /*;*/ ; drop table t", "select $a$ ; $a$ ; drop table x",
    # круг 9, N4: $ внутри идентификатора раньше маскировал `;` и запрещённые слова
    "SELECT 1 AS a$$; SELECT 2 AS b$$", "SELECT 1 AS a$tag$; COMMIT; SELECT 2 AS b$tag$",
    "EXPLAIN SELECT 1 AS a$$; SET default_transaction_read_only=off; ALTER ROLE CURRENT_USER SET statement_timeout=0; SELECT 1 AS b$$",
    "select $1", "select '$'", "select \"a$b\" from t", "select 1 as a$",
    "with x as (delete from t returning *) select * from x",
    "with x as (insert into t values (1) returning *) select * from x",
    "explain analyze select 1", "explain (analyze) select 1", "explain (analyse, buffers) select 1",
    "select 1 -- comment", "select 1 /* c */", "sel/**/ect 1", "--\nselect 1",
    "select * into t2 from t", "select pg_read_file('/etc/passwd')", "select pg_ls_dir('/')",
    "select lo_import('/etc/passwd')", "select dblink('x','y')", "select set_config('a','b',false)",
    "select pg_sleep(100)", "select nextval('s')", "select pg_terminate_backend(1)",
    "select * from t for update", "select * from t for share", "select * from t for no key update",
    "set role postgres", "reset all", "show all", "table t", "values (1)", "vacuum", "lock table t",
    "begin", "commit", "prepare p as select 1", "execute p", "listen c", "notify c", "reindex table t",
    "\\copy t to x", "select 1\n\\! ls", "\\o /tmp/x", "select '\\' as a", "select 'a\\b'",
    "", "   ", ";", "select 'unterminated", "select \"unterminated", "select $$unterminated",
    "select 1\x00", "select 1\x1b[0m", "x" * 9000, "select " + "1," * 5000 + "1",
])
def test_everything_else_is_refused_before_the_network(sql: str) -> None:
    with pytest.raises(SqlRefused):
        validate_sql(sql)


def test_non_string_and_forbidden_words_inside_strings_are_not_false_positives() -> None:
    with pytest.raises(SqlRefused):
        validate_sql(None)  # type: ignore[arg-type]
    validate_sql("select 'drop table x; delete from y' as text")  # слова внутри строки — это данные


def test_wrap_limit_and_csv_truncation_with_multiline_fields() -> None:
    assert wrap_limit("select 1", "select", 200) == "SELECT * FROM (\nselect 1\n) AS _agent_q LIMIT 201"
    assert wrap_limit("explain select 1", "explain", 200) == "explain select 1"
    rows = "a,b\n" + "".join(f'{i},"line one\nline two {i}"\n' for i in range(10))
    cut = truncate_csv(rows, 3, 10_000)
    assert cut.count("line two") == 3 and "вывод обрезан: показано 3 строк" in cut
    assert "line two 3" not in cut
    whole = truncate_csv("a\n1\n2\n", 5, 10_000)
    assert whole == "a\n1\n2\n" and "обрезан" not in whole
    big = truncate_csv("a\n" + "ю" * 5000 + "\n", 5, 100)
    assert "вывод обрезан по размеру" in big and len(big.encode("utf-8")) < 300


def settings(**over: Any) -> ProdSqlSettings:
    base = dict(ssh_host="sellerfocus.pro", ssh_user="root", ssh_key_path="/keys/prod_ro_ed25519",
                known_hosts="", row_limit=3, timeout_sec=7, max_bytes=10_000, ssh_bin="ssh", db_role=ROLE)
    base.update(over)
    return ProdSqlSettings(**base)  # type: ignore[arg-type]


class FakeSsh:
    def __init__(self, rc: int = 0, out: str = "n\n1\n2\n", err: str = "") -> None:
        self.rc, self.out, self.err = rc, out, err
        self.calls: list[tuple[list[str], str, int]] = []

    def __call__(self, argv: list[str], stdin: str, timeout: int) -> tuple[int, str, str]:
        self.calls.append((argv, stdin, timeout))
        return self.rc, self.out, self.err


def test_ssh_command_and_stdin_format() -> None:
    ssh = FakeSsh()
    assert run_query(settings(), "select 1 as n;", ssh) == "n\n1\n2\n"
    argv, stdin, timeout = ssh.calls[0]
    assert argv == ["ssh", "-F", "/dev/null", "-i", "/keys/prod_ro_ed25519", "-o", "BatchMode=yes", "-o",
                    "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ClearAllForwardings=yes",
                    "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=2",
                    "-T", "root@sellerfocus.pro", f"sql {ROLE}"]
    assert stdin == "SELECT * FROM (\nselect 1 as n\n) AS _agent_q LIMIT 4\n" and timeout == 7
    assert "-o" in ssh_argv(settings(known_hosts="/keys/known_hosts"))
    assert "UserKnownHostsFile=/keys/known_hosts" in ssh_argv(settings(known_hosts="/keys/known_hosts"))


def test_refused_sql_never_reaches_ssh_and_limits_apply() -> None:
    ssh = FakeSsh()
    for bad in ("delete from t", "select 1; select 2", "explain analyze select 1", "select 1 -- x",
                "SELECT 1 AS a$$; SELECT 2 AS b$$", "EXPLAIN SELECT 1 AS a$t$; COMMIT; SELECT 2 AS b$t$"):
        with pytest.raises(SqlRefused):
            run_query(settings(), bad, ssh)
    assert ssh.calls == []
    many = "n\n" + "".join(f"{i}\n" for i in range(50))
    out = run_query(settings(row_limit=3), "select n from t", FakeSsh(out=many))
    assert out.splitlines()[:4] == ["n", "0", "1", "2"] and "показано 3 строк" in out
    explain = run_query(settings(row_limit=2), "explain select 1", FakeSsh(out="QUERY PLAN\n" + "p\n" * 10))
    assert "показано 2 строк" in explain


def test_timeout_and_server_errors_are_reported_not_hidden() -> None:
    with pytest.raises(RuntimeError, match="не уложился в 7 с"):
        run_query(settings(), "select 1", FakeSsh(rc=124))
    with pytest.raises(RuntimeError, match="ошибка запроса .*permission denied for table secrets"):
        run_query(settings(), "select * from secrets", FakeSsh(rc=1, err="ERROR: permission denied for table secrets"))
    with pytest.raises(RuntimeError, match="код 255"):
        run_query(settings(), "select 1", FakeSsh(rc=255, err="Permission denied (publickey)"))
    assert prod_sql.default_runner(["/nonexistent-ssh-binary"], "", 5)[0] == 127


def test_default_runner_enforces_timeout(tmp_path: Path) -> None:
    sleeper = tmp_path / "slow"
    sleeper.write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
    sleeper.chmod(0o755)
    assert prod_sql.default_runner([str(sleeper)], "", 1)[0] == 124


# ------------------------------------------------------------------ MCP-сервер
def stub_ssh(tmp_path: Path, csv_out: str = "code\n111\n222\n") -> tuple[Path, Path]:
    log = tmp_path / "ssh-received.txt"
    stub = tmp_path / "fake-ssh"
    stub.write_text(f'#!/bin/sh\ncat > "{log}"\nprintf %s "{csv_out}"\n'.replace('"code\n111\n222\n"', "x"), encoding="utf-8")
    stub.write_text("#!/bin/sh\ncat > \"" + str(log) + "\"\nprintf 'code\\n111\\n222\\n'\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return stub, log


def rpc(argv: list[str], messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    res = subprocess.run(argv, input="\n".join(json.dumps(m) for m in messages) + "\n", capture_output=True,
                         text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    return [json.loads(line) for line in res.stdout.splitlines()]


CALL = {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "sql_query", "arguments": {}}}


def test_mcp_server_protocol_with_fake_ssh_binary(tmp_path: Path) -> None:
    stub, log = stub_ssh(tmp_path)
    argv = [sys.executable, "-E", "-s", "-S", str(SERVER), "--ssh-host", "h", "--ssh-user", "u", "--key",
            str(tmp_path / "key"), "--ssh-bin", str(stub), "--row-limit", "5", "--db-role", ROLE]
    ok = {**CALL, "params": {"name": "sql_query", "arguments": {"sql": "select code from t"}}}
    bad = {**CALL, "id": 4, "params": {"name": "sql_query", "arguments": {"sql": "drop table t"}}}
    other = {**CALL, "id": 5, "params": {"name": "shell", "arguments": {}}}
    out = rpc(argv, [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                     {"jsonrpc": "2.0", "method": "notifications/initialized"},
                     {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, ok, bad, other])
    assert [r["id"] for r in out] == [1, 2, 3, 4, 5]
    assert [t["name"] for t in out[1]["result"]["tools"]] == ["sql_query"]  # единственный инструмент
    assert out[2]["result"]["content"][0]["text"].startswith("code\n111\n222") and not out[2]["result"]["isError"]
    assert log.read_text(encoding="utf-8") == "SELECT * FROM (\nselect code from t\n) AS _agent_q LIMIT 6\n"
    assert out[3]["result"]["isError"] and out[3]["result"]["content"][0]["text"].startswith("ОТКАЗ")
    assert out[4]["result"]["isError"]


# ------------------------------------------------------------------ wiring в аналитиков
def make_router(tmp_path: Path, enabled: bool = True) -> Any:
    from support_agent.llm import LlmRouter
    from support_agent.store import Store

    from .conftest import make_config

    cfg = make_config(tmp_path)
    cfg.prod_db.enabled = enabled
    cfg.prod_db.ssh_key_path = str(tmp_path / "prod_ro_ed25519")
    return LlmRouter(cfg, Store(cfg.db_path))


def test_claude_analyst_gets_only_the_sql_mcp_tool_when_enabled(tmp_path: Path) -> None:
    llm = make_router(tmp_path)
    argv = llm.build_claude("opus", "readonly", None, None, str(tmp_path), with_db=llm.with_prod_db("analyst", "readonly", ROLE), db_role=ROLE)
    assert "--strict-mcp-config" in argv
    config = json.loads(argv[argv.index("--mcp-config") + 1])
    assert list(config["mcpServers"]) == ["proddb"]
    server = config["mcpServers"]["proddb"]
    assert server["command"] == sandbox.SANDBOX_EXEC and "prod_sql_mcp.py" in " ".join(server["args"])
    allowed = argv[argv.index("--allowedTools") + 1: argv.index("--disallowedTools")]
    assert "mcp__proddb__sql_query" in allowed and "Edit" not in allowed and "Bash" not in allowed
    denied = argv[argv.index("--disallowedTools") + 1:]
    assert "Read(~/.wms-support-agent/**)" in denied and "Read(~/.ssh/**)" in denied  # модели ключ недоступен
    settings_json = json.loads(argv[argv.index("--settings") + 1])["sandbox"]
    assert any(p.endswith("/.ssh") for p in settings_json["filesystem"]["denyRead"])


@pytest.mark.parametrize("role, mode, expected", [("analyst", "readonly", True), ("review", "readonly", True),
                                                   ("routine", "write", False), ("filter", "text", False),
                                                   ("frontend", "write", False), ("analyst", "text", False)])
def test_tool_is_given_only_to_read_only_analysis_roles(tmp_path: Path, role: str, mode: str, expected: bool) -> None:
    llm = make_router(tmp_path)
    assert llm.with_prod_db(role, mode, ROLE) is expected
    argv = llm.build_claude("sonnet", mode, None, None, str(tmp_path),
                            with_db=llm.with_prod_db(role, mode, ROLE), db_role=ROLE)
    assert ("--mcp-config" in argv) is expected


def test_disabled_means_no_tool_for_either_analyst(tmp_path: Path) -> None:
    llm = make_router(tmp_path, enabled=False)
    assert llm.with_prod_db("analyst", "readonly") is False
    claude = llm.build_claude("opus", "readonly", None, None, str(tmp_path), with_db=False)
    assert "--mcp-config" not in claude and "mcp__proddb__sql_query" not in claude
    codex = llm.build_codex("gpt-5.6-sol", "low", "readonly", None, str(tmp_path), "/tmp/o", role="analyst")
    assert not any("proddb" in a for a in codex)


def test_codex_analyst_gets_second_mcp_server_next_to_the_project_reader(tmp_path: Path) -> None:
    llm = make_router(tmp_path)
    argv = llm.build_codex("gpt-5.6-sol", "low", "readonly", None, str(tmp_path), "/tmp/o", role="analyst",
                           db_role=ROLE)
    assert any(a.startswith("mcp_servers.wms.command=") for a in argv)  # читатель проекта на месте
    command = json.loads(next(a for a in argv if a.startswith("mcp_servers.proddb.command=")).split("=", 1)[1])
    args = json.loads(next(a for a in argv if a.startswith("mcp_servers.proddb.args=")).split("=", 1)[1])
    assert command == sandbox.SANDBOX_EXEC and args[0] == "-p"
    profile = args[1]
    assert '(allow network-outbound (remote tcp "*:22"))' in profile and "(deny file-write*)" in profile
    assert f'(subpath "{os.path.realpath(tmp_path)}/prod_ro_ed25519")' in profile  # ровно ключ
    assert "-E" in args and "-s" in args and "-S" in args and "--key" in args
    assert 'mcp_servers.proddb.default_tools_approval_mode="approve"' in argv
    assert "shell_tool" in argv  # оболочка у Codex по-прежнему отключена
    write = llm.build_codex("gpt-5.6-sol", "low", "write", None, str(tmp_path), "/tmp/o", role="routine")
    assert not any("proddb" in a for a in write)


def test_prompts_switch_with_the_tool_and_keep_the_ban_on_inventing_and_client_boundaries() -> None:
    on, off = prompts.analyst_rules(True), prompts.analyst_rules(False)
    assert "sql_query" in on and "ЖЁСТКИЙ ЗАПРЕТ выдумывать данные остаётся" in on
    flat = " ".join(on.split())
    assert "answer_needs_data=true ставь, только если нужных данных нет ни в обращении, ни в коде, ни в базе" in flat
    assert "роль видит только данные селлера ЭТОГО обращения" in flat and "фильтруй по ним" not in flat
    assert "НЕТ доступа к данным прода" in off and "sql_query" not in off
    assert prompts.ANALYST_RULES == off


def test_pipeline_passes_the_right_rules_to_the_analyst(env: Any) -> None:
    from .test_pipeline_chat import ANALYSIS_BUG, script

    for enabled in (False, True):
        env.cfg.prod_db.enabled = enabled
        env.store.set_binding(-100111, {"seller_id": SELLER, "seller_name": "S", "tenant_id": "t",
                                        "tenant_name": "T"}, "1")
        env.llm.calls.clear()
        script(env, dict(ANALYSIS_BUG))
        env.say(-100111, f"[новая] проблема {enabled}", msg_id=f"p{enabled}")
        env.clock.advance(130)
        env.pipe.tick()
        env.clock.advance(1000)
        env.pipe.tick()
        analyst = [c for c in env.llm.calls if c["role"] == "analyst"][-1]
        assert ("sql_query" in analyst["context"]) is enabled
        assert "ЖЁСТКИЙ ЗАПРЕТ выдумывать данные" in analyst["context"]


def test_config_section_and_check_config_warnings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from support_agent.__main__ import check_config
    from support_agent.config import config_from_dict

    cfg = config_from_dict({"prod_db": {"enabled": True, "row_limit": 50, "timeout_sec": 9, "known_hosts": "~/kh"}})
    assert cfg.prod_db.enabled and cfg.prod_db.row_limit == 50 and cfg.prod_db.ssh_host == "sellerfocus.pro"
    assert config_from_dict({}).prod_db.enabled is False  # по умолчанию выключено
    key = tmp_path / "key"
    key.write_text("k", encoding="utf-8")
    key.chmod(0o644)
    path = tmp_path / "c.json"
    base = {"repo": "/x", "telegram": {"intake_bot_token": "1:AAAAAAAAAAAAAAAA", "owner_bot_token": "2:BBBBBBBBBBBBBBBB",
                                       "owner_user_id": 1, "owner_chat_id": -1, "chats": {"-2": {"role": "client"}}}}
    path.write_text(json.dumps({**base, "prod_db": {"enabled": True, "ssh_key_path": str(key)}}), encoding="utf-8")
    check_config(str(path))
    assert "доступен другим пользователям" in capsys.readouterr().out
    path.write_text(json.dumps({**base, "prod_db": {"enabled": True, "ssh_key_path": str(tmp_path / "none")}}),
                    encoding="utf-8")
    check_config(str(path))
    assert "ключа нет" in capsys.readouterr().out


# ------------------------------------------------------------------ профиль процесса с ssh
@pytest.mark.skipif(not sandbox.available(), reason="needs macOS sandbox-exec")
def test_ssh_process_profile_allows_only_key_port_22_and_blocks_the_rest() -> None:
    import shutil

    base = Path(tempfile.mkdtemp(prefix=".wms-prodsql-", dir=str(Path.home())))
    try:
        key = base / "key"
        other = base / "other-secret.txt"
        key.write_text("KEY-CONTENT", encoding="utf-8")
        other.write_text("OTHER-SECRET", encoding="utf-8")
        profile = sandbox.prod_sql_profile([str(base / "key"), str(SERVER.parent), sys.prefix, sys.base_prefix])
        probe = (
            "import socket, sys\n"
            "def t(n, f):\n"
            "    try:\n        f(); print(n, 'OK')\n"
            "    except PermissionError:\n        print(n, 'DENIED')\n"
            "    except OSError as e:\n        print(n, 'ALLOWED-' + type(e).__name__)\n"
            "t('read_key', lambda: open(sys.argv[1]).read())\n"
            "t('read_other', lambda: open(sys.argv[2]).read())\n"
            "t('write', lambda: open(sys.argv[1] + '.w', 'w').write('x'))\n"
            "t('port_22', lambda: socket.create_connection(('127.0.0.1', 22), timeout=3).close())\n"
            "t('port_8080', lambda: socket.create_connection(('127.0.0.1', 8080), timeout=3).close())\n"
        )
        res = subprocess.run([sandbox.SANDBOX_EXEC, "-p", profile, sys.executable, "-E", "-s", "-S", "-c", probe,
                              str(key), str(other)], capture_output=True, text=True, timeout=60)
        lines = dict(line.split() for line in res.stdout.strip().splitlines())
        assert lines["read_key"] == "OK" and lines["read_other"] == "DENIED" and lines["write"] == "DENIED"
        assert lines["port_8080"] == "DENIED"  # другие порты закрыты
        assert lines["port_22"] != "DENIED"  # порт 22 разрешён (откажет сам хост, если там никого нет)
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.mark.skipif(not sandbox.available(), reason="needs macOS sandbox-exec")
def test_full_sandboxed_server_command_works_with_fake_ssh(tmp_path: Path) -> None:
    llm = make_router(tmp_path)
    stub, log = stub_ssh(tmp_path)
    llm.cfg.prod_db.ssh_bin = str(stub)
    command, args = llm.prod_sql_server(None, ROLE)
    ok = {**CALL, "params": {"name": "sql_query", "arguments": {"sql": "select code from t"}}}
    out = rpc([command, *args], [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, ok])
    assert out[1]["result"]["content"][0]["text"].startswith("code\n111\n222") and not out[1]["result"]["isError"]
    assert not log.exists()  # под профилем запись на диск запрещена даже подставному ssh
