"""Два Telegram-бота: приёма (клиентские и партнёрский чаты) и владельца (сводки и команды)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from support_agent.__main__ import check_config
from support_agent.config import config_from_dict
from support_agent.pipeline import InlinePool, Pipeline
from support_agent.runner import Agent
from support_agent.store import Store
from support_agent.telegram import Bots, Inbound, flush_outbox, normalize_update

from .conftest import (
    CLIENT_CHAT,
    OWNER_CHAT,
    OWNER_ID,
    PARTNER_CHAT,
    Clock,
    FakeLlm,
    FakeTelegram,
    FakeTranscriber,
    FakeTrello,
    FakeWms,
    make_config,
)
from .test_pipeline_chat import ANALYSIS_BUG, script, script_owner


def two_bot_env(tmp_path: Path) -> SimpleNamespace:
    cfg = make_config(tmp_path)
    cfg.telegram.bot_token = ""
    cfg.telegram.intake_bot_token = "111111:INTAKE-BOT-TOKEN-VALUE"
    cfg.telegram.owner_bot_token = "222222:OWNER-BOT-TOKEN-VALUE"
    store = Store(cfg.db_path)
    intake, owner = FakeTelegram(), FakeTelegram()
    llm, clock = FakeLlm(), Clock()
    pipe = Pipeline(cfg, store, Bots(intake, owner, OWNER_CHAT), llm, FakeTrello(), FakeWms(),  # type: ignore[arg-type]
                    FakeTranscriber(), pool=InlinePool(), clock=clock)
    agent = Agent(cfg, store, Bots(intake, owner, OWNER_CHAT), pipe, clock=clock)
    return SimpleNamespace(cfg=cfg, store=store, intake=intake, owner=owner, llm=llm, clock=clock, pipe=pipe,
                           agent=agent)


def upd(uid: int, chat: int, user: int, text: str = "привет") -> dict[str, Any]:
    return {"update_id": uid, "message": {"message_id": uid, "chat": {"id": chat}, "date": 1,
            "from": {"id": user, "first_name": "Имя"}, "text": text}}


def test_config_fields_and_single_token_fallback(tmp_path: Path) -> None:
    cfg = two_bot_env(tmp_path).cfg
    assert cfg.telegram.intake_token != cfg.telegram.owner_token and not cfg.telegram.single_bot
    assert {"111111:INTAKE-BOT-TOKEN-VALUE", "222222:OWNER-BOT-TOKEN-VALUE"} <= set(cfg.secrets())
    legacy = config_from_dict({"telegram": {"bot_token": "123456:ONE-TOKEN-VALUE"}})
    assert legacy.telegram.intake_token == legacy.telegram.owner_token == "123456:ONE-TOKEN-VALUE"
    assert legacy.telegram.single_bot
    same = config_from_dict({"telegram": {"intake_bot_token": "123456:SAME-TOKEN", "owner_bot_token": "123456:SAME-TOKEN"}})
    assert same.telegram.single_bot


def test_routing_of_incoming_updates_by_bot(tmp_path: Path) -> None:
    cfg = two_bot_env(tmp_path).cfg
    # бот приёма: клиентский и партнёрский чаты; в чате владельца ничего не принимает
    assert normalize_update(upd(1, CLIENT_CHAT, 5), cfg, "intake").role == "client"  # type: ignore[union-attr]
    assert normalize_update(upd(2, PARTNER_CHAT, 5), cfg, "intake").role == "partner"  # type: ignore[union-attr]
    assert normalize_update(upd(3, OWNER_CHAT, OWNER_ID, "кати"), cfg, "intake") is None
    # владелец в клиентском чате через бота приёма — обычный участник, не команда
    as_participant = normalize_update(upd(4, CLIENT_CHAT, OWNER_ID, "кати"), cfg, "intake")
    assert as_participant is not None and as_participant.role == "client"
    # бот владельца: только чат владельца и только owner_user_id
    assert normalize_update(upd(5, OWNER_CHAT, OWNER_ID, "кати"), cfg, "owner").role == "owner"  # type: ignore[union-attr]
    assert normalize_update(upd(6, OWNER_CHAT, 777, "кати"), cfg, "owner") is None
    assert normalize_update(upd(7, CLIENT_CHAT, 5), cfg, "owner") is None
    assert normalize_update(upd(8, CLIENT_CHAT, OWNER_ID, "кати"), cfg, "owner") is None
    assert normalize_update(upd(9, PARTNER_CHAT, 5), cfg, "owner") is None


def test_owner_registers_task_group_once_and_registration_survives_restart(tmp_path: Path) -> None:
    e = two_bot_env(tmp_path)
    group = -1004441620578
    declaration = "@wms_korob_support_bot\nобщий чат для задач от владельцев системы"
    update = upd(504, group, OWNER_ID, declaration)
    update["message"]["chat"]["title"] = "ВМС — Короб"
    incoming = normalize_update(update, e.cfg, "intake")
    assert incoming is not None and incoming.role == "bind"
    assert e.pipe.ingest(incoming) is not None
    e.pipe.route_messages()
    assert e.cfg.telegram.chats[group].role == "partner"
    assert e.store.binding(group) is None and e.llm.calls == []
    assert e.pipe.ingest(incoming) is None
    flush_outbox(e.store, e.pipe.bots, e.cfg)
    assert len(e.intake.sent) == 1 and e.intake.sent[0][0] == group
    assert "зарегистрирован" in e.intake.sent[0][1] and e.owner.sent == []
    assert e.store.rows("SELECT * FROM outbox")[0]["purpose"] == "group_registration"
    # Чистая конфигурация с тем же SQLite: регистрируется без повторного подтверждения.
    restarted = two_bot_env(tmp_path)
    assert restarted.cfg.telegram.chats[group].role == "partner"
    again = normalize_update(upd(505, group, OWNER_ID, declaration), restarted.cfg, "intake")
    assert again is not None
    restarted.pipe.ingest(again)
    restarted.pipe.route_messages()
    flush_outbox(restarted.store, restarted.pipe.bots, restarted.cfg)
    assert restarted.intake.sent == [] and restarted.owner.sent == []
    task = normalize_update(upd(506, group, 11, "Trello: создай задачу по отчёту WMS"),
                            restarted.cfg, "intake")
    assert task is not None and task.role == "partner"
    restarted.llm.on("filter", "Сообщение из партнёрского чата",
                     {"is_task_request": True, "task": "отчёт WMS"})
    restarted.pipe.ingest(task)
    restarted.pipe.route_messages()
    ticket = restarted.store.rows("SELECT * FROM tickets")[0]
    assert ticket["kind"] == "partner_task" and ticket["stage"] == "task_draft"
    go = normalize_update(upd(507, group, OWNER_ID, "кати"), restarted.cfg, "intake")
    assert go is not None and go.role == "partner"
    restarted.pipe.ingest(go)
    restarted.pipe.route_messages()
    assert restarted.store.ticket(ticket["id"])["stage"] == "task_draft"
    restarted.llm.on("routine", "Владелец склада написал", {
        "scope": "wms", "reply": "Да, общий чат зарегистрирован.", "actions": [], "listed_ticket_ids": [],
    })
    question = normalize_update(upd(508, OWNER_CHAT, OWNER_ID, "Ты видишь, где я тебя тегнул?"),
                                restarted.cfg, "owner")
    assert question is not None
    restarted.pipe.ingest(question)
    restarted.pipe.route_messages()
    prompt = restarted.llm.calls[-1]["prompt"]
    assert '"owner_task_chats_current": [{' in prompt and '"name": "ВМС — Короб"' in prompt
    assert '"role": "partner"' in prompt and '"confirmation_status": "sent"' in prompt


def test_foreign_author_or_wrong_bot_cannot_register_task_group(tmp_path: Path) -> None:
    e = two_bot_env(tmp_path)
    group = -1004441620578
    text = "@wms_korob_support_bot общий чат для задач от владельцев системы"
    assert normalize_update(upd(1, group, 777, text), e.cfg, "intake") is None
    assert normalize_update(upd(2, group, OWNER_ID, text), e.cfg, "owner") is None
    # Даже уже нормализованное ложное bind-сообщение повторно проверяется кодом Pipeline.
    e.pipe.ingest(Inbound(source="telegram", chat_id=group, msg_id="3", role="bind",
                          author_id="777", author_name="чужой", ts=1, kind="text", text=text))
    e.pipe.route_messages()
    assert group not in e.cfg.telegram.chats
    assert e.store.kv_get("owner_task_chats", {}) == {}
    assert e.store.rows("SELECT * FROM outbox") == [] and e.llm.calls == []


def test_single_bot_mode_keeps_both_rules(env: Any) -> None:
    cfg = env.cfg
    assert cfg.telegram.single_bot
    assert normalize_update(upd(1, OWNER_CHAT, OWNER_ID), cfg, "intake").role == "owner"  # type: ignore[union-attr]
    assert normalize_update(upd(2, CLIENT_CHAT, 5), cfg, "intake").role == "client"  # type: ignore[union-attr]
    assert normalize_update(upd(3, OWNER_CHAT, 777), cfg, "intake") is None


def test_each_bot_has_own_offset_that_survives_restart_and_duplicates_are_ignored(tmp_path: Path) -> None:
    e = two_bot_env(tmp_path)
    script(e)
    e.intake.updates = [upd(10, CLIENT_CHAT, 5, "не работает передача")]
    e.owner.updates = [upd(50, OWNER_CHAT, OWNER_ID, "ничего")]
    e.llm.on("routine", "Владелец склада написал",
             {"scope": "wms", "reply": "Понял.", "actions": [], "listed_ticket_ids": []})
    e.agent.poll_telegram(1)
    assert e.store.kv_get("tg_offset:intake") == 11 and e.store.kv_get("tg_offset:owner") == 51
    e.agent.poll_telegram(1)  # те же обновления Telegram отдаёт снова: повторов нет
    e.store.kv_set("tg_offset:intake", 0)  # и даже потеря offset не создаёт дублей (уникальный ключ)
    e.agent.poll_telegram(1)
    assert len(e.store.rows("SELECT * FROM messages WHERE role='client'")) == 1
    assert len(e.store.rows("SELECT * FROM messages WHERE role='owner'")) == 1
    assert e.store.kv_get("tg_offset:owner") == 51
    # перезапуск: новый Agent на том же хранилище продолжает с сохранённых позиций
    e.owner.updates.append(upd(51, OWNER_CHAT, OWNER_ID, "ещё"))
    agent2 = Agent(e.cfg, e.store, Bots(e.intake, e.owner, OWNER_CHAT), e.pipe, clock=e.clock)
    agent2.poll_bot("owner", 1)
    assert e.store.kv_get("tg_offset:owner") == 52 and len(e.store.rows("SELECT * FROM messages WHERE role='owner'")) == 2


def drive_to_summary(e: Any) -> int:
    script(e)
    e.intake.updates = [upd(1, CLIENT_CHAT, 5, "не работает передача поставки")]
    e.agent.poll_telegram(1)
    e.pipe.tick()  # маршрутизация: обращение создано
    e.clock.advance(130)
    e.pipe.tick()
    e.clock.advance(1000)
    e.pipe.tick()
    e.clock.advance(100)
    e.pipe.tick()
    flush_outbox(e.store, Bots(e.intake, e.owner, OWNER_CHAT), e.cfg)
    return 1


def test_outgoing_routing_summaries_only_via_owner_bot_clients_only_via_intake_bot(tmp_path: Path) -> None:
    e = two_bot_env(tmp_path)
    drive_to_summary(e)
    assert [c for c, _, _ in e.owner.sent] and all(c == OWNER_CHAT for c, _, _ in e.owner.sent)
    assert any(t.startswith("Обращение №1") for t in e.owner.to(OWNER_CHAT))  # сводка у бота владельца
    assert [c for c, _, _ in e.intake.sent] == [CLIENT_CHAT]  # вопрос о срочности у бота приёма
    assert "Подскажите" in e.intake.to(CLIENT_CHAT)[0]
    assert e.intake.to(OWNER_CHAT) == [] and e.owner.to(CLIENT_CHAT) == []
    # документы и предпросмотры владельцу тоже только через его бота
    e.store.queue_message(key="doc", chat_id=OWNER_CHAT, text="файл", file_path=str(tmp_path / "f.txt"), repeat_ok=True)
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    e.store.queue_message(key="cdoc", chat_id=CLIENT_CHAT, text="", file_path=str(tmp_path / "f.txt"))
    flush_outbox(e.store, Bots(e.intake, e.owner, OWNER_CHAT), e.cfg)
    assert [d[0] for d in e.owner.documents] == [OWNER_CHAT] and [d[0] for d in e.intake.documents] == [CLIENT_CHAT]


def test_owner_command_via_intake_bot_is_ignored_via_owner_bot_works(tmp_path: Path) -> None:
    e = two_bot_env(tmp_path)
    drive_to_summary(e)
    assert e.store.ticket(1)["stage"] == "await_owner"
    script_owner(e, {"intent": "go", "ticket_ids": [1], "all": False})
    e.llm.on("filter", "Новое сообщение из клиентского чата", {"relevant": False, "ticket_id": None})
    # «кати» от owner_user_id: в клиентском чате через бота приёма и в чате владельца через бота приёма
    e.intake.updates = [upd(2, CLIENT_CHAT, OWNER_ID, "кати 1"), upd(3, OWNER_CHAT, OWNER_ID, "кати 1")]
    e.agent.poll_bot("intake", 1)
    e.pipe.tick()
    assert e.store.ticket(1)["stage"] == "await_owner"
    assert not e.store.rows("SELECT * FROM messages WHERE role='owner'")
    # та же команда через бота владельца запускает хотфикс
    e.owner.updates = [upd(60, OWNER_CHAT, OWNER_ID, "кати 1")]
    e.agent.poll_bot("owner", 1)
    e.pipe.tick()
    assert e.store.ticket(1)["stage"] == "hotfix"


def test_voice_is_downloaded_by_the_bot_that_received_it(tmp_path: Path) -> None:
    e = two_bot_env(tmp_path)
    e.intake.files["fi"] = b"client-audio"
    e.owner.files["fo"] = b"owner-audio"
    got: list[bytes] = []

    class Rec(FakeTranscriber):
        def transcribe(self, audio: bytes) -> str:
            got.append(audio)
            return "текст"

    e.pipe.transcriber = Rec()  # type: ignore[assignment]
    e.llm.on("filter", "Новое сообщение из клиентского чата", {"relevant": False, "ticket_id": None})
    e.llm.on("routine", "Владелец склада написал",
             {"scope": "wms", "reply": "Понял.", "actions": [], "listed_ticket_ids": []})
    e.pipe.ingest(Inbound("telegram", CLIENT_CHAT, "1", "client", "5", "А", 1.0, "voice", "", file_id="fi"))
    e.pipe.ingest(Inbound("telegram", OWNER_CHAT, "2", "owner", str(OWNER_ID), "В", 1.0, "voice", "", file_id="fo"))
    e.pipe.tick()
    assert sorted(got) == [b"client-audio", b"owner-audio"]


def test_catchup_notice_waits_until_both_bots_are_drained(tmp_path: Path) -> None:
    e = two_bot_env(tmp_path)
    e.store.kv_set("heartbeat", e.clock.now - 3 * 3600)
    e.agent.startup()
    e.intake.updates = []
    e.owner.updates = [upd(5, OWNER_CHAT, OWNER_ID, "x")]
    e.llm.on("routine", "Владелец склада написал",
             {"scope": "wms", "reply": "Понял.", "actions": [], "listed_ticket_ids": []})
    e.agent.poll_bot("intake", 1)  # приёма уже пуст, у владельца ещё есть
    flush_outbox(e.store, Bots(e.intake, e.owner, OWNER_CHAT), e.cfg)
    assert e.owner.to(OWNER_CHAT) == []
    e.agent.poll_bot("owner", 1)  # забрал обновление: ещё не пуст
    e.owner.updates = []
    e.agent.poll_bot("owner", 1)
    flush_outbox(e.store, Bots(e.intake, e.owner, OWNER_CHAT), e.cfg)
    notes = [t for t in e.owner.to(OWNER_CHAT) if "снова работает" in t]
    assert len(notes) == 1 and e.intake.to(OWNER_CHAT) == []


def test_check_config_requires_both_tokens_and_accepts_legacy_single(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = {"repo": "/x", "telegram": {"owner_user_id": 1, "owner_chat_id": -1,
                                        "chats": {"-2": {"role": "client", "seller": "S"}}}}

    def run(telegram_extra: dict[str, Any]) -> tuple[int, str]:
        data = json.loads(json.dumps(base))
        data["telegram"].update(telegram_extra)
        path = tmp_path / "c.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        code = check_config(str(path))
        return code, capsys.readouterr().out

    code, out = run({})
    assert code == 1 and "intake_bot_token" in out and "owner_bot_token" in out
    code, out = run({"intake_bot_token": "1:AAAAAAAAAAAAAAAAAAAA"})
    assert code == 1 and "owner_bot_token" in out
    code, out = run({"intake_bot_token": "1:AAAAAAAAAAAAAAAAAAAA", "owner_bot_token": "2:BBBBBBBBBBBBBBBBBBBB"})
    assert code == 0 and "совпадают" not in out
    code, out = run({"bot_token": "3:CCCCCCCCCCCCCCCCCCCC"})  # прежний одиночный токен работает
    assert code == 0 and "работает один бот" in out
    assert "AAAAAAAA" not in out and "CCCCCCCC" not in out  # токены не печатаются


def test_bots_container_routes_by_chat_and_role() -> None:
    a, b = object(), object()
    bots = Bots(a, b, OWNER_CHAT)
    assert bots.for_chat(OWNER_CHAT) is b and bots.for_chat(CLIENT_CHAT) is a and bots.for_chat(PARTNER_CHAT) is a
    assert bots.for_role("owner") is b and bots.for_role("client") is a and bots.for_role("partner") is a
    assert list(bots.named()) == ["intake", "owner"] and list(Bots(a, a, OWNER_CHAT).named()) == ["intake"]


def test_analysis_flow_unchanged_in_single_bot_mode(env: Any) -> None:
    script(env, dict(ANALYSIS_BUG))
    env.say(CLIENT_CHAT, "не работает передача поставки")
    env.clock.advance(130)
    env.pipe.tick()
    env.flush()
    assert env.tg.to(CLIENT_CHAT) and env.cfg.telegram.single_bot
