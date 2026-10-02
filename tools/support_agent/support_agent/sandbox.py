"""Граница на уровне ОС (macOS Seatbelt, sandbox-exec) для недоверенного кода и модельных сессий.

Проверки из worktree (ruff, mypy, pytest) и сессия Codex-разработчика запускаются под профилем:
запись только в свои каталоги, чтение конфига агента и учётных данных владельца запрещено, а для
проверок ещё и сеть. Для Claude используется встроенная песочница Bash самого Claude Code
(настройка sandbox), которая реально блокирует дочерние процессы (проверено вживую).
Если песочница включена, но недоступна, запуск отклоняется (fail closed), а не идёт без неё.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SANDBOX_EXEC = "/usr/bin/sandbox-exec"

# Что никогда не должно читаться недоверенным кодом (относительно домашнего каталога).
DEFAULT_DENY_READ = [
    ".wms-support-agent", ".ssh", ".config/gh", ".codex/auth.json", ".claude", ".claude.json",
    "Downloads/insurance-benchmark", ".netrc", ".aws", ".docker", ".gnupg", ".kube",
    "Library/Keychains", ".config/git", ".npmrc", ".pypirc",
]
# Переменные окружения, которые не передаются дочерним процессам CLI и проверок.
SENSITIVE_ENV = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GH_TOKEN", "GITHUB_TOKEN", "TELEGRAM_BOT_TOKEN",
                 "TRELLO_API_KEY", "TRELLO_TOKEN", "AWS_SECRET_ACCESS_KEY", "SUPPORT_AGENT_CONFIG")


class SandboxUnavailable(Exception):
    pass


def available() -> bool:
    return sys.platform == "darwin" and os.path.exists(SANDBOX_EXEC)


def require() -> None:
    if not available():
        raise SandboxUnavailable("песочница sandbox-exec недоступна, код из worktree не запускаю")


def deny_read_paths(home: str, extra: list[str] | None = None) -> list[str]:
    paths = [str(Path(home) / rel) for rel in DEFAULT_DENY_READ]
    paths += [os.path.expanduser(p) for p in (extra or [])]
    return paths


def _q(path: str) -> str:
    real = os.path.realpath(path)
    return '"' + real.replace("\\", "\\\\").replace('"', '\\"') + '"'


def profile(
    write_dirs: list[str], deny_read: list[str], *, allow_network: bool,
    keep_readable: list[str] | None = None, protect_write: list[str] | None = None,
) -> str:
    """Профиль Seatbelt: по умолчанию всё разрешено, затем запреты (последнее правило сильнее)."""
    rules = ["(version 1)", "(allow default)"]
    if not allow_network:
        rules.append("(deny network*)")
    rules.append("(deny file-write*)")
    rules.append('(allow file-write* (subpath "/dev"))')
    for path in write_dirs:
        rules.append(f"(allow file-write* (subpath {_q(path)}))")
    for path in protect_write or []:  # например <worktree>/.git: метаданные Git менять нельзя (N1)
        rules.append(f"(deny file-write* (subpath {_q(path)}))")
    for path in deny_read:
        rules.append(f"(deny file-read* (subpath {_q(path)}))")
    for path in keep_readable or []:  # исключения из запрета чтения (например, ~/.codex для Codex)
        rules.append(f"(allow file-read* (subpath {_q(path)}))")
    return "\n".join(rules)


def wrap(argv: list[str], prof: str) -> list[str]:
    require()
    return [SANDBOX_EXEC, "-p", prof, *argv]


@contextmanager
def temp_dir() -> Iterator[str]:
    path = tempfile.mkdtemp(prefix="wms-sbx-")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def check_argv(
    argv: list[str], worktree: str, tmp: str, home: str, extra_deny: list[str] | None
) -> list[str]:
    """Команда проверки: без сети, запись только в worktree и временный каталог, чистое окружение."""
    prof = profile([worktree, tmp], deny_read_paths(home, extra_deny), allow_network=False,
                   protect_write=[str(Path(worktree) / ".git")])
    env = ["/usr/bin/env", "-i", f"PATH={os.environ.get('PATH', '/usr/bin:/bin')}", f"HOME={tmp}",
           f"TMPDIR={tmp}", "LANG=en_US.UTF-8", f"npm_config_cache={tmp}/npm", "PYTHONDONTWRITEBYTECODE=1"]
    return wrap([*env, *argv], prof)


def claude_settings(
    home: str, extra_deny: list[str] | None, protect_write: list[str] | None = None
) -> str:
    """Встроенная песочница Bash Claude Code: запись в cwd и tmp, без сети, чтение секретов закрыто."""
    deny = deny_read_paths(home, extra_deny)
    return json.dumps({
        "sandbox": {
            "enabled": True,
            "allowUnsandboxedCommands": False,
            "filesystem": {"denyRead": deny, "denyWrite": list(protect_write or [])},
        }
    })
