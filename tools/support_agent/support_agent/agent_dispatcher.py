"""Durable, model-routed topic queue for the support agent."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .llm import extract_json

log = logging.getLogger(__name__)

_ROUTE_RETRY_DELAYS = (5, 30, 300, 600)
_REALTIME_VERSION = 1


def _priority(value: Any) -> int:
    """Normalize model formatting of scheduling metadata, not message meaning."""
    if isinstance(value, str):
        named = {"low": 2, "normal": 5, "medium": 5, "high": 8, "urgent": 10}
        if value.lower() in named:
            return named[value.lower()]
    try:
        return max(0, min(10, int(value)))
    except (TypeError, ValueError):
        return 5


def _safe_new_topic_id(topic_id: str, source_id: int) -> bool:
    """Accept only topics owned by this source, independent of list position."""
    base = f"topic-{source_id}"
    if topic_id == base:
        return True
    prefix = f"{base}-"
    if not topic_id.startswith(prefix):
        return False
    suffix = topic_id[len(prefix):]
    return suffix.isdigit() and suffix == str(int(suffix)) and 1 <= int(suffix) <= 8


def _safe_new_topic_for_batch(topic_id: str, event: dict[str, Any],
                              events: list[dict[str, Any]]) -> bool:
    """Allow a shared new topic only when its anchor is in the same-chat input batch."""
    if _safe_new_topic_id(topic_id, int(event["source_id"])):
        return True
    return any(
        candidate.get("kind") == "input"
        and int(candidate.get("chat_id", 0)) == int(event.get("chat_id", 0))
        and _safe_new_topic_id(topic_id, int(candidate["source_id"]))
        for candidate in events
    )


class AgentDispatcher:
    def __init__(self, coordinator: Any) -> None:
        self.agent = coordinator
        self.store = coordinator.store
        self.lock = threading.RLock()
        self.router = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent-dispatch")
        self.workers = ThreadPoolExecutor(max_workers=max(1, coordinator.cfg.limits.max_parallel),
                                          thread_name_prefix="agent-topic")
        self.worker_limit = max(1, coordinator.cfg.limits.max_parallel)
        self.routing = False
        self.active: set[str] = set()

    def accept(self, m: Any, *, topic_id_override: str | None = None) -> None:
        """Persist event and its queue membership before releasing the source row."""
        if m["role"] == "owner" and not self.agent._owner(m):
            self.store.set_message(int(m["id"]), status="handled")
            return
        if m["role"] not in ("owner", "client", "partner"):
            self.store.set_message(int(m["id"]), status="handled")
            return
        revision = int(m["revision"] if "revision" in m.keys() else 1)
        event_id = f"in:{m['id']}:{revision}"
        visible = bool(self.agent.cfg.agent.visible_moderator)
        existing_event = self.store.kv_get(f"agent_event:{event_id}", {}) if visible else {}
        if existing_event and self.store.kv_get(f"agent_event_done:{event_id}"):
            self.store.set_message(int(m["id"]), status="handled")
            return
        linked_topic = topic_id_override if visible else None
        if visible and linked_topic is None and m["role"] == "owner" and self.agent._owner(m):
            linked_topic = self.agent.case_journal.find_topic(m["reply_to"])
            if linked_topic is None and m["reply_to"]:
                linked_topic = self.store.kv_get(
                    f"case_reply_topic:{m['chat_id']}:{m['reply_to']}")
                if linked_topic is None:
                    outbox = self.store.outbox_by_tg(int(m["chat_id"]), str(m["reply_to"]))
                    if outbox is not None:
                        metadata = self.store.kv_get(
                            f"agent_realtime_outbox:{outbox['key']}", {})
                        linked_topic = metadata.get("topic_id")
                        if linked_topic is None:
                            native = self.store.kv_get(f"reply_case:{outbox['key']}", {})
                            linked_topic = native.get("topic_id")
        elif visible and linked_topic is None:
            # An explicit reply-to association is stronger than a provisional
            # card created while a voice message is still being transcribed.
            linked_topic = self.find_reply_topic(m)
            if linked_topic is None:
                linked_topic = self.agent.case_journal.find_message_topic(m["id"])
        if visible and linked_topic and m["role"] != "owner":
            linked_card = self.store.kv_get(f"case_card:{linked_topic}", {})
            try:
                linked_chat_id = int(linked_card.get("chat_id", 0))
            except (TypeError, ValueError):
                linked_chat_id = 0
            if linked_chat_id != int(m["chat_id"]):
                linked_topic = None
        card = self.store.kv_get(f"case_card:{linked_topic}", {}) if linked_topic else {}
        case_chat_id = int(card.get("chat_id") or m["chat_id"])
        topic_id = (linked_topic or str(existing_event.get("topic_id") or "")
                    or ("" if visible else f"topic-{int(m['id'])}"))
        event_chat_id = case_chat_id if linked_topic else int(m["chat_id"])
        with self.store.transaction():
            if not self.store.kv_get(f"agent_event:{event_id}"):
                event = {
                    "id": event_id, "kind": "input", "source_id": int(m["id"]),
                    "revision": revision, "chat_id": event_chat_id,
                    "owner": self.agent._owner(m),
                    "text": str(m["text"]), "ts": float(m["ts"]),
                }
                if visible:
                    event.update(source_chat_id=int(m["chat_id"]), topic_id=topic_id,
                                 linked_topic_id=linked_topic,
                                 realtime_version=_REALTIME_VERSION)
                self.store.kv_set(f"agent_event:{event_id}", event)
                queue = list(self.store.kv_get("agent_dispatch_queue", []))
                queue.append(event_id)
                self.store.kv_set("agent_dispatch_queue", queue)
            if visible and topic_id:
                index = list(self.store.kv_get("agent_topic_index", []))
                topic = self.store.kv_get(f"agent_topic:{topic_id}", {})
                if not topic:
                    topic = {"id": topic_id, "chat_id": case_chat_id,
                             "summary": card.get("summary", ""),
                             "next_action": "", "status": "queued", "priority": 5,
                             "pending": [], "generation": 0, "task_ids": [],
                             "affected_areas": [], "realtime_version": _REALTIME_VERSION}
                else:
                    # A card may predate the event dispatcher. Preserve its context but
                    # do not resume any pending work from the legacy queue.
                    if topic.get("realtime_version") != _REALTIME_VERSION:
                        topic["pending"] = []
                        topic["realtime_version"] = _REALTIME_VERSION
                    topic["chat_id"] = case_chat_id
                self.store.kv_set(f"agent_topic:{topic_id}", topic)
                if topic_id not in index:
                    index.append(topic_id)
                    self.store.kv_set("agent_topic_index", index)
            self.store.set_message(int(m["id"]), status="routed")

    def prepare_visible_realtime(self) -> int:
        """Quarantine the legacy queue once and return the first eligible message ID."""
        with self.store.transaction():
            cutover = self.store.kv_get("agent_realtime_cutover_v1")
            if isinstance(cutover, dict):
                baseline = int(cutover.get("baseline_message_id", 0))
            else:
                row = self.store.row("SELECT COALESCE(MAX(id),0) AS id FROM messages")
                baseline = int(row["id"] if row else 0)
                self.store.kv_set("agent_realtime_cutover_v1", {
                    "baseline_message_id": baseline, "at": float(self.agent.clock()),
                })
            queue = list(self.store.kv_get("agent_dispatch_queue", []))
            active: list[str] = []
            quarantined: list[str] = []
            for event_id in queue:
                event = self.store.kv_get(f"agent_event:{event_id}", {})
                if event.get("realtime_version") == _REALTIME_VERSION:
                    active.append(str(event_id))
                else:
                    quarantined.append(str(event_id))
            if quarantined:
                previous = list(self.store.kv_get("agent_dispatch_quarantined_v1", []))
                self.store.kv_set("agent_dispatch_quarantined_v1",
                                  list(dict.fromkeys(previous + quarantined))[-5000:])
            self.store.kv_set("agent_dispatch_queue", active)
        return baseline

    def recover_visible_realtime(self) -> None:
        """Resume only versioned events or an exact already-carded interrupted event."""
        rows = self.store.rows("SELECT * FROM messages WHERE status IN ('new','transcribing') "
                               "ORDER BY id")
        for message in rows:
            revision = int(message["revision"])
            received = self.store.kv_get(f"agent_realtime_received_v1:{message['id']}:{revision}")
            event_key = f"in:{message['id']}:{revision}"
            event = self.store.kv_get(f"agent_event:{event_key}", {})
            card_topic = self.agent.case_journal.find_realtime_event_topic(event_key)
            if (not received and event.get("realtime_version") != _REALTIME_VERSION
                    and not card_topic):
                continue
            if message["status"] == "transcribing":
                self._update_case_card(message, event_key, card_topic or f"topic-{message['id']}",
                                       False, waiting_for_transcript=True)
                continue
            self.accept(message, topic_id_override=card_topic)

    def recover_visible_card_projections(self) -> None:
        """Apply durable analysis results to their cards after interrupted Telegram edits."""
        rows = self.store.rows(
            "SELECT key,value FROM kv WHERE key LIKE 'agent_realtime_card_projection:%' "
            "ORDER BY key"
        )
        for row in rows:
            try:
                projection = json.loads(row["value"])
            except (TypeError, ValueError):
                log.warning("invalid realtime card projection: %s", row["key"])
                continue
            if projection.get("realtime_version") != _REALTIME_VERSION or projection.get("reported"):
                continue
            event_id = str(projection.get("event_id") or "")
            topic_id = str(projection.get("topic_id") or "")
            if not event_id or not topic_id:
                continue
            source = self.store.row("SELECT * FROM messages WHERE id=?",
                                    (projection.get("source_id"),))
            if (source is None
                    or int(source["revision"]) != int(projection.get("revision", 0))):
                projection["reported"] = True
                projection["superseded"] = True
                self.store.kv_set(str(row["key"]), projection)
                continue
            card = self.store.kv_get(f"case_card:{topic_id}", {})
            event = self.store.kv_get(f"agent_event:{event_id}", {})
            if (event.get("realtime_version") != _REALTIME_VERSION
                    or event.get("kind") != "input"):
                continue
            if not card and source["role"] != "owner":
                self._update_case_card(source, event_id, topic_id, False)
                card = self.store.kv_get(f"case_card:{topic_id}", {})
            if not card:
                continue
            updated = self._update_case_card_after_turn(
                topic_id, event, source, projection.get("result") or {})
            current = self.store.kv_get(f"case_card:{topic_id}", updated)
            body = self.agent.case_journal.render(current)
            projection_delivered = bool(current.get("message_id")
                                        and current.get("last_text") == body)
            projection_terminal = (not current.get("message_id")
                                   and current.get("delivery") in {"unknown", "rejected"})
            if not (projection_delivered or projection_terminal):
                continue
            projection["reported"] = True
            projection["reported_at"] = float(self.agent.clock())
            self.store.kv_set(str(row["key"]), projection)

    def _update_case_card(self, message: Any, event_id: str, topic_id: str,
                          linked_owner_reply: bool, *, waiting_for_transcript: bool = False) -> None:
        if (not topic_id or waiting_for_transcript or message["status"] == "transcribing"
                or not self.store.kv_get(f"agent_topic:{topic_id}")):
            return
        if message["role"] == "owner" and not linked_owner_reply:
            return
        chat_id = int(message["chat_id"])
        card = self.store.kv_get(f"case_card:{topic_id}", {})
        if linked_owner_reply:
            chat_id = int(card.get("chat_id") or chat_id)
            text = str(message["text"] or message["caption"] or "").strip()
            event_key = f"owner:{event_id}"
            self.agent.case_journal.update_card(
                self.agent.pipe.bots.owner, self.agent.cfg.telegram.owner_chat_id,
                topic_id, chat_id,
                event=("Указание владельца: " + text)[:1400], event_key=event_key,
                statuses={"queued": True}, event_timestamp=float(message["ts"]),
            )
            return
        text = str(message["text"] or message["caption"] or "").strip()
        if not text:
            text = f"Получено вложение: {message['kind']}"
        same_source_has_history = any(
            str(event.get("key") or "").startswith(f"in:{message['id']}:")
            for event in card.get("events", [])
        )
        topic = self.store.kv_get(f"agent_topic:{topic_id}", {})
        essence = str(topic.get("summary") or text).strip()
        title = " ".join(essence.split())[:110]
        summary = {"essence": essence[:1500]}
        if card and not same_source_has_history:
            title = str(card.get("title") or title)
            existing_summary = card.get("summary")
            if isinstance(existing_summary, dict) and existing_summary:
                summary = existing_summary
        binding = self.store.binding(chat_id)
        chat_title = (str(binding["chat_title"]) if binding and binding["chat_title"]
                      else str(self.store.kv_get(f"chat_title:{chat_id}", "") or chat_id))
        self.agent.case_journal.update_card(
            self.agent.pipe.bots.owner, self.agent.cfg.telegram.owner_chat_id,
            topic_id, chat_id, title=title, summary=summary,
            statuses={"queued": True},
            event=("Получено сообщение: " + text[:1000]),
            event_key=event_id, chat_title=chat_title, event_timestamp=float(message["ts"]),
        )

    def find_reply_topic(self, message: Any) -> str | None:
        """Resolve an explicit reply-to target to its existing case, if any."""
        reply_to = str(message["reply_to"] or "")
        if not reply_to:
            return None
        chat_id = int(message["chat_id"])
        linked_topic: str | None = None
        replied_input = self.store.row(
            "SELECT id FROM messages WHERE chat_id=? AND msg_id=?",
            (chat_id, reply_to),
        )
        if replied_input is not None:
            linked_topic = self.agent.case_journal.find_message_topic(int(replied_input["id"]))
        if linked_topic is None:
            linked_topic = self.store.kv_get(f"case_reply_topic:{chat_id}:{reply_to}")
        if linked_topic is None:
            outbox = self.store.outbox_by_tg(chat_id, reply_to)
            if outbox is not None:
                metadata = self.store.kv_get(f"agent_realtime_outbox:{outbox['key']}", {})
                linked_topic = metadata.get("topic_id")
                if linked_topic is None:
                    native = self.store.kv_get(f"reply_case:{outbox['key']}", {})
                    linked_topic = native.get("topic_id")
        if linked_topic is None:
            return None
        card = self.store.kv_get(f"case_card:{linked_topic}", {})
        try:
            if int(card.get("chat_id", 0)) != chat_id:
                return None
        except (TypeError, ValueError):
            return None
        return str(linked_topic)

    def emit_internal(self, topic_id: str, kind: str, payload: dict[str, Any]) -> str:
        with self.store.transaction():
            return self._emit_internal_locked(topic_id, kind, payload)

    def _emit_internal_locked(self, topic_id: str, kind: str, payload: dict[str, Any]) -> str:
        # Stable identity is supplied by caller for replayable effects; repeated
        # completion after a crash enters the dispatcher only once.
        identity = str(payload.get("event_key") or f"{topic_id}:{kind}:{payload.get('job_id', '')}")
        event_id = "internal:" + hashlib.sha256(identity.encode()).hexdigest()[:20]
        if not self.store.kv_get(f"agent_event:{event_id}"):
            self.store.kv_set(f"agent_event:{event_id}", {
                "id": event_id, "kind": kind, "topic_id": topic_id,
                "payload": payload, "chat_id": self.agent.cfg.telegram.owner_chat_id,
                "owner": False, "ts": self.agent.clock(),
                **({"realtime_version": _REALTIME_VERSION}
                   if self.agent.cfg.agent.visible_moderator else {}),
            })
            queue = list(self.store.kv_get("agent_dispatch_queue", []))
            queue.append(event_id)
            self.store.kv_set("agent_dispatch_queue", queue)
        return event_id

    def tick(self) -> None:
        if self.agent.cfg.agent.visible_moderator:
            self._route_visible_queue()
        else:
            for m in self.store.messages_with_status("new", 500):
                if m["role"] in ("owner", "client", "partner"):
                    self.accept(m)
            self._submit_route()
        topic_ids = list(self.store.kv_get("agent_topic_index", []))
        topic_ids.sort(key=lambda tid: -int(self.store.kv_get(f"agent_topic:{tid}", {})
                                            .get("priority", 0)))
        for topic_id in topic_ids:
            topic = self.store.kv_get(f"agent_topic:{topic_id}", {})
            if (self.agent.cfg.agent.visible_moderator
                    and topic.get("realtime_version") != _REALTIME_VERSION):
                continue
            if (topic.get("pending") and not topic.get("cancel_requested")
                    and topic_id not in self.active):
                if len(self.active) < self.worker_limit:
                    self._submit_topic(topic_id)
            elif (topic.get("wake_at") and topic.get("status") == "waiting"
                  and float(topic["wake_at"]) <= self.agent.clock()):
                with self.store.transaction():
                    current = self.store.kv_get(f"agent_topic:{topic_id}", {})
                    if current.get("wake_at") and current.get("status") == "waiting" \
                            and float(current["wake_at"]) <= self.agent.clock():
                        self._emit_internal_locked(topic_id, "recheck", {
                            "event_key": f"recheck:{topic_id}:{current['wake_at']}",
                            "reason": current.get("next_action", ""),
                        })
                        current["wake_at"] = None
                        self.store.kv_set(f"agent_topic:{topic_id}", current)

    def _route_visible_queue(self) -> None:
        """Classify the conversation before creating or updating a case."""
        with self.store.transaction():
            current = list(self.store.kv_get("agent_dispatch_queue", []))
            active, legacy = [], []
            for event_id in current:
                event = self.store.kv_get(f"agent_event:{event_id}", {})
                (active if event.get("realtime_version") == _REALTIME_VERSION else legacy).append(event_id)
            if legacy:
                previous = list(self.store.kv_get("agent_dispatch_quarantined_v1", []))
                self.store.kv_set("agent_dispatch_quarantined_v1",
                                  list(dict.fromkeys(previous + legacy))[-5000:])
            self.store.kv_set("agent_dispatch_queue", active)
        self._submit_route()

    def _submit_route(self) -> None:
        with self.lock:
            if (self.routing or not self.store.kv_get("agent_dispatch_queue", [])
                    or not self._route_retry_ready()):
                return
            self.routing = True

        def run() -> None:
            try:
                self._route_once()
            except Exception as exc:
                self._record_route_failure(exc)
                log.exception("agent dispatcher turn failed; queue retained")
            finally:
                with self.lock:
                    self.routing = False

        self.router.submit(run)

    def _queued_events(self) -> list[dict[str, Any]]:
        ids = list(self.store.kv_get("agent_dispatch_queue", []))
        events = [self.store.kv_get(f"agent_event:{event_id}", {}) for event_id in ids]
        events = [event for event in events if event]
        events.sort(key=lambda event: (not event.get("owner", False), event.get("ts", 0)))
        return events[:12]

    def _route_signature(self, events: list[dict[str, Any]]) -> str:
        # The oldest selected event is the one that keeps the queue blocked. New
        # arrivals must not reset its backoff and recreate a tight retry loop.
        head = str(events[0].get("id") or "") if events else ""
        return hashlib.sha256(head.encode()).hexdigest()[:20] if head else ""

    def _route_retry_ready(self) -> bool:
        retry = self.store.kv_get("agent_dispatch_retry")
        if not isinstance(retry, dict):
            return True
        events = self._queued_events()
        if not events or retry.get("signature") != self._route_signature(events):
            return True
        return float(retry.get("next_at") or 0) <= float(self.agent.clock())

    def _record_route_failure(self, exc: Exception) -> None:
        events = self._queued_events()
        if not events:
            return
        signature = self._route_signature(events)
        event_ids = [str(event.get("id") or "") for event in events]
        with self.store.transaction():
            previous = self.store.kv_get("agent_dispatch_retry", {})
            attempts = int(previous.get("attempts", 0)) + 1 \
                if previous.get("signature") == signature else 1
            delay = _ROUTE_RETRY_DELAYS[min(attempts - 1, len(_ROUTE_RETRY_DELAYS) - 1)]
            retry = {
                "signature": signature,
                "attempts": attempts,
                "next_at": float(self.agent.clock()) + delay,
                "event_ids": event_ids,
                "last_error": f"{type(exc).__name__}: {exc}"[:1000],
                "updated_at": float(self.agent.clock()),
            }
            self.store.kv_set("agent_dispatch_retry", retry)
            if attempts == 3:
                self.store.queue_message(
                    key=f"agent_dispatch_failure:{signature}",
                    chat_id=self.agent.cfg.telegram.owner_chat_id,
                    text=("Маршрутизатор трижды не смог разобрать сохранённые сообщения. "
                          "Очередь не потеряна; автоматические повторы замедлены минимум "
                          "до пяти минут, требуется проверка диспетчера."),
                    purpose="agent_dispatch_failure",
                    repeat_ok=False,
                )
        log.warning("agent dispatcher retry %s delayed for %s seconds", attempts, delay)

    def _route_once(self) -> None:
        events = self._queued_events()
        if not events:
            return
        visible = bool(self.agent.cfg.agent.visible_moderator)
        chat_ids = {int(e["chat_id"]) for e in events}
        cards = [json.loads(row["value"]) for row in self.store.rows(
            "SELECT value FROM kv WHERE key LIKE 'case_card:%'")
            if int(json.loads(row["value"]).get("chat_id", 0)) in chat_ids]
        topic_ids = list(self.store.kv_get("agent_topic_index", []))
        topics = [self.store.kv_get(f"agent_topic:{tid}", {}) for tid in topic_ids]
        compact = [{k: t.get(k) for k in ("id", "chat_id", "summary", "next_action",
                    "status", "priority", "task_ids", "affected_areas", "related_topic_ids")}
                   for t in topics if t and int(t.get("chat_id", 0)) in chat_ids]
        known = {str(t["id"]) for t in compact}
        for card in cards:
            if str(card["topic_id"]) not in known:
                compact.append({"id": str(card["topic_id"]), "chat_id": card["chat_id"],
                                "summary": card.get("summary"), "status": card.get("current_status")})
        conversations = [self.agent._snapshot(cid, cid == self.agent.cfg.telegram.owner_chat_id)
                         for cid in sorted(chat_ids)]
        prompt = json.dumps({"current_time": self.agent._local_now(), "events": events,
                             "topics": compact, "conversations": conversations,
            "instruction": "Read the complete recent conversation and all existing cases first. "
                             "A message is not a case. Continue an existing case when the user adds "
                             "requirements, an attachment, an observation or a correction about the same "
                             "process. New cases are only independent actionable requests. Social replies, "
                             "call scheduling, meeting links, thanks and reminders alone return topics:[]. "
                             "Use the existing case id even without reply_to. Explicit linked_topic_id "
                             "is authoritative. Group same-topic messages from this batch together. "
                             "The subrequest describes the accumulated business request in plain Russian, "
                             "not the literal latest message. Route each event semantically to independent "
                             "topics. Return JSON {routes:[{event_id,topics:[{topic_id,subrequest,"
                             "priority}],owner_reply?}]}. New topic_id is 'topic-' plus source numeric id "
                             "and optional '-N' for several tasks in one owner message. Several input "
                             "events from the same chat may share one new topic anchored to any of those "
                             "same-batch events. Explicit owner "
                             "control can include controls:[{action:'set_priority'|'cancel_topic'|"
                             "'cancel_job',target,value?}]. Internal events "
                             "retain their topic_id. Owner_reply is a short immediate truthful response "
                             "to an owner message, never an approval or completion claim. Same client chat "
                             "may have several topics. An owner may reference a client topic in a new "
                             "owner topic via related_topic_ids, but owner and client never share the "
                             "same topic/session. Every topic keeps its original chat. Do not investigate "
                             "project code or perform actions. "
                             "For worker_progress, worker_done or job_done, compare related topics and "
                             "provide owner_reply only for a meaningful new update; no further worker "
                             "turn is needed for worker_progress/worker_done. If answer_queued is true, "
                             "do not repeat the worker answer. Keep this turn short."},
                             ensure_ascii=False)
        result = self.agent.llm.agent_turn(
            prompt, session_key="agent:dispatcher", model=self.agent.cfg.agent.owner_model,
            provider=self.agent.cfg.agent.owner_provider, system=self.agent.system,
            mode="readonly", cwd=str(self.agent.repo), timeout=60,
            effort="medium", include_project_tools=False,
        )
        parsed = extract_json(result.text)
        routes = parsed.get("routes") if isinstance(parsed, dict) else None
        if not isinstance(routes, list):
            raise ValueError("dispatcher returned no routes")
        mapping = {str(r.get("event_id")): r for r in routes if isinstance(r, dict)}
        if set(mapping) != {e["id"] for e in events}:
            raise ValueError("dispatcher omitted or invented events")
        controls: list[dict[str, Any]] = []
        for event in events:
            for control in mapping[event["id"]].get("controls", []):
                if not isinstance(control, dict) or not event.get("owner") \
                        or event["kind"] != "input" \
                        or control.get("action") not in ("set_priority", "cancel_topic", "cancel_job"):
                    raise ValueError("invalid or untrusted control")
                source = self.store.row("SELECT * FROM messages WHERE id=?", (event["source_id"],))
                if source is None or int(source["revision"]) != int(event["revision"]):
                    raise ValueError("edited control source")
                if self.agent.semantic_verifier.check(source, str(control["action"]),
                                                      control)["authorized"]:
                    controls.append(control)
        with self.store.transaction():
            index = list(dict.fromkeys(list(self.store.kv_get("agent_topic_index", []))
                                      + [str(c["topic_id"]) for c in cards]))
            for event in events:
                route = mapping[event["id"]]
                if event["kind"] in ("worker_progress", "worker_done", "job_done"):
                    # Completion is consumed by the one moderator; feeding it
                    # back into the same worker would create a completion loop.
                    immediate = str(route.get("owner_reply") or "").strip()
                    if immediate:
                        self.store.queue_message(
                            key=f"agent_moderator:{event['id']}",
                            chat_id=self.agent.cfg.telegram.owner_chat_id,
                            text=immediate[:2500], purpose="agent_moderator",
                            repeat_ok=False,
                        )
                    continue
                parts = route.get("topics")
                if visible and event.get("linked_topic_id"):
                    parts = [{"topic_id": str(event["linked_topic_id"]),
                              "subrequest": str(event.get("text") or ""), "priority": 5}]
                if not isinstance(parts, list) or len(parts) > 8:
                    raise ValueError("invalid topic routes")
                split_ids = ([f"{event['id']}:part{position + 1}"
                              for position in range(len(parts))]
                             if len(parts) > 1 else [])
                if split_ids:
                    self.store.kv_set(f"agent_split_group:{event['id']}", {
                        "source_event": event["id"], "part_ids": split_ids,
                        "results": {}, "complete": False,
                    })
                if not parts:
                    if event["kind"] == "input":
                        current = self.store.row("SELECT revision FROM messages WHERE id=?",
                                                 (event["source_id"],))
                        if current and int(current["revision"]) == int(event["revision"]):
                            self.store.set_message(event["source_id"], status="handled")
                    self.store.kv_set(f"agent_event_done:{event['id']}", True)
                for position, part in enumerate(parts):
                    topic_id = str(part.get("topic_id") or "")
                    if event["kind"] != "input":
                        if topic_id != event.get("topic_id") or len(parts) != 1:
                            raise ValueError("internal event changed topic")
                    elif topic_id not in index and not _safe_new_topic_for_batch(
                            topic_id, event, events):
                        raise ValueError(
                            f"invalid new topic id {topic_id!r} for event {event['id']!r}"
                        )
                    topic = self.store.kv_get(f"agent_topic:{topic_id}", {})
                    known_card = self.store.kv_get(f"case_card:{topic_id}", {})
                    if known_card and int(known_card.get("chat_id", 0)) != int(event["chat_id"]):
                        raise ValueError("event crossed case chat boundary")
                    if topic and event["kind"] == "input" \
                            and int(topic.get("chat_id", 0)) != int(event["chat_id"]):
                        raise ValueError("event crossed chat boundary")
                    if not topic:
                        topic = {"id": topic_id, "chat_id": event["chat_id"], "summary": "",
                                 "next_action": "", "status": "queued", "priority": 0,
                                 "pending": [], "generation": 0, "task_ids": [],
                                 "affected_areas": []}
                        if topic_id not in index:
                            index.append(topic_id)
                    if visible:
                        if topic.get("realtime_version") != _REALTIME_VERSION:
                            topic["pending"] = []
                        topic["realtime_version"] = _REALTIME_VERSION
                        if not topic.get("summary"):
                            existing_card = self.store.kv_get(f"case_card:{topic_id}", {})
                            topic["summary"] = (existing_card.get("summary")
                                                or str(part.get("subrequest") or event.get("text") or ""))
                    routed_id = f"{event['id']}:part{position + 1}" if len(parts) > 1 else event["id"]
                    if routed_id != event["id"] and not self.store.kv_get(f"agent_event:{routed_id}"):
                        self.store.kv_set(f"agent_event:{routed_id}", {
                            **event, "id": routed_id, "parent_event_id": event["id"],
                            "subrequest": str(part.get("subrequest") or "")[:2000],
                        })
                    if routed_id not in topic["pending"]:
                        topic["pending"].append(routed_id)
                        topic["generation"] += 1
                    if event["kind"] == "input":
                        topic["last_source_id"] = event["source_id"]
                    topic["priority"] = _priority(part.get("priority"))
                    related = part.get("related_topic_ids") or []
                    if isinstance(related, list):
                        topic["related_topic_ids"] = [str(x) for x in related if str(x) in index][:20]
                    topic["status"] = "queued"
                    self.store.kv_set(f"agent_topic:{topic_id}", topic)
                if (event.get("owner") and event["kind"] == "input") or event["kind"] == "job_done":
                    immediate = str(route.get("owner_reply") or "").strip()
                    if immediate:
                        self.store.queue_message(
                            key=f"agent_dispatch_reply:{event['id']}", chat_id=int(event["chat_id"]),
                            text=immediate[:1500], reply_to=str(self.store.row(
                                "SELECT msg_id FROM messages WHERE id=?", (event["source_id"],))["msg_id"]),
                            purpose="agent_dispatch_reply", repeat_ok=False,
                        )
            self.store.kv_set("agent_topic_index", index)
            for control in controls:
                action, target = str(control["action"]), str(control.get("target") or "")
                if action in ("set_priority", "cancel_topic") and target in index:
                    selected = self.store.kv_get(f"agent_topic:{target}", {})
                    if action == "set_priority":
                        selected["priority"] = _priority(control.get("value"))
                    else:
                        selected["status"] = "cancel_requested"
                        selected["cancel_requested"] = True
                        selected["recovery_note"] = "Inspect unknown effects before resuming"
                        for job_id in self.store.kv_get("agent_job_index", []):
                            job = self.store.kv_get(f"agent_job:{job_id}", {})
                            if job.get("topic_id") != target or job.get("status") in (
                                "done", "cancelled", "needs_review", "needs_owner_review"
                            ):
                                continue
                            job["cancel_requested"] = True
                            if job.get("status") in ("scheduled", "queued"):
                                job["status"] = "cancelled"
                            self.store.kv_set(f"agent_job:{job_id}", job)
                    self.store.kv_set(f"agent_topic:{target}", selected)
                elif action == "cancel_job":
                    job = self.store.kv_get(f"agent_job:{target}", {})
                    if job:
                        job["cancel_requested"] = True
                        if job.get("status") in ("scheduled", "queued"):
                            job["status"] = "cancelled"
                        self.store.kv_set(f"agent_job:{target}", job)
            remaining = [eid for eid in self.store.kv_get("agent_dispatch_queue", [])
                         if eid not in mapping]
            self.store.kv_set("agent_dispatch_queue", remaining)
            self.store.execute("DELETE FROM kv WHERE key='agent_dispatch_retry'")
        if visible:
            for event in events:
                if event.get("kind") != "input":
                    continue
                source = self.store.row("SELECT * FROM messages WHERE id=?", (event["source_id"],))
                if source is None:
                    continue
                parts = ([{"topic_id": event["linked_topic_id"]}] if event.get("linked_topic_id")
                         else mapping[event["id"]].get("topics", []))
                for part in parts:
                    self._update_case_card(source, event["id"], str(part["topic_id"]),
                                           bool(event.get("owner") and event.get("linked_topic_id")))

    def _submit_topic(self, topic_id: str) -> None:
        with self.lock:
            if topic_id in self.active or len(self.active) >= self.worker_limit:
                return
            self.active.add(topic_id)

        def run() -> None:
            try:
                self._work_topic(topic_id)
            except Exception:
                log.exception("agent topic %s failed; source retained", topic_id)
            finally:
                with self.lock:
                    self.active.discard(topic_id)

        self.workers.submit(run)

    def _work_topic(self, topic_id: str) -> None:
        topic = self.store.kv_get(f"agent_topic:{topic_id}", {})
        if topic.get("cancel_requested"):
            return
        pending = topic.get("pending") or []
        if not pending:
            return
        batch = [self.store.kv_get(f"agent_event:{eid}", {}) for eid in pending]
        coalesced = (len(batch) > 1 and all(e.get("kind") == "input" and not e.get("owner")
                     and not e.get("parent_event_id") for e in batch))
        event_id = pending[-1] if coalesced else pending[0]
        event = dict(self.store.kv_get(f"agent_event:{event_id}", {}))
        if coalesced:
            event["conversation_updates"] = [{k: e.get(k) for k in
                ("id", "source_id", "revision", "text", "ts")} for e in batch]
            event["coalesced_event_ids"] = list(pending)
            self.store.kv_set(f"agent_event:{event_id}", event)
        if not event:
            return
        if event["kind"] == "input":
            source = self.store.row("SELECT * FROM messages WHERE id=?", (event["source_id"],))
            if source is None or int(source["revision"]) != int(event["revision"]):
                # An edit supersedes this revision; newer revision is separately routed.
                self._finish_event(topic_id, event_id, {"summary": topic.get("summary", "")})
                return
            if self.agent.cfg.agent.visible_moderator:
                self._mark_visible_analysis_started(topic_id, event_id, source)
        elif event["kind"] == "recheck" and topic.get("last_source_id"):
            source = self.store.row("SELECT * FROM messages WHERE id=?",
                                    (topic["last_source_id"],))
        else:
            source = None
        result = self.agent.run_topic_turn(topic, event, source)
        self._finish_event(topic_id, event_id, result)

    def _mark_visible_analysis_started(self, topic_id: str, event_id: str,
                                       source: Any) -> None:
        card = self.store.kv_get(f"case_card:{topic_id}", {})
        if not card:
            return
        self.agent.case_journal.update_card(
            self.agent.pipe.bots.owner, self.agent.cfg.telegram.owner_chat_id,
            topic_id, int(card.get("chat_id") or source["chat_id"]),
            statuses={"working": True}, event=None,
            event_key=f"analysis-start:{event_id}", event_timestamp=float(self.agent.clock()),
        )

    def _finish_event(self, topic_id: str, event_id: str, result: dict[str, Any]) -> None:
        event: dict[str, Any] = {}
        with self.store.transaction():
            topic = self.store.kv_get(f"agent_topic:{topic_id}", {})
            if topic.get("cancel_requested"):
                topic["status"] = "cancel_requested"
                topic["last_result"] = "Interrupted; external outcome unknown until inspected"
                self.store.kv_set(f"agent_topic:{topic_id}", topic)
                return
            completed_event = self.store.kv_get(f"agent_event:{event_id}", {})
            completed_ids = set(completed_event.get("coalesced_event_ids") or [event_id])
            for completed_id in completed_ids - {event_id}:
                completed = self.store.kv_get(f"agent_event:{completed_id}", {})
                row = self.store.row("SELECT revision FROM messages WHERE id=?", (completed.get("source_id"),))
                if row and int(row["revision"]) == int(completed.get("revision", 0)):
                    self.store.set_message(int(completed["source_id"]), status="handled")
                self.store.kv_set(f"agent_event_done:{completed_id}", True)
            topic["pending"] = [x for x in topic.get("pending", []) if x not in completed_ids]
            for field in ("summary", "next_action", "wake_at", "task_ids", "affected_areas"):
                if field in result:
                    topic[field] = result[field]
            topic["last_result"] = result.get("result", "")
            topic["status"] = "queued" if topic["pending"] else "waiting"
            self.store.kv_set(f"agent_topic:{topic_id}", topic)
            self.store.kv_set(f"agent_event_done:{event_id}", True)
            event = self.store.kv_get(f"agent_event:{event_id}", {})
            parent_event_id = str(event.get("parent_event_id") or "")
            if parent_event_id:
                group_key = f"agent_split_group:{parent_event_id}"
                group = self.store.kv_get(group_key, {})
                results = dict(group.get("results") or {})
                results[event_id] = {
                    "summary": str(result.get("summary") or topic.get("summary") or "")[:1500],
                    "text": str(result.get("result") or "")[:2500],
                    "affected_areas": topic.get("affected_areas", []),
                    "task_ids": topic.get("task_ids", []),
                }
                group["results"] = results
                part_ids = [str(item) for item in group.get("part_ids") or []]
                complete = bool(part_ids) and all(part_id in results for part_id in part_ids)
                group["complete"] = complete
                self.store.kv_set(group_key, group)
                if complete:
                    ordered = [results[part_id] for part_id in part_ids]
                    texts: list[str] = []
                    for item in ordered:
                        text = str(item.get("text") or "").strip()
                        if text and text not in texts:
                            texts.append(text)
                    if not self.agent.cfg.agent.visible_moderator:
                        self._emit_internal_locked(topic_id, "worker_done", {
                            "event_key": f"split_done:{parent_event_id}",
                            "source_event": parent_event_id,
                            "summary": "\n".join(str(item.get("summary") or "")
                                                  for item in ordered)[:2500],
                            "text": "\n\n".join(texts)[:6000],
                            "answer_queued": False, "split_complete": True,
                            "affected_areas": list(dict.fromkeys(
                                area for item in ordered for area in item.get("affected_areas", [])
                            ))[:50],
                            "task_ids": list(dict.fromkeys(
                                task_id for item in ordered for task_id in item.get("task_ids", [])
                            ))[:50],
                        })
            else:
                if not self.agent.cfg.agent.visible_moderator:
                    self._emit_internal_locked(topic_id, "worker_done", {
                        "event_key": f"done:{event_id}",
                        "source_event": event_id, "summary": topic.get("summary", ""),
                        "text": result.get("result", "")[:2500],
                        "answer_queued": bool(result.get("answer_queued")),
                        "affected_areas": topic.get("affected_areas", []),
                        "task_ids": topic.get("task_ids", []),
                    })
            if event.get("kind") == "input":
                source = self.store.row("SELECT revision FROM messages WHERE id=?",
                                        (event["source_id"],))
                if source and int(source["revision"]) == int(event["revision"]):
                    if self.agent.cfg.agent.visible_moderator:
                        card_result = {key: result[key] for key in
                                       ("summary", "checked", "found", "unknown", "next_action",
                                        "result", "case_update") if key in result}
                        self.store.kv_set(
                            f"agent_realtime_card_projection:{event_id}",
                            {"realtime_version": _REALTIME_VERSION, "event_id": event_id,
                             "topic_id": topic_id, "source_id": int(event["source_id"]),
                             "revision": int(event["revision"]), "result": card_result},
                        )
                    self.store.set_message(event["source_id"], status="handled")
        if self.agent.cfg.agent.visible_moderator and event.get("kind") == "input":
            self.recover_visible_card_projections()

    def _update_case_card_after_turn(self, topic_id: str, event: dict[str, Any],
                                     source: Any, result: dict[str, Any]) -> dict[str, Any]:
        card = self.store.kv_get(f"case_card:{topic_id}", {})
        if not card:
            return {}
        source_text = str(source["text"] or source["caption"] or "").strip()
        checked = str(result.get("checked") or "").strip()
        found = str(result.get("found") or "").strip()
        unknown = str(result.get("unknown") or "").strip()
        next_action = str(result.get("next_action") or "").strip()
        summary = {
            "essence": str(result.get("summary") or source_text or card.get("title") or "Запрос")[:900],
            "checked": (checked[:900] if checked else
                        "Разбор завершён; проверенные действия модель не перечислила"),
            "found": found[:900],
            "unknown": unknown[:900],
            "next_step": next_action[:900],
        }
        event_text = str(result.get("case_update") or "").strip()
        return self.agent.case_journal.update_card(
            self.agent.pipe.bots.owner, self.agent.cfg.telegram.owner_chat_id,
            topic_id, int(card.get("chat_id") or event.get("chat_id") or source["chat_id"]),
            summary=summary, statuses={"analysis_done": True},
            event=event_text[:400] or None, event_key=f"analysis:{event['id']}",
            event_timestamp=float(self.agent.clock()),
        )

    def recover_after_restart(self) -> None:
        # Queue and topic pending lists already live in SQLite; old in-progress
        # topic turn has unknown effects and resumes with the same source IDs.
        self.tick()
