"""Immutable fixture/receipt/policy proof and unchanged legacy-ledger controls.
Run from this repository with python3 -B; no target or PostgreSQL run.
"""
import ast
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

SOURCE = "5b9df5acfba055bf94d5b3b21793ce2a233edff6"
OLD_SOURCE = "b815b166fbcd4db9d014ed1a9d961d7c56225130"
ORIGINAL = "2006171f0feae5513f887b471125ecae1a96c2ae"
CORRECTION = "466178698fc47d4eadecc611eeb6039c475da58a"
TESTWRITER = "8d16fca4c7d16cc97ae9fe15608708563bb5d243"
DEVELOPER_RECEIPTS = "f2ad961a13b9853a94ad6290dbd794c39ea9c223"
FIXTURE = "backend/tests/test_wms662_batch_handoff_lock_order.py"
TEST = "backend/tests/test_wms662_batch_pid_snapshot_contract.py"
DIR = "docs/evidence/WMS-652/batch-pid-test-contract-20261007/"
DEV = "docs/evidence/WMS-652/batch-pid-fixture-developer-20261007/"
CHECKER = "scripts/ci/check_task_documents.py"
LEDGER = "docs/reviews/contract-corrections/WMS-662.json"


def git(*args, cwd=None, data=None):
    return subprocess.check_output(["git", *args], cwd=cwd, input=data)


def blob(path, ref=SOURCE):
    return git("show", ref + ":" + path)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def split_class(data):
    node = next(n for n in ast.parse(data).body if isinstance(n, ast.ClassDef) and n.name == "BatchSchedule")
    lines = data.splitlines(keepends=True)
    return b"".join(lines[:node.lineno - 1] + lines[node.end_lineno:]), node


before, after = blob(FIXTURE, ORIGINAL), blob(FIXTURE)
outside, original_class = split_class(before)
assert outside == split_class(after)[0]
assert after == blob(FIXTURE, CORRECTION) == blob(FIXTURE, "308dde98518a6c14de421caadef1a9528e0e0bd4")
assert git("diff-tree", "--no-commit-id", "--name-only", "-r", CORRECTION).decode().splitlines() == [FIXTURE]
frozen = git("diff-tree", "--no-commit-id", "--name-only", "-r", ORIGINAL).decode().splitlines()
assert len(frozen) == 13 and {FIXTURE} < set(frozen)
git("merge-base", "--is-ancestor", ORIGINAL, CORRECTION)
git("merge-base", "--is-ancestor", CORRECTION, SOURCE)
historical_changes = [p for p in frozen if blob(p, ORIGINAL) != blob(p)]
assert set(historical_changes) == {FIXTURE, "docs/requirements/WMS-662.md", "frontend/src/screens/v2/FfFbsSupplyWorkspace.wms662.c19.dom.test.tsx"}
assert blob("docs/requirements/WMS-662.md") == blob("docs/requirements/WMS-662.md", OLD_SOURCE)
case = next(n for n in ast.parse(after).body if isinstance(n, ast.AsyncFunctionDef) and n.name.startswith("test_public_sync_batch"))
assert sum(isinstance(n, ast.Assert) for n in ast.walk(case)) == 21
contract = json.loads(blob(DIR + "contract.json"))
assert sha(ast.dump(case, include_attributes=False).encode()) == contract["unchanged_business_case_ast_sha256"]
assert blob(TEST) == blob(TEST, TESTWRITER)
for p, digest in contract["closure_sha256"].items():
    assert sha(blob(p, TESTWRITER)) == digest
    if p != FIXTURE:
        assert sha(blob(p)) == digest
for p, digest in contract["raw_sha256"].items():
    assert sha(blob(DIR + p)) == digest
manifest = json.loads(blob(DEV + "manifest.json", DEVELOPER_RECEIPTS))
assert manifest["implementation_sha"] == "308dde98518a6c14de421caadef1a9528e0e0bd4"
for member in manifest["members"]:
    data = blob(DEV + member["path"], DEVELOPER_RECEIPTS)
    assert len(data) == member["bytes"] and sha(data) == member["sha256"]


def xml(path, ref=SOURCE):
    raw = blob(path, ref)
    rows = []
    for node in ET.fromstring(raw).iter("testcase"):
        state = next((s for s in ("failure", "error", "skipped") if node.find(s) is not None), "pass")
        rows.append({"id": node.get("classname") + "::" + node.get("name"), "status": state})
    return {"sha256": sha(raw), "counts": dict(collections.Counter(r["status"] for r in rows)), "cases": rows}


receipts = {"testwriter_before": xml(DIR + "before.xml"), "preservation_mutation": xml(DIR + "preservation-control.xml"),
            "developer_before": xml(DEV + "precode-red.xml", DEVELOPER_RECEIPTS),
            "developer_green": xml(DEV + "targeted-green.xml", DEVELOPER_RECEIPTS)}
for label in ("testwriter_before", "developer_before"):
    assert receipts[label]["counts"] == {"failure": 1, "pass": 1}
    assert set(x["id"] for x in receipts[label]["cases"]) == set(contract["xml_ids"])
assert receipts["preservation_mutation"]["counts"] == {"failure": 1}
assert "live_cycle" in receipts["preservation_mutation"]["cases"][0]["id"]
assert receipts["developer_green"]["counts"] == {"pass": 2}
assert set(x["id"] for x in receipts["developer_green"]["cases"]) == set(contract["xml_ids"])
assert b"All checks passed!" in blob(DEV + "ruff.log", DEVELOPER_RECEIPTS)
assert b"563 source files" in blob(DEV + "mypy.log", DEVELOPER_RECEIPTS)
native_log = blob(contract["original_ci"]["raw"])
assert sha(native_log) == contract["original_ci"]["sha256"]
for text in (b"writer_pids={'batch': 219, 'ordinary': 219}", b"(209, [219], 'INSERT INTO fbs_shipment_reversal_ledger", b"test_wms662_batch_handoff_lock_order.py:346", b"issues=[]"):
    assert text in native_log
assert git("diff", "--name-only", "1cf85fc500bc6ee7a5f4ef283b250c4bf59c5333", SOURCE, "--", "backend/app", "frontend/src") == b""
assert blob(CHECKER) == blob(CHECKER, OLD_SOURCE)

policy_raw = blob("guards/PROCESS_CONTRACTS.json")
policy = json.loads(policy_raw)
old_policy = json.loads(blob("guards/PROCESS_CONTRACTS.json", OLD_SOURCE))
tree = {}
for row in git("ls-tree", "-r", "-z", SOURCE).split(b"\0"):
    if row:
        header, path = row.split(b"\t", 1)
        tree[path.decode()] = header.decode().split()
for p, digest in policy["files"].items():
    assert tree[p][0] in ("100644", "100755") and tree[p][1] == "blob"
    assert sha(blob(p)) == digest, p
assert len(policy["files"]) == 235 and len(policy["suites"]) == 22
assert sum(len(s["cases"]) for s in policy["suites"].values()) == 1186
assert set(policy["files"]) - set(old_policy["files"]) == {FIXTURE, TEST}
assert all(policy["files"][p] == digest for p, digest in old_policy["files"].items())
for name, definition in old_policy["suites"].items():
    current = policy["suites"][name]
    assert {k: v for k, v in current.items() if k != "cases"} == {k: v for k, v in definition.items() if k != "cases"}
    assert current["cases"] == definition["cases"] + (contract["xml_ids"] if name == "backend-fbs" else [])
assert len(policy["suites"]["backend-fbs"]["cases"]) == 621
assert all(p in policy["files"] for p in contract["source_closure"])

entry = {"contract_commit": ORIGINAL, "correction_commit": CORRECTION, "files": [FIXTURE],
         "review": {"model": "gpt-6.1-sol", "effort": "high", "verdict": "PASS"}}
proposed = {"task": "WMS-662", "corrections": [entry]}
existing_raw = blob(LEDGER)
existing = json.loads(existing_raw)
legacy = {k: existing[k] for k in ("contract_commit", "correction_commit", "files", "review")}
preserving = {"task": "WMS-662", "corrections": [legacy, entry], "owner_supersessions": existing["owner_supersessions"]}
namespace = {"__name__": "bounded_ledger_probe"}
exec(compile(blob(CHECKER), CHECKER, "exec"), namespace)
with tempfile.TemporaryDirectory(prefix="wms652-batch-ledger-") as temp:
    root = Path(temp)
    git("init", "-q", cwd=root)
    objects = Path(git("rev-parse", "--git-common-dir").decode().strip()).resolve() / "objects"
    (root / ".git/objects/info/alternates").write_text(str(objects) + "\n")
    def add(path, data):
        oid = git("hash-object", "-w", "--stdin", cwd=root, data=data).decode().strip()
        git("update-index", "--add", "--cacheinfo", "100644," + oid + "," + path, cwd=root)
    def head():
        tree_oid = git("write-tree", cwd=root).decode().strip()
        oid = git("-c", "user.name=Independent ledger probe", "-c", "user.email=probe@example.invalid",
                  "commit-tree", tree_oid, "-p", SOURCE, cwd=root, data=b"isolated ledger control").decode().strip()
        git("update-ref", "HEAD", oid, cwd=root)
    def contract_state(original):
        # Bounded metadata Git facts: actual resolver, then the unchanged
        # checker's exact original/approved-final byte comparisons for this
        # contract only; never enumerate the entire historical CI range.
        baselines, errors = namespace["reviewed_contract_correction"](root, "WMS-662", original)
        if errors:
            return {"resolver_errors": errors}
        frozen_paths = namespace["commit_changed_paths"](root, original)
        frozen_paths = {p for p in frozen_paths if not p.startswith("docs/requirements/")}
        corrected = set().union(*baselines.values()) if baselines else set()
        changed = set()
        untouched = sorted(frozen_paths - corrected)
        if untouched:
            changed.update(git("diff", "--no-renames", "--name-only", original, "HEAD", "--", *untouched, cwd=root).decode().splitlines())
        for baseline, paths in baselines.items():
            changed.update(git("diff", "--no-renames", "--name-only", baseline, "HEAD", "--", *sorted(paths), cwd=root).decode().splitlines())
        return {"resolver_errors": [], "changed_unapproved_or_pinned_final_paths": sorted(changed)}
    git("read-tree", SOURCE, cwd=root)
    git("update-ref", "HEAD", SOURCE, cwd=root)
    without_new_entry = contract_state(ORIGINAL)
    assert without_new_entry["changed_unapproved_or_pinned_final_paths"] == [FIXTURE]
    add(LEDGER, json.dumps(proposed).encode()); head()
    pair_baselines, pair_errors = namespace["reviewed_contract_correction"](root, "WMS-662", ORIGINAL)
    assert pair_baselines == {CORRECTION: {FIXTURE}} and pair_errors == []
    standalone_errors = {ORIGINAL: contract_state(ORIGINAL), existing["contract_commit"]: contract_state(existing["contract_commit"])}
    assert standalone_errors[ORIGINAL]["changed_unapproved_or_pinned_final_paths"] == ["frontend/src/screens/v2/FfFbsSupplyWorkspace.wms662.c19.dom.test.tsx"]
    assert standalone_errors[existing["contract_commit"]]["changed_unapproved_or_pinned_final_paths"] == ["backend/tests/test_wms662_live_delivery_substatuses.py"]
    add(FIXTURE, after.replace(b"len(set(schedule.pids.values())) == 2", b"len(set(schedule.pids.values())) == 1")); head()
    mutation_errors = contract_state(ORIGINAL)
    assert FIXTURE in mutation_errors["changed_unapproved_or_pinned_final_paths"]
    git("read-tree", SOURCE, cwd=root)
    add(LEDGER, json.dumps(preserving).encode()); head()
    preserved_baselines, preserving_errors = namespace["reviewed_contract_correction"](root, "WMS-662", ORIGINAL)
    assert preserved_baselines == {} and preserving_errors == ["WMS-662: коррекция должна менять только часть исходного контракта"]

print(json.dumps({
    "fixture_source_verdict": "PASS", "complete_proposed_ledger_verdict": "REJECTED concrete existing-ledger compatibility defect",
    "SOURCE": SOURCE, "reviewed_fixture_correction": CORRECTION, "original_contract": ORIGINAL,
    "fixture_sha256": sha(after), "frozen_test_sha256": sha(blob(TEST)),
    "outside_class_bytes_and21_business_assertions_preserved": True,
    "original13_contract_changed_paths": historical_changes,
    "historical_requirements_and_owner_authorized_UI_changes_not_new_fixture_delta": True,
    "developer_receipts_commit": DEVELOPER_RECEIPTS, "developer_manifest_verified_members": len(manifest["members"]),
    "saved_receipts": receipts, "full_Ruff_Mypy_saved": "PASS/PASS563",
    "policy_sha256": sha(policy_raw), "protected_files": 235,
    "modes": dict(collections.Counter(tree[p][0] for p in policy["files"])),
    "suites": 22, "required_IDs": 1186, "old233_files_1184_IDs_retained": True,
    "backend_fbs_cases": 621, "closure_hashes": {p: policy["files"][p] for p in contract["source_closure"]},
    "APP_equals_accepted_PRODUCT1cf": True,
    "exact_new_pair_Git_facts_and_final_byte_binding": "PASS; later mutation rejected",
    "proposed_entry": entry, "existing_ledger_sha256": sha(existing_raw),
    "existing_single_file_legacy_contract": existing["contract_commit"],
    "existing_owner_supersessions_must_be_retained": True,
    "current_without_new_entry_errors": without_new_entry,
    "standalone_proposed_JSON_errors": standalone_errors,
    "later_fixture_mutation_errors": mutation_errors,
    "preserving_existing_legacy_entry_in_array_rejection": preserving_errors,
    "checker_changed": False, "scratch_removed": True,
    "native_PG_fullCI_effectiveness": "NOT verified; run375616 remains failed",
    "new_target_PG_browser_build_or_CI_runs": [], "final_SOURCE_pin_or_release_approval": False,
}, ensure_ascii=False, indent=2))
