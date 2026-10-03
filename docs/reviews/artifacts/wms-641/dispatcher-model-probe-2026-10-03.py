"""Bounded Sol semantic acceptance on synthetic local state; no external writes."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools" / "support_agent"))

from support_agent.agent_coordinator import AgentCoordinator  # noqa: E402
from support_agent.config import config_from_dict  # noqa: E402
from support_agent.llm import LlmRouter  # noqa: E402
from support_agent.store import Store  # noqa: E402


def main() -> None:
    work = ROOT / ".bot-audit-20261003" / "dispatcher-model-acceptance"
    work.mkdir(parents=True, exist_ok=True)
    db = work / "state.sqlite"
    cfg = config_from_dict({"repo": str(ROOT), "state_dir": str(work / "state"),
                            "telegram": {"owner_user_id": 42, "owner_chat_id": 900},
                            "agent": {"enabled": True}})
    store = Store(db)

    class Tools:
        def specs(self, scope: str) -> list[dict]:
            return []

    llm = LlmRouter(cfg, store)
    pipe = SimpleNamespace(cfg=cfg, store=store, llm=llm, clock=time.time,
                           _owner_snapshot=lambda: [], _is_bind_reply=lambda *_: None)
    agent = AgentCoordinator(pipe, Tools())
    existing = store.row("SELECT id FROM tickets LIMIT 1")
    ticket_id = int(existing["id"]) if existing else store.add_ticket(
        kind="chat", source="telegram", chat_id=-101, seller="Synthetic",
        stage="owner_review", author_id="7",
        data={"agent": {"version": "v1", "title": "Обработано",
                        "description": "Обработано: версия v1"}})

    def owner(text: str, name: str):
        prior = store.row("SELECT * FROM messages WHERE msg_id=?", (name,))
        if prior:
            return prior
        message_id = store.add_message(source="telegram", chat_id=900, msg_id=name,
                                       role="owner", author_id="42", author_name="Owner",
                                       ts=time.time(), kind="text", text=text, file_id=None,
                                       reply_to=None)
        assert message_id is not None
        return store.row("SELECT * FROM messages WHERE id=?", (message_id,))

    weak = owner("посмотри поставку", "weak")
    strong = owner(f"Утверждаю описание задачи {ticket_id} «Обработано», версия v1.", "strong")
    args = {"ticket_id": ticket_id, "version": "v1", "kind": "description"}
    weak_decision = next((json.loads(r["value"]) for r in store.rows(
        "SELECT value FROM kv WHERE key LIKE 'agent_semantic_auth:%'", ())
        if "посмотри поставку" in json.loads(r["value"]).get("reason", "")), None)
    if weak_decision is None:
        weak_decision = agent.semantic_verifier.check(weak, "approve_task", args)
    # The first run exposed an absent verified-private fact. Evict only the
    # prior rejected strong decision after that product defect is repaired.
    for row in store.rows("SELECT key,value FROM kv WHERE key LIKE 'agent_semantic_auth:%'", ()):
        if "приватный тип чата не подтверждён" in json.loads(row["value"]).get("reason", ""):
            store.execute("DELETE FROM kv WHERE key=?", (row["key"],))
    strong_decision = agent.semantic_verifier.check(strong, "approve_task", args)

    multi = owner("Параллельно разбери два независимых вопроса: (1) почему неверно печатается QR на коробе, (2) почему долго загружается список ячеек. Верни два отдельных результата.", "multi")
    agent.dispatcher.accept(multi)
    agent.dispatcher._route_once()
    topics = [store.kv_get(f"agent_topic:{tid}") for tid in store.kv_get("agent_topic_index", [])]
    multi_topics = [t for t in topics if t and t.get("chat_id") == 900]
    output = {
        "scope": "actual Sol5.6 medium via authenticated Codex CLI; synthetic SQLite; no real Telegram/Trello/Git writes",
        "model": cfg.agent.owner_model,
        "weak_source": weak["text"], "weak_approve_authorized": weak_decision["authorized"],
        "weak_reason": weak_decision["reason"],
        "strong_source": strong["text"], "strong_approve_authorized": strong_decision["authorized"],
        "strong_quote": strong_decision["source_quote"],
        "one_owner_message_topic_ids": [t["id"] for t in multi_topics],
        "one_owner_message_subrequests": [
            store.kv_get(f"agent_event:{t['pending'][0]}", {}).get("subrequest", "")
            for t in multi_topics],
        "passed": (not weak_decision["authorized"] and strong_decision["authorized"]
                   and len(multi_topics) >= 2),
    }
    target = Path(__file__).with_suffix(".json")
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(target), "passed": output["passed"]}), flush=True)
    if not output["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
