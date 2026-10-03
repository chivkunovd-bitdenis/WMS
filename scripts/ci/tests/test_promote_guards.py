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


if __name__ == "__main__":
    unittest.main()
