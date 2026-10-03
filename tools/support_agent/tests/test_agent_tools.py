"""Source, version and retry boundaries of the model-facing tools."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from support_agent.agent_tools import AgentTools, ToolDenied
from support_agent.config import config_from_dict
from support_agent.store import Store


@pytest.fixture
def tools(tmp_path):
    cfg = config_from_dict({"repo": str(tmp_path), "telegram": {
        "owner_user_id": 42, "owner_chat_id": 900, "chats": {}}})
    store = Store(":memory:")
    pipe = SimpleNamespace(store=store, cfg=cfg,
                           _seller_for_chat=lambda chat, role: "client",
                           say_owner=lambda *args: None, trello=SimpleNamespace())
    return AgentTools(pipe), store


def message(store, chat, role, author, msg_id, ts=100.0):
    return store.add_message(source="telegram", chat_id=chat, msg_id=msg_id,
        role=role, author_id=str(author), author_name="Test", ts=ts, kind="text",
        text="request", file_id=None, reply_to=None)


def ctx(event_id, chat_id, author_id, owner=False):
    return {"event_id": event_id, "chat_id": chat_id, "author_id": str(author_id), "owner": owner}


def test_forged_owner_flag_cannot_unlock_privileged_tool(tools):
    api, store = tools
    source = message(store, 100, "client", 5, "1")
    with pytest.raises(ToolDenied, match="tool_unavailable"):
        api.dispatch("approve_task", {"ticket_id": 1, "version": "x"}, ctx(source, 100, 5, True))
    with pytest.raises(ToolDenied, match="cross_chat"):
        api.dispatch("read_context", {"chat_id": 200}, ctx(source, 100, 5))


def test_two_topics_one_message_and_version_revokes_approval(tools):
    api, store = tools
    source = message(store, 900, "owner", 42, "1")
    base = {"chat_id": 900, "source_message_ids": [source], "description": "Сделать выгрузку",
            "title": "Выгрузка", "is_frontend": False}
    one = api.dispatch("task_record", {**base, "topic_key": "export"}, ctx(source, 900, 42))
    two = api.dispatch("task_record", {**base, "topic_key": "fix"}, ctx(source, 900, 42))
    assert one["ticket_id"] != two["ticket_id"]
    again = api.dispatch("task_record", {**base, "topic_key": "export"}, ctx(source, 900, 42))
    assert again["ticket_id"] == one["ticket_id"]
    api.dispatch("approve_task", {"ticket_id": one["ticket_id"], "version": one["version"]},
                 ctx(source, 900, 42))
    revised = api.dispatch("task_record", {**base, "ticket_id": one["ticket_id"],
                                           "description": "Сделать выгрузку за месяц"},
                           ctx(source, 900, 42))
    assert revised["owner_approved"] is False
    with pytest.raises(ToolDenied, match="stale"):
        api.dispatch("queue_reply", {"ticket_id": one["ticket_id"], "chat_id": 900,
                                     "text": "Готово", "version": one["version"]}, ctx(source, 900, 42))


def test_author_confirmation_requires_sent_description_and_later_author_message(tools, monkeypatch):
    api, store = tools
    source = message(store, 100, "client", 5, "1")
    base = {"chat_id": 100, "source_message_ids": [source], "title": "Отчёт",
            "description": "Показать итог", "is_frontend": False, "topic_key": "report"}
    task = api.dispatch("task_record", base, ctx(source, 100, 5))
    with pytest.raises(ToolDenied, match="presented"):
        api.dispatch("task_record", {**base, "ticket_id": task["ticket_id"], "confirm_author": True},
                     ctx(source, 100, 5))
    api.dispatch("queue_process_reply", {"ticket_id": task["ticket_id"],
        "kind": "description_confirmation", "text": "Правильно понял?"}, ctx(source, 100, 5))
    key = f"agent_process:{task['ticket_id']}:description_confirmation:{task['version']}"
    row = store.outbox_by_key(key)
    store.finish_outbox(row["id"], "sent", "1000")
    confirmation = message(store, 100, "client", 5, "2", ts=20000000000.0)
    monkeypatch.setattr("support_agent.agent_tools.persist_task", lambda pipe, tid:
                        {"number": 700, "sha": "a" * 40, "branch": "test"})
    monkeypatch.setattr(api, "_tool_trello_sync", lambda args, event, owner:
                        {"status": "linked", "url": "https://trello.test/1"})
    result = api.dispatch("task_record", {**base, "ticket_id": task["ticket_id"],
                                          "confirm_author": True}, ctx(confirmation, 100, 5))
    assert result["author_confirmed"] is True
    assert result["document"]["number"] == 700
