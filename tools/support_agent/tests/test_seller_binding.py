"""WMS-641 R39-R44: привязка клиентского чата к селлеру только владельцем, роль базы по обращению.

Реального ssh, Telegram и боевой базы нет: шлюз подменён."""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from support_agent import prod_sql, prompts
from support_agent.llm import ExecResult
from support_agent.prod_sql import ProdSqlSettings, SqlRefused, role_for_seller, run_query
from support_agent.seller_directory import (
    Candidate,
    DirectoryError,
    SellerDirectory,
    TenantCandidate,
    clean_name,
    clean_tenant_name,
)
from support_agent.telegram import Bots, flush_outbox

from .conftest import CLIENT_CHAT, OWNER_CHAT, OWNER_ID, PARTNER_CHAT
from .test_pipeline_chat import ANALYSIS_BUG, form_row, script
from .test_prod_sql import ROLE, SELLER, make_router, settings
from .test_two_bots import two_bot_env

S2 = "99999999-8888-7777-6666-555555555555"
ROLE2 = "wms_agent_s_99999999888877776666555555555555"


class FakeDirectory:
    """Подделка шлюза: find ищет по подстроке, журнал вызовов."""

    def __init__(self, sellers: list[Candidate], tenants: list[TenantCandidate] | None = None) -> None:
        self.sellers = sellers
        self.tenants = tenants or []
        self.tenant_finds: list[str] = []
        self.tenant_ensures: list[str] = []
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

    def find_tenants(self, name: str) -> list[TenantCandidate]:
        n = clean_tenant_name(name)
        self.tenant_finds.append(n)
        words = [w.lower() for w in n.split() if len(w) >= 3] or [n.lower()]
        hits = [(sum(w in t.tenant_name.lower() for w in words), t) for t in self.tenants]
        return [t for score, t in sorted(hits, key=lambda x: -x[0]) if score]

    def ensure_tenant(self, tenant_id: str) -> None:
        self.tenant_ensures.append(tenant_id)
        if self.fail_ensure:
            raise DirectoryError("down")

    def ensure_scope(self, level: str, scope_id: str) -> None:
        (self.ensure_tenant if level == "tenant" else self.ensure)(scope_id)


A = Candidate(SELLER, "ИП Ромашка", "t-1", "ФФ Север")
B = Candidate(S2, "ИП Ромашка", "t-2", "ФФ Юг")
C = Candidate("00000000-0000-0000-0000-00000000000c", "ИП Василёк", "t-1", "ФФ Север")


@pytest.fixture
def bind(env: Any) -> SimpleNamespace:
    d = FakeDirectory([A, B, C])
    env.pipe.directory = d
    env.fd = d
    return env


NEW_CHAT = -100777  # групповой чат, которого нет в config.chats
NEW_TITLE = "Чат Ромашки"
BOT = "@wms_korob_support_bot"
_uid = itertools.count(1)


def gupd(chat: int, user: int, text: str, *, reply_to: int | None = None, title: str = "",
         voice: str | None = None) -> dict[str, Any]:
    uid = next(_uid)
    message: dict[str, Any] = {"message_id": 5000 + uid, "chat": {"id": chat, "title": title}, "date": 1,
                               "from": {"id": user, "first_name": "Имя"}}
    if voice:
        message["voice"] = {"file_id": voice}
    else:
        message["text"] = text
    if reply_to:
        message["reply_to_message"] = {"message_id": reply_to}
    return {"update_id": uid, "message": message}


@pytest.fixture
def be(tmp_path: Path) -> SimpleNamespace:
    """Два бота: приёма (клиентские чаты) и владельца; шлюз подменён."""
    e = two_bot_env(tmp_path)
    e.fd = FakeDirectory([A, B, C])
    e.pipe.directory = e.fd
    e.tmp = tmp_path
    return e


def step(e: Any) -> None:
    e.agent.poll_telegram(1)
    e.pipe.tick()
    flush_outbox(e.store, Bots(e.intake, e.owner, OWNER_CHAT), e.cfg)


def owner_says_in_group(e: Any, text: str, chat: int = NEW_CHAT, title: str = NEW_TITLE) -> None:
    if "@" not in text:
        text = f"{BOT} {text}"  # команда принимается только с упоминанием бота
    e.intake.updates.append(gupd(chat, OWNER_ID, text, title=title))
    step(e)


def owner_replies(e: Any, text: str, to: int | str) -> None:
    e.owner.updates.append(gupd(OWNER_CHAT, OWNER_ID, text, reply_to=int(to)))
    step(e)


def proposal_msg_id(e: Any, pid: int = 1) -> str:
    row = e.store.outbox_by_key(f"bind:{pid}")
    assert row is not None and row["tg_message_id"]
    return str(row["tg_message_id"])


def assert_intake_bot_said_nothing(e: Any) -> None:
    """Бот приёма не отправил ни одного сообщения и документа никуда: названий селлеров в чатах нет."""
    assert e.intake.sent == [] and e.intake.documents == []


# --------------------------------------------------------------- C36: привязка только владельцем, только ботом владельца
def test_owner_command_in_a_group_outside_config_goes_to_the_owner_only(be: Any) -> None:
    assert NEW_CHAT not in be.cfg.telegram.chats
    owner_says_in_group(be, f"{BOT} привяжи к ИП Василёк")
    assert_intake_bot_said_nothing(be)  # в самом чате тишина
    text = be.owner.to(OWNER_CHAT)[-1]
    assert "селлер «ИП Василёк» в фулфилменте «ФФ Север»" in text and f"чат «{NEW_TITLE}»" in text
    assert "00000000" not in text  # без идентификаторов
    assert be.llm.calls == [] and be.fd.finds == ["Василёк"]  # поиск решает код, модель не участвует
    assert be.store.binding(NEW_CHAT) is None and NEW_CHAT not in be.cfg.telegram.chats  # ещё не привязан


def test_owner_confirms_in_his_chat_and_the_group_becomes_a_served_client_chat(be: Any) -> None:
    from .test_pipeline_chat import script

    script(be)
    owner_says_in_group(be, f"{BOT} привяжи к ИП Василёк")
    owner_replies(be, "да", proposal_msg_id(be))
    row = be.store.binding(NEW_CHAT)
    assert row["seller_id"] == C.seller_id and row["tenant_id"] == "t-1" and row["chat_title"] == NEW_TITLE
    assert be.fd.ensures == [C.seller_id] and be.llm.calls == []
    done = be.owner.to(OWNER_CHAT)[-1]
    assert f"Чат «{NEW_TITLE}» привязан к селлеру «ИП Василёк»" in done
    assert_intake_bot_said_nothing(be)  # и после привязки в клиентский чат ничего
    # без правки config.json чат обслуживается как клиентский: сообщение клиента даёт обращение с селлером
    assert be.cfg.telegram.chats[NEW_CHAT].role == "client"
    be.intake.updates.append(gupd(NEW_CHAT, 5, "[новая] не передаётся поставка"))
    step(be)
    ticket = be.store.ticket(1)
    assert ticket["chat_id"] == NEW_CHAT and be.store.data(1)["seller_id"] == C.seller_id


def test_group_messages_before_binding_are_neither_saved_nor_processed(be: Any) -> None:
    be.intake.updates += [
        gupd(NEW_CHAT, 5, "[новая] не передаётся поставка", title=NEW_TITLE),   # клиент
        gupd(NEW_CHAT, OWNER_ID, "просто разговор", title=NEW_TITLE),            # владелец без команды
        gupd(NEW_CHAT, 5, f"{BOT} привяжи к ИП Василёк", title=NEW_TITLE),       # команда не от владельца
        gupd(NEW_CHAT, OWNER_ID, "", voice="f1", title=NEW_TITLE),               # голос в неизвестном чате
        gupd(NEW_CHAT, 5, "привяжи к ИП Василёк", title=NEW_TITLE),
    ]
    step(be)
    assert be.store.rows("SELECT * FROM messages") == []  # ничего не сохранено
    assert be.store.rows("SELECT * FROM tickets") == [] and be.llm.calls == [] and be.fd.finds == []
    assert_intake_bot_said_nothing(be) and be.owner.sent == []
    last = max(u["update_id"] for u in be.intake.updates)
    assert be.store.kv_get("tg_offset:intake") == last + 1  # обновления прочитаны и позиция продвинута


def test_command_works_only_in_group_chats_not_in_private_owner_or_partner_chats(be: Any, tmp_path: Path) -> None:
    from support_agent.telegram import normalize_update

    cfg = be.cfg
    mk = lambda chat, bot="intake": normalize_update(  # noqa: E731
        gupd(chat, OWNER_ID, f"{BOT} привяжи к ИП Василёк"), cfg, bot)
    assert mk(NEW_CHAT).role == "bind"  # type: ignore[union-attr]
    assert mk(CLIENT_CHAT).role == "bind"  # type: ignore[union-attr]  # уже обслуживаемый клиентский чат: перепривязка
    assert mk(NEW_CHAT, "owner") is None  # через бота владельца в группах команды нет
    assert mk(PARTNER_CHAT).role == "partner"  # type: ignore[union-attr]  # в партнёрском чате это обычный текст
    assert mk(OWNER_CHAT, "owner").role == "owner"  # type: ignore[union-attr]  # в чате владельца это его обычная реплика
    assert mk(OWNER_CHAT) is None
    assert mk(12345) is None  # личный чат (положительный id)
    other = normalize_update(gupd(NEW_CHAT, 5, f"{BOT} привяжи к ИП Василёк"), cfg, "intake")
    assert other is None  # не владелец в неизвестном чате


def test_several_same_name_sellers_need_a_number_in_the_owner_chat(be: Any) -> None:
    owner_says_in_group(be, "привяжи этот чат к ИП Ромашка")
    listing = be.owner.to(OWNER_CHAT)[-1]
    assert "1. селлер «ИП Ромашка» в фулфилменте «ФФ Север»" in listing
    assert "2. селлер «ИП Ромашка» в фулфилменте «ФФ Юг»" in listing and f"чат «{NEW_TITLE}»" in listing
    pid = proposal_msg_id(be)
    owner_replies(be, "да", pid)
    owner_replies(be, "3", pid)
    assert be.store.binding(NEW_CHAT) is None  # «да» при двух не выбирает, номера 3 нет
    owner_replies(be, "2", pid)
    assert be.store.binding(NEW_CHAT)["seller_id"] == S2
    assert_intake_bot_said_nothing(be) and be.llm.calls == []


def test_the_chat_comes_from_the_proposal_not_from_the_reply_words(be: Any) -> None:
    owner_says_in_group(be, "привяжи к ИП Василёк", chat=-100501, title="Первый чат")
    owner_says_in_group(be, "привяжи к ИП Ромашка", chat=-100502, title="Второй чат")
    owner_replies(be, "да", proposal_msg_id(be, 1))  # ответ на первое предложение при открытом втором
    assert be.store.binding(-100501)["seller_id"] == C.seller_id and be.store.binding(-100502) is None
    owner_replies(be, "1", proposal_msg_id(be, 2))
    assert be.store.binding(-100502)["seller_id"] == SELLER


def test_confirmation_must_come_from_the_owner_in_the_owner_chat(be: Any) -> None:
    owner_says_in_group(be, "привяжи к ИП Василёк")
    # «да» без reply теперь засчитывается единственному открытому предложению (живой случай 03.10.2026,
    # test_plain_number_without_reply_confirms_the_only_open_proposal); здесь — только чужие пути.
    be.owner.updates.append(gupd(OWNER_CHAT, OWNER_ID, "да", reply_to=777))  # ответ на чужое
    step(be)
    be.intake.updates.append(gupd(NEW_CHAT, 5, "да", reply_to=int(proposal_msg_id(be))))  # клиент в группе
    be.intake.updates.append(gupd(NEW_CHAT, OWNER_ID, "да", reply_to=int(proposal_msg_id(be))))  # не в чате владельца
    step(be)
    assert be.store.binding(NEW_CHAT) is None and be.fd.ensures == []
    assert be.store.proposal(1)["status"] == "open"


@pytest.mark.parametrize("outcome", ["none", "error", "off", "declined", "stale", "unclear", "ensure_failed"])
def test_no_outcome_ever_sends_names_through_the_intake_bot(be: Any, outcome: str) -> None:
    if outcome == "none":
        owner_says_in_group(be, "привяжи к ИП Нету")
        assert "не нашёл" in be.owner.to(OWNER_CHAT)[-1] and f"чат «{NEW_TITLE}»" in be.owner.to(OWNER_CHAT)[-1]
    elif outcome == "error":
        def broken(name: str) -> list[Candidate]:
            raise DirectoryError("шлюз")

        be.fd.find = broken
        owner_says_in_group(be, "привяжи к ИП Василёк")
        assert "недоступен" in be.owner.to(OWNER_CHAT)[-1]
    elif outcome == "off":
        be.pipe.directory = None
        owner_says_in_group(be, "привяжи к ИП Василёк")
        assert "недоступна" in be.owner.to(OWNER_CHAT)[-1]
    elif outcome == "declined":
        owner_says_in_group(be, "привяжи к ИП Василёк")
        owner_replies(be, "нет", proposal_msg_id(be))
        assert "не привязываю" in be.owner.to(OWNER_CHAT)[-1] and be.store.binding(NEW_CHAT) is None
    elif outcome == "stale":
        owner_says_in_group(be, "привяжи к ИП Василёк")
        first = proposal_msg_id(be, 1)
        owner_says_in_group(be, "привяжи к ИП Ромашка")
        owner_replies(be, "да", first)
        assert "неактуально" in be.owner.to(OWNER_CHAT)[-1] and be.store.binding(NEW_CHAT) is None
    elif outcome == "unclear":
        owner_says_in_group(be, "привяжи к ИП Василёк")
        owner_replies(be, "может быть", proposal_msg_id(be))
        assert "Не понял" in be.owner.to(OWNER_CHAT)[-1]
    else:
        be.fd.fail_ensure = True
        owner_says_in_group(be, "привяжи к ИП Василёк")
        owner_replies(be, "да", proposal_msg_id(be))
        assert "Доступ к данным пока не подготовлен" in be.owner.to(OWNER_CHAT)[-1]
        assert be.store.binding(NEW_CHAT) is not None
    assert_intake_bot_said_nothing(be)
    assert not any(n in t for t in be.owner.to(NEW_CHAT) for n in ("Василёк", "Ромашка"))  # и бот владельца в чат не пишет
    assert be.owner.to(NEW_CHAT) == []
    assert all(c == OWNER_CHAT for c, _, _ in be.owner.sent)


def test_voice_command_in_a_served_client_chat_also_goes_to_the_owner_only(be: Any) -> None:
    be.pipe.transcriber.text = "привяжи к IP Василёк"
    be.intake.files["f1"] = b"audio"
    be.intake.updates.append(gupd(CLIENT_CHAT, OWNER_ID, "", voice="f1"))
    step(be)
    step(be)
    assert be.fd.finds == ["Василёк"] and be.llm.calls == []
    assert_intake_bot_said_nothing(be)
    assert "селлер «ИП Василёк»" in be.owner.to(OWNER_CHAT)[-1] and "ИП Тест" in be.owner.to(OWNER_CHAT)[-1]


def test_non_owner_voice_in_a_served_chat_is_an_ordinary_message(be: Any) -> None:
    from .test_pipeline_chat import script

    script(be)
    be.pipe.transcriber.text = "привяжи к IP Василёк"
    be.intake.files["f1"] = b"audio"
    be.intake.updates.append(gupd(CLIENT_CHAT, 5, "", voice="f1"))
    step(be)
    step(be)
    assert be.fd.finds == [] and be.store.binding(CLIENT_CHAT) is None


@pytest.mark.parametrize("raw, clean", [("ИП Ромашка", "Ромашка"), ("ip «Ромашка»", "Ромашка"),
                                         ("индивидуальный предприниматель Ромашка", "Ромашка"),
                                         ("  Ромашка. ", "Ромашка")])
def test_clean_name(raw: str, clean: str) -> None:
    assert clean_name(raw) == clean


def test_binding_survives_restart_and_serves_the_chat_again(be: Any, tmp_path: Path) -> None:
    owner_says_in_group(be, "привяжи к ИП Василёк")
    owner_replies(be, "да", proposal_msg_id(be))
    again = two_bot_env(tmp_path)  # тот же файл состояния, новый конфиг без этого чата
    assert again.cfg.telegram.chats[NEW_CHAT].role == "client"
    assert again.store.binding(NEW_CHAT)["seller_id"] == C.seller_id


def test_rebinding_replaces_the_binding_and_old_confirmations_are_stale(be: Any) -> None:
    owner_says_in_group(be, "привяжи к ИП Василёк")
    first = proposal_msg_id(be, 1)
    owner_replies(be, "да", first)
    owner_says_in_group(be, "перепривяжи к ИП Ромашка")
    assert "Сейчас чат привязан к «ИП Василёк»" in be.owner.to(OWNER_CHAT)[-1]
    owner_replies(be, "1", proposal_msg_id(be, 2))
    assert be.store.binding(NEW_CHAT)["seller_id"] == SELLER
    assert be.cfg.telegram.chats[NEW_CHAT].seller == "ИП Ромашка"
    owner_replies(be, "да", first)  # старое предложение
    assert be.store.binding(NEW_CHAT)["seller_id"] == SELLER
    assert_intake_bot_said_nothing(be)


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

    def ensure(level: str, seller: str) -> None:
        calls.append(seller)
        if state["fail"]:
            raise DirectoryError("шлюз недоступен")

    llm.role_ensurer = ensure
    tid = llm.store.add_ticket(kind="chat", source="t", chat_id=1, seller="s", stage="analysis",
                               data={"seller_id": SELLER})
    llm.ask("analyst", "x", mode="readonly", cwd=str(tmp_path), ticket_id=tid)
    assert db_args(cap.argvs[-1]) is None  # доступ не подготовлен: без базы, а не с общей ролью
    llm.ask("analyst", "x", mode="readonly", cwd=str(tmp_path), ticket_id=tid)
    assert calls == [SELLER]  # после неудачи пауза: сервер не дёргаем на каждый вызов
    state["fail"] = False
    llm.store.kv_set(f"role_fail:{ROLE}", {"n": 1, "next": 0})  # пауза истекла
    llm.ask("analyst", "x", mode="readonly", cwd=str(tmp_path), ticket_id=tid)
    llm.ask("analyst", "x", mode="readonly", cwd=str(tmp_path), ticket_id=tid)
    assert db_args(cap.argvs[-1]) is not None and calls == [SELLER] * 2  # успех запомнен, повторно не зовём


def test_failed_prepare_backs_off_alerts_the_owner_once_and_keeps_an_already_working_role(tmp_path: Path) -> None:
    import time

    llm = make_router(tmp_path)
    llm.exec = Capture()
    alerts: list[tuple[str, int, str]] = []
    llm.role_alert = lambda level, seller, n, why: alerts.append((seller, n, why))
    calls: list[str] = []

    def busy(level: str, seller: str) -> None:
        calls.append(seller)
        raise DirectoryError("busy: lock timeout, nothing was changed, retry later")

    llm.role_ensurer = busy
    for attempt in range(1, 5):
        assert llm._role_ready(ROLE, "seller", SELLER) is False  # ни разу не готовилась: базы нет
        state = llm.store.kv_get(f"role_fail:{ROLE}")
        assert state["n"] == attempt and state["next"] - time.time() >= llm.ROLE_RETRY_BASE_SEC * 2 ** (attempt - 1) - 5
        assert llm._role_ready(ROLE, "seller", SELLER) is False and len(calls) == attempt  # в паузе: без вызова
        llm.store.kv_set(f"role_fail:{ROLE}", {"n": attempt, "next": 0})
    assert [a[1] for a in alerts] == [3] and "lock timeout" in alerts[0][2]  # владельцу ровно один раз, на 3-й неудаче
    # роль уже работала: сбой повторной проверки доступ не отнимает
    llm.store.kv_set(f"role_ready:{ROLE}", time.time() - llm.ROLE_TTL_SEC - 10)
    llm.store.kv_set(f"role_fail:{ROLE}", {"n": 0, "next": 0})
    assert llm._role_ready(ROLE, "seller", SELLER) is True


def test_owner_is_told_about_repeated_prepare_failures(env: Any) -> None:
    env.store.set_binding(CLIENT_CHAT, {"seller_id": SELLER, "seller_name": "ИП Ромашка", "tenant_id": "t",
                                        "tenant_name": "ФФ"}, "1")
    env.pipe.on_role_failure("seller", SELLER, 3, "busy: lock timeout")
    env.flush()
    text = env.tg.to(OWNER_CHAT)[-1]
    assert "«ИП Ромашка»" in text and "3 раза" in text and "lock timeout" in text


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
