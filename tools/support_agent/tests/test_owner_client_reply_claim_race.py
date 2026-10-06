"""WMS-676 F1: committed policy changes must win before pending -> sending.

Synthetic SQLite connections and recording Telegram only. The current dispatcher
is synchronous; the injected limiter models a yield immediately before its real
claim, without replacing either the policy guard or the claim implementation.
"""

import asyncio

import pytest

from support_agent.store import Store
from support_agent.telegram import flush_outbox, recover_after_restart

from .test_owner_client_reply_pause import CLIENT_CHAT, OWNER_CHAT, OWNER_ID
from .test_owner_client_reply_pause import paused as paused  # noqa: F401
from .test_owner_client_reply_pause_cli import _source


class CallbackLimiter:
    """Deterministic yield: finish the competing writer before allowing claim."""

    def __init__(self, callback):
        self.callback = callback
        self.calls = 0

    async def acquire(self):
        self.calls += 1
        self.callback()


@pytest.mark.parametrize("change", ["pause", "approval_revoked", "ticket_version"])
def test_committed_change_during_claim_wait_prevents_external_send(paused, monkeypatch, change):
    e = paused
    policy_key = f"owner_client_reply_pause:{CLIENT_CHAT}"
    body = "Конкретный проверенный ответ"
    if change == "pause":
        e.store.execute("DELETE FROM kv WHERE key=?", (policy_key,))
        key = "queued-before-owner-pause"
        e.store.queue_message(key=key, chat_id=CLIENT_CHAT, text=body, ticket_id=e.ticket)
    else:
        source = _source(e, e.store.client_reply_approval_text(CLIENT_CHAT, e.ticket, "v1", body))
        key = e.store.approve_client_reply(
            chat_id=CLIENT_CHAT, ticket_id=e.ticket, version="v1", text=body,
            owner_user_id=OWNER_ID, owner_chat_id=OWNER_CHAT, source_message_id=source,
        )

    # Unknown / interrupted sends are separate intents and must never be replayed.
    for status in ("unknown", "sending"):
        e.store.queue_message(key=f"do-not-replay:{status}", chat_id=CLIENT_CHAT,
                              text=status, ticket_id=e.ticket, repeat_ok=False)
        e.store.execute("UPDATE outbox SET status=? WHERE key=?",
                        (status, f"do-not-replay:{status}"))

    other = Store(e.path)
    original_claim = e.store.claim_outbox
    original_guard = e.store.outbox_delivery_allowed
    first_guards = []

    def observe_guard(item, **kwargs):
        allowed = original_guard(item, **kwargs)
        first_guards.append(allowed)
        return allowed

    def commit_change():
        assert e.store.outbox_by_key(key)["status"] == "pending"
        assert e.tg.sent == []
        assert original_guard(e.store.outbox_by_key(key), owner_user_id=OWNER_ID,
                              owner_chat_id=OWNER_CHAT), "Initially authorized, not a bad fixture"
        if change == "pause":
            other.pause_client_replies(chat_id=CLIENT_CHAT, ticket_ids=[e.ticket],
                                       owner_user_id=OWNER_ID, source_message_id=e.source)
        elif change == "approval_revoked":
            other.set_message(source, text="Разрешение отозвано", revision=2)
        else:
            other.patch_data(e.ticket, agent={"version": "v2"})
        assert not other.db.in_transaction, "Competing change must commit before claim"
        assert not original_guard(e.store.outbox_by_key(key), owner_user_id=OWNER_ID,
                                  owner_chat_id=OWNER_CHAT), "Committed change forbids this reply"

    limiter = CallbackLimiter(commit_change)

    def claim_after_wait(outbox_id, *args, **kwargs):
        if outbox_id == e.store.outbox_by_key(key)["id"] and limiter.calls == 0:
            asyncio.run(limiter.acquire())
        return original_claim(outbox_id, *args, **kwargs)

    monkeypatch.setattr(e.store, "outbox_delivery_allowed", observe_guard)
    monkeypatch.setattr(e.store, "claim_outbox", claim_after_wait)
    try:
        sent = flush_outbox(e.store, e.tg, e.cfg)
        assert limiter.calls == 1, "The race window was actually exercised"
        assert len(e.tg.sent) == 0, (
            f"{change}: Telegram external calls must be 0; got {len(e.tg.sent)} "
            f"after a committed prohibition (initial guards={first_guards}, flush={sent})"
        )
        assert sent == 0
        assert e.store.outbox_by_key(key)["status"] == "pending"
        assert e.store.outbox_by_key(key)["attempts"] == 0
        assert e.store.client_reply_pause(CLIENT_CHAT)["paused"] is True
        assert e.store.client_reply_pause(OWNER_CHAT) is None
        assert e.store.data(e.ticket)["analysis"] == {"hypothesis": "saved"}

        reopened = Store(e.path)
        try:
            recover_after_restart(reopened, e.cfg)
            assert reopened.client_reply_pause(CLIENT_CHAT)["paused"] is True
            # Recovery may notify the owner; no client calls or old intents replay.
            flush_outbox(reopened, e.tg, e.cfg)
            flush_outbox(reopened, e.tg, e.cfg)
            assert all(chat != CLIENT_CHAT for chat, _ in e.tg.sent)
            for status in ("unknown", "sending"):
                assert reopened.outbox_by_key(f"do-not-replay:{status}")["status"] == "unknown"
            assert reopened.outbox_by_key(key)["status"] == "pending"
        finally:
            reopened.db.close()
    finally:
        other.db.close()
