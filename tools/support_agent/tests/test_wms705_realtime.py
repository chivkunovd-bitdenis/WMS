"""End-to-end service contracts for visible, event-driven Telegram support."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from support_agent.agent_coordinator import AgentCoordinator
from support_agent.agent_tools import AgentTools
from support_agent.case_journal import CaseJournal
from support_agent.llm import LlmResult
from support_agent.native_bridge import NativeBridge
from support_agent.pipeline import InlinePool, Pipeline
from support_agent.runner import Agent
from support_agent.store import Store
from support_agent.telegram import TelegramError

from .conftest import CLIENT_CHAT, OWNER_CHAT, OWNER_ID, FakeTelegram


class TelegramSurface(FakeTelegram):
    """Telegram boundary that records current owner-card text as well as sends."""

    def __init__(self) -> None:
        super().__init__()
        self.edits: list[tuple[int, str, str]] = []
        self.message_text: dict[tuple[int, str], str] = {}

    def send_message(self, chat_id: int, text: str, reply_to: str | None = None) -> str:
        message_id = super().send_message(chat_id, text, reply_to)
        self.message_text[(chat_id, message_id)] = text
        return message_id

    def edit_message(self, chat_id: int, message_id: str, text: str) -> None:
        self.edits.append((chat_id, str(message_id), text))
        self.message_text[(chat_id, str(message_id))] = text


def telegram_update(
    update_id: int,
    message_id: int,
    chat_id: int,
    text: str,
    *,
    author_id: int = 5,
    reply_to: str | None = None,
    edited: bool = False,
    edit_date: int = 0,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "message_id": message_id,
        "chat": {"id": chat_id},
        "date": 1_791_489_600 + update_id,
        "from": {"id": author_id, "first_name": "Клиент" if chat_id != OWNER_CHAT else "Владелец"},
        "text": text,
    }
    if reply_to:
        message["reply_to_message"] = {"message_id": reply_to}
    if edited:
        message["edit_date"] = edit_date
        return {"update_id": update_id, "edited_message": message}
    return {"update_id": update_id, "message": message}


def coordinator_for(env: Any) -> AgentCoordinator:
    """Use the real topic dispatcher and tools; only the model boundary is replaced."""
    Path(env.cfg.repo).mkdir(parents=True, exist_ok=True)
    coordinator = AgentCoordinator(env.pipe, AgentTools(env.pipe))
    env.pipe.agent = coordinator
    return coordinator


def route_and_analyze_model(
    store: Any,
    *,
    block_text: str | None = None,
    started: threading.Event | None = None,
    release: threading.Event | None = None,
    tool_queued: threading.Event | None = None,
    finish_turn: threading.Event | None = None,
    question_ticket_id: int | None = None,
    question_text: str = "Подскажите, к какому сроку нужно решить этот вопрос?",
) -> tuple[Callable[..., LlmResult], list[tuple[str, str]]]:
    """Deterministic external model fixture for the real dispatcher and topic worker."""
    calls: list[tuple[str, str]] = []

    def model_turn(prompt: str, **kwargs: Any) -> LlmResult:
        session_key = str(kwargs.get("session_key") or "")
        calls.append((session_key, prompt))
        if session_key == "agent:dispatcher":
            payload = json.loads(prompt)
            routes = []
            for event in payload["events"]:
                if event["kind"] == "input":
                    source = store.row("SELECT role,reply_to FROM messages WHERE id=?",
                                       (event["source_id"],))
                    linked_topic = None
                    if source and source["role"] == "owner" and source["reply_to"]:
                        linked_topic = next((card["topic_id"] for card in card_rows(store)
                                             if str(card.get("message_id"))
                                             == str(source["reply_to"])), None)
                    routes.append({
                        "event_id": event["id"],
                        "topics": [{"topic_id": linked_topic or f"topic-{event['source_id']}",
                                    "subrequest": event.get("text", "")}],
                    })
                else:
                    routes.append({"event_id": event["id"], "topics": []})
            text = json.dumps({"routes": routes}, ensure_ascii=False)
            return LlmResult(text, "codex", "test-model", "dispatcher")

        payload = json.loads(prompt)
        source = payload.get("source_message") or {}
        source_text = str(source.get("text") or "")
        if block_text and block_text in source_text:
            assert started is not None and release is not None
            started.set()
            if not release.wait(timeout=3):
                raise TimeoutError("test did not release the held model turn")

        if question_ticket_id is not None and source.get("role") == "client":
            handler = kwargs.get("tool_handler")
            assert callable(handler)
            handler("queue_process_reply", {
                "ticket_id": question_ticket_id,
                "kind": "necessary_question",
                "text": question_text,
                "reply_to": str(source["msg_id"]),
            })
            if tool_queued is not None:
                tool_queued.set()
            if finish_turn is not None and not finish_turn.wait(timeout=3):
                raise TimeoutError("test did not finish the held model turn")
        result = {"summary": source_text[:300], "next_action": "Проверка завершена",
                  "result": "Проверены имеющиеся сведения; повторных данных не спрашивать."}
        return LlmResult(json.dumps(result, ensure_ascii=False), "codex", "test-model", "topic")

    return model_turn, calls


def wait_for(predicate: Callable[[], bool], service: Agent, timeout: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        service.loop_once(poll=False)
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def card_rows(store: Any) -> list[dict[str, Any]]:
    return [json.loads(row["value"]) for row in store.rows(
        "SELECT value FROM kv WHERE key LIKE 'case_card:%' ORDER BY key")]


def card_for(cards: list[dict[str, Any]], fragment: str) -> dict[str, Any] | None:
    for card in cards:
        content = "\n".join([str(card.get("title") or ""), str(card.get("summary") or ""),
                             *(str(event.get("text") or "") for event in card.get("events", []))])
        if fragment in content:
            return card
    return None


def shutdown(coordinator: AgentCoordinator | None) -> None:
    if coordinator is None:
        return
    coordinator.dispatcher.router.shutdown(wait=False, cancel_futures=True)
    coordinator.dispatcher.workers.shutdown(wait=False, cancel_futures=True)
    coordinator.jobs.shutdown(wait=False, cancel_futures=True)


def test_visible_poll_starts_analysis_and_confirms_b_while_a_is_still_running(env, monkeypatch):
    from support_agent.runner import Agent

    env.cfg.agent.visible_moderator = True
    env.cfg.agent.enabled = True
    env.cfg.limits.max_parallel = 2
    env.tg = TelegramSurface()
    env.pipe.tg = env.tg
    env.pipe.bots.intake = env.tg
    env.pipe.bots.owner = env.tg
    coordinator = coordinator_for(env)
    started, release = threading.Event(), threading.Event()
    model, _ = route_and_analyze_model(
        env.store, block_text="обращение A", started=started, release=release,
    )
    monkeypatch.setattr(env.llm, "agent_turn", model, raising=False)
    service = Agent(env.cfg, env.store, env.tg, env.pipe, env.clock)
    service.startup()
    try:
        env.tg.updates = [telegram_update(1, 101, CLIENT_CHAT, "обращение A: долгий разбор")]
        service.loop_once()
        assert wait_for(lambda: card_for(card_rows(env.store), "обращение A") is not None, service), (
            "после сохранения события нет немедленной карточки владельца для A"
        )
        first_card = card_for(card_rows(env.store), "обращение A")
        assert first_card and first_card.get("message_id") and first_card.get("delivery") == "sent"
        assert wait_for(started.is_set, service), (
            "после сохранённого входящего события visible_moderator не запустил модельный разбор"
        )

        env.tg.updates.append(telegram_update(2, 102, CLIENT_CHAT, "обращение B: отдельный вопрос"))
        service.loop_once()
        assert wait_for(lambda: card_for(card_rows(env.store), "обращение B") is not None, service), (
            "долгий разбор A заблокировал сохранение и карточное подтверждение B"
        )
        second_card = card_for(card_rows(env.store), "обращение B")
        assert second_card and second_card.get("message_id") and second_card.get("delivery") == "sent"
        assert not release.is_set(), "A должен оставаться в анализе, пока карточка B уже подтверждена"
    finally:
        release.set()
        shutdown(coordinator)


def test_owner_reply_to_keeps_case_identity_across_two_cards_replay_and_edit(env, monkeypatch):
    from support_agent.runner import Agent

    env.cfg.agent.visible_moderator = True
    env.tg = TelegramSurface()
    env.pipe.tg = env.tg
    env.pipe.bots.intake = env.tg
    env.pipe.bots.owner = env.tg
    journal = CaseJournal(env.store, env.cfg.state_path / "case-history")
    card_a = journal.update_card(
        env.tg, OWNER_CHAT, "case-A", CLIENT_CHAT, title="Обращение A",
        event="Запрос A принят", event_key="seed-A",
    )
    card_b = journal.update_card(
        env.tg, OWNER_CHAT, "case-B", CLIENT_CHAT, title="Обращение B",
        event="Запрос B принят", event_key="seed-B",
    )
    before_b = env.store.kv_get("case_card:case-B")
    before_a = env.store.kv_get("case_card:case-A")
    env.cfg.agent.enabled = True
    coordinator = coordinator_for(env)
    model, _ = route_and_analyze_model(env.store)
    monkeypatch.setattr(env.llm, "agent_turn", model, raising=False)
    service = Agent(env.cfg, env.store, env.tg, env.pipe, env.clock)
    service.startup()
    instruction = "Для обращения A проверь именно этот вариант"
    bridge = None
    try:
        env.tg.updates = [telegram_update(
            1, 501, OWNER_CHAT, instruction, author_id=OWNER_ID,
            reply_to=str(card_a["message_id"]),
        )]
        service.loop_once()
        bridge = NativeBridge(env.cfg)
        first = bridge.inbox()
        owner_event = next(row for row in first["messages"] if row["msg_id"] == "501")
        assert owner_event["case_topic_id"] == "case-A"

        env.tg.updates.append(telegram_update(
            2, 501, OWNER_CHAT, instruction, author_id=OWNER_ID,
            reply_to=str(card_a["message_id"]),
        ))
        service.loop_once()
        assert wait_for(lambda: len(env.store.kv_get("case_card:case-A", {}).get("events", []))
                        > len(before_a["events"]), service), (
            "ответ владельца не был обработан как событие карточки A"
        )
        env.tg.updates.append(telegram_update(
            3, 501, OWNER_CHAT, "Для обращения A уточни этот вариант", author_id=OWNER_ID,
            reply_to=str(card_a["message_id"]), edited=True, edit_date=env.clock.now + 1,
        ))
        service.loop_once()
        replayed = bridge.inbox()
        same = [row for row in replayed["messages"] if row["msg_id"] == "501"]
        assert len(same) == 1
        assert replayed["edits"][-1]["current"]["case_topic_id"] == "case-A"
        after_a = env.store.kv_get("case_card:case-A")
        after_b = env.store.kv_get("case_card:case-B")
        assert after_a["number"] == card_a["number"]
        assert after_a["message_id"] == card_a["message_id"]
        assert len(after_a["events"]) > len(before_a["events"]), (
            "ответ владельца не добавил событие в связанную карточку A"
        )
        assert len({event["key"] for event in after_a["events"]}) == len(after_a["events"])
        assert after_b == before_b
    finally:
        bridge.store.db.close() if "bridge" in locals() else None
        shutdown(coordinator)


def test_client_question_waits_for_analysis_and_is_sent_once_without_process_noise(env, monkeypatch):
    from support_agent.runner import Agent

    env.cfg.agent.visible_moderator = True
    env.cfg.agent.enabled = True
    env.cfg.agent.client_replies_enabled = True
    env.tg = TelegramSurface()
    env.pipe.tg = env.tg
    env.pipe.bots.intake = env.tg
    env.pipe.bots.owner = env.tg
    coordinator = coordinator_for(env)
    ticket_id = env.store.add_ticket(
        kind="chat", source="telegram", chat_id=CLIENT_CHAT, seller="ИП Тест",
        stage="analysis", now=env.clock.now,
    )
    started, release = threading.Event(), threading.Event()
    question = "Подскажите, к какому сроку нужен результат?"
    tool_queued, finish_turn = threading.Event(), threading.Event()
    model, _ = route_and_analyze_model(
        env.store, block_text="проверить поставку", started=started, release=release,
        tool_queued=tool_queued, finish_turn=finish_turn,
        question_ticket_id=ticket_id, question_text=question,
    )
    monkeypatch.setattr(env.llm, "agent_turn", model, raising=False)
    service = Agent(env.cfg, env.store, env.tg, env.pipe, env.clock)
    service.startup()
    try:
        env.tg.updates = [telegram_update(1, 601, CLIENT_CHAT, "проверить поставку № 123")]
        service.loop_once()
        assert wait_for(started.is_set, service), "клиентский запрос не дошёл до аналитического хода"
        assert env.tg.to(CLIENT_CHAT) == [], "клиенту ответили до завершения анализа"
        assert wait_for(lambda: card_for(card_rows(env.store), "проверить поставку") is not None, service), (
            "во время долгого анализа карточка владельца не показывает принятый запрос"
        )
        release.set()
        assert wait_for(tool_queued.is_set, service), "модельный ход не подготовил адресный вопрос"
        assert env.tg.to(CLIENT_CHAT) == [], "вопрос ушёл до завершения модельного хода"
        finish_turn.set()
        assert wait_for(lambda: env.tg.to(CLIENT_CHAT) == [question], service), (
            "после анализа не отправлен один адресный вопрос клиенту"
        )
        env.tg.updates.append(telegram_update(2, 601, CLIENT_CHAT, "проверить поставку № 123"))
        service.loop_once()
        assert env.tg.to(CLIENT_CHAT) == [question]
        owner_messages = env.tg.to(OWNER_CHAT)
        assert len(owner_messages) == 1 and owner_messages[0].startswith("Обращение №"), (
            "в основной чат владельца попали промежуточные сообщения вместо одной карточки"
        )
        assert all(not text.startswith(("Internal:", "worker_", "agent_topic"))
                   for _, text, _ in env.tg.sent)
    finally:
        release.set()
        shutdown(coordinator)


def test_restart_resumes_saved_event_same_card_and_unknown_send_is_not_retried(env, monkeypatch):
    from support_agent.runner import Agent

    env.cfg.agent.visible_moderator = True
    env.cfg.agent.enabled = True
    env.cfg.agent.client_replies_enabled = True
    env.tg = TelegramSurface()
    env.pipe.tg = env.tg
    env.pipe.bots.intake = env.tg
    env.pipe.bots.owner = env.tg
    coordinator = coordinator_for(env)
    model, calls = route_and_analyze_model(env.store)
    monkeypatch.setattr(env.llm, "agent_turn", model, raising=False)
    journal = CaseJournal(env.store, env.cfg.state_path / "case-history")
    source_id = env.store.add_message(
        source="telegram", chat_id=CLIENT_CHAT, msg_id="701", role="client",
        author_id="5", author_name="Клиент", ts=env.clock.now, kind="text",
        text="После перезапуска продолжить этот запрос", file_id=None, reply_to=None,
    )
    assert source_id is not None
    card = journal.update_card(
        env.tg, OWNER_CHAT, "restart-topic", CLIENT_CHAT, title="Запрос после перезапуска",
        event="Входящее событие сохранено", event_key=f"in:{source_id}:1",
    )
    env.store.execute(
        "UPDATE messages SET status='new' WHERE id=?", (source_id,),
    )
    # A claimed send with a lost Telegram response is reconciled on startup, never resent blind.
    env.store.set_binding(CLIENT_CHAT, {"tenant_id": "tenant-test", "tenant_name": "Тест"},
                          bound_by="owner")
    bridge = NativeBridge(env.cfg)
    bridge.store = env.store
    bridge.journal = journal
    bridge.store.kv_set("native_paused", False)
    env.tg.fail = [TelegramError("unknown", "simulated_timeout")]
    original_delivery = bridge._delivery
    bridge._delivery = lambda: type("Delivery", (), {
        "store": env.store, "bots": env.pipe.bots,
    })()
    first = bridge.send(CLIENT_CHAT, "Проверенный ответ", "restart-unknown",
                        topic_id="restart-topic")
    bridge._delivery = original_delivery
    assert first["status"] == "unknown"
    send_count_before_restart = len(env.tg.to(CLIENT_CHAT))
    message_id = card["message_id"]
    env.store.db.close()
    restarted_store = Store(env.cfg.db_path)
    restarted_pipe = Pipeline(
        env.cfg, restarted_store, env.pipe.bots, env.llm, env.trello, env.wms, env.tr,
        pool=InlinePool(), clock=env.clock,
    )
    restarted_coordinator = AgentCoordinator(restarted_pipe, AgentTools(restarted_pipe))
    restarted_pipe.agent = restarted_coordinator
    restarted = Agent(env.cfg, restarted_store, env.tg, restarted_pipe, env.clock)
    restarted.startup()
    restarted.loop_once(poll=False)
    saved = restarted_store.kv_get("case_card:restart-topic")
    unresolved = restarted_store.outbox_by_key("native-send:restart-unknown")
    assert saved["message_id"] == message_id
    assert saved["number"] == card["number"]
    assert unresolved["status"] == "unknown" and unresolved["attempts"] == 1
    assert len(env.tg.to(CLIENT_CHAT)) == send_count_before_restart
    assert any(event.get("key") == f"unconfirmed:{unresolved['id']}" for event in saved["events"])
    assert wait_for(lambda: (
        restarted_store.row("SELECT status FROM messages WHERE id=?", (source_id,))["status"] != "new"
        and bool(calls)
    ), restarted), (
        "перезапуск сохранил сообщение, но не восстановил событийную очередь и разбор"
    )
    shutdown(coordinator)
    shutdown(restarted_coordinator)
