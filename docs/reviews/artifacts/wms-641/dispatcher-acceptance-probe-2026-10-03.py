"""Synthetic §13 dispatcher acceptance; all external transports are absent."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools" / "support_agent"))

from support_agent.agent_coordinator import AgentCoordinator  # noqa: E402
from support_agent.config import config_from_dict  # noqa: E402
from support_agent.llm import LlmResult  # noqa: E402
from support_agent.store import Store  # noqa: E402


class RouteModel:
    """Deterministic model for concurrency only; semantics is tested separately."""

    def agent_turn(self, prompt: str, **kwargs: Any) -> LlmResult:
        assert kwargs["session_key"] == "agent:dispatcher"
        data = json.loads(prompt)
        routes = []
        for event in data["events"]:
            eid = event["id"]
            text = str(event.get("text") or "").lower()
            if event["kind"] == "input" and "две задачи" in text:
                stem = f"topic-{event['source_id']}"
                routes.append({"event_id": eid, "topics": [
                    {"topic_id": stem + "-1", "subrequest": "Разобрать задачу А", "priority": 1},
                    {"topic_id": stem + "-2", "subrequest": "Разобрать задачу Б", "priority": 1},
                ], "owner_reply": "Принял две независимые задачи."})
            elif event["kind"] == "input" and "приоритет б" in text and "уточнение а" not in text:
                routes.append({"event_id": eid, "topics": [
                    {"topic_id": self.topic_b, "priority": 10}],
                    "controls": [{"action": "set_priority", "target": self.topic_b, "value": 10}],
                    "owner_reply": "Приоритет задачи Б обновляю."})
            elif event["kind"] == "input" and "уточнение а" in text:
                routes.append({"event_id": eid, "topics": [
                    {"topic_id": self.topic_a, "priority": 1}],
                    "owner_reply": "Уточнение передано задаче А."})
            elif event["kind"] in ("worker_progress", "worker_done", "job_done"):
                routes.append({"event_id": eid, "topics": [{"topic_id": event["topic_id"]}],
                               "owner_reply": f"Обновление {event['topic_id']}: {event['kind']}"})
            else:
                routes.append({"event_id": eid, "topics": [{
                    "topic_id": f"topic-{event['source_id']}", "priority": 1}]})
        return LlmResult(json.dumps({"routes": routes}, ensure_ascii=False), "codex", "synthetic", "route")


def add(store: Store, *, chat: int, role: str, author: int, msg: str, text: str,
        kind: str = "text", file_id: str | None = None, reply_to: str | None = None) -> int:
    got = store.add_message(source="telegram", chat_id=chat, msg_id=msg, role=role,
                            author_id=str(author), author_name="Synthetic", ts=time.time(),
                            kind=kind, text=text, file_id=file_id, reply_to=reply_to)
    assert got is not None
    return int(got)


def main() -> None:
    work = ROOT / ".bot-audit-20261003" / "dispatcher-acceptance"
    work.mkdir(parents=True, exist_ok=True)
    repo = work / "repo"
    repo.mkdir(exist_ok=True)
    db = work / "state.sqlite"
    if db.exists():
        db.unlink()
    cfg = config_from_dict({"repo": str(repo), "state_dir": str(work / "state"),
                            "telegram": {"owner_user_id": 42, "owner_chat_id": 900,
                                         "chats": {"-101": {"role": "client", "seller": "А"},
                                                   "-202": {"role": "client", "seller": "Б"}}},
                            "agent": {"enabled": True}, "limits": {"max_parallel": 3}})
    store = Store(db)
    fake = RouteModel()

    class Tools:
        def specs(self, scope: str) -> list[dict[str, Any]]:
            return []

    pipe = SimpleNamespace(cfg=cfg, store=store, llm=fake, clock=time.time,
                           _owner_snapshot=lambda: [], _is_bind_reply=lambda *_: None)
    agent = AgentCoordinator(pipe, Tools())
    # Authorization is a separate real-model check; this stub only proves that
    # a validated owner control updates the dispatcher state while A is blocked.
    agent.semantic_verifier.check = lambda *_: {"authorized": True}
    d = agent.dispatcher

    owner_id = add(store, chat=900, role="owner", author=42, msg="owner-1",
                   text="Вот две задачи: разбери А и разбери Б параллельно.")
    d.accept(store.row("SELECT * FROM messages WHERE id=?", (owner_id,)))
    d._route_once()
    fake.topic_a, fake.topic_b = f"topic-{owner_id}-1", f"topic-{owner_id}-2"
    assert set(store.kv_get("agent_topic_index", [])) == {fake.topic_a, fake.topic_b}
    entered_a, release_a, entered_b = threading.Event(), threading.Event(), threading.Event()
    finish_order: list[str] = []

    def worker(topic: dict[str, Any], event: dict[str, Any], source: Any) -> dict[str, Any]:
        if topic["id"] == fake.topic_a and not release_a.is_set():
            entered_a.set()
            assert release_a.wait(10)
        if topic["id"] == fake.topic_b:
            entered_b.set()
        finish_order.append(topic["id"])
        return {"summary": topic["id"], "next_action": "none", "result": "synthetic done",
                "affected_areas": ["Ячейки"], "task_ids": []}

    agent.run_topic_turn = worker  # type: ignore[method-assign]
    d._submit_topic(fake.topic_a)
    assert entered_a.wait(3)
    d._submit_topic(fake.topic_b)
    assert entered_b.wait(3), "independent owner topic B was blocked by A"
    assert not release_a.is_set()
    progress_id = d.emit_internal(fake.topic_a, "worker_progress", {
        "event_key": "synthetic-progress-A", "text": "Исследую А"})
    d._route_once()
    assert store.outbox_by_key(f"agent_moderator:{progress_id}") is not None

    follow_id = add(store, chat=900, role="owner", author=42, msg="owner-2",
                    text="Уточнение А: проверь печать, приоритет Б повыше.")
    d.accept(store.row("SELECT * FROM messages WHERE id=?", (follow_id,)))
    d._route_once()
    # One owner message can be routed to an existing topic while A remains busy.
    assert f"in:{follow_id}:1" in store.kv_get(f"agent_topic:{fake.topic_a}", {})["pending"]
    priority_id = add(store, chat=900, role="owner", author=42, msg="owner-3",
                      text="Сделай приоритет Б выше.")
    d.accept(store.row("SELECT * FROM messages WHERE id=?", (priority_id,)))
    d._route_once()
    assert store.kv_get(f"agent_topic:{fake.topic_b}")["priority"] == 10
    other_chat_id = add(store, chat=-202, role="client", author=8, msg="client-B-1",
                        text="В другом чате обсуждаем независимую ошибку списка.")
    d.accept(store.row("SELECT * FROM messages WHERE id=?", (other_chat_id,)))
    d._route_once()
    other_topic = f"topic-{other_chat_id}"
    assert store.kv_get(f"agent_topic:{other_topic}")["chat_id"] == -202
    d._submit_topic(other_topic)
    deadline = time.monotonic() + 3
    while other_topic not in finish_order and time.monotonic() < deadline:
        time.sleep(0.02)
    assert other_topic in finish_order and not release_a.is_set()
    release_a.set()
    deadline = time.monotonic() + 5
    while fake.topic_a not in finish_order and time.monotonic() < deadline:
        time.sleep(0.02)
    assert fake.topic_a in finish_order
    done_id = d.emit_internal(fake.topic_a, "job_done", {
        "event_key": "synthetic-job-A", "text": "А завершена"})
    d._route_once()
    assert store.outbox_by_key(f"agent_moderator:{done_id}") is not None
    assert d.emit_internal(fake.topic_a, "job_done", {
        "event_key": "synthetic-job-A", "text": "А завершена"}) == done_id

    # Full available chronology: older than the 18-message prompt slice.
    for n in range(23):
        add(store, chat=-101, role="client", author=7, msg=f"old-{n}", text=f"История {n}")
    voice_id = add(store, chat=-101, role="client", author=7, msg="voice-1",
                   text="", kind="voice", file_id="synthetic-file-id")
    assert store.complete_transcription(voice_id, 1, "Расшифровка один раз")
    assert not store.complete_transcription(voice_id, 1, "Повторная расшифровка")
    edited_id = store.add_message(source="telegram", chat_id=-101, msg_id="old-0", role="client",
                                  author_id="7", author_name="Synthetic", ts=time.time(),
                                  kind="text", text="Изменённая история 0", file_id=None,
                                  reply_to=None, edited=True, edit_ts=time.time())
    assert edited_id is not None
    store.queue_message(key="synthetic-out", chat_id=-101, text="Ответ", purpose="test",
                        repeat_ok=False)
    store.finish_outbox(store.outbox_by_key("synthetic-out")["id"], "sent", "synthetic-out-id")
    store.db.close()
    reopened = Store(db)
    history = reopened.history_page(-101, limit=100)
    rows = history["items"]
    old = [r for r in rows if r.get("telegram_id") == "old-0"]
    voice = [r for r in rows if r.get("telegram_id") == "voice-1"]
    outgoing = [r for r in rows if r.get("telegram_id") == "synthetic-out-id"
                and r.get("direction") == "out"]
    assert old and old[0].get("revisions") and voice and outgoing
    assert voice[0]["file_id"] == "synthetic-file-id"
    assert voice[0]["text"] == "Расшифровка один раз"
    assert outgoing[0]["status"] == "sent"
    page = reopened.history_page(-101, limit=10)
    paged = list(page["items"])
    while page["next_before"]:
        page = reopened.history_page(-101, before=page["next_before"], limit=10)
        paged.extend(page["items"])
    assert any(item.get("telegram_id") == "old-0" for item in paged)
    prior_text_search = reopened.history_page(-101, query="История 0", limit=10)
    assert any(item.get("telegram_id") == "old-0" for item in prior_text_search["items"])
    assert reopened.kv_get(f"agent_topic:{fake.topic_a}")
    assert reopened.kv_get("agent_dispatch_queue", []) is not None

    output = {"scope": "synthetic SQLite; deterministic router; no live Telegram/Trello/Git",
              "topics": [fake.topic_a, fake.topic_b], "second_started_while_first_blocked": True,
              "owner_followup_pending_for_A": True, "owner_priority_B": 10,
              "other_client_chat_started_while_A_blocked": True,
              "progress_notice_queued_before_A_final": True,
              "job_completion_notice_queued_without_Telegram_input": True,
              "repeated_completion_same_event_id": True,
              "history_records": len(rows), "older_than_18_found": bool(old),
              "paged_oldest_found": True, "old_revision_text_search_found": True,
              "voice_transcribed_once": bool(voice), "edit_version_found": bool(old[0]["revisions"]),
              "outgoing_found_after_restart": bool(outgoing),
              "pending_after_restart": reopened.kv_get(f"agent_topic:{fake.topic_a}").get("pending")}
    target = Path(__file__).with_suffix(".json")
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(target), "passed": True}), flush=True)


if __name__ == "__main__":
    main()
