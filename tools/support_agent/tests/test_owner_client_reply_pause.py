"""WMS-676: a sourced owner pause survives retries without stopping analysis.

Only synthetic local SQLite and recording Telegram doubles are used here.
The existing kv record is the operator-to-worker contract; ticket_ids document
the affected work, while chat_id is the exact outgoing recipient boundary.
"""

from types import SimpleNamespace

import pytest

from support_agent.agent_tools import AgentTools, ToolDenied
from support_agent.config import config_from_dict
from support_agent.store import Store
from support_agent.telegram import flush_outbox

OWNER_ID = 689889703
CLIENT_CHAT = -4899527415
OTHER_CHAT = -111
OWNER_CHAT = 900


class RecordingTelegram:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, text, reply_to=None):
        self.sent.append((chat_id, text))
        return str(len(self.sent))

    def send_document(self, chat_id, path, text, reply_to=None):
        self.sent.append((chat_id, text))
        return str(len(self.sent))


@pytest.fixture
def paused(tmp_path):
    cfg = config_from_dict({"repo": str(tmp_path), "state_dir": str(tmp_path),
        "telegram": {"owner_user_id": OWNER_ID, "owner_chat_id": OWNER_CHAT,
                     "chats": {str(CLIENT_CHAT): {"role": "client"},
                               str(OTHER_CHAT): {"role": "client"}}}})
    path = tmp_path / "state.db"
    store = Store(path)
    def message(chat, author, text, msg_id):
        return store.add_message(source="telegram", chat_id=chat, msg_id=msg_id,
            role="owner" if author == OWNER_ID else "client", author_id=str(author),
            author_name="Synthetic", ts=100, kind="text", text=text,
            file_id=None, reply_to=None)
    source = message(CLIENT_CHAT, OWNER_ID, "Прекрати отвечать в этом чате", "470")
    generic_owner = message(OWNER_CHAT, OWNER_ID, "Продолжай анализ", "private-1")
    client = message(CLIENT_CHAT, 123, "Уточнение задачи", "471")
    ticket = store.add_ticket(kind="chat", source="telegram", chat_id=CLIENT_CHAT,
        seller="Synthetic", stage="analysis", author_id="123",
        data={"agent": {"version": "v1"}, "analysis": {"hypothesis": "saved"}})
    policy = {"paused": True, "chat_id": CLIENT_CHAT, "ticket_ids": [ticket],
              "owner_user_id": OWNER_ID, "source_message_id": source}
    store.kv_set(f"owner_client_reply_pause:{CLIENT_CHAT}", policy)
    pipe = SimpleNamespace(store=store, cfg=cfg)
    api = AgentTools(pipe)
    api.semantic_verifier = SimpleNamespace(check=lambda *args:
        {"authorized": True, "source_quote": "generic unrelated approval"})
    yield SimpleNamespace(store=store, cfg=cfg, api=api, path=path, ticket=ticket,
        source=source, generic_owner=generic_owner, client=client, policy=policy,
        tg=RecordingTelegram())
    store.db.close()


@pytest.mark.parametrize("kind", ["necessary_question", "description_confirmation"])
def test_paused_client_process_reply_is_denied_before_enqueue(paused, kind):
    e = paused
    try:
        e.api.dispatch("queue_process_reply", {"ticket_id": e.ticket,
            "kind": kind, "text": "Промежуточный ответ"},
            {"event_id": e.client, "chat_id": CLIENT_CHAT, "author_id": "123"})
    except ToolDenied:
        pass
    assert e.store.outbox_pending() == [], "Owner pause must prevent process enqueue"
    assert e.store.ticket(e.ticket)["stage"] == "analysis"
    assert e.store.data(e.ticket)["analysis"] == {"hypothesis": "saved"}


def test_pause_blocks_all_preexisting_client_outbox_including_files_and_final(paused):
    e = paused
    purposes = ["necessary_question", "description_confirmation", "notice",
                "mockup", "owner_authorized", ""]
    for index, purpose in enumerate(purposes):
        e.store.queue_message(key=f"preexisting:{index}", chat_id=CLIENT_CHAT,
            text=purpose or "legacy", ticket_id=e.ticket if index else None,
            purpose=purpose, repeat_ok=True, file_path="synthetic.pdf" if index == 3 else None)
    assert flush_outbox(e.store, e.tg, e.cfg) == 0, "Dispatcher must gate queued legacy rows"
    assert e.tg.sent == []
    assert len(e.store.rows("SELECT * FROM outbox")) == len(purposes), "Do not erase history"
    assert e.store.data(e.ticket)["analysis"] == {"hypothesis": "saved"}


def test_pause_survives_restart_elapsed_time_and_repeated_flush(paused, monkeypatch):
    e = paused
    e.store.queue_message(key="retry", chat_id=CLIENT_CHAT, text="Retry",
                          ticket_id=e.ticket, purpose="notice", repeat_ok=True)
    reopened = Store(e.path)
    try:
        monkeypatch.setattr("time.time", lambda: 20000000000.0)
        flush_outbox(reopened, e.tg, e.cfg)
        flush_outbox(reopened, e.tg, e.cfg)
        assert e.tg.sent == [], "Restart, elapsed time and retries cannot unmute"
        assert reopened.kv_get(f"owner_client_reply_pause:{CLIENT_CHAT}") == e.policy
        assert reopened.ticket(e.ticket)["stage"] == "analysis"
        assert reopened.data(e.ticket)["analysis"] == {"hypothesis": "saved"}
    finally:
        reopened.db.close()


def test_pause_is_exact_chat_scoped_and_owner_hypotheses_remain_deliverable(paused):
    e = paused
    for chat in (CLIENT_CHAT, OTHER_CHAT, OWNER_CHAT):
        e.store.queue_message(key=f"scope:{chat}", chat_id=chat, text="Hypothesis",
                              purpose="necessary_question")
    assert flush_outbox(e.store, e.tg, e.cfg) == 2
    assert {chat for chat, _ in e.tg.sent} == {OTHER_CHAT, OWNER_CHAT}


def test_generic_owner_authorization_cannot_override_specific_reply_pause(paused):
    e = paused
    try:
        e.api.dispatch("queue_reply", {"ticket_id": e.ticket, "chat_id": CLIENT_CHAT,
            "version": "v1", "text": "Финальный ответ"},
            {"event_id": e.generic_owner, "chat_id": OWNER_CHAT, "author_id": str(OWNER_ID)})
    except ToolDenied:
        pass
    assert e.store.outbox_pending() == [], "Only a new explicit owner approval may permit a final reply"
    assert e.store.kv_get(f"owner_client_reply_pause:{CLIENT_CHAT}") == e.policy
