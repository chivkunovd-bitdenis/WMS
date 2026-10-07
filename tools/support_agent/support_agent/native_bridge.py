"""Telegram transport and journal access for an ordinary native Codex chat.

No routing, topic lifecycle, agents, decisions, delegation or turn scheduling.
The native chat reads the materials and decides what to do itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from .case_journal import CaseJournal
from .config import load_config
from .media import archive_root
from .store import Store


class NativeBridge:
    def __init__(self, cfg: Any) -> None:
        self.cfg, self.store = cfg, Store(cfg.db_path)
        self.journal = CaseJournal(self.store, archive_root(cfg))

    def status(self) -> dict[str, Any]:
        return {"paused": bool(self.store.kv_get("native_paused", True)),
                "ready": bool(self.store.kv_get("native_ready", False)),
                "moderator_thread_id": self.cfg.agent.moderator_thread_id,
                "client_replies_enabled": self.cfg.agent.client_replies_enabled,
                "history_root": str(self.journal.root),
                "latest_message_id": self.store.row("SELECT coalesce(max(id),0) n FROM messages")["n"],
                "latest_edit_id": self.store.row("SELECT coalesce(max(id),0) n FROM message_revisions")["n"],
                "cards": [{k: v for k, v in json.loads(row["value"]).items()
                           if k in ("number", "topic_id", "chat_id", "title", "summary", "statuses")}
                          for row in self.store.rows("SELECT value FROM kv WHERE key LIKE 'case_card:%'")]}

    def _messages(self, rows: list[Any]) -> list[dict[str, Any]]:
        return [{**dict(row), "media": self.store.kv_get(f"media:{row['id']}:{row['revision']}", {}),
                 "case_topic_id": self.journal.find_topic(row["reply_to"])
                 if row["role"] == "owner" else None} for row in rows]

    def history(self, chat_id: int, limit: int = 100, before_id: int = 2**63 - 1) -> dict[str, Any]:
        rows = self.store.rows("SELECT * FROM messages WHERE chat_id=? AND id<? ORDER BY id DESC LIMIT ?",
                               (chat_id, before_id, max(1, min(limit, 500))))
        outgoing = self.store.rows(
            "SELECT id,text,status,tg_message_id,reply_to,sent_at FROM outbox "
            "WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, max(1, min(limit, 500))))
        self.journal.sync_chat(chat_id)
        return {"chat_id": chat_id, "messages": self._messages(list(reversed(rows))),
                "outgoing": [dict(row) for row in reversed(outgoing)],
                "full_history": str(self.journal.root / f"chat-{chat_id}" / "history.jsonl")}

    def inbox(self, after_id: int = 0, after_edit_id: int = 0, limit: int = 100,
              known_materials: dict[str, str] | None = None) -> dict[str, Any]:
        rows = self.store.rows("SELECT * FROM messages WHERE id>? ORDER BY id LIMIT ?",
                               (after_id, max(1, min(limit, 500))))
        edits = self.store.rows("SELECT * FROM message_revisions WHERE id>? ORDER BY id LIMIT ?",
                                (after_edit_id, max(1, min(limit, 500))))
        revised = []
        for row in edits:
            current = self.store.row("SELECT * FROM messages WHERE id=?", (row["message_id"],))
            revised.append({**dict(row), "current": self._messages([current])[0]})
        # Attachments and transcripts arrive after the Telegram message itself. A
        # reader can retain these fingerprints to observe their completion without
        # rewinding its message cursor or having this transport acknowledge work.
        ids = set(known_materials or {}) | {str(row["id"]) for row in rows if row["file_id"]}
        versions, materials = {}, []
        for message_id in sorted(ids):
            row = self.store.row("SELECT * FROM messages WHERE id=?", (int(message_id),))
            if row is None:
                continue
            message = self._messages([row])[0]
            state = [message["revision"], message["text"], message["status"], message["media"]]
            # Full 64-hex strings are intentionally masked by the shared secret
            # scrubber. This public revision token must survive CLI serialization.
            digest = "v-" + hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()[:20]
            versions[message_id] = digest
            if message_id in (known_materials or {}) and known_materials[message_id] != digest:
                materials.append(message)
        return {"messages": self._messages(rows), "edits": revised,
                "materials": materials, "material_versions": versions,
                "next_message_id": max([after_id, *[int(row["id"]) for row in rows]]),
                "next_edit_id": max([after_edit_id, *[int(row["id"]) for row in edits]])}

    def watch(self, after_id: int, after_edit_id: int = 0, seconds: int = 45,
              known_materials: dict[str, str] | None = None) -> dict[str, Any]:
        until = time.monotonic() + min(45, max(0, seconds))
        while True:
            data = self.inbox(after_id, after_edit_id, known_materials=known_materials)
            if data["messages"] or data["edits"] or data["materials"] or time.monotonic() >= until:
                return data
            time.sleep(1)

    def note(self, chat_id: int, text: str, kind: str = "finding", topic_id: str | None = None,
             key: str = "") -> dict[str, Any]:
        self.journal.record(chat_id, kind, text, key or str(uuid.uuid4()), topic_id=topic_id)
        return {"saved": True, "history": str(self.journal.root / f"chat-{chat_id}" / "history.jsonl")}

    def _delivery(self) -> Any:
        if self.store.kv_get("native_paused", True):
            raise ValueError("Telegram sending is paused by owner")
        from .runner import build_agent
        return build_agent(self.cfg)

    def card(self, topic_id: str, chat_id: int, title: str = "", summary: str | None = None,
             statuses: dict[str, Any] | None = None, event: str | None = None,
             event_key: str | None = None, task_url: str = "") -> dict[str, Any]:
        agent = self._delivery()
        binding = self.store.binding(chat_id)
        title_chat = str(binding["chat_title"]) if binding else str(chat_id)
        return self.journal.update_card(agent.bots.owner, self.cfg.telegram.owner_chat_id,
                                       topic_id, chat_id, title, summary, statuses, event,
                                       event_key, chat_title=title_chat, task_url=task_url)

    def send(self, chat_id: int, text: str, key: str, reply_to: str | None = None,
             file_path: str | None = None) -> dict[str, Any]:
        agent = self._delivery()
        from .telegram import flush_outbox
        if chat_id != self.cfg.telegram.owner_chat_id and self.store.binding(chat_id) is None:
            raise ValueError("unknown connected chat")
        stable_key = "native-send:" + key
        self.store.queue_message(key=stable_key, chat_id=chat_id, text=text, reply_to=reply_to,
                                 purpose="native_reply", repeat_ok=False, file_path=file_path)
        row = self.store.outbox_by_key(stable_key)
        flush_outbox(agent.store, agent.bots, self.cfg, only_ids={int(row["id"])})
        result = self.store.outbox_by_key(stable_key)
        self.journal.sync_chat(chat_id)
        return {"key": key, "status": result["status"], "message_id": result["tg_message_id"]}

    def context(self, thread_id: str) -> dict[str, Any]:
        latest: dict[str, Any] = {}
        for path in sorted((Path.home() / ".codex/sessions").rglob(f"*{thread_id}*.jsonl")):
            with path.open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    payload = record.get("payload") or {}
                    if payload.get("type") == "token_count" and payload.get("info"):
                        latest = payload["info"]
        usage = latest.get("last_token_usage") or {}
        occupied = (int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))) if usage else None
        return {"thread_id": thread_id, "context_tokens": occupied,
                "model_context_window": latest.get("model_context_window"), "soft_limit": 250000}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["status", "history", "inbox", "watch", "note", "card", "send", "context"])
    parser.add_argument("--config", default=None)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()
    bridge = NativeBridge(load_config(args.config))
    from .redact import scrub
    try:
        data = json.loads(args.json if args.json is not None else sys.stdin.read() or "{}")
        result = getattr(bridge, args.command)(**data)
        print(scrub(bridge.cfg, json.dumps(result, ensure_ascii=False, default=str)))
        return 0
    except Exception as exc:
        error = {"error": type(exc).__name__, "detail": scrub(bridge.cfg, str(exc))}
        print(json.dumps(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
