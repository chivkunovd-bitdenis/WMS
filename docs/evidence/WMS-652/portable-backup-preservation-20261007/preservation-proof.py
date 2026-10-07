"""Execute only the actual preservation function, then refuse an assertion mutation.

Stdlib AST extraction avoids importing pytest/conftest or executing any shell gate.
The extracted function body is never replaced or reimplemented.
"""
import ast
import hashlib
import inspect
import json
from pathlib import Path
import sys
import tempfile
import traceback

root = Path(__file__).resolve().parents[4]
evidence = Path(__file__).resolve().parent
boundary = root / 'backend/tests/test_prod_deploy_backup_gate_boundary.py'
source = root / 'backend/tests/test_prod_deploy_backup.py'
boundary_raw, source_raw = boundary.read_bytes(), source.read_bytes()
tree = ast.parse(boundary_raw)
target = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == 'test_all_seven_backup_variants_and_original_assertions_are_preserved')
isolated = ast.Module(body=[target], type_ignores=[])
namespace = {'ast': ast, 'hashlib': hashlib, 'inspect': inspect, 'json': json, 'SOURCE': source}
exec(compile(isolated, str(boundary), 'exec'), namespace)
namespace[target.name]()
(evidence / 'after-target.log').write_text(
    f'Python {sys.version.split()[0]} stdlib execution of actual extracted function\n'
    f'{boundary.relative_to(root)}::{target.name} PASS\n'
    '1 target passed;0 failures;0 skips. No pytest import, gate variants or Docker execution.\n')
text = source_raw.decode()
assert text.count('assert stop < dump') == 1
mutated = text.replace('assert stop < dump', 'assert stop <= dump', 1)
parsed = ast.parse(mutated)
original_function = next(n for n in parsed.body if isinstance(n, ast.FunctionDef)
                         and n.name == 'test_deploy_requires_verified_backup_before_migration')
assert len([n for n in ast.walk(original_function) if isinstance(n, ast.Assert)]) == 23
last_assert = [n for n in ast.walk(target) if isinstance(n, ast.Assert)][-1]
with tempfile.TemporaryDirectory(prefix='.assertion-copy-', dir=evidence) as directory:
    copy = Path(directory) / 'test_prod_deploy_backup.py'
    copy.write_text(mutated)
    namespace['SOURCE'] = copy
    try:
        namespace[target.name]()
    except AssertionError as error:
        frames = traceback.extract_tb(error.__traceback__)
        assert frames[-1].lineno == last_assert.lineno, 'mutation must fail the hash assertion'
        (evidence / 'negative-copy.log').write_text(
            'Actual preservation function with SOURCE bound only to an untracked mutated copy\n'
            'Mutation: assert stop < dump -> assert stop <= dump (23 assertions retained)\n'
            + ''.join(traceback.format_exception(error))
            + 'Expected hash assertion FAIL; no setup/count failure; temporary copy removed.\n')
    else:
        raise AssertionError('Original assertion mutation must still be rejected')
assert source.read_bytes() == source_raw and boundary.read_bytes() == boundary_raw
(evidence / 'target-results.json').write_text(json.dumps({
    'python': sys.version.split()[0], 'target_id': 'backend/tests/test_prod_deploy_backup_gate_boundary.py::' + target.name,
    'execution': 'Compile actual function AST only, with real stdlib modules and actual SOURCE binding.',
    'after': {'pass': 1, 'fail': 0, 'skipped': 0},
    'negative': {'expected_fail': 1, 'assertions': 23, 'failure_line': last_assert.lineno,
                 'reason': 'Hardcoded full-format preservation hash rejects changed ordering assertion.'},
    'original_source_sha256': hashlib.sha256(source_raw).hexdigest(),
    'mutated_copy_sha256': hashlib.sha256(mutated.encode()).hexdigest(),
    'tracked_source_and_boundary_unchanged_by_execution': True, 'temporary_copy_removed': True,
    'command': 'python3 -B docs/evidence/WMS-652/portable-backup-preservation-20261007/preservation-proof.py',
}, indent=2) + '\n')
print('Actual preservation target PASS on3.14; changed assertion copy fails the same hash check; tracked source untouched.')
