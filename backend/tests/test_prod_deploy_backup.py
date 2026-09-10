"""WMS-338/377: migration ordering, private backup and obsolete listener scope."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("backup_error", ["", "dump", "archive", "listing", "empty"])
def test_deploy_requires_verified_backup_before_migration(
    tmp_path: Path, backup_error: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "docker-compose.wms-host-8088.yml").touch()
    commands = tmp_path / "commands.jsonl"
    binaries = tmp_path / "bin"
    binaries.mkdir()
    stub = binaries / "stub"
    stub.write_text(f"#!{sys.executable}\n" + '''
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["TEST_COMMANDS"], "a") as out:
    out.write(json.dumps([name, *args]) + "\\n")
error = os.environ["TEST_BACKUP_ERROR"]
if name == "git" and args[:1] == ["rev-parse"]:
    print("a" * 40)
elif name == "docker":
    if any("pg_dump" in arg for arg in args):
        assert sys.stdin.read() == ""
        print("synthetic backup")
        sys.exit(1 if error == "dump" else 0)
    if "pg_restore" in args:
        assert sys.stdin.read().strip() == "synthetic backup"
        sys.exit(1 if error == "archive" else 0)
    if args[-3:] == ["ps", "-q", "db"]:
        print("synthetic-db")
    elif args[:1] == ["inspect"]:
        print("synthetic-project")
    elif args[:2] == ["ps", "-q"]:
        if error == "listing": sys.exit(19)
        if error == "empty": sys.exit(0)
        print("synthetic-legacy-seller")
''')
    stub.chmod(0o755)
    for name in ("git", "docker", "curl"):
        (binaries / name).symlink_to(stub)
    script = Path(__file__).resolve().parents[2] / "scripts/deploy/prod-update.sh"
    backup_dir = tmp_path / "private-backups"
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True,
        env={
            **os.environ, "PATH": f"{binaries}:{os.environ['PATH']}",
            "WMS_REPO_DIR": str(repo), "WMS_BACKUP_DIR": str(backup_dir),
            "WMS_DEPLOY_GUARD_ONLY": "0", "TEST_COMMANDS": str(commands),
            "TEST_BACKUP_ERROR": backup_error,
        },
        check=False,
    )
    calls = [json.loads(line) for line in commands.read_text().splitlines()]
    stop = next(i for i, call in enumerate(calls) if call[-4:] == [
        "stop", "api", "celery_worker", "celery_beat",
    ])
    dump = next(i for i, call in enumerate(calls) if any("pg_dump" in v for v in call))
    assert stop < dump
    migrations = [i for i, call in enumerate(calls) if call[-3:] == [
        "run", "--rm", "migrations",
    ]]
    if backup_error in ("dump", "archive"):
        assert result.returncode != 0
        assert not migrations
        assert not any(call[:2] == ["docker", "stop"] for call in calls)
        return
    if backup_error == "listing":
        assert result.returncode == 19
        assert migrations
        assert not any(call[:2] == ["docker", "stop"] for call in calls)
        return
    assert result.returncode == 0, result.stderr
    verified = next(i for i, call in enumerate(calls) if "pg_restore" in call)
    assert dump < verified < migrations[0]
    route_check = next(i for i, call in enumerate(calls) if call[0] == "curl")
    assert migrations[0] < route_check
    if backup_error == "empty":
        assert not any(call[:2] == ["docker", "stop"] for call in calls)
    else:
        legacy_stop = calls.index(["docker", "stop", "synthetic-legacy-seller"])
        assert route_check < legacy_stop
    assert any("label=com.docker.compose.project=synthetic-project" in call for call in calls)
    assert any("label=com.docker.compose.service=web_seller" in call for call in calls)
    assert backup_dir.stat().st_mode & 0o777 == 0o700
    archive = next(backup_dir.glob("*.dump"))
    assert archive.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("script_error", [False, True])
def test_workflow_bootstrap_checks_git_and_separates_stdin(
    tmp_path: Path, script_error: bool,
) -> None:
    workflow = Path(__file__).resolve().parents[2] / ".github/workflows/deploy.yml"
    lines = workflow.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if 'deploy_script="$(git show' in line)
    bootstrap = "\n".join(line.strip() for line in lines[start:start + 2])
    git = tmp_path / "git"
    git.write_text(
        "#!/bin/sh\nexit 17\n" if script_error else
        "#!/bin/sh\ncat <<'SCRIPT'\ncat >/dev/null\necho bootstrap-finished\nSCRIPT\n"
    )
    git.chmod(0o755)
    result = subprocess.run(
        ["bash", "-e", "-c", bootstrap], input="must not become script input\n",
        capture_output=True, text=True,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}, check=False,
    )
    assert result.returncode == (17 if script_error else 0)
    assert result.stdout == ("" if script_error else "bootstrap-finished\n")
