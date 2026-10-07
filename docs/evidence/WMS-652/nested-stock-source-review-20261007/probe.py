"""Immutable source/contract/receipt/policy accounting. No tests are executed.
Reproduce from this repository: python3 -B <this-file> > proof.json
"""
import collections
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET

SOURCE = "dce1b012e0929e227b182863bb14a378d04d3412"
PRIOR = "321f69385a8783bbf0c2fa65e80829e4c9c32373"
BEFORE = "31cd68fd70791a7433562dc2495a7d67e969d840"
TESTWRITER = "f1e355525edbf41177d379c70cc5ee721986c967"
IMPORTED_TESTS = "021d86f97"
PRODUCT = "1cf85fc500bc6ee7a5f4ef283b250c4bf59c5333"
OLD_PRODUCT = "25ebc6fe13384a55cf1f2b7e5e4054bb862d002d"
HOOK = "backend/app/services/fbs_stock_publish_service.py"
TEST = "backend/tests/test_stock_publish_nested_commit_contract.py"
CONTRACT_DIR = "docs/evidence/WMS-652/nested-stock-test-contract-20261007/"
DEV_DIR = "docs/evidence/WMS-652/nested-stock-developer-20261007/"
REF_DIR = "docs/evidence/WMS-652/nested-stock-reference-migration-20261007/"


def git(*args):
    return subprocess.check_output(["git", *args])


def blob(path, ref=SOURCE):
    return git("show", ref + ":" + path)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tree(ref):
    rows = {}
    for entry in git("ls-tree", "-r", "-z", ref).split(b"\0"):
        if entry:
            header, path = entry.split(b"\t", 1)
            rows[path.decode()] = header.decode().split()
    return rows


frozen_paths = git("diff-tree", "--no-commit-id", "--name-only", "-r", TESTWRITER).decode().splitlines()
assert len(frozen_paths) == 9
for path in frozen_paths:
    assert blob(path) == blob(path, TESTWRITER), path
git("merge-base", "--is-ancestor", IMPORTED_TESTS, PRODUCT)
requirements = "docs/requirements/WMS-652.md"
assert blob(requirements, "476d206dc791799f88714012093c1ec315885fba") == blob(requirements, "95932a450")
git("merge-base", "--is-ancestor", "95932a450", IMPORTED_TESTS)
contract = json.loads(blob(CONTRACT_DIR + "contract.json"))
for path, expected in contract["source_closure_sha256"].items():
    assert sha(blob(path, TESTWRITER)) == expected, path
    if path != HOOK:
        assert sha(blob(path)) == expected, path
proof = json.loads(blob(CONTRACT_DIR + "preservation-proof.json"))
for path, expected in proof["raw_sha256"].items():
    assert sha(blob(CONTRACT_DIR + path)) == expected
for entry in proof["frozen_sources"]:
    assert sha(blob(entry["path"], TESTWRITER)) == entry["sha256"]
    if entry["path"] != HOOK:
        assert sha(blob(entry["path"])) == entry["sha256"]

before = blob(HOOK, BEFORE)
after = blob(HOOK)
guard = b"        if sync_session.in_nested_transaction():\n            return\n"
assert after.count(guard) == 1 and after.replace(guard, b"", 1) == before
assert after == blob(HOOK, PRODUCT)
assert git("diff-tree", "--no-commit-id", "--name-only", "-r", PRODUCT).decode().splitlines() == [HOOK]
assert git("diff", "--name-only", PRODUCT, SOURCE, "--", "backend/app", "frontend/src") == b""
app_delta = git("diff", "--name-only", OLD_PRODUCT, SOURCE, "--", "backend/app", "frontend/src").decode().splitlines()
assert app_delta == [HOOK, "frontend/src/integrations/cryptoProCades.test.ts"]
manifest = json.loads(blob(DEV_DIR + "manifest.json"))
assert manifest["implementation_sha"] == PRODUCT and len(manifest["members"]) == 8
for member in manifest["members"]:
    data = blob(DEV_DIR + member["path"])
    assert len(data) == member["bytes"] and sha(data) == member["sha256"]
dev_preservation = json.loads(blob(DEV_DIR + "preservation.json"))
for path, expected in dev_preservation["preserved_hashes"].items():
    assert sha(blob(path)) == expected, path


def receipt(path):
    raw = blob(path)
    rows = []
    for case in ET.fromstring(raw).iter("testcase"):
        status = next((x for x in ("failure", "error", "skipped") if case.find(x) is not None), "pass")
        rows.append({"id": case.get("classname") + "::" + case.get("name"), "status": status,
                     "detail": (case.find(status).get("message", "") if status != "pass" else "")})
    return {"sha256": sha(raw), "counts": dict(collections.Counter(x["status"] for x in rows)), "cases": rows}


receipts = {p: receipt(p) for p in [CONTRACT_DIR + "before.xml", CONTRACT_DIR + "ordinary-mutation.xml",
           DEV_DIR + "precode-red.xml", DEV_DIR + "targeted-green.xml",
           REF_DIR + "literal-before.xml", REF_DIR + "literal-after.xml"]}
new_ids = contract["xml_ids"]
for path in (CONTRACT_DIR + "before.xml", DEV_DIR + "precode-red.xml"):
    r = receipts[path]
    assert r["counts"] == {"failure": 3, "pass": 1}
    assert set(x["id"] for x in r["cases"]) == set(new_ids)
    assert all(x["status"] == ("pass" if "ordinary_native" in x["id"] else "failure") for x in r["cases"])
    assert all("AssertionError" in x["detail"] for x in r["cases"] if x["status"] == "failure")
mutation = receipts[CONTRACT_DIR + "ordinary-mutation.xml"]
assert mutation["counts"] == {"failure": 1} and "ordinary_native" in mutation["cases"][0]["id"]
assert "assert [] ==" in mutation["cases"][0]["detail"]
green = receipts[DEV_DIR + "targeted-green.xml"]
assert green["counts"] == {"pass": 10, "skipped": 1}
assert {x["id"] for x in green["cases"] if x["id"] in new_ids and x["status"] == "pass"} == set(new_ids)
skipped = next(x for x in green["cases"] if x["status"] == "skipped")
assert "Real PostgreSQL advisory locks required" in skipped["detail"]
assert b"All checks passed!" in blob(DEV_DIR + "ruff.log")
assert b"Success: no issues found in 563 source files" in blob(DEV_DIR + "mypy.log")
assert receipts[REF_DIR + "literal-before.xml"]["counts"] == {"failure": 1, "pass": 2}
assert receipts[REF_DIR + "literal-after.xml"]["counts"] == {"pass": 3}
assert {x["id"] for x in receipts[REF_DIR + "literal-before.xml"]["cases"]} == {
    x["id"] for x in receipts[REF_DIR + "literal-after.xml"]["cases"]}

workflow = ".github/workflows/ci.yml"
literal_test = "scripts/ci/tests/test_ci_release_additions.py"
for path in (workflow, literal_test):
    old = blob(path, PRIOR)
    assert old.count(OLD_PRODUCT.encode()) == 1
    assert blob(path) == old.replace(OLD_PRODUCT.encode(), PRODUCT.encode())
for path in ("scripts/ci/product_scope.py", "scripts/ci/tests/test_product_scope.py", "scripts/ci/check_task_documents.py"):
    assert blob(path) == blob(path, PRIOR), path
assert json.loads(blob(REF_DIR + "old-reference-scope.json")) == {"unapproved_product_paths": [HOOK]}
assert json.loads(blob(REF_DIR + "proposed-reference-scope.json")) == {"unapproved_product_paths": []}
assert blob("docs/reviews/contract-corrections/WMS-652.json") == blob("docs/reviews/contract-corrections/WMS-652.json", BEFORE)

policy_raw = blob("guards/PROCESS_CONTRACTS.json")
policy = json.loads(policy_raw)
old = json.loads(blob("guards/PROCESS_CONTRACTS.json", PRIOR))
current_tree, prior_tree = tree(SOURCE), tree(PRIOR)
actual_rows = []
for path, digest in sorted(policy["files"].items()):
    mode, kind, oid = current_tree[path]
    assert kind == "blob" and mode in ("100644", "100755")
    assert sha(blob(path)) == digest, path
    if path in old["files"]:
        assert current_tree[path][:2] == prior_tree[path][:2]
    actual_rows.append([path, mode, oid, digest])
assert len(actual_rows) == 233
added_paths = sorted(set(policy["files"]) - set(old["files"]))
assert added_paths == [HOOK, "backend/tests/test_stock_publish_nested_commit_contract.py", "backend/uv.lock"]
changed_hashes = [{"path": p, "before": h, "after": policy["files"][p]}
                  for p, h in old["files"].items() if h != policy["files"][p]]
assert {x["path"] for x in changed_hashes} == {workflow, literal_test, "backend/tests/test_prod_deploy_backup_gate_boundary.py"}
assert set(old["files"]) <= set(policy["files"])
assert len(policy["suites"]) == len(old["suites"]) == 22
assert sum(len(x["cases"]) for x in old["suites"].values()) == 1180
assert sum(len(x["cases"]) for x in policy["suites"].values()) == 1184
for name, definition in old["suites"].items():
    now = policy["suites"][name]
    assert {k: v for k, v in now.items() if k != "cases"} == {k: v for k, v in definition.items() if k != "cases"}
    assert now["cases"] == definition["cases"] + (new_ids if name == "backend-fbs" else [])
    assert len(now["cases"]) == len(set(now["cases"]))
backend = policy["suites"]["backend-fbs"]
assert len(backend["cases"]) == 619 and backend["report"] == "backend-all.xml"
assert backend["format"] == "junit" and backend["exact"] is False
assert all(path in policy["files"] for path in contract["source_closure"])

print(json.dumps({
    "verdict": "PASS R52 source/native contract and exact prepared product-reference migration",
    "reviewed_source": SOURCE, "technically_approved_exact_PRODUCT_reference": PRODUCT,
    "frozen_contract": TESTWRITER, "nine_contract_files_byte_preserved": frozen_paths,
    "only_product_change": "two-line nested-transaction early return before pending set access/reset",
    "stock_module_sha256": sha(after), "new_test_sha256": sha(blob(TEST)),
    "whole_module_other_bytes_preserved": True, "APP_diff_to_PRODUCT": [],
    "APP_diff_to_old_PRODUCT": app_delta, "developer_manifest_members_verified": 8,
    "saved_receipts": receipts, "full_ruff_saved": "PASS", "full_mypy_saved": "PASS563",
    "existing_PostgreSQL_skip": skipped, "policy_sha256": sha(policy_raw),
    "protected_regular_files": 233, "modes": dict(collections.Counter(row[1] for row in actual_rows)),
    "actual_git_rows_sha256": sha(json.dumps(actual_rows, separators=(",", ":")).encode()),
    "suites": 22, "required_case_ids": 1184, "old230_files_1180_IDs_retained": True,
    "changed_existing_protected_hashes": changed_hashes, "new_protected_paths": added_paths,
    "backend_required_cases": 619, "appended_exact_JUnit_IDs": new_ids,
    "scope_script_frozen51_checker_and_other_old_bytes_preserved": True,
    "source_closure_hashes": {p: policy["files"][p] for p in contract["source_closure"]},
    "historical_SQLite_lock_owner": "UNKNOWN",
    "prior_causal_collector_four_duplicate_labels_outside_target_and_statement_not_lockwait_limits": "RETAINED",
    "new_test_build_browser_CI_runs": [], "distinct_analyst_acceptance": "NEXT",
    "final_SOURCE_pin_approval": False, "full_CI_release_or_deploy_PASS": False,
}, ensure_ascii=False, indent=2))
