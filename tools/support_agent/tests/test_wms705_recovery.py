from __future__ import annotations

import pytest

from support_agent.case_journal import CaseJournal
from support_agent.native_bridge import NativeBridge
from support_agent.store import Store
from support_agent.telegram import Bots

from .conftest import CLIENT_CHAT, make_config
from .test_case_media_transport import Cards


def test_long_details_are_truncated_before_the_latest_card_event(tmp_path):
    store, tg = Store(tmp_path / 'state.db'), Cards()
    journal = CaseJournal(store, tmp_path / 'history')
    summary = '\n'.join(
        f'Поле {index}: ' + ('длинное значение ' * 25)
        for index in range(14)
    )
    card = journal.update_card(
        tg, 900, 'native:long-details', 10, title='Длинные подробности',
        summary=summary, statuses={'working': True},
        event='Последнее содержательное событие', event_key='latest-event',
    )

    body = journal.render(card)
    assert len(body.encode('utf-16-le')) // 2 <= 4096
    assert 'Последнее содержательное событие' in body

def test_new_unique_event_reopens_answered_case_as_working(tmp_path):
    store, tg = Store(tmp_path / 'state.db'), Cards()
    journal = CaseJournal(store, tmp_path / 'history')
    topic_id = 'native:answered-then-updated'
    journal.update_card(
        tg, 900, topic_id, 10, title='Поставка проверена',
        statuses={'answer_sent': True}, event='Ответ отправлен', event_key='answer:1',
    )

    updated = journal.update_card(
        tg, 900, topic_id, 10,
        event='Получено новое сообщение клиента', event_key='inbound:2',
    )

    assert updated['current_status'] == 'working'
    assert updated['statuses']['working'] is True
    assert updated['statuses']['answer_sent'] is not True
    assert 'Статус: 🟡 Взято в работу' in journal.render(updated)

def test_claimed_native_send_is_unknown_after_visible_restart_and_never_retried(tmp_path):
    from types import SimpleNamespace

    from support_agent.runner import Agent

    class ProcessStopped(BaseException):
        pass

    class Telegram:
        def __init__(self, stop_after_claim=False):
            self.stop_after_claim = stop_after_claim
            self.sent = []

        def send_message(self, chat_id, text, reply_to=None):
            self.sent.append((chat_id, text, reply_to))
            if self.stop_after_claim:
                raise ProcessStopped
            return "9001"

    cfg = make_config(tmp_path)
    cfg.agent.visible_moderator = True
    cfg.agent.client_replies_enabled = True
    first = NativeBridge(cfg)
    first.store.set_binding(
        CLIENT_CHAT, {"tenant_id": "tenant-test", "tenant_name": "Тест"}, bound_by="owner"
    )
    interrupted_tg = Telegram(stop_after_claim=True)
    first_bots = Bots(interrupted_tg, interrupted_tg, cfg.telegram.owner_chat_id)
    first._delivery = lambda: SimpleNamespace(store=first.store, bots=first_bots)

    with pytest.raises(ProcessStopped):
        first.send(CLIENT_CHAT, "Подтверждённый ответ", key="after-claim")

    stable_key = "native-send:after-claim"
    interrupted = first.store.outbox_by_key(stable_key)
    assert interrupted["status"] == "sending"
    assert interrupted["attempts"] == 1
    assert len(interrupted_tg.sent) == 1
    first.store.db.close()

    restarted = NativeBridge(cfg)
    Agent(cfg, restarted.store, None, None, lambda: 1.0).startup()
    settled = restarted.store.outbox_by_key(stable_key)
    assert settled["status"] == "unknown"
    assert settled["attempts"] == 1
    assert restarted.store.kv_get(f"reply_case:{stable_key}") is None

    retry_tg = Telegram()
    retry_bots = Bots(retry_tg, retry_tg, cfg.telegram.owner_chat_id)
    restarted._delivery = lambda: SimpleNamespace(store=restarted.store, bots=retry_bots)
    result = restarted.send(CLIENT_CHAT, "Подтверждённый ответ", key="after-claim")
    resolved = restarted.store.outbox_by_key(stable_key)

    assert result["status"] in {"unknown", "unresolved"}
    assert resolved["status"] in {"unknown", "unresolved"}
    assert resolved["attempts"] == 1
    assert [item for item in retry_tg.sent if item[0] == CLIENT_CHAT] == []

def test_unknown_native_send_outcome_is_recorded_on_linked_card_immediately(tmp_path):
    from types import SimpleNamespace

    from support_agent.telegram import TelegramError

    class CardsTelegram:
        def __init__(self):
            self.sent = []
            self.edits = []

        def send_message(self, chat_id, text, reply_to=None):
            self.sent.append((chat_id, text, reply_to))
            if chat_id == CLIENT_CHAT:
                raise TelegramError("unknown", "simulated_client_send_timeout")
            return "owner-card-81"

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
    tg = CardsTelegram()
    topic_id = "native:immediate-unknown-send"
    card = bridge.journal.update_card(
        tg, cfg.telegram.owner_chat_id, topic_id, CLIENT_CHAT,
        title="Проверка поставки", statuses={"working": True},
        event="Получено обращение", event_key="incoming:immediate-unknown",
    )
    bots = Bots(tg, tg, cfg.telegram.owner_chat_id)
    bridge._delivery = lambda: SimpleNamespace(store=bridge.store, bots=bots)

    result = bridge.send(
        CLIENT_CHAT, "Подтверждённый ответ", key="immediate-unknown",
        reply_to="client-origin", topic_id=topic_id,
    )

    stable_key = "native-send:immediate-unknown"
    outbox = bridge.store.outbox_by_key(stable_key)
    saved_card = bridge.store.kv_get(f"case_card:{topic_id}")
    unconfirmed = [event for event in saved_card["events"]
                   if "не подтвержд" in event["text"].lower()]
    client_sends = [item for item in tg.sent if item[0] == CLIENT_CHAT]
    assert result["status"] == outbox["status"] == "unknown"
    assert outbox["attempts"] == 1
    assert len(client_sends) == 1
    assert len(unconfirmed) == 1
    assert "повтор" in unconfirmed[0]["text"].lower()
    assert "провер" in unconfirmed[0]["text"].lower() or "чат" in unconfirmed[0]["text"].lower()
    assert saved_card["current_status"] == "working"
    assert saved_card["number"] == card["number"]
    assert saved_card["message_id"] == card["message_id"]
    assert tg.edits
    assert tg.edits[-1][1] == card["message_id"]
    assert "не подтвержд" in tg.edits[-1][2].lower()

@pytest.mark.parametrize("terminal_status", ["answer_sent", "analysis_done"])
def test_unknown_native_send_reopens_terminal_card_without_duplicate_event(
    tmp_path, terminal_status,
):
    from types import SimpleNamespace

    from support_agent.telegram import TelegramError, reconcile_unconfirmed_native_delivery

    class CardsTelegram:
        def __init__(self):
            self.sent = []
            self.edits = []

        def send_message(self, chat_id, text, reply_to=None):
            self.sent.append((chat_id, text, reply_to))
            if chat_id == CLIENT_CHAT:
                raise TelegramError("unknown", "simulated_terminal_card_send_timeout")
            return "owner-card-92"

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
    tg = CardsTelegram()
    topic_id = f"native:unknown-after-{terminal_status}"
    card = bridge.journal.update_card(
        tg, cfg.telegram.owner_chat_id, topic_id, CLIENT_CHAT,
        title="Разбор запроса", statuses={terminal_status: True},
        event="Предыдущий разбор завершён", event_key=f"incoming:{terminal_status}",
    )
    assert card["current_status"] == terminal_status
    bots = Bots(tg, tg, cfg.telegram.owner_chat_id)
    bridge._delivery = lambda: SimpleNamespace(store=bridge.store, bots=bots)

    result = bridge.send(
        CLIENT_CHAT, "Подтверждённый ответ", key=f"unknown-{terminal_status}",
        topic_id=topic_id,
    )
    stable_key = f"native-send:unknown-{terminal_status}"
    outbox = bridge.store.outbox_by_key(stable_key)
    saved_card = bridge.store.kv_get(f"case_card:{topic_id}")
    event_key = f"unconfirmed:{outbox['id']}"
    unconfirmed = [event for event in saved_card["events"] if event["key"] == event_key]
    assert result["status"] == outbox["status"] == "unknown"
    assert outbox["attempts"] == 1
    assert len([item for item in tg.sent if item[0] == CLIENT_CHAT]) == 1
    assert len(unconfirmed) == 1
    assert "не подтвержд" in unconfirmed[0]["text"].lower()
    assert "повтор" in unconfirmed[0]["text"].lower()
    assert "Ответ отправлен клиенту" not in unconfirmed[0]["text"]
    assert saved_card["current_status"] == "working"
    assert saved_card["statuses"]["working"] is True
    assert saved_card["statuses"].get(terminal_status) is not True
    assert saved_card["number"] == card["number"]
    assert saved_card["message_id"] == card["message_id"]

    reconcile_unconfirmed_native_delivery(
        bridge.journal, bridge.store, tg, cfg.telegram.owner_chat_id,
        bridge.store.outbox_by_key(stable_key),
    )

    replayed_card = bridge.store.kv_get(f"case_card:{topic_id}")
    replayed_events = [event for event in replayed_card["events"] if event["key"] == event_key]
    assert len(replayed_events) == 1
    assert replayed_card["current_status"] == "working"
    assert replayed_card["statuses"]["working"] is True
    assert replayed_card["statuses"].get(terminal_status) is not True
    assert len([item for item in tg.sent if item[0] == CLIENT_CHAT]) == 1

def test_sent_native_answer_is_reconciled_to_card_after_crash(tmp_path, monkeypatch):
    from itertools import count
    from types import SimpleNamespace

    from support_agent.case_journal import CaseJournal

    class ProcessStopped(BaseException):
        pass

    class CardsTelegram:
        def __init__(self):
            self.ids = count(1000)
            self.sent = []
            self.edits = []

        def send_message(self, chat_id, text, reply_to=None):
            message_id = str(next(self.ids))
            self.sent.append((chat_id, text, reply_to, message_id))
            return message_id

        def edit_message(self, chat_id, message_id, text):
            self.edits.append((chat_id, message_id, text))

    cfg = make_config(tmp_path)
    cfg.agent.visible_moderator = True
    cfg.agent.client_replies_enabled = True
    cfg.agent.history_dir = str(tmp_path / "history")
    first = NativeBridge(cfg)
    first.store.set_binding(
        CLIENT_CHAT, {"tenant_id": "tenant-test", "tenant_name": "Тест"}, bound_by="owner"
    )
    tg = CardsTelegram()
    topic_id = "native:sent-before-card-event"
    original_card = first.journal.update_card(
        tg, cfg.telegram.owner_chat_id, topic_id, CLIENT_CHAT,
        title="Проверка поставки", statuses={"working": True},
        event="Получено обращение", event_key="incoming:client-9",
    )
    bots = Bots(tg, tg, cfg.telegram.owner_chat_id)
    first._delivery = lambda: SimpleNamespace(store=first.store, bots=bots)
    original_update_card = CaseJournal.update_card

    def stop_before_card_event(self, *args, **kwargs):
        if str(kwargs.get("event_key", "")).startswith("delivered:"):
            raise ProcessStopped
        return original_update_card(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(CaseJournal, "update_card", stop_before_card_event)
        with pytest.raises(ProcessStopped):
            first.send(
                CLIENT_CHAT, "Проверенный ответ", key="sent-before-card-event",
                reply_to="client-9", topic_id=topic_id,
            )

    stable_key = "native-send:sent-before-card-event"
    sent_outbox = first.store.outbox_by_key(stable_key)
    delivered_key = f"delivered:{sent_outbox['id']}"
    assert sent_outbox["status"] == "sent"
    assert sent_outbox["tg_message_id"] is not None
    assert not any(event["key"] == delivered_key
                   for event in first.store.kv_get(f"case_card:{topic_id}")["events"])
    first.store.db.close()

    restarted = NativeBridge(cfg)
    restart_bots = Bots(tg, tg, cfg.telegram.owner_chat_id)
    restarted._delivery = lambda: SimpleNamespace(store=restarted.store, bots=restart_bots)
    result = restarted.send(
        CLIENT_CHAT, "Проверенный ответ", key="sent-before-card-event",
        reply_to="client-9", topic_id=topic_id,
    )

    saved_card = restarted.store.kv_get(f"case_card:{topic_id}")
    answer_events = [event for event in saved_card["events"] if event["key"] == delivered_key]
    client_sends = [item for item in tg.sent if item[0] == CLIENT_CHAT]
    assert result["status"] == "sent"
    assert len(client_sends) == 1
    assert saved_card["number"] == original_card["number"]
    assert saved_card["message_id"] == original_card["message_id"]
    assert len(answer_events) == 1
    assert "Проверенный ответ" in answer_events[0]["text"]
    assert tg.edits[-1][1] == original_card["message_id"]

def test_visible_startup_resolves_interrupted_native_sends_on_linked_card(tmp_path):
    from types import SimpleNamespace

    from support_agent.runner import Agent

    class ProcessStopped(BaseException):
        pass

    class CardsTelegram:
        def __init__(self):
            self.sent = []
            self.edits = []
            self.next_id = 1000

        def send_message(self, chat_id, text, reply_to=None):
            self.sent.append((chat_id, text, reply_to))
            if chat_id == CLIENT_CHAT:
                raise ProcessStopped
            self.next_id += 1
            return str(self.next_id)

        def edit_message(self, chat_id, message_id, text):
            self.edits.append((chat_id, message_id, text))

    cfg = make_config(tmp_path)
    cfg.agent.visible_moderator = True
    cfg.agent.client_replies_enabled = True
    cfg.agent.history_dir = str(tmp_path / "history")
    first = NativeBridge(cfg)
    first.store.set_binding(
        CLIENT_CHAT, {"tenant_id": "tenant-test", "tenant_name": "Тест"}, bound_by="owner"
    )
    tg = CardsTelegram()
    topic_id = "native:startup-unknown-deliveries"
    original_card = first.journal.update_card(
        tg, cfg.telegram.owner_chat_id, topic_id, CLIENT_CHAT,
        title="Проверка поставки", statuses={"working": True},
        event="Получено обращение", event_key="incoming:startup-unknown",
    )
    bots = Bots(tg, tg, cfg.telegram.owner_chat_id)
    first._delivery = lambda: SimpleNamespace(store=first.store, bots=bots)

    stable_keys = ["native-send:startup-unknown-a", "native-send:startup-unknown-b"]
    for key, answer in zip(
        stable_keys, ("Проверенный ответ А", "Проверенный ответ Б"), strict=True,
    ):
        with pytest.raises(ProcessStopped):
            first.send(CLIENT_CHAT, answer, key=key.removeprefix("native-send:"),
                       topic_id=topic_id)
        interrupted = first.store.outbox_by_key(key)
        assert interrupted["status"] == "sending"
        assert interrupted["attempts"] == 1
    assert len([item for item in tg.sent if item[0] == CLIENT_CHAT]) == 2
    first.store.db.close()

    restarted = NativeBridge(cfg)
    sends_before_startup = len(tg.sent)
    Agent(cfg, restarted.store, tg, None, lambda: 1.0).startup()

    resolved = [restarted.store.outbox_by_key(key) for key in stable_keys]
    assert [item["status"] for item in resolved] == ["unknown", "unknown"]
    assert [item["attempts"] for item in resolved] == [1, 1]
    assert len(tg.sent) == sends_before_startup

    saved_card = restarted.store.kv_get(f"case_card:{topic_id}")
    unconfirmed = [event for event in saved_card["events"]
                   if "не подтвержд" in event["text"].lower()]
    assert len(unconfirmed) == 2
    for event in unconfirmed:
        text = event["text"].lower()
        assert "повтор" in text
        assert "провер" in text or "чат" in text
    assert saved_card["number"] == original_card["number"]
    assert saved_card["message_id"] == original_card["message_id"]
    assert tg.edits
    assert all(edit[1] == original_card["message_id"] for edit in tg.edits)
    assert "не подтвержд" in tg.edits[-1][2].lower()
    assert tg.edits[-1][2].lower().count("не подтвержд") >= 2

def test_replayed_confirmed_native_send_retries_failed_card_projection(tmp_path):
    import json
    from itertools import count

    from support_agent.telegram import TelegramError, reconcile_case_delivery

    class CardsTelegram:
        def __init__(self):
            self.ids = count(2000)
            self.sent = []
            self.edit_attempts = []

        def send_message(self, chat_id, text, reply_to=None):
            message_id = str(next(self.ids))
            self.sent.append((chat_id, text, reply_to, message_id))
            return message_id

        def edit_message(self, chat_id, message_id, text):
            self.edit_attempts.append((chat_id, message_id, text))
            if len(self.edit_attempts) == 1:
                raise TelegramError("unknown", "simulated_owner_card_edit_failure")

    cfg = make_config(tmp_path)
    cfg.agent.visible_moderator = True
    cfg.agent.client_replies_enabled = True
    cfg.agent.history_dir = str(tmp_path / "history")
    first = NativeBridge(cfg)
    first.store.set_binding(
        CLIENT_CHAT, {"tenant_id": "tenant-test", "tenant_name": "Тест"}, bound_by="owner"
    )
    tg = CardsTelegram()
    topic_id = "native:retry-card-projection"
    original_card = first.journal.update_card(
        tg, cfg.telegram.owner_chat_id, topic_id, CLIENT_CHAT,
        title="Проверка поставки", statuses={"working": True},
        event="Получено обращение", event_key="incoming:projection-retry",
    )
    answer = "Проверенный ответ после сбоя карточки"
    stable_key = "native-send:projection-retry"
    first.store.queue_message(
        key=stable_key, chat_id=CLIENT_CHAT, text=answer,
        purpose="native_reply", repeat_ok=False,
    )
    queued = first.store.outbox_by_key(stable_key)
    assert first.store.claim_outbox(queued["id"])
    client_message_id = tg.send_message(CLIENT_CHAT, answer)
    first.store.finish_outbox(queued["id"], "sent", client_message_id)
    first.store.kv_set(
        f"reply_case:{stable_key}",
        {"topic_id": topic_id, "chat_id": CLIENT_CHAT,
         "destination_chat_id": CLIENT_CHAT, "kind": "answer"},
    )
    sent_outbox = first.store.outbox_by_key(stable_key)
    delivered_key = f"delivered:{sent_outbox['id']}"
    assert sent_outbox["status"] == "sent"
    assert len(tg.edit_attempts) == 0

    reconcile_case_delivery(
        first.journal, first.store, tg, cfg.telegram.owner_chat_id, sent_outbox,
    )
    assert len(tg.edit_attempts) == 1
    assert sent_outbox["tg_message_id"] is not None
    failed_projection = first.store.kv_get(f"case_card:{topic_id}")
    assert failed_projection["message_id"] == original_card["message_id"]
    assert failed_projection["delivery"] == "unknown"
    assert answer not in failed_projection.get("last_text", "")
    assert any(event["key"] == delivered_key for event in failed_projection["events"])
    journal_rows = first.store.rows("SELECT value FROM kv WHERE key LIKE 'journal_event:%'")
    assert any(
        json.loads(row["value"])["key"] == delivered_key
        for row in journal_rows
    )
    assert len([item for item in tg.sent if item[0] == CLIENT_CHAT]) == 1
    first.store.db.close()

    restarted = NativeBridge(cfg)
    reconcile_case_delivery(
        restarted.journal, restarted.store, tg, cfg.telegram.owner_chat_id,
        restarted.store.outbox_by_key(stable_key),
    )

    saved_card = restarted.store.kv_get(f"case_card:{topic_id}")
    answer_events = [event for event in saved_card["events"] if event["key"] == delivered_key]
    client_sends = [item for item in tg.sent if item[0] == CLIENT_CHAT]
    assert restarted.store.outbox_by_key(stable_key)["status"] == "sent"
    assert len(client_sends) == 1
    assert len(answer_events) == 1
    assert len(tg.edit_attempts) == 2
    assert tg.edit_attempts[-1][0] == cfg.telegram.owner_chat_id
    assert tg.edit_attempts[-1][1] == original_card["message_id"]
    assert answer in tg.edit_attempts[-1][2]
    assert answer in saved_card["last_text"]
    assert saved_card["number"] == original_card["number"]
    assert saved_card["message_id"] == original_card["message_id"]
