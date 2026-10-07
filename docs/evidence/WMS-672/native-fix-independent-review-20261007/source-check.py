"""Bounded read-only source/receipt checks; does not approve a product reference."""

import hashlib
import json
import re
import subprocess
import sys

ORIGINAL = "d61805978b3e7878d1056c99b4e6e0823edf49a5"
CONTRACT = "05a7d08a65e135256fa69e8bf84519e95bcdef96"
WIRING = "f528152ca04ccf2d86207b95ee3de0b96141948f"
FIX = "9e757a02cefa0cd1f7a95d272944e0b7c2b0660a"
INTEGRATED = "296107aafcf44d1ac5afa623d32c644fa5396233"
PRODUCT_PATHS = ["frontend/src/screens/ff/FfInboundRequestView.tsx",
                 "frontend/src/utils/printBarcodeLabel.ts"]


def git(*args):
    return subprocess.check_output(["git", *args])


def blob(ref, path):
    return git("show", f"{ref}:{path}")


receipt_root = "docs/evidence/WMS-672/native-decode-fix-20261007/"
frozen = json.loads(blob(INTEGRATED, receipt_root + "frozen-test-hashes.json"))
for path, digest in frozen.items():
    assert hashlib.sha256(blob(INTEGRATED, path)).hexdigest() == digest
    assert blob(WIRING, path) == blob(INTEGRATED, path)
assert blob(CONTRACT, "frontend/tests-e2e/wms672-native-errors.test.mjs") == blob(
    INTEGRATED, "frontend/tests-e2e/wms672-native-errors.test.mjs")
for path in ["scripts/ci/product_scope.py", "scripts/ci/tests/test_product_scope.py",
             ".github/workflows/ci.yml"]:
    assert blob(WIRING, path) == blob(INTEGRATED, path)
for path in PRODUCT_PATHS:
    assert blob(FIX, path) == blob(INTEGRATED, path)
assert git("diff", "--numstat", CONTRACT, FIX).decode().splitlines() == [
    "4\t1\t" + PRODUCT_PATHS[0], "1\t1\t" + PRODUCT_PATHS[1]]
probes = []
for ref, expected in [(ORIGINAL, PRODUCT_PATHS), (FIX, [])]:
    command = [sys.executable, "scripts/ci/product_scope.py", "--trusted-ref", ref]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    data = json.loads(result.stdout)
    assert data["unapproved_product_paths"] == expected
    assert result.returncode == (1 if expected else 0)
    probes.append({"command": command, "exit": result.returncode, "output": data})
raw = blob(INTEGRATED, receipt_root + "developer-green.tap").decode()
cases = re.findall(r"^ok \d+ - (.+)$", raw, re.M)
policy = json.loads(blob(INTEGRATED, "guards/PROCESS_CONTRACTS.json"))
for path in PRODUCT_PATHS:
    assert policy["files"][path] == hashlib.sha256(blob(FIX, path)).hexdigest()
assert cases == policy["suites"]["print-672-native-errors"]["cases"]
assert re.findall(r"^# (tests|pass|fail|cancelled|skipped|todo) (\d+)$", raw, re.M) == [
    ("tests", "7"), ("pass", "7"), ("fail", "0"), ("cancelled", "0"),
    ("skipped", "0"), ("todo", "0")]
print(json.dumps({
    "reviewed_fix": FIX, "integrated_source": INTEGRATED,
    "frozen_contract": CONTRACT, "ci_wiring": WIRING,
    "preserved_frozen_test_hashes": frozen, "scope_cli_probes": probes,
    "reviewed_product_hashes": {path: hashlib.sha256(blob(FIX, path)).hexdigest()
                                for path in PRODUCT_PATHS},
    "developer_actual_node_TAP": {"pass": 7, "fail": 0, "skips": 0,
                                  "cases": cases},
    "developer_local_receipt": json.loads(blob(INTEGRATED, receipt_root + "local-receipt.json")),
    "independent_tests_repeated": False, "linux_receipt": "pending",
    "product_reference_upgrade_approved": False,
}, ensure_ascii=False, indent=2))
