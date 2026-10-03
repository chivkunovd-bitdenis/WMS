"""Independent, source-bound semantic check for consequential model actions."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .llm import extract_json


class SemanticAuthorization:
    def __init__(self, coordinator: Any) -> None:
        self.agent = coordinator

    def check(self, event: Any, action: str, args: dict[str, Any]) -> dict[str, Any]:
        store = self.agent.store
        source = store.row("SELECT * FROM messages WHERE id=?", (event["id"],))
        if source is None or int(source["revision"]) != int(event["revision"]):
            return {"authorized": False, "reason": "source_edited"}
        ticket_id = args.get("ticket_id")
        agent_data = (store.data(int(ticket_id)).get("agent") or {}) if ticket_id else {}
        proposal = {
            "ticket_id": ticket_id, "version": agent_data.get("version"),
            "title": agent_data.get("title"), "description": agent_data.get("description"),
            "mockup": agent_data.get("mockup"),
            "owner_approval": agent_data.get("owner_approval"),
        }
        # The exact source revision, target and proposed effect define this
        # authorization. A model rewrite of the same Telegram event cannot widen it.
        material = json.dumps({"event_id": event["id"], "revision": event["revision"],
                               "source_text": event["text"], "action": action,
                               "arguments": args, "proposal": proposal},
                              ensure_ascii=False, sort_keys=True, default=str)
        key = "agent_semantic_auth:" + hashlib.sha256(material.encode()).hexdigest()
        cached = store.kv_get(key)
        if cached:
            return cached
        prompt = json.dumps({
            "actual_source": {"id": event["id"], "revision": event["revision"],
                              "role": event["role"], "chat_id": event["chat_id"],
                              "author_id": event["author_id"], "text": event["text"]},
            "proposed_action": action, "arguments": args, "current_object": proposal,
            "instruction": "Independently decide whether the actual source message explicitly "
            "authorizes this exact consequential action on this object and current version. "
            "A request to inspect/explain is not approval, send, develop or release. "
            "No silence or prior unrelated message is approval. For author confirmation, "
            "the author must affirm the shown process/description. For owner actions, "
            "the source must be the verified owner private message. Do not infer consent "
            "from the first model's tool call. Return JSON {authorized:boolean,"
            "source_quote:string,reason:string}. Quote an exact nonempty substring of "
            "actual_source.text when authorized; if ambiguous, authorized=false.",
        }, ensure_ascii=False, default=str)
        result = self.agent.llm.agent_turn(
            prompt, session_key=f"auth:{key[-20:]}", model=self.agent.cfg.agent.owner_model,
            provider=self.agent.cfg.agent.owner_provider, system="Semantic authorization audit only.",
            mode="readonly", cwd=str(self.agent.repo), timeout=45, tools=[],
            effort="medium", include_project_tools=False,
        )
        parsed = extract_json(result.text)
        quote = str(parsed.get("source_quote") or "")
        authorized = bool(parsed.get("authorized") is True and quote and quote in str(event["text"]))
        decision = {"authorized": authorized, "source_quote": quote if authorized else "",
                    "reason": str(parsed.get("reason") or "")[:300]}
        store.kv_set(key, decision)
        return decision
