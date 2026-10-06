"""Reproduce the immutable 6da0 scope check, without importing dirty code.

Run from any checkout containing the reviewed Git object. Exit 0 means the
reported FAIL was reproduced, not that the candidate passed review.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
TARGET = "6da0eb63b143d71d789c25a20ee04e3c49cbf14b"
PATH = "backend/tests/test_wms684_586_scope_contract.py"
raw = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{TARGET}:{PATH}"])
results = []
with tempfile.TemporaryDirectory(dir=HERE) as directory:
    directory = Path(directory)
    module_path = directory / "immutable_scope.py"
    module_path.write_bytes(raw)
    spec = importlib.util.spec_from_file_location("immutable_scope", module_path)
    scope = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scope)
    for number, subject in enumerate([
        "WMS-684 WMS-586: forbidden model",
        "WMS-652 WMS-684 WMS-586: forbidden model",
        "WMS-684 WMS-586 forbidden model",
    ]):
        root = directory / str(number)
        root.mkdir()
        scope._git("init", "--quiet", root=root)
        scope._git("config", "user.name", "Independent scope reviewer", root=root)
        scope._git("config", "user.email", "review@example.invalid", root=root)
        scope._git("config", "commit.gpgsign", "false", root=root)
        scope._write(root, "docs/requirements/WMS-586.md", "contract\n")
        contract = scope._commit(root, "WMS-684 WMS-586: контракт тестов")
        forbidden = "backend/app/models/forbidden.py"
        scope._write(root, forbidden, "new model\n")
        source = scope._commit(root, subject)
        actual = scope._git("diff", "--name-only", contract, source, root=root).splitlines()
        detected = sorted(scope.wms684_586_task_paths(root, contract))
        try:
            scope.assert_wms684_586_scope(root, contract)
            rejected, reason = False, None
        except AssertionError as exc:
            rejected, reason = True, str(exc)
        results.append(dict(subject=subject, source=source, actual_paths=actual,
                            detected_paths=detected, rejected=rejected, reason=reason))
assert results[0]["rejected"]
assert all(not row["rejected"] and row["detected_paths"] == [] for row in results[1:])
assert all(row["actual_paths"] == ["backend/app/models/forbidden.py"] for row in results)
(HERE / "scope-canaries.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
print("FAIL reproduced: forbidden task changes silently accepted in two task-title forms")
