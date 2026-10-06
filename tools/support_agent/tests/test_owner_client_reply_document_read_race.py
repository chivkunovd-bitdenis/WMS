"""Permanent WMS-676 F1.1 contract: document bytes precede the atomic claim.

Exercise the real TelegramClient/send_document/_call path with recording HTTP,
two real connections to shared in-memory SQLite, and synthetic local text only.
The frozen 24 tests and the production schema/authorization are not replaced.
"""

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from support_agent.store import Store
from support_agent.telegram import MAX_TEXT, TelegramClient, flush_outbox

from .test_owner_client_reply_pause import CLIENT_CHAT, OWNER_CHAT, OWNER_ID
from .test_owner_client_reply_pause import paused as paused_fixture
from .test_owner_client_reply_pause_cli import _source


@pytest.mark.parametrize("change", ["pause", "approval_revoked", "ticket_version"])
def test_committed_change_during_document_read_prevents_http_post(tmp_path, monkeypatch, change):
    # Reuse the frozen synthetic setup without creating any SQLite file on disk.
    connect = sqlite3.connect
    uri = f"file:wms676-document-read-{uuid4().hex}?mode=memory&cache=shared"
    connections = []

    def connect_in_memory(database, **kwargs):
        assert database == str(tmp_path / "state.db")
        connection = connect(uri, uri=True, **kwargs)
        connection.execute("PRAGMA temp_store=MEMORY")
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect_in_memory)
    fixture = paused_fixture.__wrapped__(tmp_path)
    e = next(fixture)
    other = Store(e.path)
    try:
        assert len(connections) == 2 and connections[0] is not connections[1]
        assert all(c.execute("PRAGMA database_list").fetchone()[2] == "" for c in connections)
        assert not e.path.exists()
        body = ("Проверенный длинный ответ без потери исходного текста. " * 200).strip()
        assert len(body) > MAX_TEXT
        if change == "pause":
            e.store.execute("DELETE FROM kv WHERE key=?", (f"owner_client_reply_pause:{CLIENT_CHAT}",))
            key = "long-reply-before-pause"
            e.store.queue_message(key=key, chat_id=CLIENT_CHAT, text=body, ticket_id=e.ticket)
        else:
            source = _source(e, e.store.client_reply_approval_text(CLIENT_CHAT, e.ticket, "v1", body))
            key = e.store.approve_client_reply(
                chat_id=CLIENT_CHAT, ticket_id=e.ticket, version="v1", text=body,
                owner_user_id=OWNER_ID, owner_chat_id=OWNER_CHAT, source_message_id=source,
            )
        initial = dict(e.store.outbox_by_key(key))
        allowed = e.store.outbox_delivery_allowed
        policy_args = {"owner_user_id": OWNER_ID, "owner_chat_id": OWNER_CHAT}
        assert initial["status"] == "pending" and initial["attempts"] == 0
        assert allowed(initial, **policy_args), "Initially authorized; not an invalid fixture"
        calls = []
        reads = []
        original_read = Path.read_bytes

        def read_with_competing_commit(path):
            assert path == tmp_path / "outbox-long" / f"message-{initial['id']}.txt"
            assert not calls, "The competing change occurs BEFORE the first HTTP POST"
            assert not e.store.db.in_transaction and not other.db.in_transaction
            row = e.store.outbox_by_key(key)
            reads.append((row["status"], row["attempts"]))
            assert len(reads) == 1, "Document preparation must not reread after claim"
            assert allowed(row, **policy_args)
            if change == "pause":
                other.pause_client_replies(chat_id=CLIENT_CHAT, ticket_ids=[e.ticket],
                                           owner_user_id=OWNER_ID, source_message_id=e.source)
            elif change == "approval_revoked":
                other.set_message(source, text="Разрешение отозвано", revision=2)
            else:
                other.patch_data(e.ticket, agent={"version": "v2"})
            assert not other.db.in_transaction, "Second connection has committed the prohibition"
            assert not allowed(e.store.outbox_by_key(key), **policy_args)
            content = original_read(path)
            assert content == body.encode("utf-8"), "Full original text survives document preparation"
            return content

        class HttpDouble:
            def post(self, url, **kwargs):
                assert len(reads) == 1
                assert not e.store.db.in_transaction and not other.db.in_transaction
                assert not allowed(e.store.outbox_by_key(key), **policy_args)
                assert url.endswith("/sendDocument")
                assert kwargs["data"]["chat_id"] == str(CLIENT_CHAT)
                assert kwargs["files"]["document"] == (
                    f"message-{initial['id']}.txt", body.encode("utf-8"))
                calls.append((url, kwargs))

                class Response:
                    status_code = 200

                    def json(self):
                        return {"ok": True, "result": {"message_id": 1}}

                return Response()

        monkeypatch.setattr(Path, "read_bytes", read_with_competing_commit)
        sent = flush_outbox(e.store, TelegramClient("synthetic", HttpDouble()), e.cfg)
        assert len(reads) == 1, "Real document read callback actually ran"
        row = e.store.outbox_by_key(key)
        for field in ("key", "chat_id", "ticket_id", "purpose", "text", "file_path", "reply_to"):
            assert row[field] == initial[field], "Original delivery intent must remain unchanged"
        assert e.store.client_reply_pause(CLIENT_CHAT)["paused"] is True
        assert e.store.client_reply_pause(OWNER_CHAT) is None
        assert e.store.data(e.ticket)["analysis"] == {"hypothesis": "saved"}
        assert not e.path.exists()
        observed = {"http_posts": len(calls), "flush": sent, "status": row["status"],
                    "attempts": row["attempts"], "read_states": reads}
        assert observed == {"http_posts": 0, "flush": 0, "status": "pending",
                            "attempts": 0, "read_states": [("pending", 0)]}, (
            f"{change}: committed prohibition during file IO must win before atomic claim; "
            f"actual={observed}")
    finally:
        other.db.close()
        fixture.close()
