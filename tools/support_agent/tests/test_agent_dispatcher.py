"""Durable central routing and independent topic execution."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from support_agent.agent_authorization import SemanticAuthorization
from support_agent.agent_coordinator import AgentCoordinator
from support_agent.agent_dispatcher import _priority
from support_agent.config import config_from_dict
from support_agent.llm import LlmResult
from support_agent.store import Store


def _agent(tmp_path: Path) -> tuple[AgentCoordinator, Store]:
    repo = tmp_path / "repo"
    repo.mkdir()
    cfg = config_from_dict({"repo": str(repo), "state_dir": str(tmp_path / "state"),
                            "telegram": {"owner_user_id": 42, "owner_chat_id": 4242},
                            "agent": {"enabled": True}})
    store = Store(cfg.db_path)

    class Tools:
        def specs(self, scope: str) -> list[dict[str, Any]]:
            return []

    class RouterLlm:
        def agent_turn(self, prompt: str, **kwargs: Any) -> LlmResult:
            assert kwargs["session_key"] == "agent:dispatcher"
            assert kwargs["include_project_tools"] is False
            events = json.loads(prompt)["events"]
            routes = [{"event_id": e["id"], "topics": [{"topic_id": f"topic-{e['source_id']}",
                                                            "priority": 1}]}
                      for e in events]
            return LlmResult(json.dumps({"routes": routes}), "codex", "sol", "session")

    pipe = SimpleNamespace(cfg=cfg, store=store, llm=RouterLlm(), clock=lambda: 100.0,
                           _owner_snapshot=lambda: [], _is_bind_reply=lambda *_: None)
    return AgentCoordinator(pipe, Tools()), store


def _message(store: Store, chat: int, msg_id: str, text: str) -> Any:
    mid = store.add_message(source="telegram", chat_id=chat, msg_id=msg_id,
                            role="client", author_id="7", author_name="Client", ts=100,
                            kind="text", text=text, file_id=None, reply_to=None)
    assert mid is not None
    return store.row("SELECT * FROM messages WHERE id=?", (mid,))


def test_slow_first_topic_does_not_block_second_or_followup(tmp_path: Path) -> None:
    agent, store = _agent(tmp_path)
    first = _message(store, -10, "a", "Первый вопрос")
    second = _message(store, -20, "b", "Второй вопрос")
    dispatcher = agent.dispatcher
    dispatcher.accept(first)
    dispatcher.accept(second)
    dispatcher._route_once()
    entered = threading.Event()
    release = threading.Event()
    second_done = threading.Event()

    def work(topic: dict[str, Any], event: dict[str, Any], source: Any) -> dict[str, Any]:
        if topic["chat_id"] == -10:
            entered.set()
            assert release.wait(2)
        else:
            second_done.set()
        return {"summary": str(source["text"]), "result": "done"}

    agent.run_topic_turn = work  # type: ignore[method-assign]
    dispatcher._submit_topic(f"topic-{first['id']}")
    assert entered.wait(1)
    dispatcher._submit_topic(f"topic-{second['id']}")
    assert second_done.wait(1)
    followup = _message(store, -10, "c", "Уточнение к первому")
    dispatcher.accept(followup)
    assert f"in:{followup['id']}:1" in store.kv_get("agent_dispatch_queue", [])
    release.set()


def test_edited_message_is_new_event_with_same_source_id(tmp_path: Path) -> None:
    agent, store = _agent(tmp_path)
    initial = _message(store, -10, "a", "Старая версия")
    agent.dispatcher.accept(initial)
    assert store.add_message(source="telegram", chat_id=-10, msg_id="a", role="client",
                             author_id="7", author_name="Client", ts=100, kind="text",
                             text="Исправленная версия", file_id=None, reply_to=None,
                             edited=True, edit_ts=101) == initial["id"]
    edited = store.row("SELECT * FROM messages WHERE id=?", (initial["id"],))
    agent.dispatcher.accept(edited)
    assert store.kv_get("agent_dispatch_queue", []) == [f"in:{initial['id']}:1",
                                                       f"in:{initial['id']}:2"]


def test_finished_worker_atomically_queues_moderator_event(tmp_path: Path) -> None:
    agent, store = _agent(tmp_path)
    source = _message(store, -10, "a", "Нужно проверить")
    dispatcher = agent.dispatcher
    dispatcher.accept(source)
    dispatcher._route_once()
    event_id = f"in:{source['id']}:1"
    dispatcher._finish_event(f"topic-{source['id']}", event_id,
                             {"summary": "Проверено", "result": "Готово"})
    saved = store.row("SELECT status FROM messages WHERE id=?", (source["id"],))
    assert saved is not None and saved["status"] == "handled"
    queue = store.kv_get("agent_dispatch_queue", [])
    assert len(queue) == 1 and queue[0].startswith("internal:")
    assert store.kv_get(f"agent_event:{queue[0]}")["kind"] == "worker_done"


def test_owner_cannot_inherit_client_topic_session(tmp_path: Path) -> None:
    agent, store = _agent(tmp_path)
    client = _message(store, -10, "a", "Вопрос")
    agent.dispatcher.accept(client)
    agent.dispatcher._route_once()
    owner_id = store.add_message(source="telegram", chat_id=4242, msg_id="owner",
                                 role="owner", author_id="42", author_name="Owner", ts=101,
                                 kind="text", text="Посмотри эту задачу", file_id=None,
                                 reply_to=None)
    assert owner_id is not None
    owner = store.row("SELECT * FROM messages WHERE id=?", (owner_id,))
    agent.dispatcher.accept(owner)

    def wrong_route(prompt: str, **kwargs: Any) -> LlmResult:
        event = json.loads(prompt)["events"][0]
        answer = {"routes": [{"event_id": event["id"],
                              "topics": [{"topic_id": f"topic-{client['id']}"}]}]}
        return LlmResult(json.dumps(answer), "codex", "sol", "session")

    agent.llm.agent_turn = wrong_route  # type: ignore[method-assign]
    try:
        agent.dispatcher._route_once()
    except ValueError as exc:
        assert "chat boundary" in str(exc)
    else:
        raise AssertionError("owner event inherited client session")
    assert f"in:{owner_id}:1" in store.kv_get("agent_dispatch_queue", [])


def test_background_message_can_be_acknowledged_without_topic(tmp_path: Path) -> None:
    agent, store = _agent(tmp_path)
    source = _message(store, -10, "hello", "Спасибо")
    agent.dispatcher.accept(source)

    def no_topic(prompt: str, **kwargs: Any) -> LlmResult:
        event = json.loads(prompt)["events"][0]
        return LlmResult(json.dumps({"routes": [{"event_id": event["id"], "topics": []}]}),
                         "codex", "sol", "session")

    agent.llm.agent_turn = no_topic  # type: ignore[method-assign]
    agent.dispatcher._route_once()
    saved = store.row("SELECT status FROM messages WHERE id=?", (source["id"],))
    assert saved is not None and saved["status"] == "handled"
    assert store.kv_get("agent_dispatch_queue", []) == []
    assert store.kv_get("agent_topic_index", []) == []


def test_existing_topic_before_first_new_subtopic_is_valid(tmp_path: Path) -> None:
    agent, store = _agent(tmp_path)
    initial = _message(store, -10, "initial", "Первая тема")
    agent.dispatcher.accept(initial)
    agent.dispatcher._route_once()
    existing_topic = f"topic-{initial['id']}"

    followup = _message(store, -10, "followup", "Продолжи и проверь отдельно")
    agent.dispatcher.accept(followup)

    def mixed_route(prompt: str, **kwargs: Any) -> LlmResult:
        event = json.loads(prompt)["events"][0]
        answer = {"routes": [{"event_id": event["id"], "topics": [
            {"topic_id": existing_topic, "subrequest": "Продолжить", "priority": 8},
            {"topic_id": f"topic-{followup['id']}-1", "subrequest": "Проверить отдельно",
             "priority": 8},
        ]}]}
        return LlmResult(json.dumps(answer), "codex", "sol", "session")

    agent.llm.agent_turn = mixed_route  # type: ignore[method-assign]
    agent.dispatcher._route_once()

    assert store.kv_get("agent_dispatch_queue", []) == []
    assert f"in:{followup['id']}:1:part1" in store.kv_get(
        f"agent_topic:{existing_topic}")["pending"]
    assert f"in:{followup['id']}:1:part2" in store.kv_get(
        f"agent_topic:topic-{followup['id']}-1")["pending"]


def test_split_message_emits_one_completion_after_all_parts(tmp_path: Path) -> None:
    agent, store = _agent(tmp_path)
    owner_id = store.add_message(
        source="telegram", chat_id=4242, msg_id="owner-split", role="owner",
        author_id="42", author_name="Owner", ts=100, kind="text",
        text="Проверь две связанные части", file_id=None, reply_to=None,
    )
    assert owner_id is not None
    owner = store.row("SELECT * FROM messages WHERE id=?", (owner_id,))
    assert owner is not None
    agent.dispatcher.accept(owner)

    def split_route(prompt: str, **kwargs: Any) -> LlmResult:
        event = json.loads(prompt)["events"][0]
        answer = {"routes": [{"event_id": event["id"], "topics": [
            {"topic_id": f"topic-{owner_id}-1", "subrequest": "Первая часть"},
            {"topic_id": f"topic-{owner_id}-2", "subrequest": "Вторая часть"},
        ]}]}
        return LlmResult(json.dumps(answer), "codex", "sol", "session")

    agent.llm.agent_turn = split_route  # type: ignore[method-assign]
    agent.dispatcher._route_once()
    root_event = f"in:{owner_id}:1"
    first_event = f"{root_event}:part1"
    second_event = f"{root_event}:part2"

    agent.dispatcher._finish_event(
        f"topic-{owner_id}-1", first_event,
        {"summary": "Первая проверена", "result": "Первая часть готова",
         "answer_queued": False},
    )
    assert store.kv_get("agent_dispatch_queue", []) == []

    agent.dispatcher._finish_event(
        f"topic-{owner_id}-2", second_event,
        {"summary": "Вторая проверена", "result": "Вторая часть готова",
         "answer_queued": False},
    )
    queue = store.kv_get("agent_dispatch_queue", [])
    assert len(queue) == 1
    completion = store.kv_get(f"agent_event:{queue[0]}")
    assert completion["kind"] == "worker_done"
    assert completion["payload"]["source_event"] == root_event
    assert completion["payload"]["split_complete"] is True
    assert "Первая часть готова" in completion["payload"]["text"]
    assert "Вторая часть готова" in completion["payload"]["text"]
    agent.dispatcher._finish_event(
        f"topic-{owner_id}-2", second_event,
        {"summary": "Вторая проверена", "result": "Вторая часть готова",
         "answer_queued": False},
    )
    assert store.kv_get("agent_dispatch_queue", []) == queue


def test_new_topic_id_must_belong_to_source_and_safe_suffix(tmp_path: Path) -> None:
    agent, store = _agent(tmp_path)
    source = _message(store, -10, "unsafe", "Создай тему")
    agent.dispatcher.accept(source)

    def unsafe_route(prompt: str, **kwargs: Any) -> LlmResult:
        event = json.loads(prompt)["events"][0]
        answer = {"routes": [{"event_id": event["id"],
                              "topics": [{"topic_id": "topic-999-1"}]}]}
        return LlmResult(json.dumps(answer), "codex", "sol", "session")

    agent.llm.agent_turn = unsafe_route  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="invalid new topic id"):
        agent.dispatcher._route_once()
    assert f"in:{source['id']}:1" in store.kv_get("agent_dispatch_queue", [])


def test_repeated_router_failure_is_backed_off(tmp_path: Path) -> None:
    agent, store = _agent(tmp_path)
    now = [100.0]
    agent.clock = lambda: now[0]  # type: ignore[method-assign]
    source = _message(store, -10, "retry", "Не потеряй меня")
    agent.dispatcher.accept(source)

    for expected_attempt in range(1, 4):
        agent.dispatcher._record_route_failure(RuntimeError("same invalid route"))
        retry = store.kv_get("agent_dispatch_retry")
        assert retry["attempts"] == expected_attempt
        assert retry["event_ids"] == [f"in:{source['id']}:1"]
        if expected_attempt < 3:
            now[0] = float(retry["next_at"])

    retry = store.kv_get("agent_dispatch_retry")
    assert float(retry["next_at"]) - now[0] >= 300
    assert agent.dispatcher._route_retry_ready() is False


def test_successful_route_clears_retry_state(tmp_path: Path) -> None:
    agent, store = _agent(tmp_path)
    source = _message(store, -10, "recover", "Обработай после сбоя")
    agent.dispatcher.accept(source)
    store.kv_set("agent_dispatch_retry", {
        "signature": "old", "attempts": 3, "next_at": 999,
        "event_ids": [f"in:{source['id']}:1"], "last_error": "old failure",
    })

    agent.dispatcher._route_once()

    assert store.kv_get("agent_dispatch_retry") is None
    assert store.kv_get("agent_dispatch_queue", []) == []


def test_model_priority_names_are_tolerated() -> None:
    assert _priority("normal") == 5
    assert _priority("high") == 8
    assert _priority("unexpected") == 5


def test_cancel_topic_stops_linked_project_job(tmp_path: Path) -> None:
    agent, store = _agent(tmp_path)
    client = _message(store, -10, "client", "Работа")
    agent.dispatcher.accept(client)
    agent.dispatcher._route_once()
    target = f"topic-{client['id']}"
    store.kv_set("agent_job_index", ["job-a"])
    store.kv_set("agent_job:job-a", {"id": "job-a", "topic_id": target, "status": "running"})
    owner_id = store.add_message(source="telegram", chat_id=4242, msg_id="stop",
                                 role="owner", author_id="42", author_name="Owner", ts=101,
                                 kind="text", text="Останови эту задачу", file_id=None,
                                 reply_to=None)
    assert owner_id is not None
    owner = store.row("SELECT * FROM messages WHERE id=?", (owner_id,))
    agent.dispatcher.accept(owner)

    class AllowVerifier(SemanticAuthorization):
        def check(self, event: Any, action: str, args: dict[str, Any]) -> dict[str, Any]:
            return {"authorized": True}

    agent.semantic_verifier = AllowVerifier(agent)

    def cancel_route(prompt: str, **kwargs: Any) -> LlmResult:
        event = json.loads(prompt)["events"][0]
        answer = {"routes": [{"event_id": event["id"], "topics": [],
                              "controls": [{"action": "cancel_topic", "target": target}]}]}
        return LlmResult(json.dumps(answer), "codex", "sol", "session")

    agent.llm.agent_turn = cancel_route  # type: ignore[method-assign]
    agent.dispatcher._route_once()
    assert store.kv_get(f"agent_topic:{target}")["cancel_requested"] is True
    assert store.kv_get("agent_job:job-a")["cancel_requested"] is True


def test_authorization_sees_only_prior_same_chat_and_reply_target(tmp_path: Path) -> None:
    agent, store = _agent(tmp_path)
    store.queue_message(key="shown", chat_id=4242, text="Описание v1: Обработано",
                        purpose="proposal")
    store.execute("UPDATE outbox SET status='sent',tg_message_id='proposal-7' WHERE key='shown'")
    _message(store, -10, "secret", "Другая клиентская переписка")
    source_id = store.add_message(source="telegram", chat_id=4242, msg_id="approval",
                                  role="owner", author_id="42", author_name="Owner",
                                  ts=time.time() + 10, kind="text", text="Да, утверждаю",
                                  file_id=None, reply_to="proposal-7")
    assert source_id is not None
    source = store.row("SELECT * FROM messages WHERE id=?", (source_id,))
    seen: dict[str, Any] = {}

    def checker(prompt: str, **kwargs: Any) -> LlmResult:
        seen.update(json.loads(prompt))
        return LlmResult('{"authorized":true,"source_quote":"утверждаю","reason":"reply"}',
                         "codex", "sol", "session")

    agent.llm.agent_turn = checker  # type: ignore[method-assign]
    decision = agent.semantic_verifier.check(source, "queue_reply", {"chat_id": -10})
    assert decision["authorized"] is True
    assert seen["actual_source"]["verified_owner_private"] is True
    assert seen["actual_source"]["reply_to"] == "proposal-7"
    assert any(x.get("msg_id") == "proposal-7" for x in seen["prior_same_chat"])
    assert "Другая клиентская переписка" not in json.dumps(seen, ensure_ascii=False)


def test_authorization_accepts_exact_ordered_sentences_from_voice_source(tmp_path: Path) -> None:
    agent, store = _agent(tmp_path)
    text = "Упакуй это всё в вордовский документ. Без лишних заголовков. И пришли мне на утверждение."
    mid = store.add_message(source="telegram", chat_id=4242, msg_id="152", role="owner",
                            author_id="42", author_name="Owner", ts=100, kind="text",
                            text=text, file_id=None, reply_to=None)
    source = store.row("SELECT * FROM messages WHERE id=?", (mid,))
    quote = "Упакуй это всё в вордовский документ. И пришли мне на утверждение."

    def audit(prompt: str, **kwargs: Any) -> LlmResult:
        return LlmResult(json.dumps({"authorized": True, "source_quote": quote,
                                     "reason": "владелец прямо поручил"}), "codex", "sol", None)

    agent.llm.agent_turn = audit  # type: ignore[method-assign]
    decision = agent.semantic_verifier.check(source, "project_job", {"request": "подготовить DOCX"})
    assert decision["authorized"] is True
    assert len(decision["source_quotes"]) == 2
    assert all(span in text for span in decision["source_quotes"])


def test_authorization_does_not_accept_paraphrase_or_reordered_quote() -> None:
    source = "Подготовь документ. Сначала покажи мне. Клиенту не отправляй."
    assert SemanticAuthorization._quote_spans(source, "Создай документ.") == []
    assert SemanticAuthorization._quote_spans(source, "Клиенту не отправляй. Подготовь документ.") == []
    assert SemanticAuthorization._quote_spans(source, "Подготовь документ. Отправь клиенту.") == []
    assert SemanticAuthorization._quote_spans(source, "") == []
