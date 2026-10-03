# ruff: noqa: F811
"""WMS-641: привязка чата к ФУЛФИЛМЕНТУ (тенанту) и к селлеру, роль базы по уровню привязки."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from support_agent import prompts
from support_agent.prod_sql import ROLE_RE, SqlRefused, role_for_scope, role_for_tenant
from support_agent.seller_directory import (
    DirectoryError,
    SellerDirectory,
    TenantCandidate,
    clean_tenant_name,
)
from support_agent.store import Store
from support_agent.telegram import normalize_update, parse_bind_command

from . import test_seller_binding
from .conftest import CLIENT_CHAT, OWNER_CHAT, OWNER_ID
from .test_pipeline_chat import form_row, script
from .test_prod_sql import ROLE, SELLER, make_router
from .test_seller_binding import (
    BOT,
    NEW_CHAT,
    NEW_TITLE,
    A,
    Capture,
    assert_intake_bot_said_nothing,
    db_args,
    gupd,
    owner_replies,
    owner_says_in_group,
    proposal_msg_id,
    step,
)

be = test_seller_binding.be  # общая фикстура: два бота, подменённый шлюз
TENANT = "aaaaaaaa-1111-2222-3333-444444444444"
TENANT_ROLE = "wms_agent_t_aaaaaaaa111122223333444444444444"
TENANT2 = "bbbbbbbb-1111-2222-3333-444444444444"
LVOV = TenantCandidate(TENANT, "Империя ФФ", 3)
OTHER = TenantCandidate(TENANT2, "Империя Север", 1)


@pytest.fixture
def tb(be: Any) -> Any:
    be.fd.tenants = [LVOV, OTHER]
    return be


# ---------------------------------------------------------------- мягкий разбор команды
@pytest.mark.parametrize("text, expected", [
    (f"{BOT} Это фулфилмент Империя Львов", ("tenant", "Империя Львов")),
    (f"{BOT} это ФФ Империя Львов", ("tenant", "Империя Львов")),
    (f"{BOT} это фф «Империя Львов».", ("tenant", "Империя Львов")),
    (f"{BOT}, это фулфилмент: Империя", ("tenant", "Империя")),
    (f"Это фулфилмент Империя Львов {BOT}", ("tenant", "Империя Львов")),
    (f"{BOT} это чат фулфилмента Империя", ("tenant", "Империя")),
    (f"{BOT} привяжи к ФФ Империя", ("tenant", "Империя")),
    (f"{BOT} привяжи к фулфилменту Империя Львов", ("tenant", "Империя Львов")),
    (f"{BOT} Привяжи этот чат к фулфилменту «Империя»", ("tenant", "Империя")),
    (f"{BOT} перепривяжи к ФФ Империя", ("tenant", "Империя")),
    (f"{BOT} привяжи к ИП Василёк", ("seller", "Василёк")),
    (f"{BOT} привяжи к ip Василёк", ("seller", "Василёк")),
    (f"{BOT} привяжи к селлеру Василёк", ("seller", "Василёк")),
    (f"{BOT} это ИП Иванов", ("seller", "Иванов")),
    (f"{BOT} это селлер Иванов", ("seller", "Иванов")),
    (f"{BOT} это индивидуальный предприниматель Иванов", ("seller", "Иванов")),
    (f"{BOT} привяжи к Василёк", ("seller", "Василёк")),  # без слова уровня: селлер, как раньше
])
def test_bind_command_phrases(text: str, expected: tuple[str, str]) -> None:
    assert parse_bind_command(text) == expected


@pytest.mark.parametrize("text", [
    "Это фулфилмент Империя Львов",  # без упоминания бота игнор
    "привяжи к ИП Василёк", "это ФФ Империя", f"{BOT} привет", f"{BOT} это ипподром Х", f"{BOT}",
    f"{BOT} это фулфилмент", f"{BOT} это ФФ  ", f"{BOT} привяжи к", f"{BOT} расскажи про фулфилмент Империя",
])
def test_non_commands_are_ignored(text: str) -> None:
    assert parse_bind_command(text) is None


def test_voice_command_needs_no_mention() -> None:
    assert parse_bind_command("это фулфилмент Империя Львов", require_mention=False) == ("tenant", "Империя Львов")
    assert parse_bind_command("привяжи к IP Василёк", require_mention=False) == ("seller", "Василёк")


def test_normalize_accepts_the_command_only_from_the_owner_with_a_mention(be: Any) -> None:
    cfg = be.cfg
    mk = lambda user, text, chat=NEW_CHAT: normalize_update(gupd(chat, user, text, title="Чат"), cfg, "intake")  # noqa: E731
    ok = mk(OWNER_ID, f"{BOT} Это фулфилмент Империя Львов")
    assert ok is not None and ok.role == "bind" and ok.chat_title == "Чат"
    assert mk(OWNER_ID, "Это фулфилмент Империя Львов") is None  # без упоминания: неизвестный чат не обслуживается
    assert mk(5, f"{BOT} Это фулфилмент Империя Львов") is None  # не владелец
    assert normalize_update(gupd(NEW_CHAT, OWNER_ID, f"{BOT} это ФФ Империя"), cfg, "owner") is None  # не тем ботом
    served = mk(OWNER_ID, "Это фулфилмент Империя Львов", CLIENT_CHAT)
    assert served is not None and served.role == "client"  # в обслуживаемом чате без упоминания это обычный текст
    assert mk(5, f"{BOT} это ФФ Империя", CLIENT_CHAT).role == "client"  # type: ignore[union-attr]


# ---------------------------------------------------------------- привязка к фулфилменту
def test_owner_binds_a_chat_to_a_tenant_and_the_chat_becomes_served(tb: Any) -> None:
    script(tb)
    owner_says_in_group(tb, "Это фулфилмент Империя Львов")
    assert_intake_bot_said_nothing(tb)  # в чате тишина
    text = tb.owner.to(OWNER_CHAT)[-1]
    assert f"фулфилмент «Империя ФФ» (3 селлера), чат «{NEW_TITLE}» — привязать?" not in text  # несколько вариантов
    assert "1. фулфилмент «Империя ФФ» (3 селлера)" in text and "2. фулфилмент «Империя Север» (1 селлер)" in text
    assert tb.llm.calls == [] and tb.fd.tenant_finds == ["Империя Львов"]
    owner_replies(tb, "1", proposal_msg_id(tb))
    row = tb.store.binding(NEW_CHAT)
    assert row["level"] == "tenant" and row["tenant_id"] == TENANT and row["seller_id"] == ""
    assert tb.fd.tenant_ensures == [TENANT] and tb.fd.ensures == []
    assert tb.cfg.telegram.chats[NEW_CHAT].role == "client" and tb.cfg.telegram.chats[NEW_CHAT].seller == "Империя ФФ"
    done = tb.owner.to(OWNER_CHAT)[-1]
    assert f"Чат «{NEW_TITLE}» привязан к фулфилменту «Империя ФФ» (3 селлера" in done
    assert_intake_bot_said_nothing(tb)
    tb.intake.updates.append(gupd(NEW_CHAT, 5, "[новая] не передаётся поставка"))
    step(tb)
    data = tb.store.data(1)
    assert data["level"] == "tenant" and data["tenant_id"] == TENANT and data["seller_id"] == ""


def test_single_tenant_candidate_message_and_yes(tb: Any) -> None:
    tb.fd.tenants = [LVOV]
    owner_says_in_group(tb, "это ФФ Империя")
    text = tb.owner.to(OWNER_CHAT)[-1]
    assert f"фулфилмент «Империя ФФ» (3 селлера), чат «{NEW_TITLE}» — привязать?" in text
    owner_replies(tb, "да", proposal_msg_id(tb))
    assert tb.store.binding(NEW_CHAT)["level"] == "tenant"


def test_tenant_not_found_and_gateway_errors_go_only_to_the_owner(tb: Any) -> None:
    owner_says_in_group(tb, "это фулфилмент Нету")
    assert "фулфилмент «Нету» не нашёл" in tb.owner.to(OWNER_CHAT)[-1]

    def broken(name: str) -> list[TenantCandidate]:
        raise DirectoryError("шлюз")

    tb.fd.find_tenants = broken
    owner_says_in_group(tb, "это фулфилмент Империя")
    assert "недоступен" in tb.owner.to(OWNER_CHAT)[-1]
    assert_intake_bot_said_nothing(tb)
    assert tb.store.binding(NEW_CHAT) is None


def test_tenant_binding_can_be_replaced_by_seller_binding_and_back(tb: Any) -> None:
    owner_says_in_group(tb, "это ФФ Север")
    owner_replies(tb, "да", proposal_msg_id(tb, 1))
    assert tb.store.binding(NEW_CHAT)["level"] == "tenant"
    owner_says_in_group(tb, "привяжи к ИП Василёк")
    assert "Сейчас чат привязан к «Империя Север»" in tb.owner.to(OWNER_CHAT)[-1]
    owner_replies(tb, "да", proposal_msg_id(tb, 2))
    row = tb.store.binding(NEW_CHAT)
    assert row["level"] == "seller" and row["seller_id"] != ""
    owner_says_in_group(tb, "это ФФ Север")
    assert "Сейчас чат привязан к «ИП Василёк»" in tb.owner.to(OWNER_CHAT)[-1]
    assert_intake_bot_said_nothing(tb)


def test_ticket_keeps_its_level_after_rebinding(env: Any) -> None:
    script(env)
    env.store.set_binding(CLIENT_CHAT, {"level": "tenant", "tenant_id": TENANT, "tenant_name": "Империя ФФ"}, "1")
    env.say(CLIENT_CHAT, "[новая] не передаётся поставка", msg_id="20")
    assert env.store.data(1)["level"] == "tenant"
    env.store.set_binding(CLIENT_CHAT, {"level": "seller", "seller_id": SELLER, "seller_name": "ИП", "tenant_id": TENANT,
                                       "tenant_name": "Империя ФФ"}, "1")
    env.say(CLIENT_CHAT, "[новая] другая проблема", msg_id="21")
    levels = {t["id"]: env.store.data(t["id"])["level"] for t in env.store.tickets_in("collecting")}
    assert sorted(levels.values()) == ["seller", "tenant"] and env.store.data(1)["level"] == "tenant"


def test_binding_table_is_migrated_from_the_previous_schema(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.executescript("""CREATE TABLE chat_bindings (chat_id INTEGER PRIMARY KEY, seller_id TEXT NOT NULL,
        seller_name TEXT NOT NULL, tenant_id TEXT NOT NULL, tenant_name TEXT NOT NULL, bound_at REAL NOT NULL,
        bound_by TEXT NOT NULL);
        INSERT INTO chat_bindings VALUES (-5, 's', 'ИП', 't', 'ФФ', 1, '1');""")
    db.commit()
    db.close()
    store = Store(path)
    row = store.binding(-5)
    assert row["level"] == "seller" and row["chat_title"] == ""  # прежняя привязка осталась привязкой к селлеру


# ---------------------------------------------------------------- роль базы по уровню
def test_roles_by_level_and_the_shared_role_is_still_refused() -> None:
    assert role_for_tenant(TENANT) == TENANT_ROLE and role_for_scope("tenant", TENANT) == TENANT_ROLE
    assert role_for_scope("seller", SELLER) == ROLE
    assert ROLE_RE.match(TENANT_ROLE) and ROLE_RE.match(ROLE)
    for bad in ("wms_agent_ro", "wms_agent_x_" + "a" * 32, "wms_agent_t_" + "a" * 31, "postgres"):
        assert not ROLE_RE.match(bad)
    for bad in ("", "x; drop", TENANT + "x"):
        with pytest.raises(SqlRefused):
            role_for_tenant(bad)


@pytest.mark.parametrize("cli", ["claude", "codex"])
def test_analyst_gets_the_tenant_role_for_a_tenant_ticket(tmp_path: Path, cli: str) -> None:
    import time

    llm = make_router(tmp_path)
    if cli == "codex":
        llm.store.kv_set("cooldown:claude", time.time() + 999)
    cap = Capture()
    llm.exec = cap
    tenant_ticket = llm.store.add_ticket(kind="chat", source="t", chat_id=1, seller="s", stage="analysis",
                                         data={"level": "tenant", "tenant_id": TENANT, "seller_id": ""})
    seller_ticket = llm.store.add_ticket(kind="chat", source="t", chat_id=2, seller="s", stage="analysis",
                                         data={"level": "seller", "seller_id": SELLER, "tenant_id": TENANT})
    legacy_ticket = llm.store.add_ticket(kind="chat", source="t", chat_id=3, seller="s", stage="analysis",
                                         data={"seller_id": SELLER})
    broken = llm.store.add_ticket(kind="chat", source="t", chat_id=4, seller="s", stage="analysis",
                                  data={"level": "tenant", "tenant_id": "x; drop", "seller_id": SELLER})
    for tid in (tenant_ticket, seller_ticket, legacy_ticket, broken):
        llm.ask("analyst", "x", mode="readonly", cwd=str(tmp_path), ticket_id=tid)
    args = [db_args(a) for a in cap.argvs]
    roles = [a[a.index("--db-role") + 1] if a else None for a in args]
    assert roles == [TENANT_ROLE, ROLE, ROLE, None]  # у битого идентификатора инструмента нет, селлер не подставляется


def test_ensure_is_called_with_the_level_and_cached_per_role(tmp_path: Path) -> None:
    llm = make_router(tmp_path)
    llm.exec = Capture()
    calls: list[tuple[str, str]] = []
    llm.role_ensurer = lambda level, scope_id: calls.append((level, scope_id))
    tid = llm.store.add_ticket(kind="chat", source="t", chat_id=1, seller="s", stage="analysis",
                               data={"level": "tenant", "tenant_id": TENANT})
    for _ in range(3):
        llm.ask("analyst", "x", mode="readonly", cwd=str(tmp_path), ticket_id=tid)
    assert calls == [("tenant", TENANT)]


def test_owner_is_told_about_tenant_prepare_failures(be: Any) -> None:
    be.store.set_binding(CLIENT_CHAT, {"level": "tenant", "tenant_id": TENANT, "tenant_name": "Империя ФФ"}, "1")
    be.pipe.on_role_failure("tenant", TENANT, 3, "busy: lock timeout")
    step(be)
    text = be.owner.to(OWNER_CHAT)[-1]
    assert "«Империя ФФ»" in text and "3 раза" in text and "lock timeout" in text


# ---------------------------------------------------------------- формы
def test_form_binds_to_the_seller_for_a_seller_author_and_to_the_tenant_for_ff_staff(env: Any) -> None:
    script(env)
    seller_author = dict(form_row("r-1", "bug"), seller_id=SELLER, tenant_id=TENANT)
    ff_staff = dict(form_row("r-2", "bug"), seller_id=None, tenant_id=TENANT)
    forged = dict(form_row("r-3", "bug"), seller_id="x; drop", tenant_id="y", description=f"мой ФФ {TENANT2}")
    nothing = dict(form_row("r-4", "bug"), seller_id=None, tenant_id=None)
    env.wms.rows = [seller_author, ff_staff, forged, nothing]
    env.pipe.poll_forms()
    rows = {env.store.data(t)["form"]["id"]: env.store.data(t) for t in (1, 2, 3, 4)}
    assert rows["r-1"]["level"] == "seller" and rows["r-1"]["seller_id"] == SELLER
    assert rows["r-2"]["level"] == "tenant" and rows["r-2"]["tenant_id"] == TENANT and "seller_id" not in rows["r-2"]
    assert "level" not in rows["r-3"] and "level" not in rows["r-4"]  # нет идентификатора: нет базы
    assert env.llm.calls == []


def test_form_of_a_tenant_gets_the_tenant_prompt_and_the_one_without_scope_gets_no_data(env: Any) -> None:
    script(env)
    env.cfg.prod_db.enabled = True
    env.wms.rows = [dict(form_row("r-1", "bug"), seller_id=None, tenant_id=TENANT)]
    env.pipe.poll_forms()
    env.pipe.tick()
    context = [c for c in env.llm.calls if c["role"] == "analyst"][-1]["context"]
    assert "Чат с ФУЛФИЛМЕНТОМ" in context and "sql_query" in context and "не определил селлера" not in context


# ---------------------------------------------------------------- подсказки
def test_prompts_by_level() -> None:
    tenant = " ".join(prompts.analyst_rules(True, True, False, "tenant").split())
    seller = " ".join(prompts.analyst_rules(True, True, False, "seller").split())
    assert "ВСЕГО этого фулфилмента" in tenant and "sql_query" in tenant and "фильтруй по ним" not in tenant
    assert "ВСЕГО этого фулфилмента" not in seller and "роль видит только данные селлера ЭТОГО обращения" in seller
    assert "селлера" not in prompts.analyst_rules(False, True, False, "tenant")  # база выключена: без инструмента
    unbound = prompts.analyst_rules(True, False, False, "tenant")
    assert "чат не привязан, данных для ответа нет" in unbound and "@бот это фулфилмент" in unbound


# ---------------------------------------------------------------- клиент шлюза
def gateway(out: str, rc: int = 0) -> tuple[SellerDirectory, list[list[str]]]:
    from support_agent.prod_sql import ProdSqlSettings

    seen: list[list[str]] = []

    def runner(argv: list[str], stdin: str, timeout: int) -> tuple[int, str, str]:
        seen.append(argv)
        return rc, out, "refused" if rc else ""

    return SellerDirectory(ProdSqlSettings("h", "u", "/k"), runner), seen


def test_directory_finds_and_ensures_tenants_through_the_fixed_commands() -> None:
    out = f"tenant_id,tenant_name,sellers\n{TENANT},Империя ФФ,3\n{TENANT2},Империя Север,1\n"
    directory, seen = gateway(out)
    assert directory.find_tenants("ФФ Империя Львов") == [TenantCandidate(TENANT, "Империя ФФ", 3),
                                                        TenantCandidate(TENANT2, "Империя Север", 1)]
    assert seen[0][-1] == "find-tenant Империя Львов"  # «ФФ» отброшено, название как продиктовано
    directory, seen = gateway(f"ok role={TENANT_ROLE} tables=107 spec=x state=applied\n")
    directory.ensure_tenant(TENANT)
    directory.ensure_scope("tenant", TENANT)
    assert [c[-1] for c in seen] == [f"ensure-tenant {TENANT}"] * 2


@pytest.mark.parametrize("bad", ["", "a", "x; rm -rf /", "x`id`", "x$(id)", "x" * 81, "x|y", "x\\y"])
def test_directory_refuses_unsafe_tenant_names_before_ssh(bad: str) -> None:
    directory, seen = gateway("")
    with pytest.raises(DirectoryError):
        directory.find_tenants(bad)
    assert seen == []


def test_directory_rejects_malformed_tenant_answers() -> None:
    directory, _ = gateway("tenant_id,tenant_name,sellers\nnot-a-uuid,x,1\n")
    with pytest.raises(DirectoryError):
        directory.find_tenants("Империя")
    directory, _ = gateway(f"tenant_id,tenant_name,sellers\n{TENANT},x,many\n")
    with pytest.raises(DirectoryError):
        directory.find_tenants("Империя")
    for bad in ("x; id", TENANT_ROLE, "", "wms_agent_ro"):
        with pytest.raises(DirectoryError):
            gateway("")[0].ensure_tenant(bad)
    directory, _ = gateway("something else")
    with pytest.raises(DirectoryError):
        directory.ensure_tenant(TENANT)


def test_clean_tenant_name() -> None:
    assert clean_tenant_name("ФФ Империя Львов") == "Империя Львов"
    assert clean_tenant_name("«Империя Львов».") == "Империя Львов"
    assert clean_tenant_name("фулфилмент Империя") == "Империя"
    assert json.dumps(clean_tenant_name("  Империя   Львов ")) == json.dumps("Империя Львов")
    assert A.seller_name  # импорт образца кандидата-селлера используется в соседних тестах


def test_plain_number_without_reply_confirms_the_only_open_proposal(tb: Any) -> None:
    """03.10.2026 живой случай: владелец ответил «1» отдельным сообщением, не reply — привязка должна пройти."""
    script(tb)
    owner_says_in_group(tb, "Это фулфилмент Империя Львов")
    tb.owner.updates.append(gupd(OWNER_CHAT, OWNER_ID, "1"))
    step(tb)
    row = tb.store.binding(NEW_CHAT)
    assert row is not None and row["level"] == "tenant" and row["tenant_id"] == TENANT
    assert tb.llm.calls == []  # выбор разобрал код, модель не вызывалась
    assert_intake_bot_said_nothing(tb)


def test_plain_number_is_not_guessed_when_two_proposals_are_open(tb: Any) -> None:
    script(tb)
    owner_says_in_group(tb, "Это фулфилмент Империя Львов")
    owner_says_in_group(tb, "это ФФ Империя", chat=NEW_CHAT - 1, title="Другой чат")
    tb.owner.updates.append(gupd(OWNER_CHAT, OWNER_ID, "1"))
    step(tb)
    assert tb.store.binding(NEW_CHAT) is None and tb.store.binding(NEW_CHAT - 1) is None
