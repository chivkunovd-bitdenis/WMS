"""WMS-676: model migration preserves durable work and never invokes a fallback."""

from pathlib import Path
from typing import Any

import pytest

from support_agent.app_server import AppServerTurn
from support_agent.llm import LlmResult, LlmRouter, LlmUnavailable, _CallFailed
from support_agent.store import Store

from .conftest import make_config


@pytest.mark.parametrize("role", ["filter", "routine", "analyst", "frontend", "mockup", "review"])
def test_stale_config_cannot_select_an_old_model(tmp_path: Path, monkeypatch: Any, role: str) -> None:
    cfg = make_config(tmp_path, llm={
        "cli_order": ["claude"],
        "models": {"claude": {role: "sonnet"}, "codex": {role: "gpt-5.6-sol"}},
    })
    llm = LlmRouter(cfg, Store(cfg.db_path))
    calls: list[tuple[str, str]] = []

    def run(cli: str, model: str, *args: Any, **kwargs: Any) -> LlmResult:
        calls.append((cli, model))
        return LlmResult("ok", cli, model)

    monkeypatch.setattr(llm, "_run_once", run)
    expected = "gpt-6-astra" if role == "review" else "gpt-6.1-sol"
    assert llm.ask(role, "continue").model == expected
    assert calls == [("codex", expected)]
    assert llm.model_for("claude", role) is None


def test_failure_does_not_call_claude_or_another_model(tmp_path: Path, monkeypatch: Any) -> None:
    cfg = make_config(tmp_path)
    store = Store(cfg.db_path)
    llm = LlmRouter(cfg, store)
    calls = []

    def fail(cli: str, model: str, *args: Any, **kwargs: Any) -> None:
        calls.append((cli, model))
        raise _CallFailed("model unavailable")

    monkeypatch.setattr(llm, "_run_once", fail)
    with pytest.raises(LlmUnavailable):
        llm.ask("frontend", "continue")
    assert calls == [("codex", "gpt-6.1-sol")]
    store.kv_set("cooldown:codex", 10**12)
    with pytest.raises(LlmUnavailable):
        llm.ask("review", "review separately")
    assert len(calls) == 1


def test_model_key_change_preserves_task_code_history_and_separate_roles(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    cfg = make_config(tmp_path)
    store = Store(cfg.db_path)
    tid = store.add_ticket(kind="chat", source="telegram", chat_id=1, seller="seller",
                           stage="development", data={"step": "developer", "feedback": "fix C2",
                           "contract_commit": "test-sha", "version": "approved-version"})
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    source = worktree / "code.py"
    source.write_text("already_written = True\n")
    prior = [{"prompt": "approved task C2", "answer": "existing code saved"}]
    old_key = f"background_context:role:{tid}:dev:codex:gpt-5.6-sol:write"
    store.kv_set(old_key, prior)
    store.kv_set(f"background_context:role:{tid}:review:codex:gpt-6-astra:write",
                 [{"prompt": "review private history", "answer": "defect"}])
    store.kv_set(f"background_context:role:{tid}:dev:subtask:codex:gpt-5.6-sol:write",
                 [{"prompt": "nested task private history", "answer": "unrelated"}])
    before = dict(store.ticket(tid))
    calls: list[str] = []

    def run(cli: str, model: str, role: str, prompt: str, **kwargs: Any) -> LlmResult:
        calls.append(prompt)
        return LlmResult("continued once", cli, model)

    llm = LlmRouter(cfg, store)
    monkeypatch.setattr(llm, "_run_once", run)
    llm.ask("routine", "fix C2", ticket_id=tid, session_key="dev", mode="write", cwd=str(worktree))
    restarted = LlmRouter(cfg, store)
    monkeypatch.setattr(restarted, "_run_once", run)
    restarted.ask("routine", "continue", ticket_id=tid, session_key="dev", mode="write")
    assert "approved task C2" in calls[0] and "existing code saved" in calls[0]
    assert all("review private history" not in call for call in calls)
    assert all("nested task private history" not in call for call in calls)
    history = store.kv_get(f"background_context:role:{tid}:dev:shared:write")
    assert len(history) == 3 and history[0] == prior[0]
    assert calls[1].count("approved task C2") == 1
    assert store.kv_get(old_key) == prior
    assert dict(store.ticket(tid)) == before and len(store.open_tickets()) == 1
    assert source.read_text() == "already_written = True\n"


def test_native_old_job_model_keeps_background_context_and_handoff(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    cfg = make_config(tmp_path, agent={"owner_model": "opus", "owner_provider": "claude"})
    store = Store(cfg.db_path)
    old = "agent_session:job:abc:codex:gpt-5.6-sol:owner"
    store.kv_set(old, {"thread_id": "old-native-thread", "handoff": "confirmed source and next step"})
    store.kv_set(f"background_context:{old}", [{"prompt": "old task", "answer": "saved code"}])
    job = {"id": "abc", "phase": "finalize", "status": "queued", "model": "gpt-5.6-sol",
           "provider": "codex", "worktree": str(tmp_path), "task_ids": ["WMS-654"]}
    store.kv_set("agent_job:abc", job)
    calls: list[tuple[str, dict[str, Any]]] = []

    def run(self: Any, prompt: str, **kwargs: Any) -> tuple[str, str, int]:
        calls.append((prompt, kwargs))
        return "finalized", "new-ephemeral-thread", 0

    monkeypatch.setattr(AppServerTurn, "run", run)
    result = LlmRouter(cfg, store).agent_turn(
        "finalize next step", session_key="job:abc", model="opus", provider="claude",
        mode="owner", owner_authorized=True, cwd=str(tmp_path), include_project_tools=False,
    )
    assert (result.cli, result.model) == ("codex", "gpt-6.1-sol")
    assert len(calls) == 1 and calls[0][1]["session_id"] is None
    assert "old task" in calls[0][0] and "saved code" in calls[0][0]
    assert "confirmed source and next step" in calls[0][0]
    assert store.kv_get("agent_job:abc") == job
    assert store.kv_get("agent_job_index") is None
    assert len(store.kv_get("background_context:agent_session:job:abc:shared:owner")) == 2


def test_history_migration_uses_literal_task_boundaries(tmp_path: Path, monkeypatch: Any) -> None:
    cfg = make_config(tmp_path)
    store = Store(cfg.db_path)
    store.kv_set("background_context:role:None:job_a:codex:gpt-5.6-sol:text",
                 [{"prompt": "another task secret", "answer": "private"}])
    llm = LlmRouter(cfg, store)
    seen = []

    def run(cli: str, model: str, role: str, prompt: str, **kwargs: Any) -> LlmResult:
        seen.append(prompt)
        return LlmResult("ok", cli, model)

    monkeypatch.setattr(llm, "_run_once", run)
    llm.ask("routine", "current task", session_key="job_%", mode="text")
    assert seen == ["current task"]


def test_astra_review_high_never_falls_back_to_sol(tmp_path: Path, monkeypatch: Any) -> None:
    llm = LlmRouter(make_config(tmp_path), Store(str(tmp_path / "state.db")))
    calls = []

    def fail(cli: str, model: str, role: str, *args: Any, **kwargs: Any) -> None:
        calls.append((cli, model, llm.effort_for(cli, role)))
        raise _CallFailed("Astra unavailable")

    monkeypatch.setattr(llm, "_run_once", fail)
    with pytest.raises(LlmUnavailable):
        llm.ask("review", "review", session_key="review")
    assert calls == [("codex", "gpt-6-astra", "high")]


def test_native_review_uses_astra_high_despite_stale_sol_choice(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    cfg = make_config(tmp_path, llm={"codex_effort": "xhigh"})
    calls = []

    def run(self: Any, prompt: str, **kwargs: Any) -> tuple[str, str, int]:
        calls.append(kwargs)
        return "review result", "ephemeral-review", 0

    monkeypatch.setattr(AppServerTurn, "run", run)
    result = LlmRouter(cfg, Store(cfg.db_path)).agent_turn(
        "review", session_key="job:review", role="review", model="gpt-6.1-sol",
        provider="claude", mode="readonly", cwd=str(tmp_path), include_project_tools=False,
    )
    assert result.model == "gpt-6-astra"
    assert calls[0]["model"] == "gpt-6-astra" and calls[0]["effort"] == "high"
