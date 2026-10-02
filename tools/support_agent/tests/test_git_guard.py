"""N1: подмена .git недоверенным кодом не должна приводить к исполнению чужих настроек Git."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from support_agent import sandbox
from support_agent.hotfix import HotfixRunner, StepFailed

from .conftest import FakeLlm, FakeTelegram, FakeTranscriber, FakeTrello, FakeWms, make_config

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}


def sh(*argv: str, cwd: Path) -> str:
    return subprocess.run(argv, cwd=cwd, env=GIT_ENV, capture_output=True, text=True, check=True).stdout


def build(tmp_path: Path, env: Any = None) -> tuple[HotfixRunner, Path, Path]:
    from support_agent.pipeline import InlinePool, Pipeline
    from support_agent.store import Store

    repo = tmp_path / "repo"
    repo.mkdir()
    sh("git", "init", "-q", "-b", "etalon", ".", cwd=repo)
    (repo / "a.txt").write_text("1", encoding="utf-8")
    sh("git", "add", "-A", cwd=repo)
    sh("git", "commit", "-qm", "init", cwd=repo)
    wt = repo / ".worktrees" / "wms700-hotfix"
    sh("git", "worktree", "add", "-q", "-b", "hotfix/x", str(wt), "HEAD", cwd=repo)
    cfg = make_config(tmp_path, repo=str(repo))
    cfg.repo = str(repo)
    store = Store(cfg.db_path)
    pipe = Pipeline(cfg, store, FakeTelegram(), FakeLlm(), FakeTrello(), FakeWms(),  # type: ignore[arg-type]
                    FakeTranscriber(), pool=InlinePool())
    return HotfixRunner(pipe), repo, wt


def evil_config(marker: Path, script: Path) -> str:
    script.write_text(f"#!/bin/sh\necho owned > {marker}\nprintf '\\0'\n", encoding="utf-8")
    script.chmod(0o755)
    return f"[core]\n\trepositoryformatversion = 1\n\tfsmonitor = {script}\n[extensions]\n\tworktreeConfig = false\n"


def replace_git_with_evil_dir(wt: Path, marker: Path, script: Path) -> None:
    (wt / ".git").unlink()
    evil = wt / ".git"
    evil.mkdir()
    (evil / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (evil / "config").write_text(evil_config(marker, script), encoding="utf-8")
    (evil / "objects").mkdir()
    (evil / "refs").mkdir()


def test_untouched_worktree_passes_guard_and_hardened_git_works(tmp_path: Path) -> None:
    runner, repo, wt = build(tmp_path)
    runner.guard_gitdir(wt)
    assert runner.git("status", "--porcelain", cwd=wt) == ""
    (wt / "new.txt").write_text("x", encoding="utf-8")
    assert "new.txt" in runner.git("status", "--porcelain", cwd=wt)


def test_replaced_git_directory_is_refused_before_any_git_runs(tmp_path: Path) -> None:
    runner, repo, wt = build(tmp_path)
    marker, script = tmp_path / "MARKER-fsmonitor-ran", tmp_path / "evil.sh"
    replace_git_with_evil_dir(wt, marker, script)
    # сценарий Astra: обычный `git status` с правами диспетчера исполнил бы fsmonitor
    plain = subprocess.run(["git", "status", "--porcelain"], cwd=wt, env=GIT_ENV, capture_output=True)
    baseline_fired = marker.exists()
    marker.unlink(missing_ok=True)
    h = {"path": str(wt), "number": 700, "dev": {"summary": "x"}}
    with pytest.raises(StepFailed, match="подменены"):
        runner.commit_dev(1, h)
    with pytest.raises(StepFailed, match="подменены"):
        runner.verify_worktree({**h, "number": 700})
    assert not marker.exists(), "диспетчер исполнил чужой fsmonitor"
    del plain, baseline_fired  # на разных версиях git базовый запуск может не срабатывать; важно, что наш путь не исполняет


def test_git_file_pointing_to_foreign_gitdir_is_refused(tmp_path: Path) -> None:
    runner, repo, wt = build(tmp_path)
    marker, script = tmp_path / "MARKER-2", tmp_path / "evil2.sh"
    foreign = tmp_path / "foreign-gitdir"
    shutil.copytree(repo / ".git", foreign)
    (foreign / "config").write_text((foreign / "config").read_text(encoding="utf-8")
                                    + evil_config(marker, script), encoding="utf-8")
    (wt / ".git").write_text(f"gitdir: {foreign}\n", encoding="utf-8")
    with pytest.raises(StepFailed, match="подменены"):
        runner.commit_dev(1, {"path": str(wt), "number": 700, "dev": {}})
    assert not marker.exists()


def test_symlinked_git_is_refused(tmp_path: Path) -> None:
    runner, repo, wt = build(tmp_path)
    real = tmp_path / "real-git-file"
    real.write_text((wt / ".git").read_text(encoding="utf-8"), encoding="utf-8")
    (wt / ".git").unlink()
    (wt / ".git").symlink_to(real)
    with pytest.raises(StepFailed, match="не файл-ссылка"):
        runner.guard_gitdir(wt)


def test_hardened_git_ignores_fsmonitor_and_hooks_even_without_guard(tmp_path: Path) -> None:
    """Второй слой: даже если проверка пропущена, fsmonitor и хуки из конфига не исполняются."""
    runner, repo, wt = build(tmp_path)
    marker, script = tmp_path / "MARKER-3", tmp_path / "evil3.sh"
    admin = runner.trusted_admin_dir(wt)
    (admin / "config.worktree").write_text(evil_config(marker, script), encoding="utf-8")
    sh("git", "config", "extensions.worktreeConfig", "true", cwd=repo)
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(f"#!/bin/sh\necho owned > {tmp_path / 'MARKER-hook'}\n", encoding="utf-8")
    hook.chmod(0o755)
    (wt / "f.txt").write_text("x", encoding="utf-8")
    runner.git("status", "--porcelain", cwd=wt)
    runner.git("add", "-A", cwd=wt)
    runner.git("-c", "user.name=a", "-c", "user.email=a@a", "commit", "--no-verify", "-m", "WMS-700: x", cwd=wt)
    assert not marker.exists() and not (tmp_path / "MARKER-hook").exists()


@pytest.mark.skipif(not sandbox.available(), reason="needs macOS sandbox-exec")
def test_sandboxed_code_cannot_replace_or_modify_dot_git(tmp_path: Path) -> None:
    runner, repo, wt = build(tmp_path)
    probe = (
        "import os, pathlib, shutil\n"
        "def t(n, f):\n"
        "    try:\n        f(); print(n, 'OK')\n    except Exception as e:\n        print(n, 'DENIED', type(e).__name__)\n"
        "t('remove_dot_git', lambda: os.remove('.git'))\n"
        "t('overwrite_dot_git', lambda: pathlib.Path('.git').write_text('gitdir: /tmp/evil'))\n"
        "t('write_inside', lambda: pathlib.Path('ok.txt').write_text('x'))\n"
    )
    with sandbox.temp_dir() as tmp:
        cmd = sandbox.check_argv([sys.executable, "-c", probe], str(wt), tmp, str(tmp_path / "home"), [])
        res = subprocess.run(cmd, cwd=wt, capture_output=True, text=True, timeout=60)
    lines = dict(line.split()[:2] for line in res.stdout.strip().splitlines())
    assert lines == {"remove_dot_git": "DENIED", "overwrite_dot_git": "DENIED", "write_inside": "OK"}, (
        res.stdout + res.stderr)
    runner.guard_gitdir(wt)  # метаданные остались нетронутыми


def test_foreign_commits_between_deployed_and_merge_are_detected_with_real_git(tmp_path: Path) -> None:
    runner, repo, wt = build(tmp_path)
    base = sh("git", "rev-parse", "HEAD", cwd=repo).strip()
    sh("git", "checkout", "-q", "-b", "hotfix/y", cwd=repo)
    (repo / "fix.txt").write_text("fix", encoding="utf-8")
    sh("git", "add", "-A", cwd=repo)
    sh("git", "commit", "-qm", "WMS-700: fix", cwd=repo)
    sh("git", "checkout", "-q", "etalon", cwd=repo)
    sh("git", "merge", "--no-ff", "-q", "-m", "Merge hotfix", "hotfix/y", cwd=repo)
    clean_merge = sh("git", "rev-parse", "HEAD", cwd=repo).strip()
    assert runner.foreign_commits(base, clean_merge) == []  # только хотфикс и его слияние
    # чужой коммит попал в etalon до слияния хотфикса
    sh("git", "reset", "-q", "--hard", base, cwd=repo)
    (repo / "other.txt").write_text("o", encoding="utf-8")
    sh("git", "add", "-A", cwd=repo)
    sh("git", "commit", "-qm", "foreign", cwd=repo)
    foreign = sh("git", "rev-parse", "HEAD", cwd=repo).strip()
    sh("git", "merge", "--no-ff", "-q", "-m", "Merge hotfix 2", "hotfix/y", cwd=repo)
    merge = sh("git", "rev-parse", "HEAD", cwd=repo).strip()
    assert runner.foreign_commits(base, merge) == [foreign]
