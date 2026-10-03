"""Coordination boundaries: actual source identity, durable schedules, and deadline wakeup."""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from support_agent.agent_authorization import SemanticAuthorization
from support_agent.agent_coordinator import AgentCoordinator
from support_agent.config import config_from_dict
from support_agent.llm import LlmResult
from support_agent.pipeline import InlinePool
from support_agent.store import Store


class StubTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        self.cards: list[dict[str, Any]] = []
        self.semantic_verifier: SemanticAuthorization | None = None

    def specs(self, scope):
        return []

    def dispatch(self, name, args, context):
        self.calls.append((name, args, context))
        return {"ok": True}

    def ready_cards(self):
        return self.cards


class StubLlm:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.answer = "Проверенный ответ"

    def agent_turn(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return LlmResult(self.answer, "codex", kwargs["model"], "session")


class FixtureVerifier(SemanticAuthorization):
    def check(self, event: Any, action: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"authorized": True, "reason": "fixture"}


def coordinator(tmp_path: Path, *, now: list[float], store: Store | None = None):
    cfg = config_from_dict({"repo": str(tmp_path / "repo"), "state_dir": str(tmp_path / "state"),
                            "telegram": {"owner_user_id": 42, "owner_chat_id": 4242},
                            "agent": {"enabled": True, "hourly_interval_sec": 3600}})
    cfg_path = Path(cfg.repo)
    cfg_path.mkdir(exist_ok=True)
    db = store or Store(cfg.db_path)
    llm = StubLlm()
    tools = StubTools()
    pipe = SimpleNamespace(cfg=cfg, store=db, llm=llm, clock=lambda: now[0],
                           pool=InlinePool(), _owner_snapshot=lambda: [],
                           _is_bind_reply=lambda *_: None,
                           _seller_for_chat=lambda *_: "client", mockups=None)
    agent = AgentCoordinator(pipe, tools)
    agent.semantic_verifier = FixtureVerifier(agent)
    tools.semantic_verifier = agent.semantic_verifier
    return agent, db, llm, tools


def message(store: Store, chat: int, author: str, text: str) -> int:
    got = store.add_message(source="telegram", chat_id=chat, msg_id=f"{chat}-{author}-{text}",
                            role="owner" if chat == 4242 else "client", author_id=author,
                            author_name="person", ts=100, kind="text", text=text,
                            file_id=None, reply_to=None)
    assert got is not None
    return got


def test_owner_native_job_is_source_bound_and_client_cannot_request_it(tmp_path):
    now = [100.0]
    agent, store, llm, _ = coordinator(tmp_path, now=now)
    owner_id = message(store, 4242, "42", "Сделай выгрузку")
    client_id = message(store, -100, "99", "Сделай выгрузку")
    owner_event = store.row("SELECT * FROM messages WHERE id=?", (owner_id,))
    client_event = store.row("SELECT * FROM messages WHERE id=?", (client_id,))
    assert owner_event and client_event
    agent.handle_message(client_event)
    assert "project_job" not in {t["name"] for t in llm.calls[-1][1]["tools"]}
    client_context = agent._context(client_event, owner=False)
    assert agent._owner_tool("project_job", {"request": "export"}, client_context) == {
        "error": "owner_source_required"}
    # Only the trusted dispatcher may call owner tools; a client turn never receives one.
    agent.handle_message(owner_event)
    assert "project_job" in {t["name"] for t in llm.calls[-1][1]["tools"]}
    assert '"timezone": "Asia/Tbilisi"' in llm.calls[-1][0]
    assert '"current_time":' in llm.calls[-1][0]
    assert store.outbox_by_key(f"agent_answer:{owner_id}") is not None
    assert store.row("SELECT status FROM messages WHERE id=?", (owner_id,))["status"] == "handled"


def test_scheduled_owner_job_survives_restart_and_deadline_enters_finalization(tmp_path):
    now = [100.0]
    agent, store, _, _ = coordinator(tmp_path, now=now)
    source_id = message(store, 4242, "42", "К сроку выпусти проверенную часть")
    source = store.row("SELECT * FROM messages WHERE id=?", (source_id,))
    assert source
    context = agent._context(source, owner=True)
    queued = agent._owner_tool("schedule_project_job", {
        "request": "Prepare chosen changes and release verified ready subset",
        "run_at": "1970-01-01T00:03:20+00:00", "release_authorized": True,
    }, context)
    jid = queued["id"]
    assert queued["status"] == "scheduled"
    resumed, _, _, _ = coordinator(tmp_path, now=now, store=store)
    submitted: list[str] = []
    resumed._submit_job = submitted.append
    now[0] = 201.0
    resumed.tick()
    assert submitted == [jid]
    assert store.kv_get(f"agent_job:{jid}")["status"] == "queued"
    job = store.kv_get(f"agent_job:{jid}")
    job.update(deadline_at=202.0, deadline_status="pending", status="running")
    store.kv_set(f"agent_job:{jid}", job)
    now[0] = 203.0
    resumed.tick()
    updated = store.kv_get(f"agent_job:{jid}")
    assert updated["phase"] == "finalize"
    assert updated["deadline_status"] == "finalizing"
    assert updated["source_event_id"] == source_id


def test_hourly_list_reads_live_board_and_deduplicates_slot(tmp_path):
    now = [4000.0]
    agent, store, _, tools = coordinator(tmp_path, now=now)
    tools.cards = [{"id": "c1", "name": "WMS-700 Исправить выбор", "url": "https://trello.test/c1"}]
    agent._hourly()
    agent._hourly()
    queued = store.rows("SELECT * FROM outbox WHERE purpose='agent_hourly'")
    assert len(queued) == 1
    assert "WMS-700" in queued[0]["text"]


def test_arbitrary_job_uses_native_owner_mode_and_exact_source(tmp_path):
    now = [100.0]
    agent, store, llm, _ = coordinator(tmp_path, now=now)
    source_id = message(store, 4242, "42", "Сделай выгрузку таблицы")
    source = store.row("SELECT * FROM messages WHERE id=?", (source_id,))
    assert source
    agent._submit_job = lambda _: None
    created = agent._owner_tool("project_job", {"request": "Export the table to CSV"},
                                agent._context(source, owner=True))
    job_id = created["id"]
    worktree = tmp_path / "repo" / ".worktrees" / f"support-job-{job_id}"
    worktree.mkdir(parents=True)
    agent._worktree = lambda _: worktree
    agent._run_job(job_id)
    assert store.kv_get(f"agent_job:{job_id}")["status"] == "done"
    prompt, kwargs = llm.calls[-1]
    assert kwargs["mode"] == "owner" and kwargs["owner_authorized"] is True
    assert "Export the table" in prompt and "Сделай выгрузку" in prompt
    assert '"timezone": "Asia/Tbilisi"' in prompt
    assert kwargs["cwd"] == str(worktree)


def test_selected_frontend_task_needs_current_description_and_mockup_approval(tmp_path):
    now = [100.0]
    agent, store, _, _ = coordinator(tmp_path, now=now)
    source_id = message(store, 4242, "42", "Запусти WMS-700")
    source = store.row("SELECT * FROM messages WHERE id=?", (source_id,))
    assert source
    tid = store.add_ticket(kind="agent_task", source="telegram", chat_id=-100,
                           seller="client", stage="agent_discussion",
                           data={"agent": {"wms_number": 700, "version": "v2",
                                           "document_version": "v2", "is_frontend": True,
                                           "owner_approval": {"version": "v2"},
                                           "mockup": {"version": "v2", "status": "published",
                                                      "url": "https://mock.test/v2"}}})
    args = {"request": "Develop selected task", "task_ids": ["WMS-700"]}
    context = agent._context(source, owner=True)
    refused = agent._owner_tool("project_job", args, context)
    assert refused["error"] == "task_not_ready" and "mockup" in refused["reason"]
    data = store.data(tid)
    data["agent"]["mockup_approval"] = {"version": "v2", "url": "https://mock.test/v2"}
    store.patch_data(tid, **data)
    agent._submit_job = lambda _: None
    accepted = agent._owner_tool("project_job", args, context)
    assert accepted["status"] == "queued"
    assert accepted["task_ids"] == ["WMS-700"]


def test_job_file_relative_path_is_anchored_under_verified_worktree(tmp_path):
    now = [100.0]
    agent, store, _, _ = coordinator(tmp_path, now=now)
    source_id = message(store, 4242, "42", "Пришли экспорт")
    source = store.row("SELECT * FROM messages WHERE id=?", (source_id,))
    assert source
    root = tmp_path / "repo" / ".worktrees" / "support-job-abc"
    output = root / "out" / "export.csv"
    output.parent.mkdir(parents=True)
    output.write_text("a,b\n1,2\n")
    store.kv_set("agent_job:abc", {"id": "abc", "status": "done", "worktree": str(root)})
    result = agent._send_job_file({"job_id": "abc", "path": "out/export.csv"},
                                  agent._context(source, owner=True))
    assert result["queued"] is True
    assert store.outbox_by_key(result["key"])["file_path"] == str(output)
    denied = agent._send_job_file({"job_id": "abc", "path": "../outside.csv"},
                                  agent._context(source, owner=True))
    assert denied["error"] == "file_not_in_job_worktree"


def test_cancel_race_is_reported_unknown_and_deadline_callback_reads_current_state(tmp_path):
    now = [100.0]
    agent, store, llm, _ = coordinator(tmp_path, now=now)
    source_id = message(store, 4242, "42", "Сделай работу")
    source = store.row("SELECT * FROM messages WHERE id=?", (source_id,))
    assert source
    agent._submit_job = lambda _: None
    created = agent._owner_tool("project_job", {"request": "Do work",
                                                    "deadline_at": "1970-01-01T01:00:00+00:00"},
                                agent._context(source, owner=True))
    jid = created["id"]
    worktree = tmp_path / "repo" / ".worktrees" / f"support-job-{jid}"
    worktree.mkdir(parents=True)
    agent._worktree = lambda _: worktree

    def complete_while_cancelled(prompt, **kwargs):
        assert kwargs["cancelled"]() is False
        agent._patch_job(jid, deadline_at=99.0)
        assert kwargs["cancelled"]() is True
        agent._patch_job(jid, cancel_requested=True)
        return LlmResult("work may have finished", "codex", kwargs["model"], "session")

    llm.agent_turn = complete_while_cancelled
    agent._run_job(jid)
    saved = store.kv_get(f"agent_job:{jid}")
    assert saved["status"] == "needs_review"
    assert saved["cancel_requested"] is True
    assert store.outbox_by_key(f"agent_job_done:{jid}") is None
    assert store.outbox_by_key(f"agent_job_cancel_unknown:{jid}") is not None


def test_interrupted_mockup_is_queued_for_same_worktree_recovery(tmp_path):
    now = [100.0]
    agent, store, _, _ = coordinator(tmp_path, now=now)
    tid = store.add_ticket(kind="agent_task", source="telegram", chat_id=-100,
                           seller="client", stage="agent_discussion",
                           data={"agent": {"version": "v1", "mockup": {
                               "version": "v1", "status": "running"}}})
    agent.recover_after_restart()
    mockup = store.data(tid)["agent"]["mockup"]
    assert mockup["status"] == "queued"
    assert "inspect" in mockup["recovery_note"]


def test_independent_project_jobs_can_run_concurrently(tmp_path: Path) -> None:
    agent, _, _, _ = coordinator(tmp_path, now=[100.0])
    first_started = threading.Event()
    second_started = threading.Event()
    release = threading.Event()

    def run(job_id: str) -> None:
        if job_id == "first":
            first_started.set()
            assert release.wait(2)
        else:
            second_started.set()

    agent._run_job = run  # type: ignore[method-assign]
    agent._submit_job("first")
    assert first_started.wait(1)
    agent._submit_job("second")
    assert second_started.wait(1)
    release.set()
