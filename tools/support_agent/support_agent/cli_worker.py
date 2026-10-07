"""One durable Sol 6.1 investigation when native moderator slots are occupied.

Invoked by the visible moderator, never by the intake loop. Results go back to
its durable inbox; this worker has no Telegram/Trello action tools.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import time
from typing import Any

from .config import load_config
from .llm import extract_json
from .runner import build_agent


def run_worker(config_path: str | None, topic_id: str, source_id: int,
               thread_id: str | None = None, worker_id: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    agent = build_agent(cfg)
    coordinator = agent.pipe.agent
    if coordinator is None:
        # Intake-only disables the legacy autonomous coordinator globally. A
        # one-shot explicitly assigned worker needs only its local helpers;
        # never register it on the poller or call dispatcher.tick/recover.
        from .agent_coordinator import AgentCoordinator
        from .agent_tools import AgentTools

        coordinator = AgentCoordinator(agent.pipe, AgentTools(agent.pipe))
    store = agent.store
    topic = store.kv_get(f"agent_topic:{topic_id}", {})
    if not topic:
        raise ValueError("topic must first be assigned by the moderator")
    source = store.row("SELECT * FROM messages WHERE id=?", (source_id,))
    if source is None or (int(source["chat_id"]) != int(topic["chat_id"])
                          and not coordinator._owner(source)):
        raise ValueError("source message does not belong to this topic's chat")
    event_id = f"in:{source_id}:{source['revision']}"
    for candidate in topic.get("pending", []):
        pending = store.kv_get(f"agent_event:{candidate}", {})
        if pending.get("source_id") == source_id and pending.get("revision") == int(source["revision"]):
            event_id = candidate
            break
    event = store.kv_get(f"agent_event:{event_id}", {})
    if not event:
        raise ValueError("source event must first enter the durable moderator inbox")
    lock_root = cfg.state_path / "cli-workers"
    lock_root.mkdir(parents=True, exist_ok=True)
    lock_path = lock_root / (hashlib.sha256(topic_id.encode()).hexdigest() + ".lock")
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("this topic already has a running CLI worker") from exc
        if store.kv_get(f"agent_event_done:{event_id}"):
            return {"status": "already_completed", "topic_id": topic_id}
        claim = store.kv_get(f"agent_native_claim:{event_id}", {})
        if worker_id and claim.get("worker_id") not in (None, worker_id):
            raise ValueError("event belongs to another active worker")
        worker_key = f"agent_cli_worker:{topic_id}"
        worker = {"pid": os.getpid(), "status": "running", "source_id": source_id,
                  "event_id": event_id, "started_at": time.time(), "topic_id": topic_id,
                  "worker_id": worker_id or claim.get("worker_id")}
        store.kv_set(worker_key, worker)
        delivered: list[str] = []
        offered: list[str] = []

        def live_inputs() -> list[dict[str, Any]]:
            worker["updated_at"] = time.time()
            store.kv_set(worker_key, worker)
            fresh = store.kv_get(f"agent_topic:{topic_id}", {})
            entries: list[dict[str, Any]] = []
            offered.clear()
            for eid in fresh.get("pending", []):
                if eid == event_id or eid in delivered:
                    continue
                item = store.kv_get(f"agent_event:{eid}", {})
                if item.get("kind") != "input":
                    continue
                row = store.row("SELECT * FROM messages WHERE id=?", (item.get("source_id"),))
                if row is None or int(row["revision"]) != int(item.get("revision", 1)):
                    continue
                offered.append(eid)
                entries.append({"type": "text", "text": json.dumps(
                    {"additional_source": dict(row), "event": item}, ensure_ascii=False, default=str)})
                if hasattr(agent.pipe, "message_image_paths"):
                    entries.extend({"type": "localImage", "path": path}
                                   for path in agent.pipe.message_image_paths(row))
            return entries

        def acknowledge(_entries: list[dict[str, Any]]) -> None:
            delivered.extend(offered)
            offered.clear()

        def progress(text: str) -> None:
            if text.strip():
                coordinator.journal.record(int(topic["chat_id"]), "worker_progress", text,
                    f"cli-progress:{event_id}:{hashlib.sha256(text.encode()).hexdigest()[:16]}", topic_id)

        prompt = json.dumps({"topic": topic, "source": dict(source), "event": event,
            "history_root": str(coordinator.journal.root),
            "instructions": "Ты исполнитель обращения, назначенный видимым модератором. "
            "Изучи полную историю чата, вложения, код и доступные данные. Сам установи смысл "
            "запроса и причину. Ничего не отправляй в Telegram, не управляй ключами и не "
            "меняй production. Сохрани результаты исследования, источники, предлагаемый "
            "ответ и следующий шаг. Уточняющий вопрос предлагай лишь если важный факт "
            "нельзя установить самостоятельно. Все дополнения относятся к этому же "
            "продолжаемому разбору. Заверши JSON: summary, result, next_action, "
            "development_needed, task_needed, owner_needed; значения должны отражать факты."},
            ensure_ascii=False, default=str)
        try:
            result = agent.pipe.llm.agent_turn(
                prompt, session_key=f"topic:{topic_id}", session_id=thread_id,
                session_name=f"Обращение {topic_id} · CLI-разбор", mode="readonly",
                system=coordinator.system, include_project_tools=False,
                image_paths=(agent.pipe.message_image_paths(source)
                             if hasattr(agent.pipe, "message_image_paths") else []),
                live_inputs=live_inputs, inputs_delivered=acknowledge,
                cancelled=lambda: bool(store.kv_get(f"agent_topic:{topic_id}", {}).get("cancel_requested")),
                progress_callback=progress,
            )
            try:
                conclusion = extract_json(result.text)
            except ValueError:
                conclusion = {"summary": result.text[:1500], "result": result.text,
                              "next_action": "moderator_review"}
            conclusion.setdefault("result", result.text)
            conclusion["worker_session_id"] = result.session_id
            conclusion["consumed_event_ids"] = delivered
            coordinator.journal.record(int(topic["chat_id"]), "worker_result", result.text,
                                       f"cli-result:{event_id}", topic_id, conclusion)
            # Durable completion and notification precede process exit.
            coordinator.dispatcher._finish_event(topic_id, event_id, conclusion)
            worker.update(status="completed", session_id=result.session_id,
                          context_tokens=result.context_tokens, finished_at=time.time())
            store.kv_set(worker_key, worker)
            return {"status": "completed", "topic_id": topic_id,
                    "session_id": result.session_id, "context_tokens": result.context_tokens}
        except Exception as exc:
            worker.update(status="failed", error=type(exc).__name__, finished_at=time.time())
            store.kv_set(worker_key, worker)
            coordinator.dispatcher.emit_internal(topic_id, "worker_error", {
                "event_key": f"cli-error:{event_id}:{worker['started_at']}",
                "summary": f"CLI-разбор не завершён: {type(exc).__name__}; сообщения сохранены",
                "source_event": event_id})
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--topic-id", required=True)
    parser.add_argument("--source-id", required=True, type=int)
    parser.add_argument("--thread-id")
    parser.add_argument("--worker-id")
    args = parser.parse_args()
    print(json.dumps(run_worker(args.config, args.topic_id, args.source_id, args.thread_id, args.worker_id),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
