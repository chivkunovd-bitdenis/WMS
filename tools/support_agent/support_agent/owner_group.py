"""Смысловая постановка задач в зарегистрированном общем чате, с устойчивой доставкой в Trello."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import prompts
from .llm import LlmError
from .trello import ensure_card, ensure_card_update

if TYPE_CHECKING:
    from .pipeline import Pipeline


class GroupDeliveryPending(Exception):
    """Решение сохранено, внешний результат ещё не подтверждён; сообщение остаётся в очереди."""


class OwnerGroup:
    def __init__(self, pipe: Pipeline) -> None:
        self.pipe, self.store = pipe, pipe.store

    def registered(self, chat_id: int) -> bool:
        return str(chat_id) in self.store.kv_get("owner_task_chats", {})

    def tasks(self, chat_id: int) -> list[dict[str, Any]]:
        result = []
        for t in self.store.rows("SELECT * FROM tickets WHERE chat_id=? AND kind='partner_task' ORDER BY id",
                                 (chat_id,)):
            d = self.store.data(t["id"])
            card = self.store.card(f"task:{t['id']}")
            result.append({"id": t["id"],
                           "title": d.get("group_title") or (d.get("draft") or {}).get("title"),
                           "description": d.get("group_description") or d.get("approved_description") or
                           self.pipe._task_text(d), "stage": t["stage"],
                           "card_status": card["status"] if card else "not_confirmed",
                           "card_url": card["url"] if card and card["status"] == "linked" else None,
                           "delivery": d.get("group_delivery"),
                           "source_message_ids": d.get("group_sources", [])})
        return result

    @staticmethod
    def message(row: Any) -> dict[str, object]:
        return {key: row[key] for key in ("id", "msg_id", "chat_id", "author_id", "author_name",
                                         "ts", "text", "reply_to", "kind")}

    def say(self, m: Any, suffix: str, text: str, tid: int | None = None) -> None:
        self.store.queue_message(key=f"owner_group:{m['id']}:{suffix}", chat_id=m["chat_id"], text=text,
                                 reply_to=m["msg_id"], ticket_id=tid, purpose="owner_group", repeat_ok=False)

    def handle(self, m: Any) -> None:
        key = f"owner_group_decision:{m['id']}"
        decision = self.store.kv_get(key)
        if decision is None:
            history = [self.message(row) for row in self.store.rows(
                "SELECT * FROM messages WHERE chat_id=? AND id<=? AND text!='' ORDER BY ts,id",
                (m["chat_id"], m["id"]),
            )]
            tasks = self.tasks(m["chat_id"])
            parsed, _ = self.pipe.llm.ask_json(
                "routine", prompts.owner_group_prompt(self.message(m), history,
                    self.store.kv_get(f"owner_group_memory:{m['chat_id']}", []), tasks),
                system=prompts.OWNER_GROUP_SYSTEM,
            )
            decision = self.validate(parsed, m, history, tasks)
            # Всё решение и локальные задачи фиксируются до первого внешнего действия.
            with self.store.transaction():
                existing = self.store.kv_get(key)
                if existing is None:
                    self.prepare(decision, m)
                    self.store.kv_set(key, decision)
                    memory_key = f"owner_group_memory:{m['chat_id']}"
                    memory = self.store.kv_get(memory_key, [])
                    for fact in decision["facts"]:
                        if fact not in memory:
                            memory.append(fact)
                    self.store.kv_set(memory_key, memory)
                else:
                    decision = existing
        if decision["scope"] != "wms":
            self.say(m, "scope", prompts.SCOPE_REFUSAL)
            return
        if decision["intent"] == "blocked":
            self.say(m, "blocked", "В общем чате ставлю задачи WMS. Выкладку и изменения продукта "
                     "здесь не запускаю; такие действия подтверждаются в личном чате владельца.")
            return
        pending = False
        for index, action in enumerate(decision["actions"]):
            if action.get("done"):
                continue
            if action["kind"] == "no_action":
                action["done"] = True
            elif action["kind"] == "status":
                self.status(m, action.get("ticket_id"), index)
                action["done"] = True
            else:
                action["done"] = self.deliver(m, action, index)
                pending = pending or not action["done"]
            self.store.kv_set(key, decision)
        if pending:
            raise GroupDeliveryPending()

    def validate(self, parsed: dict[str, Any], m: Any, history: list[dict[str, object]],
                 tasks: list[dict[str, Any]]) -> dict[str, Any]:
        if parsed.get("scope") != "wms":
            return {"scope": "off_topic", "intent": "discussion", "facts": [], "actions": []}
        intent = parsed.get("intent")
        if intent not in ("request", "agreement", "discussion", "question", "canceled", "blocked"):
            raise LlmError("invalid_group_intent")
        if intent == "blocked":
            return {"scope": "wms", "intent": intent, "facts": [], "actions": []}
        messages = {row["id"]: row for row in history}
        known = {row["id"]: row for row in tasks}
        actions, facts = parsed.get("actions"), parsed.get("facts")
        if not isinstance(actions, list) or not isinstance(facts, list):
            raise LlmError("invalid_group_decision")
        validated = []
        for item in actions:
            if (not isinstance(item, dict)
                    or item.get("kind") not in ("create", "update", "status", "no_action")):
                raise LlmError("invalid_group_action")
            kind, tid = item["kind"], item.get("ticket_id")
            if tid is not None and (type(tid) is not int or tid not in known):
                raise LlmError("group_task_not_in_chat")
            if kind == "update" and tid is None or kind == "create" and tid is not None:
                raise LlmError("invalid_group_target")
            action: dict[str, Any] = {"kind": kind, "ticket_id": tid}
            if kind in ("create", "update"):
                ids = item.get("source_message_ids")
                allowed = intent in ("request", "agreement") or (intent == "canceled" and kind == "update")
                if (not allowed or not isinstance(ids, list) or m["id"] not in ids
                        or any(type(mid) is not int or mid not in messages for mid in ids)):
                    raise LlmError("ungrounded_group_action")
                title, description = item.get("title"), item.get("description")
                if kind == "update" and (not isinstance(title, str) or not title.strip()):
                    title = known[tid]["title"] or "Задача WMS"
                if not isinstance(title, str) or not title.strip() or not isinstance(description, str) \
                        or not description.strip():
                    raise LlmError("invalid_group_description")
                raw = "\n".join(str(messages[mid]["text"]) for mid in dict.fromkeys(ids))
                draft = self.pipe._grounded_partner_draft(raw, [], {
                    "title": title, "essence": description, "expected": description, "notes": [],
                })
                action.update(title=draft["title"], description=draft["expected"], source_message_ids=ids,
                              raw=raw)
            if action not in validated:
                validated.append(action)
        checked_facts = []
        for fact in facts:
            if not isinstance(fact, dict):
                raise LlmError("invalid_group_fact")
            mid, quote = fact.get("message_id"), fact.get("quote")
            if (type(mid) is not int or mid not in messages or not isinstance(quote, str) or not quote.strip()
                    or quote not in str(messages[mid]["text"]) or fact.get("state") not in
                    ("idea", "agreed", "canceled", "question") or not isinstance(fact.get("topic"), str)):
                raise LlmError("ungrounded_group_fact")
            checked_facts.append({"topic": fact["topic"], "state": fact["state"], "message_id": mid,
                                  "quote": quote, "author_id": messages[mid]["author_id"]})
        return {"scope": "wms", "intent": intent, "facts": checked_facts, "actions": validated}

    def prepare(self, decision: dict[str, Any], m: Any) -> None:
        for index, action in enumerate(decision["actions"]):
            if action["kind"] != "create":
                continue
            # Точный повтор карточки не зависит от выбранного моделью слова create/update.
            duplicate = next((task for task in self.tasks(m["chat_id"])
                              if task["title"] == action["title"]
                              and task["description"] == action["description"]), None)
            if duplicate:
                action.update(kind="no_action", ticket_id=duplicate["id"])
                continue
            tid = self.store.add_ticket(
                kind="partner_task", source=m["source"], chat_id=m["chat_id"],
                seller=self.pipe._chat_label(m["chat_id"]), author_id=m["author_id"],
                stage="group_pending", category="task", now=self.pipe.clock(),
                data={"owner_group": True, "raw": action["raw"], "msg_id": m["msg_id"],
                      "author_name": m["author_name"], "group_title": action["title"],
                      "group_description": action["description"],
                      "group_sources": action["source_message_ids"],
                      "group_delivery": {"operation": f"{m['id']}:{index}", "status": "pending"}},
            )
            action["ticket_id"] = tid

    def deliver(self, m: Any, action: dict[str, Any], index: int) -> bool:
        tid, operation = action["ticket_id"], f"{m['id']}:{index}"
        d = self.store.data(tid)
        previous = d.get("group_delivery") or {}
        if previous.get("operation") != operation and previous.get("status") in ("pending", "unknown"):
            return False  # не перезаписываем ещё не подтверждённое предыдущее уточнение
        if not self.pipe.cfg.trello.api_key:
            self.say(m, f"unconfigured:{index}", "Задача сохранена. Trello пока не настроен; "
                     "создание или обновление карточки не подтверждено.", tid)
            return False
        if action["kind"] == "create":
            result = ensure_card(self.store, self.pipe.trello, key=f"task:{tid}", ticket_id=tid,
                                 list_id=self.pipe.cfg.trello.partner_list_id, name=action["title"],
                                 body=action["description"] + "\n\nИсточник: "
                                 + self.pipe._chat_label(m["chat_id"]) + ", "
                                 + self.pipe._chat_link(m["chat_id"], m["msg_id"]))
        else:
            result = ensure_card_update(self.store, self.pipe.trello, key=f"task:{tid}",
                                        operation=f"group:{operation}",
                                        addition=f"Уточнение от {m['author_name']}:\n{action['description']}")
        if result.status != "linked":
            self.store.patch_data(tid, group_delivery={"operation": operation, "status": result.status})
            self.say(m, f"delivery:{index}:{result.status}",
                     "Результат Trello пока не подтверждён; задача и поручение сохранены. "
                     "При неизвестном исходе повторную карточку не создаю.", tid)
            return False
        with self.store.transaction():
            # История уточнений накапливается без удаления прежних договорённостей.
            description = str(d.get("group_description") or d.get("approved_description")
                              or self.pipe._task_text(d))
            if action["kind"] == "update":
                description += f"\n\nУточнение от {m['author_name']}:\n{action['description']}"
            self.store.set_stage(tid, "done", owner_group=True,
                                 group_title=d.get("group_title") or action["title"],
                                 group_description=description,
                                 group_sources=list(dict.fromkeys(d.get("group_sources", [])
                                                                 + action["source_message_ids"])),
                                 group_delivery={"operation": operation, "status": "confirmed"},
                                 card_id=result.card_id, card_url=result.url)
            self.say(m, f"confirmed:{index}",
                     f"{'Создана задача' if action['kind'] == 'create' else 'Задача обновлена'}: "
                     f"{d.get('group_title') or action['title']}\n{result.url or ''}", tid)
            # Даже сбой после транзакции не добавит уточнение/сообщение второй раз.
            action["done"] = True
            decision = self.store.kv_get(f"owner_group_decision:{m['id']}")
            decision["actions"][index] = action
            self.store.kv_set(f"owner_group_decision:{m['id']}", decision)
        return True

    def status(self, m: Any, tid: int | None, index: int) -> None:
        tasks = [task for task in self.tasks(m["chat_id"]) if tid is None or task["id"] == tid]
        lines = []
        for task in tasks:
            delivery = task.get("delivery") or {}
            state = ("карточка подтверждена" if task["card_status"] == "linked"
                     else "карточка не подтверждена")
            if delivery.get("status") not in (None, "confirmed"):
                state += "; последнее поручение ожидает подтверждения Trello"
            lines.append(f"№{task['id']} {task['title'] or 'Задача'}: {state}. "
                         f"Реализация не подтверждена. {task['card_url'] or ''}")
        self.say(m, f"status:{index}", "\n".join(lines) if lines else "В этом чате пока нет созданных задач.")
