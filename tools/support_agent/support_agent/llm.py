"""Вызовы моделей только через залогиненные CLI владельца: claude -p и codex exec (R36).

Платных API-ключей нет. Astra всегда с явным effort не выше high (жёсткое правило AGENTS.md).
"""

from __future__ import annotations

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

from . import readonly_mcp, sandbox
from .config import Config
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


class LlmRouter:
    def __init__(self, cfg: Config, store: Store, exec_fn: ExecFn = default_exec) -> None:
        self.cfg = cfg
        self.store = store
        self.exec = exec_fn
        self.scratch = cfg.state_path / "scratch"

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
        cwd: str = "",
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
            argv += ["--permission-mode", "dontAsk", "--allowedTools", *READONLY_TOOLS]
            argv += ["--disallowedTools", "Edit", "Write", "NotebookEdit", *secret_read_denies()]
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

    def mcp_args(self, root: str) -> list[str]:
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
        return ["-c", f"mcp_servers.wms.command={json.dumps(command)}",
                "-c", f"mcp_servers.wms.args={toml_args}",
                "-c", 'mcp_servers.wms.default_tools_approval_mode="approve"']

    def build_codex(
        self, model: str, effort: str | None, mode: str, session_id: str | None,
        cwd: str | None, last_message_file: str,
    ) -> list[str]:
        effort = check_effort(model, effort)
        argv = [self.cfg.llm.codex_bin, "exec"]
        if session_id:
            argv += ["resume", session_id]
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
            argv += self.mcp_args(cwd)
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
        options = self.candidates(role, cli_only, exclude_cli)
        if not options:
            raise LlmUnavailable("no_cli_available")
        self.scratch.mkdir(parents=True, exist_ok=True)
        work_cwd = cwd or str(self.scratch)
        last_error = ""
        for cli, model in options:
            sessions = self._sessions(ticket_id, session_key)
            existing = sessions.get(cli)
            for resume in ([True, False] if existing else [False]):
                full = prompt if resume else (f"{context}\n\n{prompt}" if context else prompt)
                try:
                    result = self._run_once(
                        cli, model, role, full, mode=mode, cwd=work_cwd, system=system,
                        session_id=existing if resume else None, keep_session=bool(session_key),
                        timeout=timeout,
                    )
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
                if session_key and ticket_id is not None and result.session_id:
                    self._save_session(ticket_id, session_key, cli, result.session_id)
                return result
        raise LlmUnavailable(last_error or "no_cli_available")

    def _sessions(self, ticket_id: int | None, key: str | None) -> dict[str, str]:
        if ticket_id is None or not key:
            return {}
        sessions = self.store.data(ticket_id).get("sessions", {})
        value = sessions.get(key, {})
        return dict(value) if isinstance(value, dict) else {}

    def _save_session(self, ticket_id: int, key: str, cli: str, session_id: str) -> None:
        sessions = self.store.data(ticket_id).get("sessions", {})
        sessions.setdefault(key, {})[cli] = session_id
        self.store.patch_data(ticket_id, sessions=sessions)

    def _run_once(
        self, cli: str, model: str, role: str, prompt: str, *, mode: str, cwd: str,
        system: str | None, session_id: str | None, keep_session: bool, timeout: int,
    ) -> LlmResult:
        if cli == "claude":
            if keep_session:
                session = (session_id, True) if session_id else (str(uuid.uuid4()), False)
            else:
                session = None
            argv = self.build_claude(model, mode, session, system, cwd)
            res = self.exec(argv, cwd, timeout, prompt)
            text, new_id, is_error = _parse_claude(res)
            if res.rc != 0 or is_error:
                blob = f"{res.err}\n{text}"
                if LIMIT_PATTERNS.search(blob) or res.rc == 127:
                    raise _LimitHit(blob[:200])
                raise _CallFailed(blob[:200])
            return LlmResult(text, "claude", model, new_id or (session[0] if session else None))
        # codex
        with sandbox.temp_dir() as tmp:
            out_file = str(Path(tmp) / "last.txt")
            argv = self.build_codex(model, self.effort_for("codex", role), mode, session_id, cwd,
                                    out_file)
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
