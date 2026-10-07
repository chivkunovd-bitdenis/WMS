"""Bounded immutable AST/byte proof and actual legacy-ledger controls.

Run from this checkout with python3 -B. Scratch Git has local object alternates,
no checkout/remotes, and is removed on exit. No product/test file is edited.
"""
import ast
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import tempfile

SOURCE = "d40bc41995cb2ad434187734419dd2bfe507b8da"
CONTRACT = "e70291d40e7d769109e33aa291e70bfa289974a4"
PORTABLE = "ed14e025af0e16931c93ded0851c99da9aaa0e33"
PRIOR = "321f69385a8783bbf0c2fa65e80829e4c9c32373"
PRODUCT = "25ebc6fe13384a55cf1f2b7e5e4054bb862d002d"
FILE = "backend/tests/test_prod_deploy_backup_gate_boundary.py"
ORIGINAL = "backend/tests/test_prod_deploy_backup.py"
CHECKER = "scripts/ci/check_task_documents.py"
LEDGER_PATH = "docs/reviews/contract-corrections/WMS-652.json"
FULL = "0632023b3ebea0de566823f112e6a1eeca5b5222a3cfd538d5624da1d4d81408"


def git(*args, cwd=None, data=None):
    return subprocess.check_output(["git", *args], cwd=cwd, input=data)


def blob(ref, path):
    return git("show", ref + ":" + path)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data):
    return ast.dump(ast.parse(data), include_attributes=False, show_empty=True)


before = blob(PORTABLE, FILE)
after = blob(SOURCE, FILE)
assert canonical(before) == canonical(after)
assert after == blob("26770cb844c62999ad29042eba0e5ada51729482", FILE)
assert git("diff-tree", "--no-commit-id", "--name-only", "-r", SOURCE).decode().splitlines() == [FILE]
assert blob(SOURCE, CHECKER) == blob(PRIOR, CHECKER)
frozen = git("diff-tree", "--no-commit-id", "--name-only", "-r", CONTRACT).decode().splitlines()
assert len(frozen) == 4 and {FILE} < set(frozen)
assert all(blob(CONTRACT, p) == blob(SOURCE, p) for p in frozen if p != FILE)
gate_name = "test_backup_fixture_server_ci_boundary_precedes_every_docker_action"


def function(data, name):
    return next(n for n in ast.parse(data).body if isinstance(n, ast.FunctionDef) and n.name == name)


assert ast.dump(function(blob(CONTRACT, FILE), gate_name), show_empty=True) == ast.dump(function(after, gate_name), show_empty=True)
assert blob(SOURCE, ORIGINAL) == blob(PRIOR, ORIGINAL)
original = function(blob(SOURCE, ORIGINAL), "test_deploy_requires_verified_backup_before_migration")
variants = ast.literal_eval(original.decorator_list[0].args[1])
assert variants == ["", "dump", "archive", "listing", "empty", "network", "retry"]
assertions = [ast.dump(n, include_attributes=False, show_empty=True)
              for n in ast.walk(original) if isinstance(n, ast.Assert)]
assert len(assertions) == 23
assert sha(json.dumps(assertions, ensure_ascii=False).encode()) == FULL
old_data = blob(CONTRACT, ORIGINAL).decode()
old_function = function(old_data, "test_deploy_requires_verified_backup_before_migration")
old_asserts = [n for n in ast.walk(old_function) if isinstance(n, ast.Assert)]
new_asserts = [n for n in ast.walk(original) if isinstance(n, ast.Assert)]
assert [ast.get_source_segment(old_data, n) for n in old_asserts] == [
    ast.get_source_segment(blob(SOURCE, ORIGINAL).decode(), n) for n in new_asserts
]
assert ast.dump(old_function.decorator_list[0], show_empty=True) == ast.dump(original.decorator_list[0], show_empty=True)
# The feature detection selects full-field output on3.14, and no unsupported
# keyword on legacy APIs. The historical3.11 actual digest is retained in Git.
def legacy_dump(node, annotate_fields=True, include_attributes=False, *, indent=None):
    return ast.dump(node, annotate_fields=annotate_fields,
                    include_attributes=include_attributes, indent=indent, show_empty=True)
assert ("show_empty" in inspect.signature(ast.dump).parameters) is True
assert ("show_empty" in inspect.signature(legacy_dump).parameters) is False
legacy_assertions = [legacy_dump(n, include_attributes=False)
                     for n in ast.walk(original) if isinstance(n, ast.Assert)]
assert legacy_assertions == assertions
serialized = json.loads(blob(SOURCE, "docs/evidence/WMS-652/portable-backup-preservation-20261007/serialization-proof.json"))
assert serialized["linux_311_actual_sha256"] == FULL
assert after.count(FULL.encode()) == 1
assert b"ddbfe3e8447dd54825fadf01f437a1adb6fa18f2ed583f58172cb1ed962fc3da" not in after
assert git("diff", "--name-only", PRIOR, SOURCE, "--", "frontend", "backend/app", CHECKER) == b""
app_delta = git("diff", "--name-only", PRODUCT, SOURCE, "--", "frontend/src", "backend/app").decode().splitlines()
assert app_delta == ["frontend/src/integrations/cryptoProCades.test.ts"]

ledger = {"task": "WMS-652", "corrections": [{
    "contract_commit": CONTRACT, "correction_commit": SOURCE, "files": [FILE],
    "review": {"model": "gpt-6.1-sol", "effort": "high", "verdict": "PASS"},
}]}
namespace = {"__name__": "independent_ledger_probe"}
exec(compile(blob(SOURCE, CHECKER), CHECKER, "exec"), namespace)
with tempfile.TemporaryDirectory(prefix="wms652-ledger-review-") as scratch:
    root = Path(scratch)
    git("init", "-q", cwd=root)
    objects = Path(git("rev-parse", "--git-common-dir").decode().strip()).resolve() / "objects"
    (root / ".git/objects/info/alternates").write_text(str(objects) + "\n")
    git("read-tree", SOURCE, cwd=root)
    def add_blob(path, data):
        oid = git("hash-object", "-w", "--stdin", cwd=root, data=data).decode().strip()
        git("update-index", "--add", "--cacheinfo", "100644," + oid + "," + path, cwd=root)
    def commit(parent, message):
        tree = git("write-tree", cwd=root).decode().strip()
        oid = git("-c", "user.name=Independent ledger probe", "-c", "user.email=probe@example.invalid",
                  "commit-tree", tree, "-p", parent, cwd=root, data=message.encode()).decode().strip()
        git("update-ref", "HEAD", oid, cwd=root)
        return oid
    # Without ledger, the actual frozen-contract comparison rejects the amendment.
    git("update-ref", "HEAD", SOURCE, cwd=root)
    base = git("rev-parse", CONTRACT + "^", cwd=root).decode().strip()
    without = namespace["contract_change_errors"](root, base)
    assert any(FILE in e for e in without)
    add_blob(LEDGER_PATH, json.dumps(ledger).encode())
    accepted_head = commit(SOURCE, "isolated exact ledger positive control")
    baselines, ledger_errors = namespace["reviewed_contract_correction"](root, "WMS-652", CONTRACT)
    assert baselines == {SOURCE: {FILE}} and ledger_errors == []
    positive = namespace["contract_change_errors"](root, base)
    assert positive == [], positive
    # This is an actual later Git blob mutation, while the ledger pin staysd40.
    add_blob(FILE, after.replace(b"assert len(assertions) == 23", b"assert len(assertions) == 22"))
    commit(accepted_head, "isolated later boundary mutation negative control")
    negative = namespace["contract_change_errors"](root, base)
    assert any(FILE in e for e in negative), negative

print(json.dumps({
    "verdict": "PASS finite cumulative portable metadata/format amendment and exact existing ledger",
    "source": SOURCE, "original_contract": CONTRACT, "portable_amendment": PORTABLE,
    "file_sha256": sha(after), "format_before_sha256": sha(before),
    "whole_file_AST_equal_before_after_format": True,
    "canonical_AST_sha256": sha(canonical(after).encode()),
    "original_23_assertions_and_seven_parameters_byte_preserved": True,
    "original_five_gate_controls_AST_preserved": True,
    "fixed_full_field_assertions_sha256": FULL, "legacy_signature_control": "PASS",
    "original_contract_files": frozen, "other_three_contract_files_byte_preserved": True,
    "proposed_exact_ledger": ledger, "actual_checker_sha256": sha(blob(SOURCE, CHECKER)),
    "actual_checker_unchanged": True,
    "ledger_absent_rejection": without, "actual_ledger_baselines": {SOURCE: [FILE]},
    "actual_contract_gate_with_ledger": positive,
    "later_mutation_rejection": negative, "scratch_removed": True,
    "frontend_including_43_CDP7_Node12_and_APP_unchanged_since_prior_pin": True,
    "product_comparison_only_prior_infrastructure_test_title": app_delta,
    "new_SOURCE_pin_approval": False, "full_CI_pass": False,
}, ensure_ascii=False, indent=2))
