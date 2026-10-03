"""One bounded real Sol client turn with actual local tools and no external writes."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools" / "support_agent"))

from support_agent.agent_coordinator import AgentCoordinator  # noqa: E402
from support_agent.agent_tools import AgentTools  # noqa: E402
from support_agent.config import config_from_dict  # noqa: E402
from support_agent.llm import LlmRouter  # noqa: E402
from support_agent.store import Store  # noqa: E402


def main() -> None:
    work = ROOT / ".bot-audit-20261003" / "dispatcher-discussion-acceptance"
    work.mkdir(parents=True, exist_ok=True)
    repo = work / "repo"
    repo.mkdir(exist_ok=True)
    db = work / "state.sqlite"
    if db.exists():
        db.unlink()
    cfg = config_from_dict({"repo": str(repo), "state_dir": str(work / "state"),
                            "telegram": {"owner_user_id": 42, "owner_chat_id": 900,
                                         "chats": {"-101": {"role": "client", "seller": "Synthetic"}}},
                            "agent": {"enabled": True}})
    store = Store(db)
    real_llm = LlmRouter(cfg, store)

    class BoundedLlm:
        def agent_turn(self, prompt: str, **kwargs: Any):
            kwargs["timeout"] = min(int(kwargs.get("timeout", 90)), 90)
            return real_llm.agent_turn(prompt, **kwargs)

    pipe = SimpleNamespace(cfg=cfg, store=store, llm=BoundedLlm(), clock=time.time,
                           _owner_snapshot=lambda: [], _is_bind_reply=lambda *_: None,
                           _seller_for_chat=lambda *_: "Synthetic",
                           say_owner=lambda key, text, ticket_id=None, purpose="notice":
                           store.queue_message(key=key, chat_id=900, text=text,
                                               ticket_id=ticket_id, purpose=purpose,
                                               repeat_ok=True))
    calls: list[dict[str, Any]] = []
    real_tools = AgentTools(pipe)

    class CaptureTools:
        def specs(self, scope: str) -> list[dict[str, Any]]:
            return real_tools.specs(scope)

        def dispatch(self, name: str, args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
            calls.append({"name": name, "args": args})
            if name == "task_record" and args.get("confirm_author"):
                return {"error": "fixture_blocks_canonical_publishing"}
            if name not in {"read_context", "remember", "task_record",
                            "queue_process_reply", "owner_digest", "read_data"}:
                return {"error": "fixture_blocks_external_action"}
            return real_tools.dispatch(name, args, context)

    agent = AgentCoordinator(pipe, CaptureTools())
    texts = [
        "Может, добавим кнопку массового удаления всех ошибочных сканов? Пока обсуждаем идею.",
        "Нет, массовое удаление отменяем. Лучше показывать причину ошибки прямо рядом со сканом.",
        "Да, при сканировании нераспознанного кода нужно видеть понятную причину рядом с ним. "
        "Если нужны детали процесса — спросите, прежде чем заводить окончательную задачу.",
    ]
    ids = []
    for index, text in enumerate(texts):
        message_id = store.add_message(source="telegram", chat_id=-101, msg_id=f"client-{index}",
                                       role="client", author_id="7", author_name="Client",
                                       ts=time.time() + index, kind="text", text=text,
                                       file_id=None, reply_to=None)
        assert message_id is not None
        ids.append(message_id)
    topic_id = f"topic-{ids[0]}"
    topic = {"id": topic_id, "chat_id": -101,
             "summary": "Обсуждают обработку ошибочных сканов; удаление отменено.",
             "next_action": "Уточнить текущую договорённость до оформления задачи.",
             "status": "queued", "priority": 1, "pending": [], "generation": 0,
             "task_ids": [], "affected_areas": []}
    store.kv_set(f"agent_topic:{topic_id}", topic)
    event = {"id": f"in:{ids[-1]}:1", "kind": "input", "source_id": ids[-1],
             "revision": 1, "chat_id": -101, "owner": False, "text": texts[-1], "ts": time.time()}
    source = store.row("SELECT * FROM messages WHERE id=?", (ids[-1],))
    result = agent.run_topic_turn(topic, event, source)
    tickets = store.rows("SELECT * FROM tickets ORDER BY id", ())
    outbox = store.rows("SELECT * FROM outbox ORDER BY id", ())
    memory = store.kv_get("agent_memory:-101", {})
    prohibited = [c for c in calls if c["name"] in ("approve_task", "trello_sync", "project_job")
                  or (c["name"] == "task_record" and c["args"].get("confirm_author"))]
    draft = [t for t in tickets if t["stage"] == "agent_discussion"]
    question = [m for m in outbox if m["purpose"] == "necessary_question" and m["chat_id"] == -101]
    digest = [m for m in outbox if m["purpose"] == "agent_digest" and m["chat_id"] == 900]
    output = {"scope": "one actual Sol5.6 client topic turn; actual local tools; fixture SQLite/repo; no external writes",
              "model": cfg.agent.owner_model, "input": texts,
              "tool_calls": calls, "result_summary": result.get("summary"),
              "result_next_action": result.get("next_action"),
              "prohibited_consequential_calls": prohibited,
              "ticket_ids": [t["id"] for t in tickets],
              "draft_ticket_ids": [t["id"] for t in draft],
              "queued_question_ids": [m["id"] for m in question],
              "queued_owner_digest_ids": [m["id"] for m in digest],
              "memory_sources": memory.get("source_message_ids", []),
              "no_canonical_publish_or_approval": not prohibited and all(
                  not (store.data(t["id"]).get("agent") or {}).get("author_confirmation")
                  for t in tickets),
              "cancelled_deletion_not_in_next_action": "удален" not in str(result.get("next_action", "")).lower(),
              "passed": bool(draft and question and digest and memory and not prohibited)}
    target = Path(__file__).with_suffix(".json")
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(target), "passed": output["passed"]}), flush=True)
    if not output["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
