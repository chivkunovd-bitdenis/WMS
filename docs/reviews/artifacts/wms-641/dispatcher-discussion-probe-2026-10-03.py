"""One bounded real Sol client discussion turn with isolated capture tools."""

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
                           _owner_snapshot=lambda: [], _is_bind_reply=lambda *_: None)
    calls: list[dict[str, Any]] = []

    class CaptureTools:
        def specs(self, scope: str) -> list[dict[str, Any]]:
            return AgentTools(pipe).specs(scope)

        def dispatch(self, name: str, args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
            calls.append({"name": name, "args": args})
            if name == "read_context":
                return {"messages": [dict(r) for r in store.rows(
                    "SELECT * FROM messages WHERE chat_id=-101 ORDER BY id", ())]}
            return {"recorded_in_isolated_fixture": True}

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
    prohibited = [c for c in calls if c["name"] in ("approve_task", "trello_sync", "project_job")
                  or (c["name"] == "task_record" and c["args"].get("confirm_author"))]
    output = {"scope": "one actual Sol5.6 client topic turn; capture tools only; fixture SQLite/repo; no external writes",
              "model": cfg.agent.owner_model, "input": texts,
              "tool_calls": calls, "result_summary": result.get("summary"),
              "result_next_action": result.get("next_action"),
              "prohibited_consequential_calls": prohibited,
              "no_canonical_publish_or_approval": not prohibited,
              "cancelled_deletion_not_in_next_action": "удален" not in str(result.get("next_action", "")).lower(),
              "passed": not prohibited}
    target = Path(__file__).with_suffix(".json")
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(target), "passed": output["passed"]}), flush=True)
    if not output["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
