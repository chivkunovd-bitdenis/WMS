"""Bounded acceptance of saved evidence; does not run product tests or APIs."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.ci.process_contracts import browser_results, junit_results, node_tap_results
from scripts.ci.product_scope import verify_product_scope

SOURCE = "0151a555ac429957d0eee591317cc4326e909dfd"
GEOMETRY = "1c045a4f2d6c1bb34eeed2f5e79f6e53be2a8a9d"
MAC = "7a2fa31d83e06b2724edbcca1aaead0914ad5e56"
POLICY = json.loads((ROOT / "guards/PROCESS_CONTRACTS.json").read_text())


def raw(path):
    return (ROOT / path).read_bytes()


def git_bytes(commit, path):
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)


def exact_suite(name, actual):
    required = POLICY["suites"][name]["cases"]
    assert len(required) == len(set(required))
    assert set(actual) == set(required), name
    assert set(actual.values()) == {"passed"}, name
    return len(actual)


result = {"accepted_source": SOURCE, "scope_reference": "d61805978b3e7878d1056c99b4e6e0823edf49a5"}
assert verify_product_scope(ROOT, result["scope_reference"]) == []
result["unapproved_product_paths"] = []
for path, digest in POLICY["files"].items():
    assert hashlib.sha256(raw(path)).hexdigest() == digest, path
result["registered_files"] = len(POLICY["files"])
result["registered_cases"] = sum(len(s["cases"]) for s in POLICY["suites"].values())
rules = json.loads(raw("docs/evidence/WMS-652/process-gates-20261006/ruleset-after.json"))
checks = next(r["parameters"] for r in rules["rules"] if r["type"] == "required_status_checks")
assert rules["enforcement"] == "active" and rules["bypass_actors"] == []
assert checks["strict_required_status_checks_policy"] is True
assert len(checks["required_status_checks"]) == 9
result["saved_ruleset_readback"] = {"id": rules["id"], "required_checks": 9, "strict": True, "bypass": False, "operational_canary_claimed": False}
for path in POLICY["files"]:
    if path.startswith("frontend/tests-e2e/wms652-critical/"):
        assert raw(path) == git_bytes(GEOMETRY, path), path
for name in ["avpack-macos-launcher.js", "avpack-sold-kiz-filter.js", "avpack-sold-kiz.command", "build-avpack-macos-command.cjs"]:
    path = "scripts/ops/" + name
    assert raw(path) == git_bytes(MAC, path), path
result["geometry_source_bytes_equal"] = GEOMETRY
result["mac_source_bytes_equal"] = MAC
result["command_sha256"] = hashlib.sha256(raw("scripts/ops/avpack-sold-kiz.command")).hexdigest()
result["mac_110"] = exact_suite("mac-517-helper", node_tap_results(raw("docs/evidence/WMS-652/process-gates-20261006/integrated-mac-110.tap")))
review = junit_results(raw("docs/evidence/WMS-652/ci-delta-independent-review-20261006/contracts.xml"))
for name in ["ci-shards", "product-scope"]:
    selected = {k: v for k, v in review.items() if k in POLICY["suites"][name]["cases"]}
    result[name] = exact_suite(name, selected)
result["review_junit_records_including_subtests"] = len(review)
result["geometry_43"] = exact_suite("real-fbs-browser", browser_results(raw("docs/evidence/WMS-652/critical-fbs-contracts-20261006/geometry-final-green/result.json"), GEOMETRY))
mutation_root = ROOT / "docs/evidence/WMS-652/critical-fbs-contracts-20261006/geometry-mutants"
expected = {"hide-packing-print-action": 7, "overlap-order-seller-header": 2, "hide-selected-action-only-for-long-data": 1}
result["geometry_mutants"] = {}
for name, count in expected.items():
    report = json.loads((mutation_root / name / "result.json").read_text())
    assert report["sha"] == "695a429cd08b4a0b3675cb2d4af0d3f33eeaf9f5"
    assert [c["id"] for c in report["cases"]] == POLICY["suites"]["real-fbs-browser"]["cases"]
    failed = [c for c in report["cases"] if c["status"] == "FAIL"]
    assert len(failed) == count
    assert all("AssertionError" in c["failure"] for c in failed)
    assert all(c["status"] in {"PASS", "FAIL"} for c in report["cases"])
    result["geometry_mutants"][name] = {"failed": count, "passed": 43 - count, "failed_ids": [c["id"] for c in failed]}
collection = json.loads(raw("docs/evidence/WMS-652/ci-two-shards-20261006/backend-collection.json"))
if isinstance(collection, dict):
    collection = collection.get("nodeids", collection.get("cases"))
assert isinstance(collection, list) and len(collection) == len(set(collection)) == 4625
halves = [set(sorted(collection)[i::2]) for i in range(2)]
assert not halves[0] & halves[1] and halves[0] | halves[1] == set(collection)
result["saved_collection_only"] = {"total": 4625, "shards": [len(h) for h in halves], "intersection": 0, "executed_4625_claimed": False}
result["mac_exact_names"] = POLICY["suites"]["mac-517-helper"]["cases"]
result["geometry_exact_names"] = POLICY["suites"]["real-fbs-browser"]["cases"][-10:]
result["limits"] = ["No full CI or new product run", "No mandatory GitHub activation proof", "No deployment", "No physical Mac/signature/paper/external submission"]
print(json.dumps(result, ensure_ascii=False, indent=2))
