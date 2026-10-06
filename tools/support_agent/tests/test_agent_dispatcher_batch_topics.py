"""Regression contract for sharing a new topic inside one routing batch."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from support_agent.agent_coordinator import AgentCoordinator
from support_agent.config import config_from_dict
from support_agent.llm import LlmResult
from support_agent.store import Store


def _agent(tmp_path: Path) -> tuple[AgentCoordinator, Store]:
    repo = tmp_path / "repo"
    repo.mkdir()
    cfg = config_from_dict({
        "repo": str(repo),
        "state_dir": str(tmp_path / "state"),
        "telegram": {"owner_user_id": 42, "owner_chat_id": 4242},
        "agent": {"enabled": True},
    })
    store = Store(cfg.db_path)

    class Tools:
        def specs(self, scope: str) -> list[dict[str, Any]]:
            return []

    pipe = SimpleNamespace(
        cfg=cfg, store=store, llm=SimpleNamespace(), clock=lambda: 100.0,
        _owner_snapshot=lambda: [], _is_bind_reply=lambda *_: None,
    )
    return AgentCoordinator(pipe, Tools()), store


def _message(store: Store, chat: int, msg_id: str, text: str) -> Any:
    mid = store.add_message(
        source="telegram", chat_id=chat, msg_id=msg_id, role="client",
        author_id="7", author_name="Client", ts=100, kind="text", text=text,
        file_id=None, reply_to=None,
    )
    assert mid is not None
    return store.row("SELECT * FROM messages WHERE id=?", (mid,))


def test_same_chat_batch_can_share_topic_anchored_to_later_message(tmp_path: Path) -> None:
    agent, store = _agent(tmp_path)
    first = _message(store, -10, "first-control", "Не отправляй без согласования")
    second = _message(store, -10, "second-control", "Только после моего согласования")
    agent.dispatcher.accept(first)
    agent.dispatcher.accept(second)

    def combined_route(prompt: str, **kwargs: Any) -> LlmResult:
        events = json.loads(prompt)["events"]
        shared_topic = f"topic-{second['id']}"
        return LlmResult(json.dumps({"routes": [
            {"event_id": event["id"], "topics": [{"topic_id": shared_topic}]}
            for event in events
        ]}), "codex", "sol", "session")

    agent.llm.agent_turn = combined_route  # type: ignore[method-assign]
    agent.dispatcher._route_once()

    topic = store.kv_get(f"agent_topic:topic-{second['id']}")
    assert topic["chat_id"] == -10
    assert topic["pending"] == [f"in:{first['id']}:1", f"in:{second['id']}:1"]
    assert store.kv_get("agent_dispatch_queue", []) == []


def test_batch_cannot_anchor_new_topic_to_message_from_another_chat(tmp_path: Path) -> None:
    agent, store = _agent(tmp_path)
    first = _message(store, -10, "first-chat", "Первая задача")
    second = _message(store, -20, "second-chat", "Вторая задача")
    agent.dispatcher.accept(first)
    agent.dispatcher.accept(second)

    def crossed_route(prompt: str, **kwargs: Any) -> LlmResult:
        events = json.loads(prompt)["events"]
        return LlmResult(json.dumps({"routes": [
            {"event_id": events[0]["id"],
             "topics": [{"topic_id": f"topic-{second['id']}"}]},
            {"event_id": events[1]["id"],
             "topics": [{"topic_id": f"topic-{second['id']}"}]},
        ]}), "codex", "sol", "session")

    agent.llm.agent_turn = crossed_route  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="invalid new topic id"):
        agent.dispatcher._route_once()
    assert store.kv_get("agent_topic_index", []) == []
