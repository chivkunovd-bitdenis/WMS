"""Offline immutable Git accounting; no tests, source execution or network calls.

Reproduce from this repository: python3 -B <this-file> > source-probe.json
"""
import collections
import hashlib
import json
import subprocess

BASE = "4b298efc95be7b4b6b7fe5665be9f3671f1fe747"
SOURCE = "321f69385a8783bbf0c2fa65e80829e4c9c32373"
REVIEWED = "972da18be97cab8c41b14b0aa00a3d30773e4492"
HISTORICAL = "9dae4b19f6d4dca554200e08282579414a110848"
OLD = "93b0757103fbd29fb00d4f198f6baab8def85172"
PRODUCT = "25ebc6fe13384a55cf1f2b7e5e4054bb862d002d"
ANALYST = "ff6110eebc0ca1d39c1f2308e1141420e5853d79"
REVIEW = "7c4670975d7e70cbbfe28fb0cd4ee66f39018007"
POLICY = "guards/PROCESS_CONTRACTS.json"
EXPECTED = "1dced9197f99a8922ca6d10795fab51a02c48ebd821e90fc686ac56860caa2eb"


def git(*args):
    return subprocess.check_output(["git", *args])


def blob(ref, path):
    return git("show", ref + ":" + path)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tree(ref):
    result = {}
    for record in git("ls-tree", "-r", "-z", ref).split(b"\0"):
        if record:
            header, path = record.split(b"\t", 1)
            mode, kind, oid = header.decode().split()
            result[path.decode()] = (mode, kind, oid)
    return result


raw = blob(SOURCE, POLICY)
policy = json.loads(raw)
assert sha(raw) == EXPECTED
assert raw == blob(REVIEWED, POLICY)
git("merge-base", "--is-ancestor", BASE, SOURCE)
assert POLICY not in tree(BASE)
actual = tree(SOURCE)
reviewed_tree = tree(REVIEWED)
rows = []
for path, expected in sorted(policy["files"].items()):
    mode, kind, oid = actual[path]
    assert kind == "blob" and mode in {"100644", "100755"}, path
    digest = sha(blob(SOURCE, path))
    assert digest == expected, path
    assert actual[path] == reviewed_tree[path], path
    rows.append([path, mode, oid, digest])
assert len(rows) == 230
modes = dict(collections.Counter(row[1] for row in rows))
assert modes == {"100644": 223, "100755": 7}
suites = policy["suites"]
assert len(suites) == 22
assert sum(len(v["cases"]) for v in suites.values()) == 1180
assert all(len(v["cases"]) == len(set(v["cases"])) for v in suites.values())

retention = {}
for ref in (OLD, HISTORICAL, REVIEWED):
    previous = json.loads(blob(ref, POLICY))
    old_tree = tree(ref)
    assert set(previous["files"]) <= set(policy["files"])
    for path in previous["files"]:
        assert old_tree[path][:2] == actual[path][:2], path
    for name, definition in previous["suites"].items():
        now = suites[name]
        assert {k: v for k, v in definition.items() if k != "cases"} == {
            k: v for k, v in now.items() if k != "cases"
        }, name
        assert set(definition["cases"]) <= set(now["cases"]), name
        assert [x for x in now["cases"] if x in set(definition["cases"])] == definition["cases"], name
    changes = [{"path": p, "before": h, "after": policy["files"][p]}
               for p, h in previous["files"].items() if h != policy["files"][p]]
    retention[ref] = {
        "previous_files": len(previous["files"]),
        "previous_suites": len(previous["suites"]),
        "previous_case_ids": sum(len(v["cases"]) for v in previous["suites"].values()),
        "all_paths_modes_ids_order_and_suite_metadata_retained": True,
        "changed_existing_hashes": changes,
        "new_paths": sorted(set(policy["files"]) - set(previous["files"])),
        "existing_suite_definitions_byte_semantic_equal": previous["suites"] == {
            k: suites[k] for k in previous["suites"]
        },
    }
assert not retention[REVIEWED]["changed_existing_hashes"]
assert set(x["path"] for x in retention[HISTORICAL]["changed_existing_hashes"]) == {
    ".github/workflows/ci.yml", "backend/tests/test_prod_deploy_backup_gate_boundary.py",
    "frontend/tests-e2e/wms652-critical/browser.mjs", "scripts/ci/tests/test_ci_release_additions.py",
}
assert retention[HISTORICAL]["existing_suite_definitions_byte_semantic_equal"]
assert retention[HISTORICAL]["new_paths"] == ["frontend/tests-e2e/wms652-cdp-cancellation.test.mjs"]

changed_docs = git("diff", "--name-only", REVIEWED, SOURCE).decode().splitlines()
assert all(p.startswith("docs/") for p in changed_docs)
app_delta = git("diff", "--name-only", PRODUCT, SOURCE, "--", "frontend/src", "backend/app",
                "frontend/package.json", "frontend/package-lock.json", "backend/pyproject.toml").decode().splitlines()
assert app_delta == ["frontend/src/integrations/cryptoProCades.test.ts"]
workflow = blob(SOURCE, ".github/workflows/ci.yml").decode()
assert workflow.count("--trusted-ref " + PRODUCT) == 1
assert workflow.count("node --test --test-reporter=tap frontend/tests-e2e/wms652-cdp-cancellation.test.mjs") == 1
closure = ["frontend/tests-e2e/wms652-cdp-cancellation.test.mjs",
           "frontend/tests-e2e/wms652-critical/browser.mjs", "frontend/package.json", "frontend/package-lock.json"]
assert all(p in policy["files"] for p in closure)
assert blob(SOURCE, closure[0]) == blob("d0242bb882290daadd59e5a38e678392d3a520a3", closure[0])
assert blob(SOURCE, closure[1]) == blob("307873b739c879a7e322275efc223f0069b47745", closure[1])
assert suites["fbs-cdp-cancellation"]["report"] == "print/wms652-cdp-cancellation.tap"
assert suites["fbs-cdp-cancellation"]["format"] == "node-tap"
assert suites["fbs-cdp-cancellation"]["exact"] is True
assert len(suites["fbs-cdp-cancellation"]["cases"]) == 7

acceptance_path = "docs/evidence/WMS-652/infrastructure-delta-acceptance-20261007/acceptance.json"
acceptance_raw = blob(SOURCE, acceptance_path)
assert acceptance_raw == blob(ANALYST, acceptance_path)
acceptance = json.loads(acceptance_raw)
# Locate identity assertions without depending on a document's nesting layout.
assert REVIEWED in acceptance_raw.decode() and REVIEW in acceptance_raw.decode()
assert "ACCEPTED prepared cumulative four infrastructure corrections" in acceptance_raw.decode()
review_path = "docs/evidence/WMS-652/cdp-cancellation-source-review-20261007/r1-rereview.md"
assert blob(SOURCE, review_path) == blob(REVIEW, review_path)

print(json.dumps({
    "verdict": "APPROVED exact bootstrap BASE/SOURCE pair; prepared candidate only",
    "BASE": BASE, "SOURCE": SOURCE, "policy_sha256": sha(raw),
    "regular_files": len(rows), "modes": modes, "suites": len(suites), "case_ids": 1180,
    "actual_git_rows_sha256": sha(json.dumps(rows, separators=(",", ":")).encode()),
    "all_actual_git_blob_hashes_match_policy": True,
    "protected_blobs_modes_policy_and_suites_identical_to_reviewed_SOURCE": REVIEWED,
    "retention": retention, "docs_only_delta_since_reviewed_SOURCE": changed_docs,
    "closure_hashes": {p: policy["files"][p] for p in closure},
    "new_suite": suites["fbs-cdp-cancellation"], "static_accepted_product_reference": PRODUCT,
    "app_comparison_only_prior_reviewed_infrastructure_title": app_delta,
    "analyst_commit": ANALYST, "acceptance_sha256": sha(acceptance_raw),
    "independent_R1_closed_review": REVIEW,
    "new_test_build_browser_CI_or_network_runs": [],
    "original_historical_CI_cause": "UNKNOWN",
    "full_CI_and_post_patch_actual_43_case_effectiveness": "REQUIRED NEXT; NOT APPROVED AS PASS",
    "main_pin_activation_release_deploy_physical_proof": "NOT PERFORMED OR CLAIMED",
}, ensure_ascii=False, indent=2))
