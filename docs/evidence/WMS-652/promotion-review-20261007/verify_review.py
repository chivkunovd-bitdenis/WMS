"""Independent bounded review of cafaaef; fixtures are synthetic, not release proof."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
TARGET = 'cafaaefae22b529207ddf5bdd0aacbb1194f735b'
FROZEN = '90cf5e8f49e5eee1070c914b19ed87de4fa49353'
PREVIOUS = '14c340a76db5f77c248794183b44d8b13880ef81'
OLD = '0151a555ac429957d0eee591317cc4326e909dfd'
sys.path.insert(0, str(ROOT))
from scripts.ci import process_contracts as pc


def blob(ref, path):
    return subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{ref}:{path}'])


def load_promoter(ref):
    module = types.ModuleType('review_promoter')
    module.__file__ = str(ROOT / 'scripts/ci/promote_guards.py')
    exec(compile(blob(ref, 'scripts/ci/promote_guards.py'), f'{ref}:scripts/ci/promote_guards.py', 'exec'), module.__dict__)
    return module


test_path = 'scripts/ci/tests/test_promote_guards.py'
assert blob(TARGET, test_path) == blob(FROZEN, test_path) == (ROOT / test_path).read_bytes()
assert blob(TARGET, 'scripts/ci/promote_guards.py') == (ROOT / 'scripts/ci/promote_guards.py').read_bytes()
assert blob(TARGET, 'scripts/ci/process_contracts.py') == blob(PREVIOUS, 'scripts/ci/process_contracts.py')
spec = importlib.util.spec_from_file_location('review_frozen_tests', ROOT / test_path)
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
summary = {}
for label, ref in [('red', TARGET + '^'), ('green', TARGET)]:
    tests.promoter = load_promoter(ref)
    with (HERE / f'{label}.log').open('w') as output:
        result = unittest.TextTestRunner(stream=output, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
    summary[label] = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'failed_ids': [t.id() for t, _ in result.failures]}
assert summary['red']['tests'] == 5 and summary['red']['failures'] == 2 and summary['red']['errors'] == 0
assert summary['green'] == {'tests': 5, 'failures': 0, 'errors': 0, 'failed_ids': []}
promoter = tests.promoter


def fixture():
    test = tests.PromoteGuardsTests()
    test.setUp()
    source = 'backend/tests/test_immutable_contract.py'
    test.write(source, 'def test_frozen_case_id(): pass\n')
    test.write_saved_process_protection(source, 'tests.test_immutable_contract::test_frozen_case_id')
    test.write_manifest('active')
    test.write('docs/requirements/WMS-902.md', f'| Проверка | Класс | Тест | Вердикт |\n| --- | --- | --- | --- |\n| C902 | навсегда | {source}::test_frozen_case_id | принято |\n')
    test.git('add', '.')
    test.git('commit', '-qm', 'saved protected fixture')
    return test, source


def snapshot(root):
    files = {}
    for path in root.rglob('*'):
        if '.git' in path.relative_to(root).parts:
            continue
        if path.is_symlink():
            files[str(path.relative_to(root))] = 'symlink:' + str(path.readlink())
        elif path.is_file():
            files[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


probes = []
for scenario in ['changed-bytes', 'head-bytes-mismatch-with-matching-policy-hash', 'wrong-saved-hash', 'missing-case', 'wrong-format-report-binding', 'invalid-empty-report', 'uncommitted-policy', 'self-rehash-uncommitted', 'source-symlink', 'deleted-policy', 'dangling-policy-symlink']:
    test, source = fixture()
    try:
        policy_path = test.root / pc.POLICY_PATH
        policy = json.loads(policy_path.read_bytes())
        save = False
        if scenario in ['changed-bytes', 'head-bytes-mismatch-with-matching-policy-hash', 'self-rehash-uncommitted']:
            (test.root / source).write_text('def test_frozen_case_id(): assert True # changed\n')
            if scenario != 'changed-bytes':
                policy['files'][source] = hashlib.sha256((test.root / source).read_bytes()).hexdigest()
                policy_path.write_text(json.dumps(policy))
                if scenario == 'head-bytes-mismatch-with-matching-policy-hash':
                    test.git('add', pc.POLICY_PATH)
                    test.git('commit', '-qm', 'policy hash matches dirty source but HEAD source differs')
        elif scenario == 'wrong-saved-hash':
            policy['files'][source] = '0' * 64
            save = True
        elif scenario == 'missing-case':
            policy['suites']['protected-fixture']['cases'] = ['tests.other::test_other']
            save = True
        elif scenario == 'wrong-format-report-binding':
            policy['suites']['protected-fixture']['format'] = 'vitest'
            policy['suites']['protected-fixture']['report'] = 'frontend.json'
            save = True
        elif scenario == 'invalid-empty-report':
            policy['suites']['protected-fixture']['report'] = ''
            save = True
        elif scenario == 'uncommitted-policy':
            policy['suites']['protected-fixture']['exact'] = False
            policy_path.write_text(json.dumps(policy))
        elif scenario == 'source-symlink':
            (test.root / 'outside.py').write_bytes((test.root / source).read_bytes())
            (test.root / source).unlink()
            (test.root / source).symlink_to(test.root / 'outside.py')
        elif scenario == 'deleted-policy':
            policy_path.unlink()
        elif scenario == 'dangling-policy-symlink':
            policy_path.unlink()
            policy_path.symlink_to(test.root / 'missing-policy.json')
        if save:
            policy_path.write_text(json.dumps(policy))
            test.git('add', pc.POLICY_PATH)
            test.git('commit', '-qm', 'saved negative fixture')
        before = snapshot(test.root)
        before_status = test.git('status', '--porcelain')
        try:
            returned = promoter.promote(test.root, 'WMS-902')
            refused, reason = False, 'returned: ' + repr(returned)
        except (ValueError, OSError, subprocess.CalledProcessError) as exc:
            refused, reason = True, str(exc)
        probes.append({'scenario': scenario, 'refused': refused, 'reason': reason, 'no_mutation': before == snapshot(test.root) and before_status == test.git('status', '--porcelain'), 'protected_original_exists': (test.root / source).is_file(), 'moved_target_exists': (test.root / 'backend/tests/guards/test_immutable_contract.py').is_file(), 'status_after': test.git('status', '--porcelain')})
    finally:
        test.doCleanups()
assert all(p['refused'] and p['no_mutation'] for p in probes[:-2])
assert all(not p['refused'] and not p['protected_original_exists'] and p['moved_target_exists'] for p in probes[-2:])

old = json.loads(blob(OLD, pc.POLICY_PATH))
previous = json.loads(blob(PREVIOUS, pc.POLICY_PATH))
policy = json.loads(blob(TARGET, pc.POLICY_PATH))
for baseline in [old, previous]:
    for name, suite in baseline['suites'].items():
        assert all(policy['suites'][name][k] == suite[k] for k in ['report', 'format', 'exact'])
        assert [c for c in policy['suites'][name]['cases'] if c in suite['cases']] == suite['cases']
changed_hashes = [p for p in previous['files'] if previous['files'][p] != policy['files'].get(p)]
new_files = sorted(set(policy['files']) - set(previous['files']))
assert changed_hashes == [test_path]
assert new_files == ['scripts/ci/promote_guards.py']
for path, digest in policy['files'].items():
    assert hashlib.sha256(blob(TARGET, path)).hexdigest() == digest
new_cases = [c for c in policy['suites']['ci-shards']['cases'] if c not in previous['suites']['ci-shards']['cases']]
assert len(new_cases) == 3
assert len(policy['files']) == 226 and len(policy['suites']) == 19 and sum(len(s['cases']) for s in policy['suites'].values()) == 1164
workflow = yaml.safe_load(blob(TARGET, '.github/workflows/ci.yml'))
step = next(s for s in workflow['jobs']['guards']['steps'] if s.get('name') == 'Persist exact full-backend shard infrastructure cases')
assert 'test_promote_guards.py' not in step['run']
assert blob(TARGET, '.github/workflows/ci.yml') == blob(PREVIOUS, '.github/workflows/ci.yml')
raw_root = ROOT / 'docs/evidence/WMS-652/night1007-integration/process-wiring-20261007'
try:
    pc.verify_reports({'version': 1, 'files': {}, 'suites': {'ci-shards': policy['suites']['ci-shards']}}, raw_root)
    raise AssertionError('Existing receipt unexpectedly proves the new promotion cases')
except ValueError as exc:
    receipt_failure = str(exc)
    assert all(case in receipt_failure for case in new_cases)

result = {'reviewed_sha': TARGET, 'frozen_test_commit': FROZEN, 'frozen_test_bytes_unchanged': True, 'red_green': summary, 'probes': probes, 'old_1146_ids_and_suite_bindings_preserved': True, 'previous_1161_ids_and_suite_bindings_preserved': True, 'current': {'files': 226, 'suites': 19, 'cases': 1164}, 'changed_existing_hashes_since_14c': changed_hashes, 'new_protected_files': new_files, 'new_ci_shards_cases': new_cases, 'actual_ci_shards_producer_command': step['run'], 'actual_ci_shards_receipt_rejected_by_target_policy': receipt_failure, 'promotion_readme_claimed_files': 225, 'verdict': 'FAIL', 'final_P_S': 'pending', 'full_release_approval': False}
(HERE / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False, indent=2))
