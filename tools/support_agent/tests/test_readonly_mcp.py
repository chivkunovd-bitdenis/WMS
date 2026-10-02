"""Круг 4: доверенный читатель проекта для Codex-аналитика (MCP по stdio) строго внутри корня."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from support_agent import sandbox
from support_agent.readonly_mcp import MAX_READ, Reader, call_tool

SERVER = Path(__file__).resolve().parents[1] / "support_agent" / "readonly_mcp.py"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "app").mkdir(parents=True)
    (root / "app" / "main.py").write_text("print('hello')\nTARGET = 42\n", encoding="utf-8")
    (root / "README.md").write_text("PROJECT-FILE-CONTENT\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (root / ".env.production").write_text("SECRET=2\n", encoding="utf-8")
    (root / "server.pem").write_text("KEY\n", encoding="utf-8")
    (root / "credentials.json").write_text("{}", encoding="utf-8")
    (root / "bin.dat").write_bytes(b"\x00\x01\x02" * 10)
    (root / "big.txt").write_text("x" * (MAX_READ + 5000), encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("OUTSIDE-MARKER", encoding="utf-8")
    (root / "link-to-file").symlink_to(outside)
    (root / "link-to-dir").symlink_to(tmp_path)
    (root / "inner-link").symlink_to(root / "README.md")  # даже внутренняя ссылка запрещена
    return root


def ask(root: Path, tool: str, **args: object) -> tuple[str, bool]:
    return call_tool(Reader(str(root)), tool, dict(args))


def test_reads_project_files_and_lists_directories(project: Path) -> None:
    text, err = ask(project, "read_file", path="README.md")
    assert text.strip() == "PROJECT-FILE-CONTENT" and not err
    listing, err = ask(project, "list_files", path=".")
    assert "app/" in listing and "README.md" in listing and not err
    assert all(hidden not in listing for hidden in (".git", ".env", "server.pem", "credentials.json",
                                                     "link-to-file", "link-to-dir", "inner-link"))
    assert "app/main.py" in ask(project, "list_files", path="app")[0]


@pytest.mark.parametrize("path", ["../outside-secret.txt", "app/../../outside-secret.txt", "..", "app/../..",
                                   "/etc/hosts", "/", "~/x", "~", "\x00"])
def test_escape_and_absolute_paths_are_refused(project: Path, path: str) -> None:
    text, err = ask(project, "read_file", path=path)
    assert err and text.startswith("ОТКАЗ") and "OUTSIDE-MARKER" not in text


@pytest.mark.parametrize("path", ["link-to-file", "link-to-dir", "link-to-dir/outside-secret.txt", "inner-link"])
def test_symlinks_are_refused_even_inside_project(project: Path, path: str) -> None:
    text, err = ask(project, "read_file", path=path)
    assert err and "символические ссылки" in text and "OUTSIDE-MARKER" not in text
    assert ask(project, "list_files", path=path)[1]


@pytest.mark.parametrize("path", [".git/config", ".git", ".env", ".env.production", "server.pem",
                                   "credentials.json"])
def test_git_internals_env_and_secret_files_are_refused(project: Path, path: str) -> None:
    text, err = ask(project, "read_file", path=path)
    assert err and text.startswith("ОТКАЗ") and "SECRET" not in text


def test_size_limit_binary_and_search(project: Path) -> None:
    text, err = ask(project, "read_file", path="big.txt")
    assert not err and len(text) < MAX_READ + 200 and "файл продолжается" in text
    assert ask(project, "read_file", path="big.txt", max_bytes=10**9)[0].count("x") <= MAX_READ
    assert ask(project, "read_file", path="bin.dat")[0] == "ОТКАЗ: двоичный файл"
    hits, err = ask(project, "search", pattern="TARGET")
    assert "app/main.py:2: TARGET = 42" in hits and not err
    everything, _ = ask(project, "search", pattern=".*")
    assert "SECRET" not in everything and "OUTSIDE-MARKER" not in everything and "KEY" not in everything
    assert ask(project, "search", pattern="x", path="../")[1]


def make_git_repo(root: Path) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["git", "init", "-q", "-b", "main", "."], ["git", "add", "README.md", "app"],
                ["git", "commit", "-qm", "first commit"]):
        subprocess.run(cmd, cwd=root, env=env, check=True, capture_output=True)


def test_git_log_and_show_are_read_only_and_validated(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("PROJECT-FILE-CONTENT\n", encoding="utf-8")
    (root / "app").mkdir()
    (root / "app" / "main.py").write_text("TARGET = 42\n", encoding="utf-8")
    make_git_repo(root)
    log, err = ask(root, "git_log", max_count=5)
    assert "first commit" in log and not err
    shown, err = ask(root, "git_show", rev="HEAD", path="README.md")
    assert shown.strip() == "PROJECT-FILE-CONTENT" and not err
    assert "first commit" in ask(root, "git_show", rev="HEAD")[0]
    for bad in ("--output=/tmp/x", "-p", "HEAD;ls", "$(id)", "", "a" * 200):
        assert ask(root, "git_show", rev=bad)[1], bad
    assert ask(root, "git_show", rev="HEAD", path="../x")[1]
    assert ask(root, "git_show", rev="HEAD", path=".git/config")[1]
    assert ask(root, "git_log", path="/etc")[1]


def rpc(root: Path, messages: list[dict[str, object]], argv_prefix: list[str] | None = None) -> list[dict]:
    argv = [*(argv_prefix or []), sys.executable, "-I", "-S", str(SERVER), "--root", str(root)]
    res = subprocess.run(argv, input="\n".join(json.dumps(m) for m in messages) + "\n", capture_output=True,
                         text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    return [json.loads(line) for line in res.stdout.splitlines()]


def test_stdio_protocol_handshake_tools_list_and_call(project: Path) -> None:
    out = rpc(project, [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "read_file", "arguments": {"path": "README.md"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "write_file", "arguments": {"path": "x", "content": "y"}}},
        {"jsonrpc": "2.0", "id": 5, "method": "nope"},
    ])
    assert [r["id"] for r in out] == [1, 2, 3, 4, 5]  # на уведомление ответа нет
    assert out[0]["result"]["capabilities"] == {"tools": {}}
    names = {t["name"] for t in out[1]["result"]["tools"]}
    assert names == {"list_files", "read_file", "search", "git_log", "git_show"}  # только чтение
    assert out[2]["result"]["content"][0]["text"].strip() == "PROJECT-FILE-CONTENT"
    assert out[3]["result"]["isError"] is True and out[4]["error"]["code"] == -32601


@pytest.mark.skipif(not sandbox.available(), reason="needs macOS sandbox-exec")
def test_server_under_strict_profile_cannot_read_outside_root_write_or_use_network(project: Path) -> None:
    home_probe = Path.home() / ".wms-mcp-test-outside"
    root_probe = project.parent / "outside-secret.txt"
    prof = sandbox.mcp_profile(str(project), [str(SERVER.parent), sys.prefix, sys.base_prefix])
    prefix = [sandbox.SANDBOX_EXEC, "-p", prof]
    out = rpc(project, [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                         "params": {"name": "read_file", "arguments": {"path": "README.md"}}}], prefix)
    assert out[0]["result"]["content"][0]["text"].strip() == "PROJECT-FILE-CONTENT"
    # даже в обход проверок самого сервера процесс под профилем не читает, не пишет и не ходит в сеть
    code = ("import sys, urllib.request\n"
            "for n, f in (('read_outside_root', lambda: open(sys.argv[1]).read()),"
            " ('write', lambda: open(sys.argv[2], 'w').write('x')),"
            " ('network', lambda: urllib.request.urlopen('http://127.0.0.1:9', timeout=3))):\n"
            "    try:\n        f(); print(n, 'OK')\n    except Exception as e:\n        print(n, 'DENIED')\n")
    home_probe.write_text("HOME-OUTSIDE-MARKER", encoding="utf-8")
    try:
        res = subprocess.run([*prefix, sys.executable, "-I", "-S", "-c", code, str(home_probe),
                              str(project / "w.txt")], capture_output=True, text=True, timeout=60)
    finally:
        home_probe.unlink(missing_ok=True)
    lines = dict(line.split() for line in res.stdout.strip().splitlines())
    assert lines == {"read_outside_root": "DENIED", "write": "DENIED", "network": "DENIED"}, (
        res.stdout + res.stderr)
    assert root_probe.exists() and not (project / "w.txt").exists()
