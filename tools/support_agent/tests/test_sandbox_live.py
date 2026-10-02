"""F2: граница ОС проверяется настоящим sandbox-exec (без сетевых вызовов наружу, секретов нет)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from support_agent import sandbox

pytestmark = pytest.mark.skipif(not sandbox.available(), reason="needs macOS sandbox-exec")

PROBE = """
import pathlib, socket, sys
def t(name, f):
    try:
        print(name, "OK", f())
    except Exception as exc:
        print(name, "DENIED", type(exc).__name__)
t("write_outside", lambda: pathlib.Path(sys.argv[1]).write_text("x"))
t("read_secret", lambda: pathlib.Path(sys.argv[2]).read_text())
t("network", lambda: socket.create_connection(("127.0.0.1", int(sys.argv[3])), timeout=3).close())
t("write_inside", lambda: pathlib.Path("inside.txt").write_text("x"))
"""


def run_in_sandbox(tmp_path: Path, argv: list[str], worktree: Path) -> subprocess.CompletedProcess[str]:
    secret_dir = tmp_path / "fake-home-secrets"
    with sandbox.temp_dir() as tmp:
        cmd = sandbox.check_argv(argv, str(worktree), tmp, str(tmp_path / "home"), [str(secret_dir)])
        return subprocess.run(cmd, cwd=worktree, capture_output=True, text=True, timeout=120)


def test_probe_cannot_write_outside_read_secrets_or_use_network(tmp_path: Path) -> None:
    worktree = tmp_path / "wt"
    worktree.mkdir()
    secret_dir = tmp_path / "fake-home-secrets"
    secret_dir.mkdir()
    (secret_dir / "config.json").write_text("FAKE-SECRET-MARKER", encoding="utf-8")
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    outside = tmp_path / "outside-marker.txt"
    res = run_in_sandbox(
        tmp_path,
        [sys.executable, "-c", PROBE, str(outside), str(secret_dir / "config.json"), str(port)],
        worktree,
    )
    server.close()
    lines = dict(line.split()[:2] for line in res.stdout.strip().splitlines())
    assert lines == {"write_outside": "DENIED", "read_secret": "DENIED", "network": "DENIED",
                     "write_inside": "OK"}, res.stdout + res.stderr
    assert not outside.exists() and "FAKE-SECRET-MARKER" not in res.stdout
    # без песочницы то же самое работает (проверка, что запреты дала именно она)
    open_run = subprocess.run(
        [sys.executable, "-c", PROBE, str(outside), str(secret_dir / "config.json"), str(port)],
        cwd=worktree, capture_output=True, text=True, timeout=60)
    assert "write_outside OK" in open_run.stdout and "read_secret OK" in open_run.stdout


def test_small_pytest_passes_inside_sandbox(tmp_path: Path) -> None:
    pytest.importorskip("pytest")
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / "test_small.py").write_text(
        "import pathlib, tempfile\n"
        "def test_small():\n"
        "    p = pathlib.Path(tempfile.mkdtemp()) / 'x'\n"
        "    p.write_text('1')\n"
        "    assert p.read_text() == '1'\n",
        encoding="utf-8",
    )
    res = run_in_sandbox(tmp_path, [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                    "test_small.py"], worktree)
    assert res.returncode == 0 and "1 passed" in res.stdout, res.stdout + res.stderr


def test_environment_is_scrubbed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-must-not-pass")
    worktree = tmp_path / "wt"
    worktree.mkdir()
    res = run_in_sandbox(tmp_path, ["/usr/bin/env"], worktree)
    assert "sk-must-not-pass" not in res.stdout and "OPENAI" not in res.stdout
    assert os.path.realpath(str(tmp_path)) not in res.stdout.split("HOME=")[1].split("\n")[0]
