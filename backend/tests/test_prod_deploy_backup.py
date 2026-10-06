"""WMS-338/377: migration ordering, private backup and obsolete listener scope."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("backup_error", ["", "dump", "archive", "listing", "empty", "network",
                                        "retry"])
def test_deploy_requires_verified_backup_before_migration(
    tmp_path: Path, backup_error: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = Path(__file__).resolve().parents[2]
    for relative in ("docker-compose.wms-host-8088.yml", "deploy/Caddyfile.http",
                     "scripts/deploy/verify-wms-host-network.py",
                     "scripts/ci/verify_server_process_ci.py", "scripts/ci/verify_ci.py"):
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
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
stopped = Path(os.environ["TEST_STOPPED_API"])
if name == "git" and args[:1] == ["rev-parse"]:
    print("a" * 40)
elif name == "docker":
    if not Path(os.environ["TEST_GATE_PASSED"]).exists():
        raise RuntimeError("Docker was reached before the server process gate")
    if "stop" in args and "api" in args:
        stopped.touch()
    if args[:1] == ["inspect"] and "State.Running" in args[-1]:
        print(("false" if args[1] == "synthetic-api" and stopped.exists() else "true")
              + "|wms-network")
        sys.exit(0)
    if args[:3] == ["network", "ls", "-q"]:
        print("wms-network")
        sys.exit(0)
    if args[:2] == ["network", "inspect"]:
        edge = args[2] == "edge-network"
        number = 18 if edge else (22 if error == "network" else 21)
        print(json.dumps([{"Id": args[2], "Name": args[2], "IPAM": {"Config": [
            {"Subnet": f"172.{number}.0.0/16", "Gateway": f"172.{number}.0.1"}
        ]}}]))
        sys.exit(0)
    if args[:1] == ["inspect"] and "NetworkSettings.Networks" in args[-1]:
        edge = args[1] == "synthetic-edge"
        network = "edge-network" if edge else "wms-network"
        number = 18 if edge else 21
        off = args[1] == "synthetic-api" and stopped.exists()
        print(json.dumps({network: {"NetworkID": network,
                                  "Gateway": "" if off else f"172.{number}.0.1",
                                  "IPAddress": "" if off else f"172.{number}.0.6",
                                  "IPPrefixLen": 0 if off else 16}}))
        sys.exit(0)
    if args[:2] == ["ps", "-q"] or args[:3] == ["ps", "-a", "-q"]:
        if "publish=443" in args:
            print("synthetic-edge")
            sys.exit(0)
        if any(v.endswith("service=api") or v.endswith("service=web") for v in args):
            if args[-1].endswith("service=api"):
                if not stopped.exists() or "-a" in args: print("synthetic-api")
            else: print("synthetic-web")
            sys.exit(0)
    if any("pg_dump" in arg for arg in args):
        assert sys.stdin.read() == ""
        print("synthetic backup")
        sys.exit(1 if error == "dump" else 0)
    if "pg_restore" in args:
        assert sys.stdin.read().strip() == "synthetic backup"
        sys.exit(1 if error == "archive" else 0)
    if args[-3:] == ["ps", "-q", "db"] or args[-4:] == ["ps", "-a", "-q", "db"]:
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
    # Keep the server gate real while replacing only its public GitHub HTTP boundary.
    # A Docker command fails if the real verifier did not first complete successfully.
    site = tmp_path / "site"
    site.mkdir()
    site.joinpath("sitecustomize.py").write_text('''
import io, json, os
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import urllib.request

class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *_): self.close()

def response(path):
    parsed = urlparse(path)
    route, query = parsed.path.lstrip('/'), parse_qs(parsed.query)
    sha = query.get('head_sha', ['a' * 40])[0]
    root = 'repos/chivkunovd-bitdenis/WMS'
    run = {'id': 654, 'workflow_id': 987, 'path': '.github/workflows/ci.yml@refs/heads/etalon',
           'repository': {'full_name': 'chivkunovd-bitdenis/WMS'},
           'head_repository': {'full_name': 'chivkunovd-bitdenis/WMS'}, 'head_sha': sha,
           'head_branch': 'etalon', 'event': 'push', 'run_number': 1, 'run_attempt': 1,
           'status': 'completed', 'conclusion': 'success', 'check_suite_id': 321}
    if route == root + '/actions/workflows/ci.yml':
        return {'id': 987, 'path': '.github/workflows/ci.yml', 'state': 'active'}
    if route == root + '/actions/workflows/987/runs':
        return {'total_count': 1, 'workflow_runs': [run]}
    if route == root + '/check-suites/321':
        return {'app': {'id': 15368, 'slug': 'github-actions'}, 'head_sha': sha}
    if route == root + '/actions/runs/654/attempts/1/jobs':
        names = ['baseline', 'backlog', 'backend', 'frontend-build', 'охрана',
                 'print-regressions', 'printer-windows', 'process-proof']
        jobs = [{'id': i, 'name': name, 'head_sha': sha, 'run_id': 654,
                 'status': 'completed', 'conclusion': 'success'} for i, name in enumerate(names)]
        return {'total_count': len(jobs), 'jobs': jobs}
    if route == root + '/actions/runs/654/artifacts':
        return {'total_count': 1, 'artifacts': [{'id': 777, 'name': f'process-proof-{sha}-654-1',
            'expired': False, 'size_in_bytes': 1, 'workflow_run': {'id': 654, 'head_sha': sha}}]}
    raise AssertionError('unexpected GitHub gate request: ' + route)

def fake_urlopen(request, timeout):
    Path(os.environ['TEST_GATE_PASSED']).touch()
    with Path(os.environ['TEST_GATE_REQUESTS']).open('a') as output:
        output.write(request.full_url + '\\n')
    return Response(json.dumps(response(request.full_url)).encode())

urllib.request.urlopen = fake_urlopen
''')
    script = Path(__file__).resolve().parents[2] / "scripts/deploy/prod-update.sh"
    backup_dir = tmp_path / "private-backups"
    gate_requests = tmp_path / "gate-requests"
    environment = {
            **os.environ, "PATH": f"{binaries}:{os.environ['PATH']}",
            "PYTHONPATH": f"{site}:{os.environ.get('PYTHONPATH', '')}",
            "WMS_REPO_DIR": str(repo), "WMS_BACKUP_DIR": str(backup_dir),
            "WMS_DEPLOY_GUARD_ONLY": "0", "TEST_COMMANDS": str(commands),
            "TEST_BACKUP_ERROR": "dump" if backup_error == "retry" else backup_error,
            "TEST_STOPPED_API": str(tmp_path / "api-stopped"),
            "TEST_GATE_PASSED": str(tmp_path / "gate-passed"),
            "TEST_GATE_REQUESTS": str(gate_requests),
    }
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, env=environment,
        check=False,
    )
    if backup_error == "retry":
        assert result.returncode != 0
        assert "backup failed" in result.stderr
        assert (tmp_path / "api-stopped").exists()
        commands.write_text("")
        environment["TEST_BACKUP_ERROR"] = ""
        result = subprocess.run(
            ["bash", str(script)], capture_output=True, text=True, env=environment, check=False,
        )
    calls = [json.loads(line) for line in commands.read_text().splitlines()]
    assert (tmp_path / "gate-passed").exists(), "real server gate must complete before Docker"
    assert any("/actions/workflows/987/runs" in request
               for request in gate_requests.read_text().splitlines())
    if backup_error == "network":
        assert result.returncode != 0
        assert "subnet/gateway changed" in result.stderr
        assert not any("build" in call or "stop" in call or "migrations" in call for call in calls)
        assert not backup_dir.exists()
        return
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
