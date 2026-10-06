"""Bounded real-model acceptance on synthetic messages and isolated SQLite only.

No Telegram, Trello, production DB, Git remote or WMS API operation is performed.
Canonical publication and Trello are replaced only at their external boundary.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools" / "support_agent"))

import support_agent.agent_tools as agent_tools_module  # noqa: E402
from support_agent.agent_coordinator import AgentCoordinator  # noqa: E402
from support_agent.agent_tools import AgentTools  # noqa: E402
from support_agent.config import config_from_dict  # noqa: E402
from support_agent.llm import LlmRouter  # noqa: E402
from support_agent.store import Store  # noqa: E402


def main() -> None:
    work = ROOT / ".bot-audit-20261003" / "model-intake-fixture"
    work.mkdir(parents=True, exist_ok=True)
    (work / "README.md").write_text(
        "Это синтетический мини-проект. Экран «Ячейки» показывает ячейки и количество; "
        "сектор сейчас не показывается. Данные тестовые.\n", encoding="utf-8"
    )
    db = work / "state.sqlite"
    continue_run = "--continue" in sys.argv
    if db.exists() and not continue_run:
        db.unlink()
    cfg = config_from_dict({
        "repo": str(work), "state_dir": str(work / "state"),
        "telegram": {"owner_user_id": 42, "owner_chat_id": 900,
                     "chats": {"-555": {"role": "client", "seller": "Тестовый клиент"}}},
        "agent": {"enabled": True, "owner_model": "gpt-5.6-sol", "owner_provider": "codex"},
        "llm": {"codex_effort": "low"},
    })
    store = Store(db)
    llm = LlmRouter(cfg, store)
    notices: list[dict] = []
    calls: list[dict] = []
    original_turn = llm.agent_turn

    def recorded_turn(prompt: str, **kwargs):
        original_handler = kwargs["tool_handler"]

        def handler(name: str, args: dict):
            result = original_handler(name, args)
            calls.append({"tool": name, "args": args, "result": result})
            return result

        kwargs["tool_handler"] = handler
        return original_turn(prompt, **kwargs)

    llm.agent_turn = recorded_turn  # type: ignore[method-assign]

    def say_owner(key: str, text: str, ticket_id: int | None = None, purpose: str = ""):
        notices.append({"key": key, "text": text, "ticket_id": ticket_id, "purpose": purpose})
        store.queue_message(key=key, chat_id=900, text=text, ticket_id=ticket_id,
                            purpose=purpose, repeat_ok=False)

    pipe = SimpleNamespace(
        cfg=cfg, store=store, llm=llm, clock=time.time,
        _owner_snapshot=lambda: [], _seller_for_chat=lambda *_: "Тестовый клиент",
        say_owner=say_owner, trello=SimpleNamespace(),
    )
    tools = AgentTools(pipe)
    coordinator = AgentCoordinator(pipe, tools)

    def fake_persist(_pipe, ticket_id: int):
        agent = dict(store.data(ticket_id)["agent"])
        agent.update(wms_number=999991, document_sha="a" * 40,
                     document_branch="synthetic/WMS-999991", document_version=agent["version"])
        store.patch_data(ticket_id, agent=agent)
        return {"number": 999991, "sha": "a" * 40, "branch": "synthetic/WMS-999991"}

    agent_tools_module.persist_task = fake_persist

    def fake_trello(args, _event, _owner):
        return {"status": "linked", "card_id": "synthetic-card", "url": "https://invalid.test/card"}

    tools._tool_trello_sync = fake_trello  # type: ignore[method-assign]

    text1 = (
        "Хочу в разделе Ячейки новую колонку Сектор перед колонкой Ячейка. "
        "Если у ячейки сектор не задан, показывайте прочерк. Остальные колонки оставьте как сейчас. "
        "Давайте согласуем описание, чтобы потом завести задачу."
    )
    if not continue_run:
        event1 = store.add_message(source="telegram", chat_id=-555, msg_id="synthetic-1", role="client",
                                   author_id="77", author_name="Автор", ts=time.time(), kind="text",
                                   text=text1, file_id=None, reply_to=None)
        coordinator.handle_message(store.row("SELECT * FROM messages WHERE id=?", (event1,)))
        first = {"calls": list(calls), "notices": list(notices),
                 "outbox": [dict(x) for x in store.rows("SELECT key,purpose,text,status FROM outbox")],
                 "tickets": [dict(x) for x in store.rows("SELECT id,stage,data FROM tickets")]}
        print(json.dumps({"step": "initial", "tools": [c["tool"] for c in calls]}), flush=True)
    else:
        first = json.loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))["first"]
    clarification: dict = {}
    if not store.rows("SELECT id FROM outbox WHERE purpose='description_confirmation'"):
        existing2 = store.row("SELECT id FROM messages WHERE msg_id='synthetic-2'") is not None
        next_msg_id = "synthetic-3" if existing2 else "synthetic-2"
        next_text = ("Пришлите, пожалуйста, пошаговое описание прямо сейчас и спросите, "
                     "всё ли верно. Это задача на доработку." if existing2 else
                     "Да, это именно задача на доработку. Опиши простыми шагами, как понял, и спроси, всё ли верно.")
        event2 = store.add_message(source="telegram", chat_id=-555, msg_id=next_msg_id, role="client",
                                   author_id="77", author_name="Автор", ts=time.time() + 5,
                                   kind="text", text=next_text,
                                   file_id=None, reply_to="synthetic-1")
        coordinator.handle_message(store.row("SELECT * FROM messages WHERE id=?", (event2,)))
        clarification = {"calls": list(calls),
                         "outbox": [dict(x) for x in store.rows(
                             "SELECT key,purpose,text,status FROM outbox")]}
        print(json.dumps({"step": "clarification", "tools": [c["tool"] for c in calls]}), flush=True)

    pending = store.rows("SELECT id FROM outbox WHERE purpose='description_confirmation'")
    if pending:
        store.finish_outbox(pending[0]["id"], "sent", "synthetic-outbox-1")
        confirmation_id = "synthetic-4" if store.row(
            "SELECT id FROM messages WHERE msg_id='synthetic-3'") else "synthetic-3"
        event3 = store.add_message(source="telegram", chat_id=-555, msg_id=confirmation_id, role="client",
                                   author_id="77", author_name="Автор", ts=time.time() + 5,
                                   kind="text", text="Да, это описание верно. Подтверждаю задачу.",
                                   file_id=None, reply_to="synthetic-outbox-1")
        # Restore SQLite and model thread ID from disk between turns.
        store.db.close()
        store = Store(db)
        llm = LlmRouter(cfg, store)
        pipe.store = store
        pipe.llm = llm
        tools = AgentTools(pipe)
        tools._tool_trello_sync = fake_trello  # type: ignore[method-assign]
        coordinator = AgentCoordinator(pipe, tools)
        calls.clear()
        original_turn = llm.agent_turn
        llm.agent_turn = recorded_turn  # type: ignore[method-assign]
        coordinator.handle_message(store.row("SELECT * FROM messages WHERE id=?", (event3,)))
    final = {"calls": list(calls), "notices": list(notices),
             "outbox": [dict(x) for x in store.rows("SELECT key,purpose,text,status FROM outbox")],
             "tickets": [dict(x) for x in store.rows("SELECT id,stage,data FROM tickets")],
             "memory": store.kv_get("agent_memory:-555", {})}
    artifact = {"scope": "synthetic messages; real Codex model; external transports mocked",
                "first": first, "clarification": clarification, "after_restart": final}
    target = Path(__file__).with_suffix(".json")
    target.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(target), "final_tools": [c["tool"] for c in calls]}), flush=True)


if __name__ == "__main__":
    main()
