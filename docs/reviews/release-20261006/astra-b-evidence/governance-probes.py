"""Read-only candidate audit; synthetic Git repositories only, no application writes."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
CANDIDATE = Path('/Users/deniscivkunov/Projects/WMS/.worktrees/priority-five-release-20261006')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, CANDIDATE / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


promote = load('promote', 'scripts/ci/promote_guards.py')
checker = load('checker', 'scripts/ci/check_task_documents.py')
scope = load('scope', 'backend/tests/test_wms653_scope_contract.py')
out = {}
for number in [653, 657, 659, 660, 667, 669, 670, 672, 673]:
    rows = promote.permanent_references((CANDIDATE / f'docs/requirements/WMS-{number}.md').read_text().splitlines())
    failures = []
    for line, column, path, name in rows:
        if name not in (CANDIDATE / path).read_text():
            failures.append({'line': line + 1, 'reason': 'whole multi-reference cell treated as one test name', 'path': str(path)})
            continue
        try:
            promote.guard_target(path)
        except ValueError as error:
            failures.append({'line': line + 1, 'reason': str(error), 'path': str(path)})
    out[f'promotion_{number}'] = {'references': len(rows), 'preflight_failures': failures}


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, stderr=subprocess.DEVNULL).strip()


with tempfile.TemporaryDirectory(prefix='wms-audit-b-') as tmp:
    root = Path(tmp)
    git(root, 'init', '-q', '-b', 'audit')
    git(root, 'config', 'user.name', 'Isolated audit')
    git(root, 'config', 'user.email', 'audit@example.invalid')
    (root / 'docs/requirements').mkdir(parents=True)
    (root / 'docs/requirements/WMS-653.md').write_text('initial\n')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'WMS-653: контракт тестов')
    contract = git(root, 'rev-parse', 'HEAD')
    path = root / 'backend/app/models/audit_forbidden.py'
    path.parent.mkdir(parents=True)
    path.write_text('new_unrequested_model = True\n')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'WMS-652 WMS-653: introduce forbidden model')
    scope.assert_wms653_scope(root, contract)
    out['scope_other_primary_task_bypass'] = {'result': 'PASS despite committed forbidden model', 'subject': 'WMS-652 WMS-653: introduce forbidden model'}
    git(root, 'commit', '--amend', '-qm', 'WMS-653: introduce forbidden model')
    try:
        scope.assert_wms653_scope(root, contract)
    except AssertionError as error:
        out['scope_negative_control'] = {'result': 'REJECTED with WMS-653 primary subject', 'message': str(error)}

with tempfile.TemporaryDirectory(prefix='wms-audit-b-') as tmp:
    root = Path(tmp)
    git(root, 'init', '-q', '-b', 'audit')
    git(root, 'config', 'user.name', 'Isolated audit')
    git(root, 'config', 'user.email', 'audit@example.invalid')
    (root / 'initial').write_text('initial\n')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'base')
    base = git(root, 'rev-parse', 'HEAD')
    path = root / 'test_contract.py'
    path.write_text('def test_expected():\n    assert False\n')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'WMS-673: контракт тестов — RED цвета, PDF-проверка отложена')
    path.write_text('def test_expected():\n    assert True\n')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'WMS-673: implementation')
    out['contract_subject_suffix_bypass'] = checker.contract_change_errors(root, base)
    git(root, 'checkout', '-q', '-b', 'exact-subject-control', base)
    path.write_text('def test_expected():\n    assert False\n')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'WMS-673: контракт тестов')
    path.write_text('def test_expected():\n    assert True\n')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'WMS-673: implementation')
    out['contract_exact_subject_negative_control'] = checker.contract_change_errors(root, base)
    path.write_text('# test_only_in_comment\n')
    out['reference_comment_only'] = checker.test_reference_errors(root, 'test_contract.py::test_only_in_comment')

print(json.dumps(out, indent=2, ensure_ascii=False))
