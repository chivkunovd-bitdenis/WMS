"""Read-only source preservation checks for the independent fixture review."""

import ast
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = "f6066d68bd198794602a6e8916612d0d3b32460f"
CONTRACT = "030d75c01549b32a67ed4af405fea984b5974025"
SOURCE = "d736a02427c916979b2117ebecc1ace10dc9cc07"
OLD = "backend/tests/test_prod_deploy_backup.py"
NEW = "backend/tests/test_prod_deploy_backup_gate_boundary.py"


def git(*args):
    return subprocess.check_output(["git", *args])


def blob(ref, path):
    return git("show", f"{ref}:{path}")


def contract_shape(data):
    tree = ast.parse(data)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == "test_deploy_requires_verified_backup_before_migration")
    decorator = next(n for n in node.decorator_list if isinstance(n, ast.Call))
    asserts = [ast.dump(n, include_attributes=False) for n in ast.walk(node)
               if isinstance(n, ast.Assert)]
    return {"parameters": ast.literal_eval(decorator.args[1]),
            "assertions": len(asserts),
            "assertions_sha256": hashlib.sha256(
                json.dumps(asserts, ensure_ascii=False).encode()).hexdigest()}


before = contract_shape(blob(BASE, OLD))
after = contract_shape(blob(SOURCE, OLD))
assert before == after
assert after["assertions"] == 23 and len(after["parameters"]) == 7
assert blob(CONTRACT, NEW) == blob(SOURCE, NEW) == Path(NEW).read_bytes()
paths = ["scripts/ci", "scripts/deploy", "backend/app", "frontend/src",
         ".github/workflows", "guards"]
assert git("diff", "--name-only", BASE, SOURCE, "--", *paths) == b""
assert git("diff", "--numstat", BASE, SOURCE, "--", OLD).decode().strip() == f"17\t0\t{OLD}"
report = ET.parse(Path(__file__).with_name("targeted.xml"))
cases = list(report.iter("testcase"))
assert len(cases) == 15
assert not any(list(case.iter("failure")) or list(case.iter("error"))
               or list(case.iter("skipped")) for case in cases)
print(json.dumps({
    "base": BASE, "test_first": CONTRACT, "reviewed_source": SOURCE,
    "old_contract_preserved": after,
    "frozen_new_contract_unchanged": True,
    "new_contract_sha256": hashlib.sha256(blob(SOURCE, NEW)).hexdigest(),
    "product_and_ci_and_policy_diff": [],
    "fixture_change": {"added_lines": 17, "deleted_lines": 0},
    "actual_junit": {"tests": len(cases), "failures": 0, "errors": 0,
                     "skips": 0, "cases": [case.attrib for case in cases]},
    "production_shell_sha256": hashlib.sha256(
        blob(SOURCE, "scripts/deploy/prod-update.sh")).hexdigest(),
    "real_server_verifier_sha256": hashlib.sha256(
        blob(SOURCE, "scripts/ci/verify_server_process_ci.py")).hexdigest(),
}, ensure_ascii=False, indent=2))
