"""Account immutable Git blobs and saved receipts. No tests or technical self-review."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

SOURCE = "972da18be97cab8c41b14b0aa00a3d30773e4492"
PREVIOUS = "3151a29954138f0b92226ae8965a5b186b26b9f3"
INSTALLED = "9dae4b19f6d4dca554200e08282579414a110848"
PRODUCT = "25ebc6fe13384a55cf1f2b7e5e4054bb862d002d"
DIRECTORY = Path(__file__).resolve().parent
REVIEW_SHA, REVIEW_PATH = sys.argv[1:3]

def raw(ref, path):
    return subprocess.check_output(["git", "show", ref + ":" + path])

def digest(data):
    return hashlib.sha256(data).hexdigest()

policy_bytes = raw(SOURCE, "guards/PROCESS_CONTRACTS.json")
policy = json.loads(policy_bytes)
previous = json.loads(raw(PREVIOUS, "guards/PROCESS_CONTRACTS.json"))
installed = json.loads(raw(INSTALLED, "guards/PROCESS_CONTRACTS.json"))
entries = {}
for line in subprocess.check_output(["git", "ls-tree", "-r", SOURCE], text=True).splitlines():
    meta, path = line.split("\t", 1)
    entries[path] = meta.split()
files = []
for path, expected in policy["files"].items():
    actual = digest(raw(SOURCE, path))
    mode, kind, oid = entries[path]
    assert actual == expected and kind == "blob" and mode in ("100644", "100755"), path
    files.append({"path": path, "mode": mode, "blob": oid, "sha256": actual})
assert len(files) == 230 and len(policy["suites"]) == 22
assert set(previous["files"]) == set(policy["files"])
assert set(installed["files"]) <= set(policy["files"])
assert all(policy["suites"].get(name) == suite for name, suite in installed["suites"].items())
for name, old in previous["suites"].items():
    current = policy["suites"][name]
    assert {k: v for k, v in current.items() if k != "cases"} == {k: v for k, v in old.items() if k != "cases"}
    assert current["cases"][:len(old["cases"])] == old["cases"]
case_count = sum(len(suite["cases"]) for suite in policy["suites"].values())
assert case_count == 1180
new_suite = policy["suites"]["fbs-cdp-cancellation"]
contract = json.loads(raw(SOURCE, "docs/evidence/WMS-652/cdp-cancellation-test-contract-20261007/contract.json"))
assert new_suite["cases"] == contract["case_ids"] and new_suite["exact"] is True
assert new_suite["report"] == "print/wms652-cdp-cancellation.tap"
test = raw(SOURCE, "frontend/tests-e2e/wms652-cdp-cancellation.test.mjs")
assert all(name.encode() in test for name in contract["case_ids"])
assert test == raw("d0242bb882290daadd59e5a38e678392d3a520a3", "frontend/tests-e2e/wms652-cdp-cancellation.test.mjs")
changes = {p: policy["files"][p] for p in previous["files"] if policy["files"][p] != previous["files"][p]}
assert set(changes) == {"frontend/tests-e2e/wms652-cdp-cancellation.test.mjs", "frontend/tests-e2e/wms652-critical/browser.mjs"}
changed_app = subprocess.check_output(["git", "diff", "--name-only", PRODUCT, SOURCE, "--", "backend/app", "frontend/src"], text=True).splitlines()
assert changed_app == ["frontend/src/integrations/cryptoProCades.test.ts"]
inputs = [
 "docs/evidence/WMS-652/common-ci-37548248403/final-summary.json",
 "docs/evidence/WMS-652/cumulative-infrastructure-review-20261007/review.md",
 "docs/evidence/WMS-652/explicit-abort-independent-review-20261007/review.md",
 "docs/evidence/WMS-652/cdp-cancellation-contract-review-20261007/review.md",
 "docs/evidence/WMS-652/cdp-cancellation-test-contract-20261007/contract.json",
 "docs/evidence/WMS-652/cdp-cancellation-test-contract-20261007/ambiguity-proof.json",
 "docs/evidence/WMS-652/cdp-ambiguity-developer-20261007/preservation.json",
 "docs/evidence/WMS-652/cdp-ambiguity-developer-20261007/targeted-green.tap",
 "docs/evidence/WMS-652/frontend-report-identities-20261007/result.md",
 "docs/evidence/WMS-652/portable-backup-preservation-20261007/result.md",
]
review_bytes = raw(REVIEW_SHA, REVIEW_PATH)
result = {
 "source": SOURCE, "previous_prepared_source": PREVIOUS, "historical_installed_source": INSTALLED,
 "accepted_product": PRODUCT, "independent_review": {"sha": REVIEW_SHA, "path": REVIEW_PATH, "sha256": digest(review_bytes)},
 "policy_sha256": digest(policy_bytes), "files": files, "file_count": 230, "suite_count": 22, "case_ids_count": case_count,
 "previous230_22_1178_retained": True, "installed229_21_1173_retained": True,
 "changed_digests_since3151": changes, "new_cases_since3151": new_suite["cases"][5:],
 "raw_testrefs": ["frontend/tests-e2e/wms652-cdp-cancellation.test.mjs::" + name for name in new_suite["cases"]],
 "application_roots_difference": changed_app, "difference_class": "previously reviewed infrastructure .test.ts title; excluded by unchanged product_scope",
 "saved_inputs": [{"ref": SOURCE, "path": p, "sha256": digest(raw(SOURCE, p))} for p in inputs],
 "before_document_hashes": {p: digest(raw(SOURCE, p)) for p in ("docs/requirements/WMS-652.md", "docs/KANONICHESKIY_BACKLOG.md")},
 "boundary": "Identity/accounting only; no test/build/browser/runtime execution, technical self-review or final SOURCE approval",
}
(DIRECTORY / "source-probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print("PASS: exact230 Git hashes /22 suites /1180 IDs; old230/22/1178 and installed229/21/1173 retained; frozen7 exactrefs. No tests executed.")
