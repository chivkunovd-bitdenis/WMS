"""Independent immutable-object audit; collection is not execution evidence."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
TARGET = 'ef154664e365644f4ba002c6e8affc5607fae725'
PRIOR = '65049df62d2bac87932fc5349f6326caec43dea5'
OLD = '0151a555ac429957d0eee591317cc4326e909dfd'

def blob(ref, path):
    return subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{ref}:{path}'])

def load(path):
    return json.loads(blob(TARGET, path))

def definitions(raw):
    return {n.name: ast.dump(n, include_attributes=False) for n in ast.walk(ast.parse(raw))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test_')}

spec = importlib.util.spec_from_file_location('pc', ROOT / '.review-fixture-ef154/scripts/ci/process_contracts.py')
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)
policy = load(pc.POLICY_PATH)
old = json.loads(blob(OLD, pc.POLICY_PATH))
prior = json.loads(blob(PRIOR, pc.POLICY_PATH))
pc.validate_policy(policy)
assert len(policy['files']) == 262 and len(policy['suites']) == 23
assert sum(len(s['cases']) for s in policy['suites'].values()) == 1502
bindings = []
for name, suite in old['suites'].items():
    current = policy['suites'][name]
    assert all(suite[k] == current[k] for k in ['report', 'format', 'exact'])
    assert set(suite['cases']) <= set(current['cases'])
    bindings.append({'suite': name, 'retained': len(suite['cases']),
                     'added_after_65049': len(set(current['cases']) - set(prior['suites'][name]['cases'])),
                     'report': current['report'], 'format': current['format'], 'exact': current['exact']})
assert sum(x['retained'] for x in bindings) == 1146
changed = []
for path, digest in policy['files'].items():
    raw = blob(TARGET, path)
    assert hashlib.sha256(raw).hexdigest() == digest, path
    mode = subprocess.check_output(['git', '-C', str(ROOT), 'ls-tree', TARGET, '--', path]).decode().split()[0]
    assert mode in ['100644', '100755'], (path, mode)
    if path in old['files']:
        assert subprocess.check_output(['git', '-C', str(ROOT), 'ls-tree', OLD, '--', path]).decode().split()[0] == mode
        if old['files'][path] != digest:
            changed.append(path)
assert set(old['files']) <= set(policy['files'])
assert set(changed) == {'.github/workflows/ci.yml', 'frontend/tests-e2e/wms672-dom.test.tsx',
                       'scripts/ci/tests/test_ci_release_additions.py', 'scripts/ci/tests/test_promote_guards.py'}
frozen = []
assert all(definitions(blob(TARGET, 'scripts/ci/test_check_task_documents.py')).get(name) == body
           for name, body in definitions(blob(PRIOR, 'scripts/ci/test_check_task_documents.py')).items())
for source, path in [('1fb6646c7', 'scripts/ci/test_check_task_documents.py'),
                     ('afed199fd', 'scripts/ci/test_check_task_documents.py'),
                     ('50bb0b9f0', 'scripts/ci/test_check_task_documents.py'),
                     ('8eae77ac3', 'scripts/ci/tests/test_promote_guards.py'),
                     ('7eb7a1683', 'scripts/ci/test_check_task_documents.py')]:
    before, after = definitions(blob(source, path)), definitions(blob(TARGET, path))
    approved_replacements = {
        'afed199fd': {'test_exact_chain_records_match_published_parent_blobs_and_report'},
        '50bb0b9f0': {'test_wms680_owner_semantic_and_fixture_matrix_is_registered_exactly',
                      'test_wms680_closed_matrix_rejects_owner_report_assertion_and_scope_canaries'},
    }.get(source, set())
    changed_definitions = {name for name, body in before.items() if after.get(name) != body}
    assert changed_definitions == approved_replacements, (source, changed_definitions)
    # The later independent Sol contract exercises 680 against real Git objects;
    # the ordinary parent-proof test still covers both untouched 658/681 chains.
    frozen.append({'source': source, 'path': path, 'preserved_test_definitions': len(before) - len(changed_definitions),
                   'replaced_by_7eb7_actual_graph_contract': sorted(changed_definitions)})
for path in ['scripts/ci/process_contracts.py', 'scripts/ci/build_process_proof.py',
             'scripts/ci/backend_shards.py', 'scripts/ci/product_scope.py']:
    assert blob(PRIOR, path) == blob(TARGET, path), path
record658 = load('scripts/ci/tests/fixtures/wms652_exact_reviewed_correction_chains.json')['tasks']['WMS-658']
ledger658 = load('docs/reviews/contract-corrections/WMS-658.json')['fixture_corrections']
assert len(ledger658) == len(record658['steps']) == 4
for entry, step in zip(ledger658, record658['steps']):
    assert entry['source_commit'] == step['source'] and entry['correction_commit'] == step['correction']
    assert entry['review']['evidence_commit'] == record658['report']['commit']
    assert entry['review']['evidence_blob'] == record658['report']['blob']
    assert entry['review']['evidence'] == record658['report']['path']

evidence = 'docs/evidence/WMS-652/final-closure-20261007/'
collections = set()
for name in ['new-front-collected.json', 'new-front-support-collected.json', 'new-front-658-collected.json']:
    for item in load(evidence + name):
        owner = item['file'].rsplit('/frontend/', 1)[1]
        # Vitest --list uses ' > ' between describe groups; JSON execution uses spaces.
        collections.add(owner + '::' + item['name'].replace(' > ', ' '))
front_additions = set(policy['suites']['frontend-fbs']['cases']) - set(prior['suites']['frontend-fbs']['cases'])
assert front_additions <= collections, sorted(front_additions - collections)
back_collected = set()
for name in ['new-back-collected.log', 'new-back-681-collected.log']:
    for line in blob(TARGET, evidence + name).decode().splitlines():
        if line.startswith('tests/') and '::' in line:
            owner, case = line.split('::', 1)
            back_collected.add(owner.removesuffix('.py').replace('/', '.') + '::' + case)
back_additions = set(policy['suites']['backend-fbs']['cases']) - set(prior['suites']['backend-fbs']['cases'])
assert back_additions <= back_collected, sorted(back_additions - back_collected)
raw72 = pc.vitest_results(blob(TARGET, evidence + 'merged-680-673-unit.json'))
assert len(raw72) == 72 and set(raw72.values()) == {'passed'}
c6_raw = blob(TARGET, 'docs/evidence/WMS-681/postgres-c6/green-junit.xml')
c6 = pc.junit_results(c6_raw)
assert c6 == dict.fromkeys(policy['suites']['wms681-postgres-c6']['cases'], 'passed')
properties = {p.get('name'): p.get('value') for p in ET.fromstring(c6_raw).iter('property')}
first, second = map(json.loads, [properties['first_worker'], properties['second_worker']])
assert first['os_pid'] != second['os_pid'] and first['pg_pid'] != second['pg_pid']
assert first['pg_pid'] in json.loads(properties['blocking_pids'])
assert json.loads(properties['wb_create_amounts']) == [5]
assert [r['status'] for r in json.loads(properties['worker_results'])] == [200, 200]

workflow = yaml.safe_load(blob(TARGET, '.github/workflows/ci.yml'))
jobs = workflow['jobs']
assert jobs['process-proof']['needs'] == ['baseline', 'backend', 'frontend-build', 'guards',
                                        'print-regressions', 'printer-windows', 'wms686-mockup']
assert jobs['backend']['needs'] == ['backend-checks', 'backend-shards']
pg_step = next(s for s in jobs['backend-checks']['steps'] if s.get('name', '').startswith('WMS-681 two-worker'))
assert 'if' not in pg_step and 'continue-on-error' not in pg_step
assert pg_step['env']['WMS_TEST_DATABASE_URL'].endswith('/wms_test_681_recovery')
assert 'pytest -n 0' in pg_step['run'] and '::test_wms681_postgres_two_workers_recover_one_group_across_qr_checkpoint' in pg_step['run']
assert 'release-postgres/681.xml' in pg_step['run']
assert 'release-postgres' in next(s['with']['path'] for s in jobs['backend-checks']['steps'] if s.get('uses','').startswith('actions/upload-artifact'))
doc_step = next(s for s in jobs['guards']['steps'] if 'docgate-687.xml' in s.get('run',''))
selection = doc_step['run'].split('-k "')[1].split('"')[0].split(' or ')
defs = definitions(blob(TARGET, 'scripts/ci/test_check_task_documents.py'))
doc_ids = {'scripts.ci.test_check_task_documents.GitTests::' + name for name in defs if any(x in name for x in selection)}
assert doc_ids == set(policy['suites']['docgate-687']['cases']), sorted(doc_ids ^ set(policy['suites']['docgate-687']['cases']))
for job in ['backend-checks', 'backend', 'frontend-build', 'guards', 'printer-windows', 'print-regressions', 'wms686-mockup']:
    for step in jobs[job]['steps']:
        if step.get('uses', '').startswith('actions/upload-artifact'):
            assert '${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}' in step['with']['name']
for step in jobs['process-proof']['steps']:
    if step.get('uses', '').startswith('actions/download-artifact'):
        assert '${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}' in step['with']['name']

negative = []
with tempfile.TemporaryDirectory(dir=ROOT / '.review-fixture-ef154') as directory:
    root = Path(directory)
    report = root / 'release-postgres/681.xml'
    report.parent.mkdir()
    focused = {'version': 1, 'files': {}, 'suites': {'c6': policy['suites']['wms681-postgres-c6']}}
    report.write_bytes(c6_raw)
    assert pc.verify_reports(focused, root)['c6'] == list(c6)
    for scenario in ['missing-report', 'missing-case', 'sqlite-skip', 'failure', 'wrong-case', 'extra-case']:
        tree = ET.fromstring(c6_raw)
        case = next(tree.iter('testcase'))
        if scenario == 'missing-report':
            report.unlink()
        elif scenario == 'missing-case':
            tree.find('testsuite').remove(case)
        elif scenario in ['sqlite-skip', 'failure']:
            ET.SubElement(case, 'skipped' if scenario == 'sqlite-skip' else 'failure')
        elif scenario == 'wrong-case':
            case.set('name', 'other-case')
        else:
            extra = copy.deepcopy(case)
            extra.set('name', 'other-case')
            tree.find('testsuite').append(extra)
        if scenario != 'missing-report':
            report.write_bytes(ET.tostring(tree))
        try:
            pc.verify_reports(focused, root)
            raise AssertionError('accepted ' + scenario)
        except ValueError as exc:
            negative.append({'scenario': scenario, 'rejected': str(exc)})
        report.write_bytes(c6_raw)

view = 'frontend/src/screens/ff/FfInboundRequestView.tsx'
assert blob(TARGET, view) == blob('593c8a6ee', view) == blob('230cad6f3', view)
before = blob('5ddd09aac', view).decode()
after = blob(TARGET, view).decode()
start, end = '  const printInboundInternalLabels', '  const printInboundBoxLabel'
old_procedure = before[before.index(start):before.index(end)]
new_procedure = after[after.index(start):after.index(end)]
new_procedure = new_procedure.replace("          metadata: target.kind === 'box' ? [\n            `Короб № ${target.number}`,\n            detail?.seller_name?.trim() || '—',\n            `Приёмка ${formatHumanDocumentNumber(detail) ?? '—'} от ${inboundReceiptDate(detail?.created_at)}`,\n          ] : undefined,\n", '')
new_procedure = new_procedure.replace("      // Native decode errors belong to the print iframe's realm and need not\n      // be instances of this window's Error constructor.\n      const message = typeof e === 'object' && e !== null && 'message' in e\n        && typeof e.message === 'string' ? e.message : ''\n      setError(message.trim() ? message : 'Не удалось напечатать этикетки.')", "      setError(e instanceof Error ? e.message : 'Не удалось напечатать этикетки.')")
assert new_procedure == old_procedure
ux = 'frontend/src/screens/v2/fbsUx.ts'
diff = subprocess.check_output(['git', '-C', str(ROOT), 'diff', 'b4b36f648', TARGET, '--', ux]).decode()
assert 'current.color = row.color' in diff and 'order.external_order_id ?? order.wb_order_id' in diff
assert blob(TARGET, ux) == blob('33becfcce', ux)
local = pc.junit_results((HERE / 'targeted.xml').read_bytes())
old_ci = pc.junit_results(blob(TARGET, 'docs/evidence/WMS-652/process-fixes-20261007/ci-shards-process-final.xml'))
old_doc = pc.junit_results(blob(TARGET, 'docs/evidence/WMS-652/process-fixes-20261007/docgate-687.xml'))
for suite, previous_results in [('ci-shards', old_ci), ('docgate-687', old_doc)]:
    required = set(policy['suites'][suite]['cases'])
    introduced = required - set(prior['suites'][suite]['cases'])
    assert introduced <= set(local), (suite, introduced - set(local))
    assert all(local[case] == 'passed' for case in introduced)
    assert set(prior['suites'][suite]['cases']) <= set(previous_results)
    assert all(previous_results[case] == 'passed' for case in prior['suites'][suite]['cases'])
raw_summaries = []
for name, named, aggregate in [('680-graph-green.xml', 4, 19), ('expanded-green.xml', 10, 15),
                              ('process-expanded-regression.xml', 95, 118)]:
    raw = blob(TARGET, evidence + name)
    parsed = pc.junit_results(raw)
    tree = ET.fromstring(raw)
    assert len(parsed) == named and set(parsed.values()) == {'passed'}
    assert int(tree.find('testsuite').get('tests')) == aggregate
    raw_summaries.append({'report': evidence + name, 'named_cases': named,
                          'aggregate_including_subtests': aggregate, 'sha256': hashlib.sha256(raw).hexdigest()})
transition = load('scripts/ci/tests/fixtures/wms652_source_binding_transition.json')
assert transition['final_reviewed_source'] is None
result = {'target': TARGET, 'prior': PRIOR, 'original_source': OLD,
          'paths': len(policy['files']), 'suites': len(policy['suites']), 'cases': 1502,
          'retained_bindings': bindings, 'original_hash_deltas': changed,
          'frozen_test_definitions': frozen, 'new_front_collected': len(front_additions),
          'new_backend_collected': len(back_additions), 'historical_680_673_pass': len(raw72),
          'historical_c6': {'properties': properties, 'sha256': hashlib.sha256(c6_raw).hexdigest()},
          'mandatory_docgate_ids': len(doc_ids), 'c6_negative_receipts': negative,
          'integration_fbsUx_delta': diff, 'historical_raw_summaries': raw_summaries,
          'new_cases_executed_locally': {'ci-shards': 6, 'docgate-687': 15},
          'pending_source_fixture': transition}
# Worker results contain synthetic API response bodies; keep only concise proven facts in our evidence.
result['historical_c6']['properties'] = {k: properties[k] for k in ['first_worker','second_worker','blocking_pids','qr_boundary','wb_create_amounts']}
(HERE / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print('PASS immutable policy/frozen-tests/collection/producers/C6 receipts/integration source audit')
