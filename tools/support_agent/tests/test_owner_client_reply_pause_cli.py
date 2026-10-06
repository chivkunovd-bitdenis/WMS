"""Operator policy actions use synthetic sources and preserve analysis state."""

from copy import deepcopy

import pytest

from support_agent import __main__ as cli

from .test_owner_client_reply_pause import CLIENT_CHAT, OTHER_CHAT, OWNER_CHAT, OWNER_ID
from .test_owner_client_reply_pause import paused as paused  # noqa: F401


def _source(e, text, *, author=OWNER_ID, chat=OWNER_CHAT):
    return e.store.add_message(source="telegram", chat_id=chat, msg_id=str(len(e.store.rows(
        "SELECT id FROM messages")) + 1), role="owner", author_id=str(author),
        author_name="Synthetic", ts=200, kind="text", text=text, file_id=None, reply_to=None)


def _run(e, monkeypatch, command, source, text_path=None, version="v1"):
    args = ["support_agent", command, "--chat-id", str(CLIENT_CHAT),
            "--source-message-id", str(source), "--ticket-id", str(e.ticket)]
    if text_path:
        args += ["--version", version, "--text-file", str(text_path)]
    monkeypatch.setattr(cli, "load_config", lambda _: e.cfg)
    monkeypatch.setattr("sys.argv", args)
    return cli.main()


@pytest.mark.parametrize("wrong", ["author", "chat"])
def test_pause_cli_rejects_wrong_source_without_changing_policy(paused, monkeypatch, wrong):
    e = paused
    source = _source(e, "Прекрати отвечать", author=123 if wrong == "author" else OWNER_ID,
                     chat=CLIENT_CHAT if wrong == "author" else OTHER_CHAT)
    before = deepcopy(e.store.kv_get(f"owner_client_reply_pause:{CLIENT_CHAT}"))
    assert _run(e, monkeypatch, "pause-client-replies", source) == 1
    assert e.store.kv_get(f"owner_client_reply_pause:{CLIENT_CHAT}") == before


def test_pause_cli_records_real_owner_source_and_preserves_existing_work(paused, monkeypatch):
    e = paused
    before = [tuple(row) for row in e.store.rows("SELECT * FROM tickets")]
    e.store.kv_set("agent_sessions", {"analysis": "keep"})
    assert _run(e, monkeypatch, "pause-client-replies", e.source) == 0
    assert e.store.kv_get(f"owner_client_reply_pause:{CLIENT_CHAT}") == e.policy
    assert [tuple(row) for row in e.store.rows("SELECT * FROM tickets")] == before
    assert e.store.kv_get("agent_sessions") == {"analysis": "keep"}


def test_old_pause_source_cannot_replace_a_newer_owner_instruction(paused, monkeypatch):
    e = paused
    newer = _source(e, "Прекрати ответы до моего нового разрешения", chat=CLIENT_CHAT)
    assert _run(e, monkeypatch, "pause-client-replies", newer) == 0
    before = deepcopy(e.store.client_reply_pause(CLIENT_CHAT))
    assert _run(e, monkeypatch, "pause-client-replies", e.source) == 1
    assert e.store.client_reply_pause(CLIENT_CHAT) == before


def test_specific_reply_cli_delivers_only_new_exact_reply_and_keeps_pause(paused, monkeypatch, tmp_path):
    from support_agent.telegram import flush_outbox

    e = paused
    e.store.queue_message(key="old-final", chat_id=CLIENT_CHAT, ticket_id=e.ticket,
                          text="Old final", purpose="owner_authorized")
    body = "Проверили конкретную задачу; результат подтверждён."
    text_path = tmp_path / "reply.txt"
    text_path.write_text(body, encoding="utf-8")
    source = _source(e, e.store.client_reply_approval_text(CLIENT_CHAT, e.ticket, "v1", body))
    assert _run(e, monkeypatch, "approve-client-reply", source, text_path) == 0
    assert _run(e, monkeypatch, "approve-client-reply", source, text_path) == 0
    assert flush_outbox(e.store, e.tg, e.cfg) == 1
    assert e.tg.sent == [(CLIENT_CHAT, body)]
    assert flush_outbox(e.store, e.tg, e.cfg) == 0
    assert e.store.client_reply_pause(CLIENT_CHAT)["paused"] is True
    assert e.store.outbox_by_key("old-final")["status"] == "pending"
    assert e.store.data(e.ticket)["analysis"] == {"hypothesis": "saved"}


@pytest.mark.parametrize("wrong", ["author", "source_chat", "body", "version", "old", "ticket"])
def test_specific_reply_cli_rejects_mismatched_authorization(paused, monkeypatch, tmp_path, wrong):
    e = paused
    body = "Точный новый ответ"
    text_path = tmp_path / "reply.txt"
    text_path.write_text(body, encoding="utf-8")
    source_text = e.store.client_reply_approval_text(
        CLIENT_CHAT, e.ticket + 1 if wrong == "ticket" else e.ticket, "v1",
        "Другой ответ" if wrong == "body" else body)
    source = _source(e, source_text, author=123 if wrong == "author" else OWNER_ID,
                     chat=OTHER_CHAT if wrong == "source_chat" else OWNER_CHAT)
    if wrong == "old":
        source = e.source
    before = deepcopy(e.store.client_reply_pause(CLIENT_CHAT))
    assert _run(e, monkeypatch, "approve-client-reply", source, text_path,
                version="stale" if wrong == "version" else "v1") == 1
    assert e.store.client_reply_pause(CLIENT_CHAT) == before
    assert e.store.outbox_pending() == []


@pytest.mark.parametrize("change", ["version", "source", "repaused", "body"])
def test_specific_reply_is_revalidated_before_dispatch(paused, change):
    from support_agent.telegram import flush_outbox

    e = paused
    body = "Точный новый ответ"
    source = _source(e, e.store.client_reply_approval_text(CLIENT_CHAT, e.ticket, "v1", body))
    key = e.store.approve_client_reply(chat_id=CLIENT_CHAT, ticket_id=e.ticket, version="v1",
        text=body, owner_user_id=OWNER_ID, owner_chat_id=OWNER_CHAT, source_message_id=source)
    if change == "version":
        e.store.patch_data(e.ticket, agent={"version": "v2"})
    elif change == "source":
        e.store.set_message(source, text="Разрешение отозвано", revision=2)
    elif change == "body":
        e.store.execute("UPDATE outbox SET text='Changed' WHERE key=?", (key,))
    else:
        new_pause = _source(e, "Пауза остаётся", chat=CLIENT_CHAT)
        e.store.pause_client_replies(chat_id=CLIENT_CHAT, ticket_ids=[e.ticket],
            owner_user_id=OWNER_ID, source_message_id=new_pause)
    assert flush_outbox(e.store, e.tg, e.cfg) == 0
    assert e.tg.sent == []
    assert e.store.outbox_by_key(key)["status"] == "pending"
