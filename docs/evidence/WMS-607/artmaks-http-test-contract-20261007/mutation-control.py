"""Reproducible copy-only control: remove known-key protection for unsafe states.

No tracked source is edited. The observed native lp boundary remains unchanged.
Exit 0 here means all three preservation tests rejected the mutant, not acceptance.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
SOURCE = ROOT / "tools/print-agent/wms_print_direct_macos.swift"
TEST = ROOT / "tools/print-agent/test_macos_artmaks_http_contract.py"
CASES = [
    "test_unknown_same_key_never_resubmits_after_queue_recovery",
    "test_submitting_same_key_has_one_live_external_submission",
    "test_accepted_receipt_same_key_never_resubmits",
]
original = SOURCE.read_text()
needle = "if let old=jobs[key] {"
assert original.count(needle) == 1
with tempfile.TemporaryDirectory(prefix="wms607-http-copy-control-") as directory:
    mutant = Path(directory) / "unsafe-known-key.swift"
    mutant.write_text(original.replace(needle, 'if let old=jobs[key], old.status == "failed_before_submit" {'))
    result = subprocess.run(
        [sys.executable, str(TEST), "-v", *["ArtMaksHTTPContract." + c for c in CASES]],
        env={**os.environ, "WMS607_SWIFT_SOURCE": str(mutant),
             "WMS607_HTTP_EVIDENCE_DIR": str(EVIDENCE / "mutant")},
        capture_output=True, text=True, timeout=90,
    )
    log = result.stdout + result.stderr
    (EVIDENCE / "mutation-red.log").write_text(log)
    expected = result.returncode == 1 and "FAILED (failures=3)" in log and "ERROR:" not in log
    summary = {"exit": result.returncode, "expected_failures": 3, "all_rejected": expected,
               "change": "Known-key branch protects only failed_before_submit; other states overwritten",
               "cases": CASES, "tracked_source_unchanged": SOURCE.read_text() == original}
    (EVIDENCE / "mutation-result.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
    sys.exit(0 if expected else 1)
