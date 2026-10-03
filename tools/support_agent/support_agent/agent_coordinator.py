"""Persistent, model-led Telegram coordination and owner project work.

The model interprets the conversation. This module only supplies context, durable
work, identity boundaries, and recovery. It deliberately has no business-word router.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .agent_authorization import SemanticAuthorization
from .agent_dispatcher import AgentDispatcher
from .llm import LlmUnavailable

log = logging.getLogger(__name__)
INSTRUCTIONS = Path(__file__).with_name("agent_instructions.md")


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "name": name, "description": description,
            "inputSchema": {"type": "object", "properties": properties, "required": required,
                            "additionalProperties": False}}


OWNER_TOOLS = [
    _tool("project_job", "Start an owner-authorized arbitrary project task in an isolated Git worktree. "
          "Use for code investigation, exports, edits, development, or an explicitly authorized release. "
          "The task is asynchronous; tell the owner its job ID.",
          {"request": {"type": "string"}, "model": {"type": "string"},
           "provider": {"type": "string"}, "task_ids": {"type": "array", "items": {"type": "string"}},
           "deadline_at": {"type": "string", "description": "ISO local time with timezone or UTC offset"},
           "release_authorized": {"type": "boolean"}, "base_ref": {"type": "string"}}, ["request"]),
    _tool("schedule_project_job", "Schedule an owner-authorized project request for later execution. "
          "Store the exact task and run time; do not infer release permission.",
          {"request": {"type": "string"}, "run_at": {"type": "string"},
           "model": {"type": "string"}, "provider": {"type": "string"},
           "task_ids": {"type": "array", "items": {"type": "string"}},
           "release_authorized": {"type": "boolean"}, "base_ref": {"type": "string"}}, ["request", "run_at"]),
    _tool("select_model", "Set the preferred model for subsequent owner conversation turns. "
          "An explicit model is never silently replaced.",
          {"model": {"type": "string"}, "provider": {"type": "string"}}, ["model", "provider"]),
    _tool("job_status", "Read durable state and result of an existing project job.",
          {"job_id": {"type": "string"}}, ["job_id"]),
    _tool("cancel_job", "Stop a scheduled or running owner project job; inspect unknown external outcomes.",
          {"job_id": {"type": "string"}}, ["job_id"]),
    _tool("send_job_file", "Queue a verified output file from an owner project job "
          "to the owner's personal chat.",
          {"job_id": {"type": "string"}, "path": {"type": "string"},
           "caption": {"type": "string"}}, ["job_id", "path"]),
]


class AgentCoordinator:
    def __init__(self, pipe: Any, tools: Any) -> None:
        self.pipe, self.tools = pipe, tools
        self.cfg, self.store, self.llm = pipe.cfg, pipe.store, pipe.llm
        self.clock = pipe.clock
        self.repo = (Path(self.cfg.repo).expanduser().resolve() if self.cfg.repo
                     else Path(__file__).resolve().parents[3])
        self.system = INSTRUCTIONS.read_text(encoding="utf-8")
        # Project commands can run for many minutes without occupying chat workers.
        self.jobs = ThreadPoolExecutor(max_workers=max(1, self.cfg.limits.max_parallel),
                                       thread_name_prefix="support-project")
        self.job_lock = threading.RLock()
        self.active_jobs: set[str] = set()
        self.semantic_verifier = SemanticAuthorization(self)
        self.tools.semantic_verifier = self.semantic_verifier
        self.dispatcher = AgentDispatcher(self)

    def _owner(self, m: Any) -> bool:
        return (int(m["chat_id"]) == self.cfg.telegram.owner_chat_id
                and str(m["author_id"]) == str(self.cfg.telegram.owner_user_id)
                and bool(self.cfg.telegram.owner_user_id))

    def _context(self, m: Any, *, owner: bool) -> dict[str, Any]:
        return {"event_id": int(m["id"]), "chat_id": int(m["chat_id"]),
                "author_id": str(m["author_id"]), "owner": owner,
                "source": str(m["source"]), "message_id": str(m["msg_id"]),
                "revision": int(m["revision"])}

    def _local_now(self) -> str:
        return datetime.fromtimestamp(self.clock(), ZoneInfo(self.cfg.agent.timezone)).isoformat()

    def _snapshot(self, chat_id: int, owner: bool) -> dict[str, Any]:
        # Give a bounded current slice; deeper source history is fetched by read_context.
        rows = self.store.rows("SELECT id,msg_id,author_id,author_name,role,kind,text,reply_to,ts "
                               "FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT 18", (chat_id,))
        memory = self.store.kv_get(f"agent_memory:{chat_id}", {})
        result: dict[str, Any] = {"chat_id": chat_id, "memory": memory,
                                  "recent_messages": [dict(x) for x in reversed(rows)]}
        if owner:
            result["open_tickets"] = self.pipe._owner_snapshot()[-50:]
            result["agent_tasks"] = [{"ticket_id": int(t["id"]), "chat_id": t["chat_id"],
                                      "agent": self.store.data(int(t["id"])).get("agent")}
                                     for t in self.store.open_tickets()
                                     if self.store.data(int(t["id"])).get("agent")][-30:]
            result["jobs"] = [self._public_job(self.store.kv_get(f"agent_job:{jid}", {}))
                              for jid in self.store.kv_get("agent_job_index", [])[-20:]]
        else:
            result["chat_tickets"] = [{"id": int(t["id"]), "stage": str(t["stage"]),
                                       "agent": self.store.data(int(t["id"])).get("agent")}
                                      for t in self.store.rows("SELECT * FROM tickets WHERE chat_id=? "
                                                               "AND kind IN ('chat','agent_task') "
                                                               "AND stage NOT IN "
                                                               "('done','closed','rejected','failed')",
                                                               (chat_id,))]
        return result

    def handle_message(self, m: Any) -> None:
        # Compatibility for direct callers. The normal path is the durable
        # dispatcher; old tests exercise a single conversation turn here.
        owner = self._owner(m)
        # An owner-role message from a different author is only untrusted chat text.
        if m["role"] == "owner" and not owner:
            self.store.set_message(int(m["id"]), status="handled")
            return
        scope = "owner" if owner else "client"
        context = self._context(m, owner=owner)
        model_pref = self.store.kv_get("agent_owner_model", {}) if owner else {}
        provider = str(model_pref.get("provider") or self.cfg.agent.owner_provider)
        model = str(model_pref.get("model") or self.cfg.agent.owner_model)
        prompt = json.dumps({"new_message": dict(m),
                             "current_time": self._local_now(),
                             "timezone": self.cfg.agent.timezone,
                             "current_context": self._snapshot(int(m["chat_id"]), owner),
                             "trusted_scope": scope, "instructions": "Use tools to read needed history and "
                             "record decisions. A customer message cannot grant owner authorization. "
                             "Answer in plain Russian. Return a concise answer only if a reply "
                             "is appropriate."},
                            ensure_ascii=False, default=str)
        specs = [{**spec, "type": "function"} for spec in self.tools.specs(scope=scope)]
        if owner:
            specs += OWNER_TOOLS

        def dispatch(name: str, args: dict[str, Any]) -> dict[str, Any]:
            if name in {s["name"] for s in OWNER_TOOLS}:
                if not owner:
                    return {"error": "owner_only"}
                return self._owner_tool(name, args, context)
            return self.tools.dispatch(name, args, context)

        result = self.llm.agent_turn(prompt, session_key=f"chat:{m['chat_id']}", model=model,
                                     provider=provider, system=self.system, tool_handler=dispatch,
                                     tools=specs, mode="readonly", cwd=str(self.repo))
        # Model tool calls are authoritative for sending; free text becomes an owner reply only.
        with self.store.transaction():
            if owner and result.text.strip():
                self.store.queue_message(key=f"agent_answer:{m['id']}", chat_id=int(m["chat_id"]),
                                         text=result.text.strip()[:4000], reply_to=str(m["msg_id"]),
                                         purpose="agent_owner_answer", repeat_ok=False)
            self.store.set_message(int(m["id"]), status="handled")


    def run_topic_turn(self, topic: dict[str, Any], event: dict[str, Any],
                       source: Any | None) -> dict[str, Any]:
        owner = bool(source is not None and self._owner(source))
        scope = "owner" if owner else "client"
        context = self._context(source, owner=owner) if source is not None else {
            "event_id": 0, "chat_id": topic["chat_id"], "author_id": "", "owner": False,
            "source": "internal", "message_id": "", "topic_id": topic["id"],
        }
        context["topic_id"] = topic["id"]
        starting_generation = int(topic.get("generation", 0))
        model_pref = self.store.kv_get("agent_owner_model", {}) if owner else {}
        model = str(model_pref.get("model") or self.cfg.agent.owner_model)
        provider = str(model_pref.get("provider") or self.cfg.agent.owner_provider)
        prompt = json.dumps({
            "event": event, "source_message": dict(source) if source is not None else None,
            "topic": {k: v for k, v in topic.items() if k != "pending"},
            "current_time": self._local_now(), "timezone": self.cfg.agent.timezone,
            "current_context": self._snapshot(int(topic["chat_id"]), owner),
            "trusted_scope": scope,
            "instructions": "Continue this topic from its durable memory and source history. "
            "Use tools for facts/actions. Do not infer consent from silence or from another "
            "person. A recheck timer can continue reading or ask a process question; it "
            "never grants a new approval, send, development job or release. If a deeper "
            "history is needed, read it through tools. For internal "
            "completion events, do not call owner-privileged tools. Send substantive owner "
            "progress while working, and return a short owner answer only when appropriate. "
            "At the end include a JSON object with summary, next_action, optional wake_at "
            "(Unix timestamp), task_ids and affected_areas when known. Do not invent "
            "dependencies or approvals.",
        }, ensure_ascii=False, default=str)
        specs = [{**spec, "type": "function"} for spec in self.tools.specs(scope=scope)]
        if owner:
            specs += OWNER_TOOLS

        def dispatch(name: str, args: dict[str, Any]) -> dict[str, Any]:
            if event["kind"] != "input":
                allowed_recheck = {"read_context", "read_history", "read_data",
                                   "read_trello_card", "remember", "owner_digest",
                                   "queue_process_reply", "job_status"}
                if name == "task_record" and not args.get("confirm_author"):
                    pass
                elif name not in allowed_recheck:
                    return {"error": "timer_or_completion_cannot_grant_new_approval"}
            fresh = self.store.kv_get(f"agent_topic:{topic['id']}", {})
            if fresh.get("cancel_requested"):
                return {"error": "topic_cancelled_outcome_requires_inspection"}
            if name not in ("read_context", "read_history", "read_data", "read_trello_card",
                            "job_status") and int(fresh.get("generation", 0)) != starting_generation:
                return {"error": "new_followup_pending_reconsider_action"}
            if source is not None:
                current = self.store.row("SELECT revision FROM messages WHERE id=?", (source["id"],))
                if current is None or int(current["revision"]) != int(source["revision"]):
                    return {"error": "source_message_edited_reconsider_action"}
            if name in {s["name"] for s in OWNER_TOOLS}:
                return self._owner_tool(name, args, context) if owner else {"error": "owner_only"}
            if source is None:
                return {"error": "internal_event_has_no_source"}
            if name == "read_history":
                return self._read_history(args, context)
            return self.tools.dispatch(name, args, context)

        specs.append(_tool("read_history", "Search or page stored inbound and outbound chat history, "
                           "including edits and delivery state.",
                           {"chat_id": {"type": "integer"}, "before": {"type": "string"},
                            "after": {"type": "string"}, "limit": {"type": "integer"},
                            "query": {"type": "string"}}, []))

        def progress(message: str) -> None:
            if not message.strip():
                return
            # Commentary is an event for the single moderator, never a direct
            # completion claim or a second independent owner notification.
            digest = hashlib.sha256(message.encode()).hexdigest()[:16]
            self.dispatcher.emit_internal(topic["id"], "worker_progress", {
                "event_key": f"progress:{event['id']}:{digest}", "text": message[:1500],
                "source_event": event["id"],
            })

        result = self.llm.agent_turn(
            prompt, session_key=f"topic:{topic['id']}", model=model, provider=provider,
            system=self.system, tool_handler=dispatch, tools=specs, mode="readonly",
            cwd=str(self.repo), timeout=900, progress_callback=progress,
            effort="high", include_project_tools=True,
            cancelled=lambda: bool(self.store.kv_get(f"agent_topic:{topic['id']}", {})
                                   .get("cancel_requested")),
        )
        body = result.text.strip()
        try:
            from .llm import extract_json

            parsed = extract_json(body)
        except (ValueError, TypeError):
            parsed = {}
        answer = str(parsed.get("answer") or "") if isinstance(parsed, dict) else ""
        fresh = self.store.kv_get(f"agent_topic:{topic['id']}", {})
        current_source = (self.store.row("SELECT revision FROM messages WHERE id=?", (source["id"],))
                          if source is not None else None)
        answer_queued = bool(owner and source is not None and answer
                             and not fresh.get("cancel_requested")
                             and int(fresh.get("generation", 0)) == starting_generation
                             and current_source is not None
                             and int(current_source["revision"]) == int(source["revision"]))
        if answer_queued and source is not None:
            self.store.queue_message(key=f"agent_answer:{event['id']}",
                                     chat_id=int(source["chat_id"]), text=answer[:4000],
                                     reply_to=str(source["msg_id"]), purpose="agent_owner_answer",
                                     repeat_ok=False)
        output = {"summary": str(parsed.get("summary") or topic.get("summary") or "")[:3000],
                "next_action": str(parsed.get("next_action") or "")[:1000],
                "wake_at": parsed.get("wake_at") if isinstance(parsed.get("wake_at"), (int, float)) else None,
                "task_ids": parsed.get("task_ids") if isinstance(parsed.get("task_ids"), list)
                else topic.get("task_ids", []),
                "affected_areas": parsed.get("affected_areas")
                if isinstance(parsed.get("affected_areas"), list) else topic.get("affected_areas", []),
                "result": body[:4000], "answer_queued": answer_queued}
        return output

    def _read_history(self, args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        chat_id = int(args.get("chat_id") or context["chat_id"])
        if not context["owner"] and chat_id != int(context["chat_id"]):
            return {"error": "chat_scope"}
        limit = min(100, max(1, int(args.get("limit") or 50)))
        return self.store.history_page(chat_id, before=args.get("before"),
                                       after=args.get("after"), limit=limit,
                                       query=args.get("query"))

    def _owner_tool(self, name: str, args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        source = self.store.row("SELECT * FROM messages WHERE id=?", (context.get("event_id"),))
        if source is None or not self._owner(source) or int(source["chat_id"]) != context.get("chat_id"):
            return {"error": "owner_source_required"}
        if context.get("revision") and int(source["revision"]) != int(context["revision"]):
            return {"error": "source_message_edited"}
        if name in ("project_job", "schedule_project_job", "cancel_job", "send_job_file",
                    "select_model"):
            decision = self.semantic_verifier.check(source, name, args)
            if not decision["authorized"]:
                return {"error": "source_does_not_authorize_action", "reason": decision["reason"]}
        if name == "select_model":
            model, provider = str(args.get("model", "")).strip(), str(args.get("provider", "")).strip()
            if not model or provider not in ("codex", "claude"):
                return {"error": "invalid_model_selection"}
            self.store.kv_set("agent_owner_model", {"model": model, "provider": provider,
                                                    "event_id": context["event_id"]})
            return {"selected": model, "provider": provider}
        if name == "job_status":
            return self._public_job(self.store.kv_get(f"agent_job:{args.get('job_id')}", {}))
        if name == "cancel_job":
            job_id = str(args.get("job_id") or "")
            job = self.store.kv_get(f"agent_job:{job_id}")
            if not job:
                return {"error": "job_not_found"}
            if job.get("status") in ("scheduled", "queued"):
                self._patch_job(job_id, status="cancelled", cancel_requested=True)
            elif job.get("status") == "running":
                self._patch_job(job_id, cancel_requested=True)
            return self._public_job(self.store.kv_get(f"agent_job:{job_id}"))
        if name == "send_job_file":
            return self._send_job_file(args, context)
        if name in ("project_job", "schedule_project_job"):
            request = str(args.get("request") or "").strip()
            if not request or len(request) > 20_000:
                return {"error": "invalid_request"}
            run_at = self.clock()
            if name == "schedule_project_job":
                try:
                    run_at = self._timestamp(str(args["run_at"]))
                except (KeyError, ValueError):
                    return {"error": "invalid_run_at"}
            deadline_at = args.get("deadline_at")
            try:
                deadline = self._timestamp(str(deadline_at)) if deadline_at else None
            except ValueError:
                return {"error": "invalid_deadline_at"}
            material = {"event_id": context["event_id"], "request": request,
                        "run_at": run_at if name == "schedule_project_job" else None,
                        "task_ids": args.get("task_ids") or []}
            task_ids = args.get("task_ids") or []
            if not isinstance(task_ids, list) or any(not isinstance(x, str) for x in task_ids):
                return {"error": "invalid_task_ids"}
            snapshot = self._task_snapshot(task_ids)
            scope_error = self._task_scope_error(task_ids, snapshot)
            if scope_error:
                return {"error": "task_not_ready", "reason": scope_error}
            material_json = json.dumps(material, sort_keys=True, ensure_ascii=False)
            job_id = hashlib.sha256(material_json.encode()).hexdigest()[:16]
            key = f"agent_job:{job_id}"
            existing = self.store.kv_get(key)
            if existing:
                return self._public_job(existing)
            pref = self.store.kv_get("agent_owner_model", {})
            job = {"id": job_id, "source_event_id": context["event_id"],
                   "source_chat_id": context["chat_id"], "source_message_id": context["message_id"],
                   "topic_id": context.get("topic_id") or f"topic-{context['event_id']}",
                   "request": request, "task_ids": args.get("task_ids") or [],
                   "model": str(args.get("model") or pref.get("model") or self.cfg.agent.owner_model),
                   "provider": str(args.get("provider") or pref.get("provider")
                                   or self.cfg.agent.owner_provider),
                   "release_authorized": bool(args.get("release_authorized", False)),
                   "base_ref": str(args.get("base_ref") or ""),
                   "task_snapshot": snapshot,
                   "created_at": self.clock(), "run_at": run_at, "deadline_at": deadline,
                   "preflight_at": deadline - 75 * 60 if deadline else None,
                   "preflight_status": "pending" if deadline else None,
                   "deadline_status": "pending" if deadline else None,
                   "phase": "work",
                   "status": "scheduled" if run_at > self.clock() else "queued"}
            with self.store.transaction():
                if not self.store.kv_get(key):
                    self.store.kv_set(key, job)
                    ids = list(self.store.kv_get("agent_job_index", []))
                    ids.append(job_id)
                    self.store.kv_set("agent_job_index", ids)
            if job["status"] == "queued":
                self._submit_job(job_id)
            return self._public_job(job)
        return {"error": "unknown_tool"}

    def _timestamp(self, value: str) -> float:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(self.cfg.agent.timezone))
        return dt.timestamp()

    @staticmethod
    def _public_job(job: dict[str, Any]) -> dict[str, Any]:
        return {k: job.get(k) for k in ("id", "status", "request", "model", "provider", "task_ids",
                                        "run_at", "deadline_at", "worktree", "result", "error",
                                        "recovery_note", "cancel_requested")
                if k in job}

    def _save_job(self, job: dict[str, Any]) -> None:
        with self.store.transaction():
            current = self.store.kv_get(f"agent_job:{job['id']}", {})
            merged = {**current, **job}
            # The deadline and preflight run in separate threads from the job.
            # A stale worker snapshot must not undo a newer finalization or result.
            if current.get("phase") == "finalize":
                merged["phase"] = "finalize"
                if job.get("phase") != "finalize" and job.get("status") == "done":
                    merged["status"] = "queued"
                    merged["interim_result"] = job.get("result")
                    merged.pop("result", None)
            if current.get("status") == "done" and job.get("status") != "done":
                merged["status"] = "done"
                merged["result"] = current.get("result")
            if current.get("cancel_requested") and job.get("status") == "done":
                merged["status"] = "needs_review"
                merged["interim_result"] = job.get("result")
                merged["recovery_note"] = ("Cancel raced completion; inspect actual commands "
                                           "and external outcome")
                merged.pop("result", None)
            if (current.get("preflight_status") in ("reported", "unknown")
                    and job.get("preflight_status") not in ("reported", "unknown")):
                merged["preflight_status"] = current["preflight_status"]
                merged["preflight_result"] = current.get("preflight_result")
            if current.get("deadline_status") == "finalizing":
                merged["deadline_status"] = "finalizing"
            self.store.kv_set(f"agent_job:{job['id']}", merged)

    def _patch_job(self, job_id: str, **fields: Any) -> None:
        with self.store.transaction():
            current = self.store.kv_get(f"agent_job:{job_id}", {})
            if current:
                current.update(fields)
                self.store.kv_set(f"agent_job:{job_id}", current)

    def _task_snapshot(self, task_ids: list[str]) -> dict[str, Any]:
        wanted = {str(x) for x in task_ids}
        result: dict[str, Any] = {}
        for ticket in self.store.open_tickets():
            data = self.store.data(int(ticket["id"]))
            agent = data.get("agent") or {}
            identifiers = {str(ticket["id"]), f"WMS-{agent.get('wms_number')}"}
            for task_id in wanted & identifiers:
                mockup = agent.get("mockup") or {}
                mockup_approval = agent.get("mockup_approval") or {}
                result[task_id] = {"ticket_id": int(ticket["id"]),
                                   "approved_version": (agent.get("owner_approval") or {}).get("version"),
                                   "description_version": agent.get("version"),
                                   "is_frontend": bool(agent.get("is_frontend")),
                                   "document_version": agent.get("document_version"),
                                   "mockup_version": mockup.get("version"),
                                   "mockup_status": mockup.get("status"),
                                   "mockup_url": mockup.get("url"),
                                   "mockup_approved_version": mockup_approval.get("version"),
                                   "mockup_approved_url": mockup_approval.get("url")}
        return result

    @staticmethod
    def _task_scope_error(task_ids: list[str], snapshot: dict[str, Any]) -> str | None:
        for task_id in map(str, task_ids):
            state = snapshot.get(task_id)
            if not state:
                return f"selected task {task_id} is not linked to a current ticket"
            version = state.get("description_version")
            if not version or state.get("approved_version") != version:
                return f"description for {task_id} lacks current owner approval"
            if state.get("document_version") != version:
                return f"canonical requirements for {task_id} are not saved"
            if state.get("is_frontend") and (state.get("mockup_status") != "published"
                                             or state.get("mockup_version") != version
                                             or not state.get("mockup_url")
                                             or state.get("mockup_approved_version") != version
                                             or state.get("mockup_approved_url") != state.get("mockup_url")):
                return f"published mockup for {task_id} lacks current owner approval"
        return None

    def _submit_job(self, job_id: str) -> None:
        with self.job_lock:
            if job_id in self.active_jobs:
                return
            self.active_jobs.add(job_id)

        def run() -> None:
            try:
                self._run_job(job_id)
            finally:
                with self.job_lock:
                    self.active_jobs.discard(job_id)
        self.jobs.submit(run)

    def _worktree(self, job: dict[str, Any]) -> Path:
        path = self.repo / ".worktrees" / f"support-job-{job['id']}"
        if path.is_dir():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not job.get("base_ref"):
            # Refresh the canonical trunk before creating an isolated task branch.
            subprocess.run(["git", "-C", str(self.repo), "fetch", "origin", "etalon"],
                           capture_output=True, text=True, timeout=120, check=False)
        task = next((str(x) for x in job.get("task_ids", []) if re.fullmatch(r"WMS-\d+", str(x))), "")
        prefix = task.lower() if task else "agent"
        branch = f"codex/{prefix}-job-{job['id']}"
        refs = [job["base_ref"]] if job.get("base_ref") else ["origin/etalon", "origin/main", "origin/master"]
        base = ""
        for ref in refs:
            checked = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "--verify",
                                      "--quiet", f"{ref}^{{commit}}"],
                                     capture_output=True, text=True, timeout=20)
            if checked.returncode == 0:
                base = ref
                break
        if not base:
            raise RuntimeError("No verified base branch; owner must select an existing base_ref")
        proc = subprocess.run(["git", "-C", str(self.repo), "worktree", "add", "-b", branch,
                               str(path), base], capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(f"git worktree creation failed: {proc.stderr[-800:]}")
        return path

    def _run_job(self, job_id: str) -> None:
        job = self.store.kv_get(f"agent_job:{job_id}")
        if not job or job["status"] not in ("queued", "running", "recovering"):
            return
        if job.get("cancel_requested"):
            self._patch_job(job_id, status="cancelled")
            return
        recovery = job["status"] in ("running", "recovering")
        finalizing = job.get("phase") == "finalize"
        try:
            current_snapshot = self._task_snapshot(job.get("task_ids") or [])
            scope_error = self._task_scope_error(job.get("task_ids") or [], current_snapshot)
            if scope_error:
                job.update(status="needs_owner_review", error=scope_error)
                self._save_job(job)
                return
            if job.get("task_snapshot") != current_snapshot:
                job.update(status="needs_owner_review",
                           error="Task version or approval changed after selection")
                self._save_job(job)
                self.store.queue_message(key=f"agent_job_changed:{job_id}",
                                         chat_id=self.cfg.telegram.owner_chat_id,
                                         text=f"Работа {job_id} ждёт повторного выбора: "
                                              "описание или согласование "
                                              "задачи изменилось после поручения.", purpose="agent_job",
                                         repeat_ok=False)
                return
            worktree = self._worktree(job)
            job.update(status="recovering" if recovery else "running", worktree=str(worktree),
                       started_at=job.get("started_at") or self.clock())
            self._save_job(job)
            source = self.store.row("SELECT * FROM messages WHERE id=?", (job["source_event_id"],))
            if source is None or not self._owner(source):
                raise RuntimeError("owner authorization source is missing")
            prompt = json.dumps({"owner_request": job["request"], "source_message": source["text"],
                                 "current_time": self._local_now(), "timezone": self.cfg.agent.timezone,
                                 "task_ids": job["task_ids"], "deadline_at": job["deadline_at"],
                                 "task_snapshot_at_authorization": job.get("task_snapshot"),
                                 "preflight_at": job.get("preflight_at"),
                                 "preflight_result": job.get("preflight_result"),
                                 "release_authorized": job["release_authorized"],
                                 "recovery": recovery, "phase": job.get("phase", "work"),
                                 "instructions": "You have native project shell, read and edit tools in this "
                                 "worktree. Fulfill the owner's exact request, including an unusual request "
                                 "without a predefined service handler. Read AGENTS.md. Record evidence and "
                                 "actual output paths. Do not manage secrets. Before external sends, "
                                 "releases, "
                                 "or destructive effects verify authorization scope. If recovering after an "
                                 "interrupted CLI run, inspect Git and external state first; never blindly "
                                 "repeat an operation whose outcome is unknown. If phase is finalize, "
                                 "inspect all current commits, production and staging served SHAs, reviews "
                                 "and acceptance; release only a verified ready subset IF "
                                 "release_authorized, "
                                 "and reconcile any unknown outcome before repeating. Report the remainder "
                                 "and exact evidence. Do not start new unready work in finalization. "
                                 "For an export you intend to send, save the file under the job worktree. "
                                 "Report uncertainty honestly."},
                                ensure_ascii=False)
            context = self._context(source, owner=True)
            context.update(job_id=job_id, worktree=str(worktree))
            def job_progress(message: str) -> None:
                if not message.strip():
                    return
                digest = hashlib.sha256(message.encode()).hexdigest()[:16]
                self.dispatcher.emit_internal(str(job.get("topic_id")), "worker_progress", {
                    "event_key": f"job_progress:{job_id}:{digest}", "job_id": job_id,
                    "text": message[:1500],
                })

            result = self.llm.agent_turn(prompt, session_key=f"job:{job_id}", model=job["model"],
                                         provider=job["provider"], system=self.system,
                                         tools=[{**spec, "type": "function"}
                                                for spec in self.tools.specs(scope="owner")],
                                         tool_handler=lambda name, args: self.tools.dispatch(
                                             name, args, context),
                                         mode="owner", owner_authorized=True,
                                         cwd=str(worktree), timeout=3600,
                                         progress_callback=job_progress,
                                         cancelled=lambda: bool(
                                             self.store.kv_get(f"agent_job:{job_id}", {})
                                             .get("cancel_requested")
                                             or (not finalizing and
                                                 (deadline := self.store.kv_get(
                                                     f"agent_job:{job_id}", {}).get("deadline_at"))
                                                 and self.clock() >= float(deadline))))
            latest = self.store.kv_get(f"agent_job:{job_id}", {})
            if latest.get("phase") == "finalize" and not finalizing:
                job.update(phase="finalize", status="queued", interim_result=result.text[:8000])
                self._save_job(job)
                return
            job.update(status="done", result=result.text[:12000], finished_at=self.clock())
            self._save_job(job)
            if self.store.kv_get(f"agent_job:{job_id}", {}).get("status") != "done":
                if self.store.kv_get(f"agent_job:{job_id}", {}).get("cancel_requested"):
                    self.store.queue_message(key=f"agent_job_cancel_unknown:{job_id}",
                                             chat_id=self.cfg.telegram.owner_chat_id,
                                             text=f"Работа {job_id} была остановлена во время завершения. "
                                                  "Исход команд нужно проверить; успех не подтверждаю.",
                                             purpose="agent_job", repeat_ok=False)
                return  # deadline switched to finalization while this turn was ending
            self.dispatcher.emit_internal(str(job.get("topic_id")), "job_done", {
                "event_key": f"job_done:{job_id}", "job_id": job_id,
                "text": result.text[:3600], "status": "done",
            })
        except LlmUnavailable as exc:
            latest = self.store.kv_get(f"agent_job:{job_id}", {})
            if latest.get("phase") == "finalize" and not finalizing:
                job.update(phase="finalize", status="queued",
                           recovery_note="Deadline interrupted work; inspect every external outcome")
                self._save_job(job)
                return
            # The native turn may have acted before a lost response. Preserve the
            # worktree/session and require state inspection before any continuation.
            job.update(status="needs_review", error=str(exc)[:800],
                       recovery_note="CLI outcome unknown; inspect Git and external state")
            self._save_job(job)
            self.store.queue_message(key=f"agent_job_model:{job_id}", chat_id=self.cfg.telegram.owner_chat_id,
                                     text=f"Работа {job_id} прервалась на модели {job['model']}; "
                                          "исход команд требует проверки перед продолжением.",
                                     purpose="agent_job", repeat_ok=False)
        except Exception as exc:
            log.exception("agent project job %s failed", job_id)
            job.update(status="needs_review", error=f"{type(exc).__name__}: {exc}"[:800])
            self._save_job(job)
            self.store.queue_message(key=f"agent_job_error:{job_id}", chat_id=self.cfg.telegram.owner_chat_id,
                                     text=f"Работа {job_id} остановилась: {type(exc).__name__}. "
                                          "Состояние сохранено, результат требует проверки.",
                                     purpose="agent_job", repeat_ok=False)

    def _send_job_file(self, args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        job = self.store.kv_get(f"agent_job:{args.get('job_id')}")
        if not job or job.get("status") != "done":
            return {"error": "job_not_done"}
        root = Path(str(job.get("worktree", ""))).resolve()
        raw_path = Path(str(args.get("path", "")))
        path = (raw_path if raw_path.is_absolute() else root / raw_path).resolve()
        if root not in path.parents or not path.is_file():
            return {"error": "file_not_in_job_worktree"}
        if path.stat().st_size > 50_000_000:
            return {"error": "file_too_large"}
        key_material = f"{context['event_id']}:{job['id']}:{path}"
        key = "agent_file:" + hashlib.sha256(key_material.encode()).hexdigest()[:20]
        queued = self.store.queue_message(key=key, chat_id=self.cfg.telegram.owner_chat_id,
                                          text=str(args.get("caption") or path.name)[:1000],
                                          purpose="agent_job_file", repeat_ok=False,
                                          file_path=str(path))
        return {"queued": queued, "key": key, "file": path.name}

    def tick(self) -> None:
        # Existing owner binding replies are a transport protocol, not topic
        # discussion. Everything else enters the single durable dispatcher.
        for m in self.store.messages_with_status("new", 500):
            if m["role"] == "owner" and self._owner(m):
                pid = self.pipe._is_bind_reply(m)
                if pid is not None:
                    self.pipe._confirm_binding(m, pid)
        self.dispatcher.tick()
        now = self.clock()
        for ticket in self.store.open_tickets():
            data = self.store.data(int(ticket["id"]))
            agent = data.get("agent") or {}
            version = agent.get("version")
            if (agent.get("is_frontend") and version
                    and (agent.get("author_confirmation") or {}).get("version") == version
                    and agent.get("document_version") == version
                    and not agent.get("mockup")):
                agent["mockup"] = {"version": version, "status": "queued"}
                self.store.patch_data(int(ticket["id"]), agent=agent)
            if (agent.get("mockup") or {}).get("status") == "queued":
                tid = int(ticket["id"])
                self._submit_mockup(tid)
        for jid in self.store.kv_get("agent_job_index", []):
            job = self.store.kv_get(f"agent_job:{jid}", {})
            if job.get("status") == "scheduled" and float(job.get("run_at", 0)) <= now:
                job["status"] = "queued"
                self._save_job(job)
            if job.get("status") == "queued":
                self._submit_job(jid)
            if (job.get("preflight_status") == "pending" and job.get("preflight_at")
                    and now >= float(job["preflight_at"])):
                job["preflight_status"] = "queued"
                self._save_job(job)
                self.jobs.submit(self._deadline_preflight, jid)
            if (job.get("deadline_status") == "pending" and job.get("deadline_at")
                    and now >= float(job["deadline_at"])):
                job["deadline_status"] = "finalizing"
                if job.get("status") not in ("done", "needs_review", "needs_owner_review"):
                    job["phase"] = "finalize"
                    if job.get("status") in ("scheduled", "waiting_model"):
                        job["status"] = "queued"
                self._save_job(job)
                if job.get("status") == "queued":
                    self._submit_job(jid)
        interval = max(300, int(self.cfg.agent.hourly_interval_sec))
        next_at = float(self.store.kv_get("agent_hourly_next_at", 0) or 0)
        if not next_at:
            self.store.kv_set("agent_hourly_next_at", now + interval)
        elif now >= next_at:
            self.store.kv_set("agent_hourly_next_at", now + interval)
            self.pipe.pool.submit("agent_hourly", self._hourly)

    def recover_after_restart(self) -> None:
        self.dispatcher.recover_after_restart()
        for jid in self.store.kv_get("agent_job_index", []):
            job = self.store.kv_get(f"agent_job:{jid}", {})
            if job.get("status") == "running":
                job["status"] = "recovering"
                job["recovery_note"] = "Previous CLI outcome unknown; inspect state before any retry."
                self._save_job(job)
                self._submit_job(jid)
            if job.get("preflight_status") == "running":
                job["preflight_status"] = "unknown"
                self._save_job(job)
        for ticket in self.store.open_tickets():
            agent = self.store.data(int(ticket["id"])).get("agent") or {}
            if (agent.get("mockup") or {}).get("status") == "running":
                agent["mockup"] = {**agent["mockup"], "status": "queued",
                                   "recovery_note": "Interrupted run: inspect existing files and public URL "
                                                    "before creating or publishing again"}
                self.store.patch_data(int(ticket["id"]), agent=agent)

    def _submit_mockup(self, tid: int) -> None:
        key = f"mockup:{tid}"
        with self.job_lock:
            if key in self.active_jobs:
                return
            self.active_jobs.add(key)

        def run() -> None:
            try:
                data = self.store.data(tid)
                agent = data.get("agent") or {}
                version = agent.get("version")
                if (agent.get("mockup") or {}).get("status") != "queued":
                    return
                agent["mockup"] = {**agent["mockup"], "status": "running"}
                self.store.patch_data(tid, agent=agent)
                self.pipe.mockups.run(tid)
                latest = self.store.data(tid).get("agent") or {}
                if (latest.get("version") == version
                        and (latest.get("mockup") or {}).get("status") == "running"):
                    latest["mockup"] = {**latest["mockup"], "status": "failed"}
                    self.store.patch_data(tid, agent=latest)
            except Exception:
                log.exception("agent mockup %s failed", tid)
                latest = self.store.data(tid).get("agent") or {}
                if (latest.get("mockup") or {}).get("status") == "running":
                    latest["mockup"] = {**latest["mockup"], "status": "unknown"}
                    self.store.patch_data(tid, agent=latest)
            finally:
                with self.job_lock:
                    self.active_jobs.discard(key)
        self.jobs.submit(run)

    def _hourly(self) -> None:
        """A scheduled read of the live board does not impersonate an owner message."""
        try:
            cards = self.tools.ready_cards()
        except Exception:
            log.exception("hourly Trello read failed")
            return
        if not cards:
            return
        lines = ["Задачи с согласованным описанием, которые можно выбрать в работу:"]
        for card in cards[:25]:
            lines.append(f"• {card.get('name') or 'Без названия'} — {card.get('url') or 'ссылка недоступна'}")
        lines.append("Какие запустить?")
        slot = int(self.clock() // max(300, int(self.cfg.agent.hourly_interval_sec)))
        self.store.queue_message(key=f"agent_hourly:{slot}", chat_id=self.cfg.telegram.owner_chat_id,
                                 text="\n".join(lines)[:4000], purpose="agent_hourly", repeat_ok=False)

    def _deadline_preflight(self, job_id: str) -> None:
        """Read actual Git/deploy state before the deadline, in a separate checkout."""
        job = self.store.kv_get(f"agent_job:{job_id}", {})
        if not job or job.get("preflight_status") not in ("queued", "running"):
            return
        source = self.store.row("SELECT * FROM messages WHERE id=?", (job.get("source_event_id"),))
        if source is None or not self._owner(source):
            self._patch_job(job_id, preflight_status="source_missing")
            return
        self._patch_job(job_id, preflight_status="running")
        try:
            preflight = {**job, "id": f"{job_id}-preflight", "task_ids": job.get("task_ids", [])}
            path = self._worktree(preflight)
            prompt = json.dumps({"owner_request": job["request"], "deadline_at": job["deadline_at"],
                                 "current_time": self._local_now(), "timezone": self.cfg.agent.timezone,
                                 "task_ids": job["task_ids"],
                                 "instruction": "This is the 75-minute preflight. Read actual production and "
                                 "staging served versions, Git state and parallel commits/branches. "
                                 "Do not deploy, merge, edit or send externally. Report confirmed SHAs, "
                                 "risks, unknowns, ready subset and what remains. Inspect state before "
                                 "any possible later repeat of an uncertain release."}, ensure_ascii=False)
            result = self.llm.agent_turn(prompt, session_key=f"preflight:{job_id}",
                                         model=job["model"], provider=job["provider"],
                                         system=self.system, mode="owner", owner_authorized=True,
                                         cwd=str(path), timeout=600)
            self._patch_job(job_id, preflight_status="reported", preflight_result=result.text[:8000])
            self.store.queue_message(key=f"agent_preflight:{job_id}",
                                     chat_id=self.cfg.telegram.owner_chat_id,
                                     text=f"Проверка перед сроком {job_id}: {result.text[:3500]}",
                                     purpose="agent_preflight", repeat_ok=False)
        except Exception as exc:
            self._patch_job(job_id, preflight_status="unknown", preflight_error=type(exc).__name__)
            self.store.queue_message(key=f"agent_preflight_error:{job_id}",
                                     chat_id=self.cfg.telegram.owner_chat_id,
                                     text=f"Проверка перед сроком {job_id} не завершилась; "
                                          "фактические версии пока не подтверждены.",
                                     purpose="agent_preflight", repeat_ok=False)
