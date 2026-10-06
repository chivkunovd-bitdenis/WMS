"""Execute frozen targeted tests with implementation modules loaded from exact Git SHA."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[4]
TARGET = '65049df62d2bac87932fc5349f6326caec43dea5'
sys.path.insert(0, str(ROOT))
import scripts.ci


def load(path, name):
    raw = subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{TARGET}:{path}'])
    mod = types.ModuleType(name)
    mod.__file__ = str(ROOT / path)
    mod.__spec__ = importlib.util.spec_from_file_location(name, ROOT / path)
    sys.modules[name] = mod
    exec(compile(raw, f'{TARGET}:{path}', 'exec'), mod.__dict__)
    return mod


checker = load('scripts/ci/check_task_documents.py', 'scripts.ci.check_task_documents')
scripts.ci.check_task_documents = checker
promoter = load('scripts/ci/promote_guards.py', 'review_exact_promoter')
for path in ['scripts/ci/tests/test_promote_guards.py', 'scripts/ci/test_check_task_documents.py', 'scripts/ci/process_contracts.py']:
    assert (ROOT / path).read_bytes() == subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{TARGET}:{path}'])
prom_tests = load('scripts/ci/tests/test_promote_guards.py', 'scripts.ci.tests.test_promote_guards')
prom_tests.promoter = promoter
doc_tests = load('scripts/ci/test_check_task_documents.py', 'scripts.ci.test_check_task_documents')
doc_tests.checker = checker
import pytest
print('Executed implementation and frozen tests pinned to ' + TARGET, flush=True)
raise SystemExit(pytest.main(['-q', '-n', '0', *sys.argv[1:]]))
