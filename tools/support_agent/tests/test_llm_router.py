"""R16, R36: CLI вместо API-ключей, переключение при лимите, Astra не выше high."""

from __future__ import annotations

import json
import sys
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
        self.full: list[list[str]] = []

    def __call__(self, argv: list[str], cwd: str | None, timeout: int, stdin: str | None) -> ExecResult:
        self.stdin.append(stdin)
        self.full.append(argv)
        argv = argv[next(i for i, a in enumerate(argv) if a in ("claude", "codex")):]
        self.calls.append(argv)
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


def test_roles_use_sol61_without_api_keys(tmp_path: Path) -> None:
    script = ExecScript()
    llm, _ = router(tmp_path, script)
    llm.ask("filter", "x")
    llm.ask("routine", "x", mode="write", cwd=str(tmp_path))
    llm.ask("analyst", "x", mode="readonly", cwd=str(tmp_path))
    models = [c[c.index("-m") + 1] for c in script.calls]
    assert models == ["gpt-6.1-sol"] * 3
    flat = " ".join(" ".join(c) for c in script.calls).lower()
    assert "api-key" not in flat and "api_key" not in flat
    assert "bypassPermissions" not in " ".join(script.calls[1])
    assert script.calls[2][script.calls[2].index("-s") + 1] == "read-only"


@pytest.mark.parametrize("cli", ["codex"])
@pytest.mark.parametrize("role", ["filter", "routine", "analyst", "review", "frontend", "mockup"])
def test_every_role_receives_common_wms_policy_on_new_and_resumed_turns(
    tmp_path: Path, cli: str, role: str,
) -> None:
    from support_agent import prompts

    script = ExecScript()
    llm, _ = router(tmp_path, script)
    for _ in range(2):
        llm.ask(role, "поручение", cli_only=cli, session_key="policy-test", system="Правила роли")
        if cli == "claude":
            delivered = script.calls[-1][script.calls[-1].index("--system-prompt") + 1]
        else:
            delivered = script.stdin[-1] or ""
        assert delivered.startswith(prompts.WMS_SYSTEM_POLICY + "\n\nПравила роли")
        assert "Сохраняй существующие идентификаторы, дизайн и действия" in delivered
        assert "Не придумывай лимиты, блокировки, новые идентификаторы или сущности" in delivered
        assert "Догадки и предложения модели не являются обязательными требованиями" in delivered
        assert "обычную форму или расположение действия выбирай сам" in delivered


def test_limit_waits_for_codex_and_recovers_without_fallback(tmp_path: Path) -> None:
    script = ExecScript()
    llm, store = router(tmp_path, script)
    script.claude_limit = True
    result = llm.ask("analyst", "x", mode="readonly")
    assert result.cli == "codex" and not llm.cooling("claude")
    before = len(script.calls)
    llm.ask("analyst", "y", mode="readonly")
    assert all("claude" not in c[:6] for c in script.full[before:])  # claude в паузе: не дёргаем
    script.codex_limit = True
    store.kv_set("cooldown:claude", 0)
    with pytest.raises(LlmUnavailable):
        llm.ask("analyst", "z", mode="readonly")
    with pytest.raises(LlmUnavailable):
        llm.ask("analyst", "w", mode="readonly")  # оба в паузе: даже не вызываем
    assert llm.available_clis() == []
    store.kv_set("cooldown:codex", time.time() - 1)
    script.codex_limit = False
    assert llm.ask("analyst", "back", mode="readonly").cli == "codex"


@pytest.mark.parametrize("cli", ["codex"])
def test_owner_session_without_fake_ticket_is_saved_and_resumed_after_router_restart(
    tmp_path: Path, cli: str,
) -> None:
    from support_agent import prompts

    script = ExecScript()
    llm, store = router(tmp_path, script)
    rules = prompts.OWNER_CHAT_SYSTEM
    policy = prompts.WMS_SYSTEM_POLICY
    first = llm.ask("routine", "первый ход: обращение №1 в разборе", session_key="owner_conversation",
                    cli_only=cli, system=rules)
    assert first.session_id and store.rows("SELECT * FROM tickets") == []
    saved = store.kv_get("llm_sessions:owner_conversation")
    assert saved == ({cli: first.session_id} if cli == "claude" else None)
    restarted = LlmRouter(llm.cfg, store, exec_fn=script)
    current = "История: первый ход. Теперь обращение №1 закрыто; новое обращение №2 в разборе."
    updated_rules = rules + "\nИспользуй актуальный снимок обращений в каждом ходе."
    restarted.ask("routine", current, session_key="owner_conversation", cli_only=cli, system=updated_rules)
    if cli == "claude":
        assert script.calls[-1][script.calls[-1].index("--resume") + 1] == first.session_id
        for argv, expected in zip(script.calls, (rules, updated_rules), strict=True):
            assert argv[argv.index("--system-prompt") + 1] == f"{policy}\n\n{expected}"
        assert script.stdin[-1] == current
    else:
        assert script.calls[-1][:3] == ["codex", "exec", "--ephemeral"]
        assert "первый ход: обращение №1 в разборе" in (script.stdin[-1] or "")
        assert script.stdin[0] == f"{policy}\n\n{rules}\n\nпервый ход: обращение №1 в разборе"
        assert (script.stdin[-1] or "").startswith(f"{policy}\n\n{updated_rules}\n\n")
        assert (script.stdin[-1] or "").endswith(current)
    assert store.kv_get("llm_sessions:owner_conversation") == saved
    assert store.rows("SELECT * FROM tickets") == []


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
    llm.cfg.llm.codex_effort = "xhigh"  # ревью явно ограничено high
    calls = len(script.calls)
    llm.ask("review", "x", mode="readonly")
    assert len(script.calls) == calls + 1
    assert 'model_reasoning_effort="high"' in script.calls[-1]


def test_cross_check_excludes_the_analyst_family(tmp_path: Path) -> None:
    script = ExecScript()
    llm, _ = router(tmp_path, script)
    llm.ask("review", "x", mode="readonly", exclude_cli="claude")
    assert script.calls[-1][0] == "codex"
    with pytest.raises(LlmUnavailable):
        llm.ask("review", "x", mode="readonly", exclude_cli="codex")


def test_allowed_roles_fall_back_to_sol_automatically_never_astra(tmp_path: Path) -> None:
    script = ExecScript()
    llm, store = router(tmp_path, script)
    store.kv_set("cooldown:claude", time.time() + 999)  # Claude недоступен
    for role in ("frontend", "mockup", "analyst", "routine", "filter"):
        llm.ask(role, "x", mode="write" if role in ("frontend", "mockup", "routine") else "text",
                cwd=str(tmp_path))
    models = [c[c.index("-m") + 1] for c in script.calls]
    assert models == ["gpt-6.1-sol"] * 5
    assert llm.cfg.llm.models["claude"]["frontend"] == "sonnet"
    assert llm.cfg.llm.models["claude"]["mockup"] == "sonnet"
    assert llm.cfg.llm.models["codex"]["review"] == "gpt-6-astra"
    assert {r for r, m in ((r, llm.model_for("codex", r)) for r in ("filter", "routine", "analyst",
            "frontend", "mockup", "review")) if m and "astra" in m} == {"review"}


def test_stale_astra_config_cannot_override_sol61(tmp_path: Path) -> None:
    script = ExecScript()
    llm, _ = router(tmp_path, script)
    llm.cfg.llm.models["codex"]["analyst"] = "gpt-6-astra"
    assert llm.model_for("codex", "analyst") == "gpt-6.1-sol"


def test_frontend_models_and_review_are_fixed(tmp_path: Path) -> None:
    script = ExecScript()
    llm, _ = router(tmp_path, script)
    assert llm.model_for("claude", "frontend") is None
    assert llm.model_for("codex", "frontend") == "gpt-6.1-sol"
    llm.cfg.llm.cli_order = ["codex", "claude"]
    assert llm.candidates("frontend", None, None) == [
        ("codex", "gpt-6.1-sol")]
    llm.cfg.llm.codex_effort = "xhigh"
    assert llm.effort_for("codex", "review") == "high"
    llm.cfg.llm.models["codex"]["review"] = "gpt-5.6-sol"
    assert llm.model_for("codex", "review") == "gpt-6-astra"


def test_dev_session_has_minimal_rights_not_bypass(tmp_path: Path) -> None:
    script = ExecScript()
    llm, _ = router(tmp_path, script)
    wt = str(tmp_path / "wt")
    argv = llm.build_claude("sonnet", "write", None, None, wt)
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "bypassPermissions" not in argv and "--dangerously-skip-permissions" not in argv
    allowed = argv[argv.index("--allowedTools") + 1: argv.index("--disallowedTools")]
    denied = argv[argv.index("--disallowedTools") + 1:]
    assert f"Edit(/{wt}/**)" in allowed and f"Write(/{wt}/**)" in allowed  # только свой worktree
    assert "Edit" not in allowed and "Write" not in allowed and "Bash" not in allowed
    assert not any(a.startswith("Bash(git add") or a.startswith("Bash(git commit")
                   or a.startswith("Bash(git push") for a in allowed)
    for needed in ("Bash(ruff:*)", "Bash(mypy:*)", "Bash(pytest:*)", "Bash(npm run build:*)",
                   "Bash(npx tsc:*)", "Bash(git status:*)"):
        assert needed in allowed
    for blocked in ("Bash(git push:*)", "Bash(gh:*)", "Bash(ssh:*)", "Bash(curl:*)", "Read(**/*.env)",
                    "Read(~/.wms-support-agent/**)"):
        assert blocked in denied


def test_codex_dev_has_readonly_project_reader_and_only_file_edits(tmp_path: Path) -> None:
    """Sol читает worktree через изолированный MCP, а меняет только файлы через apply_patch."""
    script = ExecScript()
    llm, store = router(tmp_path, script)
    store.kv_set("cooldown:claude", time.time() + 999)
    tid = store.add_ticket(kind="chat", source="t", chat_id=1, seller="s", stage="hotfix")
    wt = str(tmp_path / "wt")
    llm.ask("routine", "x", mode="write", cwd=wt, ticket_id=tid, session_key="dev")
    argv = script.full[-1]
    assert argv[0] == "codex"  # без внешней оболочки: она больше не нужна и не даёт доступ к ~/.codex
    disabled = [argv[i + 1] for i, a in enumerate(argv) if a == "--disable"]
    assert {"shell_tool", "unified_exec", "browser_use", "computer_use", "apps"} <= set(disabled)
    assert "--ignore-user-config" in argv and "--ignore-rules" in argv
    assert argv[argv.index("-s") + 1] == "workspace-write" and "danger-full-access" not in argv
    assert "sandbox_workspace_write.network_access=false" in argv
    assert 'mcp_servers.wms.default_tools_approval_mode="approve"' in argv
    assert any(a.startswith("mcp_servers.wms.args=") for a in argv)
    llm.ask("routine", "y", mode="write", cwd=wt, ticket_id=tid, session_key="dev")  # resume
    resume = script.full[-1]
    assert resume[:3] == ["codex", "exec", "--ephemeral"] and "shell_tool" in resume
    assert resume[resume.index("-s") + 1] == "workspace-write" and "--ignore-user-config" in resume
    assert any(a.startswith("mcp_servers.wms.args=") for a in resume)


def test_codex_text_has_no_shell_but_analyst_keeps_read_only_shell(tmp_path: Path) -> None:
    script = ExecScript()
    llm, store = router(tmp_path, script)
    store.kv_set("cooldown:claude", time.time() + 999)
    llm.ask("filter", "x", mode="text", cwd=str(tmp_path))
    assert "shell_tool" in script.full[-1]
    llm.ask("analyst", "x", mode="readonly", cwd=str(tmp_path))
    argv = script.full[-1]
    assert "shell_tool" in argv  # оболочка отключена и у аналитика (читает проект через MCP)


def test_codex_dev_without_seatbelt_falls_back_to_native_workspace_write(tmp_path: Path) -> None:
    script = ExecScript()
    llm, store = router(tmp_path, script)
    llm.cfg.sandbox.enabled = False
    store.kv_set("cooldown:claude", time.time() + 999)
    llm.ask("routine", "x", mode="write", cwd=str(tmp_path / "wt"))
    argv = script.full[-1]
    assert argv[0] == "codex" and argv[argv.index("-s") + 1] == "workspace-write"
    assert "sandbox_workspace_write.network_access=false" in argv


def test_codex_analyst_has_no_shell_and_reads_only_through_sandboxed_mcp(tmp_path: Path) -> None:
    """Остаток F2 (круг 4): у Sol-аналитика нет модельных команд; проект читается доверенным MCP-читателем,
    который запускается под sandbox-exec (чтение только корня и самого агента, без сети, без записи)."""
    script = ExecScript()
    llm, store = router(tmp_path, script)
    store.kv_set("cooldown:claude", time.time() + 999)
    root = tmp_path / "proj"
    root.mkdir()
    llm.ask("analyst", "x", mode="readonly", cwd=str(root))
    argv = script.full[-1]
    assert argv[0] == "codex"  # без внешней оболочки и без копии CODEX_HOME: штатный каталог владельца
    assert not any(a.startswith("CODEX_HOME=") for a in argv)
    disabled = {argv[i + 1] for i, a in enumerate(argv) if a == "--disable"}
    assert {"shell_tool", "unified_exec", "browser_use", "computer_use", "apps"} <= disabled
    assert argv[argv.index("-s") + 1] == "read-only" and "danger-full-access" not in argv
    assert "--ignore-user-config" in argv and "--ignore-rules" in argv
    assert 'mcp_servers.wms.default_tools_approval_mode="approve"' in argv
    # круг 5: фактический набор инструментов сведён к минимуму (проверено живым вызовом Sol)
    assert {"view_image", "multi_agent", "goals", "hooks", "memories", "plugins", "skill_search",
            "sleep_tool", "tool_suggest", "multi_agent_v2", "code_mode"} <= disabled
    assert "code_mode_host" not in disabled  # без него в этой сборке не работают и инструменты MCP
    assert 'web_search="disabled"' in argv and "tools.view_image=false" in argv
    command = next(a for a in argv if a.startswith("mcp_servers.wms.command="))
    args = json.loads(next(a for a in argv if a.startswith("mcp_servers.wms.args=")).split("=", 1)[1])
    assert json.loads(command.split("=", 1)[1]) == "/usr/bin/sandbox-exec" and args[0] == "-p"
    prof = args[1]
    assert "(deny network*)" in prof and "(deny file-write*)" in prof and "(deny file-read-data (subpath" in prof
    assert f'(allow file-read-data file-read-metadata (subpath "{root.resolve()}"))' in prof
    assert args[-2:] == ["--root", str(root)] and args[2:5] == [sys.executable, "-I", "-S"]


def test_codex_analyst_resume_keeps_mcp_and_disabled_tools(tmp_path: Path) -> None:
    script = ExecScript()
    llm, store = router(tmp_path, script)
    store.kv_set("cooldown:claude", time.time() + 999)
    tid = store.add_ticket(kind="chat", source="t", chat_id=1, seller="s", stage="analysis")
    for text in ("a", "b"):
        llm.ask("analyst", text, mode="readonly", cwd=str(tmp_path), ticket_id=tid, session_key="analyst")
    resume = script.full[-1]
    assert resume[:3] == ["codex", "exec", "--ephemeral"]
    assert "shell_tool" in resume and any(a.startswith("mcp_servers.wms.args=") for a in resume)
    assert resume[resume.index("-s") + 1] == "read-only"


def test_no_codex_home_copy_or_auth_sync_code_exists() -> None:
    """N5: механизма копии CODEX_HOME и переноса auth.json больше нет."""
    source = Path(__file__).resolve().parents[1].joinpath("support_agent", "llm.py").read_text(encoding="utf-8")
    for needle in ("_sync_codex_auth", "_prepare_codex_home", "CODEX_HOME", "codex_auth_path", "auth.json"):
        assert needle not in source, needle


def test_codex_readonly_without_seatbelt_still_has_no_shell(tmp_path: Path) -> None:
    script = ExecScript()
    llm, store = router(tmp_path, script)
    llm.cfg.sandbox.enabled = False
    store.kv_set("cooldown:claude", time.time() + 999)
    llm.ask("analyst", "x", mode="readonly", cwd=str(tmp_path))
    argv = script.full[-1]
    assert argv[0] == "codex" and "shell_tool" in argv and argv[argv.index("-s") + 1] == "read-only"
    assert json.loads(next(a for a in argv if a.startswith("mcp_servers.wms.command=")).split("=", 1)[1]) == sys.executable


def test_claude_write_and_readonly_get_builtin_sandbox_and_secret_read_denies(tmp_path: Path) -> None:
    script = ExecScript()
    llm, _ = router(tmp_path, script)
    for mode in ("write", "readonly"):
        argv = llm.build_claude("sonnet", mode, None, None, str(tmp_path))
        settings = json.loads(argv[argv.index("--settings") + 1])["sandbox"]
        assert settings["enabled"] is True and settings["allowUnsandboxedCommands"] is False
        deny = settings["filesystem"]["denyRead"]
        assert any(p.endswith("/.wms-support-agent") for p in deny) and any(p.endswith("/.ssh") for p in deny)
        assert any(p.endswith("/.config") for p in deny) and any("insurance-benchmark" in p for p in deny)
        denied_tools = argv[argv.index("--disallowedTools") + 1:]
        assert "Read(~/.wms-support-agent/**)" in denied_tools and "Read(**/*.env)" in denied_tools


def test_sandbox_unavailable_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from support_agent import sandbox

    script = ExecScript()
    llm, _ = router(tmp_path, script)
    monkeypatch.setattr(sandbox, "available", lambda: False)
    with pytest.raises(sandbox.SandboxUnavailable):
        llm.ask("routine", "x", mode="write", cwd=str(tmp_path))
    assert script.calls == []


def test_sensitive_env_is_not_passed_to_children(monkeypatch: pytest.MonkeyPatch) -> None:
    from support_agent.llm import default_exec

    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("GH_TOKEN", "gh-should-not-leak")
    res = default_exec(["/usr/bin/env"], None, 20, None)
    assert "should-not-leak" not in res.out and "PATH=" in res.out


def test_real_codex_json_stream_gives_session_id() -> None:
    from support_agent.llm import _codex_session_id

    live = (
        '{"type":"thread.started","thread_id":"01a0fd43-39f6-70c3-9213-907ea87ac473"}\n'
        '{"type":"turn.started"}\n{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}\n'
    )
    assert _codex_session_id(live) == "01a0fd43-39f6-70c3-9213-907ea87ac473"


@pytest.mark.parametrize("cli", ["codex"])
def test_resumed_analyst_receives_current_rules_history_and_state_after_restart(
    tmp_path: Path, cli: str,
) -> None:
    from support_agent import prompts

    script = ExecScript()
    llm, store = router(tmp_path, script)
    tid = store.add_ticket(kind="chat", source="t", chat_id=1, seller="s", stage="analysis")
    first_result = llm.ask("analyst", "разбери", ticket_id=tid, session_key="analyst",
                           context="Старые правила. Клиент: короб не сканируется.",
                           mode="readonly", cli_only=cli)
    current = prompts.analysis_context(
        "Клиент: короб не сканируется.\nКлиент: код уже присылал.\n"
        "Состояние: вопрос клиенту уже отправлен. Владелец запретил новые вопросы.", "",
    )
    note = "Перечитай всю переписку и проверь код сам без вопросов клиенту."
    restarted = LlmRouter(llm.cfg, store, exec_fn=script)
    restarted.ask("analyst", note, ticket_id=tid, session_key="analyst", context=current,
                  mode="readonly", cli_only=cli)
    first, second = script.calls
    if cli == "claude":
        assert "--session-id" in first and "--resume" in second
        assert first[first.index("--session-id") + 1] == second[second.index("--resume") + 1]
    else:
        assert second[:3] == ["codex", "exec", "--ephemeral"]
        assert "Старые правила. Клиент: короб не сканируется." in (script.stdin[-1] or "")
    policy = f"{prompts.WMS_SYSTEM_POLICY}\n\n" if cli == "codex" else ""
    assert script.stdin[0] == policy + "Старые правила. Клиент: короб не сканируется.\n\nразбери"
    assert (script.stdin[1] or "").startswith(policy)
    assert (script.stdin[1] or "").endswith(f"{current}\n\n{note}")
    if cli == "claude":
        assert store.data(tid)["sessions"]["analyst"][cli] == first_result.session_id
    else:
        assert "sessions" not in store.data(tid)


def test_codex_context_is_saved_without_persistent_session(tmp_path: Path) -> None:
    script = ExecScript()
    llm, store = router(tmp_path, script)
    store.kv_set("cooldown:claude", time.time() + 999)
    tid = store.add_ticket(kind="chat", source="t", chat_id=1, seller="s", stage="analysis")
    llm.ask("analyst", "a", ticket_id=tid, session_key="analyst", mode="readonly")
    llm.ask("analyst", "b", ticket_id=tid, session_key="analyst", mode="readonly")
    assert script.calls[1][:3] == ["codex", "exec", "--ephemeral"]
    assert '"prompt": "a"' in (script.stdin[1] or "")
    assert "sessions" not in store.data(tid)


def test_ask_json_retries_once_and_calls_are_logged(tmp_path: Path) -> None:
    answers = iter(["не json", '```json\n{"a": 1}\n```'])

    def fake(argv: list[str], cwd: str | None, timeout: int, stdin: str | None) -> ExecResult:
        Path(argv[argv.index("-o") + 1]).write_text(next(answers))
        return ExecResult(0, "", "")

    cfg = make_config(tmp_path)
    store = Store(cfg.db_path)
    llm = LlmRouter(cfg, store, exec_fn=fake)
    data, _ = llm.ask_json("filter", "q")
    assert data == {"a": 1}
    rows = store.rows("SELECT cli, model, ok FROM llm_calls")
    assert [(r["cli"], r["model"], r["ok"]) for r in rows] == [("codex", "gpt-6.1-sol", 1)] * 2


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
    assert cfg.llm.models["codex"]["filter"] == "gpt-6.1-sol" and cfg.llm.codex_effort == "high"
    assert cfg.telegram.chats[-1000000000001].role == "client" and cfg.secrets() == []
