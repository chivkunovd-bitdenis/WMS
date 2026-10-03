"""The local archive contains only observed messages, including edits and sends."""

from __future__ import annotations

import time

from support_agent.config import config_from_dict
from support_agent.store import Store
from support_agent.telegram import normalize_update


def _add(store: Store, number: int, *, chat: int = 10, text: str | None = None,
         kind: str = "text", file_id: str | None = None, ts: float | None = None) -> int:
    value = store.add_message(source="telegram", chat_id=chat, msg_id=str(number), role="client",
        author_id="5", author_name="Анна", ts=ts or time.time() + number, kind=kind,
        text=text if text is not None else f"сообщение {number}", file_id=file_id,
        reply_to=str(number - 1) if number > 1 else None)
    assert value is not None
    return value


def test_history_pages_past_recent_window_and_searches_edited_text(tmp_path):
    path = tmp_path / "state.sqlite3"
    store = Store(path)
    for number in range(1, 31):
        _add(store, number)
    store.queue_message(key="reply:1", chat_id=10, text="Ответ агента", reply_to="30")
    outgoing = store.outbox_by_key("reply:1")
    store.finish_outbox(outgoing["id"], "sent", "telegram-99")
    old_id = store.row("SELECT id FROM messages WHERE chat_id=10 AND msg_id='2'")["id"]
    edited = store.add_message(source="telegram", chat_id=10, msg_id="2", role="client",
        author_id="5", author_name="Анна", ts=time.time() + 2, kind="text",
        text="исправленное сообщение", file_id=None, reply_to="1", edited=True)
    assert edited == old_id
    assert store.add_message(source="telegram", chat_id=10, msg_id="2", role="client",
        author_id="5", author_name="Анна", ts=time.time() + 2, kind="text",
        text="исправленное сообщение", file_id=None, reply_to="1", edited=True) is None
    page = store.history_page(10, limit=10)
    all_items = list(page["items"])
    while page["next_before"]:
        page = store.history_page(10, before=page["next_before"], limit=10)
        all_items = page["items"] + all_items
    assert len(all_items) == 31
    assert any(item["id"] == f"in:{old_id}" and item["revision"] == 2
               and item["revisions"][0]["text"] == "сообщение 2" for item in all_items)
    assert any(item["direction"] == "out" and item["telegram_id"] == "telegram-99"
               and item["reply_to"] == "30" and item["status"] == "sent" for item in all_items)
    old_search = store.history_page(10, query="сообщение 2")
    assert any(item["id"] == f"in:{old_id}" for item in old_search["items"])
    restored = Store(path)
    assert len(restored.history_page(10, limit=100)["items"]) == 31
    assert restored.history_page(11)["items"] == []


def test_voice_transcript_bound_to_revision_and_old_worker_cannot_overwrite_edit():
    store = Store(":memory:")
    voice_id = _add(store, 1, text="", kind="voice", file_id="voice-file")
    assert store.complete_transcription(voice_id, 1, "(расшифровка) сначала")
    assert not store.complete_transcription(voice_id, 1, "повтор")
    store.add_message(source="telegram", chat_id=10, msg_id="1", role="client",
        author_id="5", author_name="Анна", ts=time.time(), kind="text",
        text="исправленный текст", file_id="voice-file", reply_to=None, edited=True)
    assert not store.complete_transcription(voice_id, 1, "старый воркер")
    item = store.history_page(10)["items"][0]
    assert item["file_id"] == "voice-file" and item["revision"] == 2
    assert item["revisions"][0]["text"] == "(расшифровка) сначала"


def test_duplicate_voice_edit_after_transcription_does_not_create_another_revision():
    store = Store(":memory:")
    message_id = _add(store, 1, text="", kind="voice", file_id="voice-1")
    edit = dict(source="telegram", chat_id=10, msg_id="1", role="client",
                author_id="5", author_name="Анна", ts=100.0, kind="voice",
                text="", file_id="voice-1", reply_to=None, caption="Новая подпись",
                edited=True, edit_ts=101.0)
    assert store.add_message(**edit) == message_id
    assert store.complete_transcription(message_id, 2, "Расшифровка новой версии")
    assert store.add_message(**edit) is None
    current = store.row("SELECT revision,text,status FROM messages WHERE id=?", (message_id,))
    assert current is not None and current["revision"] == 2
    assert current["text"] == "Расшифровка новой версии" and current["status"] == "new"
    assert store.row("SELECT count(*) AS n FROM message_revisions WHERE message_id=?",
                     (message_id,))["n"] == 1
    assert store.add_message(**{**edit, "caption": "Ещё одна подпись", "edit_ts": 102.0}) == message_id
    assert store.row("SELECT revision FROM messages WHERE id=?", (message_id,))["revision"] == 3
    assert store.add_message(**{**edit, "file_id": "voice-2", "edit_ts": 103.0}) == message_id
    assert store.row("SELECT revision,file_id FROM messages WHERE id=?", (message_id,))["revision"] == 4


def test_incremental_after_cursor_reads_oldest_new_events_first():
    store = Store(":memory:")
    for number in range(1, 6):
        _add(store, number, ts=1000 + number)
    page = store.history_page(10, limit=3)
    oldest = page["items"][0]
    cursor = store._history_cursor(oldest["ts"], "in", int(oldest["id"].split(":")[1]))
    later = store.history_page(10, after=cursor, limit=1)
    assert [item["telegram_id"] for item in later["items"]] == ["4"]
    assert later["next_after"] is not None


def test_telegram_edit_retains_message_id_and_voice_reference():
    cfg = config_from_dict({"telegram": {"owner_chat_id": 900, "owner_user_id": 42,
                            "chats": {"10": {"role": "client"}}}})
    update = {"edited_message": {"message_id": 7, "date": 100, "edit_date": 120,
        "chat": {"id": 10}, "from": {"id": 5, "first_name": "Анна"},
        "voice": {"file_id": "voice-ref"}, "caption": "Исправленное описание"}}
    item = normalize_update(update, cfg)
    assert item is not None and item.edited and item.edit_ts == 120
    assert item.msg_id == "7" and item.file_id == "voice-ref"
    assert item.text == "" and item.caption == "Исправленное описание"


def test_uncaptioned_attachment_is_archived_with_original_reference():
    cfg = config_from_dict({"telegram": {"owner_chat_id": 900, "owner_user_id": 42,
                            "chats": {"10": {"role": "client"}}}})
    update = {"message": {"message_id": 8, "date": 100, "chat": {"id": 10},
        "from": {"id": 5, "first_name": "Анна"},
        "photo": [{"file_id": "low-res"}, {"file_id": "high-res"}]}}
    item = normalize_update(update, cfg)
    assert item is not None and item.kind == "photo"
    assert item.file_id == "high-res" and item.text == "(photo без подписи)"
    store = Store(":memory:")
    store.add_message(source=item.source, chat_id=item.chat_id, msg_id=item.msg_id,
        role=item.role, author_id=item.author_id, author_name=item.author_name,
        ts=item.ts, kind=item.kind, text=item.text, file_id=item.file_id,
        reply_to=item.reply_to, caption=item.caption)
    archived = store.history_page(10)["items"][0]
    assert archived["kind"] == "photo" and archived["file_id"] == "high-res"
