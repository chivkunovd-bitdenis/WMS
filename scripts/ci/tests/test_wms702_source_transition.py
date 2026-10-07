"""WMS-702 bounded SOURCE transition contract, recorded before metadata changes.

EXPECTED_PRODUCT is a proposed exact reference until the separate composition
review passes. These assertions do not grant acceptance or main-merge authority.
The existing 51 product_scope cases and test_reviewed_process_upgrade continue
to cover neighbor rejection and exact trusted-main BASE/SOURCE selection; this
file checks only their concrete WMS-702 binding and additive execution receipt.
The eventual S702 cannot name itself before its commit exists: its exact main
pin must be verified separately after independent S702 review, before owner
approval. HEAD, GITHUB_SHA and environment inputs never select these constants.
"""

import copy
import hashlib
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.ci import process_contracts

ROOT = Path(__file__).resolve().parents[3]
ACCEPTED_SOURCE = "39d1afdc8f37cdfda3c7768804ccccc3c9ad4e6e"
EXPECTED_PRODUCT = "86f450ad54745a5a2f2d77b3facdac8b778ac442"
PRODUCTION = "212f19d548496fef7baf75c83204b771e304281b"
LABEL_BLOB = "e6314c4c4f5126f5f951a342707a1e77db831ea8"
BINDING_PATH = "scripts/ci/tests/fixtures/wms652_source_binding_transition.json"
WORKFLOW_PATH = ".github/workflows/ci.yml"
RUNNER_PATH = "scripts/ci/run_release_print.sh"
GEOMETRY_PATH = "frontend/src/utils/wms702ProductLabelGeometry.test.ts"
UNIT_PATH = "frontend/src/utils/printProductThermalLabel.test.ts"
CASE = (GEOMETRY_PATH.removeprefix("frontend/") + "::"
        "WMS-702 real ordinary WB label geometry "
        "keeps every selected field visible, separated and readable in every stock size and both print documents")
RECEIPT = {"report": "print/702.json", "format": "vitest", "exact": True, "cases": [CASE]}
DERIVATIVES = {WORKFLOW_PATH, BINDING_PATH, RUNNER_PATH}


def git_bytes(ref, path):
    return subprocess.check_output(["git", "-C", str(ROOT), "show", f"{ref}:{path}"],
                                   stderr=subprocess.PIPE)


def dictionaries(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from dictionaries(child)
    elif isinstance(value, list):
        for child in value:
            yield from dictionaries(child)


class Wms702SourceTransitionTests(unittest.TestCase):
    def policy(self):
        return json.loads((ROOT / process_contracts.POLICY_PATH).read_bytes())

    def receipt_policy(self):
        policy = self.policy()
        suites = {name: suite for name, suite in policy["suites"].items()
                  if suite["report"] == RECEIPT["report"]}
        self.assertEqual(len(suites), 1, "WMS-702 full geometry execution receipt is not protected")
        self.assertEqual(next(iter(suites.values())), RECEIPT)
        return {"version": 1, "files": {}, "suites": suites}

    def test_exact_product_reference_and_prior_accepted_history_are_bound_together(self):
        raw = (ROOT / WORKFLOW_PATH).read_text()
        refs = re.findall(r"python scripts/ci/product_scope.py --root \. --trusted-ref ([^\s]+)", raw)
        self.assertEqual(refs, [EXPECTED_PRODUCT], "WMS-702 needs the exact independently reviewed product reference")
        binding = json.loads((ROOT / BINDING_PATH).read_bytes())
        self.assertEqual(binding["status"], "independently-accepted-final-freeze")
        self.assertEqual(binding["final_reviewed_source"], EXPECTED_PRODUCT)
        self.assertEqual(binding["frozen_source"], EXPECTED_PRODUCT)
        original = json.loads(git_bytes(ACCEPTED_SOURCE, BINDING_PATH))
        self.assertTrue(set(original["accepted_reviewed_sources"]).issubset(binding["accepted_reviewed_sources"]))
        self.assertIn(EXPECTED_PRODUCT, binding["accepted_reviewed_sources"])
        self.assertIn(original, list(dictionaries(binding)), "Keep the complete previous accepted binding and its history")
        acceptance = binding["independent_acceptance_record"]
        self.assertRegex(acceptance, r"^[0-9a-f]{40}$")
        self.assertNotIn(acceptance, {EXPECTED_PRODUCT, ACCEPTED_SOURCE, original["independent_acceptance_record"]})
        self.assertEqual(binding["independent_review_verdict"], "PASS")
        subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{acceptance}^{{commit}}"], check=True, capture_output=True)

    def test_production_and_accepted_source_ancestry_and_reviewed_label_are_preserved(self):
        for ref in (ACCEPTED_SOURCE, PRODUCTION):
            subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", ref, EXPECTED_PRODUCT],
                           check=True, capture_output=True)
        actual = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse",
                                          f"{EXPECTED_PRODUCT}:frontend/src/utils/printProductThermalLabel.ts"], text=True).strip()
        self.assertEqual(actual, LABEL_BLOB)

    def test_all_previous_protected_paths_cases_and_semantics_survive_bounded_derivatives(self):
        previous = json.loads(git_bytes(ACCEPTED_SOURCE, process_contracts.POLICY_PATH))
        current = self.policy()
        process_contracts.validate_policy(current)
        process_contracts.retained_contracts(previous, current, same_digests=False)
        changed = {path for path, digest in previous["files"].items() if current["files"][path] != digest}
        self.assertEqual(changed, DERIVATIVES, "Only reviewed workflow, binding and WMS-702 print-hook derivatives change")
        for path in DERIVATIVES:
            self.assertEqual(current["files"][path], hashlib.sha256((ROOT / path).read_bytes()).hexdigest())
        # Old print contracts remain exact, including report locations and case order.
        for name, suite in previous["suites"].items():
            if name.startswith("print-"):
                self.assertEqual(current["suites"][name], suite)

    def test_702_test_bytes_and_full_geometry_receipt_are_protected(self):
        self.receipt_policy()
        policy = self.policy()
        for path in (GEOMETRY_PATH, UNIT_PATH):
            expected = hashlib.sha256(git_bytes(EXPECTED_PRODUCT, path)).hexdigest()
            self.assertEqual(policy["files"].get(path), expected, f"Protect the independently reviewed WMS-702 contract: {path}")
            self.assertEqual(hashlib.sha256(git_bytes("HEAD", path)).hexdigest(), expected)
        own_path = Path(__file__).relative_to(ROOT).as_posix()
        self.assertEqual(policy["files"].get(own_path), hashlib.sha256(Path(__file__).read_bytes()).hexdigest())

    def test_full_702_producer_and_existing_print_commands_are_preserved(self):
        runner = (ROOT / RUNNER_PATH).read_bytes()
        self.assertEqual(runner, git_bytes(EXPECTED_PRODUCT, RUNNER_PATH), "Keep the reviewed complete WMS-702 producer, without a shortened matrix")
        workflow = (ROOT / WORKFLOW_PATH).read_text()
        self.assertIn("run: bash scripts/ci/run_release_print.sh", workflow)
        self.assertIn("name: release-print-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}", workflow)
        self.assertIn("path: ${{ runner.temp }}/release-print", workflow)
        self.assertIn("python -m unittest discover -s scripts/ci/tests -p 'test_*.py' -v", workflow)

    def test_required_702_report_rejects_missing_skip_failure_and_same_count_replacement(self):
        # Exercise the real existing report consumer even before its additive
        # WMS-702 registration exists; registration is asserted independently.
        policy = {"version": 1, "files": {}, "suites": {"print-702": RECEIPT}}
        report = {"success": True, "numTotalTests": 1, "numPassedTests": 1, "numPendingTests": 0,
                  "numFailedTests": 0, "testResults": [{"name": GEOMETRY_PATH.removeprefix("frontend/"),
                  "status": "passed", "assertionResults": [{"fullName": CASE.split("::", 1)[1], "status": "passed"}]}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / RECEIPT["report"]
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(report))
            process_contracts.verify_reports(policy, root)
            for mutation in ("missing", "skipped", "failed", "wrong-case", "wrong-file"):
                with self.subTest(mutation=mutation):
                    data = copy.deepcopy(report)
                    if mutation == "missing":
                        path.unlink()
                    else:
                        case = data["testResults"][0]["assertionResults"][0]
                        if mutation in {"skipped", "failed"}:
                            case["status"] = mutation
                        elif mutation == "wrong-case":
                            case["fullName"] = "unrelated single green test"
                        else:
                            data["testResults"][0]["name"] = "src/utils/unrelated.test.ts"
                        path.write_text(json.dumps(data))
                    with self.assertRaises(ValueError):
                        process_contracts.verify_reports(policy, root)


if __name__ == "__main__":
    unittest.main()
