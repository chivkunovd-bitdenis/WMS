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
        "owner_user_id": 42, "owner_chat_id": 900, "chats": {"100": {"role": "client"}}},
        "trello": {"board_id": "board"}})
    store = Store(":memory:")
    def say_owner(key, text, ticket_id=None, purpose="notice"):
        store.queue_message(key=key, chat_id=900, text=text, ticket_id=ticket_id,
                            purpose=purpose, repeat_ok=True)
    pipe = SimpleNamespace(store=store, cfg=cfg,
                           _seller_for_chat=lambda chat, role: "client",
                           say_owner=say_owner, trello=SimpleNamespace(),
                           llm=SimpleNamespace(role_ensurer=None))
    api = AgentTools(pipe)
    api.semantic_verifier = SimpleNamespace(check=lambda event, action, args:
                                            {"authorized": True, "source_quote": "test"})
    return api, store


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


def test_consequential_tool_denied_without_semantic_authorization(tools):
    api, store = tools
    owner = message(store, 900, "owner", 42, "look-only")
    api.semantic_verifier = SimpleNamespace(check=lambda event, action, args:
                                            {"authorized": False, "reason": "look only"})
    with pytest.raises(ToolDenied, match="needs_clarification"):
        api.dispatch("queue_reply", {"chat_id": 100, "text": "Отправить"}, ctx(owner, 900, 42))
    del api.semantic_verifier
    with pytest.raises(ToolDenied, match="verifier_unavailable"):
        api.dispatch("queue_reply", {"chat_id": 100, "text": "Отправить"}, ctx(owner, 900, 42))


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
    seen_owner = []
    def sync(args, event, owner):
        seen_owner.append(owner)
        return {"status": "linked", "url": "https://trello.test/1"}
    monkeypatch.setattr(api, "_tool_trello_sync", sync)
    result = api.dispatch("task_record", {**base, "ticket_id": task["ticket_id"],
                                          "confirm_author": True}, ctx(confirmation, 100, 5))
    assert result["author_confirmed"] is True
    assert result["document"]["number"] == 700
    assert seen_owner == [False]
    digest = api.dispatch("owner_digest", {"ticket_id": task["ticket_id"],
                                            "text": "Задача подтверждена"}, ctx(confirmation, 100, 5))
    assert digest["status"] == "covered_by_task_notice"
    assert api.dispatch("owner_digest", {"text": "Задача подтверждена"},
                        ctx(confirmation, 100, 5))["status"] == "covered_by_task_notice"
    owner_notices = store.rows("SELECT * FROM outbox WHERE chat_id=900")
    assert len(owner_notices) == 1 and owner_notices[0]["purpose"] == "task_notice"


def test_mockup_retry_reuses_task_after_failure_and_reports_published_version(tools):
    api, store = tools
    owner = message(store, 900, "owner", 42, "retry-mockup")
    tid = store.add_ticket(kind="agent_task", source="telegram", chat_id=100, seller="client",
                           stage="failed", data={"agent": {
                               "version": "v1", "is_frontend": True,
                               "author_confirmation": {"version": "v1"},
                               "document_version": "v1", "document_branch": "codex/wms700",
                               "mockup": {"version": "v1", "status": "failed"}}})
    store.kv_once(f"agent_mockup:{tid}:v1")
    result = api.dispatch("request_mockup", {"ticket_id": tid}, ctx(owner, 900, 42))
    assert result["queued"] is True and result["status"] == "queued"
    assert store.ticket(tid)["stage"] == "agent_discussion"
    agent = store.data(tid)["agent"]
    assert agent["mockup"]["recovery_note"]
    agent["mockup"] = {"version": "v1", "status": "published", "url": "https://example.test/v1"}
    store.patch_data(tid, agent=agent)
    result = api.dispatch("request_mockup", {"ticket_id": tid}, ctx(owner, 900, 42))
    assert result["queued"] is False and result["status"] == "published"
    assert result["url"] == "https://example.test/v1"


def test_client_digest_only_reaches_owner_and_deduplicates(tools):
    api, store = tools
    source = message(store, 100, "client", 5, "digest")
    args = {"text": "Обсуждают выгрузку; нужен ответ по периоду."}
    first = api.dispatch("owner_digest", args, ctx(source, 100, 5))
    second = api.dispatch("owner_digest", {"text": "Другими словами, нужен период"}, ctx(source, 100, 5))
    rows = store.rows("SELECT chat_id, text FROM outbox WHERE key=?", (first["key"],))
    assert first["key"] == second["key"] and len(rows) == 1
    assert rows[0]["chat_id"] == 900 and "сообщение digest" in rows[0]["text"]
    assert second["frozen_text"] == rows[0]["text"]
    newer = message(store, 100, "client", 5, "digest-new")
    third = api.dispatch("owner_digest", {"text": "Новое обсуждение"}, ctx(newer, 100, 5))
    assert third["key"] != first["key"]


def test_mockup_approval_binds_current_published_url_and_change_revokes_it(tools):
    api, store = tools
    owner = message(store, 900, "owner", 42, "approve")
    source = message(store, 900, "owner", 42, "task")
    task = api.dispatch("task_record", {"chat_id": 900, "source_message_ids": [source],
        "title": "Экран", "description": "Показать таблицу", "topic_key": "screen",
        "is_frontend": True}, ctx(source, 900, 42))
    tid, version = task["ticket_id"], task["version"]
    with pytest.raises(ToolDenied, match="published"):
        api.dispatch("approve_task", {"ticket_id": tid, "version": version,
                                      "kind": "mockup"}, ctx(owner, 900, 42))
    agent = store.data(tid)["agent"]
    agent["mockup"] = {"version": version, "status": "published", "url": "https://example.test/v1"}
    store.patch_data(tid, agent=agent)
    result = api.dispatch("approve_task", {"ticket_id": tid, "version": version,
                                           "kind": "mockup"}, ctx(owner, 900, 42))
    assert result["url"] == "https://example.test/v1"
    changed = api.dispatch("task_record", {"ticket_id": tid, "chat_id": 900,
        "source_message_ids": [source], "title": "Экран", "description": "Показать таблицу и итог",
        "is_frontend": True}, ctx(source, 900, 42))
    assert changed["version"] != version
    assert "mockup_approval" not in store.data(tid)["agent"]


def test_owner_may_send_exact_text_to_connected_chat_without_task(tools):
    api, store = tools
    owner = message(store, 900, "owner", 42, "send")
    result = api.dispatch("queue_reply", {"chat_id": 100, "text": "Ответьте, пожалуйста, завтра."},
                          ctx(owner, 900, 42))
    row = store.outbox_by_key(result["key"])
    assert row["chat_id"] == 100 and row["ticket_id"] is None
    assert row["purpose"] == "owner_authorized"
    retried = api.dispatch("queue_reply", {"chat_id": 100, "text": "Другая формулировка"},
                           ctx(owner, 900, 42))
    assert retried["key"] == result["key"] and retried["queued"] is False
    assert retried["frozen_text"] == "Ответьте, пожалуйста, завтра."
    second = api.dispatch("queue_reply", {"chat_id": 100, "text": "Дополнение", "slot": "second"},
                          ctx(owner, 900, 42))
    assert second["key"] != result["key"]
    next_owner = message(store, 900, "owner", 42, "send-new")
    next_message = api.dispatch("queue_reply", {"chat_id": 100, "text": "Исправленный текст"},
                                ctx(next_owner, 900, 42))
    assert next_message["key"] != result["key"]


def test_read_data_uses_actual_chat_binding_and_readonly_query(tools, monkeypatch):
    api, store = tools
    source = message(store, 100, "client", 5, "data")
    api.p.cfg.prod_db.enabled = True
    seller_id = "12345678-1234-1234-1234-123456789abc"
    store.set_binding(100, {"seller_id": seller_id, "seller_name": "Test",
                            "tenant_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                            "tenant_name": "Tenant", "level": "seller"}, "42")
    observed: dict[str, str] = {}
    def fake_query(settings, sql, on_send):
        observed.update(role=settings.db_role, sql=sql)
        on_send()
        return "count\n1"
    monkeypatch.setattr("support_agent.agent_tools.run_query", fake_query)
    result = api.dispatch("read_data", {"sql": "SELECT count(*) FROM orders"}, ctx(source, 100, 5))
    assert result["status"] == "ok" and observed["role"] == "wms_agent_s_" + seller_id.replace("-", "")
    with pytest.raises(ToolDenied, match="cross_chat"):
        api.dispatch("read_data", {"chat_id": 200, "sql": "SELECT 1"}, ctx(source, 100, 5))


def test_owner_reads_external_board_card_without_local_ticket(tools):
    api, store = tools
    owner = message(store, 900, "owner", 42, "card")
    client = message(store, 100, "client", 5, "card")
    api.p.trello.get_card = lambda card_id: {"id": card_id, "idBoard": "board",
        "name": "WMS-700", "desc": "Описание", "shortUrl": "https://trello.com/c/Abc12345",
        "idList": "ready", "closed": False}
    card = api.dispatch("read_trello_card", {"card_id_or_url":
        "https://trello.com/c/Abc12345/wms-700"}, ctx(owner, 900, 42))
    assert card["name"] == "WMS-700" and card["desc"] == "Описание"
    with pytest.raises(ToolDenied, match="tool_unavailable"):
        api.dispatch("read_trello_card", {"card_id_or_url": "Abc12345"}, ctx(client, 100, 5))
    api.p.trello.get_card = lambda card_id: {"id": card_id, "idBoard": "other"}
    with pytest.raises(ToolDenied, match="outside"):
        api.dispatch("read_trello_card", {"card_id_or_url": "Abc12345"}, ctx(owner, 900, 42))
