"""Prove rejection tests fail if validation is bypassed in an actual-source COPY."""

import subprocess
import sys
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
TEST = "backend/tests/test_wms662_exact_fixture_pairs_contract.py"
CHECKER = "scripts/ci/check_task_documents.py"
INPUTS = "docs/evidence/WMS-652/batch-exact-ledger-test-contract-20261007/historical-inputs.json"
source = subprocess.check_output(["git", "show", f"HEAD:{CHECKER}"], cwd=ROOT).decode()
before = "    def fail(reason: str) -> tuple[dict[str, set[str]], list[str]]:"
assert source.count(before) == 1
mutated = source.replace(before, "    return {}, []  # deliberate copy-only bypass\n\n" + before)
with tempfile.TemporaryDirectory(prefix="wms662-exact-pairs-") as directory:
    root = Path(directory)
    for path, value in ((TEST, (ROOT / TEST).read_bytes()),
                        (INPUTS, (ROOT / INPUTS).read_bytes()), (CHECKER, mutated.encode())):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    result = subprocess.run([
        sys.executable, "-B", "-m", "pytest", "--noconftest", "-c", "/dev/null",
        "--rootdir=" + str(root / "backend"), "-q", "-p", "no:cacheprovider", str(root / TEST),
        "-k", "wrong_task or mutated_assertion or missing_changed_review",
        "--junitxml=" + str(OUT / "failclosed-control.xml"),
    ], cwd=root, capture_output=True, text=True, check=False)
    (OUT / "failclosed-control.log").write_text(result.stdout + result.stderr)
    print(result.stdout + result.stderr, end="")
    raise SystemExit(result.returncode)
