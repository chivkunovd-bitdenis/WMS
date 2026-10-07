"""Corrupt current-PID tracking only in a disposable actual-source copy."""

import subprocess
import sys
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
TEST = "test_wms662_batch_pid_snapshot_contract.py"
FIXTURE = "test_wms662_batch_handoff_lock_order.py"
HELPER = "test_wms662_cancellation_lock_order.py"
with tempfile.TemporaryDirectory(prefix="wms652-batch-pid-") as directory:
    root = Path(directory)
    tests = root / "tests"
    tests.mkdir()
    (tests / TEST).write_bytes((ROOT / "backend/tests" / TEST).read_bytes())
    for name in (FIXTURE, HELPER):
        source = subprocess.check_output(["git", "show", f"HEAD:backend/tests/{name}"],
                                         cwd=ROOT).decode()
        if name == FIXTURE:
            before = "            self.pids[worker] = pid"
            assert source.count(before) == 1
            source = source.replace(before, "            self.pids.setdefault(worker, pid)")
        (tests / name).write_text(source)
    command = [
        sys.executable, "-B", "-m", "pytest", "--noconftest", "-c", "/dev/null",
        "--rootdir=" + str(root), "-q", "--capture=tee-sys", "-p", "no:cacheprovider",
        str(tests / TEST), "-k", "test_live_cycle_observation_after_pid_change",
        "--junitxml=" + str(OUT / "preservation-control.xml"),
    ]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    (OUT / "preservation-control.log").write_text(result.stdout + result.stderr)
    print(result.stdout + result.stderr, end="")
    raise SystemExit(result.returncode)
