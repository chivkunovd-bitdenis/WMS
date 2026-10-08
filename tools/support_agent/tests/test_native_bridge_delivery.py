"""An active native reader must see edits and asynchronously prepared material."""
from support_agent.native_bridge import NativeBridge
from support_agent.telegram import Bots

from .conftest import CLIENT_CHAT, make_config


def add(bridge, *, kind="text", text="before", role="client", reply_to=None, edited=False):
    return bridge.store.add_message(source="telegram", chat_id=12, msg_id="7", role=role,
                                    author_id="3", author_name="Client", ts=1, kind=kind,
                                    text=text, file_id="file" if kind != "text" else None,
                                    reply_to=reply_to, edited=edited)


def test_native_reader_gets_current_version_of_an_edit(tmp_path):
    bridge = NativeBridge(make_config(tmp_path))
    ident = add(bridge)
    first = bridge.inbox()
    add(bridge, text="after", edited=True)
    result = bridge.watch(first["next_message_id"], first["next_edit_id"], seconds=0)
    assert result["messages"] == []
    assert result["edits"][0]["text"] == "before"
    assert result["edits"][0]["current"]["id"] == ident
    assert result["edits"][0]["current"]["text"] == "after"
    assert result["edits"][0]["current"]["revision"] == 2


def test_voice_and_image_completion_are_visible_after_message_cursor(tmp_path):
    import json

    from support_agent.redact import scrub

    bridge = NativeBridge(make_config(tmp_path))
    ident = add(bridge, kind="voice", text="")
    first = bridge.inbox()
    serialized = json.loads(scrub(bridge.cfg, json.dumps(first)))
    assert serialized["material_versions"] == first["material_versions"]
    assert bridge.store.complete_transcription(ident, 1, "actual transcript")
    bridge.store.kv_set(f"media:{ident}:1", {"path": "/original.ogg", "status": "ready"})
    ready = bridge.watch(first["next_message_id"], seconds=0,
                         known_materials=first["material_versions"])
    assert ready["messages"] == []
    assert ready["materials"][0]["text"] == "actual transcript"
    assert ready["materials"][0]["media"]["path"] == "/original.ogg"
    unchanged = bridge.watch(first["next_message_id"], seconds=0,
                             known_materials=ready["material_versions"])
    assert unchanged["materials"] == []


def test_owner_reply_to_card_carries_case_identity(tmp_path):
    bridge = NativeBridge(make_config(tmp_path))
    bridge.store.kv_set("case_card:existing", {"topic_id": "existing", "message_id": "50"})
    add(bridge, role="owner", reply_to="50")
    assert bridge.inbox()["messages"][0]["case_topic_id"] == "existing"


def test_confirmed_native_send_links_answer_to_same_case_card_once(tmp_path):
    from itertools import count
    from types import SimpleNamespace

    class CardsTelegram:
        def __init__(self):
            self.sent = []
            self.edits = []
            self.ids = count(1000)
            self.before_send = None

        def send_message(self, chat_id, text, reply_to=None):
            if self.before_send:
                self.before_send(chat_id, text)
            message_id = str(next(self.ids))
            self.sent.append((chat_id, text, reply_to, message_id))
            return message_id

        def edit_message(self, chat_id, message_id, text):
            self.edits.append((chat_id, message_id, text))

    cfg = make_config(tmp_path)
    cfg.agent.visible_moderator = True
    cfg.agent.client_replies_enabled = True
    cfg.agent.history_dir = str(tmp_path / "history")
    bridge = NativeBridge(cfg)
    bridge.store.set_binding(
        CLIENT_CHAT, {"tenant_id": "tenant-test", "tenant_name": "Тест"}, bound_by="owner"
    )
    source_id = bridge.store.add_message(
        source="telegram", chat_id=CLIENT_CHAT, msg_id="client-7", role="client",
        author_id="5", author_name="Анна", ts=100, kind="text", text="Проверить поставку",
        file_id=None, reply_to=None,
    )
    tg = CardsTelegram()
    topic_id = "native:confirmed-answer"
    card = bridge.journal.update_card(
        tg, cfg.telegram.owner_chat_id, topic_id, CLIENT_CHAT,
        title="Проверка поставки", statuses={"working": True},
        event="Получено обращение", event_key="incoming:client-7",
    )
    link_key = "reply_case:native-send:confirmed-answer"
    links_seen_before_send = []
    tg.before_send = lambda chat_id, _text: (
        links_seen_before_send.append(bridge.store.kv_get(link_key, {}))
        if chat_id == CLIENT_CHAT else None
    )
    bots = Bots(tg, tg, cfg.telegram.owner_chat_id)
    bridge._delivery = lambda: SimpleNamespace(store=bridge.store, bots=bots)

    result = bridge.send(
        CLIENT_CHAT, "Подтверждённый ответ клиенту", key="confirmed-answer",
        reply_to="client-7", topic_id=topic_id,
    )
    replay = bridge.send(
        CLIENT_CHAT, "Подтверждённый ответ клиенту", key="confirmed-answer",
        reply_to="client-7", topic_id=topic_id,
    )

    saved_card = bridge.store.kv_get(f"case_card:{topic_id}")
    client_sends = [item for item in tg.sent if item[0] == CLIENT_CHAT]
    assert source_id is not None
    assert result["status"] == replay["status"] == "sent"
    assert len(client_sends) == 1
    assert len(links_seen_before_send) == 1
    assert links_seen_before_send[0]["topic_id"] == topic_id
    assert links_seen_before_send[0]["chat_id"] == CLIENT_CHAT
    assert saved_card["number"] == card["number"]
    assert saved_card["message_id"] == card["message_id"]
    assert len(tg.edits) == 1
    assert tg.edits[0][1] == card["message_id"]
    assert "Подтверждённый ответ клиенту" in tg.edits[0][2]
    assert sum(event["text"].count("Подтверждённый ответ клиенту")
               for event in saved_card["events"]) == 1


def test_visible_service_only_collects_and_does_not_drain_old_outbox(env):
    from support_agent.runner import Agent

    from .conftest import CLIENT_CHAT, OWNER_CHAT

    env.cfg.agent.visible_moderator = True
    env.cfg.agent.client_replies_enabled = True
    env.store.queue_message(key="old-owner", chat_id=OWNER_CHAT, text="old")
    env.store.queue_message(key="old-client", chat_id=CLIENT_CHAT, text="old")
    env.tg.updates = [{"update_id": 1, "message": {
        "message_id": 1, "chat": {"id": CLIENT_CHAT}, "date": 1,
        "from": {"id": 3, "first_name": "Client"}, "text": "new incoming"}}]
    service = Agent(env.cfg, env.store, env.tg, env.pipe, env.clock)
    service.startup()
    service.loop_once()
    assert env.store.row("SELECT text FROM messages")["text"] == "new incoming"
    assert env.store.rows("SELECT * FROM tickets") == []
    assert env.llm.calls == []
    assert env.tg.sent == []
    assert {row["status"] for row in env.store.rows("SELECT status FROM outbox")} == {"pending"}
