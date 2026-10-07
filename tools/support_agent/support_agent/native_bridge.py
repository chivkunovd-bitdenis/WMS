"""Small durable transport for the visible native Codex moderator.

Meaning and delegation belong to the moderator. This module provides history,
leases, exact source identity, case cards and safe handover; it never classifies text.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from .case_journal import CaseJournal
from .config import load_config
from .store import Store


class NativeBridge:
    def __init__(self, cfg: Any, store: Store | None = None) -> None:
        self.cfg, self.store = cfg, store or Store(cfg.db_path)
        self.journal = CaseJournal(
            self.store, cfg.agent.history_dir or Path(cfg.repo) / "var/support-conversations"
        )

    def owner(self, row: Any) -> bool:
        return (
            row["role"] == "owner"
            and int(row["chat_id"]) == int(self.cfg.telegram.owner_chat_id)
            and str(row["author_id"]) == str(self.cfg.telegram.owner_user_id)
        )

    def ingest(self) -> None:
        chats: set[int] = set()
        with self.store.transaction():
            queue = list(self.store.kv_get("agent_dispatch_queue", []))
            for row in self.store.messages_with_status("new", 500):
                if row["role"] not in ("owner", "client", "partner"):
                    continue
                if row["role"] == "owner" and not self.owner(row):
                    self.store.set_message(int(row["id"]), status="handled")
                    continue
                eid = f"in:{row['id']}:{row['revision']}"
                if not self.store.kv_get(f"agent_event:{eid}"):
                    self.store.kv_set(
                        f"agent_event:{eid}",
                        {
                            "id": eid,
                            "kind": "input",
                            "source_id": int(row["id"]),
                            "revision": int(row["revision"]),
                            "chat_id": int(row["chat_id"]),
                            "owner": self.owner(row),
                            "text": row["text"],
                            "ts": row["ts"],
                            "linked_topic_id": self.journal.find_topic(row["reply_to"])
                            if self.owner(row)
                            else None,
                        },
                    )
                    queue.append(eid)
                self.store.set_message(int(row["id"]), status="routed")
                chats.add(int(row["chat_id"]))
            self.store.kv_set("agent_dispatch_queue", list(dict.fromkeys(queue)))
        for chat_id in chats:
            self.journal.sync_chat(chat_id)

    def snapshot(self) -> dict[str, Any]:
        self.ingest()
        topics = [self.store.kv_get(f"agent_topic:{tid}", {})
                  for tid in self.store.kv_get("agent_topic_index", [])]
        archive = self.journal.root / "topics-state.json"
        tmp = archive.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(topics, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(archive)
        compact = [{k: value for k, value in topic.items() if k in (
            "id", "chat_id", "status", "pending", "worker_session_id", "native_agent_id", "task_ids")}
                   | {"summary": str(topic.get("summary") or "")[:500]}
                   for topic in topics]
        return {
            "moderator": self.store.kv_get("agent_native_moderator", {}),
            "native_ready": bool(self.store.kv_get("native_ready", False)),
            "heartbeat_id": self.store.kv_get("native_heartbeat_id", ""),
            "history_root": str(self.journal.root),
            "case_archive": str(archive),
            "cases": compact,
            "events": self.events(),
            "claims": [json.loads(row["value"]) for row in self.store.rows(
                "SELECT value FROM kv WHERE key LIKE 'agent_native_claim:%'")],
            "jobs": [self.store.kv_get(f"agent_job:{jid}", {})
                     for jid in self.store.kv_get("agent_job_index", [])],
        }

    def events(self, limit: int = 50, worker_id: str = "") -> list[dict[str, Any]]:
        self.ingest()
        result = []
        now = time.time()
        for eid in self.store.kv_get("agent_dispatch_queue", []):
            if self.store.kv_get(f"agent_event_done:{eid}"):
                continue
            lease = self.store.kv_get(f"agent_native_claim:{eid}", {})
            if lease and lease.get("worker_id") != worker_id and float(lease.get("expires_at", 0)) > now:
                continue
            event = self.store.kv_get(f"agent_event:{eid}", {})
            if not event:
                continue
            item = dict(event)
            if item.get("source_id"):
                row = self.store.row("SELECT * FROM messages WHERE id=?", (item["source_id"],))
                item["source_message"] = dict(row) if row else None
                binding = self.store.binding(int(item["chat_id"]))
                item["chat_title"] = str(binding["chat_title"]) if binding else ""
                # Paths are prepared by intake; no credentials are ever returned.
                item["media"] = self.store.kv_get(f"media:{item['source_id']}:{item.get('revision', 1)}", {})
            item["claim"] = lease or None
            result.append(item)
            if len(result) >= max(1, min(200, limit)):
                break
        return result

    def watch(self, seconds: int = 45, worker_id: str = "") -> list[dict[str, Any]]:
        until = time.monotonic() + max(0, min(45, seconds))
        while True:
            result = self.events(worker_id=worker_id)
            if result or time.monotonic() >= until:
                return result
            time.sleep(1)

    def register(
        self,
        thread_id: str,
        generation: int | None = None,
        project_id: str = "79eb5dbd-44eb-4518-bddd-ca5bed6f93a4",
    ) -> dict[str, Any]:
        with self.store.transaction():
            previous = self.store.kv_get("agent_native_moderator", {})
            if previous.get("thread_id") == thread_id and (
                generation is None or generation == previous.get("generation")
            ):
                return previous
            state = {
                "thread_id": thread_id,
                "generation": generation or previous.get("generation", 1),
                "name": f"Чат разбора №{generation or previous.get('generation', 1)}",
                "registered_at": time.time(),
                "predecessor": previous.get("thread_id"),
                "project_id": project_id,
            }
            self.store.kv_set("agent_native_moderator", state)
            return state

    def claim(
        self,
        event_ids: list[str],
        worker_id: str = "",
        topic_id: str = "",
        thread_id: str = "",
        ttl: int = 3600,
        inspected_previous_outcome: bool = False,
    ) -> dict[str, Any]:
        worker_id = worker_id or thread_id
        if not worker_id:
            raise ValueError("worker/thread identity required")
        if not event_ids:
            return {"error": "event_ids_required"}
        with self.store.transaction():
            now = time.time()
            existing_topic = self.store.kv_get(f"agent_topic:{topic_id}", {}) if topic_id else {}
            for eid in event_ids:
                incoming = self.store.kv_get(f"agent_event:{eid}", {})
                if existing_topic and incoming.get("kind") == "input" and not incoming.get("owner"):
                    if int(incoming.get("chat_id", 0)) != int(existing_topic.get("chat_id", 0)):
                        return {"error": "client_case_chat_scope", "event_id": eid}
                if not self.store.kv_get(f"agent_event:{eid}") or self.store.kv_get(
                    f"agent_event_done:{eid}"
                ):
                    return {"error": "event_unavailable", "event_id": eid}
                old = self.store.kv_get(f"agent_native_claim:{eid}", {})
                if old.get("worker_id") and old.get("worker_id") != worker_id:
                    if float(old.get("expires_at", 0)) <= now and not inspected_previous_outcome:
                        return {
                            "error": "expired_claim_requires_outcome_inspection",
                            "event_id": eid,
                            "worker_id": old["worker_id"],
                        }
                    if inspected_previous_outcome:
                        continue
                    return {"error": "already_claimed", "event_id": eid, "worker_id": old["worker_id"]}
            for eid in event_ids:
                self.store.kv_set(
                    f"agent_native_claim:{eid}",
                    {
                        "event_id": eid,
                        "worker_id": worker_id,
                        "topic_id": topic_id,
                        "claimed_at": now,
                        "expires_at": now + max(30, min(86400, ttl)),
                    },
                )
            if topic_id:
                topic = self.store.kv_get(f"agent_topic:{topic_id}", {})
                if not topic:
                    first = self.store.kv_get(f"agent_event:{event_ids[0]}", {})
                    topic = {
                        "id": topic_id,
                        "chat_id": first.get("chat_id"),
                        "pending": [],
                        "generation": 0,
                        "created_at": now,
                    }
                    index = list(self.store.kv_get("agent_topic_index", []))
                    if topic_id not in index:
                        index.append(topic_id)
                        self.store.kv_set("agent_topic_index", index)
                topic["pending"] = list(dict.fromkeys([*topic.get("pending", []), *event_ids]))
                topic["status"] = "running"
                topic["native_agent_id"] = worker_id
                topic["generation"] = int(topic.get("generation", 0)) + 1
                self.store.kv_set(f"agent_topic:{topic_id}", topic)
            return {"claimed": event_ids, "worker_id": worker_id}

    def topic(self, topic_id: str, chat_id: int | None = None, **fields: Any) -> dict[str, Any]:
        with self.store.transaction():
            old = self.store.kv_get(f"agent_topic:{topic_id}", {})
            if not old and chat_id is None:
                raise ValueError("new topic requires original chat_id")
            if old and chat_id is not None and int(old["chat_id"]) != int(chat_id):
                raise ValueError("original case chat cannot change")
            topic = old or {
                "id": topic_id,
                "chat_id": chat_id,
                "pending": [],
                "generation": 0,
                "created_at": time.time(),
                "status": "queued",
            }
            allowed = {
                "summary",
                "next_action",
                "status",
                "worker_session_id",
                "native_agent_id",
                "task_ids",
                "affected_areas",
                "last_source_id",
                "last_client_source_id",
                "pending",
                "handoff",
                "wake_at",
            }
            if set(fields) - allowed:
                raise ValueError("unsupported topic fields")
            topic.update(fields)
            self.store.kv_set(f"agent_topic:{topic_id}", topic)
            index = list(self.store.kv_get("agent_topic_index", []))
            if topic_id not in index:
                index.append(topic_id)
                self.store.kv_set("agent_topic_index", index)
            return topic

    def ack(
        self,
        event_ids: list[str],
        worker_id: str = "",
        topic_id: str = "",
        summary: str = "",
        result: str = "",
        statuses: dict[str, Any] | None = None,
        thread_id: str = "",
        revisions: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        worker_id = worker_id or thread_id
        topic = self.store.kv_get(f"agent_topic:{topic_id}", {})
        if not topic:
            return {"error": "topic_not_found"}
        # Persist completed evidence before removing inbox membership. File lock is
        # acquired outside the SQLite transaction to keep lock ordering consistent.
        for eid in event_ids:
            lease = self.store.kv_get(f"agent_native_claim:{eid}", {})
            if lease.get("worker_id") != worker_id:
                return {"error": "claim_owner_mismatch", "event_id": eid}
            self.journal.record(
                int(topic["chat_id"]),
                "result",
                result or summary,
                f"native-result:{eid}",
                topic_id=topic_id,
                data={"worker_id": worker_id, "statuses": statuses or {}},
            )
        with self.store.transaction():
            for eid in event_ids:
                lease = self.store.kv_get(f"agent_native_claim:{eid}", {})
                if lease.get("worker_id") != worker_id:
                    return {"error": "claim_owner_mismatch", "event_id": eid}
                event = self.store.kv_get(f"agent_event:{eid}", {})
                if revisions and eid in revisions and int(event.get("revision", 1)) != int(revisions[eid]):
                    return {"error": "revision_mismatch", "event_id": eid}
            topic = self.store.kv_get(f"agent_topic:{topic_id}", {})
            topic["summary"] = summary or topic.get("summary", "")
            topic["pending"] = [eid for eid in topic.get("pending", []) if eid not in event_ids]
            topic["status"] = "running" if topic["pending"] else "waiting"
            self.store.kv_set(f"agent_topic:{topic_id}", topic)
            for eid in event_ids:
                self.store.kv_set(f"agent_event_done:{eid}", True)
                event = self.store.kv_get(f"agent_event:{eid}", {})
                if event.get("source_id"):
                    row = self.store.row("SELECT revision FROM messages WHERE id=?", (event["source_id"],))
                    if row and int(row["revision"]) == int(event.get("revision", 1)):
                        self.store.set_message(int(event["source_id"]), status="handled")
            queue = [eid for eid in self.store.kv_get("agent_dispatch_queue", []) if eid not in event_ids]
            self.store.kv_set("agent_dispatch_queue", queue)
            return {"acknowledged": event_ids, "topic_id": topic_id}

    def handoff(
        self, thread_id: str = "", summary: str = "", generation: int | None = None, new_thread_id: str = ""
    ) -> dict[str, Any]:
        thread_id = thread_id or new_thread_id
        if not thread_id:
            raise ValueError("successor actual thread ID required")
        snapshot = self.snapshot()
        old = snapshot["moderator"]
        if old.get("thread_id") == thread_id:
            return old
        number = generation or int(old.get("generation", 1)) + 1
        payload = {
            **snapshot,
            "summary": summary,
            "successor_thread_id": thread_id,
            "created_at": time.time(),
            "instruction": "Keep worker sessions and claims. "
            "Do not duplicate jobs. Old active workers finish safe steps; new input and their "
            "durable results belong to the successor. Read client history as necessary.",
        }
        path = self.journal.root / f"native-moderator-handoff-{number - 1}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)
        state = self.register(thread_id, number)
        state["handoff_path"] = str(path)
        self.store.kv_set("agent_native_moderator", state)
        return state

    def history(
        self,
        chat_id: int,
        limit: int = 100,
        before: str | None = None,
        after: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        self.journal.sync_chat(chat_id)
        return self.store.history_page(
            chat_id, before=before, after=after, limit=max(1, min(500, limit)), query=query
        )

    def context(self, thread_id: str) -> dict[str, Any]:
        # Read only the exact native thread's rollout; never touch Codex state DB.
        root = Path.home() / ".codex" / "sessions"
        matches = list(root.rglob(f"*{thread_id}*.jsonl"))
        latest: dict[str, Any] = {}
        if not matches:
            return {"thread_id": thread_id, "available": False}
        path = max(matches, key=lambda item: item.stat().st_mtime)
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                payload = item.get("payload") or {}
                if item.get("type") == "event_msg" and payload.get("type") == "token_count":
                    info = payload.get("info") or {}
                    usage = info.get("last_token_usage") or {}
                    if usage:
                        latest = {
                            "usage": usage,
                            "model_context_window": info.get("model_context_window"),
                            "timestamp": item.get("timestamp"),
                        }
        usage = latest.get("usage") or {}
        occupied = int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
        return {
            "thread_id": thread_id,
            "available": bool(latest),
            "context_tokens": occupied,
            "soft_limit_tokens": 250000,
            "handoff_recommended": occupied >= 250000,
            **latest,
        }

    def case(
        self,
        topic_id: str,
        chat_id: int | None = None,
        title: str = "",
        summary: str | None = None,
        statuses: dict[str, Any] | None = None,
        event: str = "",
        event_key: str = "",
        source_id: int | None = None,
        thread_id: str = "",
        worker_session_id: str = "",
        task_url: str = "",
    ) -> dict[str, Any]:
        if source_id:
            row = self.store.row("SELECT * FROM messages WHERE id=?", (source_id,))
            if row is None:
                return {"error": "source_not_found"}
            existing = self.store.kv_get(f"agent_topic:{topic_id}", {})
            chat_id = chat_id or existing.get("chat_id") or int(row["chat_id"])
        fields = {}
        if summary is not None:
            fields["summary"] = summary
        if worker_session_id:
            fields["worker_session_id"] = worker_session_id
        if thread_id:
            fields["native_agent_id"] = thread_id
        topic = self.topic(topic_id, chat_id=chat_id, **fields)
        original_chat = int(topic["chat_id"])
        binding = self.store.binding(original_chat)
        chat_title = str(binding["chat_title"]) if binding else ""
        import httpx

        from .telegram import TelegramClient

        with httpx.Client() as client:
            tg = TelegramClient(self.cfg.telegram.owner_token, client)
            return self.journal.update_card(
                tg,
                self.cfg.telegram.owner_chat_id,
                topic_id,
                original_chat,
                title=title,
                summary=summary,
                statuses=statuses,
                event=event or None,
                event_key=event_key or f"native-card:{topic_id}:{source_id}:{event}",
                chat_title=chat_title,
                task_url=task_url,
            )

    def action(
        self, source_id: int, topic_id: str, name: str, args: dict[str, Any], revision: int | None = None
    ) -> dict[str, Any]:
        from .runner import build_agent
        from .telegram import flush_outbox

        agent = build_agent(self.cfg)
        source = agent.store.row("SELECT * FROM messages WHERE id=?", (source_id,))
        if source is None or revision is not None and int(source["revision"]) != revision:
            return {"error": "missing_or_edited_source"}
        from .agent_coordinator import AgentCoordinator
        from .agent_tools import AgentTools

        coordinator = agent.pipe.agent or AgentCoordinator(agent.pipe, AgentTools(agent.pipe))
        context = coordinator._context(source, owner=coordinator._owner(source))
        context["topic_id"] = topic_id
        before = int(agent.store.row("SELECT coalesce(max(id),0) AS n FROM outbox")["n"])
        if name in {
            "project_job",
            "schedule_project_job",
            "job_status",
            "cancel_job",
            "send_job_file",
            "select_model",
        }:
            result = coordinator._owner_tool(name, args, context)
        elif name == "read_history":
            result = coordinator._read_history(args, context)
        else:
            result = coordinator.tools.dispatch(name, args, context)
        new_ids = {int(row["id"]) for row in agent.store.rows("SELECT id FROM outbox WHERE id>?", (before,))}
        # Retry of a frozen existing send includes only its exact returned key, never backlog.
        if isinstance(result, dict) and result.get("key"):
            row = agent.store.row("SELECT id FROM outbox WHERE key=?", (result["key"],))
            if row:
                new_ids.add(int(row["id"]))
        sent = flush_outbox(agent.store, agent.bots, self.cfg, only_ids=new_ids)
        self.journal.sync_chat(int(source["chat_id"]))
        return {
            "result": result,
            "delivery_count": sent,
            "deliveries": [
                dict(row)
                for row in agent.store.rows(
                    "SELECT id,key,status,tg_message_id,purpose FROM outbox WHERE id IN ("
                    + ",".join("?" for _ in new_ids)
                    + ")",
                    tuple(new_ids),
                )
            ]
            if new_ids
            else [],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=[
            "snapshot",
            "events",
            "watch",
            "register",
            "claim",
            "ack",
            "topic",
            "handoff",
            "case",
            "action",
            "run-worker",
            "history",
            "context",
        ],
    )
    parser.add_argument("--config", default=None)
    parser.add_argument("--json", default=None, help="Command arguments as JSON; do not include credentials")
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--chat", type=int, default=None)
    parser.add_argument("--thread", default=None)
    parser.add_argument("--event-ids", nargs="*", default=None)
    args = parser.parse_args()
    bridge = NativeBridge(load_config(args.config))
    raw = args.json if args.json is not None else (sys.stdin.read() if not sys.stdin.isatty() else "{}")
    data = json.loads(raw or "{}")
    if args.timeout is not None:
        data["seconds"] = args.timeout
    if args.limit is not None:
        data["limit"] = args.limit
    if args.chat is not None:
        data["chat_id"] = args.chat
    if args.thread:
        data["thread_id"] = args.thread
    if args.event_ids is not None:
        data["event_ids"] = args.event_ids
    if args.command == "run-worker":
        from .cli_worker import run_worker

        result = run_worker(args.config, **data)
    else:
        result = getattr(bridge, args.command)(**data)
    from .redact import scrub

    print(scrub(bridge.cfg, json.dumps(result, ensure_ascii=False, default=str)))
    return 1 if isinstance(result, dict) and result.get("error") else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # HTTP library exceptions may contain token-bearing Telegram URLs.
        # Surface the class only; structured command results carry useful detail.
        print(json.dumps({"error": type(exc).__name__, "detail": "Command failed; state retained"}))
        raise SystemExit(1) from None
