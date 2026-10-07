"""Exact immutable pin handoff; reuses prior hash review via Git-object equality.
Run from this repository: python3 -B <this-file> > pin-proof.json
No tests, prior probe, build, browser, CI or network action is executed.
"""
import collections
import hashlib
import json
import subprocess

BASE = "4b298efc95be7b4b6b7fe5665be9f3671f1fe747"
SOURCE = "b815b166fbcd4db9d014ed1a9d961d7c56225130"
REVIEWED = "dce1b012e0929e227b182863bb14a378d04d3412"
REVIEW = "4e4819af8f5cd4fa6685c7cf76a0f16085e15f84"
PRODUCT = "1cf85fc500bc6ee7a5f4ef283b250c4bf59c5333"
ANALYST = "4fefb44aa094a6283ccbe3889f316c98017862ff"
POLICY = "guards/PROCESS_CONTRACTS.json"
EVIDENCE = "docs/evidence/WMS-652/nested-stock-source-review-20261007/"
ACCEPTANCE = "docs/evidence/WMS-652/nested-stock-acceptance-20261007/"


def git(*args):
    return subprocess.check_output(["git", *args])


def blob(path, ref=SOURCE):
    return git("show", ref + ":" + path)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tree(ref):
    result = {}
    for row in git("ls-tree", "-r", "-z", ref).split(b"\0"):
        if row:
            header, path = row.split(b"\t", 1)
            result[path.decode()] = header.decode().split()
    return result


actual, reviewed = tree(SOURCE), tree(REVIEWED)
assert POLICY not in tree(BASE)
git("merge-base", "--is-ancestor", BASE, SOURCE)
raw = blob(POLICY)
assert raw == blob(POLICY, REVIEWED)
policy_hash = sha(raw)
assert policy_hash == "7307bc57f5a585eeb56f5287eb73550a91e54fbda272040e0bba947474f5274c"
policy = json.loads(raw)
prior_proof_raw = blob(EVIDENCE + "proof.json")
assert prior_proof_raw == blob(EVIDENCE + "proof.json", REVIEW)
assert blob(EVIDENCE + "review.md") == blob(EVIDENCE + "review.md", REVIEW)
prior_proof = json.loads(prior_proof_raw)
assert prior_proof["reviewed_source"] == REVIEWED and prior_proof["policy_sha256"] == policy_hash
rows = []
for path, digest in sorted(policy["files"].items()):
    assert actual[path] == reviewed[path], path
    mode, kind, oid = actual[path]
    assert mode in ("100644", "100755") and kind == "blob", path
    rows.append([path, mode, oid, digest])
assert len(rows) == prior_proof["protected_regular_files"] == 233
modes = dict(collections.Counter(row[1] for row in rows))
assert modes == {"100644": 226, "100755": 7}
rows_hash = sha(json.dumps(rows, separators=(",", ":")).encode())
assert rows_hash == prior_proof["actual_git_rows_sha256"]
assert len(policy["suites"]) == 22
assert sum(len(s["cases"]) for s in policy["suites"].values()) == 1184
retention = {}
for ref in ("93b0757103fbd29fb00d4f198f6baab8def85172", "321f69385a8783bbf0c2fa65e80829e4c9c32373"):
    old = json.loads(blob(POLICY, ref))
    old_tree = tree(ref)
    assert set(old["files"]) <= set(policy["files"])
    assert all(actual[p][:2] == old_tree[p][:2] for p in old["files"])
    for name, definition in old["suites"].items():
        now = policy["suites"][name]
        assert {k: v for k, v in definition.items() if k != "cases"} == {k: v for k, v in now.items() if k != "cases"}
        assert set(definition["cases"]) <= set(now["cases"])
        assert [c for c in now["cases"] if c in set(definition["cases"])] == definition["cases"]
    retention[ref] = {"files": len(old["files"]), "case_ids": sum(len(s["cases"]) for s in old["suites"].values()),
                      "all_paths_modes_case_ids_order_and_suite_metadata_retained": True}
backend = policy["suites"]["backend-fbs"]
assert len(backend["cases"]) == 619 and backend["report"] == "backend-all.xml"
assert backend["exact"] is False and backend["format"] == "junit"
contract = json.loads(blob("docs/evidence/WMS-652/nested-stock-test-contract-20261007/contract.json"))
assert backend["cases"][-4:] == contract["xml_ids"]
frozen = git("diff-tree", "--no-commit-id", "--name-only", "-r", "f1e355525edbf41177d379c70cc5ee721986c967").decode().splitlines()
frozen_tree = tree("f1e355525edbf41177d379c70cc5ee721986c967")
assert len(frozen) == 9 and all(actual[p] == frozen_tree[p] for p in frozen)
assert git("diff", "--name-only", PRODUCT, SOURCE, "--", "backend/app", "frontend/src") == b""
changed = git("diff", "--name-only", REVIEWED, SOURCE).decode().splitlines()
assert all(p.startswith("docs/") for p in changed)

actor_hashes = {}
for path in (ACCEPTANCE + "README.md", ACCEPTANCE + "source-probe.json",
             "docs/requirements/WMS-652.md", "docs/KANONICHESKIY_BACKLOG.md"):
    content = blob(path)
    assert content == blob(path, ANALYST), path
    actor_hashes[path] = sha(content)
acceptance = json.loads(blob(ACCEPTANCE + "source-probe.json"))
assert acceptance["analyst_session"] == "01a11390-1014-76a0-9302-fbe0fd46ed1f"
assert acceptance["reviewed_source"] == REVIEWED and acceptance["independent_review_commit"] == REVIEW
assert acceptance["approved_PRODUCT_reference"] == PRODUCT
assert acceptance["software_acceptance"] == "PASS R52/C66-C68 and bounded formatting/ledger/reference migration"
assert acceptance["release_accepted"] is False and acceptance["final_SOURCE_pin_approval"] is False
assert acceptance["xml_ids"] == contract["xml_ids"]
assert acceptance["counts_from_independent_proof"]["actual_git_rows_sha256"] == rows_hash
for path, digest in acceptance["input_sha256"].items():
    assert sha(blob(path)) == digest, path

print(json.dumps({
    "verdict": "APPROVED exact bootstrap BASE/SOURCE pair; prepared accepted candidate only",
    "BASE": BASE, "SOURCE": SOURCE, "PRODUCT": PRODUCT, "policy_sha256": policy_hash,
    "protected_regular_files": 233, "modes": modes, "suites": 22, "required_IDs": 1184,
    "all233_actual_Git_blobs_and_modes_identical_to_reviewed_SOURCE": REVIEWED,
    "prior_verified_SHA256s_carried_by_identical_Git_objects": True,
    "actual_git_rows_sha256": rows_hash, "old_retention": retention,
    "changed_existing_hashes_from_prior_source_review": prior_proof["changed_existing_protected_hashes"],
    "closure_hashes": prior_proof["source_closure_hashes"], "backend_required_cases": 619,
    "four_exact_appended_JUnit_IDs": contract["xml_ids"], "nine_frozen_contract_files_preserved": True,
    "whole_APP_equal_to_exact_PRODUCT": True, "docs_only_delta_since_reviewed_SOURCE": changed,
    "independent_review": REVIEW, "distinct_R52_analyst_commit": ANALYST,
    "analyst_acceptance_source": acceptance["acceptance_source"], "actor_documents_sha256": actor_hashes,
    "historical_failed_CI": "37556521625 attempt1; cbd/8b8 merge FAILED733s/12m13; mandatoryPG not executed",
    "historical_SQLite_lock_owner": "UNKNOWN", "existing_local_PG_advisory_skip": "NOT verified PASS",
    "new_test_build_browser_CI_or_prior_probe_runs": [],
    "main_pin_activation_fullCI_release_deploy_or_physical_proof": "NOT performed or claimed",
    "next_required": "ordinary configuration-only main PR with exact SOURCEb815, then final candidate fullCI",
}, ensure_ascii=False, indent=2))
