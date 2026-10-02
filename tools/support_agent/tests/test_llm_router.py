"""R16, R36: CLI вместо API-ключей, переключение при лимите, Astra не выше high."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from support_agent.llm import LlmRouter, LlmUnavailable, check_effort, extract_json
from support_agent.pipeline import FORBIDDEN_IN_SUMMARY
from support_agent.store import Store

from .conftest import ExecResult, make_config


class ExecScript:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.claude_limit = False
        self.codex_limit = False
        self.stdin: list[str | None] = []

    def __call__(self, argv: list[str], cwd: str | None, timeout: int, stdin: str | None) -> ExecResult:
        self.calls.append(argv)
        self.stdin.append(stdin)
        if argv[0] == "claude":
            if self.claude_limit:
                return ExecResult(1, json.dumps({"is_error": True, "result": "You've hit your usage limit"}), "")
            sid = argv[argv.index("--session-id") + 1] if "--session-id" in argv else (
                argv[argv.index("--resume") + 1] if "--resume" in argv else "none")
            return ExecResult(0, json.dumps({"result": '{"ok": true}', "session_id": sid,
                                             "is_error": False}), "")
        if self.codex_limit:
            return ExecResult(1, "", "rate limit exceeded")
        out = Path(argv[argv.index("-o") + 1])
        out.write_text('{"ok": true}', encoding="utf-8")
        return ExecResult(0, json.dumps({"type": "thread.started", "thread_id": "T-1"}) + "\n", "")


def router(tmp_path: Path, script: ExecScript) -> tuple[LlmRouter, Store]:
    cfg = make_config(tmp_path)
    store = Store(cfg.db_path)
    return LlmRouter(cfg, store, exec_fn=script), store


def test_roles_use_cheap_and_strong_models_without_api_keys(tmp_path: Path) -> None:
    script = ExecScript()
    llm, _ = router(tmp_path, script)
    llm.ask("filter", "x")
    llm.ask("routine", "x", mode="write", cwd=str(tmp_path))
    llm.ask("analyst", "x", mode="readonly", cwd=str(tmp_path))
    models = [c[c.index("--model") + 1] for c in script.calls]
    assert models == ["haiku", "sonnet", "opus"]
    flat = " ".join(" ".join(c) for c in script.calls).lower()
    assert "api-key" not in flat and "api_key" not in flat
    assert "--tools" in script.calls[0]  # фильтр: без инструментов
    assert "bypassPermissions" in script.calls[1] and "dontAsk" in script.calls[2]
    assert "Edit" in script.calls[2][script.calls[2].index("--disallowedTools"):]  # аналитик не пишет


def test_limit_switches_to_codex_and_remembers_then_both_down_then_recovers(tmp_path: Path) -> None:
    script = ExecScript()
    llm, store = router(tmp_path, script)
    script.claude_limit = True
    result = llm.ask("analyst", "x", mode="readonly")
    assert result.cli == "codex" and llm.cooling("claude")
    before = len(script.calls)
    llm.ask("analyst", "y", mode="readonly")
    assert all(c[0] == "codex" for c in script.calls[before:])  # claude в паузе: не дёргаем
    script.codex_limit = True
    store.kv_set("cooldown:claude", 0)
    with pytest.raises(LlmUnavailable):
        llm.ask("analyst", "z", mode="readonly")
    with pytest.raises(LlmUnavailable):
        llm.ask("analyst", "w", mode="readonly")  # оба в паузе: даже не вызываем
    assert llm.available_clis() == []
    store.kv_set("cooldown:claude", time.time() - 1)
    script.claude_limit = False
    assert llm.ask("analyst", "back", mode="readonly").cli == "claude"


def test_astra_effort_is_always_explicit_and_never_above_high(tmp_path: Path) -> None:
    script = ExecScript()
    llm, store = router(tmp_path, script)
    store.kv_set("cooldown:claude", time.time() + 999)
    llm.ask("review", "x", mode="readonly")
    argv = script.calls[-1]
    assert argv[argv.index("-m") + 1] == "gpt-6-astra"
    assert 'model_reasoning_effort="high"' in argv
    for bad in ("xhigh", "max", "ultra", None):
        with pytest.raises(ValueError):
            check_effort("gpt-6-astra", bad)
    for good in ("low", "medium", "high"):
        assert check_effort("gpt-6-astra", good) == good
    llm.cfg.llm.codex_effort = "xhigh"  # даже ошибка в настройках не даст запустить
    calls = len(script.calls)
    with pytest.raises(ValueError):
        llm.ask("review", "x", mode="readonly")
    assert len(script.calls) == calls


def test_cross_check_excludes_the_analyst_family(tmp_path: Path) -> None:
    script = ExecScript()
    llm, _ = router(tmp_path, script)
    llm.ask("review", "x", mode="readonly", exclude_cli="claude")
    assert script.calls[-1][0] == "codex"
    llm.ask("review", "x", mode="readonly", exclude_cli="codex")
    assert script.calls[-1][0] == "claude"


def test_claude_only_role_does_not_fall_back_to_codex(tmp_path: Path) -> None:
    script = ExecScript()
    llm, store = router(tmp_path, script)
    store.kv_set("cooldown:claude", time.time() + 999)
    with pytest.raises(LlmUnavailable, match="claude_only"):
        llm.ask("mockup", "x", mode="write", cli_only="claude")
    assert script.calls == []  # Astra не вызвана


def test_session_is_created_then_resumed_and_context_only_for_new(tmp_path: Path) -> None:
    script = ExecScript()
    llm, store = router(tmp_path, script)
    tid = store.add_ticket(kind="chat", source="t", chat_id=1, seller="s", stage="analysis")
    llm.ask("analyst", "вопрос 1", ticket_id=tid, session_key="analyst", context="КОНТЕКСТ", mode="readonly")
    llm.ask("analyst", "вопрос 2", ticket_id=tid, session_key="analyst", context="КОНТЕКСТ", mode="readonly")
    first, second = script.calls
    assert "--session-id" in first and "--resume" in second
    assert first[first.index("--session-id") + 1] == second[second.index("--resume") + 1]
    assert script.stdin[0].startswith("КОНТЕКСТ") and script.stdin[1] == "вопрос 2"


def test_codex_session_id_is_saved_and_resumed(tmp_path: Path) -> None:
    script = ExecScript()
    llm, store = router(tmp_path, script)
    store.kv_set("cooldown:claude", time.time() + 999)
    tid = store.add_ticket(kind="chat", source="t", chat_id=1, seller="s", stage="analysis")
    llm.ask("analyst", "a", ticket_id=tid, session_key="analyst", mode="readonly")
    llm.ask("analyst", "b", ticket_id=tid, session_key="analyst", mode="readonly")
    assert script.calls[1][:4] == ["codex", "exec", "resume", "T-1"]


def test_ask_json_retries_once_and_calls_are_logged(tmp_path: Path) -> None:
    answers = iter(["не json", '```json\n{"a": 1}\n```'])

    def fake(argv: list[str], cwd: str | None, timeout: int, stdin: str | None) -> ExecResult:
        return ExecResult(0, json.dumps({"result": next(answers), "session_id": "s", "is_error": False}), "")

    cfg = make_config(tmp_path)
    store = Store(cfg.db_path)
    llm = LlmRouter(cfg, store, exec_fn=fake)
    data, _ = llm.ask_json("filter", "q")
    assert data == {"a": 1}
    rows = store.rows("SELECT cli, model, ok FROM llm_calls")
    assert [(r["cli"], r["model"], r["ok"]) for r in rows] == [("claude", "haiku", 1)] * 2


def test_extract_json_handles_nested_and_noise() -> None:
    assert extract_json('вот {"a": {"b": [1, 2]}, "s": "}"} конец') == {"a": {"b": [1, 2]}, "s": "}"}
    with pytest.raises(ValueError):
        extract_json("нет json")


def test_summary_filter_catches_technical_leaks() -> None:
    for bad in ("см. services/foo.py", "ШК 4600000000001", "```code```", "файл main.tsx"):
        assert FORBIDDEN_IN_SUMMARY.search(bad), bad
    assert not FORBIDDEN_IN_SUMMARY.search("Оператор не может передать поставку: появляется ошибка.")


def test_config_example_loads() -> None:
    from support_agent.config import config_from_dict

    cfg = config_from_dict(json.loads(Path("config.example.json").read_text(encoding="utf-8")))
    assert cfg.llm.models["claude"]["filter"] == "haiku" and cfg.llm.codex_effort == "high"
    assert cfg.telegram.chats[-1000000000001].role == "client" and cfg.secrets() == []
