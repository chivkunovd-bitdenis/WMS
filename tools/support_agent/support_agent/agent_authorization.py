"""Independent, source-bound semantic check for consequential model actions."""

from __future__ import annotations

import hashlib
import json
import re
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
        owner_cfg = self.agent.cfg.telegram
        verified_owner_private = bool(
            source["role"] == "owner" and int(source["chat_id"]) == owner_cfg.owner_chat_id
            and str(source["author_id"]) == str(owner_cfg.owner_user_id)
            and bool(owner_cfg.owner_user_id)
        )
        if action != "task_record" and not verified_owner_private:
            return {"authorized": False, "reason": "verified_owner_private_required"}
        ticket_id = args.get("ticket_id")
        agent_data = (store.data(int(ticket_id)).get("agent") or {}) if ticket_id else {}
        proposal = {
            "ticket_id": ticket_id, "version": agent_data.get("version"),
            "title": agent_data.get("title"), "description": agent_data.get("description"),
            "mockup": agent_data.get("mockup"),
            "owner_approval": agent_data.get("owner_approval"),
        }
        prior = self._prior_context(source)
        # The exact source revision, target and proposed effect define this
        # authorization. A model rewrite of the same Telegram event cannot widen it.
        material = json.dumps({"evidence_version": 2, "event_id": event["id"], "revision": event["revision"],
                               "source_text": event["text"], "action": action,
                               "arguments": args, "proposal": proposal,
                               "prior": prior},
                              ensure_ascii=False, sort_keys=True, default=str)
        key = "agent_semantic_auth:" + hashlib.sha256(material.encode()).hexdigest()
        cached = store.kv_get(key)
        if cached:
            return cached
        prompt = json.dumps({
            "actual_source": {"id": event["id"], "revision": event["revision"],
                              "message_id": source["msg_id"],
                              "role": event["role"], "chat_id": event["chat_id"],
                              "author_id": event["author_id"], "text": event["text"],
                              "reply_to": event["reply_to"],
                              "verified_owner_private": verified_owner_private},
            "proposed_action": action, "arguments": args, "current_object": proposal,
            "prior_same_chat": prior,
            "instruction": "Independently decide whether the actual source message explicitly "
            "authorizes this exact consequential action on this object and current version. "
            "Use actual same-chat prior messages, especially a verified reply target, "
            "to resolve short answers such as 'да, утверждаю'. Only a sent outgoing "
            "message was shown to the person. An unrelated 'да' is not authorization. "
            "A request to inspect/explain is not approval, send, develop or release. "
            "No silence or prior unrelated message is approval. For author confirmation, "
            "the author must affirm the shown process/description. For owner actions, "
            "the source must have verified_owner_private=true (this fact is checked by "
            "service identity configuration). Do not infer consent "
            "from the first model's tool call. Return JSON {authorized:boolean,"
            "source_quote:string,reason:string}. Copy one SHORT exact nonempty substring of "
            "actual_source.text when authorized. Do not concatenate separated sentences. "
            "Preparing a requested draft for the owner does not require approval of the "
            "draft that has not been created yet. Prior messages include event_id (internal) "
            "and msg_id (Telegram); do not confuse these identifiers. "
            "If ambiguous, authorized=false.",
        }, ensure_ascii=False, default=str)
        result = self.agent.llm.agent_turn(
            prompt, session_key=f"auth:{key[-20:]}", model=self.agent.cfg.agent.owner_model,
            provider=self.agent.cfg.agent.owner_provider, system="Semantic authorization audit only.",
            mode="readonly", cwd=str(self.agent.repo), timeout=45, tools=[],
            effort="medium", include_project_tools=False,
        )
        parsed = extract_json(result.text)
        quote = str(parsed.get("source_quote") or "")
        spans = self._quote_spans(str(source["text"]), quote)
        authorized = bool(parsed.get("authorized") is True and spans)
        reason = str(parsed.get("reason") or "")[:300]
        if parsed.get("authorized") is True and not spans:
            reason = "Проверяющая модель подтвердила поручение, но неверно процитировала источник; " \
                     "это ошибка проверки цитаты, а не отсутствие разрешения владельца."
        decision = {"authorized": authorized, "source_quote": spans[0] if authorized else "",
                    "source_quotes": spans if authorized else [], "reason": reason}
        store.kv_set(key, decision)
        return decision

    @staticmethod
    def _quote_spans(source: str, quote: str) -> list[str]:
        if not quote:
            return []
        if quote in source:
            return [quote]
        # Voice transcripts contain interjections between sentences. A model may
        # join exact sentences; validate every span in order, without fuzzy matching.
        spans = re.split(r"(?<=[.!?])\s+", quote.strip())
        if len(spans) < 2:
            return []
        cursor = 0
        for span in spans:
            found = source.find(span, cursor)
            if not span or found < 0:
                return []
            cursor = found + len(span)
        return spans

    def _prior_context(self, source: Any) -> list[dict[str, Any]]:
        store = self.agent.store
        chat_id, ts = int(source["chat_id"]), float(source["ts"])
        incoming = store.rows(
            "SELECT id AS event_id,msg_id,author_id,text,reply_to,ts,revision FROM messages "
            "WHERE chat_id=? AND (ts<? OR (ts=? AND id<?)) ORDER BY ts DESC,id DESC LIMIT 8",
            (chat_id, ts, ts, int(source["id"])),
        )
        outgoing = store.rows(
            "SELECT tg_message_id AS msg_id,text,reply_to,created_at AS ts,status "
            "FROM outbox WHERE chat_id=? AND created_at<=? AND status='sent' "
            "ORDER BY created_at DESC,id DESC LIMIT 8", (chat_id, ts),
        )
        items = [{**dict(x), "direction": "in"} for x in incoming]
        items.extend({**dict(x), "direction": "out"} for x in outgoing)
        reply_to = str(source["reply_to"] or "")
        if reply_to and not any(str(x.get("msg_id")) == reply_to for x in items):
            target_in = store.row(
                "SELECT id AS event_id,msg_id,author_id,text,reply_to,ts,revision FROM messages "
                "WHERE chat_id=? AND msg_id=? AND ts<=?", (chat_id, reply_to, ts),
            )
            target_out = store.row(
                "SELECT tg_message_id AS msg_id,text,reply_to,created_at AS ts,status "
                "FROM outbox WHERE chat_id=? AND tg_message_id=? AND created_at<=? AND status='sent'",
                (chat_id, reply_to, ts),
            )
            target = target_in or target_out
            if target is not None:
                items.append({**dict(target), "direction": "in" if target_in else "out",
                              "explicit_reply_target": True})
        items.sort(key=lambda x: float(x["ts"]))
        return items[-16:]
