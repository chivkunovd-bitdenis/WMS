"""Small, source-checked tools for the conversational WMS agent.

The model decides what a message means. This module only checks the source,
object identity, version and durable intent before carrying out an action.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .canonical_tasks import CanonicalTaskError, persist_task
from .trello import TrelloError, ensure_card


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


class ToolDenied(ValueError):
    pass


class AgentTools:
    def __init__(self, pipe: Any) -> None:
        self.p = pipe
        self.store = pipe.store

    def specs(self, scope: str) -> list[dict[str, Any]]:
        common = [
            self._spec("read_context", "Read source messages, linked tasks and memory. Paginate with before_id.",
                       {"chat_id": "integer", "ticket_id": "integer", "before_id": "integer", "limit": "integer"}),
            self._spec("remember", "Save a source-linked current summary, facts, open questions and next step.",
                       {"chat_id": "integer", "summary": "string", "facts": "array", "questions": "array",
                        "next_step": "string", "source_message_ids": "array"}),
            self._spec("task_record", "Create or revise one task from discussion; confirmation uses the actual author's message.",
                       {"ticket_id": "integer", "chat_id": "integer", "title": "string",
                        "description": "string", "is_frontend": "boolean", "source_message_ids": "array",
                        "topic_key": "string",
                        "confirm_author": "boolean"}),
        ]
        if scope == "owner":
            common.extend([
                self._spec("approve_task", "Approve the current task description version from this owner message.",
                           {"ticket_id": "integer", "version": "string"}),
                self._spec("queue_reply", "Queue an owner-authorized exact message to a specified chat and task.",
                           {"ticket_id": "integer", "chat_id": "integer", "text": "string",
                            "version": "string", "reply_to": "string"}),
                self._spec("trello_sync", "Create/find the card or move it to Description agreed after version approval.",
                           {"ticket_id": "integer", "action": "string"}),
                self._spec("request_mockup", "Queue Sonnet mockup for a confirmed frontend task.",
                           {"ticket_id": "integer"}),
            ])
        else:
            common.append(self._spec("queue_process_reply", "Ask one necessary question or show description for author confirmation.",
                                     {"ticket_id": "integer", "kind": "string", "text": "string",
                                      "reply_to": "string"}))
        return common

    def ready_cards(self) -> list[dict[str, Any]]:
        """Read current Trello candidates for the hourly owner digest."""
        list_id = self.p.trello.list_named("Описание согласовано")
        if not list_id:
            return []
        cards = self.p.trello.board_cards()
        return [{"id": card.get("id"), "name": card.get("name"), "url": card.get("shortUrl")}
                for card in cards if card.get("idList") == list_id]

    @staticmethod
    def _spec(name: str, description: str, fields: dict[str, str]) -> dict[str, Any]:
        return {"name": name, "description": description, "inputSchema": {
            "type": "object", "properties": {key: ({"type": kind, "items": {"type": "integer" if key == "source_message_ids" else "string"}}
                                                       if kind == "array" else {"type": kind})
                                           for key, kind in fields.items()},
            "additionalProperties": False,
        }}

    def dispatch(self, name: str, args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        event = self._event(context)
        owner = self._owner(event)
        allowed = {s["name"] for s in self.specs("owner" if owner else "client")}
        if name not in allowed:
            raise ToolDenied("tool_unavailable_for_source")
        if not isinstance(args, dict):
            raise ToolDenied("invalid_arguments")
        method = getattr(self, f"_tool_{name}")
        return method(args, event, owner)

    def _event(self, context: dict[str, Any]) -> Any:
        # No model-supplied owner flag, author or source is trusted.
        event_id = int(context.get("event_id") or 0)
        row = self.store.row("SELECT * FROM messages WHERE id=?", (event_id,))
        if row is None or row["chat_id"] != int(context.get("chat_id") or 0):
            raise ToolDenied("unknown_source_event")
        if str(row["author_id"]) != str(context.get("author_id")):
            raise ToolDenied("source_author_mismatch")
        return row

    def _owner(self, event: Any) -> bool:
        cfg = self.p.cfg.telegram
        return (event["role"] == "owner" and event["chat_id"] == cfg.owner_chat_id
                and str(event["author_id"]) == str(cfg.owner_user_id))

    def _chat(self, requested: Any, event: Any, owner: bool) -> int:
        chat = int(requested or event["chat_id"])
        if not owner and chat != event["chat_id"]:
            raise ToolDenied("cross_chat_access")
        return chat

    def _ticket(self, tid: Any, event: Any, owner: bool) -> Any:
        row = self.store.row("SELECT * FROM tickets WHERE id=?", (int(tid),))
        if row is None or (not owner and row["chat_id"] != event["chat_id"]):
            raise ToolDenied("ticket_out_of_scope")
        return row

    def _sources(self, ids: Any, chat_id: int) -> list[int]:
        if not isinstance(ids, list) or not ids or len(ids) > 30:
            raise ToolDenied("source_messages_required")
        result = sorted({int(n) for n in ids})
        marks = ",".join("?" for _ in result)
        rows = self.store.rows(f"SELECT id FROM messages WHERE chat_id=? AND id IN ({marks})",
                               (chat_id, *result))
        if len(rows) != len(result):
            raise ToolDenied("source_message_out_of_scope")
        return result

    def _tool_read_context(self, args: dict[str, Any], event: Any, owner: bool) -> dict[str, Any]:
        chat_id = self._chat(args.get("chat_id"), event, owner)
        tid = args.get("ticket_id")
        if tid:
            ticket = self._ticket(tid, event, owner)
            if ticket["chat_id"] != chat_id:
                raise ToolDenied("ticket_chat_mismatch")
        limit = max(1, min(int(args.get("limit") or 30), 100))
        before = int(args.get("before_id") or 2**63 - 1)
        rows = self.store.rows(
            "SELECT id,source,chat_id,msg_id,role,author_id,author_name,ts,kind,text,reply_to,ticket_id "
            "FROM messages WHERE chat_id=? AND id<? ORDER BY id DESC LIMIT ?", (chat_id, before, limit),
        )
        task_rows = self.store.rows(
            "SELECT id,kind,stage,author_id,data FROM tickets WHERE chat_id=? ORDER BY id DESC LIMIT 30",
            (chat_id,),
        )
        outgoing = self.store.rows(
            "SELECT id,key,chat_id,reply_to,text,status,tg_message_id,ticket_id,purpose,created_at,sent_at "
            "FROM outbox WHERE chat_id=? AND id<? ORDER BY id DESC LIMIT ?", (chat_id, before, limit),
        )
        return {"messages": [dict(r) for r in reversed(rows)],
                "outgoing": [dict(r) for r in reversed(outgoing)],
                "next_before_id": rows[-1]["id"] if len(rows) == limit else None,
                "tasks": [{**dict(r), "data": json.loads(r["data"])} for r in task_rows],
                "memory": self.store.kv_get(f"agent_memory:{chat_id}", {})}

    def _tool_remember(self, args: dict[str, Any], event: Any, owner: bool) -> dict[str, Any]:
        chat_id = self._chat(args.get("chat_id"), event, owner)
        sources = self._sources(args.get("source_message_ids"), chat_id)
        for name in ("facts", "questions"):
            if not isinstance(args.get(name), list):
                raise ToolDenied(f"{name}_must_be_list")
        memory = {"summary": str(args.get("summary") or "")[:8000],
                  "facts": args["facts"][:50], "questions": args["questions"][:20],
                  "next_step": str(args.get("next_step") or "")[:2000],
                  "source_message_ids": sources, "updated_by_event": event["id"]}
        self.store.kv_set(f"agent_memory:{chat_id}", memory)
        return {"saved": True, "source_message_ids": sources}

    def _tool_task_record(self, args: dict[str, Any], event: Any, owner: bool) -> dict[str, Any]:
        chat_id = self._chat(args.get("chat_id"), event, owner)
        title = str(args.get("title") or "").strip()[:160]
        description = str(args.get("description") or "").strip()[:16000]
        if not title or not description:
            raise ToolDenied("title_and_description_required")
        sources = self._sources(args.get("source_message_ids"), chat_id)
        version = _digest(f"{title}\n{description}\n{bool(args.get('is_frontend'))}")
        with self.store.transaction():
            tid = args.get("ticket_id")
            if tid:
                ticket = self._ticket(tid, event, owner)
                if ticket["chat_id"] != chat_id:
                    raise ToolDenied("ticket_chat_mismatch")
                if ticket["stage"] in {"hotfix", "sending", "deploy", "verify"}:
                    raise ToolDenied("active_external_work_cannot_be_reclassified")
                tid = int(tid)
            else:
                # The first source anchors creation across model/session retries.
                anchor = sources[0]
                topic_key = str(args.get("topic_key") or "").strip()
                if not topic_key or len(topic_key) > 120:
                    raise ToolDenied("stable_topic_key_required_for_new_task")
                found = self.store.row(
                    "SELECT id FROM tickets WHERE chat_id=? AND json_extract(data,'$.agent.anchor')=? "
                    "AND json_extract(data,'$.agent.topic_key')=?",
                    (chat_id, anchor, topic_key),
                )
                if found:
                    tid = int(found["id"])
                else:
                    tid = self.store.add_ticket(kind="agent_task", source=str(event["source"]),
                        chat_id=chat_id, seller=self.p._seller_for_chat(chat_id, str(event["role"])),
                        stage="agent_discussion", author_id=str(event["author_id"]),
                        category="task", data={"agent": {"anchor": anchor, "topic_key": topic_key}})
            data = self.store.data(tid)
            prior = dict(data.get("agent") or {})
            if prior.get("version") != version:
                prior.pop("author_confirmation", None)
                prior.pop("owner_approval", None)
                prior.pop("mockup", None)
                prior["version"] = version
            prior.update(title=title, description=description, is_frontend=bool(args.get("is_frontend")),
                         source_message_ids=sources)
            if args.get("confirm_author"):
                if str(event["author_id"]) != str(self.store.ticket(tid)["author_id"]):
                    raise ToolDenied("confirmation_requires_actual_author")
                if not owner:
                    sent = self.store.row(
                        "SELECT sent_at FROM outbox WHERE key=? AND status='sent'",
                        (f"agent_process:{tid}:description_confirmation:{version}",),
                    )
                    if sent is None or event["ts"] <= sent["sent_at"]:
                        raise ToolDenied("description_must_be_presented_before_confirmation")
                prior["author_confirmation"] = {"version": version, "message_id": event["id"]}
            self.store.patch_data(tid, agent=prior)
            self.store.set_stage(tid, "agent_discussion")
        document: dict[str, Any] | None = None
        card: dict[str, Any] | None = None
        if args.get("confirm_author"):
            try:
                document = persist_task(self.p, tid)
                card = self._tool_trello_sync({"ticket_id": tid, "action": "create"}, event, True)
                if card["status"] == "linked":
                    self.p.say_owner(f"agent_task_confirmed:{tid}:{version}",
                        f"Задача WMS-{document['number']} подтверждена автором: {title}\n"
                        f"Карточка: {card['url']}\nВетка требований: {document['branch']} "
                        f"({document['sha'][:12]}). Для этапа «Описание согласовано» требуется ваше "
                        "отдельное утверждение этой версии.", tid, "task_notice")
            except (CanonicalTaskError, TrelloError) as exc:
                return {"ticket_id": tid, "version": version, "status": "pending_external",
                        "reason": str(exc)[:200]}
        return {"ticket_id": tid, "version": version,
                "document": document, "card": card,
                "author_confirmed": prior.get("author_confirmation", {}).get("version") == version,
                "owner_approved": prior.get("owner_approval", {}).get("version") == version}

    def _tool_approve_task(self, args: dict[str, Any], event: Any, owner: bool) -> dict[str, Any]:
        tid = int(args["ticket_id"])
        self._ticket(tid, event, owner)
        data = self.store.data(tid)
        agent = dict(data.get("agent") or {})
        if not agent.get("version") or args.get("version") != agent["version"]:
            raise ToolDenied("stale_description")
        agent["owner_approval"] = {"version": agent["version"], "message_id": event["id"]}
        self.store.patch_data(tid, agent=agent)
        return {"approved_version": agent["version"], "source_message_id": event["id"]}

    def _tool_queue_reply(self, args: dict[str, Any], event: Any, owner: bool) -> dict[str, Any]:
        tid = int(args["ticket_id"])
        ticket = self._ticket(tid, event, owner)
        chat_id = int(args["chat_id"])
        if chat_id != ticket["chat_id"]:
            raise ToolDenied("recipient_ticket_mismatch")
        agent = self.store.data(tid).get("agent") or {}
        version = str(args.get("version") or "")
        if version != agent.get("version"):
            raise ToolDenied("stale_description")
        body = str(args.get("text") or "").strip()
        if not body:
            raise ToolDenied("empty_reply")
        key = f"agent_reply:{event['id']}:{tid}:{_digest(body)}"
        created = self.store.queue_message(key=key, chat_id=chat_id, text=body,
                        reply_to=args.get("reply_to"), ticket_id=tid, purpose="owner_authorized",
                        repeat_ok=False)
        return {"queued": created, "key": key, "status": self.store.outbox_by_key(key)["status"],
                "owner_message_id": event["id"], "version": version}

    def _tool_queue_process_reply(self, args: dict[str, Any], event: Any, owner: bool) -> dict[str, Any]:
        tid = int(args["ticket_id"])
        ticket = self._ticket(tid, event, owner)
        kind = str(args.get("kind") or "")
        if kind not in {"necessary_question", "description_confirmation"}:
            raise ToolDenied("process_reply_only")
        body = str(args.get("text") or "").strip()
        if not body or len(body) > 3000:
            raise ToolDenied("invalid_reply")
        agent = self.store.data(tid).get("agent") or {}
        if kind == "description_confirmation" and not agent.get("version"):
            raise ToolDenied("description_missing")
        version = agent.get("version", "discussion")
        key = f"agent_process:{tid}:{kind}:{version}"
        created = self.store.queue_message(key=key, chat_id=ticket["chat_id"], text=body,
                         reply_to=args.get("reply_to"), ticket_id=tid, purpose=kind,
                         repeat_ok=False)
        return {"queued": created, "key": key, "status": self.store.outbox_by_key(key)["status"]}

    def _tool_trello_sync(self, args: dict[str, Any], event: Any, owner: bool) -> dict[str, Any]:
        tid = int(args["ticket_id"])
        self._ticket(tid, event, owner)
        agent = self.store.data(tid).get("agent") or {}
        version = agent.get("version")
        if not version or agent.get("author_confirmation", {}).get("version") != version:
            raise ToolDenied("author_confirmation_required")
        action = str(args.get("action") or "create")
        if action == "create":
            if agent.get("document_version") != version or not agent.get("document_sha") or not agent.get("wms_number"):
                raise ToolDenied("canonical_document_required")
            cfg = self.p.cfg.trello
            chat_id = self.store.ticket(tid)["chat_id"]
            chat_cfg = self.p.cfg.telegram.chats.get(chat_id)
            list_id = (cfg.partner_list_id if chat_cfg and chat_cfg.role == "partner"
                       else cfg.client_list_id)
            result = ensure_card(self.store, self.p.trello, key=f"agent:{tid}", ticket_id=tid,
                                 list_id=list_id, name=f"{agent['title']} [WMS-{agent.get('wms_number', '?')}]",
                                 body=f"{agent['description']}\n\nВерсия: {version}\nИсточник: чат {self.store.ticket(tid)['chat_id']}")
            if result.status == "linked":
                self.store.patch_data(tid, card_id=result.card_id, card_url=result.url)
            return {"status": result.status, "card_id": result.card_id, "url": result.url}
        if action == "description_agreed":
            if agent.get("owner_approval", {}).get("version") != version:
                raise ToolDenied("current_owner_approval_required")
            row = self.store.card(f"agent:{tid}")
            if row is None or row["status"] != "linked":
                raise ToolDenied("card_not_linked")
            list_key = "trello_list:description_agreed"
            list_state = self.store.kv_get(list_key, {})
            list_id = self.p.trello.list_named("Описание согласовано")
            if not list_id:
                if list_state.get("status") in {"creating", "unknown"}:
                    return {"status": "unknown", "reason": "list_creation_outcome_unknown"}
                self.store.kv_set(list_key, {"status": "creating"})
                try:
                    self.p.trello.create_list("Описание согласовано")
                    list_id = self.p.trello.list_named("Описание согласовано")
                except TrelloError as exc:
                    self.store.kv_set(list_key, {"status": "rejected" if exc.rejected else "unknown"})
                    return {"status": "rejected" if exc.rejected else "unknown", "reason": "list_create"}
                if not list_id:
                    self.store.kv_set(list_key, {"status": "unknown"})
                    return {"status": "unknown", "reason": "list_not_visible"}
            self.store.kv_set(list_key, {"status": "confirmed", "list_id": list_id})
            card = self.p.trello.get_card(row["card_id"])
            if card["idList"] != list_id:
                intent = f"agent_card_move:{tid}:{version}"
                state = self.store.kv_get(intent, {})
                if state.get("status") in ("sending", "unknown"):
                    return {"status": "unknown", "card_id": row["card_id"]}
                self.store.kv_set(intent, {"status": "sending", "owner_event": event["id"]})
                try:
                    self.p.trello.move_card(row["card_id"], list_id)
                except TrelloError as exc:
                    self.store.kv_set(intent, {"status": "rejected" if exc.rejected else "unknown"})
                    return {"status": "rejected" if exc.rejected else "unknown"}
                card = self.p.trello.get_card(row["card_id"])
                if card["idList"] != list_id:
                    return {"status": "unknown"}
                self.store.kv_set(intent, {"status": "confirmed"})
            return {"status": "linked", "card_id": row["card_id"], "list_id": list_id}
        raise ToolDenied("unknown_trello_action")

    def _tool_request_mockup(self, args: dict[str, Any], event: Any, owner: bool) -> dict[str, Any]:
        tid = int(args["ticket_id"])
        self._ticket(tid, event, owner)
        agent = self.store.data(tid).get("agent") or {}
        version = agent.get("version")
        if not agent.get("is_frontend") or not version:
            raise ToolDenied("frontend_description_required")
        if agent.get("author_confirmation", {}).get("version") != version:
            raise ToolDenied("author_confirmation_required")
        if agent.get("document_version") != version or not agent.get("document_branch"):
            raise ToolDenied("canonical_document_required")
        key = f"agent_mockup:{tid}:{version}"
        created = self.store.kv_once(key)
        if created:
            # The scheduler runs the dedicated Sonnet runner. It must verify a public URL.
            self.store.patch_data(tid, agent={**agent, "mockup": {"version": version,
                                  "status": "queued", "owner_event": event["id"]}})
        return {"queued": created, "ticket_id": tid, "version": version,
                "model": "sonnet", "status": "queued"}
