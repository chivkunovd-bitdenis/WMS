"""Exercise frozen tests against a temporary shell copy that ignores CI refusal."""
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import traceback
from pathlib import Path

import pytest

root = Path(__file__).resolve().parents[4]
source = root / "scripts/deploy/prod-update.sh"
original = source.read_bytes()
line = b'python3 scripts/ci/verify_server_process_ci.py --sha "$DEPLOY_SHA"'
assert original.count(line) == 1
contract = root / "backend/tests/test_prod_deploy_backup_gate_boundary.py"
spec = importlib.util.spec_from_file_location("frozen_boundary_contract", contract)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
results = []
real_run = subprocess.run
with tempfile.TemporaryDirectory(prefix="wms652-gate-negative-") as folder:
    base = Path(folder)
    mutant = base / "prod-update.sh"
    mutant.write_bytes(original.replace(line, line + b" || true"))
    for state in ["accepted", "failed", "unavailable", "wrong-sha"]:
        case = base / state
        case.mkdir()
        patch = pytest.MonkeyPatch()

        def redirected_run(*args, **kwargs):
            command = args[0]
            if command == ["bash", str(source)]:
                args = (["bash", str(mutant)], *args[1:])
            return real_run(*args, **kwargs)

        patch.setattr(subprocess, "run", redirected_run)
        try:
            module.test_backup_fixture_server_ci_boundary_precedes_every_docker_action(
                case, patch, state,
            )
            assert state == "accepted", "A CI refusal was silently accepted by the contract"
            results.append({"state": state, "result": "PASS positive control"})
        except AssertionError as error:
            assert state != "accepted", "The positive control must pass"
            failure = traceback.extract_tb(error.__traceback__)[-1]
            assert failure.name == "test_backup_fixture_server_ci_boundary_precedes_every_docker_action"
            assert failure.line == "assert outcome.returncode != 0"
            calls = [json.loads(v) for v in (case / "commands.jsonl").read_text().splitlines()]
            assert any(v[0] == "docker" for v in calls)
            assert [v for v in calls if v[0] == "server-ci"] == [["server-ci", "--sha", "a" * 40]]
            results.append({"state": state, "result": "targeted RED", "assertion": failure.line,
                            "docker_calls_when_mutant_ignores_refusal": sum(v[0] == "docker" for v in calls)})
        finally:
            patch.undo()
assert source.read_bytes() == original
print(json.dumps({"mutation": "temporary shell copy ignores server CI refusal with || true",
                  "tracked_product_sha256_unchanged": hashlib.sha256(original).hexdigest(),
                  "frozen_contract_sha256": hashlib.sha256(contract.read_bytes()).hexdigest(),
                  "cases": results}, ensure_ascii=False, indent=2))
