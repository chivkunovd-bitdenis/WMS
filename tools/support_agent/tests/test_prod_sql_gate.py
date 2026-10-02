"""Круг 7: N1 (сообщения клиенту при чтении базы только через предпросмотр) и N2 (лимиты вывода SQL)."""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from support_agent import prod_sql
from support_agent.prod_sql import OUTPUT_TRUNCATED_RC, ProdSqlSettings, run_query, truncate_csv
from support_agent.telegram import Bots, flush_outbox

from .conftest import CLIENT_CHAT, OWNER_CHAT, OWNER_ID
from .test_pipeline_chat import ANALYSIS_BUG, script, script_owner
from .test_prod_sql import CALL, ROLE, SELLER, SERVER, FakeSsh, make_router, rpc, settings, stub_ssh
from .test_two_bots import drive_to_summary, two_bot_env, upd  # noqa: F401

MARKER = "Client A,7319"


# ------------------------------------------------------------------ след чтения базы (доверенный, не слова модели)
class DbScript:
    """Подделка CLI: может «записать след» в --log сервера sql_query, как это сделал бы доверенный сервер."""

    def __init__(self, write_log: bool, fail_after: bool = False) -> None:
        self.write_log, self.fail_after = write_log, fail_after

    def __call__(self, argv: list[str], cwd: str | None, timeout: int, stdin: str | None) -> Any:
        from support_agent.llm import ExecResult

        blob = " ".join(argv)
        log = None
        if "--log" in blob:
            if argv[0] == "claude":
                config = json.loads(argv[argv.index("--mcp-config") + 1])
                args = config["mcpServers"]["proddb"]["args"]
            else:
                args = json.loads(next(a for a in argv if a.startswith("mcp_servers.proddb.args="))
                                  .split("=", 1)[1])
            log = args[args.index("--log") + 1]
        if log and self.write_log:
            Path(log).write_text("ok\n", encoding="utf-8")
        if self.fail_after:
            return ExecResult(1, "", "rate limit exceeded")
        if argv[0] == "claude":
            return ExecResult(0, json.dumps({"result": "{}", "session_id": "s", "is_error": False}), "")
        out = Path(argv[argv.index("-o") + 1])
        out.write_text("{}", encoding="utf-8")
        return ExecResult(0, "", "")


@pytest.mark.parametrize("cli", ["claude", "codex"])
def test_db_use_is_recorded_from_the_trusted_server_log_not_from_model_words(tmp_path: Path, cli: str) -> None:
    llm = make_router(tmp_path)
    if cli == "codex":
        llm.store.kv_set("cooldown:claude", time.time() + 999)
    tid = llm.store.add_ticket(kind="chat", source="t", chat_id=1, seller="s", stage="analysis",
                              data={"seller_id": SELLER})
    llm.exec = DbScript(write_log=False)
    llm.ask("analyst", "Я читал базу и получил данные клиента A", mode="readonly", cwd=str(tmp_path), ticket_id=tid)
    assert not llm.store.data(tid).get("db_used")  # слова модели ничего не значат
    llm.exec = DbScript(write_log=True)
    llm.ask("analyst", "x", mode="readonly", cwd=str(tmp_path), ticket_id=tid)
    assert llm.store.data(tid)["db_used"] is True
    assert list((tmp_path / "state" / "prod-sql-log").glob("*.log")) == []  # след прибран


def test_review_role_and_failed_call_after_success_also_mark_the_ticket(tmp_path: Path) -> None:
    from support_agent.llm import LlmUnavailable

    llm = make_router(tmp_path)
    tid = llm.store.add_ticket(kind="chat", source="t", chat_id=1, seller="s", stage="analysis",
                              data={"seller_id": SELLER})
    llm.exec = DbScript(write_log=True, fail_after=True)
    with pytest.raises(LlmUnavailable):
        llm.ask("review", "x", mode="readonly", cwd=str(tmp_path), ticket_id=tid)
    assert llm.store.data(tid)["db_used"] is True  # данные могли попасть в контекст, даже если вызов упал


def test_no_log_and_no_marking_without_the_tool(tmp_path: Path) -> None:
    llm = make_router(tmp_path, enabled=False)
    tid = llm.store.add_ticket(kind="chat", source="t", chat_id=1, seller="s", stage="analysis",
                              data={"seller_id": SELLER})
    llm.exec = DbScript(write_log=True)
    llm.ask("analyst", "x", mode="readonly", cwd=str(tmp_path), ticket_id=tid)
    assert not llm.store.data(tid).get("db_used") and not (tmp_path / "state" / "prod-sql-log").exists()


def test_mcp_server_writes_the_trace_only_for_successful_queries(tmp_path: Path) -> None:
    stub, _ = stub_ssh(tmp_path)
    log = tmp_path / "trace.log"
    log.touch()
    argv = [sys.executable, "-E", "-s", "-S", str(SERVER), "--ssh-host", "h", "--ssh-user", "u", "--key", "k",
            "--ssh-bin", str(stub), "--log", str(log), "--db-role", ROLE]
    bad = {**CALL, "id": 1, "params": {"name": "sql_query", "arguments": {"sql": "delete from t"}}}
    rpc(argv, [bad])
    assert log.read_text(encoding="utf-8") == ""
    ok = {**CALL, "id": 2, "params": {"name": "sql_query", "arguments": {"sql": "select 1"}}}
    rpc(argv, [ok, ok])
    assert log.read_text(encoding="utf-8") == "ok\nok\n"


# ------------------------------------------------------------------ N1: need_data и «пробуйте» через предпросмотр
def analyst_that_read_the_db(env: Any, tid_holder: dict[str, int], analysis: dict[str, Any]) -> None:
    def reply(prompt: str, kw: Any) -> dict[str, Any]:
        env.store.patch_data(kw["ticket_id"], db_used=True)  # как это делает маршрутизатор по следу сервера
        return analysis

    env.llm.on("analyst", "Разберись", reply)


NEED = dict(ANALYSIS_BUG, need_data={"why": "сверить", "points": [f"Подтвердите остаток: {MARKER}"]})


def run_to_question(e: Any) -> None:
    script(e)
    analyst_that_read_the_db(e, {}, NEED)
    e.intake.updates = [upd(1, CLIENT_CHAT, 5, "не сходится остаток")]
    e.agent.poll_telegram(1)
    e.pipe.tick()
    e.clock.advance(130)
    e.pipe.tick()
    e.clock.advance(1000)  # молчание на вопрос о срочности -> разбор -> need_data
    e.pipe.tick()
    flush_outbox(e.store, Bots(e.intake, e.owner, OWNER_CHAT), e.cfg)


def test_need_data_with_db_result_goes_through_owner_preview_in_two_bot_mode(tmp_path: Path) -> None:
    e = two_bot_env(tmp_path)
    run_to_question(e)
    assert e.store.ticket(1)["stage"] == "await_owner_msg"
    client_texts = e.intake.to(CLIENT_CHAT)
    assert len(client_texts) == 1 and "Подскажите, пожалуйста" in client_texts[0]  # только шаблонный вопрос
    assert not any(MARKER in t for t in client_texts) and e.owner.to(CLIENT_CHAT) == []
    previews = [t for t in e.owner.to(OWNER_CHAT) if t.startswith("Предпросмотр сообщения клиенту")]
    assert len(previews) == 1 and MARKER in previews[0] and "читалась база" in previews[0]
    assert e.intake.to(OWNER_CHAT) == []  # предпросмотр только у бота владельца
    # подтверждение «кати» ответом на ЭТОТ предпросмотр: уходит ботом приёма дословно
    preview_id = e.store.outbox_by_key("msgpreview1:1")["tg_message_id"]
    script_owner(e, {"intent": "go", "ticket_ids": [], "all": False})
    e.owner.updates = [{**upd(70, OWNER_CHAT, OWNER_ID, "кати"), "message": {
        **upd(70, OWNER_CHAT, OWNER_ID, "кати")["message"], "reply_to_message": {"message_id": int(preview_id)}}}]
    e.agent.poll_bot("owner", 1)
    e.pipe.tick()
    flush_outbox(e.store, Bots(e.intake, e.owner, OWNER_CHAT), e.cfg)
    sent = e.intake.to(CLIENT_CHAT)
    assert len(sent) == 2 and sent[1].startswith("Чтобы разобраться, пришлите") and MARKER in sent[1]
    assert e.store.ticket(1)["stage"] == "await_client_data" and e.owner.to(CLIENT_CHAT) == []


def test_unconfirmed_and_generic_commands_send_nothing(tmp_path: Path) -> None:
    e = two_bot_env(tmp_path)
    run_to_question(e)
    for _ in range(3):
        e.clock.advance(5000)
        e.pipe.tick()
    flush_outbox(e.store, Bots(e.intake, e.owner, OWNER_CHAT), e.cfg)
    assert len(e.intake.to(CLIENT_CHAT)) == 1 and e.store.ticket(1)["stage"] == "await_owner_msg"
    # то же «кати» через бота приёма (клиентский чат) команда не является
    script_owner(e, {"intent": "go", "ticket_ids": [1], "all": False})
    e.llm.on("filter", "Новое сообщение из клиентского чата", {"relevant": False, "ticket_id": None})
    e.intake.updates = [upd(9, CLIENT_CHAT, OWNER_ID, "кати 1")]
    e.agent.poll_bot("intake", 1)
    e.pipe.tick()
    assert len(e.intake.to(CLIENT_CHAT)) == 1
    # «всё кати» не подтверждает сообщения клиентам
    e.owner.updates = [upd(71, OWNER_CHAT, OWNER_ID, "всё кати")]
    script_owner(e, {"intent": "go", "ticket_ids": [], "all": True})
    e.agent.poll_bot("owner", 1)
    e.pipe.tick()
    flush_outbox(e.store, Bots(e.intake, e.owner, OWNER_CHAT), e.cfg)
    assert len(e.intake.to(CLIENT_CHAT)) == 1 and e.store.ticket(1)["stage"] == "await_owner_msg"
    # явный номер подтверждает, предпросмотр уже доставлен
    e.owner.updates = [upd(72, OWNER_CHAT, OWNER_ID, "кати 1")]
    script_owner(e, {"intent": "go", "ticket_ids": [1], "all": False})
    e.agent.poll_bot("owner", 1)
    e.pipe.tick()
    flush_outbox(e.store, Bots(e.intake, e.owner, OWNER_CHAT), e.cfg)
    assert len(e.intake.to(CLIENT_CHAT)) == 2


def test_rejecting_the_question_continues_analysis_without_sending(tmp_path: Path) -> None:
    e = two_bot_env(tmp_path)
    run_to_question(e)
    e.owner.updates = [upd(73, OWNER_CHAT, OWNER_ID, "нет 1")]
    script_owner(e, {"intent": "reject", "ticket_ids": [1], "all": False})
    e.agent.poll_bot("owner", 1)
    e.pipe.tick()
    flush_outbox(e.store, Bots(e.intake, e.owner, OWNER_CHAT), e.cfg)
    assert len(e.intake.to(CLIENT_CHAT)) == 1  # вопрос клиенту не задан
    assert e.store.data(1)["pending_client"] is None and e.store.data(1)["no_asks"] is True
    assert e.store.ticket(1)["stage"] in ("report_ready", "await_owner")  # разбор довёл до сводки без вопроса


def test_without_db_reads_questions_are_still_automatic(env: Any) -> None:
    script(env, dict(NEED))
    env.say(CLIENT_CHAT, "не сходится остаток", msg_id="a1")
    env.clock.advance(130)
    env.pipe.tick()
    env.clock.advance(1000)
    env.pipe.tick()
    env.flush()
    assert any(t.startswith("Чтобы разобраться, пришлите") for t in env.tg.to(CLIENT_CHAT))
    assert env.store.ticket(1)["stage"] == "await_client_data"


def test_tryit_after_hotfix_with_db_reads_goes_through_preview(env: Any, tmp_path: Path) -> None:
    from .test_owner_and_hotfix import await_owner_ticket, drive, hotfix_env

    hotfix_env(env, tmp_path)
    tid = await_owner_ticket(env)
    env.store.patch_data(tid, db_used=True)
    env.llm.on("routine", "1-2 короткие вежливые фразы", f"Исправили. Данные: {MARKER}")
    env.store.set_stage(tid, "hotfix", hotfix={"step": "start"})
    drive(env, tid)
    assert env.store.ticket(tid)["stage"] == "await_owner_msg"
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == []  # «пробуйте» не ушло
    previews = [t for t in env.tg.to(OWNER_CHAT) if t.startswith("Предпросмотр сообщения клиенту")]
    assert len(previews) == 1 and MARKER in previews[0]
    reports = [t for t in env.tg.to(OWNER_CHAT) if t.startswith("Исправление по обращению")]
    assert len(reports) == 1  # отчёт владельцу, как и раньше
    preview_id = env.store.outbox_by_key(f"msgpreview1:{tid}")["tg_message_id"]
    script_owner(env, {"intent": "go", "ticket_ids": [], "all": False})
    env.say(OWNER_CHAT, "кати", user=OWNER_ID, name="Владелец", reply_to=preview_id, msg_id="oo1")
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == [f"Исправили. Данные: {MARKER}"]
    assert env.store.ticket(tid)["stage"] == "done"
    env.say(OWNER_CHAT, "кати ещё", user=OWNER_ID, name="Владелец", msg_id="oo2")
    env.flush()
    assert len(env.tg.to(CLIENT_CHAT)) == 1  # второй раз не уходит


def test_tryit_without_db_reads_is_sent_immediately_as_before(env: Any, tmp_path: Path) -> None:
    from .test_owner_and_hotfix import await_owner_ticket, drive, hotfix_env

    hotfix_env(env, tmp_path)
    tid = await_owner_ticket(env)
    env.store.set_stage(tid, "hotfix", hotfix={"step": "start"})
    drive(env, tid)
    env.flush()
    assert env.store.ticket(tid)["stage"] == "done" and len(env.tg.to(CLIENT_CHAT)) == 1


def test_stale_preview_reply_is_refused(env: Any) -> None:
    from .test_owner_and_hotfix import await_owner_ticket

    tid = await_owner_ticket(env)
    env.store.patch_data(tid, db_used=True)
    env.pipe.send_client_gated(tid, "k1", "первый текст", None, {"stage": "done", "patch": {}})
    env.flush()
    first = env.store.outbox_by_key(f"msgpreview1:{tid}")["tg_message_id"]
    env.store.set_stage(tid, "await_owner_msg")
    env.pipe.send_client_gated(tid, "k2", "второй текст", None, {"stage": "done", "patch": {}})
    env.flush()
    script_owner(env, {"intent": "go", "ticket_ids": [], "all": False})
    env.say(OWNER_CHAT, "кати", user=OWNER_ID, name="Владелец", reply_to=first, msg_id="st1")
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == [] and any("устаревший предпросмотр" in t for t in env.tg.to(OWNER_CHAT))


# ------------------------------------------------------------------ N2: лимиты вывода
def script_file(tmp_path: Path, name: str, body: str) -> list[str]:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return [sys.executable, str(path)]


def test_runner_stops_a_flooding_process_and_keeps_memory_bounded(tmp_path: Path) -> None:
    argv = script_file(tmp_path, "flood.py", "import sys\nsys.stdin.read()\n"
                       "while True:\n    sys.stdout.write('x' * 65536)\n    sys.stdout.flush()\n")
    started = time.time()
    rc, out, err = prod_sql.default_runner(argv, "select 1\n", timeout=20, max_out=100_000)
    assert rc == OUTPUT_TRUNCATED_RC and len(out.encode()) <= 100_000 and time.time() - started < 15


def test_runner_big_stderr_is_capped_and_does_not_hang(tmp_path: Path) -> None:
    argv = script_file(tmp_path, "err.py", "import sys\nsys.stdin.read()\n"
                       "for _ in range(200):\n    sys.stderr.write('e' * 65536)\nsys.stdout.write('a\\n1\\n')\nsys.exit(3)\n")
    rc, out, err = prod_sql.default_runner(argv, "select 1\n", timeout=30, max_out=100_000)
    assert rc == 3 and out == "a\n1\n" and len(err) <= prod_sql.STDERR_BUDGET
    with pytest.raises(RuntimeError, match="ошибка запроса") as info:
        run_query(settings(), "select 1", lambda a, s, t: (3, "", err))
    assert len(str(info.value)) < 600


def test_runner_timeout_and_normal_output(tmp_path: Path) -> None:
    slow = script_file(tmp_path, "slow.py", "import time, sys\nsys.stdin.read()\ntime.sleep(10)\n")
    assert prod_sql.default_runner(slow, "q\n", timeout=1)[0] == 124
    fine = script_file(tmp_path, "fine.py", "import sys\nsys.stdin.read()\nprint('n')\nprint(1)\n")
    assert prod_sql.default_runner(fine, "q\n", timeout=10) == (0, "n\n1\n", "")


def test_single_huge_field_and_multibyte_text_do_not_crash_parsing() -> None:
    huge = "code\n" + "x" * 300_000 + "\n"
    out = truncate_csv(huge, 200, 60_000)
    assert len(out.encode("utf-8")) < 60_300 and "вывод обрезан по размеру" in out
    multibyte = "t\n" + "ёж" * 100_000 + "\n"  # 400 тыс. байт, обрезка по границе символа
    cut = truncate_csv(multibyte, 200, 60_001)
    assert cut.startswith("t\n") and "вывод обрезан по размеру" in cut
    cut.encode("utf-8")  # корректный UTF-8
    quoted = 'a,b\n1,"' + "z" * 200_000 + '\n'  # оборван внутри кавычек (процесс остановлен посреди поля)
    assert "вывод обрезан" in truncate_csv(quoted, 200, 60_000)
    assert csv.field_size_limit() >= 131072


def test_run_query_reports_truncated_output_with_a_note() -> None:
    out = run_query(settings(max_bytes=10_000), "select 1", lambda a, s, t: (OUTPUT_TRUNCATED_RC, "n\n" + "9" * 50_000, ""))
    assert "вывод оборван: ответ сервера слишком большой" in out and len(out.encode("utf-8")) < 10_300


def test_server_survives_every_refusal_and_handler_crash(tmp_path: Path) -> None:
    flood = tmp_path / "flood-ssh"
    flood.write_text("#!/bin/sh\ncat >/dev/null\npython3 -c \"print('code'); print('x'*400000)\"\n", encoding="utf-8")
    flood.chmod(0o755)
    err_ssh = tmp_path / "err-ssh"
    err_ssh.write_text("#!/bin/sh\ncat >/dev/null\npython3 -c \"import sys; sys.stderr.write('e'*3000000)\"\nexit 1\n",
                       encoding="utf-8")
    err_ssh.chmod(0o755)

    def argv(ssh: Path) -> list[str]:
        return [sys.executable, "-E", "-s", "-S", str(SERVER), "--ssh-host", "h", "--ssh-user", "u", "--key", "k",
                "--ssh-bin", str(ssh), "--max-bytes", "20000", "--timeout", "30", "--db-role", ROLE]

    def call(i: int, sql: str) -> dict[str, Any]:
        return {**CALL, "id": i, "params": {"name": "sql_query", "arguments": {"sql": sql}}}

    out = rpc(argv(flood), [call(1, "select repeat('x', 400000)"), call(2, "drop table t"),
                            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, call(4, "select 1")])
    assert [r["id"] for r in out] == [1, 2, 3, 4]  # каждый вызов получил ответ, сервер жив
    assert "вывод обрезан" in out[0]["result"]["content"][0]["text"] and not out[0]["result"]["isError"]
    assert out[1]["result"]["isError"] and out[2]["result"]["tools"][0]["name"] == "sql_query"
    assert "вывод обрезан" in out[3]["result"]["content"][0]["text"]
    out = rpc(argv(err_ssh), [call(1, "select 1"), call(2, "select 2")])
    assert [r["id"] for r in out] == [1, 2] and all(r["result"]["isError"] for r in out)
    assert len(out[0]["result"]["content"][0]["text"]) < 700


def test_handler_exceptions_become_errors_and_do_not_stop_serving(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from support_agent import prod_sql_mcp

    def boom(settings: Any, sql: str) -> str:
        raise ValueError("unexpected parser failure")

    monkeypatch.setattr(prod_sql_mcp, "run_query", boom)
    lines = [json.dumps({**CALL, "id": 1, "params": {"name": "sql_query", "arguments": {"sql": "select 1"}}}),
             json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})]
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(lines) + "\n"))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    prod_sql_mcp.serve(ProdSqlSettings("h", "u", "k", db_role=ROLE))
    replies = [json.loads(x) for x in out.getvalue().splitlines()]
    assert [r["id"] for r in replies] == [1, 2]
    assert replies[0]["result"]["isError"] and "ValueError" in replies[0]["result"]["content"][0]["text"]
    assert replies[1]["result"]["tools"]


def test_prompt_tells_to_list_columns_and_not_repeat_star_after_permission_denied() -> None:
    from support_agent import prompts

    flat = " ".join(prompts.analyst_rules(True).split())
    assert "users.password_hash" in flat and "permission denied" in flat
    assert "Всегда перечисляй нужные колонки явно" in flat and "не повторяй запрос со звёздочкой" in flat
    assert FakeSsh  # используется общими подделками
