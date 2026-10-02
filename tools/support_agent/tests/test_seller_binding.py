"""WMS-641 R39-R44: привязка клиентского чата к селлеру только владельцем, роль базы по обращению.

Реального ssh, Telegram и боевой базы нет: шлюз подменён."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from support_agent import prod_sql, prompts
from support_agent.llm import ExecResult
from support_agent.prod_sql import ProdSqlSettings, SqlRefused, role_for_seller, run_query
from support_agent.seller_directory import Candidate, DirectoryError, SellerDirectory, clean_name

from .conftest import CLIENT_CHAT, OWNER_CHAT, OWNER_ID
from .test_pipeline_chat import ANALYSIS_BUG, form_row, script
from .test_prod_sql import ROLE, SELLER, make_router, settings

S2 = "99999999-8888-7777-6666-555555555555"
ROLE2 = "wms_agent_s_99999999888877776666555555555555"


class FakeDirectory:
    """Подделка шлюза: find ищет по подстроке, журнал вызовов."""

    def __init__(self, sellers: list[Candidate]) -> None:
        self.sellers = sellers
        self.finds: list[str] = []
        self.ensures: list[str] = []
        self.fail_ensure = False

    def find(self, name: str) -> list[Candidate]:
        n = clean_name(name)  # как делает настоящая директория
        self.finds.append(n)
        n = n.lower()
        return [c for c in self.sellers if n in c.seller_name.lower()]

    def ensure(self, seller_id: str) -> None:
        self.ensures.append(seller_id)
        if self.fail_ensure:
            raise DirectoryError("down")


A = Candidate(SELLER, "ИП Ромашка", "t-1", "ФФ Север")
B = Candidate(S2, "ИП Ромашка", "t-2", "ФФ Юг")
C = Candidate("00000000-0000-0000-0000-00000000000c", "ИП Василёк", "t-1", "ФФ Север")


@pytest.fixture
def bind(env: Any) -> SimpleNamespace:
    d = FakeDirectory([A, B, C])
    env.pipe.directory = d
    env.fd = d
    return env


def reply_id(env: Any, key: str) -> str:
    row = env.store.outbox_by_key(key)
    assert row is not None and row["tg_message_id"], key
    return str(row["tg_message_id"])


def client_texts(env: Any) -> list[str]:
    return env.tg.to(CLIENT_CHAT)


# --------------------------------------------------------------- C36: привязка только владельцем
def test_owner_binds_chat_by_confirmed_candidate_without_any_model_call(bind: Any) -> None:
    bind.say(CLIENT_CHAT, "привяжи к ИП Василёк", user=OWNER_ID, msg_id="10")
    bind.flush()
    assert bind.llm.calls == []  # поиск и подтверждение решает код, модель не участвует
    assert bind.fd.finds == ["Василёк"] and bind.store.binding(CLIENT_CHAT) is None
    text = client_texts(bind)[-1]
    assert "«ИП Василёк» в фулфилменте «ФФ Север»" in text and "00000000" not in text  # без идентификаторов
    bind.say(CLIENT_CHAT, "да", user=OWNER_ID, reply_to=reply_id(bind, "bind:1"), msg_id="11")
    row = bind.store.binding(CLIENT_CHAT)
    assert row["seller_id"] == C.seller_id and row["tenant_id"] == "t-1" and row["bound_by"] == str(OWNER_ID)
    assert bind.fd.ensures == [C.seller_id] and bind.llm.calls == []
    bind.flush()
    assert "чат привязан к селлеру «ИП Василёк»" in client_texts(bind)[-1]


def test_two_sellers_with_the_same_name_need_a_number_and_yes_is_not_enough(bind: Any) -> None:
    bind.say(CLIENT_CHAT, "Привяжи этот чат к ИП Ромашка", user=OWNER_ID, msg_id="10")
    bind.flush()
    listing = client_texts(bind)[-1]
    assert "1. «ИП Ромашка» в фулфилменте «ФФ Север»" in listing and "2. «ИП Ромашка» в фулфилменте «ФФ Юг»" in listing
    rid = reply_id(bind, "bind:1")
    bind.say(CLIENT_CHAT, "да", user=OWNER_ID, reply_to=rid, msg_id="11")
    assert bind.store.binding(CLIENT_CHAT) is None  # «да» при двух кандидатах ничего не выбирает
    bind.say(CLIENT_CHAT, "3", user=OWNER_ID, reply_to=rid, msg_id="12")
    assert bind.store.binding(CLIENT_CHAT) is None  # номера нет в списке
    bind.say(CLIENT_CHAT, "2", user=OWNER_ID, reply_to=rid, msg_id="13")
    assert bind.store.binding(CLIENT_CHAT)["seller_id"] == S2 and bind.llm.calls == []


def test_confirmation_without_reply_to_our_message_does_nothing(bind: Any) -> None:
    bind.say(CLIENT_CHAT, "привяжи к ИП Василёк", user=OWNER_ID, msg_id="10")
    bind.say(CLIENT_CHAT, "да", user=OWNER_ID, msg_id="11")  # не ответом на сообщение бота
    assert bind.store.binding(CLIENT_CHAT) is None
    bind.say(CLIENT_CHAT, "да", user=OWNER_ID, reply_to="777", msg_id="12")  # ответ на чужое сообщение
    assert bind.store.binding(CLIENT_CHAT) is None


def test_non_owner_cannot_bind_or_confirm(bind: Any) -> None:
    script(bind)
    bind.say(CLIENT_CHAT, "привяжи к ИП Василёк", user=5, msg_id="10")
    assert bind.fd.finds == [] and bind.store.binding(CLIENT_CHAT) is None  # у чужой команды силы нет
    before = len(bind.llm.calls)  # обычное сообщение клиента прошло обычный путь (фильтр), как и должно
    bind.say(CLIENT_CHAT, "привяжи к ИП Василёк", user=OWNER_ID, msg_id="11")
    bind.flush()
    rid = reply_id(bind, "bind:1")
    bind.say(CLIENT_CHAT, "да", user=5, reply_to=rid, msg_id="12")  # клиент отвечает «да» вместо владельца
    bind.say(CLIENT_CHAT, "1", user=77, reply_to=rid, msg_id="13")
    assert bind.store.binding(CLIENT_CHAT) is None and bind.fd.ensures == []
    assert bind.store.proposal(1)["status"] == "open"
    assert len(bind.llm.calls) == before  # ответы клиента на служебное сообщение отброшены без модели


def test_owner_binding_is_rejected_in_partner_and_owner_chats(bind: Any) -> None:
    from .conftest import PARTNER_CHAT

    script(bind)
    bind.say(PARTNER_CHAT, "привяжи к ИП Василёк", user=OWNER_ID, msg_id="10")
    assert bind.fd.finds == [] and bind.store.binding(PARTNER_CHAT) is None


def test_seller_not_found_and_gateway_failure_are_reported_to_the_chat(bind: Any) -> None:
    bind.say(CLIENT_CHAT, "привяжи к ИП Нету", user=OWNER_ID, msg_id="10")
    bind.flush()
    assert "не нашёл" in client_texts(bind)[-1] and bind.store.binding(CLIENT_CHAT) is None

    def broken(name: str) -> list[Candidate]:
        raise DirectoryError("шлюз")

    bind.fd.find = broken
    bind.say(CLIENT_CHAT, "привяжи к ИП Василёк", user=OWNER_ID, msg_id="11")
    bind.flush()
    assert "недоступен" in client_texts(bind)[-1] and bind.store.binding(CLIENT_CHAT) is None


def test_voice_command_with_latin_ip_prefix_is_recognised_and_cleaned(bind: Any) -> None:
    bind.tr.text = "привяжи к IP Василёк"
    bind.tg.files["f1"] = b"audio"
    bind.say(CLIENT_CHAT, "", user=OWNER_ID, voice=True, msg_id="10")
    bind.pipe.transcribe_pending()
    bind.pipe.route_messages()
    assert bind.fd.finds == ["Василёк"] and bind.llm.calls == []


@pytest.mark.parametrize("raw, clean", [("ИП Ромашка", "Ромашка"), ("ip «Ромашка»", "Ромашка"),
                                         ("индивидуальный предприниматель Ромашка", "Ромашка"),
                                         ("  Ромашка. ", "Ромашка")])
def test_clean_name(raw: str, clean: str) -> None:
    assert clean_name(raw) == clean


def test_binding_survives_restart_and_rebinding_replaces_it(bind: Any) -> None:
    from support_agent.store import Store

    bind.say(CLIENT_CHAT, "привяжи к ИП Василёк", user=OWNER_ID, msg_id="10")
    bind.flush()
    bind.say(CLIENT_CHAT, "да", user=OWNER_ID, reply_to=reply_id(bind, "bind:1"), msg_id="11")
    assert Store(bind.cfg.db_path).binding(CLIENT_CHAT)["seller_id"] == C.seller_id  # после перезапуска
    bind.say(CLIENT_CHAT, "перепривяжи к ИП Ромашка", user=OWNER_ID, msg_id="12")
    bind.flush()
    assert "Сейчас чат привязан к «ИП Василёк»" in client_texts(bind)[-1]
    bind.say(CLIENT_CHAT, "1", user=OWNER_ID, reply_to=reply_id(bind, "bind:2"), msg_id="13")
    assert Store(bind.cfg.db_path).binding(CLIENT_CHAT)["seller_id"] == SELLER
    old = bind.store.proposal(1)
    assert old["status"] == "confirmed"
    bind.say(CLIENT_CHAT, "да", user=OWNER_ID, reply_to=reply_id(bind, "bind:1"), msg_id="14")  # старое предложение
    assert bind.store.binding(CLIENT_CHAT)["seller_id"] == SELLER  # устаревшее подтверждение не действует


def test_ticket_keeps_the_seller_it_was_created_with_after_rebinding(bind: Any) -> None:
    script(bind)
    bind.store.set_binding(CLIENT_CHAT, {"seller_id": SELLER, "seller_name": "ИП Ромашка", "tenant_id": "t-1",
                                         "tenant_name": "ФФ Север"}, str(OWNER_ID))
    bind.say(CLIENT_CHAT, "[новая] не передаётся поставка", msg_id="20")
    assert bind.store.data(1)["seller_id"] == SELLER
    bind.store.set_binding(CLIENT_CHAT, {"seller_id": S2, "seller_name": "ИП Ромашка", "tenant_id": "t-2",
                                         "tenant_name": "ФФ Юг"}, str(OWNER_ID))
    bind.say(CLIENT_CHAT, "[новая] другая проблема", msg_id="21")
    assert bind.store.data(1)["seller_id"] == SELLER  # прежнее обращение не переехало
    ids = [bind.store.data(t["id"])["seller_id"] for t in bind.store.tickets_in("collecting")]
    assert S2 in ids


def test_unbound_chat_ticket_has_no_seller(bind: Any) -> None:
    script(bind)
    bind.say(CLIENT_CHAT, "[новая] не передаётся поставка", msg_id="20")
    assert "seller_id" not in bind.store.data(1)


# --------------------------------------------------------------- C37/C41: роль выбирает только доверенный код
def test_role_name_is_derived_only_from_a_uuid_and_the_shared_role_is_never_accepted() -> None:
    assert role_for_seller(SELLER) == ROLE
    for bad in ("wms_agent_ro", "", "x; drop table t", SELLER + "x", SELLER.upper() + "'", "../etc"):
        with pytest.raises(SqlRefused):
            role_for_seller(bad)
    with pytest.raises(SqlRefused):
        run_query(settings(db_role="wms_agent_ro"), "select 1", lambda *a: (0, "", ""))
    with pytest.raises(SqlRefused):
        run_query(settings(db_role=""), "select 1", lambda *a: (0, "", ""))


def test_ssh_remote_command_is_sql_with_the_ticket_role_only() -> None:
    seen: list[list[str]] = []

    def runner(argv: list[str], stdin: str, timeout: int) -> tuple[int, str, str]:
        seen.append(argv)
        return 0, "n\n1\n", ""

    run_query(settings(), "select 1 as n", runner)
    assert seen[0][-2:] == ["root@sellerfocus.pro", f"sql {ROLE}"]
    assert "wms_agent_ro" not in " ".join(seen[0])


class Capture:
    def __init__(self) -> None:
        self.argvs: list[list[str]] = []

    def __call__(self, argv: list[str], cwd: str | None, timeout: int, stdin: str | None) -> ExecResult:
        self.argvs.append(list(argv))
        if argv[0] == "claude":
            return ExecResult(0, json.dumps({"result": "{}", "session_id": "s", "is_error": False}), "")
        Path(argv[argv.index("-o") + 1]).write_text("{}", encoding="utf-8")
        return ExecResult(0, "", "")


def db_args(argv: list[str]) -> list[str] | None:
    if argv[0] == "claude":
        if "--mcp-config" not in argv:
            return None
        return list(json.loads(argv[argv.index("--mcp-config") + 1])["mcpServers"]["proddb"]["args"])
    raw = [a for a in argv if a.startswith("mcp_servers.proddb.args=")]
    return list(json.loads(raw[0].split("=", 1)[1])) if raw else None


@pytest.mark.parametrize("cli", ["claude", "codex"])
def test_analyst_tool_gets_the_role_of_the_ticket_seller_unbound_gets_no_tool(tmp_path: Path, cli: str) -> None:
    import time

    llm = make_router(tmp_path)
    if cli == "codex":
        llm.store.kv_set("cooldown:claude", time.time() + 999)
    cap = Capture()
    llm.exec = cap
    mine = llm.store.add_ticket(kind="chat", source="t", chat_id=1, seller="s", stage="analysis",
                                data={"seller_id": SELLER})
    other = llm.store.add_ticket(kind="chat", source="t", chat_id=2, seller="s", stage="analysis",
                                 data={"seller_id": S2})
    loose = llm.store.add_ticket(kind="chat", source="t", chat_id=3, seller="s", stage="analysis")
    for tid in (mine, other, loose):
        llm.ask("analyst", "text with wms_agent_ro and role ROLE", mode="readonly", cwd=str(tmp_path), ticket_id=tid)
    llm.ask("analyst", "x", mode="readonly", cwd=str(tmp_path))  # без обращения
    args = [db_args(a) for a in cap.argvs]
    assert args[0] is not None and args[0][args[0].index("--db-role") + 1] == ROLE
    assert args[1] is not None and args[1][args[1].index("--db-role") + 1] == ROLE2
    assert args[2] is None and args[3] is None  # нет привязки или нет обращения: нет инструмента вовсе
    assert not any("wms_agent_ro" in " ".join(db_args(a) or []) for a in cap.argvs)


def test_review_role_also_uses_the_ticket_role_and_text_roles_never_get_the_tool(tmp_path: Path) -> None:
    llm = make_router(tmp_path)
    cap = Capture()
    llm.exec = cap
    tid = llm.store.add_ticket(kind="chat", source="t", chat_id=1, seller="s", stage="analysis",
                               data={"seller_id": SELLER})
    llm.ask("review", "x", mode="readonly", cwd=str(tmp_path), ticket_id=tid)
    llm.ask("filter", "x", ticket_id=tid)
    first, second = (db_args(a) for a in cap.argvs)
    assert first is not None and first[first.index("--db-role") + 1] == ROLE and second is None


def test_role_is_prepared_once_and_failure_means_no_tool(tmp_path: Path) -> None:
    llm = make_router(tmp_path)
    cap = Capture()
    llm.exec = cap
    calls: list[str] = []
    state = {"fail": True}

    def ensure(seller: str) -> None:
        calls.append(seller)
        if state["fail"]:
            raise DirectoryError("шлюз недоступен")

    llm.role_ensurer = ensure
    tid = llm.store.add_ticket(kind="chat", source="t", chat_id=1, seller="s", stage="analysis",
                               data={"seller_id": SELLER})
    llm.ask("analyst", "x", mode="readonly", cwd=str(tmp_path), ticket_id=tid)
    assert db_args(cap.argvs[-1]) is None  # доступ не подготовлен: без базы, а не с общей ролью
    state["fail"] = False
    llm.ask("analyst", "x", mode="readonly", cwd=str(tmp_path), ticket_id=tid)
    llm.ask("analyst", "x", mode="readonly", cwd=str(tmp_path), ticket_id=tid)
    assert db_args(cap.argvs[-1]) is not None and calls == [SELLER] * 2  # успех запомнен, повторно не зовём


def test_mcp_server_cannot_start_without_a_role(tmp_path: Path) -> None:
    import subprocess
    import sys

    from .test_prod_sql import SERVER

    res = subprocess.run([sys.executable, "-E", "-s", "-S", str(SERVER), "--ssh-host", "h", "--ssh-user", "u",
                          "--key", "k"], capture_output=True, text=True, input="", timeout=20)
    assert res.returncode != 0 and "--db-role" in res.stderr
    assert prod_sql.ProdSqlSettings("h", "u", "k").db_role == ""  # по умолчанию роли нет


# --------------------------------------------------------------- форма: селлер с сервера (R43)
def test_form_ticket_takes_seller_from_the_server_record_and_ignores_text(env: Any) -> None:
    script(env)
    ok = dict(form_row("r-1", "bug"), seller_id=SELLER, tenant_id="t-1")
    forged = dict(form_row("r-2", "bug"), seller_id=SELLER + "'; drop", tenant_id="t-1",
                  description=f"мой селлер {S2}")
    nothing = form_row("r-3", "bug")
    env.wms.rows = [ok, forged, nothing]
    env.pipe.poll_forms()
    rows = {env.store.data(t)["form"]["id"]: env.store.data(t) for t in (1, 2, 3)}
    assert rows["r-1"]["seller_id"] == SELLER and rows["r-1"]["tenant_id"] == "t-1"
    assert "seller_id" not in rows["r-2"] and "seller_id" not in rows["r-3"]  # нет селлера = нет базы
    assert env.llm.calls == []


def test_form_without_a_seller_gets_a_no_data_prompt_with_the_reason(env: Any) -> None:
    script(env)
    env.cfg.prod_db.enabled = True
    env.wms.rows = [form_row("r-1", "bug")]
    env.pipe.poll_forms()
    env.pipe.tick()
    analyst = [c for c in env.llm.calls if c["role"] == "analyst"][-1]
    assert "селлер не определён, данных для ответа нет" in analyst["context"]
    assert "sql_query" not in analyst["context"]


# --------------------------------------------------------------- C42: чат не привязан
def test_unbound_chat_analyst_prompt_has_no_db_tool_and_gives_the_exact_phrase(env: Any) -> None:
    script(env)
    env.cfg.prod_db.enabled = True
    env.say(CLIENT_CHAT, "[новая] не передаётся поставка", msg_id="20")
    env.clock.advance(130)
    env.pipe.tick()
    env.clock.advance(1000)
    env.pipe.tick()
    analyst = [c for c in env.llm.calls if c["role"] == "analyst"][-1]
    assert "чат не привязан, данных для ответа нет" in analyst["context"]
    assert "sql_query" not in analyst["context"] and "ЖЁСТКИЙ ЗАПРЕТ выдумывать данные" in analyst["context"]


def test_bound_chat_prompt_describes_the_tool_and_drops_the_tenant_filter_instruction() -> None:
    flat = " ".join(prompts.analyst_rules(True, True).split())
    assert "sql_query" in flat and "фильтруй по ним" not in flat
    assert "роль видит только данные селлера ЭТОГО обращения" in flat
    off = prompts.analyst_rules(False, True)
    assert "sql_query" not in off and "не привязан" not in off  # база выключена: привязка не упоминается


# --------------------------------------------------------------- R44: пометка ответа без запросов к базе
def run_info(env: Any, used_db: bool) -> str:
    def reply(prompt: str, kw: Any) -> dict[str, Any]:
        if used_db:
            env.store.patch_data(kw["ticket_id"], db_used=True)
        return dict(ANALYSIS_BUG, category="info", info_answer="Короба 3 и 5", hotfix={})

    script(env, category="info")
    env.llm.on("analyst", "Разберись", reply)
    env.say(CLIENT_CHAT, "какие короба не отдали?", msg_id="60")
    env.pipe.tick()
    env.clock.advance(130)
    env.pipe.tick()
    env.clock.advance(1000)
    env.pipe.tick()
    env.clock.advance(100)
    env.pipe.tick()
    env.flush()
    return next(t for t in env.tg.to(OWNER_CHAT) if "Короба 3 и 5" in t and "Предпросмотр" in t)


def test_owner_preview_marks_answers_built_without_database_queries(env: Any) -> None:
    preview = run_info(env, used_db=False)
    assert "ответ собран без запросов к базе" in preview and "———\nКороба 3 и 5\n———" in preview


def test_owner_preview_has_no_mark_when_the_database_was_read(env: Any) -> None:
    preview = run_info(env, used_db=True)
    assert "ответ собран без запросов к базе" not in preview and "Короба 3 и 5" in preview


# --------------------------------------------------------------- шлюз: клиент директории
def fake_gateway(out: str = "", rc: int = 0) -> tuple[SellerDirectory, list[list[str]]]:
    seen: list[list[str]] = []

    def runner(argv: list[str], stdin: str, timeout: int) -> tuple[int, str, str]:
        seen.append(argv)
        return rc, out, "refused" if rc else ""

    cfg = ProdSqlSettings("h", "u", "/k", db_role="")
    return SellerDirectory(cfg, runner), seen


def test_directory_find_sends_only_the_fixed_remote_command_and_parses_candidates() -> None:
    csv_out = f"seller_id,seller_name,tenant_id,tenant_name\n{SELLER},ИП Ромашка,t-1,ФФ Север\n"
    directory, seen = fake_gateway(csv_out)
    found = directory.find("ИП Ромашка")
    assert found == [Candidate(SELLER, "ИП Ромашка", "t-1", "ФФ Север")]
    assert seen[0][-1] == "find-seller Ромашка" and seen[0][-2] == "u@h"


@pytest.mark.parametrize("bad", ["", "a", "x; rm -rf /", "x`id`", "x$(id)", "x" * 81, "x|y", "x\\y"])
def test_directory_refuses_unsafe_names_before_any_ssh(bad: str) -> None:
    directory, seen = fake_gateway("")
    with pytest.raises(DirectoryError):
        directory.find(bad)
    assert seen == []


def test_directory_rejects_malformed_gateway_answers_and_ensure_needs_ok() -> None:
    directory, _ = fake_gateway("seller_id,seller_name,tenant_id,tenant_name\nnot-a-uuid,x,y,z\n")
    with pytest.raises(DirectoryError):
        directory.find("Ромашка")
    directory, seen = fake_gateway(f"ok role={ROLE} tables=90 spec=abc\n")
    directory.ensure(SELLER)
    assert seen[0][-1] == f"ensure-seller {SELLER}"
    for bad in ("x; id", ROLE, "", "wms_agent_ro"):
        with pytest.raises(DirectoryError):
            directory.ensure(bad)
    directory, _ = fake_gateway("something else")
    with pytest.raises(DirectoryError):
        directory.ensure(SELLER)
    directory, _ = fake_gateway("", rc=2)
    with pytest.raises(DirectoryError):
        directory.ensure(SELLER)
