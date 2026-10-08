"""Infrastructure checks for retained regression coverage, separate from business tests."""

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_regression_guards.py"
spec = importlib.util.spec_from_file_location("guards", SCRIPT)
guards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guards)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        (self.root / "baseline.txt").write_text("baseline")
        self.initial = self.commit()
        for directory in guards.ROOTS:
            target = self.root / directory / "README.md"
            target.parent.mkdir(parents=True)
            target.write_text("Bootstrap: no approved business tests\n")
        (self.root / "guards").mkdir()
        self.manifest = {"version": 1, "state": "bootstrap", "files": {}}
        self.save_manifest()
        checker = self.root / "scripts/ci/check_regression_guards.py"
        checker.parent.mkdir(parents=True)
        checker.write_bytes(SCRIPT.read_bytes())
        self.base = self.commit()

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.root), *args], stderr=subprocess.PIPE
        ).decode().strip()

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def save_manifest(self):
        self.manifest["files"] = {
            p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for directory in guards.ROOTS
            for p in (self.root / directory).rglob("*")
            if p.is_file() and not p.is_symlink()
        }
        (self.root / guards.MANIFEST).write_text(json.dumps(self.manifest))

    def active_base(self):
        test = self.root / guards.ROOTS[0] / "test_stock_guard.py"
        test.write_text("def test_stock_contract():\n    assert True\n")
        self.manifest["state"] = "active"
        self.save_manifest()
        self.base = self.commit()
        return test

    def test_unchanged_bootstrap_has_zero_business_guards(self):
        self.assertEqual(guards.verify(self.root, self.base),
                         {"backend_tests": 0, "frontend_tests": 0})

    def test_source_fixture_correction_and_stale_legacy_hash_pass_without_pin(self):
        test = self.active_base()
        test.write_text("def test_stock_contract():\n    assert True # corrected fixture\n")
        self.assertEqual(guards.verify(self.root, self.base),
                         {"backend_tests": 1, "frontend_tests": 0})

    def test_renaming_and_adding_a_test_need_no_manifest_refresh(self):
        test = self.active_base()
        test.rename(test.with_name("test_stock_guard_renamed.py"))
        (test.parent / "test_additional.py").write_text(
            "def test_additional(): assert True\n")
        self.assertEqual(guards.verify(self.root, self.base),
                         {"backend_tests": 2, "frontend_tests": 0})

    def test_removing_mandatory_test_file_fails(self):
        self.active_base().unlink()
        with self.assertRaisesRegex(ValueError, "test-file count decreased"):
            guards.verify(self.root, self.base)

    def test_backend_guard_cannot_import_unprotected_test_module(self):
        guard = self.root / guards.ROOTS[0] / "test_stock_guard.py"
        self.active_base()
        guard.write_text("from tests.test_unprotected_seed import seed\n")
        with self.assertRaisesRegex(ValueError, r"tests\.test_unprotected_seed"):
            guards.verify(self.root, self.base)

    def test_backend_guard_allows_protected_and_external_imports(self):
        guard = self.active_base()
        guard.write_text("from app.services.stock import reserve\n"
                         "from tests.guards.stock_helpers import seed\n"
                         "import pytest\n")
        self.assertEqual(guards.verify(self.root, self.base),
                         {"backend_tests": 1, "frontend_tests": 0})

    def test_missing_baseline_requires_explicit_bootstrap(self):
        with self.assertRaisesRegex(ValueError, "only explicit bootstrap"):
            guards.verify(self.root, self.initial)
        self.assertEqual(sum(guards.verify(self.root, self.initial, True).values()), 0)

    def test_first_introduction_may_add_active_business_tests(self):
        test = self.root / guards.ROOTS[0] / "test_first_guard.py"
        test.write_text("def test_guard():\n    assert True\n")
        self.manifest["state"] = "active"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "only explicit bootstrap"):
            guards.verify(self.root, self.initial)
        self.assertEqual(guards.verify(self.root, self.initial, True),
                         {"backend_tests": 1, "frontend_tests": 0})

    def test_bootstrap_cannot_introduce_business_tests_or_helpers(self):
        (self.root / guards.ROOTS[0] / "conftest.py").write_text("raise RuntimeError()")
        with self.assertRaisesRegex(ValueError, "only infrastructure README"):
            guards.verify(self.root, self.initial, True)

    def test_symlink_is_rejected(self):
        target = self.root / guards.ROOTS[0] / "README.md"
        target.unlink()
        target.symlink_to(self.root / "baseline.txt")
        with self.assertRaisesRegex(ValueError, "Symlinks are not protected files"):
            guards.verify(self.root, self.base)

    def test_trusted_checker_cannot_be_bypassed_by_disabling_candidate_script(self):
        self.active_base().unlink()
        checker_path = "scripts/ci/check_regression_guards.py"
        (self.root / checker_path).write_text("print('pretend success')")
        trusted_script = self.root / "trusted_checker.py"
        trusted_script.write_text(self.git("show", f"{self.base}:{checker_path}"))
        result = subprocess.run(
            [sys.executable, str(trusted_script), "--root", str(self.root),
             "--base", self.base], capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("test-file count decreased", result.stderr)

    def test_invalid_manifest_path_is_rejected(self):
        self.manifest["files"]["backend/tests/guards/../../escape"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "Invalid protected path"):
            guards.parse_manifest(json.dumps(self.manifest).encode())

    def test_active_guard_counts_are_separate(self):
        self.active_base()
        frontend = self.root / guards.ROOTS[1] / "fixture.test.ts"
        frontend.write_text("// frontend contract\n")
        self.assertEqual(guards.verify(self.root, self.base),
                         {"backend_tests": 1, "frontend_tests": 1})


if __name__ == "__main__":
    unittest.main()
