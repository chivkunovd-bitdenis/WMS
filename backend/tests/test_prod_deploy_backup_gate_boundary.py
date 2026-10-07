"""WMS-652: backup fixture must exercise the new server-CI shell boundary."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import inspect
import json
import subprocess
from pathlib import Path

import pytest

SOURCE = Path(__file__).with_name("test_prod_deploy_backup.py")
SHA = "a" * 40


def test_all_seven_backup_variants_and_original_assertions_are_preserved() -> None:
    tree = ast.parse(SOURCE.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "test_deploy_requires_verified_backup_before_migration")
    parameters = next(node for node in function.decorator_list if isinstance(node, ast.Call))
    assert ast.literal_eval(parameters.args[1]) == [
        "", "dump", "archive", "listing", "empty", "network", "retry",
    ]
    # Python 3.14 omits empty fields by default; the legacy CI format includes them.
    dump_options = (
        {"show_empty": True} if "show_empty" in inspect.signature(ast.dump).parameters else {}
    )
    assertions = [
        ast.dump(node, include_attributes=False, **dump_options)
        for node in ast.walk(function)
        if isinstance(node, ast.Assert)
    ]
    assert len(assertions) == 23
    assert hashlib.sha256(json.dumps(assertions, ensure_ascii=False).encode()).hexdigest() == (
        "0632023b3ebea0de566823f112e6a1eeca5b5222a3cfd538d5624da1d4d81408"
    )


@pytest.mark.parametrize("gate_state", [
    "accepted", "failed", "unavailable", "wrong-sha", "missing",
])
def test_backup_fixture_server_ci_boundary_precedes_every_docker_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gate_state: str,
) -> None:
    spec = importlib.util.spec_from_file_location("backup_boundary_harness", SOURCE)
    assert spec is not None and spec.loader is not None
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    monkeypatch.setenv("WMS_TEST_SERVER_CI_RESULT", gate_state)
    monkeypatch.setenv("WMS_TEST_SERVER_CI_SHA", "b" * 40 if gate_state == "wrong-sha" else SHA)
    captured: list[subprocess.CompletedProcess[str]] = []
    real_run = subprocess.run

    def observe_run(*args, **kwargs):
        command = args[0]
        if command[0] == "bash" and command[1].endswith("/prod-update.sh"):
            if gate_state == "missing":
                gate = (Path(kwargs["env"]["WMS_REPO_DIR"])
                        / "scripts/ci/verify_server_process_ci.py")
                gate.unlink(missing_ok=True)
            outcome = real_run(*args, **kwargs)
            captured.append(outcome)
            return outcome
        return real_run(*args, **kwargs)

    monkeypatch.setattr(harness.subprocess, "run", observe_run)
    old_assertion_error = None
    try:
        harness.test_deploy_requires_verified_backup_before_migration(tmp_path, "")
    except (AssertionError, StopIteration) as error:
        # A gate rejection deliberately prevents the old backup assertions from
        # finding migration/backup calls. Inspect the actual shell result below.
        old_assertion_error = error
    assert len(captured) == 1
    outcome = captured[0]
    calls = [json.loads(line) for line in (tmp_path / "commands.jsonl").read_text().splitlines()]
    expected_gate = ["server-ci", "--sha", SHA]
    docker = [call for call in calls if call[0] == "docker"]
    gates = [call for call in calls if call[0] == "server-ci"]
    if gate_state == "accepted":
        assert outcome.returncode == 0, outcome.stderr
        assert old_assertion_error is None
        assert gates == [expected_gate]
        assert docker
        gate_index = calls.index(expected_gate)
        assert all(gate_index < index for index, call in enumerate(calls) if call[0] == "docker")
        assert (tmp_path / "private-backups").is_dir()
    else:
        assert outcome.returncode != 0
        assert docker == []
        assert not (tmp_path / "private-backups").exists()
        assert not (tmp_path / "api-stopped").exists()
        if gate_state == "missing":
            assert gates == []
            assert "verify_server_process_ci.py" in outcome.stderr
            assert "No such file" in outcome.stderr
        else:
            assert gates == [expected_gate]
            assert "synthetic server CI refused" in outcome.stderr
            assert gate_state in outcome.stderr
