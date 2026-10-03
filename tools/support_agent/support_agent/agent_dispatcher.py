"""Durable, model-routed topic queue for the support agent."""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .llm import extract_json

log = logging.getLogger(__name__)


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

    def accept(self, m: Any) -> None:
        """Persist event and its queue membership before releasing the source row."""
        if m["role"] == "owner" and not self.agent._owner(m):
            self.store.set_message(int(m["id"]), status="handled")
            return
        event_id = f"in:{m['id']}:{m['revision'] if 'revision' in m.keys() else 1}"
        with self.store.transaction():
            if not self.store.kv_get(f"agent_event:{event_id}"):
                self.store.kv_set(f"agent_event:{event_id}", {
                    "id": event_id, "kind": "input", "source_id": int(m["id"]),
                    "revision": int(m["revision"] if "revision" in m.keys() else 1),
                    "chat_id": int(m["chat_id"]), "owner": self.agent._owner(m),
                    "text": str(m["text"]), "ts": float(m["ts"]),
                })
                queue = list(self.store.kv_get("agent_dispatch_queue", []))
                queue.append(event_id)
                self.store.kv_set("agent_dispatch_queue", queue)
            self.store.set_message(int(m["id"]), status="routed")

    def emit_internal(self, topic_id: str, kind: str, payload: dict[str, Any]) -> str:
        with self.store.transaction():
            return self._emit_internal_locked(topic_id, kind, payload)

    def _emit_internal_locked(self, topic_id: str, kind: str, payload: dict[str, Any]) -> str:
        # Stable identity is supplied by caller for replayable effects; repeated
        # completion after a crash enters the dispatcher only once.
        identity = str(payload.get("event_key") or f"{topic_id}:{kind}:{payload.get('job_id', '')}")
        import hashlib

        event_id = "internal:" + hashlib.sha256(identity.encode()).hexdigest()[:20]
        if not self.store.kv_get(f"agent_event:{event_id}"):
            self.store.kv_set(f"agent_event:{event_id}", {
                "id": event_id, "kind": kind, "topic_id": topic_id,
                "payload": payload, "chat_id": self.agent.cfg.telegram.owner_chat_id,
                "owner": False, "ts": self.agent.clock(),
            })
            queue = list(self.store.kv_get("agent_dispatch_queue", []))
            queue.append(event_id)
            self.store.kv_set("agent_dispatch_queue", queue)
        return event_id

    def tick(self) -> None:
        for m in self.store.messages_with_status("new", 500):
            if m["role"] in ("owner", "client", "partner"):
                self.accept(m)
        self._submit_route()
        topic_ids = list(self.store.kv_get("agent_topic_index", []))
        topic_ids.sort(key=lambda tid: -int(self.store.kv_get(f"agent_topic:{tid}", {})
                                            .get("priority", 0)))
        for topic_id in topic_ids:
            topic = self.store.kv_get(f"agent_topic:{topic_id}", {})
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

    def _submit_route(self) -> None:
        with self.lock:
            if self.routing or not self.store.kv_get("agent_dispatch_queue", []):
                return
            self.routing = True

        def run() -> None:
            try:
                self._route_once()
            except Exception:
                log.exception("agent dispatcher turn failed; queue retained")
            finally:
                with self.lock:
                    self.routing = False

        self.router.submit(run)

    def _route_once(self) -> None:
        ids = list(self.store.kv_get("agent_dispatch_queue", []))
        events = [self.store.kv_get(f"agent_event:{eid}", {}) for eid in ids]
        events = [e for e in events if e]
        if not events:
            return
        events.sort(key=lambda e: (not e.get("owner", False), e.get("ts", 0)))
        events = events[:12]
        topics = [self.store.kv_get(f"agent_topic:{tid}", {})
                  for tid in self.store.kv_get("agent_topic_index", [])[-80:]]
        compact = [{k: t.get(k) for k in ("id", "chat_id", "summary", "next_action",
                                          "status", "priority", "task_ids", "affected_areas",
                                          "related_topic_ids")}
                   for t in topics if t]
        prompt = json.dumps({"current_time": self.agent._local_now(), "events": events,
                             "topics": compact,
            "instruction": "Route each event semantically to one or several independent "
                             "topics. Return JSON {routes:[{event_id,topics:[{topic_id,subrequest,"
                             "priority}],owner_reply?}]}. New topic_id is 'topic-' plus source numeric id "
                             "and optional '-N' for several tasks in one owner message. Explicit owner "
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
            index = list(self.store.kv_get("agent_topic_index", []))
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
                if not isinstance(parts, list) or len(parts) > 8:
                    raise ValueError("invalid topic routes")
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
                    elif topic_id not in index and topic_id not in (
                        f"topic-{event['source_id']}", f"topic-{event['source_id']}-{position + 1}"
                    ):
                        raise ValueError("invalid new topic id")
                    topic = self.store.kv_get(f"agent_topic:{topic_id}", {})
                    if topic and event["kind"] == "input" \
                            and int(topic.get("chat_id", 0)) != int(event["chat_id"]):
                        raise ValueError("event crossed chat boundary")
                    if not topic:
                        topic = {"id": topic_id, "chat_id": event["chat_id"], "summary": "",
                                 "next_action": "", "status": "queued", "priority": 0,
                                 "pending": [], "generation": 0, "task_ids": [],
                                 "affected_areas": []}
                        index.append(topic_id)
                    routed_id = f"{event['id']}:part{position + 1}" if len(parts) > 1 else event["id"]
                    if routed_id != event["id"] and not self.store.kv_get(f"agent_event:{routed_id}"):
                        self.store.kv_set(f"agent_event:{routed_id}", {
                            **event, "id": routed_id, "subrequest": str(part.get("subrequest") or "")[:2000],
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
        event_id = pending[0]
        event = self.store.kv_get(f"agent_event:{event_id}", {})
        if not event:
            return
        if event["kind"] == "input":
            source = self.store.row("SELECT * FROM messages WHERE id=?", (event["source_id"],))
            if source is None or int(source["revision"]) != int(event["revision"]):
                # An edit supersedes this revision; newer revision is separately routed.
                self._finish_event(topic_id, event_id, {"summary": topic.get("summary", "")})
                return
        elif event["kind"] == "recheck" and topic.get("last_source_id"):
            source = self.store.row("SELECT * FROM messages WHERE id=?",
                                    (topic["last_source_id"],))
        else:
            source = None
        result = self.agent.run_topic_turn(topic, event, source)
        self._finish_event(topic_id, event_id, result)

    def _finish_event(self, topic_id: str, event_id: str, result: dict[str, Any]) -> None:
        with self.store.transaction():
            topic = self.store.kv_get(f"agent_topic:{topic_id}", {})
            if topic.get("cancel_requested"):
                topic["status"] = "cancel_requested"
                topic["last_result"] = "Interrupted; external outcome unknown until inspected"
                self.store.kv_set(f"agent_topic:{topic_id}", topic)
                return
            topic["pending"] = [x for x in topic.get("pending", []) if x != event_id]
            for field in ("summary", "next_action", "wake_at", "task_ids", "affected_areas"):
                if field in result:
                    topic[field] = result[field]
            topic["last_result"] = result.get("result", "")
            topic["status"] = "queued" if topic["pending"] else "waiting"
            self.store.kv_set(f"agent_topic:{topic_id}", topic)
            self.store.kv_set(f"agent_event_done:{event_id}", True)
            self._emit_internal_locked(topic_id, "worker_done", {
                "event_key": f"done:{event_id}",
                "source_event": event_id, "summary": topic.get("summary", ""),
                "text": result.get("result", "")[:2500],
                "answer_queued": bool(result.get("answer_queued")),
                "affected_areas": topic.get("affected_areas", []),
                "task_ids": topic.get("task_ids", []),
            })
            event = self.store.kv_get(f"agent_event:{event_id}", {})
            if event.get("kind") == "input":
                source = self.store.row("SELECT revision FROM messages WHERE id=?",
                                        (event["source_id"],))
                if source and int(source["revision"]) == int(event["revision"]):
                    self.store.set_message(event["source_id"], status="handled")

    def recover_after_restart(self) -> None:
        # Queue and topic pending lists already live in SQLite; old in-progress
        # topic turn has unknown effects and resumes with the same source IDs.
        self.tick()
