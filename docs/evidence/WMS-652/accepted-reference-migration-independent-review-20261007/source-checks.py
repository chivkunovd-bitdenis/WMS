"""Read immutable Git blobs and saved receipts; never rerun the three tests."""
import ast
import collections
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = 'ce212ec254a87a4f5570b549d6aa721db971b5ef'
PRIOR = '9dae4b19f6d4dca554200e08282579414a110848'
CONTRACT = '88343975e13f8819d6b81cd03cddbba1d67db078'
ACCEPTED = '25ebc6fe13384a55cf1f2b7e5e4054bb862d002d'
OLD = 'd61805978b3e7878d1056c99b4e6e0823edf49a5'
TEST = 'scripts/ci/tests/test_ci_release_additions.py'
POLICY = 'guards/PROCESS_CONTRACTS.json'
E = 'docs/evidence/WMS-652/accepted-reference-contract-migration-20261007/'


def git(*args):
    return subprocess.check_output(['git', *args])


def raw(path, ref=SOURCE):
    return git('show', ref + ':' + path)


def obj(path, ref=SOURCE):
    return json.loads(raw(path, ref))


def sha(data):
    return hashlib.sha256(data).hexdigest()


before, after = raw(TEST, PRIOR), raw(TEST)
assert before.count(OLD.encode()) == 1 and after.count(ACCEPTED.encode()) == 1
assert before.replace(OLD.encode(), ACCEPTED.encode(), 1) == after
assert after == raw(TEST, CONTRACT)
before_ast, after_ast = ast.parse(before), ast.parse(after)
constants = [node for node in ast.walk(after_ast) if isinstance(node, ast.Constant)
             and isinstance(node.value, str) and ACCEPTED in node.value]
assert len(constants) == 1
new_literal = constants[0].value
assert new_literal == 'python scripts/ci/product_scope.py --root . --trusted-ref ' + ACCEPTED
constants[0].value = new_literal.replace(ACCEPTED, OLD)
assert ast.dump(before_ast, include_attributes=False) == ast.dump(after_ast, include_attributes=False)
case_ids = ['scripts.ci.tests.test_ci_release_additions.ReleaseCommandContracts.' + n.name
            for c in before_ast.body if isinstance(c, ast.ClassDef)
            for n in c.body if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
assert len(case_ids) == 3 and case_ids == obj(E + 'cases.json')
assert b"self.assertIn('pytest -q scripts/ci/tests/test_product_scope.py --junitxml=', guard)" in after
policy, old_policy = obj(POLICY), obj(POLICY, PRIOR)
assert len(policy['files']) == 229 and len(policy['suites']) == 21
assert sum(len(s['cases']) for s in policy['suites'].values()) == 1173
assert policy['files'].keys() == old_policy['files'].keys() and policy['suites'] == old_policy['suites']
assert [p for p in policy['files'] if policy['files'][p] != old_policy['files'][p]] == [TEST]
assert policy['files'][TEST] == sha(after) == '9fe9ca325e8fa264e609449ab70cd3742fd5d54af501ea54bfe3c69a8742af4a'
tree = {}
for row in git('ls-tree', '-r', '-z', SOURCE).split(b'\0'):
    if row:
        meta, path = row.decode().split('\t', 1)
        tree[path] = meta.split()
verified = []
for path, digest in policy['files'].items():
    mode, kind, blob_id = tree[path]
    assert mode in ['100644', '100755'] and kind == 'blob'
    assert sha(raw(path)) == digest, path
    if path != TEST:
        assert raw(path) == raw(path, PRIOR), path
    verified.append([path, mode, blob_id, digest])
assert len(policy['suites']['product-scope']['cases']) == 51
assert git('diff', '--name-only', PRIOR, SOURCE, '--', '.github/workflows', 'scripts/ci',
           'backend/app', 'backend/alembic', 'frontend/src', 'frontend/package.json',
           'frontend/package-lock.json').decode().splitlines() == [TEST]
assert git('diff', '--name-only', ACCEPTED, SOURCE, '--', 'backend/app', 'backend/alembic',
           'frontend/src', 'frontend/package.json', 'frontend/package-lock.json') == b''
c5 = 'frontend/tests-e2e/wms672-box-labels.test.mjs'
assert raw(c5) == raw(c5, PRIOR)
frozen = obj(E + 'frozen-hashes.json')
for row in frozen:
    assert sha(raw(row['path'])) == row['base_sha256'] == row['current_sha256']
provenance = obj(E + 'provenance.json')
for row in provenance['approval_inputs']:
    assert sha(raw(row['path'], row['commit'])) == row['sha256']
assert provenance['accepted_reference'] == ACCEPTED
guard_log = raw('docs/evidence/WMS-652/common-ci-37548248403/guards-job.log')
assert sha(guard_log) == provenance['actual_full_ci']['job_log_sha256']
assert b'Ran 131 tests' in guard_log and b'FAILED (failures=1)' in guard_log
assert b'FAIL: test_actual_candidate_product_scope_uses_fixed_independently_reviewed_reference' in guard_log
for row in provenance['actual_full_ci']['selected_raw_lines']:
    assert guard_log.decode().splitlines()[row['line'] - 1] == row['raw']
neg = obj(E + 'negative-control.json')
workflow = raw('.github/workflows/ci.yml')
counterexample = workflow.replace(ACCEPTED.encode(), OLD.encode(), 1)
assert sha(workflow) == neg['original_workflow_sha256']
assert sha(counterexample) == neg['counterexample_workflow_sha256']
assert (neg['tests'], neg['fail'], neg['errors'], neg['skipped']) == (1, 1, 0, 0)
negative_log = raw(E + 'old-reference-counterexample.log').decode()
assert 'Ran 1 test' in negative_log and 'FAILED (failures=1)' in negative_log
assert new_literal in negative_log and 'not found in' in negative_log
before_log, after_log = raw(E + 'before.log').decode(), raw(E + 'after.log').decode()
assert 'Ran 3 tests' in before_log and 'FAILED (failures=1)' in before_log
assert 'Ran 3 tests' in after_log and after_log.rstrip().endswith('OK')
actual = json.loads((HERE / 'three-tests-receipt.json').read_text())
actual_log = (HERE / 'three-tests.log').read_bytes()
assert actual['source_sha'] == SOURCE and actual['exit_code'] == 0 and actual['executions_by_this_reviewer'] == 1
assert sha(actual_log) == actual['raw_sha256']
lines = re.findall(r'^([^\n]+) \.\.\. ok$', actual_log.decode(), re.M)
assert len(lines) == 3 and 'Ran 3 tests' in actual_log.decode() and actual_log.decode().rstrip().endswith('OK')
actual_ids = ['scripts.ci.tests.test_ci_release_additions.ReleaseCommandContracts.' + line.split(' ', 1)[0]
              for line in lines]
assert set(actual_ids) == set(case_ids)
result = {
    'verdict': 'PASS bounded literal contract and digest migration only', 'source_sha': SOURCE,
    'contract_commit': CONTRACT, 'previous_reviewed_source': PRIOR,
    'previous_SOURCE_approval_historical_only': 'f4d095aa4280c89075bfafcef2883f88e17c25d4',
    'approved_product_reference_retained': ACCEPTED, 'policy_sha256': sha(raw(POLICY)),
    'changed_test': {'path': TEST, 'before_sha256': sha(before), 'after_sha256': sha(after),
                     'exact_one_literal_byte_change': True, 'normalized_AST_identical': True,
                     'old_literal': new_literal.replace(ACCEPTED, OLD), 'new_literal': new_literal,
                     'case_ids': case_ids, 'all_other_assertions_and_bytes_preserved': True},
    'protected_files_verified': len(verified), 'regular_modes': dict(collections.Counter(r[1] for r in verified)),
    'verified_sorted_path_mode_blob_digest_rows_sha256': sha(json.dumps(sorted(verified), separators=(',', ':')).encode()),
    'suites': 21, 'case_ids': 1173, 'all_21_suite_definitions_identical_to_9dae': True,
    'other228_protected_blobs_identical_to_9dae': True, 'scope51_and_CLI_unchanged': True,
    'C5_bytes_unchanged': True, 'app_diff_vs_25eb': [],
    'saved_actual_CI': {'run': 37548248403, 'tested_merge': 'ac845328b27b5be265962695e10766efddef339e',
                        'guards_raw_sha256': sha(guard_log), 'infrastructure_tests': 131, 'pass': 130, 'fail': 1},
    'saved_testwriter_before_after': {'before': '2PASS/1 targeted assertion FAIL', 'after': '3PASS/0skip'},
    'negative_control': {'same_actual_test_old_reference': '1 assertion FAIL/0errors/0skip',
                          'copied_workflow_sha256': sha(counterexample), 'replayed_by_this_reviewer': False},
    'independent_three_test_run': actual,
    'review_gap_acknowledged': 'Earlier workflow/ref/pin review missed this protected test constant still requiring d618.',
    'distinct_analyst_migration_acceptance': 'pending next stage',
    'final_SOURCE_pin_approval': False, 'main_or_pin_changed': False,
    'fullCI_build_browser_C5_other_cases_repeated': False,
    'bounds': 'Existing software/reference approval retained; new pin requires analyst then tiny exact-SHA review. No fullCI/release/deploy/paper claim.'}
(HERE / 'source-checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: result[k] for k in ['verdict', 'source_sha', 'policy_sha256', 'protected_files_verified',
                                        'suites', 'case_ids', 'final_SOURCE_pin_approval']}, indent=2))
