"""Narrow independent exact-SHA probes. Synthetic Git fixtures are not release proof."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
TARGET = '65049df62d2bac87932fc5349f6326caec43dea5'
PRODUCT = 'aadd1716abc34f316648639e3baa10c1ac8c5e54'
OLD = '0151a555ac429957d0eee591317cc4326e909dfd'
sys.path.insert(0, str(ROOT))
from scripts.ci import process_contracts as pc


def blob(ref, path):
    return subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{ref}:{path}'])


def module(ref, path, name):
    result = types.ModuleType(name)
    result.__file__ = str(ROOT / path)
    exec(compile(blob(ref, path), f'{ref}:{path}', 'exec'), result.__dict__)
    return result


promoter = module(TARGET, 'scripts/ci/promote_guards.py', 'review_promoter')
checker = module(TARGET, 'scripts/ci/check_task_documents.py', 'review_checker')
sys.modules['scripts.ci.check_task_documents'] = checker
import scripts.ci
scripts.ci.check_task_documents = checker
prom_tests = module(TARGET, 'scripts/ci/tests/test_promote_guards.py', 'review_promote_tests')
doc_tests = module(TARGET, 'scripts/ci/test_check_task_documents.py', 'review_doc_tests')
prom_tests.promoter = promoter
doc_tests.checker = checker
assert blob(TARGET, 'scripts/ci/tests/test_promote_guards.py') == blob('1dc7fc05dd3a559534474a91b419986f6f3ca483', 'scripts/ci/tests/test_promote_guards.py')
assert blob(TARGET, 'scripts/ci/test_check_task_documents.py') == blob('ca4f8d0fd470fc27c5f1e356eb682edcb95daca1', 'scripts/ci/test_check_task_documents.py')
def definitions(raw):
    return {n.name: ast.dump(n, include_attributes=False) for n in ast.walk(ast.parse(raw)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
aba = definitions(blob('aba5577bbe2516e92a6f258900499054da82516a', 'scripts/ci/tests/test_promote_guards.py'))
final = definitions(blob(TARGET, 'scripts/ci/tests/test_promote_guards.py'))
assert all(final[name] == body for name, body in aba.items())
for path in ['scripts/ci/tests/test_promote_guards.py', 'scripts/ci/test_check_task_documents.py', 'scripts/ci/process_contracts.py']:
    assert (ROOT / path).read_bytes() == blob(TARGET, path)

# Replay only new frozen failures against the exact pre-implementation programs.
prom_tests.promoter = module(PRODUCT + '^', 'scripts/ci/promote_guards.py', 'review_old_promoter')
selected = ['test_missing_saved_protected_policy_refuses_legacy_move', 'test_dangling_saved_protected_policy_refuses_legacy_move', 'test_protected_wms654_templates_bind_every_real_case_in_fixed_vitest_report']
with (HERE / 'promotion-targeted-red.log').open('w') as output:
    red = unittest.TextTestRunner(stream=output, verbosity=2).run(unittest.TestSuite(prom_tests.PromoteGuardsTests(name) for name in selected))
assert (red.testsRun, len(red.failures), len(red.errors)) == (3, 2, 1)
prom_tests.promoter = promoter
doc_tests.checker = module(PRODUCT + '^', 'scripts/ci/check_task_documents.py', 'review_old_checker')
selected_doc = [name for name in dir(doc_tests.GitTests) if name.startswith('test_wms687')]
with (HERE / 'docgate-targeted-red.log').open('w') as output:
    doc_red = unittest.TextTestRunner(stream=output, verbosity=2).run(unittest.TestSuite(doc_tests.GitTests(name) for name in selected_doc))
assert (doc_red.testsRun, len(doc_red.failures), len(doc_red.errors)) == (4, 2, 0)
doc_tests.checker = checker


def snapshot(root):
    result = {}
    for path in root.rglob('*'):
        if '.git' in path.relative_to(root).parts:
            continue
        if path.is_symlink():
            result[str(path.relative_to(root))] = 'symlink:' + str(path.readlink())
        elif path.is_file():
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


promotion_probes = []
for scenario in ['deleted', 'dangling']:
    test = prom_tests.PromoteGuardsTests()
    test.setUp()
    try:
        source = test.protected_original_fixture('WMS-905')
        policy_path = test.root / pc.POLICY_PATH
        policy_path.unlink()
        if scenario == 'dangling':
            policy_path.symlink_to('missing-policy.json')
        before = snapshot(test.root)
        status = test.git('status', '--porcelain')
        try:
            promoter.promote(test.root, 'WMS-905')
            raise AssertionError('Missing committed policy was accepted')
        except ValueError as exc:
            reason = str(exc)
        assert before == snapshot(test.root) and status == test.git('status', '--porcelain')
        promotion_probes.append({'scenario': scenario, 'rejected_before_mutation': True, 'reason': reason})
    finally:
        test.doCleanups()
test = prom_tests.PromoteGuardsTests()
test.setUp()
try:
    source, owner = test.wms654_protected_template_fixture()
    before = snapshot(test.root)
    promoter.promote(test.root, 'WMS-654')
    promoter.promote(test.root, 'WMS-654')
    assert snapshot(test.root) == before and test.git('status', '--porcelain') == ''
    promotion_probes.append({'scenario': 'actual two-template fixture twice', 'all_12_registered': True, 'no_diff': True})
finally:
    test.doCleanups()
for missing in range(12):
    test = prom_tests.PromoteGuardsTests()
    test.setUp()
    try:
        cases = test.wms654_expanded_cases('src/sections/CatalogSection.wms654.test.tsx')
        removed = cases.pop(missing)
        test.wms654_protected_template_fixture(cases=cases)
        before = snapshot(test.root)
        try:
            promoter.promote(test.root, 'WMS-654')
            raise AssertionError('Incomplete matrix accepted')
        except ValueError as exc:
            assert 'case/report' in str(exc)
        assert before == snapshot(test.root) and test.git('status', '--porcelain') == ''
        promotion_probes.append({'scenario': 'one missing matrix ID', 'removed': removed, 'rejected_before_mutation': True})
    finally:
        test.doCleanups()

ledger_probes = []
for scenario in ['allowed', 'arbitrary-same-task-test', 'business-file', 'foreign-task-test', 'foreign-doc', 'own-business-requirement', 'existing-permission', 'deleted-original', 'deleted-companion', 'symlink-companion', 'executable-companion', 'declared-mismatch', 'review-report-changed']:
    test = doc_tests.GitTests()
    test.setUp()
    try:
        rollout, contract, frozen_paths, document = test.wms687_contract(second_frozen=scenario == 'existing-permission')
        frozen = frozen_paths[0]
        permission = 'frontend/src/screens/ff/FfInboundRequestView.wms687.permission.test.ts'
        regression = 'frontend/src/screens/ff/FfInboundRequestView.wms687.regression.dom.test.tsx'
        if scenario == 'deleted-original':
            (test.root / frozen).unlink()
        else:
            test.write(frozen, "export const frozenContract = 'reviewed correction'\n")
        test.write(permission, '// WMS-687 own new permission test\n')
        test.write(regression, '// WMS-687 own new regression test\n')
        test.write(document, test.wms687_document(f'{frozen}::old<br>{permission}::permission<br>{regression}::regression'))
        if scenario == 'arbitrary-same-task-test':
            test.write('frontend/src/screens/ff/Other.wms687.test.tsx', '// same task but not allowed exact path\n')
        elif scenario == 'business-file':
            test.write('frontend/src/screens/ff/FfInboundRequestView.tsx', '// forbidden product change\n')
        elif scenario == 'foreign-task-test':
            test.write('frontend/src/screens/ff/FfInboundRequestView.wms688.test.tsx', '// foreign task\n')
        elif scenario == 'foreign-doc':
            test.write('docs/requirements/WMS-688.md', 'foreign semantics\n')
        elif scenario == 'own-business-requirement':
            test.write(document, (test.root / document).read_text().replace('R1', 'R99'))
        elif scenario == 'deleted-companion':
            (test.root / permission).unlink()
            # Deletion of a preexisting file must be visible in correction diff.
            test.git('reset', '--hard', contract)
            test.write(permission, '// existing before correction\n')
            test.commit('prepare existing companion')
            (test.root / permission).unlink()
            test.write(frozen, "export const frozenContract = 'reviewed correction'\n")
        elif scenario == 'symlink-companion':
            (test.root / permission).unlink()
            (test.root / permission).symlink_to('missing.ts')
        elif scenario == 'executable-companion':
            (test.root / permission).chmod(0o755)
        correction = test.commit('WMS-687 reviewed correction')
        test.wms687_ledger(contract, correction, [frozen])
        ledger_path = test.root / 'docs/reviews/contract-corrections/WMS-687.json'
        if scenario == 'declared-mismatch':
            ledger = json.loads(ledger_path.read_text())
            ledger['ancillary_files'] = [permission]
            ledger_path.write_text(json.dumps(ledger))
            test.commit('mismatching ancillary declaration')
        elif scenario == 'review-report-changed':
            report = 'docs/reviews/review.md'
            test.write(report, 'independent PASS\n')
            review_commit = test.commit('immutable review')
            ledger = json.loads(ledger_path.read_text())
            ledger['review'].update(report=report, report_commit=review_commit)
            ledger_path.write_text(json.dumps(ledger))
            test.commit('bind review artifact')
            test.write(report, 'changed after independent review\n')
            test.commit('mutate review report')
        before = snapshot(test.root)
        errors = checker.contract_change_errors(test.root, rollout)
        assert bool(errors) == (scenario != 'allowed'), (scenario, errors)
        assert before == snapshot(test.root) and test.git('status', '--porcelain') == ''
        ledger_probes.append({'scenario': scenario, 'rejected': bool(errors), 'errors': errors, 'no_mutation': True})
    finally:
        test.doCleanups()

old = json.loads(blob(OLD, pc.POLICY_PATH))
policy = json.loads(blob(TARGET, pc.POLICY_PATH))
pc.validate_policy(policy)
assert (len(policy['files']), len(policy['suites']), sum(len(s['cases']) for s in policy['suites'].values())) == (233, 22, 1218)
assert set(old['files']).issubset(policy['files'])
def tree_entries(ref):
    raw = subprocess.check_output(['git', '-C', str(ROOT), 'ls-tree', '-r', '-z', ref])
    return {row.split(b'\t', 1)[1].decode(): row.split(b'\t', 1)[0].decode().split() for row in raw.split(b'\0') if row}
old_tree, final_tree = tree_entries(OLD), tree_entries(TARGET)
changed_old = []
for path, digest in old['files'].items():
    assert old_tree[path][0] == final_tree[path][0]
    if policy['files'][path] != digest:
        changed_old.append(path)
    else:
        assert old_tree[path] == final_tree[path]
assert sorted(changed_old) == ['.github/workflows/ci.yml', 'frontend/tests-e2e/wms672-dom.test.tsx', 'scripts/ci/tests/test_ci_release_additions.py', 'scripts/ci/tests/test_promote_guards.py']
assert blob(TARGET, 'frontend/tests-e2e/wms672-dom.test.tsx') == blob('ce615a3324c14109a02c830fc8cfa977c302e9a1', 'frontend/tests-e2e/wms672-dom.test.tsx')
additions = {}
for name, suite in old['suites'].items():
    current = policy['suites'][name]
    assert all(current[k] == suite[k] for k in ['report', 'format', 'exact'])
    assert [c for c in current['cases'] if c in suite['cases']] == suite['cases']
for name, suite in policy['suites'].items():
    additions[name] = [c for c in suite['cases'] if c not in old['suites'].get(name, {}).get('cases', [])]
for path, digest in policy['files'].items():
    assert hashlib.sha256(blob(TARGET, path)).hexdigest() == digest
workflow = yaml.safe_load(blob(TARGET, '.github/workflows/ci.yml'))['jobs']
needs = workflow['process-proof']['needs']
assert set(needs) == {'baseline', 'backend', 'frontend-build', 'guards', 'print-regressions', 'printer-windows', 'wms686-mockup'}
assert set(workflow['backend']['needs']) == {'backend-checks', 'backend-shards'}
commands = {name: '\n'.join(s.get('run', '') for s in job['steps']) for name, job in workflow.items()}
assert 'scripts/ci/tests/test_promote_guards.py' in commands['guards']
assert '-k wms687 --junitxml="$RUNNER_TEMP/docgate-687.xml"' in commands['guards']
assert '--junitxml="$RUNNER_TEMP/release-postgres/654.xml"' in commands['backend-checks']
assert '--ignore=tests/test_wms654' not in commands['backend-shards']
assert 'backend_shards.py run' in commands['backend-shards']
assert 'npx vitest run --reporter=default --reporter=json --outputFile.json="$RUNNER_TEMP/frontend-all.json"' in commands['frontend-build']
assert "-t 'C5a 33 labels'" in commands['frontend-build']
for name in ['guards', 'frontend-build', 'backend-checks']:
    assert not workflow[name].get('continue-on-error', False)
    for step in workflow[name]['steps']:
        assert not step.get('continue-on-error', False)
downloads = [s['with']['name'] for s in workflow['process-proof']['steps'] if s.get('uses') == 'actions/download-artifact@v4']
for name in ['guards', 'frontend-build', 'backend']:
    upload = next(s for s in workflow[name]['steps'] if s.get('uses') == 'actions/upload-artifact@v4')
    assert upload['with']['name'] in downloads
    assert '${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}' in upload['with']['name']
guard_upload = next(s for s in workflow['guards']['steps'] if s.get('uses') == 'actions/upload-artifact@v4')
assert '${{ runner.temp }}/ci-shards.xml' in guard_upload['with']['path'] and '${{ runner.temp }}/docgate-687.xml' in guard_upload['with']['path']
front_upload = next(s for s in workflow['frontend-build']['steps'] if s.get('uses') == 'actions/upload-artifact@v4')
assert '${{ runner.temp }}/wms672-c5a.json' in front_upload['with']['path']
pg_upload = next(s for s in workflow['backend-checks']['steps'] if s.get('uses') == 'actions/upload-artifact@v4')
assert '${{ runner.temp }}/release-postgres' in pg_upload['with']['path']
assert pg_upload['with']['name'] in [s['with']['name'] for s in workflow['backend']['steps'] if s.get('uses') == 'actions/download-artifact@v4']
assert '${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}' in pg_upload['with']['name']

raw = ROOT / 'docs/evidence/WMS-652/process-fixes-20261007'
closure = ROOT / 'docs/evidence/WMS-652/closure-20261007'
read_results = {}
for name, report in [('ci-shards', raw / 'ci-shards-process-final.xml'), ('docgate-687', raw / 'docgate-687.xml'), ('pg-654', ROOT / 'docs/evidence/WMS-654/combined-postgres-20261007.xml'), ('print-672-c5a', closure / 'wms672-c5a.json')]:
    suite = copy.deepcopy(policy['suites'][name])
    suite['report'] = report.name
    result = pc.verify_reports({'version': 1, 'files': {}, 'suites': {name: suite}}, report.parent)
    read_results[name] = len(result[name])
front = pc.vitest_results((closure / '654-frontend.json').read_bytes())
assert len(additions['frontend-fbs']) == 20 and all(front[c] == 'passed' for c in additions['frontend-fbs'])
matrix = prom_tests.PromoteGuardsTests().wms654_expanded_cases('src/sections/CatalogSection.wms654.test.tsx')
assert len(matrix) == 12 and set(matrix).issubset(policy['suites']['frontend-fbs']['cases']) and all(front[c] == 'passed' for c in matrix)
read_results['frontend654-added-cases'] = 20
for name, report, cases in [('docgate-687', HERE / 'docgate-687.xml', policy['suites']['docgate-687']['cases']), ('promotion', HERE / 'promotion.xml', [c for c in policy['suites']['ci-shards']['cases'] if '.test_promote_guards.' in c])]:
    suite = {'report': report.name, 'format': 'junit', 'exact': True, 'cases': cases}
    verified = pc.verify_reports({'version': 1, 'files': {}, 'suites': {name: suite}}, HERE)
    read_results['fresh-' + name] = len(verified[name])
collection = (closure / '654-collection.log').read_text().splitlines()
for case in additions['backend-fbs']:
    owner, name = case.split('::', 1)
    assert owner.replace('.', '/') + '.py::' + name in collection
binding = json.loads(blob(TARGET, 'scripts/ci/tests/fixtures/wms652_source_binding_transition.json'))
assert binding['final_reviewed_source'] is None and binding['status'] == 'pending-final-independent-freeze'
assert 'product_scope.py --root . --trusted-ref d61805978b3e7878d1056c99b4e6e0823edf49a5' in commands['guards']

result = {'reviewed_sha': TARGET, 'implementation_sha': PRODUCT, 'old_source': OLD, 'frozen_contract_bytes_preserved': True, 'targeted_red': {'promotion': {'tests': 3, 'failures': 2, 'errors': 1}, 'docgate687': {'tests': 4, 'failures': 2}}, 'promotion_probes': promotion_probes, 'ledger_probes': ledger_probes, 'policy': {'paths': 233, 'suites': 22, 'ids': 1218}, 'original_1146_ids_and_all_18_bindings_preserved': True, 'old_222_paths_and_modes_preserved': True, 'old_protected_hash_delta': changed_old, 'additions': {k: v for k, v in additions.items() if v}, 'required_needs': needs, 'backend_needs': workflow['backend']['needs'], 'raw_reports_verified': read_results, 'new_backend_16_cases_collection_bound_not_claimed_executed': True, 'P': 'd618 explicit pending placeholder, final not frozen', 'S': 'pending', 'full_ci_release_approval': False}
(HERE / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'additions'}, ensure_ascii=False, indent=2))
