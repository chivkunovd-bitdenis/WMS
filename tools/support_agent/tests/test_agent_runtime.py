"""Native model loop, durable session identity, and owner boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from support_agent.app_server import _occupancy
from support_agent.config import config_from_dict
from support_agent.llm import LlmRouter, agent_capability_signature, normalize_agent_tools
from support_agent.store import Store

from .conftest import ExecResult, make_config


def fake_server(path: Path) -> None:
    path.write_text("""#!/usr/bin/env python3
import json, sys
def send(value):
    sys.stdout.write(json.dumps(value) + '\\n'); sys.stdout.flush()
has_project = False
for line in sys.stdin:
    msg = json.loads(line)
    method = msg.get('method')
    if method == 'initialize':
        send({'id': msg['id'], 'result': {}})
    elif method == 'config/read':
        send({'id': msg['id'], 'result': {'config': {'mcp_servers': {}}}})
    elif method == 'thread/start':
        params = msg['params']
        assert params.get('ephemeral') is True, 'background thread must not persist'
        has_project = any(t.get('name') == 'project' for t in params.get('dynamicTools', []))
        send({'id': msg['id'], 'result': {'model': params['model'], 'thread': {'id': 'thread-1'}}})
    elif method == 'thread/resume':
        send({'id': msg['id'], 'result': {'thread': {'id': msg['params']['threadId']}}})
    elif method == 'turn/start':
        send({'id': msg['id'], 'result': {'turn': {'id': 'turn-1'}}})
        send({'method': 'item/completed', 'params': {'item': {'type': 'agentMessage',
              'phase': 'commentary', 'text': 'Reading current facts'}}})
        if has_project:
            send({'id': 99, 'method': 'item/tool/call', 'params': {'tool': 'read_file',
                  'namespace': 'project', 'arguments': {'path': 'README.md'}}})
        else:
            send({'method': 'item/completed', 'params': {'item': {'type': 'agentMessage',
                  'phase': 'final_answer', 'text': 'routed'}}})
            send({'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}})
    elif msg.get('id') == 99:
        reply = msg['result']['contentItems'][0]['text']
        send({'method': 'thread/tokenUsage/updated', 'params': {'tokenUsage': {
              'last': {'totalTokens': 122000}, 'total': {'totalTokens': 900000}}}})
        send({'method': 'item/completed', 'params': {'item': {'type': 'agentMessage',
              'phase': 'final_answer', 'text': reply}}})
        send({'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}})
""", encoding="utf-8")
    path.chmod(0o755)


def test_actual_context_not_lifetime_total() -> None:
    assert _occupancy({"last": {"totalTokens": 123}, "total": {"totalTokens": 900_000}}) == 123


def test_agent_opt_in_is_loaded_from_config() -> None:
    assert config_from_dict({"agent": {"enabled": True, "owner_model": "gpt-5.6-sol"}}).agent.enabled


def test_real_agent_specs_and_owner_style_use_one_native_format() -> None:
    from support_agent.agent_tools import AgentTools

    tools = AgentTools.__new__(AgentTools)
    # specs() only describes tools and does not touch collaborators.
    plain = tools.specs("owner")
    nested = {"type": "function", "function": {"name": "project_job",
              "description": "Execute owner project work", "parameters": {"type": "object",
              "properties": {"goal": {"type": "string"}}}}}
    normalized = normalize_agent_tools([*plain, nested])
    assert all(spec["type"] == "function" and "inputSchema" in spec for spec in normalized)
    assert {spec["name"] for spec in normalized} >= {"project_job", plain[0]["name"]}


def test_background_context_survives_tool_changes_without_handoff_threads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from support_agent.app_server import AppServerTurn

    cfg = make_config(tmp_path)
    store = Store(cfg.db_path)
    llm = LlmRouter(cfg, store)
    calls: list[dict[str, object]] = []

    def fake_run(self: AppServerTurn, prompt: str, **kwargs: object) -> tuple[str, str, int]:
        calls.append({"prompt": prompt, **kwargs})
        thread_id = kwargs.get("session_id") or f"thread-{len(calls)}"
        started = kwargs.get("session_started")
        if callable(started):
            started(str(thread_id))
        return "handoff" if "Сохрани передачу" in prompt else "done", str(thread_id), 100

    monkeypatch.setattr(AppServerTurn, "run", fake_run)
    first = [{"name": "one", "description": "first", "inputSchema": {"type": "object"}}]
    second = [{"name": "two", "description": "second", "inputSchema": {"type": "object"}}]
    assert agent_capability_signature(normalize_agent_tools(first), str(tmp_path)) != (
        agent_capability_signature(normalize_agent_tools(second), str(tmp_path)))
    kwargs: dict[str, Any] = {"session_key": "job", "mode": "owner", "owner_authorized": True,
                              "cwd": str(tmp_path), "tool_handler": lambda name, args: {}}
    llm.agent_turn("a", tools=first, **kwargs)
    llm.agent_turn("b", tools=first, **kwargs)
    assert len(calls) == 2 and calls[1]["session_id"] is None
    assert '"prompt": "a"' in str(calls[1]["prompt"])
    llm.agent_turn("c", tools=second, **kwargs)
    assert len(calls) == 3
    assert all(call["session_id"] is None for call in calls)
    assert '"prompt": "b"' in str(calls[2]["prompt"])
    assert not any("Сохрани передачу" in str(call["prompt"]) for call in calls)
    # Restart does not lose the logical session or create a desktop resume.
    LlmRouter(cfg, store).agent_turn("d", tools=second, **kwargs)
    assert '"prompt": "c"' in str(calls[3]["prompt"])
    assert len(list((cfg.state_path / "background-sessions").glob("*.jsonl"))) == 1


def test_codex_dynamic_project_reader_and_persisted_thread(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    repo = Path(cfg.repo)
    repo.mkdir()
    (repo / "README.md").write_text("project facts", encoding="utf-8")
    binary = tmp_path / "fake-codex"
    fake_server(binary)
    cfg.llm.codex_bin = str(binary)
    store = Store(cfg.db_path)
    llm = LlmRouter(cfg, store)
    result = llm.agent_turn("Read project", session_key="owner", mode="readonly")
    assert "project facts" in json.loads(result.text)["text"]
    assert result.session_id == "thread-1"
    state = store.kv_get("agent_session:owner:codex:gpt-5.6-sol:readonly")
    assert state["thread_id"] is None and state["rollover"] is False
    history = store.kv_get("background_context:agent_session:owner:codex:gpt-5.6-sol:readonly")
    assert history[0]["prompt"] == "Read project" and "project facts" in history[0]["answer"]
    assert "900000" not in str(state)


def test_dispatch_turn_omits_project_reader_and_streams_completed_commentary(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    Path(cfg.repo).mkdir()
    binary = tmp_path / "fake-codex"
    fake_server(binary)
    cfg.llm.codex_bin = str(binary)
    store = Store(cfg.db_path)
    progress: list[str] = []
    result = LlmRouter(cfg, store).agent_turn(
        "Route new event", session_key="agent:dispatcher", mode="readonly",
        effort="medium", include_project_tools=False, progress_callback=progress.append,
    )
    assert result.text == "routed" and progress == ["Reading current facts"]
    row = store.row("SELECT effort FROM llm_calls ORDER BY id DESC LIMIT 1")
    assert row is not None and row["effort"] == "medium"


def test_full_project_mode_requires_trusted_owner(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    llm = LlmRouter(cfg, Store(cfg.db_path))
    with pytest.raises(PermissionError):
        llm.agent_turn("Export", session_key="job", mode="owner", cwd=str(tmp_path))


def test_explicit_opus_uses_claude_without_fallback(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    calls: list[list[str]] = []
    progress: list[str] = []

    def execute(argv: list[str], cwd: str | None, timeout: int,
                stdin: str | None) -> ExecResult:
        calls.append(argv)
        return ExecResult(0, json.dumps({"result": "Done", "session_id": "claude-thread",
                                         "is_error": False}), "")

    llm = LlmRouter(cfg, Store(cfg.db_path), exec_fn=execute)
    result = llm.agent_turn("Do it", session_key="owner", model="opus", provider="claude",
                            mode="owner", owner_authorized=True, cwd=str(tmp_path),
                            effort="medium", progress_callback=progress.append)
    assert result.model == "opus" and result.cli == "claude"
    assert calls[0][calls[0].index("--model") + 1] == "opus"
    assert calls[0][calls[0].index("--effort") + 1] == "medium"
    assert progress == ["Claude: ход модели начат."]
    assert "codex" not in calls[0]


def test_claude_service_tool_reports_actual_stage_before_handler(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    progress: list[str] = []
    seen: list[str] = []
    results = iter([{"result": '{"tool":"lookup","arguments":{}}',
                     "session_id": "claude-thread", "is_error": False},
                    {"result": '{"final":"done"}', "session_id": "claude-thread",
                     "is_error": False}])

    def execute(argv: list[str], cwd: str | None, timeout: int,
                stdin: str | None) -> ExecResult:
        return ExecResult(0, json.dumps(next(results)), "")

    def handle(name: str, args: dict[str, Any]) -> dict[str, Any]:
        seen.append(name)
        assert progress[-1] == "Claude: вызван сервисный инструмент lookup."
        return {"found": True}

    result = LlmRouter(cfg, Store(cfg.db_path), exec_fn=execute).agent_turn(
        "Inspect", session_key="owner", model="opus", provider="claude", mode="owner",
        owner_authorized=True, cwd=str(tmp_path),
        tools=[{"name": "lookup", "description": "synthetic lookup",
                "inputSchema": {"type": "object", "properties": {}}}],
        tool_handler=handle, progress_callback=progress.append)
    assert result.text == "done" and seen == ["lookup"]
    assert progress == ["Claude: ход модели начат.",
                        "Claude: вызван сервисный инструмент lookup."]
