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


# ------------------------------------------------------------------ круг 5: N6
@pytest.fixture
def secret_tree(tmp_path: Path) -> Path:
    root = tmp_path / "tree"
    for directory in ("secrets", "Secrets", ".env.private", "credentials", "Credentials", "ok", ".GIT"):
        (root / directory).mkdir(parents=True, exist_ok=True)
        if directory != "ok":
            (root / directory / "data.txt").write_text("SYNTHETIC_PRIVATE_MARKER", encoding="utf-8")
    (root / ".GIT" / "config").write_text("SYNTHETIC_GIT_CONFIG", encoding="utf-8")
    (root / "ok" / "visible.txt").write_text("VISIBLE-MARKER", encoding="utf-8")
    (root / "ok" / ".Env").write_text("SYNTHETIC_PRIVATE_MARKER", encoding="utf-8")
    (root / "ok" / "Server.PEM").write_text("SYNTHETIC_PRIVATE_MARKER", encoding="utf-8")
    return root


def test_search_never_returns_files_from_forbidden_directories(secret_tree: Path) -> None:
    for pattern in ("SYNTHETIC_PRIVATE_MARKER", ".*", "SYNTHETIC"):
        for path in (".", "ok"):
            text, err = call_tool(Reader(str(secret_tree)), "search", {"pattern": pattern, "path": path})
            assert "SYNTHETIC" not in text, (pattern, path, text)
    text, _ = call_tool(Reader(str(secret_tree)), "search", {"pattern": "VISIBLE"})
    assert "ok/visible.txt:1: VISIBLE-MARKER" in text  # обычное по-прежнему находится


@pytest.mark.parametrize("path", [".GIT/config", ".Git/config", ".gIt", "secrets/data.txt", "Secrets/data.txt",
                                   ".env.private/data.txt", "credentials/data.txt", "Credentials/data.txt",
                                   "ok/.Env", "ok/Server.PEM", ".GIT"])
def test_case_variants_are_refused_by_every_tool(secret_tree: Path, path: str) -> None:
    reader = Reader(str(secret_tree))
    for tool, args in (("read_file", {"path": path}), ("list_files", {"path": path}),
                       ("search", {"pattern": "SYNTHETIC", "path": path})):
        text, err = call_tool(reader, tool, args)
        assert err and text.startswith("ОТКАЗ") and "SYNTHETIC" not in text, (tool, path, text)


def test_listing_hides_forbidden_entries_in_any_case(secret_tree: Path) -> None:
    text, err = call_tool(Reader(str(secret_tree)), "list_files", {"path": "."})
    assert not err and "ok/" in text
    for hidden in ("secrets", "Secrets", ".env.private", "credentials", "Credentials", ".GIT"):
        assert hidden not in text, hidden
    inner, _ = call_tool(Reader(str(secret_tree)), "list_files", {"path": "ok"})
    assert "visible.txt" in inner and ".Env" not in inner and "Server.PEM" not in inner


# ------------------------------------------------------------------ круг 5: N7
GITENV = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
          "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def linked_worktree_under_home() -> tuple[Path, Path]:
    """Настоящий связанный worktree в .worktrees внутри ДОМАШНЕГО каталога (там действует запрет чтения)."""
    import tempfile

    base = Path(tempfile.mkdtemp(prefix=".wms-mcp-n7-", dir=str(Path.home())))
    repo = base / "repo"
    repo.mkdir()
    for cmd in (["git", "init", "-q", "-b", "etalon", "."],):
        subprocess.run(cmd, cwd=repo, env=GITENV, check=True, capture_output=True)
    (repo / "README.md").write_text("HISTORY-FILE-V1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, env=GITENV, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "first commit"], cwd=repo, env=GITENV, check=True, capture_output=True)
    (repo / "README.md").write_text("HISTORY-FILE-V2\n", encoding="utf-8")
    subprocess.run(["git", "commit", "-qam", "second commit"], cwd=repo, env=GITENV, check=True, capture_output=True)
    worktree = repo / ".worktrees" / "support-agent-etalon"
    subprocess.run(["git", "worktree", "add", "-q", "--detach", str(worktree), "HEAD"], cwd=repo, env=GITENV,
                   check=True, capture_output=True)
    return base, worktree


@pytest.mark.skipif(not sandbox.available(), reason="needs macOS sandbox-exec")
def test_git_log_and_show_work_in_a_real_linked_worktree_under_the_profile() -> None:
    import shutil

    from support_agent.llm import LlmRouter

    base, worktree = linked_worktree_under_home()
    try:
        assert (worktree / ".git").is_file()  # файл-указатель: метаданные вне корня
        dirs = LlmRouter.git_metadata_dirs(str(worktree))
        real_base = os.path.realpath(base)
        assert len(dirs) == 2 and dirs[0].startswith(f"{real_base}/repo/.git/worktrees/")
        assert dirs[1] == f"{real_base}/repo/.git"
        prof = sandbox.mcp_profile(str(worktree), [str(SERVER.parent), sys.prefix, sys.base_prefix, *dirs])
        prefix = [sandbox.SANDBOX_EXEC, "-p", prof]

        def call(name: str, **arguments: object) -> dict:
            out = rpc(worktree, [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                  "params": {"name": name, "arguments": arguments}}], prefix)
            return out[0]["result"]

        log = call("git_log", max_count=5)
        assert not log["isError"] and "second commit" in log["content"][0]["text"]
        assert "first commit" in log["content"][0]["text"]
        old = call("git_show", rev="HEAD~1", path="README.md")
        assert not old["isError"] and old["content"][0]["text"].strip() == "HISTORY-FILE-V1"
        assert "second commit" in call("git_show", rev="HEAD")["content"][0]["text"]
        assert call("read_file", path="README.md")["content"][0]["text"].strip() == "HISTORY-FILE-V2"
        # прямое чтение метаданных моделью остаётся запрещённым (проверка в Python)
        for tool, args in (("read_file", {"path": ".git"}), ("read_file", {"path": ".GIT"}),
                           ("search", {"pattern": "gitdir"}), ("list_files", {"path": ".git"}),
                           ("read_file", {"path": f"{dirs[0]}/HEAD"}), ("read_file", {"path": "../../.git/HEAD"})):
            res = call(tool, **args)
            body = res["content"][0]["text"]
            assert ("gitdir:" not in body) and (res["isError"] or tool == "search"), (tool, args, body)
        # и процесс под профилем не читает остальной домашний каталог даже в обход сервера
        probe = subprocess.run([*prefix, sys.executable, "-I", "-S", "-c",
                                f"open({str(base / 'repo' / 'README.md')!r}).read()"],
                               capture_output=True, text=True, timeout=60)
        assert probe.returncode != 0 and "Operation not permitted" in probe.stderr  # вне корня закрыто
    finally:
        shutil.rmtree(base, ignore_errors=True)
    assert not base.exists()


def test_git_metadata_dirs_for_plain_repo_and_non_repo(tmp_path: Path) -> None:
    from support_agent.llm import LlmRouter

    assert LlmRouter.git_metadata_dirs(str(tmp_path)) == []
    subprocess.run(["git", "init", "-q", "."], cwd=tmp_path, env=GITENV, check=True, capture_output=True)
    dirs = LlmRouter.git_metadata_dirs(str(tmp_path))
    assert dirs == [os.path.realpath(tmp_path / ".git")]


def test_profile_for_codex_analyst_includes_verified_git_dirs(tmp_path: Path) -> None:
    from .test_llm_router import ExecScript, router

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "etalon", "."], cwd=repo, env=GITENV, check=True, capture_output=True)
    (repo / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, env=GITENV, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "c"], cwd=repo, env=GITENV, check=True, capture_output=True)
    wt = repo / ".worktrees" / "wt"
    subprocess.run(["git", "worktree", "add", "-q", "--detach", str(wt), "HEAD"], cwd=repo, env=GITENV,
                   check=True, capture_output=True)
    script = ExecScript()
    llm, store = router(tmp_path, script)
    import time as _t

    store.kv_set("cooldown:claude", _t.time() + 999)
    llm.ask("analyst", "x", mode="readonly", cwd=str(wt))
    argv = script.full[-1]
    args = json.loads(next(a for a in argv if a.startswith("mcp_servers.wms.args=")).split("=", 1)[1])
    prof = args[1]
    assert f'(subpath "{os.path.realpath(repo / ".git")}")' in prof
    assert f'(subpath "{os.path.realpath(repo / ".git" / "worktrees" / "wt")}")' in prof
