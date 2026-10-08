"""Cross-review regressions for current-source questions and linked voice replies."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace
from typing import Any

from support_agent.agent_coordinator import AgentCoordinator
from support_agent.agent_tools import AgentTools
from support_agent.case_journal import CaseJournal
from support_agent.llm import LlmResult
from support_agent.native_bridge import NativeBridge
from support_agent.runner import Agent
from support_agent.telegram import flush_outbox

from .conftest import CLIENT_CHAT, OWNER_CHAT, FakeTelegram


class TelegramSurface(FakeTelegram):
    """Keep sent Telegram IDs available for testing an explicit client reply-to."""

    def __init__(self) -> None:
        super().__init__()
        self.message_text: dict[tuple[int, str], str] = {}

    def send_message(self, chat_id: int, text: str, reply_to: str | None = None) -> str:
        message_id = super().send_message(chat_id, text, reply_to)
        self.message_text[(chat_id, message_id)] = text
        return message_id

    def edit_message(self, chat_id: int, message_id: str, text: str) -> None:
        self.message_text[(chat_id, str(message_id))] = text


def _result() -> LlmResult:
    return LlmResult(json.dumps({
        "summary": "Запрос проверен по актуальному тексту",
        "checked": "История и доступные материалы проверены",
        "found": "Результат подтверждён",
        "unknown": "",
        "next_action": "Сообщить результат",
        "answer": "",
    }, ensure_ascii=False), "codex", "test-model", "topic")


def _client_source(env: Any, *, msg_id: str, text: str, edited: bool = False) -> int:
    return env.store.add_message(
        source="telegram", chat_id=CLIENT_CHAT, msg_id=msg_id, role="client",
        author_id="5", author_name="Клиент", ts=env.clock.now, kind="text", text=text,
        file_id=None, reply_to=None, edited=edited, edit_ts=env.clock.now + 1 if edited else None,
    )


def test_deferred_question_is_not_promoted_from_superseded_source_revision(env, monkeypatch):
    """An edit supersedes a staged client question before any send is eligible."""
    env.cfg.agent.visible_moderator = True
    env.cfg.agent.enabled = True
    env.cfg.agent.client_replies_enabled = True
    coordinator = AgentCoordinator(env.pipe, AgentTools(env.pipe))
    env.pipe.agent = coordinator
    ticket_id = env.store.add_ticket(
        kind="chat", source="telegram", chat_id=CLIENT_CHAT, seller="ИП Тест",
        stage="analysis", now=env.clock.now,
    )
    source_id = _client_source(env, msg_id="rev-1", text="Старый текст без срока")
    assert source_id is not None
    topic_id = f"topic-{source_id}"
    topic = {"id": topic_id, "chat_id": CLIENT_CHAT, "summary": "", "generation": 0,
             "pending": [], "task_ids": [], "affected_areas": [], "status": "working",
             "realtime_version": 1}
    env.store.kv_set(f"agent_topic:{topic_id}", topic)
    first_source = env.store.row("SELECT * FROM messages WHERE id=?", (source_id,))
    assert first_source is not None
    first_event = {"id": f"in:{source_id}:1", "kind": "input", "source_id": source_id,
                   "revision": 1, "topic_id": topic_id, "chat_id": CLIENT_CHAT,
                   "owner": False, "text": first_source["text"], "ts": env.clock.now,
                   "realtime_version": 1}
    staged, finish_old_turn = threading.Event(), threading.Event()
    stale_question = "Подскажите срок по старому тексту?"

    def model_turn(prompt: str, **kwargs: Any) -> LlmResult:
        if kwargs.get("session_key") == f"topic:{topic_id}":
            payload = json.loads(prompt)
            source = payload["source_message"]
            if int(source["revision"]) == 1:
                tool_handler = kwargs["tool_handler"]
                outcome = tool_handler("queue_process_reply", {
                    "ticket_id": ticket_id, "kind": "necessary_question",
                    "text": stale_question, "reply_to": "rev-1",
                })
                assert outcome.get("deferred") is True
                staged.set()
                if not finish_old_turn.wait(timeout=3):
                    raise TimeoutError("test did not release the revision 1 analysis")
            return _result()
        raise AssertionError(f"unexpected model session {kwargs.get('session_key')!r}")

    monkeypatch.setattr(env.llm, "agent_turn", model_turn, raising=False)
    errors: list[BaseException] = []

    def analyze_old_revision() -> None:
        try:
            coordinator.run_topic_turn(topic, first_event, first_source)
        except BaseException as exc:  # propagate worker assertion failures to the test thread
            errors.append(exc)

    worker = threading.Thread(target=analyze_old_revision, daemon=True)
    worker.start()
    try:
        assert staged.wait(timeout=1), "revision 1 did not create its deferred question stage"
        edited_id = _client_source(env, msg_id="rev-1", text="Обновлённый текст: срок уже указан",
                                   edited=True)
        assert edited_id == source_id
        finish_old_turn.set()
        worker.join(timeout=2)
        assert not worker.is_alive(), "revision 1 analysis did not finish"
        assert errors == []
        assert env.store.rows("SELECT id FROM outbox WHERE purpose='necessary_question'") == []

        current_source = env.store.row("SELECT * FROM messages WHERE id=?", (source_id,))
        assert current_source is not None and int(current_source["revision"]) == 2
        current_topic = env.store.kv_get(f"agent_topic:{topic_id}")
        current_event = {"id": f"in:{source_id}:2", "kind": "input", "source_id": source_id,
                         "revision": 2, "topic_id": topic_id, "chat_id": CLIENT_CHAT,
                         "owner": False, "text": current_source["text"], "ts": env.clock.now + 1,
                         "realtime_version": 1}
        coordinator.run_topic_turn(current_topic, current_event, current_source)
        flush_outbox(env.store, env.tg, env.cfg)

        assert env.tg.to(CLIENT_CHAT) == [], (
            "client received a question whose source text was superseded by revision 2"
        )
        assert env.store.rows("SELECT id FROM outbox WHERE purpose='necessary_question'") == [], (
            "revision 2 promoted a client question staged from superseded revision 1"
        )
    finally:
        finish_old_turn.set()
        worker.join(timeout=2)
        coordinator.dispatcher.router.shutdown(wait=False, cancel_futures=True)
        coordinator.dispatcher.workers.shutdown(wait=False, cancel_futures=True)
        coordinator.jobs.shutdown(wait=False, cancel_futures=True)


def test_voice_reply_to_linked_bot_answer_uses_existing_case_card_and_transcript(env):
    """Voice material replying to a linked bot answer stays in that answer's case."""
    env.cfg.agent.visible_moderator = True
    env.cfg.agent.enabled = True
    env.cfg.agent.client_replies_enabled = True
    env.cfg.agent.history_dir = str(env.cfg.state_path / "case-history")
    env.tg = TelegramSurface()
    env.pipe.tg = env.tg
    env.pipe.bots.intake = env.tg
    env.pipe.bots.owner = env.tg
    env.tg.files["voice-file"] = b"voice bytes"
    env.tr.text = "Клиент уточняет по той же поставке"
    env.store.set_binding(CLIENT_CHAT, {"tenant_id": "tenant-test", "tenant_name": "Тест"},
                          bound_by="owner")

    source_id = _client_source(env, msg_id="question-1", text="Проверьте поставку")
    assert source_id is not None
    env.store.set_message(source_id, status="handled")
    topic_id = "topic-existing-request"
    journal = CaseJournal(env.store, env.cfg.state_path / "case-history")
    original_card = journal.update_card(
        env.tg, OWNER_CHAT, topic_id, CLIENT_CHAT, title="Проверка поставки",
        event="Исходный запрос принят", event_key="seed:question-1",
    )
    bridge = NativeBridge(env.cfg)
    bridge.store = env.store
    bridge.journal = journal
    bridge.store.kv_set("native_paused", False)
    bridge._delivery = lambda: SimpleNamespace(store=env.store, bots=env.pipe.bots)
    sent_answer = bridge.send(
        CLIENT_CHAT, "Нашли причину; уточняем одну деталь", key="linked-answer",
        reply_to="question-1", topic_id=topic_id, message_kind="answer",
    )
    assert sent_answer["status"] == "sent"
    answer_message = env.store.outbox_by_key("native-send:linked-answer")
    assert answer_message is not None and answer_message["tg_message_id"]

    coordinator = AgentCoordinator(env.pipe, AgentTools(env.pipe))
    # Route/queue the accepted voice event, but leave semantic analysis outside this card-link test.
    coordinator.dispatcher._submit_topic = lambda _topic_id: None  # type: ignore[method-assign]
    env.pipe.agent = coordinator
    service = Agent(env.cfg, env.store, env.tg, env.pipe, env.clock)
    service.startup()
    env.tg.updates = [{"update_id": 10, "message": {
        "message_id": 702, "chat": {"id": CLIENT_CHAT},
        "date": env.clock.now + 2, "from": {"id": 5, "first_name": "Клиент"},
        "voice": {"file_id": "voice-file"},
        "reply_to_message": {"message_id": answer_message["tg_message_id"]},
    }}]
    try:
        service.loop_once()
        voice = env.store.row("SELECT * FROM messages WHERE msg_id='702'")
        assert voice is not None and voice["kind"] == "voice" and voice["status"] == "new"
        assert "Клиент уточняет по той же поставке" in voice["text"]

        service.loop_once(poll=False)
        existing = env.store.kv_get(f"case_card:{topic_id}")
        provisional = env.store.kv_get(f"case_card:topic-{voice['id']}")
        keys = {event.get("key") for event in existing.get("events", [])}
        assert existing["number"] == original_card["number"]
        assert existing["message_id"] == original_card["message_id"]
        assert provisional is None, (
            "voice reply created an unrelated provisional topic card instead of reusing its linked case"
        )
        assert f"in:{voice['id']}:1" in keys, (
            "voice input was not added to the existing case card"
        )
        assert f"transcript:{voice['id']}:1" in keys, "transcript was not added to the existing case card"
        assert len([row for row in env.store.rows("SELECT key FROM kv WHERE key LIKE 'case_card:%'")]) == 1
    finally:
        coordinator.dispatcher.router.shutdown(wait=False, cancel_futures=True)
        coordinator.dispatcher.workers.shutdown(wait=False, cancel_futures=True)
        coordinator.jobs.shutdown(wait=False, cancel_futures=True)
