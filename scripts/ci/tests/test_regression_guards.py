"""Infrastructure mutation checks; deliberately not approved business guards."""

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
        return (
            subprocess.check_output(
                ["git", "-C", str(self.root), *args], stderr=subprocess.PIPE
            )
            .decode()
            .strip()
        )

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def save_manifest(self):
        self.manifest["files"] = {
            p.relative_to(self.root).as_posix(): hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
            for directory in guards.ROOTS
            for p in (self.root / directory).rglob("*")
            if p.is_file()
        }
        (self.root / guards.MANIFEST).write_text(json.dumps(self.manifest))

    def test_unchanged_bootstrap_has_zero_business_guards(self):
        self.assertEqual(
            guards.verify(self.root, self.base),
            {"backend_tests": 0, "frontend_tests": 0},
        )

    def test_changed_file_fails(self):
        (self.root / guards.ROOTS[0] / "README.md").write_text("changed")
        with self.assertRaisesRegex(
            ValueError, "изменён защищённый тест .* — нужно решение владельца"
        ):
            guards.verify(self.root, self.base)

    def test_deleted_file_fails(self):
        (self.root / guards.ROOTS[0] / "README.md").unlink()
        with self.assertRaisesRegex(
            ValueError, "изменён защищённый тест .* — нужно решение владельца"
        ):
            guards.verify(self.root, self.base)

    def test_added_file_fails(self):
        (self.root / guards.ROOTS[0] / "test_new.py").write_text("assert True")
        with self.assertRaisesRegex(ValueError, "Protected files changed"):
            guards.verify(self.root, self.base)

    def test_added_file_registered_in_manifest_is_allowed(self):
        (self.root / guards.ROOTS[0] / "test_new.py").write_text(
            "def test_new(): assert True"
        )
        self.manifest["state"] = "active"
        self.save_manifest()
        self.assertEqual(
            guards.verify(self.root, self.base),
            {"backend_tests": 1, "frontend_tests": 0},
        )

    def test_simultaneous_file_and_hash_change_fails(self):
        (self.root / guards.ROOTS[0] / "README.md").write_text("changed")
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "изменён защищённый тест"):
            guards.verify(self.root, self.base)

    def test_manifest_only_change_fails(self):
        self.manifest["state"] = "active"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "must contain business tests"):
            guards.verify(self.root, self.base)

    def test_missing_baseline_requires_explicit_bootstrap(self):
        with self.assertRaisesRegex(ValueError, "explicit empty bootstrap"):
            guards.verify(self.root, self.initial)
        self.assertEqual(sum(guards.verify(self.root, self.initial, True).values()), 0)

    def test_bootstrap_cannot_introduce_business_tests_or_helpers(self):
        (self.root / guards.ROOTS[0] / "conftest.py").write_text("raise RuntimeError()")
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "only infrastructure README"):
            guards.verify(self.root, self.initial, True)

    def test_symlink_is_rejected(self):
        target = self.root / guards.ROOTS[0] / "README.md"
        target.unlink()
        target.symlink_to(self.root / "baseline.txt")
        with self.assertRaisesRegex(ValueError, "изменён защищённый тест"):
            guards.verify(self.root, self.base)

    def test_baseline_checker_rejects_mutation_when_candidate_checker_is_disabled(self):
        checker_path = "scripts/ci/check_regression_guards.py"
        (self.root / checker_path).write_text("print('pretend success')")
        (self.root / guards.ROOTS[0] / "README.md").write_text("changed")
        trusted_script = self.root / "trusted_checker.py"
        trusted_script.write_text(self.git("show", f"{self.base}:{checker_path}"))
        result = subprocess.run(
            [
                sys.executable,
                str(trusted_script),
                "--root",
                str(self.root),
                "--base",
                self.base,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("изменён защищённый тест", result.stderr)

    def test_invalid_manifest_path_is_rejected(self):
        self.manifest["files"]["backend/tests/guards/../../escape"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "Invalid protected path"):
            guards.parse_manifest(json.dumps(self.manifest).encode())

    def test_corrupt_trusted_manifest_fails(self):
        (self.root / guards.ROOTS[0] / "README.md").write_text(
            "changed without updating hash"
        )
        corrupt = self.commit()
        with self.assertRaisesRegex(ValueError, "Trusted BASE hash mismatch"):
            guards.verify(self.root, corrupt)

    def test_active_guard_counts_are_separate(self):
        (self.root / guards.ROOTS[0] / "test_fixture.py").write_text(
            "def test_example(): assert True"
        )
        (self.root / guards.ROOTS[1] / "fixture.test.ts").write_text("// fixture")
        self.manifest["state"] = "active"
        self.save_manifest()
        active = self.commit()
        self.assertEqual(
            guards.verify(self.root, active), {"backend_tests": 1, "frontend_tests": 1}
        )


if __name__ == "__main__":
    unittest.main()
