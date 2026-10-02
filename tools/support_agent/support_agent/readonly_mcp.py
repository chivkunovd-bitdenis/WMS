"""Доверенный читатель проекта для Codex-аналитика (MCP по stdio, только стандартная библиотека).

У Codex-аналитика нет командной оболочки: код проекта он читает ТОЛЬКО через эти инструменты.
Всё строго внутри корня (--root): пути канонизируются, выход за корень, символические ссылки,
внутренности .git и файлы с секретами отклоняются. Сервер запускается под sandbox-exec
(чтение только корня и самого агента, без сети, без записи), см. llm.py.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

PROTOCOL = "2024-11-05"
MAX_READ = 50_000
MAX_LIST = 500
MAX_HITS = 200
MAX_OUT = 60_000
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
SECRET_NAMES = ("*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*", "*.keystore", ".netrc",
                ".npmrc", ".pypirc", "credentials*", "secrets*", "*.secret", "*.secrets", ".htpasswd")
GIT_HARDEN = ["-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "core.pager=cat",
              "-c", "diff.external=", "-c", "core.untrackedCache=false", "--no-pager"]
REV_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./~^@-]{0,99}$")


class Refused(Exception):
    pass


class Reader:
    def __init__(self, root: str) -> None:
        self.root = Path(os.path.realpath(root))

    # -- проверка пути ---------------------------------------------------------------
    def resolve(self, rel: str) -> Path:
        """Путь внутри корня: без абсолютных, без .., без символических ссылок по пути."""
        if not isinstance(rel, str) or "\0" in rel:
            raise Refused("некорректный путь")
        if rel.startswith(("/", "~")) or os.path.isabs(rel):
            raise Refused("абсолютные пути запрещены")
        parts = [p for p in Path(rel).parts if p not in ("", ".")]
        if ".." in parts:
            raise Refused("выход за корень проекта запрещён")
        current = self.root
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise Refused("символические ссылки запрещены")
        real = Path(os.path.realpath(current))
        if real != self.root and self.root not in real.parents:
            raise Refused("выход за корень проекта запрещён")
        self.check_name(parts)
        return current

    @staticmethod
    def check_name(parts: list[str]) -> None:
        """ЕДИНАЯ проверка компонентов относительного пути, без учёта регистра (APFS нечувствительна):
        её проходят read_file, list_files, search и каждый каталог и файл при обходе."""
        for part in parts:
            low = part.lower()
            if low == ".git":
                raise Refused("внутренности .git недоступны (используйте git_log и git_show)")
            if low == ".env" or low.startswith(".env.") or low.endswith(".env"):
                raise Refused("файлы окружения недоступны")
            if any(fnmatch.fnmatch(low, pat) for pat in SECRET_NAMES):
                raise Refused("файл похож на секрет и недоступен")

    def rel(self, path: Path) -> str:
        return str(path.relative_to(self.root)) or "."

    # -- инструменты -----------------------------------------------------------------
    def list_files(self, path: str = ".", max_entries: int = 200) -> str:
        target = self.resolve(path)
        if not target.is_dir():
            raise Refused("это не каталог")
        out = []
        for entry in sorted(target.iterdir()):
            if entry.is_symlink() or entry.name.lower() in SKIP_DIRS:
                continue
            try:
                self.check_name([entry.name])
            except Refused:
                continue
            out.append(self.rel(entry) + ("/" if entry.is_dir() else ""))
            if len(out) >= min(max_entries, MAX_LIST):
                out.append("… список обрезан")
                break
        return "\n".join(out) or "(пусто)"

    def read_file(self, path: str, offset: int = 0, max_bytes: int = MAX_READ) -> str:
        target = self.resolve(path)
        if not target.is_file():
            raise Refused("это не файл")
        limit = max(1, min(int(max_bytes), MAX_READ))
        with open(target, "rb") as fh:
            fh.seek(max(0, int(offset)))
            data = fh.read(limit + 1)
        if b"\0" in data[:4096]:
            raise Refused("двоичный файл")
        text = data[:limit].decode("utf-8", "replace")
        return text + ("\n… файл продолжается, читайте дальше через offset" if len(data) > limit else "")

    def search(self, pattern: str, path: str = ".", glob: str = "*") -> str:
        base = self.resolve(path)
        try:
            rx = re.compile(pattern)
        except re.error:
            rx = re.compile(re.escape(pattern))
        hits: list[str] = []
        files = [base] if base.is_file() else self._walk(base)
        for file in files:
            if not fnmatch.fnmatch(file.name, glob):
                continue
            try:
                if file.stat().st_size > MAX_READ * 5:
                    continue
                text = file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{self.rel(file)}:{number}: {line[:300]}")
                    if len(hits) >= MAX_HITS:
                        return "\n".join(hits) + "\n… результатов слишком много, уточните запрос"
        return "\n".join(hits) or "(ничего не найдено)"

    def _walk(self, base: Path) -> list[Path]:
        found: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            kept = []
            for d in sorted(dirnames):  # запретный каталог отсекается целиком, вместе со всем содержимым
                if d.lower() in SKIP_DIRS or os.path.islink(os.path.join(dirpath, d)):
                    continue
                try:
                    self.check_name([d])
                except Refused:
                    continue
                kept.append(d)
            dirnames[:] = kept
            for name in sorted(filenames):
                full = Path(dirpath) / name
                if full.is_symlink():
                    continue
                try:
                    self.check_name(list(full.relative_to(self.root).parts))  # полный путь, все компоненты
                except Refused:
                    continue
                found.append(full)
        return found

    def _git(self, *args: str) -> str:
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GIT_CONFIG_NOSYSTEM": "1",
               "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0", "LANG": "C.UTF-8"}
        res = subprocess.run(["git", "-C", str(self.root), *GIT_HARDEN, *args], capture_output=True,
                             text=True, timeout=60, env=env)
        if res.returncode != 0:
            raise Refused(f"git: {res.stderr.strip()[:300]}")
        return res.stdout[:MAX_OUT]

    def git_log(self, max_count: int = 20, path: str = "") -> str:
        args = ["log", f"--max-count={max(1, min(int(max_count), 100))}", "--format=%h %ad %an %s",
                "--date=short"]
        if path:
            self.resolve(path)
            args += ["--", path]
        return self._git(*args) or "(пусто)"

    def git_show(self, rev: str, path: str = "") -> str:
        if not REV_RE.match(rev):
            raise Refused("некорректная ревизия")
        if path:
            self.resolve(path)
            return self._git("show", f"{rev}:{path}")
        return self._git("show", "--stat", "--format=fuller", rev)


TOOLS: list[dict[str, Any]] = [
    {"name": "list_files", "description": "Список файлов каталога проекта (только чтение).",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"},
                                                       "max_entries": {"type": "integer"}}}},
    {"name": "read_file", "description": "Прочитать текстовый файл проекта (с лимитом размера).",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"},
                                                       "offset": {"type": "integer"},
                                                       "max_bytes": {"type": "integer"}},
                     "required": ["path"]}},
    {"name": "search", "description": "Поиск по regex в файлах проекта.",
     "inputSchema": {"type": "object", "properties": {"pattern": {"type": "string"},
                                                       "path": {"type": "string"},
                                                       "glob": {"type": "string"}},
                     "required": ["pattern"]}},
    {"name": "git_log", "description": "История коммитов (только чтение).",
     "inputSchema": {"type": "object", "properties": {"max_count": {"type": "integer"},
                                                       "path": {"type": "string"}}}},
    {"name": "git_show", "description": "Показать коммит или файл на ревизии (rev или rev + path).",
     "inputSchema": {"type": "object", "properties": {"rev": {"type": "string"}, "path": {"type": "string"}},
                     "required": ["rev"]}},
]


def call_tool(reader: Reader, name: str, args: dict[str, Any]) -> tuple[str, bool]:
    try:
        func: Any = {"list_files": reader.list_files, "read_file": reader.read_file, "search": reader.search,
                "git_log": reader.git_log, "git_show": reader.git_show}.get(name)
        if func is None:
            return f"неизвестный инструмент {name}", True
        return str(func(**args))[:MAX_OUT], False
    except Refused as exc:
        return f"ОТКАЗ: {exc}", True
    except (TypeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        return f"ОШИБКА: {type(exc).__name__}", True


def handle(reader: Reader, message: dict[str, Any]) -> dict[str, Any] | None:
    method, msg_id = message.get("method"), message.get("id")
    if msg_id is None:
        return None  # уведомления (initialized и т. п.) ответа не требуют
    if method == "initialize":
        result: dict[str, Any] = {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                                  "serverInfo": {"name": "wms-readonly", "version": "1"}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = message.get("params") or {}
        text, is_error = call_tool(reader, str(params.get("name")), dict(params.get("arguments") or {}))
        result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "method not found"}}
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def serve(root: str) -> None:
    reader = Reader(root)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            reply = handle(reader, json.loads(line))
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    serve(parser.parse_args().root)


if __name__ == "__main__":
    main()
