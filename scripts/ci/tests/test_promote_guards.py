import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "promote_guards.py"
spec = importlib.util.spec_from_file_location("promote_guards", SCRIPT)
promoter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(promoter)


class PromoteGuardsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        for directory in ("backend/tests/guards", "frontend/src/guards"):
            path = self.root / directory / "README.md"
            path.parent.mkdir(parents=True)
            path.write_text("guard\n", encoding="utf-8")
        (self.root / "guards").mkdir()
        self.write_manifest("bootstrap")

    def git(self, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(self.root), *args], text=True
        ).strip()

    def write(self, name: str, text: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def write_manifest(self, state: str) -> None:
        files = {}
        for directory in ("backend/tests/guards", "frontend/src/guards"):
            for path in (self.root / directory).rglob("*"):
                if path.is_file():
                    files[path.relative_to(self.root).as_posix()] = hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
        (self.root / "guards/MANIFEST.json").write_text(
            json.dumps({"version": 1, "state": state, "files": files}),
            encoding="utf-8",
        )

    def write_saved_process_protection(
        self,
        source: str,
        case: str,
        *,
        digest: str | None = None,
        report: str = "protected-fixture.xml",
        policy_source: str | None = None,
        suite_name: str = "protected-fixture",
    ) -> None:
        actual_digest = hashlib.sha256((self.root / source).read_bytes()).hexdigest()
        self.write(
            "guards/PROCESS_CONTRACTS.json",
            json.dumps(
                {
                    "version": 1,
                    "files": {policy_source or source: actual_digest if digest is None else digest},
                    "suites": {
                        suite_name: {
                            "report": report,
                            "format": "junit",
                            "exact": True,
                            "cases": [case],
                        }
                    },
                },
                indent=2,
            ) + "\n",
        )

    def protected_ci_shards_fixture(
        self,
        *,
        digest: str | None = None,
        case: str | None = None,
        report: str = "ci-shards.xml",
        policy_source: str | None = None,
    ) -> tuple[str, str]:
        source = "scripts/ci/tests/test_backend_shards.py"
        test_name = "test_exact_two_shards_merge_all_cases_and_receipt_identity"
        actual_case = (
            "scripts.ci.tests.test_backend_shards.BackendShardContracts::"
            + test_name
        )
        self.write(
            source,
            "\n".join(
                (
                    "class BackendShardContracts:",
                    f"    def {test_name}(self):",
                    "        pass",
                    "",
                )
            ),
        )
        self.write_saved_process_protection(
            source,
            actual_case if case is None else case,
            digest=digest,
            report=report,
            policy_source=policy_source,
            suite_name="ci-shards",
        )
        self.write_manifest("active")
        self.write(
            "docs/requirements/WMS-652.md",
            f"""| Проверка | Класс | Тест | Вердикт |
| --- | --- | --- | --- |
| C393 | навсегда | {source}::{test_name} | принято |
""",
        )
        self.git("add", ".")
        self.git("commit", "-qm", "WMS-652 protected ci-shards fixture")
        return source, test_name

    def wms654_expanded_cases(self, owner: str) -> list[str]:
        catalog = [
            f"{owner}::WMS-654 actual CatalogSection contract "
            f"C6 independent coordinates sides={sides} tiers={tiers}"
            for sides, tiers in (("false", "false"), ("true", "false"),
                                 ("false", "true"), ("true", "true"))
        ]
        map_cases = [
            f"{owner}::WMS-654 real map form openings C6 {entry} "
            f"sides={sides} tiers={tiers}"
            for entry in ("warehouse-map-create-cell", "warehouse-map-create-first-cell")
            for sides, tiers in (("false", "false"), ("true", "false"),
                                 ("false", "true"), ("true", "true"))
        ]
        return [*catalog, *map_cases]

    def wms654_protected_template_fixture(
        self,
        *,
        digest: str | None = None,
        cases: list[str] | None = None,
        report: str = "frontend-all.json",
    ) -> tuple[str, str]:
        source = "frontend/src/sections/CatalogSection.wms654.test.tsx"
        owner = "src/sections/CatalogSection.wms654.test.tsx"
        templates = (
            "C6 independent coordinates sides=%s tiers=%s",
            "C6 ${entry} sides=%s tiers=%s",
        )
        self.write(source, "\n".join([f"// {template}" for template in templates]) + "\n")
        expected_digest = hashlib.sha256((self.root / source).read_bytes()).hexdigest()
        self.write(
            "guards/PROCESS_CONTRACTS.json",
            json.dumps(
                {
                    "version": 1,
                    "files": {source: expected_digest if digest is None else digest},
                    "suites": {
                        "frontend-fbs": {
                            "report": report,
                            "format": "vitest",
                            "exact": False,
                            "cases": self.wms654_expanded_cases(owner) if cases is None else cases,
                        }
                    },
                },
                indent=2,
            ) + "\n",
        )
        self.write_manifest("active")
        self.write(
            "docs/requirements/WMS-654.md",
            f"""| Проверка | Класс | Тест | Вердикт |
| --- | --- | --- | --- |
| C6 | навсегда | {source}::{templates[0]}<br>{source}::{templates[1]} | принято |
""",
        )
        self.git("add", ".")
        self.git("commit", "-qm", "WMS-654 protected template fixture")
        return source, owner

    def wms687_actual_cases(self, owner: str) -> list[str]:
        title = "selects only document products and opens the catalog FbsStockDialogContainer"
        describe = "WMS-687 shared FBS stock dialog from an inbound document"
        return [f"{owner}::{describe} {operation} {title}" for operation in ("inbound", "return")]

    def wms687_protected_each_fixture(
        self,
        *,
        digest: str | None = None,
        cases: list[str] | None = None,
        report: str = "frontend-all.json",
    ) -> tuple[str, str]:
        source = "frontend/src/screens/ff/FfInboundRequestView.wms687.dom.test.tsx"
        owner = "src/screens/ff/FfInboundRequestView.wms687.dom.test.tsx"
        template = "'%s selects only document products and opens the catalog FbsStockDialogContainer'"
        self.write(
            source,
            "\n".join(
                (
                    "describe('WMS-687 shared FBS stock dialog from an inbound document', () => {",
                    "  it.each(['inbound', 'return'] as const)(",
                    f"    {template},",
                    "    async (operationType) => { void operationType },",
                    "  )",
                    "})",
                    "",
                )
            ),
        )
        expected_digest = hashlib.sha256((self.root / source).read_bytes()).hexdigest()
        self.write(
            "guards/PROCESS_CONTRACTS.json",
            json.dumps(
                {
                    "version": 1,
                    "files": {source: expected_digest if digest is None else digest},
                    "suites": {
                        "frontend-fbs": {
                            "report": report,
                            "format": "vitest",
                            "exact": False,
                            "cases": self.wms687_actual_cases(owner) if cases is None else cases,
                        }
                    },
                },
                indent=2,
            ) + "\n",
        )
        self.write_manifest("active")
        self.write(
            "docs/requirements/WMS-687.md",
            f"""| Проверка | Класс | Тест | Вердикт |
| --- | --- | --- | --- |
| C2 | навсегда | {source}::inbound selects only document products and opens the catalog FbsStockDialogContainer<br>{source}::return selects only document products and opens the catalog FbsStockDialogContainer | принято |
""",
        )
        self.git("add", ".")
        self.git("commit", "-qm", "WMS-687 protected it.each fixture")
        return source, owner

    def fixture(self) -> None:
        self.write(
            "backend/tests/unit/test_stock.py",
            "from .helpers import value\n\ndef test_stock_saved(): assert value\n",
        )
        self.write("backend/tests/test_once.py", "def test_once(): pass\n")
        self.write("frontend/src/service.ts", "export const value = 1\n")
        self.write(
            "frontend/src/features/label.test.ts",
            'import { value } from "../service"\ntest("label stays", () => value)\n',
        )
        self.write(
            "docs/requirements/WMS-900.md",
            """# WMS-900

| Проверка | Класс | Тест | Вердикт |
| --- | --- | --- | --- |
| C1 | навсегда | backend/tests/unit/test_stock.py::test_stock_saved | принято |
| C2 | навсегда | frontend/src/features/label.test.ts::label stays | принято |
| C3 | разово | backend/tests/test_once.py::test_once | принято |
| C4 | руками | | принято |

## Заключение
Принято.
""",
        )
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")

    def test_promotes_only_permanent_tests_and_updates_references(self):
        self.fixture()
        promoted = promoter.promote(self.root, "WMS-900")

        backend = "backend/tests/guards/unit/test_stock.py"
        frontend = "frontend/src/guards/features/label.test.ts"
        self.assertEqual(promoted, [backend, frontend])
        self.assertFalse((self.root / "backend/tests/unit/test_stock.py").exists())
        self.assertFalse((self.root / "frontend/src/features/label.test.ts").exists())
        self.assertTrue((self.root / "backend/tests/test_once.py").is_file())
        self.assertIn("from tests.unit.helpers import value", (self.root / backend).read_text())
        self.assertIn('from "../../service"', (self.root / frontend).read_text())

        document = (self.root / "docs/requirements/WMS-900.md").read_text()
        self.assertIn(f"{backend}::test_stock_saved", document)
        self.assertIn(f"{frontend}::label stays", document)
        self.assertIn("backend/tests/test_once.py::test_once", document)

        manifest = json.loads((self.root / "guards/MANIFEST.json").read_text())
        self.assertEqual(manifest["state"], "active")
        self.assertIn(backend, manifest["files"])
        self.assertIn(frontend, manifest["files"])

    def test_rejects_test_outside_supported_trees(self):
        self.write("misc/test_contract.py", "def test_contract(): pass\n")
        self.write(
            "docs/requirements/WMS-901.md",
            """| Проверка | Класс | Тест | Вердикт |
| --- | --- | --- | --- |
| C1 | навсегда | misc/test_contract.py::test_contract | принято |
""",
        )
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        with self.assertRaisesRegex(ValueError, "вне поддерживаемых"):
            promoter.promote(self.root, "WMS-901")

    def test_protected_original_stays_registered_and_second_promotion_is_idempotent(self):
        source = "backend/tests/test_immutable_contract.py"
        test_name = "test_frozen_case_id"
        self.write(source, f"def {test_name}(): pass\n")
        self.write_saved_process_protection(source, f"tests.test_immutable_contract::{test_name}")
        self.write_manifest("active")
        self.write(
            "docs/requirements/WMS-902.md",
            f"""| Проверка | Класс | Тест | Вердикт |
| --- | --- | --- | --- |
| C902 | навсегда | {source}::{test_name} | принято |
""",
        )
        self.git("add", ".")
        self.git("commit", "-qm", "protected fixture")

        protected_policy = (self.root / "guards/PROCESS_CONTRACTS.json").read_bytes()
        original_document = (self.root / "docs/requirements/WMS-902.md").read_text()
        promoter.promote(self.root, "WMS-902")

        self.assertTrue((self.root / source).is_file())
        self.assertFalse((self.root / "backend/tests/guards/test_immutable_contract.py").exists())
        self.assertEqual((self.root / "guards/PROCESS_CONTRACTS.json").read_bytes(), protected_policy)
        self.assertEqual((self.root / "docs/requirements/WMS-902.md").read_text(), original_document)
        self.assertEqual(self.git("status", "--porcelain"), "")

        promoter.promote(self.root, "WMS-902")
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_protected_ci_shards_junit_uses_the_full_scripts_module_name(self):
        source, _ = self.protected_ci_shards_fixture()
        original_document = (self.root / "docs/requirements/WMS-652.md").read_text()

        promoter.promote(self.root, "WMS-652")

        self.assertTrue((self.root / source).is_file())
        self.assertEqual(
            self.git("status", "--porcelain"),
            "",
        )
        self.assertEqual((self.root / "docs/requirements/WMS-652.md").read_text(), original_document)

    def test_protected_ci_shards_junit_rejects_changed_source_hash(self):
        source, _ = self.protected_ci_shards_fixture(digest="0" * 64)

        with self.assertRaisesRegex(ValueError, "Изменён защищённый original тест"):
            promoter.promote(self.root, "WMS-652")
        self.assertTrue((self.root / source).is_file())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_protected_ci_shards_junit_rejects_a_different_policy_source_path(self):
        source, _ = self.protected_ci_shards_fixture(
            policy_source="scripts/ci/tests/test_other_backend_shards.py"
        )

        with self.assertRaisesRegex(ValueError, "вне поддерживаемых"):
            promoter.promote(self.root, "WMS-652")
        self.assertTrue((self.root / source).is_file())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_protected_ci_shards_junit_rejects_wrong_report(self):
        source, _ = self.protected_ci_shards_fixture(report="other-ci-shards.xml")

        with self.assertRaisesRegex(ValueError, "обязательного case/report"):
            promoter.promote(self.root, "WMS-652")
        self.assertTrue((self.root / source).is_file())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_protected_ci_shards_junit_rejects_missing_exact_case(self):
        source, _ = self.protected_ci_shards_fixture(
            case=(
                "scripts.ci.tests.test_backend_shards.BackendShardContracts::"
                "test_some_other_backend_shard_contract"
            )
        )

        with self.assertRaisesRegex(ValueError, "обязательного case/report"):
            promoter.promote(self.root, "WMS-652")
        self.assertTrue((self.root / source).is_file())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_parses_every_br_and_semicolon_separated_permanent_reference(self):
        source = "backend/tests/test_multiple_immutable_cases.py"
        self.write(
            source,
            "def test_alpha(): pass\ndef test_beta(): pass\ndef test_gamma(): pass\n",
        )
        self.write(
            "docs/requirements/WMS-903.md",
            f"""| Проверка | Класс | Тест | Вердикт |
| --- | --- | --- | --- |
| C903 | навсегда | `{source}::test_alpha`<br>`{source}::test_beta`; `{source}::test_gamma` | принято |
""",
        )
        self.git("add", ".")
        self.git("commit", "-qm", "multiple references fixture")

        references = promoter.permanent_references(
            (self.root / "docs/requirements/WMS-903.md").read_text().splitlines()
        )

        self.assertEqual(
            [(str(path), name) for _, _, path, name in references],
            [
                (source, "test_alpha"),
                (source, "test_beta"),
                (source, "test_gamma"),
            ],
        )
        promoter.promote(self.root, "WMS-903")

        target = "backend/tests/guards/test_multiple_immutable_cases.py"
        self.assertFalse((self.root / source).exists())
        document = (self.root / "docs/requirements/WMS-903.md").read_text()
        for test_name in ("test_alpha", "test_beta", "test_gamma"):
            self.assertIn(f"{target}::{test_name}", document)

    def test_empty_active_permanent_reference_still_refuses_promotion(self):
        self.write(
            "docs/requirements/WMS-904.md",
            """| Проверка | Класс | Тест | Вердикт |
| --- | --- | --- | --- |
| C904 | навсегда | | принято |
""",
        )
        self.git("add", ".")
        self.git("commit", "-qm", "empty reference fixture")

        with self.assertRaisesRegex(ValueError, "Некорректная ссылка на тест"):
            promoter.promote(self.root, "WMS-904")

    def test_protected_wms654_templates_bind_every_real_case_in_fixed_vitest_report(self):
        source, _ = self.wms654_protected_template_fixture()
        original_document = (self.root / "docs/requirements/WMS-654.md").read_text()

        promoter.promote(self.root, "WMS-654")

        self.assertTrue((self.root / source).is_file())
        self.assertFalse((self.root / "frontend/src/guards/sections/CatalogSection.wms654.test.tsx").exists())
        self.assertEqual((self.root / "docs/requirements/WMS-654.md").read_text(), original_document)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_protected_wms654_templates_reject_unbound_expanded_case(self):
        owner = "src/sections/CatalogSection.wms654.test.tsx"
        cases = self.wms654_expanded_cases(owner)[:-1]
        self.wms654_protected_template_fixture(cases=cases)

        with self.assertRaisesRegex(ValueError, "обязательного case/report"):
            promoter.promote(self.root, "WMS-654")

    def test_protected_wms654_templates_reject_wrong_expanded_case_or_source(self):
        owner = "src/sections/CatalogSection.wms654.test.tsx"
        cases = self.wms654_expanded_cases(owner)
        cases[-1] = cases[-1].replace("tiers=true", "tiers=wrong")
        self.wms654_protected_template_fixture(cases=cases)

        with self.assertRaisesRegex(ValueError, "обязательного case/report"):
            promoter.promote(self.root, "WMS-654")

    def test_protected_wms654_templates_reject_wrong_case_file(self):
        wrong_owner = "src/sections/OtherCatalogSection.wms654.test.tsx"
        self.wms654_protected_template_fixture(cases=self.wms654_expanded_cases(wrong_owner))

        with self.assertRaisesRegex(ValueError, "обязательного case/report"):
            promoter.promote(self.root, "WMS-654")

    def test_protected_wms654_templates_reject_wrong_vitest_report(self):
        self.wms654_protected_template_fixture(report="other-vitest-report.json")

        with self.assertRaisesRegex(ValueError, "обязательного case/report"):
            promoter.promote(self.root, "WMS-654")

    def test_protected_wms654_templates_reject_changed_source_hash(self):
        self.wms654_protected_template_fixture(digest="0" * 64)

        with self.assertRaisesRegex(ValueError, "Изменён защищённый original тест"):
            promoter.promote(self.root, "WMS-654")

    def test_protected_wms687_each_uses_the_two_exact_executed_case_ids(self):
        source, _ = self.wms687_protected_each_fixture()
        original_document = (self.root / "docs/requirements/WMS-687.md").read_text()

        promoter.promote(self.root, "WMS-687")

        self.assertTrue((self.root / source).is_file())
        self.assertFalse(
            (self.root / "frontend/src/guards/screens/ff/FfInboundRequestView.wms687.dom.test.tsx").exists()
        )
        self.assertEqual((self.root / "docs/requirements/WMS-687.md").read_text(), original_document)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_protected_wms687_each_rejects_missing_exact_case(self):
        owner = "src/screens/ff/FfInboundRequestView.wms687.dom.test.tsx"
        self.wms687_protected_each_fixture(cases=self.wms687_actual_cases(owner)[:-1])

        with self.assertRaisesRegex(ValueError, "обязательного case/report"):
            promoter.promote(self.root, "WMS-687")

    def test_protected_wms687_each_rejects_wrong_report(self):
        self.wms687_protected_each_fixture(report="other-vitest-report.json")

        with self.assertRaisesRegex(ValueError, "обязательного case/report"):
            promoter.promote(self.root, "WMS-687")

    def test_protected_wms687_each_rejects_changed_source_hash(self):
        self.wms687_protected_each_fixture(digest="0" * 64)

        with self.assertRaisesRegex(ValueError, "Изменён защищённый original тест"):
            promoter.promote(self.root, "WMS-687")

    def test_protected_wms687_each_rejects_arbitrary_describe_group_prefix(self):
        owner = "src/screens/ff/FfInboundRequestView.wms687.dom.test.tsx"
        cases = self.wms687_actual_cases(owner)
        cases[0] = cases[0].replace(
            "WMS-687 shared FBS stock dialog from an inbound document",
            "arbitrary describe group",
        )
        self.wms687_protected_each_fixture(cases=cases)

        with self.assertRaisesRegex(ValueError, "обязательного case/report"):
            promoter.promote(self.root, "WMS-687")

    def test_unprotected_legacy_each_reference_still_requires_a_literal_source_name(self):
        source = "frontend/src/sections/legacy.each.test.tsx"
        self.write(source, "it.each(['inbound'] as const)('%s keeps a legacy contract', () => {})\n")
        self.write(
            "docs/requirements/WMS-688.md",
            f"""| Проверка | Класс | Тест | Вердикт |
| --- | --- | --- | --- |
| C1 | навсегда | {source}::inbound keeps a legacy contract | принято |
""",
        )
        self.git("add", ".")
        self.git("commit", "-qm", "unprotected legacy fixture")

        with self.assertRaisesRegex(ValueError, "не найдено имя теста inbound keeps a legacy contract"):
            promoter.promote(self.root, "WMS-688")

    def protected_original_fixture(self, task: str) -> str:
        source = "backend/tests/test_immutable_contract.py"
        test_name = "test_frozen_case_id"
        self.write(source, f"def {test_name}(): pass\n")
        self.write_saved_process_protection(source, f"tests.test_immutable_contract::{test_name}")
        self.write_manifest("active")
        self.write(
            f"docs/requirements/{task}.md",
            f"""| Проверка | Класс | Тест | Вердикт |
| --- | --- | --- | --- |
| C1 | навсегда | {source}::{test_name} | принято |
""",
        )
        self.git("add", ".")
        self.git("commit", "-qm", "protected fixture")
        return source

    def assert_protected_original_was_not_moved(self, source: str, before: str) -> None:
        self.assertTrue((self.root / source).is_file())
        self.assertFalse((self.root / "backend/tests/guards/test_immutable_contract.py").exists())
        self.assertEqual(self.git("status", "--porcelain"), before)

    def test_missing_saved_protected_policy_refuses_legacy_move(self):
        source = self.protected_original_fixture("WMS-905")
        policy = self.root / "guards/PROCESS_CONTRACTS.json"
        policy.unlink()
        before = self.git("status", "--porcelain")

        with self.assertRaisesRegex(ValueError, "Process protection"):
            promoter.promote(self.root, "WMS-905")

        self.assert_protected_original_was_not_moved(source, before)

    def test_dangling_saved_protected_policy_refuses_legacy_move(self):
        source = self.protected_original_fixture("WMS-906")
        policy = self.root / "guards/PROCESS_CONTRACTS.json"
        policy.unlink()
        policy.symlink_to("missing-PROCESS_CONTRACTS.json")
        self.assertTrue(policy.is_symlink())
        self.assertFalse(policy.exists())
        before = self.git("status", "--porcelain")

        with self.assertRaisesRegex(ValueError, "Process protection"):
            promoter.promote(self.root, "WMS-906")

        self.assert_protected_original_was_not_moved(source, before)


if __name__ == "__main__":
    unittest.main()
