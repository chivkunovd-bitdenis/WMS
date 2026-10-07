"""Durable handover between visible moderator generations, without stopping workers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ModeratorContinuity:
    def __init__(self, agent: Any) -> None:
        self.agent, self.store = agent, agent.store
        state = self.store.kv_get("agent_moderator", {})
        if not state:
            state = {
                "generation": 1,
                "thread_id": getattr(agent.cfg.agent, "moderator_thread_id", "") or None,
                "created_at": agent.clock(),
                "context_tokens": 0,
            }
            self.store.kv_set("agent_moderator", state)

    @property
    def state(self) -> dict[str, Any]:
        return self.store.kv_get("agent_moderator", {})

    @property
    def session_key(self) -> str:
        return f"agent:moderator:{self.state.get('generation', 1)}"

    @property
    def thread_id(self) -> str | None:
        return self.state.get("thread_id") or None

    @property
    def name(self) -> str:
        return f"Чат разбора №{self.state.get('generation', 1)}"

    def snapshot(self) -> dict[str, Any]:
        state = self.state
        return {
            "generation": state.get("generation"),
            "handoff_path": state.get("handoff_path"),
            "handoff": state.get("handoff", {}),
            "history_root": str(self.agent.journal.root) if hasattr(self.agent, "journal") else "",
        }

    def observe(self, result: Any) -> None:
        state = self.state
        if getattr(result, "session_id", None):
            state["thread_id"] = result.session_id
        tokens = int(getattr(result, "context_tokens", 0) or 0)
        state["context_tokens"] = tokens
        self.store.kv_set("agent_moderator", state)
        limit = int(getattr(self.agent.cfg.agent, "context_limit_tokens", 250000))
        if tokens < limit:
            return
        # Routing runs serially; this is the moderator's safe completed-turn boundary.
        # Existing workers keep their thread IDs and receive no cancellation. Fresh
        # ingress and late completions are read by the successor from durable queues.
        topics = []
        for tid in self.store.kv_get("agent_topic_index", []):
            topic = self.store.kv_get(f"agent_topic:{tid}", {})
            if not topic:
                continue
            topics.append(
                {
                    key: topic.get(key)
                    for key in (
                        "id",
                        "chat_id",
                        "summary",
                        "next_action",
                        "status",
                        "task_ids",
                        "worker_session_id",
                        "pending",
                        "last_source_id",
                        "last_client_source_id",
                        "generation",
                        "wake_at",
                    )
                }
            )
        handoff = {
            "previous_thread_id": state.get("thread_id"),
            "created_at": self.agent.clock(),
            "topics": topics,
            "queued_event_ids": self.store.kv_get("agent_dispatch_queue", []),
            "job_ids": self.store.kv_get("agent_job_index", []),
            "instruction": "Continue existing cases and worker sessions. Never duplicate queued jobs. "
            "Active workers finish their current safe step independently; consume their "
            "journaled results here. Read full per-chat history when needed.",
        }
        root = (
            Path(self.agent.journal.root)
            if hasattr(self.agent, "journal")
            else Path(
                getattr(self.agent.cfg.agent, "history_dir", "")
                or self.agent.repo / "var/support-conversations"
            )
        )
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"moderator-handoff-{state.get('generation', 1)}.json"
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(handoff, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
        self.store.kv_set(
            f"agent_moderator_generation:{state.get('generation', 1)}",
            {**state, "status": "handed_over", "handoff_path": str(path)},
        )
        self.store.kv_set(
            "agent_moderator",
            {
                "generation": int(state.get("generation", 1)) + 1,
                "thread_id": None,
                "created_at": self.agent.clock(),
                "context_tokens": 0,
                "handoff_path": str(path),
                "handoff": handoff,
            },
        )
