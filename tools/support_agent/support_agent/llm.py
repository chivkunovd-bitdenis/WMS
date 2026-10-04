"""Вызовы моделей только через залогиненные CLI владельца: claude -p и codex exec (R36).

Платных API-ключей нет. Astra всегда с явным effort не выше high (жёсткое правило AGENTS.md).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import prod_sql_mcp, prompts, readonly_mcp, sandbox
from .config import Config
from .prod_sql import ROLE_RE, SqlRefused, role_for_scope
from .store import Store

log = logging.getLogger(__name__)

ASTRA_ALLOWED_EFFORT = ("minimal", "low", "medium", "high")
LIMIT_PATTERNS = re.compile(
    r"usage limit|rate.?limit|limit reached|hit your limit|quota|too many requests|"
    r"\b429\b|overloaded|credit balance|resets? at|not logged in|please run /login|"
    r"authentication|unauthorized|invalid api key",
    re.IGNORECASE,
)
CODEX_DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "browser_use", "browser_use_external",
    "browser_use_full_cdp_access", "computer_use", "apps", "in_app_browser", "image_generation",
    "view_image", "multi_agent", "goals", "hooks", "memories", "plugins", "plugin_sharing",
    "remote_plugin", "skill_search", "sleep_tool", "tool_suggest", "multi_agent_v2", "code_mode",
    "code_mode_only", "code_mode_interrupt", "code_mode_prewarm", "default_mode_request_user_input",
    "request_permissions_tool", "exec_permission_approvals", "deferred_executor",
    "executor_capability_discovery", "collaboration_modes", "js_repl", "standalone_web_search",
)
# Дополнительные настройки: веб-поиск и просмотр картинок выключены, подтверждений не запрашиваем.
CODEX_EXTRA_CONFIG = ('web_search="disabled"', "tools.view_image=false", 'approval_policy="never"')
READONLY_TOOLS = [
    "Read", "Grep", "Glob", "Bash(git log:*)", "Bash(git show:*)", "Bash(git diff:*)",
    "Bash(git grep:*)", "Bash(git status:*)", "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)",
    "Bash(rg:*)", "Bash(find:*)", "Bash(wc:*)",
]


def secret_read_denies() -> list[str]:
    """Запрет инструменту Read читать конфиг агента и учётные данные (аналитик и разработчик)."""
    rules = ["Read(**/*.env)", "Read(**/.env*)"]
    for rel in sandbox.DEFAULT_DENY_READ:
        rules += [f"Read(~/{rel})", f"Read(~/{rel}/**)"]
    return rules


class LlmUnavailable(Exception):
    """Нет доступного CLI: обращение остаётся в очереди (R36)."""


class LlmError(Exception):
    pass


@dataclass
class ExecResult:
    rc: int
    out: str
    err: str


ExecFn = Callable[[list[str], str | None, int, str | None], ExecResult]


def default_exec(argv: list[str], cwd: str | None, timeout: int, stdin: str | None) -> ExecResult:
    # Ключи агента не передаются дочерним CLI и их процессам (проверка и модельные сессии).
    env = {k: v for k, v in os.environ.items() if k not in sandbox.SENSITIVE_ENV}
    try:
        proc = subprocess.run(
            argv, cwd=cwd, input=stdin or "", capture_output=True, text=True, timeout=timeout,
            env=env,
        )
    except FileNotFoundError:
        return ExecResult(127, "", "command not found")
    except subprocess.TimeoutExpired:
        return ExecResult(124, "", "timeout")
    return ExecResult(proc.returncode, proc.stdout, proc.stderr)


@dataclass
class LlmResult:
    text: str
    cli: str
    model: str
    session_id: str | None = None


def check_effort(model: str, effort: str | None) -> str | None:
    """Astra: effort обязан быть задан явно и не выше high (AGENTS.md)."""
    if "astra" in model.lower():
        if effort not in ASTRA_ALLOWED_EFFORT:
            raise ValueError(f"Astra effort must be one of {ASTRA_ALLOWED_EFFORT}, got {effort!r}")
    return effort


def extract_json(text: str) -> dict[str, Any]:
    """Первый сбалансированный JSON-объект в ответе модели (с кодовыми заборами или без)."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start : i + 1])
                    except ValueError:
                        break
                    if isinstance(value, dict):
                        return value
                    break
        start = text.find("{", start + 1)
    raise ValueError("no JSON object in model answer")


def normalize_agent_tools(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Accept existing AgentTools specs and OpenAI-style caller specs once."""
    normalized: list[dict[str, Any]] = []
    for raw in specs:
        if raw.get("type") == "namespace":
            inner = normalize_agent_tools(raw.get("tools") or [])
            normalized.append({"type": "namespace", "name": raw["name"],
                               "description": raw.get("description", ""), "tools": inner})
            continue
        nested = raw.get("function")
        source: dict[str, Any] = nested if isinstance(nested, dict) else raw
        name = source.get("name")
        schema = source.get("inputSchema", source.get("parameters", {"type": "object"}))
        if not isinstance(name, str) or not name or not isinstance(schema, dict):
            raise ValueError("invalid agent tool spec")
        normalized.append({"type": "function", "name": name,
                           "description": str(source.get("description") or ""),
                           "inputSchema": schema})
    return normalized


def agent_capability_signature(tools: list[dict[str, Any]], cwd: str) -> str:
    """Stable fingerprint of the tools and project boundary persisted in a thread."""
    def ordered(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(({**spec, "tools": ordered(spec["tools"])} if spec.get("type") == "namespace"
                       else spec for spec in specs), key=lambda spec: spec["name"])

    payload = json.dumps({"tools": ordered(tools), "cwd": cwd}, ensure_ascii=False,
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LlmRouter:
    def __init__(self, cfg: Config, store: Store, exec_fn: ExecFn = default_exec) -> None:
        self.cfg = cfg
        self.store = store
        self.exec = exec_fn
        self.scratch = cfg.state_path / "scratch"
        # Подготовка роли селлера на сервере (шлюз ensure-seller); подключает runner. Без неё
        # (в тестах) роль считается готовой.
        self.role_ensurer: Callable[[str, str], None] | None = None  # (уровень: seller|tenant, uuid)
        # Сообщение владельцу, когда подготовка роли не удалась несколько раз подряд; подключает runner.
        self.role_alert: Callable[[str, str, int, str], None] | None = None  # уровень, uuid, попыток, причина

    def agent_turn(
        self,
        prompt: str,
        *,
        session_key: str,
        model: str | None = None,
        provider: str | None = None,
        system: str = "",
        tool_handler: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        mode: str = "readonly",
        cwd: str | None = None,
        timeout: int = 900,
        owner_authorized: bool = False,
        cancelled: Callable[[], bool] | None = None,
        effort: str | None = None,
        include_project_tools: bool = True,
        progress_callback: Callable[[str], None] | None = None,
    ) -> LlmResult:
        """Native tool-capable turn for the agent; no provider/model fallback.

        Business facts and conversation context remain in Store and local transcripts.
        Native background turns are ephemeral and never create desktop chat history.
        """
        from .app_server import AppServerError, AppServerTurn

        if not session_key:
            raise ValueError("agent session_key is required")
        model = model or self.cfg.agent.owner_model
        provider = provider or self.cfg.agent.owner_provider
        chosen_effort = effort or self.cfg.llm.codex_effort
        if provider not in ("codex", "claude"):
            raise LlmUnavailable(f"agent provider {provider!r} is not configured")
        if provider == "codex":
            check_effort(model, chosen_effort)
        if mode not in ("readonly", "write", "owner"):
            raise ValueError("agent mode must be readonly, write or owner")
        if mode == "owner" and not owner_authorized:
            raise PermissionError("full project agent mode requires trusted owner authorization")
        work_cwd = cwd or self.cfg.repo
        if not work_cwd:
            raise ValueError("agent project cwd is required")
        work_cwd = str(Path(work_cwd).resolve())
        tools = normalize_agent_tools(tools or [])
        if mode == "readonly" and include_project_tools:
            from .readonly_mcp import TOOLS, Reader, call_tool

            reader = Reader(work_cwd)
            project_tools = [{**spec, "type": "function"} for spec in TOOLS]
            tools = [*(tools or []), {"type": "namespace", "name": "project",
                                       "description": "Read project files and Git history safely",
                                       "tools": project_tools}]
            original_handler = tool_handler

            def scoped_handler(name: str, args: dict[str, Any]) -> dict[str, Any]:
                if name.startswith("project."):
                    output, failed = call_tool(reader, name.split(".", 1)[1], args)
                    return {"text": output, "error": failed}
                if original_handler is None:
                    raise ValueError("tool unavailable")
                return original_handler(name, args)

            tool_handler = scoped_handler
        if provider == "claude":
            return self._claude_agent_turn(
                prompt, session_key=session_key, model=model, system=system,
                tools=tools or [], tool_handler=tool_handler, mode=mode,
                cwd=work_cwd, timeout=timeout, cancelled=cancelled,
                effort=effort, progress_callback=progress_callback,
            )
        signature = agent_capability_signature(tools, work_cwd)
        key = f"agent_session:{session_key}:{provider}:{model}:{mode}"
        saved = self.store.kv_get(key, {})
        state = saved if isinstance(saved, dict) else {}
        handoff = str(state.get("handoff") or "")
        original_prompt = prompt
        prompt = self._background_prompt(key, prompt, handoff=handoff)
        turn = AppServerTurn(self.cfg.llm.codex_bin, timeout=timeout)

        try:
            answer, thread_id, occupied = turn.run(
                prompt, model=model, provider=provider, effort=chosen_effort,
                cwd=work_cwd, mode=mode,
                system=prompts.WMS_SYSTEM_POLICY + (f"\n\n{system}" if system else ""),
                session_id=None, tools=tools or [], tool_handler=tool_handler,
                cancelled=cancelled,
                progress_callback=progress_callback,
                redact_error=self.cfg.redact,
            )
        except (AppServerError, OSError) as exc:
            raise LlmUnavailable(f"native agent turn failed: {type(exc).__name__}") from exc
        self._remember_background(key, original_prompt, answer)
        self.store.kv_set(key, {"thread_id": None, "handoff": handoff,
                                "legacy_thread_id": state.get("legacy_thread_id") or state.get("thread_id"),
                                "rollover": False, "capability_signature": signature})
        self.store.log_llm(cli=provider, model=model, effort=chosen_effort,
                           role="agent", ticket_id=None, ok=True)
        return LlmResult(answer, provider, model, thread_id)

    def _claude_agent_turn(
        self, prompt: str, *, session_key: str, model: str, system: str,
        tools: list[dict[str, Any]],
        tool_handler: Callable[[str, dict[str, Any]], dict[str, Any]] | None,
        mode: str, cwd: str, timeout: int,
        cancelled: Callable[[], bool] | None,
        effort: str | None,
        progress_callback: Callable[[str], None] | None,
    ) -> LlmResult:
        """Claude CLI keeps native tools; JSON tool requests bridge service tools.

        The existing JSON CLI call is blocking, so callback stages report actual
        start and service-tool calls, not invented model reasoning.
        """
        if effort is not None and effort not in {"low", "medium", "high", "xhigh", "max"}:
            raise ValueError("unsupported Claude effort")
        key = f"agent_session:{session_key}:claude:{model}:{mode}"
        saved = self.store.kv_get(key, {})
        state = saved if isinstance(saved, dict) else {}
        session_id = state.get("thread_id")
        system_text = prompts.WMS_SYSTEM_POLICY + (f"\n\n{system}" if system else "")
        handoff = str(state.get("handoff") or "")
        if state.get("rollover") and session_id:
            argv = self.build_claude(model, "text", (session_id, True), system_text, cwd)
            if effort is not None:
                argv += ["--effort", effort]
            transfer = self.exec(
                argv, cwd, min(timeout, 300),
                "Сохрани передачу следующей сессии: цель, подтверждённые факты и источники, "
                "уже совершённые действия, открытые вопросы и следующий шаг. Ничего не выполняй.",
            )
            handoff_text, _, failed = _parse_claude(transfer)
            if transfer.rc != 0 or failed or not handoff_text.strip():
                raise LlmUnavailable("Claude context handoff unavailable; old session retained")
            handoff = handoff_text
            session_id = None
            self.store.kv_set(key, {"thread_id": None, "handoff": handoff,
                                    "rollover": False})
        if handoff and not session_id:
            prompt = f"Передача прошлой сессии (сверяй с авторитетным состоянием):\n{handoff}\n\n{prompt}"
        names: list[tuple[str, str, dict[str, Any]]] = []
        for spec in tools:
            if spec.get("type") == "namespace":
                names.extend((f"{spec['name']}.{tool['name']}", tool.get("description", ""),
                              tool.get("inputSchema", {})) for tool in spec.get("tools", []))
            elif spec.get("type") == "function":
                names.append((spec["name"], spec.get("description", ""),
                              spec.get("inputSchema", {})))
        if names:
            system_text += ("\n\nСервисные инструменты доступны по запросу JSON: "
                            "{\"tool\":\"имя\",\"arguments\":{...}}. "
                            "После результата продолжай работу. Финальный ответ: "
                            "{\"final\":\"текст\"}. Сервисные инструменты: "
                            + json.dumps(names, ensure_ascii=False))
        allowed = {name for name, _, _ in names}
        current = prompt
        for turn_number in range(20):
            if cancelled is not None and cancelled():
                raise LlmUnavailable("Claude turn cancelled; external outcome must be verified")
            session = (str(session_id), True) if session_id else (str(uuid.uuid4()), False)
            claude_mode = "text" if mode == "readonly" else mode
            argv = self.build_claude(model, claude_mode, session, system_text, cwd)
            if effort is not None:
                argv += ["--effort", effort]
            if turn_number == 0 and progress_callback is not None:
                progress_callback("Claude: ход модели начат.")
            result = self.exec(argv, cwd, timeout, current)
            answer, new_id, is_error = _parse_claude(result)
            if cancelled is not None and cancelled():
                raise LlmUnavailable("Claude turn cancelled; external outcome must be verified")
            if result.rc != 0 or is_error:
                raise LlmUnavailable("explicit Claude model unavailable or turn failed")
            session_id = new_id or session[0]
            try:
                raw = json.loads(result.out)
            except ValueError:
                raw = {}
            usage = raw.get("usage") or {}
            occupied = 0
            if int(raw.get("num_turns") or 1) == 1 and isinstance(usage, dict):
                occupied = sum(int(usage.get(field) or 0) for field in (
                    "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            self.store.kv_set(key, {"thread_id": session_id, "handoff": handoff,
                                    "rollover": occupied >= self.cfg.agent.context_limit_tokens})
            if not allowed:
                return LlmResult(answer, "claude", model, session_id)
            try:
                parsed = extract_json(answer)
            except ValueError:
                return LlmResult(answer, "claude", model, session_id)
            if "final" in parsed:
                return LlmResult(str(parsed["final"]), "claude", model, session_id)
            name, args = parsed.get("tool"), parsed.get("arguments")
            if (not isinstance(name, str) or name not in allowed
                    or not isinstance(args, dict) or tool_handler is None):
                current = "Сервисный инструмент недоступен или аргументы неверны; исправь вызов."
                continue
            if progress_callback is not None:
                progress_callback(f"Claude: вызван сервисный инструмент {name}.")
            try:
                output = tool_handler(name, args)
            except Exception as exc:  # noqa: BLE001 - let model recover from tool failure
                output = {"error": type(exc).__name__}
            current = "Результат инструмента:\n" + json.dumps(output, ensure_ascii=False)
        raise LlmError("too many service tool calls in one Claude turn")

    # -- выбор CLI и модели ----------------------------------------------------------
    def cooling(self, cli: str) -> bool:
        return float(self.store.kv_get(f"cooldown:{cli}", 0)) > time.time()

    def available_clis(self) -> list[str]:
        return [c for c in self.cfg.llm.cli_order if not self.cooling(c)]

    def model_for(self, cli: str, role: str) -> str | None:
        model = self.cfg.llm.models.get(cli, {}).get(role)
        if model and "astra" in model.lower() and role != "review":
            # Astra — только ревьюер (решение владельца); ошибка в конфиге не должна её запустить.
            raise ValueError(f"Astra is reviewer-only, but configured for role {role!r}")
        return model

    def effort_for(self, cli: str, role: str) -> str | None:
        if cli != "codex":
            return None
        return "low" if role == "filter" else self.cfg.llm.codex_effort

    def candidates(
        self, role: str, cli_only: str | None, exclude_cli: str | None
    ) -> list[tuple[str, str]]:
        result = []
        for cli in self.available_clis():
            if cli_only and cli != cli_only:
                continue
            if exclude_cli and cli == exclude_cli:
                continue
            model = self.model_for(cli, role)
            if model:
                result.append((cli, model))
        return result

    # -- построение команд -------------------------------------------------------------
    def write_tools(self, cwd: str) -> tuple[list[str], list[str]]:
        """Минимальные права разработчика/макетчика (WMS-641): правка файлов только в своём worktree,
        явный список команд. push, gh, ssh, curl и т. п. выполняет код диспетчера, не модель."""
        bin_dir = self.cfg.hotfix.backend_bin.rstrip("/")
        tools = [f"Bash({name}:*)" for name in ("ruff", "mypy", "pytest")]
        if bin_dir:
            tools += [f"Bash({bin_dir}/{name}:*)" for name in ("ruff", "mypy", "pytest")]
        allowed = [
            "Read", "Grep", "Glob", f"Edit(/{cwd}/**)", f"Write(/{cwd}/**)",
            "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)",
            "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(wc:*)", "Bash(cd:*)",
            "Bash(python -m pytest:*)", "Bash(python3 -m pytest:*)", "Bash(npm run build:*)",
            "Bash(npx tsc:*)", *tools,
        ]
        denied = [
            "Bash(git push:*)", "Bash(git remote:*)", "Bash(git config:*)", "Bash(gh:*)",
            "Bash(ssh:*)", "Bash(scp:*)", "Bash(rsync:*)", "Bash(curl:*)", "Bash(wget:*)",
            "Bash(docker:*)", "Bash(sudo:*)", "Bash(launchctl:*)", "Bash(npm install:*)",
            "Bash(npm publish:*)", "Read(**/*.env)", "Read(**/.env*)", "Read(~/.ssh/**)",
            "Read(~/.wms-support-agent/**)", "Read(~/.config/**)", "Read(~/.aws/**)",
            "Edit(**/.git/**)", "Write(**/.git/**)", "NotebookEdit",
        ]
        return allowed, denied

    def build_claude(
        self, model: str, mode: str, session: tuple[str, bool] | None, system: str | None,
        cwd: str = "", with_db: bool = False, db_log: str | None = None, db_role: str = "",
    ) -> list[str]:
        argv = [self.cfg.llm.claude_bin, "-p", "--model", model, "--output-format", "json"]
        if session is None:
            argv.append("--no-session-persistence")
        elif session[1]:
            argv += ["--resume", session[0]]
        else:
            argv += ["--session-id", session[0]]
        if system:
            argv += ["--system-prompt", system]
        if mode in ("readonly", "write") and self.cfg.sandbox.enabled:
            # Встроенная песочница Bash Claude Code: запись только в cwd и tmp, без сети,
            # чтение конфига агента и учётных данных закрыто (проверено вживую).
            sandbox.require()
            protect = [str(Path(cwd) / ".git")] if cwd else []
            argv += ["--settings", sandbox.claude_settings(
                os.path.expanduser("~"), self.cfg.sandbox.extra_deny_read, protect)]
        if mode == "text":
            argv += ["--tools", "", "--disable-slash-commands", "--setting-sources", ""]
        elif mode == "readonly":
            allowed = list(READONLY_TOOLS)
            if with_db:
                # Чтение боевой базы: единственный MCP-сервер, только его инструмент разрешён.
                command, args = self.prod_sql_server(db_log, db_role)
                argv += ["--mcp-config", json.dumps({"mcpServers": {"proddb": {
                    "command": command, "args": args}}}, ensure_ascii=False), "--strict-mcp-config"]
                allowed.append("mcp__proddb__sql_query")
            argv += ["--permission-mode", "dontAsk", "--allowedTools", *allowed]
            argv += ["--disallowedTools", "Edit", "Write", "NotebookEdit", *secret_read_denies()]
        elif mode == "owner":
            # Only a trusted personal-chat command can reach this mode. Claude's
            # native Bash/Edit/Write tools provide general project work.
            argv += ["--permission-mode", "dontAsk", "--allowedTools",
                     "Bash", "Read", "Grep", "Glob", "Edit", "Write"]
            argv += ["--disallowedTools", *secret_read_denies()]
        else:  # write: разработчик хотфикса / макетчик в своём worktree, без bypassPermissions
            allowed, denied = self.write_tools(cwd)
            denied += [d for d in secret_read_denies() if d not in denied]
            argv += ["--permission-mode", "dontAsk", "--allowedTools", *allowed]
            argv += ["--disallowedTools", *denied]
        return argv

    @staticmethod
    def git_metadata_dirs(root: str) -> list[str]:
        """Каталоги метаданных git (gitdir и common-dir), найденные ДОВЕРЕННЫМ кодом до запуска сервера.

        В связанном worktree `.git` — файл-указатель, а история лежит вне корня; чтению профиля дают
        именно эти проверенные каталоги. Прямое чтение моделью остаётся запрещённым проверкой путей."""
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GIT_CONFIG_NOSYSTEM": "1",
               "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0"}
        try:
            res = subprocess.run(
                ["git", "-C", root, "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
                 "rev-parse", "--absolute-git-dir", "--git-common-dir"],
                capture_output=True, text=True, timeout=20, env=env,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        lines = res.stdout.split("\n")
        if res.returncode != 0 or len([x for x in lines if x]) != 2:
            return []
        dirs = []
        for raw in lines[:2]:
            path = Path(raw) if os.path.isabs(raw) else Path(root) / raw
            real = os.path.realpath(path)
            if os.path.isdir(real) and real not in dirs:
                dirs.append(real)
        return dirs

    def prod_sql_server(self, log_path: str | None = None, db_role: str = "") -> tuple[str, list[str]]:
        """Команда MCP-сервера sql_query: доверенный процесс с ключом ssh, под sandbox-exec (чтение только
        ключа, known_hosts и кода агента; сеть только на порт 22). Модель ключа не видит."""
        c = self.cfg.prod_db
        script = Path(prod_sql_mcp.__file__).resolve()
        key = os.path.expanduser(c.ssh_key_path)
        known = os.path.expanduser(c.known_hosts) if c.known_hosts else ""
        args = [str(script), "--ssh-host", c.ssh_host, "--ssh-user", c.ssh_user, "--key", key,
                "--row-limit", str(c.row_limit), "--timeout", str(c.timeout_sec),
                "--max-bytes", str(c.max_bytes), "--ssh-bin", c.ssh_bin, "--db-role", db_role]
        if known:
            args += ["--known-hosts", known]
        if log_path:
            args += ["--log", log_path]
        # без -I: каталог скрипта нужен в sys.path (рядом лежит prod_sql); -E -s -S изолируют окружение
        command, full = sys.executable, ["-E", "-s", "-S", *args]
        if self.cfg.sandbox.enabled:
            sandbox.require()
            readable = [str(script.parent), sys.prefix, sys.base_prefix, key,
                        known or os.path.expanduser("~/.ssh/known_hosts")]
            profile = sandbox.prod_sql_profile(readable, [log_path] if log_path else None)
            command, full = sandbox.SANDBOX_EXEC, ["-p", profile, sys.executable, *full]
        return command, full

    def with_prod_db(self, role: str, mode: str, db_role: str = "") -> bool:
        """Инструмент базы получает только вызов по обращению с привязанным селлером (R42):
        без db_role инструмента нет вовсе, общая роль wms_agent_ro обращениям не выдаётся."""
        return bool(self.cfg.prod_db.enabled and mode == "readonly" and role in ("analyst", "review")
                    and ROLE_RE.match(db_role))

    def ticket_db_role(self, ticket_id: int | None) -> str:
        """Роль базы обращения: селлера или фулфилмента (уровень привязки). Берётся доверенным кодом из
        записи обращения (область зафиксирована при создании по привязке чата или по данным формы с
        сервера); текст клиента и модель на неё не влияют."""
        if ticket_id is None:
            return ""
        data = self.store.data(ticket_id)
        level = "tenant" if data.get("level") == "tenant" else "seller"
        scope_id = str(data.get("tenant_id" if level == "tenant" else "seller_id") or "")
        try:
            role = role_for_scope(level, scope_id) if scope_id else ""
        except SqlRefused:
            return ""
        if role and self.role_ensurer is not None and not self._role_ready(role, level, scope_id):
            return ""  # не удалось подготовить доступ: инструмента базы у этого вызова нет
        return role

    ROLE_TTL_SEC = 6 * 3600
    ROLE_RETRY_BASE_SEC = 600  # пауза после неудачи удваивается: 10 мин, 20 мин, 40 мин ... до 6 ч
    ROLE_ALERT_AFTER = 3

    def _role_ready(self, role: str, level: str, scope_id: str) -> bool:
        """Роль и политики на сервере (идемпотентно). Успех помнится 6 часов; на текущей версии сервер
        отвечает дёшево (без блокировок таблиц). Сбой: пауза с нарастанием (не крутимся в цикле), после
        ROLE_ALERT_AFTER неудач подряд один раз сообщается владельцу. Если роль уже готовилась раньше,
        сбой повторной проверки доступ не отнимает; если ни разу не удалось, у вызова базы нет."""
        key, fail_key = f"role_ready:{role}", f"role_fail:{role}"
        now = time.time()
        last_ok = float(self.store.kv_get(key, 0))
        if now - last_ok < self.ROLE_TTL_SEC:
            return True
        state = self.store.kv_get(fail_key) or {"n": 0, "next": 0}
        if now < float(state["next"]):
            return last_ok > 0  # пауза после неудачи: сервер не дёргаем
        try:
            assert self.role_ensurer is not None
            self.role_ensurer(level, scope_id)
        except Exception as exc:  # noqa: BLE001 - любой сбой шлюза: роль не подтверждена
            attempts = int(state["n"]) + 1
            pause = min(self.ROLE_RETRY_BASE_SEC * 2 ** (attempts - 1), self.ROLE_TTL_SEC)
            self.store.kv_set(fail_key, {"n": attempts, "next": now + pause})
            log.warning("seller role not prepared (%s), attempt %s: %s", role, attempts, type(exc).__name__)
            if attempts == self.ROLE_ALERT_AFTER and self.role_alert is not None:
                self.role_alert(level, scope_id, attempts, str(exc)[:200])
            return last_ok > 0
        self.store.kv_set(key, now)
        self.store.kv_set(fail_key, None)
        return True

    def mcp_args(self, root: str, with_db: bool = False, db_log: str | None = None,
                 db_role: str = "") -> list[str]:
        """Подключение читателя проекта: сервер запускает Codex, но под sandbox-exec (чтение только
        корня проекта и кода самого сервера, без сети и без записи)."""
        script = Path(readonly_mcp.__file__).resolve()
        python = sys.executable
        if self.cfg.sandbox.enabled:
            prof = sandbox.mcp_profile(root, [str(script.parent), sys.prefix, sys.base_prefix,
                                              *self.git_metadata_dirs(root)])
            command, args = sandbox.SANDBOX_EXEC, ["-p", prof, python, "-I", "-S", str(script),
                                                    "--root", root]
            sandbox.require()
        else:
            command, args = python, ["-I", "-S", str(script), "--root", root]
        toml_args = "[" + ", ".join(json.dumps(a, ensure_ascii=False) for a in args) + "]"
        extra: list[str] = []
        if with_db:
            db_command, db_args = self.prod_sql_server(db_log, db_role)
            db_toml = "[" + ", ".join(json.dumps(a, ensure_ascii=False) for a in db_args) + "]"
            extra = ["-c", f"mcp_servers.proddb.command={json.dumps(db_command)}",
                     "-c", f"mcp_servers.proddb.args={db_toml}",
                     "-c", 'mcp_servers.proddb.default_tools_approval_mode="approve"']
        return ["-c", f"mcp_servers.wms.command={json.dumps(command)}",
                "-c", f"mcp_servers.wms.args={toml_args}",
                "-c", 'mcp_servers.wms.default_tools_approval_mode="approve"', *extra]

    def build_codex(
        self, model: str, effort: str | None, mode: str, session_id: str | None,
        cwd: str | None, last_message_file: str, role: str = "", db_log: str | None = None,
        db_role: str = "",
    ) -> list[str]:
        effort = check_effort(model, effort)
        # Background roles keep their context in the bot, never in the desktop sidebar.
        session_id = None
        argv = [self.cfg.llm.codex_bin, "exec", "--ephemeral"]
        argv += ["-m", model]
        if effort:
            argv += ["-c", f'model_reasoning_effort="{effort}"']
        # Пользовательские настройки Codex (MCP, хуки, плагины) не подгружаем. У Codex ВО ВСЕХ
        # режимах отключены командная оболочка и внешние инструменты (проверено вживую). Разработчик
        # (write) только правит файлы через apply_patch в worktree; аналитик (readonly) читает проект
        # лишь через доверенный MCP-читатель readonly_mcp (только чтение внутри корня, под
        # строгим sandbox-exec); проверки делает диспетчер. Модельных команд у Codex нет.
        argv += ["--ignore-user-config", "--ignore-rules"]
        for feature in CODEX_DISABLED_FEATURES:
            argv += ["--disable", feature]
        for setting in CODEX_EXTRA_CONFIG:
            argv += ["-c", setting]
        if mode == "readonly" and cwd:
            argv += self.mcp_args(cwd, with_db=self.with_prod_db(role, mode, db_role), db_log=db_log,
                                  db_role=db_role)
        sbx_mode = {"text": "read-only", "readonly": "read-only", "write": "workspace-write"}[mode]
        if mode == "write":
            argv += ["-c", "sandbox_workspace_write.network_access=false"]
        if not session_id:
            argv += ["-s", sbx_mode, "--color", "never"]
            if cwd:
                argv += ["-C", cwd]
        else:
            argv += ["-c", f'sandbox_mode="{sbx_mode}"']
        argv += ["--json", "--skip-git-repo-check", "-o", last_message_file, "-"]
        return argv

    # -- вызов -------------------------------------------------------------------------
    def ask(
        self,
        role: str,
        prompt: str,
        *,
        context: str | None = None,
        ticket_id: int | None = None,
        session_key: str | None = None,
        cwd: str | None = None,
        mode: str = "text",
        cli_only: str | None = None,
        exclude_cli: str | None = None,
        system: str | None = None,
        timeout: int = 900,
    ) -> LlmResult:
        system = prompts.WMS_SYSTEM_POLICY + (f"\n\n{system}" if system else "")
        options = self.candidates(role, cli_only, exclude_cli)
        if not options:
            raise LlmUnavailable("no_cli_available")
        self.scratch.mkdir(parents=True, exist_ok=True)
        work_cwd = cwd or str(self.scratch)
        last_error = ""
        wants_db = self.cfg.prod_db.enabled and mode == "readonly" and role in ("analyst", "review")
        db_role = self.ticket_db_role(ticket_id) if wants_db else ""
        # Resume сохраняет историю, но правила и снимок обращения могли измениться с прошлого хода.
        full = f"{context}\n\n{prompt}" if context else prompt
        for cli, model in options:
            sessions = self._sessions(ticket_id, session_key)
            existing = sessions.get(cli) if cli != "codex" else None
            history_key = f"role:{ticket_id}:{session_key}:codex:{model}:{mode}" if session_key else ""
            call_prompt = self._background_prompt(history_key, full) if cli == "codex" else full
            for resume in ([True, False] if existing else [False]):
                db_log = self._new_db_log(role, mode, db_role)
                try:
                    try:
                        result = self._run_once(
                            cli, model, role, call_prompt, mode=mode, cwd=work_cwd, system=system,
                            session_id=existing if resume else None, keep_session=bool(session_key),
                            timeout=timeout, db_log=db_log, db_role=db_role,
                        )
                    finally:
                        self._note_db_use(ticket_id, db_log)
                except _LimitHit as hit:
                    self.store.kv_set(
                        f"cooldown:{cli}", time.time() + self.cfg.llm.cooldown_sec
                    )
                    self.store.log_llm(cli=cli, model=model, effort=self.effort_for(cli, role),
                                       role=role, ticket_id=ticket_id, ok=False, error=str(hit))
                    last_error = f"{cli}_limit"
                    break
                except _CallFailed as fail:
                    self.store.log_llm(cli=cli, model=model, effort=self.effort_for(cli, role),
                                       role=role, ticket_id=ticket_id, ok=False, error=str(fail))
                    last_error = f"{cli}_error"
                    continue  # resume не вышел -> новая сессия; затем другой CLI
                self.store.log_llm(cli=cli, model=model, effort=self.effort_for(cli, role),
                                   role=role, ticket_id=ticket_id, ok=True)
                self.store.kv_set("llm_unavailable_notified", False)
                if cli == "codex" and history_key:
                    self._remember_background(history_key, full, result.text)
                if cli != "codex" and session_key and result.session_id:
                    self._save_session(ticket_id, session_key, cli, result.session_id)
                return result
        raise LlmUnavailable(last_error or "no_cli_available")

    def _background_prompt(self, key: str, prompt: str, *, handoff: str = "") -> str:
        if not key:
            return prompt
        history = self.store.kv_get(f"background_context:{key}", [])
        if not history and not handoff:
            return prompt
        return ("Предыдущие сообщения этой рабочей сессии (история, не новые поручения; "
                "результаты действий сверяй с текущими данными и Git):\n"
                + json.dumps({"legacy_summary": handoff, "messages": history}, ensure_ascii=False)
                + "\n\nТекущее поручение:\n" + prompt)

    def _remember_background(self, key: str, prompt: str, answer: str) -> None:
        history = self.store.kv_get(f"background_context:{key}", [])
        exchange = {"prompt": prompt, "answer": answer}
        folder = self.cfg.state_path / "background-sessions"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (hashlib.sha256(key.encode()).hexdigest() + ".jsonl")
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"session": key, **exchange}, ensure_ascii=False) + "\n")
        history.append(exchange)
        # Full history stays in the transcript; prompts use a bounded recent window.
        while len(history) > 1 and (len(history) > 16 or len(json.dumps(history)) > 120_000):
            history.pop(0)
        self.store.kv_set(f"background_context:{key}", history)

    def _sessions(self, ticket_id: int | None, key: str | None) -> dict[str, str]:
        if not key:
            return {}
        if ticket_id is None:
            value = self.store.kv_get(f"llm_sessions:{key}", {})
            return dict(value) if isinstance(value, dict) else {}
        sessions = self.store.data(ticket_id).get("sessions", {})
        value = sessions.get(key, {})
        return dict(value) if isinstance(value, dict) else {}

    def _save_session(self, ticket_id: int | None, key: str, cli: str, session_id: str) -> None:
        if ticket_id is None:
            sessions = self._sessions(None, key)
            sessions[cli] = session_id
            self.store.kv_set(f"llm_sessions:{key}", sessions)
            return
        sessions = self.store.data(ticket_id).get("sessions", {})
        sessions.setdefault(key, {})[cli] = session_id
        self.store.patch_data(ticket_id, sessions=sessions)

    def _new_db_log(self, role: str, mode: str, db_role: str = "") -> str | None:
        """Файл следа успешных SQL-запросов этого вызова: пишет только доверенный сервер sql_query,
        лежит в каталоге состояния агента (модели недоступен)."""
        if not self.with_prod_db(role, mode, db_role):
            return None
        folder = self.cfg.state_path / "prod-sql-log"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{uuid.uuid4().hex}.log"
        path.touch()
        return str(path)

    def _note_db_use(self, ticket_id: int | None, db_log: str | None) -> None:
        """Если сервер хоть раз успешно вернул данные, обращение помечается db_used: любое сообщение
        клиенту по нему уходит только через предпросмотр владельцу (N1)."""
        if not db_log:
            return
        try:
            used = bool(Path(db_log).read_text(encoding="utf-8").strip())
        except OSError:
            used = True  # след не прочитан или его нет: считаем, что база использовалась (fail closed)
        try:
            Path(db_log).unlink(missing_ok=True)
        except OSError:
            pass
        if used and ticket_id is not None:
            self.store.patch_data(ticket_id, db_used=True)

    def _run_once(
        self, cli: str, model: str, role: str, prompt: str, *, mode: str, cwd: str,
        system: str | None, session_id: str | None, keep_session: bool, timeout: int,
        db_log: str | None = None, db_role: str = "",
    ) -> LlmResult:
        if cli == "claude":
            if keep_session:
                session = (session_id, True) if session_id else (str(uuid.uuid4()), False)
            else:
                session = None
            argv = self.build_claude(model, mode, session, system, cwd,
                                     with_db=self.with_prod_db(role, mode, db_role), db_log=db_log,
                                     db_role=db_role)
            res = self.exec(argv, cwd, timeout, prompt)
            text, new_id, is_error = _parse_claude(res)
            if res.rc != 0 or is_error:
                blob = f"{res.err}\n{text}"
                if LIMIT_PATTERNS.search(blob) or res.rc == 127:
                    raise _LimitHit(blob[:200])
                raise _CallFailed(blob[:200])
            return LlmResult(text, "claude", model, new_id or (session[0] if session else None))
        # codex
        # У Codex нет используемого здесь флага --system-prompt: передаём правила в каждом ходе.
        if system:
            prompt = f"{system}\n\n{prompt}"
        with sandbox.temp_dir() as tmp:
            out_file = str(Path(tmp) / "last.txt")
            argv = self.build_codex(model, self.effort_for("codex", role), mode, session_id, cwd,
                                    out_file, role=role, db_log=db_log, db_role=db_role)
            res = self.exec(argv, cwd, timeout, prompt)
            text = ""
            try:
                text = Path(out_file).read_text(encoding="utf-8")
            except OSError:
                pass
        if res.rc != 0 or not text.strip():
            blob = f"{res.err}\n{res.out[-500:]}"
            if LIMIT_PATTERNS.search(blob) or res.rc == 127:
                raise _LimitHit(blob[:200])
            raise _CallFailed(blob[:200])
        return LlmResult(text, "codex", model, _codex_session_id(res.out))

    # -- JSON-ответы -------------------------------------------------------------------
    def ask_json(self, role: str, prompt: str, **kwargs: Any) -> tuple[dict[str, Any], LlmResult]:
        result = self.ask(role, prompt, **kwargs)
        try:
            return extract_json(result.text), result
        except ValueError:
            retry = self.ask(
                role,
                "Твой предыдущий ответ не был JSON. Верни ТОЛЬКО один JSON-объект по заданной "
                f"форме, без пояснений.\n\nПредыдущий ответ:\n{result.text[:3000]}",
                **{**kwargs, "session_key": None, "context": None},
            )
            try:
                return extract_json(retry.text), retry
            except ValueError:
                raise LlmError("model_answer_is_not_json") from None


class _LimitHit(Exception):
    pass


class _CallFailed(Exception):
    pass


def _parse_claude(res: ExecResult) -> tuple[str, str | None, bool]:
    try:
        body = json.loads(res.out)
    except ValueError:
        return res.out, None, res.rc != 0
    return str(body.get("result", "")), body.get("session_id"), bool(body.get("is_error"))


def _codex_session_id(stdout: str) -> str | None:
    """Живой вывод `codex exec --json` (проверено): первая строка {"type":"thread.started",
    "thread_id":"<uuid>"}. Не нашли — продолжаем без resume."""
    for line in stdout.splitlines()[:8]:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        found = _find_key(event, ("thread_id", "session_id", "conversation_id"))
        if found:
            return found
    return None


def _find_key(value: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(value, dict):
        for key in keys:
            if isinstance(value.get(key), str):
                return str(value[key])
        for inner in value.values():
            found = _find_key(inner, keys)
            if found:
                return found
    elif isinstance(value, list):
        for inner in value:
            found = _find_key(inner, keys)
            if found:
                return found
    return None
