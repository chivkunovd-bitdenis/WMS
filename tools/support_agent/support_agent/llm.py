"""Вызовы моделей только через залогиненные CLI владельца: claude -p и codex exec (R36).

Платных API-ключей нет. Astra всегда с явным effort не выше high (жёсткое правило AGENTS.md).
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
READONLY_TOOLS = [
    "Read", "Grep", "Glob", "Bash(git log:*)", "Bash(git show:*)", "Bash(git diff:*)",
    "Bash(git grep:*)", "Bash(git status:*)", "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)",
    "Bash(rg:*)", "Bash(find:*)", "Bash(wc:*)",
]


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
    try:
        proc = subprocess.run(
            argv, cwd=cwd, input=stdin or "", capture_output=True, text=True, timeout=timeout
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
        return self.cfg.llm.models.get(cli, {}).get(role)

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
    def build_claude(
        self, model: str, mode: str, session: tuple[str, bool] | None, system: str | None
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
        if mode == "text":
            argv += ["--tools", "", "--disable-slash-commands", "--setting-sources", ""]
        elif mode == "readonly":
            argv += ["--permission-mode", "dontAsk", "--allowedTools", *READONLY_TOOLS]
            argv += ["--disallowedTools", "Edit", "Write", "NotebookEdit"]
        else:  # write: разработчик хотфикса в своём worktree
            argv += ["--permission-mode", "bypassPermissions"]
        return argv

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
        sandbox = {"text": "read-only", "readonly": "read-only", "write": "danger-full-access"}[mode]
        if not session_id:
            argv += ["-s", sandbox, "--color", "never"]
            if cwd:
                argv += ["-C", cwd]
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
            raise LlmUnavailable(
                "claude_only_unavailable" if cli_only else "no_cli_available"
            )
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
            argv = self.build_claude(model, mode, session, system)
            res = self.exec(argv, cwd, timeout, prompt)
            text, new_id, is_error = _parse_claude(res)
            if res.rc != 0 or is_error:
                blob = f"{res.err}\n{text}"
                if LIMIT_PATTERNS.search(blob) or res.rc == 127:
                    raise _LimitHit(blob[:200])
                raise _CallFailed(blob[:200])
            return LlmResult(text, "claude", model, new_id or (session[0] if session else None))
        # codex
        out_file = str(self.scratch / f"codex-last-{uuid.uuid4().hex}.txt")
        argv = self.build_codex(model, self.effort_for("codex", role), mode, session_id, cwd, out_file)
        res = self.exec(argv, cwd, timeout, prompt)
        text = ""
        try:
            text = Path(out_file).read_text(encoding="utf-8")
            Path(out_file).unlink()
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
    """Best effort: ищем id сессии в первых строках JSONL; не нашли — продолжаем без resume."""
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
