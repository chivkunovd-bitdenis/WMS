"""Run only the new contract from an exact Git source copy using existing deps."""

import io
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
TEST = "backend/tests/test_stock_publish_nested_commit_contract.py"
HOOK = "backend/app/services/fbs_stock_publish_service.py"
mutation = sys.argv[1:] == ["--ordinary-dispatch-mutation"]
if sys.argv[1:] and not mutation:
    raise SystemExit("Only --ordinary-dispatch-mutation is supported")
archive = subprocess.check_output([
    "git", "archive", "HEAD", "backend/app", "backend/tests/conftest.py",
    "backend/pyproject.toml",
], cwd=ROOT)
with tempfile.TemporaryDirectory(prefix="wms652-native-stock-") as directory:
    root = Path(directory)
    with tarfile.open(fileobj=io.BytesIO(archive)) as files:
        files.extractall(root, filter="data")
    (root / TEST).write_bytes((ROOT / TEST).read_bytes())
    if mutation:
        path = root / HOOK
        source = path.read_text()
        before = "        queued = session.info.get(_PENDING_KEY)"
        assert source.count(before) == 1
        path.write_text(source.replace(before, "        return\n" + before))
    stem = "ordinary-mutation" if mutation else "before"
    environment = os.environ.copy()
    environment.update({
        "GITHUB_ACTIONS": "false",
        "WMS_TEST_DATABASE_URL": f"sqlite+aiosqlite:///{root / 'conftest.sqlite'}",
        "WMS_TEST_DATA_DIR": str(root / "data"),
        "WMS_TEST_PHYSICAL_GUARDS": "0",
    })
    command = [
        sys.executable, "-B", "-m", "pytest", "-q", "--capture=tee-sys",
        "-p", "no:cacheprovider", "tests/" + Path(TEST).name,
        "--junitxml=" + str(OUT / (stem + ".xml")),
    ]
    if mutation:
        command += ["-k", "test_c67_ordinary_native_outer_commit_coalesces_duplicates_once"]
    result = subprocess.run(command, cwd=root / "backend", env=environment,
                            capture_output=True, text=True, check=False)
    (OUT / (stem + ".log")).write_text(result.stdout + result.stderr)
    print(result.stdout + result.stderr, end="")
    raise SystemExit(result.returncode)
