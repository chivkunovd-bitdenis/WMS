"""Immutable final-delta and deterministic activation-data audit."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from types import ModuleType
import xml.etree.ElementTree as ET
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
TARGET = "4190460c97db0db439712b17a083c5b474ee3d74"
PRIOR = "c4faeb3a58c42e2d2e04bff790230532e8970b90"
OLD = "0151a555ac429957d0eee591317cc4326e909dfd"
P = "0b5cde29ed11b2ae8a71b5c8040fbff0609b9d00"
BASE = "docs/evidence/WMS-652/final-closure-20261007/"

def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])

def blob(ref, path):
    return git("show", f"{ref}:{path}")

def data(ref, path):
    return json.loads(blob(ref, path))

def module(path):
    value = ModuleType("immutable_" + Path(path).stem)
    value.__file__ = str(ROOT / path)
    exec(compile(blob(TARGET, path), value.__file__, "exec"), value.__dict__)
    return value

pc = module("scripts/ci/process_contracts.py")
policy, prior, old = [data(ref, pc.POLICY_PATH) for ref in [TARGET, PRIOR, OLD]]
pc.validate_policy(policy)
assert (len(policy["files"]), len(policy["suites"]), sum(len(s["cases"]) for s in policy["suites"].values())) == (262, 24, 1648)
assert all(hashlib.sha256(blob(TARGET, path)).hexdigest() == digest for path, digest in policy["files"].items())
retained = []
for name, suite in old["suites"].items():
    now = policy["suites"][name]
    assert all(now[k] == suite[k] for k in ["report", "format", "exact"])
    assert set(suite["cases"]) <= set(now["cases"])
    retained.append(dict(suite=name, cases=len(suite["cases"]), **{k: now[k] for k in ["report", "format", "exact"]}))
assert len(retained) == 18 and sum(s["cases"] for s in retained) == 1146
original_ids = {case for s in old["suites"].values() for case in s["cases"]}
prior_ids = {case for s in prior["suites"].values() for case in s["cases"]}
now_ids = {case for s in policy["suites"].values() for case in s["cases"]}
assert prior_ids <= now_ids and len(now_ids-prior_ids) == 4
pg_name, pg_suite = next((name, s) for name,s in policy["suites"].items() if s["report"] == "release-postgres/658.xml")
assert pg_suite["format"] == "junit" and pg_suite["exact"] and len(pg_suite["cases"]) == 9
backend_name = next(name for name,s in policy["suites"].items() if s["report"] == "backend-all.xml")
assert set(pg_suite["cases"]) <= set(prior["suites"][backend_name]["cases"])
assert not original_ids.intersection(pg_suite["cases"])
assert set(prior["suites"][backend_name]["cases"])-set(policy["suites"][backend_name]["cases"]) == set(pg_suite["cases"])
raw = blob(TARGET, BASE + "658-ci-producer-local.xml")
assert pc.junit_results(raw) == dict.fromkeys(pg_suite["cases"], "passed")
assert not any(list(ET.fromstring(raw).iter(tag)) for tag in ["failure", "error", "skipped"])
pg_metadata = data(TARGET, BASE + "backend-aggregate-658-producer-correction.json")
assert hashlib.sha256(raw).hexdigest() == pg_metadata["local_real_pg"]["sha256"]
negatives = []
with tempfile.TemporaryDirectory(dir=HERE) as directory:
    root = Path(directory)
    report = root / pg_suite["report"]
    report.parent.mkdir(parents=True)
    focused = {"version": 1, "files": {}, "suites": {pg_name: pg_suite}}
    for scenario in ["missing-report", "one-missing", "sqlite-skip", "failure", "wrong-id", "extra-id"]:
        tree = ET.fromstring(raw)
        case = next(tree.iter("testcase"))
        if scenario == "missing-report":
            report.unlink(missing_ok=True)
        else:
            if scenario == "one-missing":
                next(tree.iter("testsuite")).remove(case)
            elif scenario in ["sqlite-skip", "failure"]:
                ET.SubElement(case, "skipped" if scenario == "sqlite-skip" else "failure")
            elif scenario == "wrong-id":
                case.set("name", "unregistered")
            else:
                extra = copy.deepcopy(case)
                extra.set("name", "unregistered")
                next(tree.iter("testsuite")).append(extra)
            report.write_bytes(ET.tostring(tree))
        try:
            pc.verify_reports(focused, root)
            raise AssertionError("accepted " + scenario)
        except ValueError as exc:
            negatives.append(dict(scenario=scenario, rejected=str(exc)))

unchanged = ["scripts/ci/process_contracts.py", "scripts/ci/backend_shards.py", "scripts/ci/build_process_proof.py",
             "scripts/ci/product_scope.py", "scripts/ci/check_task_documents.py", "scripts/ci/promote_guards.py",
             "frontend/src/screens/ff/FfInboundRequestView.tsx", "frontend/src/utils/printBarcodeLabel.ts"]
assert all(blob(PRIOR, path) == blob(TARGET, path) for path in unchanged)
workflow = yaml.safe_load(blob(TARGET, ".github/workflows/ci.yml"))["jobs"]
old_workflow = yaml.safe_load(blob(PRIOR, ".github/workflows/ci.yml"))["jobs"]
assert workflow["process-proof"] == old_workflow["process-proof"]
assert workflow["backend"]["needs"] == ["backend-checks", "backend-shards"]
assert "wms686-mockup" in workflow["process-proof"]["needs"]
step = next(s for s in workflow["backend-checks"]["steps"] if s.get("name", "").startswith("WMS-658 nine"))
assert "if" not in step and "continue-on-error" not in step
assert step["env"]["WMS_TEST_DATABASE_URL"].endswith("/wms_test_658_identity")
assert "CREATE DATABASE wms_test_658_identity" in step["run"] and "pytest -n 0" in step["run"]
assert "::test_postgresql_workers_share_one_code_pool_and_link_for_identity_variants" in step["run"]
assert "release-postgres/658.xml" in step["run"]
assert any("release-postgres" in s.get("with", {}).get("path", "") for s in workflow["backend-checks"]["steps"] if s.get("uses", "").startswith("actions/upload-artifact"))
ps = module("scripts/ci/product_scope.py")
product_delta = [p for p in git("diff", "--name-only", "--no-renames", P, TARGET).decode().splitlines() if ps.product_path(p)]
assert product_delta == []

template_path = BASE + "wms680-reviewed-activation-template.json"
template = data(TARGET, template_path)
record = template["record"]
constants = {}
for node in ast.parse(blob(TARGET, "scripts/ci/check_task_documents.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ["WMS680_CLOSED_CHAIN", "WMS680_CLOSED_SCOPES"]:
        constants[node.targets[0].id] = json.loads(json.dumps(ast.literal_eval(node.value)))
old_record = constants["WMS680_CLOSED_CHAIN"]
assert record["steps"][:-2] == old_record["steps"]
assert record["owner"] == old_record["owner"] and record["original_contract"] == old_record["original_contract"]
final = "535e8a970928e8834147553ad4c0139fcc5f10da"
assert record["final_correction_commit"] == record["reviewed_source_commit"] == final
assert record["report"] == {"path": "docs/reviews/WMS-652-final-night-release-review-20261007.md", "commit": "ACTUAL_FINAL_REVIEW_PUBLICATION_SHA", "blob": "DERIVED_FROM_ACTUAL_REVIEW_PUBLICATION"}
assert list(template["scope_addition"]) == ["4ed0c391135c95b67879c954195034b9c43d4980", final]
for step in record["steps"][-2:]:
    sha, parent = step["correction"], step["source"]
    assert git("rev-list", "--parents", "-n", "1", sha).decode().split() == [sha, parent]
    assert git("diff-tree", "--no-commit-id", "--name-only", "-r", sha).decode().splitlines() == list(step["files"])
    assert template["scope_addition"][sha] == step["files"]
    for name, pair in step["files"].items():
        assert [git("rev-parse", f"{ref}:{name}").decode().strip() for ref in [parent, sha]] == pair
    git("merge-base", "--is-ancestor", sha, TARGET)
for contract, paths in record["contracts"].items():
    assert paths.keys() == old_record["contracts"][contract].keys()
    for name, pair in paths.items():
        assert pair[0] == old_record["contracts"][contract][name][0]
        assert git("rev-parse", f"{contract}:{name}").decode().strip() == pair[0]
        assert git("rev-parse", f"{TARGET}:{name}").decode().strip() == pair[1]
# Derive the proposed ledger exactly as the unchanged validator derives it.
expected = copy.deepcopy(template["exact_ledger_after_actual_PASS"])
steps = record["steps"][1:]
entries = expected["fixture_corrections"]
expected_edges = [(record["steps"][0]["correction"], step) for step in steps]
expected_edges.append((steps[-1]["source"], steps[-1]))
assert len(entries) == len(expected_edges)
for entry, (contract, step) in zip(entries, expected_edges):
    assert entry["contract_commit"] == contract
    assert entry["source_commit"] == step["source"] and entry["correction_commit"] == step["correction"]
    assert entry["files"] == [{"transform": step["transform"], "path": n, "before_blob": p[0], "after_blob": p[1]} for n,p in step["files"].items()]
    assert entry["companion_files"] == []
    review = entry["review"]
    assert review == dict(model="gpt-6.1-sol", effort="high", verdict="PASS", source_commit=step["source"], correction_commit=step["correction"], evidence=record["report"]["path"], evidence_commit=record["report"]["commit"], evidence_blob=record["report"]["blob"])
proposal_path = BASE + "proposed-final-P-S.json"
proposal = data(TARGET, proposal_path)
assert proposal["product_reference_P"] == P
pins = proposal["reviewed_activation_template"]
assert all(pins[k] == P for k in ["workflow_product_scope_trusted_ref", "fixture_final_reviewed_source", "fixture_frozen_source", "fixture_accepted_sources_addition"])
template_hashes = {path: hashlib.sha256(blob(TARGET,path)).hexdigest() for path in [template_path, proposal_path]}
for name, path in [("680-template.json",template_path),("P-S-template.json",proposal_path),("pg658.xml",BASE+"658-ci-producer-local.xml")]:
    (HERE/name).write_bytes(blob(TARGET,path))
result = dict(target=TARGET, proposed_P=P, policy=dict(paths=262,reports=24,cases=1648,all_hashes_match=True), old_bindings=retained,
              new_cases=sorted(now_ids-prior_ids), moved_new_pg_cases=pg_suite["cases"], actual_pg_pass=9, pg_negative_reports=negatives,
              unchanged_modules=unchanged, product_delta_from_P=product_delta, approved_template_sha256=template_hashes,
              exact_two_edges=record["steps"][-2:], report_publication="future real descendant publication only; identical independent report blob required",
              replay_metadata=pg_metadata, post_activation_checks="existing graph positive/13 negative + strict document gate + strict product scope; full remote CI pending")
(HERE/"audit.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
print("PASS immutable policy/PG658 negative receipts/product P/exact two-edge data-template audit")
