"""Execute the actual migrated assertion against an untracked old-ref workflow copy."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

root = Path(__file__).resolve().parents[4]
evidence = Path(__file__).resolve().parent
workflow = root / '.github/workflows/ci.yml'
test_file = root / 'scripts/ci/tests/test_ci_release_additions.py'
old = 'd61805978b3e7878d1056c99b4e6e0823edf49a5'
accepted = '25ebc6fe13384a55cf1f2b7e5e4054bb862d002d'
command = 'python scripts/ci/product_scope.py --root . --trusted-ref '
original = workflow.read_bytes()
test_original = test_file.read_bytes()
assert original.count((command + accepted).encode()) == 1
counterexample = original.replace((command + accepted).encode(), (command + old).encode(), 1)
spec = importlib.util.spec_from_file_location('actual_release_contract', test_file)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
case = 'test_actual_candidate_product_scope_uses_fixed_independently_reviewed_reference'
with tempfile.TemporaryDirectory(prefix='.workflow-copy-', dir=evidence) as directory:
    copy = Path(directory) / '.github/workflows/ci.yml'
    copy.parent.mkdir(parents=True)
    copy.write_bytes(counterexample)
    module.ROOT = Path(directory)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.TestSuite([module.ReleaseCommandContracts(case)]))
    raw = stream.getvalue()
    (evidence / 'old-reference-counterexample.log').write_text(raw)
    assert result.testsRun == 1 and len(result.failures) == 1
    assert not result.errors and not result.skipped
    assert command + accepted in result.failures[0][1] and 'not found in' in result.failures[0][1]
assert workflow.read_bytes() == original and test_file.read_bytes() == test_original
(evidence / 'negative-control.json').write_text(json.dumps({
    'case': 'scripts.ci.tests.test_ci_release_additions.ReleaseCommandContracts.' + case,
    'reproduce': 'python3 -B docs/evidence/WMS-652/accepted-reference-contract-migration-20261007/negative-control.py',
    'boundary': 'Only module.ROOT points to an automatically removed untracked workflow copy.',
    'mutation': command + accepted + ' -> ' + command + old,
    'original_workflow_sha256': hashlib.sha256(original).hexdigest(),
    'counterexample_workflow_sha256': hashlib.sha256(counterexample).hexdigest(),
    'tests': 1, 'pass': 0, 'fail': 1, 'errors': 0, 'skipped': 0,
    'tracked_workflow_and_test_unchanged': True, 'temporary_copy_removed': True,
}, indent=2) + '\n')
print('Actual target test refuses the old d618 reference:1 FAIL,0 errors,0 skips; tracked files unchanged.')
