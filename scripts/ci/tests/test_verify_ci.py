"""Offline contract tests. No GitHub API, credentials or deployment access."""
import copy
import json
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlparse

from scripts.ci.verify_ci import GateError, REQUIRED_JOBS, pages, verify

SHA = "a" * 40
REPO = "owner/repo"


class Fixture:
    def __init__(self):
        self.run = dict(id=10, run_number=1, run_attempt=1, workflow_id=5,
                        path=".github/workflows/ci.yml", repository={"full_name": REPO},
                        head_repository={"full_name": REPO}, head_sha=SHA,
                        head_branch="etalon", event="push", status="completed",
                        conclusion="success", check_suite_id=7)
        self.runs = [self.run]
        self.jobs = [dict(id=i, name=name, head_sha=SHA, run_id=10,
                          status="completed", conclusion="success")
                     for i, name in enumerate(sorted(REQUIRED_JOBS), 1)]
        self.app = {"id": 15368, "slug": "github-actions"}
        self.paths = []
        self.run_reads = 0
        self.on_second_read = None

    def get(self, path):
        self.paths.append(path)
        if path.endswith("/workflows/ci.yml"):
            return dict(id=5, path=".github/workflows/ci.yml", state="active")
        if "/workflows/5/runs?" in path:
            self.run_reads += 1
            if self.run_reads == 2 and self.on_second_read:
                self.on_second_read()
            return copy.deepcopy(dict(total_count=len(self.runs), workflow_runs=self.runs))
        if "/check-suites/" in path:
            return dict(app=self.app, head_sha=SHA)
        if "/jobs?" in path:
            return copy.deepcopy(dict(total_count=len(self.jobs), jobs=self.jobs))
        raise AssertionError(path)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def verify(self):
        return verify(self.f.get, REPO, SHA)

    def test_success_checks_exact_sha_and_attempt(self):
        self.assertEqual(self.verify()["sha"], SHA)
        self.assertTrue(any("/attempts/1/jobs?" in p for p in self.f.paths))
        self.assertEqual(self.f.run_reads, 2)

    def test_baseline_is_mandatory_even_when_dependents_look_green(self):
        self.f.jobs = [job for job in self.f.jobs if job["name"] != "baseline"]
        with self.assertRaisesRegex(GateError, "baseline"):
            self.verify()

    def test_failed_baseline_with_skipped_dependents_refuses(self):
        for job in self.f.jobs:
            if job["name"] == "baseline":
                job["conclusion"] = "failure"
            elif job["name"] in {"backlog", "охрана"}:
                job["conclusion"] = "skipped"
        with self.assertRaises(GateError):
            self.verify()

    def test_ruleset_requires_baseline_to_block_skipped_dependency_chain(self):
        path = (Path(__file__).resolve().parents[3] / "docs" / "reviews" /
                "WMS-652-step9-draft" / "etalon.ruleset.disabled.json")
        rules = json.loads(path.read_text())["rules"]
        checks = next(rule for rule in rules if rule["type"] == "required_status_checks")
        names = {item["context"] for item in checks["parameters"]["required_status_checks"]}
        self.assertIn("baseline", names)
        self.assertEqual(names, REQUIRED_JOBS)

    def test_wrong_identity_never_authorizes_deploy(self):
        for field, value in [("head_sha", "b" * 40), ("event", "pull_request"),
                             ("event", "workflow_dispatch"), ("head_branch", "feature"),
                             ("workflow_id", 6), ("path", ".github/workflows/fake.yml"),
                             ("repository", {"full_name": "other/repo"}),
                             ("head_repository", {"full_name": "fork/repo"})]:
            with self.subTest(field=field, value=value):
                self.f = Fixture()
                self.f.run[field] = value
                with self.assertRaises(GateError):
                    self.verify()

    def test_newest_run_wins_even_when_old_is_green(self):
        bad = {**self.f.run, "id": 11, "run_number": 2, "conclusion": "failure"}
        self.f.runs = [bad, self.f.run]
        with self.assertRaises(GateError):
            self.verify()

    def test_missing_or_duplicate_required_job_fails(self):
        for duplicate in [False, True]:
            with self.subTest(duplicate=duplicate):
                self.f = Fixture()
                if duplicate:
                    self.f.jobs.append({**self.f.jobs[0], "id": 99})
                else:
                    self.f.jobs.pop()
                with self.assertRaises(GateError):
                    self.verify()

    def test_every_non_success_job_fails(self):
        for conclusion in ["failure", "skipped", "neutral", "cancelled", "timed_out", None]:
            with self.subTest(conclusion=conclusion):
                self.f = Fixture()
                self.f.jobs[0]["conclusion"] = conclusion
                with self.assertRaises(GateError):
                    self.verify()

    def test_job_other_sha_or_run_fails(self):
        for field, value in [("head_sha", "b" * 40), ("run_id", 123), ("status", "queued")]:
            with self.subTest(field=field):
                self.f = Fixture()
                self.f.jobs[0][field] = value
                with self.assertRaises(GateError):
                    self.verify()

    def test_other_app_fails(self):
        self.f.app["id"] = 999
        with self.assertRaises(GateError):
            self.verify()

    def test_pending_run_has_separate_outcome(self):
        self.f.run["status"] = "in_progress"
        with self.assertRaises(GateError) as err:
            self.verify()
        self.assertEqual(err.exception.code, 4)

    def test_partial_rerun_does_not_borrow_jobs_from_previous_attempt(self):
        self.f.run["run_attempt"] = 2
        self.f.jobs.pop()
        with self.assertRaises(GateError):
            self.verify()
        self.assertTrue(any("/attempts/2/jobs?" in p for p in self.f.paths))

    def test_rerun_during_read_invalidates_success(self):
        self.f.on_second_read = lambda: self.f.run.update(run_attempt=2)
        with self.assertRaises(GateError):
            self.verify()

    def test_malformed_sha_fails_before_api(self):
        with self.assertRaises(GateError):
            verify(self.f.get, REPO, "etalon")
        self.assertEqual(self.f.paths, [])

    def test_pagination_reads_more_than_one_page(self):
        requests = []

        def get(path):
            page = int(parse_qs(urlparse(path).query)["page"][0])
            requests.append(page)
            return {"total_count": 101, "jobs": [{"id": i} for i in
                    (range(100) if page == 1 else [100])]}

        self.assertEqual(len(pages(get, "jobs", "jobs")), 101)
        self.assertEqual(requests, [1, 2])

    def test_truncated_or_unstable_pagination_refuses(self):
        for data in [{"total_count": 1000, "workflow_runs": []},
                     {"total_count": 1, "workflow_runs": []}]:
            with self.subTest(data=data), self.assertRaises(GateError):
                pages(lambda _: data, "runs", "workflow_runs")

    def test_duplicate_page_refuses(self):
        def get(path):
            return {"total_count": 2, "jobs": [{"id": 1}]}

        with self.assertRaises(GateError):
            pages(get, "jobs", "jobs")


if __name__ == "__main__":
    unittest.main()
