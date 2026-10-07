"""Independent, bounded WMS-652 review probes; no production or policy writes.

Run from the reviewed checkout after producing this directory's raw TAP/JUnit.
Mutated receipts below are adversarial in-memory fixtures, never release proof.
"""
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

import yaml

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.ci import process_contracts as pc
from scripts.ci import verify_process_ci as gate
from scripts.ci.tests.test_process_deploy_gate import EvidenceFixture
from scripts.ci.tests.test_verify_ci import REPO, SHA

HERE = Path(__file__).resolve().parent
TARGET = '14c340a76db5f77c248794183b44d8b13880ef81'
OLD = '0151a555ac429957d0eee591317cc4326e909dfd'
BASE = '4b298efc95be7b4b6b7fe5665be9f3671f1fe747'
P = 'd61805978b3e7878d1056c99b4e6e0823edf49a5'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def blob(ref, path):
    return git('show', f'{ref}:{path}')


def rejected(callback, expected):
    try:
        callback()
    except (ValueError, gate.GateError) as exc:
        return {'probe': expected, 'rejected': True, 'reason': str(exc)}
    raise AssertionError(f'Accepted negative: {expected}')


assert git('rev-parse', 'HEAD').decode().strip() == TARGET
old = json.loads(blob(OLD, pc.POLICY_PATH))
new = json.loads(blob(TARGET, pc.POLICY_PATH))
pc.validate_policy(old)
pc.validate_policy(new)
assert (len(old['files']), len(old['suites']), sum(len(s['cases']) for s in old['suites'].values())) == (222, 18, 1146)
assert (len(new['files']), len(new['suites']), sum(len(s['cases']) for s in new['suites'].values())) == (225, 19, 1161)
delta = []
for path, digest in old['files'].items():
    assert hashlib.sha256(blob(OLD, path)).hexdigest() == digest
    assert path in new['files']
    old_mode = git('ls-tree', OLD, '--', path).decode().split()[0]
    new_mode = git('ls-tree', TARGET, '--', path).decode().split()[0]
    assert old_mode == new_mode
    if new['files'][path] != digest:
        delta.append(path)
    else:
        assert blob(OLD, path) == blob(TARGET, path)
assert sorted(delta) == ['.github/workflows/ci.yml', 'scripts/ci/tests/test_ci_release_additions.py']
new_files = sorted(set(new['files']) - set(old['files']))
assert new_files == ['docs/mockups/WMS-686/model.test.ts', 'scripts/ci/tests/fixtures/wms652_source_binding_transition.json', 'scripts/ci/tests/fixtures/wms686_raw_receipt_contract.json']
assert blob(TARGET, 'docs/mockups/WMS-686/model.test.ts') == blob('ed4b88703', 'docs/mockups/WMS-686/model.test.ts')
assert blob(TARGET, 'docs/mockups/WMS-686/model.test.ts') == blob('0d054a2256322428e815ed78fc8d149b0c140aa6', 'docs/mockups/WMS-686/model.test.ts')
for original, imported in [('1ab749', '72e4fde'), ('5ca749', '977aa7')]:
    paths = git('diff-tree', '--no-commit-id', '--name-only', '-r', original).decode().splitlines()
    for path in paths:
        if path.startswith('scripts/ci/tests/'):
            assert blob(original, path) == blob(imported, path)
for path in ['scripts/ci/tests/test_ci_release_additions.py', *[p for p in new_files if p.startswith('scripts/')]]:
    assert blob(TARGET, path) == blob('977aa7', path)
additions = {}
for name, suite in old['suites'].items():
    current = new['suites'][name]
    assert all(current[k] == suite[k] for k in ('report', 'format', 'exact'))
    assert [c for c in current['cases'] if c in suite['cases']] == suite['cases']
    additions[name] = [c for c in current['cases'] if c not in suite['cases']]
assert {k: len(v) for k, v in additions.items() if v} == {'ci-shards': 4}
assert set(new['suites']) - set(old['suites']) == {'wms686-model'}
additions['wms686-model'] = new['suites']['wms686-model']['cases']

old_jobs = yaml.safe_load(blob(OLD, '.github/workflows/ci.yml'))['jobs']
jobs = yaml.safe_load(blob(TARGET, '.github/workflows/ci.yml'))['jobs']
for name, job in old_jobs.items():
    if name != 'process-proof':
        assert jobs[name] == job, name
proof = copy.deepcopy(jobs['process-proof'])
assert proof.pop('needs') == [*old_jobs['process-proof']['needs'], 'wms686-mockup']
download = [s for s in proof['steps'] if s.get('with', {}).get('name', '').startswith('wms686-executed-contracts-')]
assert len(download) == 1
proof['steps'].remove(download[0])
previous = copy.deepcopy(old_jobs['process-proof'])
previous.pop('needs')
assert proof == previous
model_job = jobs['wms686-mockup']
assert 'if' not in model_job and not model_job.get('continue-on-error', False)
assert not any(s.get('continue-on-error', False) for s in model_job['steps'])
setup = [s for s in model_job['steps'] if s.get('uses') == 'actions/setup-node@v4']
assert len(setup) == 1 and str(setup[0]['with']['node-version']) == '24'
commands = [s['run'] for s in model_job['steps'] if 'run' in s]
assert commands[1] == 'node --test --test-reporter=tap docs/mockups/WMS-686/model.test.ts > "$RUNNER_TEMP/wms686-model.tap"'
artifact = 'wms686-executed-contracts-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}'
upload = [s for s in model_job['steps'] if s.get('uses') == 'actions/upload-artifact@v4']
assert len(upload) == 1 and upload[0]['if'] == 'always()'
assert upload[0]['with']['name'] == download[0]['with']['name'] == artifact
assert upload[0]['with']['path'] == '${{ runner.temp }}/wms686-model.tap'
assert upload[0]['with']['if-no-files-found'] == 'error'
assert download[0]['uses'] == 'actions/download-artifact@v4'
assert download[0]['with']['path'] == '${{ runner.temp }}/process-proof'
assert set(jobs['process-proof']['needs']) == set(old_jobs['process-proof']['needs']) | {'wms686-mockup'}
assert 'if' not in jobs['process-proof'] and not jobs['process-proof'].get('continue-on-error', False)

binding = json.loads(blob(TARGET, 'scripts/ci/tests/fixtures/wms652_source_binding_transition.json'))
assert binding['status'] == 'pending-final-independent-freeze' and binding['final_reviewed_source'] is None
assert binding['current_reviewed_source'] == P and binding['accepted_reviewed_sources'] == [P]
guard_commands = '\n'.join(s.get('run', '') for s in jobs['guards']['steps'])
assert re.findall(r'product_scope.py --root . --trusted-ref (\S+)', guard_commands) == [P]

negatives = []
assert len(pc.verify_integrity(ROOT, BASE, bootstrap=True)['files']) == 225
assert len(pc.verify_integrity(ROOT, TARGET)['files']) == 225
negatives.append(rejected(lambda: pc.verify_integrity(ROOT, OLD), 'old SOURCE rejects updated protected hashes'))
raw = (HERE / 'wms686-model.tap').read_bytes()
suite = new['suites']['wms686-model']
assert len(pc.node_tap_results(raw)) == 11
for report_dir in [HERE, ROOT / 'docs/evidence/WMS-652/night1007-integration/process-wiring-20261007']:
    actual = pc.verify_reports({'version': 1, 'files': {}, 'suites': {k: new['suites'][k] for k in ['ci-shards', 'wms686-model']}}, report_dir)
    assert {k: len(v) for k, v in actual.items()} == {'ci-shards': 24, 'wms686-model': 11}
with tempfile.TemporaryDirectory(prefix='wms652-review-negative-') as temporary:
    report_root = Path(temporary)
    policy = {'version': 1, 'files': {}, 'suites': {'wms686-model': suite}}
    path = report_root / suite['report']
    negatives.append(rejected(lambda: pc.verify_reports(policy, report_root), 'missing actual TAP receipt'))
    name = suite['cases'][0].encode()
    mutations = {
        'empty': b'',
        'malformed': b'not TAP',
        'same-count-wrong-case': raw.replace(b'ok 1 - ' + name, b'ok 1 - unrelated'),
        'failed-case-even-with-zero-summary': raw.replace(b'\nok 1 - ', b'\nnot ok 1 - ', 1),
        'skipped-case': raw.replace(b'ok 1 - ' + name, b'ok 1 - ' + name + b' # SKIP'),
        'todo-case': raw.replace(b'ok 1 - ' + name, b'ok 1 - ' + name + b' # TODO'),
        'missing-plan': raw.replace(b'1..11\n', b''),
        'incorrect-plan': raw.replace(b'1..11\n', b'1..10\n'),
        'missing-summary': raw.replace(b'# cancelled 0\n', b''),
        'nonzero-summary': raw.replace(b'# fail 0\n', b'# fail 1\n'),
        'duplicate-case': raw.replace(b'ok 2 - ' + suite['cases'][1].encode(), b'ok 2 - ' + name),
        'extra-case-valid-plan': raw.replace(b'1..11\n', b'ok 12 - unrelated\n1..12\n').replace(b'# tests 11\n', b'# tests 12\n').replace(b'# pass 11\n', b'# pass 12\n'),
    }
    for label, receipt in mutations.items():
        path.write_bytes(receipt)
        negatives.append(rejected(lambda: pc.verify_reports(policy, report_root), label))
    path.unlink()
    path.symlink_to(HERE / 'wms686-model.tap')
    negatives.append(rejected(lambda: pc.verify_reports(policy, report_root), 'symlink receipt'))

# Exercise the unchanged full artifact reader with real TAP bytes. API identity
# and metadata here are explicitly synthetic; they do not claim an Actions run.
fixture = EvidenceFixture()
fixture.policy = {'version': 1, 'files': {}, 'suites': {'wms686-model': suite}}
fixture.policy_bytes = json.dumps(fixture.policy, sort_keys=True).encode()
fixture.metadata['policy_sha256'] = hashlib.sha256(fixture.policy_bytes).hexdigest()
def archive_with_tap(include=True):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('execution.json', json.dumps(fixture.metadata))
        if include:
            archive.writestr('wms686-model.tap', raw)
    return stream.getvalue()
def verify_archive(include=True):
    return gate.verify_execution(fixture.get, lambda _: archive_with_tap(include), REPO, SHA, fixture.policy_bytes)
assert verify_archive()['executed_cases'] == 11
negatives.append(rejected(lambda: verify_archive(False), 'artifact reader: missing real TAP member'))
for key, value in [('sha', 'b'*40), ('head_sha', 'b'*40), ('run_id', 11), ('run_attempt', 2), ('policy_sha256', '0'*64)]:
    original = fixture.metadata[key]
    fixture.metadata[key] = value
    negatives.append(rejected(verify_archive, 'artifact reader: wrong ' + key))
    fixture.metadata[key] = original
original = fixture.artifacts[0]['name']
fixture.artifacts[0]['name'] = f'process-proof-{SHA}-10-2'
negatives.append(rejected(verify_archive, 'artifact reader: other attempt artifact'))
fixture.artifacts[0]['name'] = original

result = {
    'reviewed_sha': TARGET, 'old_source': OLD, 'base': BASE,
    'old': {'files': 222, 'suites': 18, 'cases': 1146},
    'current': {'files': 225, 'suites': 19, 'cases': 1161},
    'all_old_ids_in_order_preserved': True, 'old_suite_semantics_preserved': True,
    'existing_protected_hash_delta': delta, 'new_protected_files': new_files,
    'old_protected_modes_preserved': True, '220_other_old_protected_blobs_unchanged': True,
    'tester_commits_byte_equivalent_and_unchanged_by_developer': True,
    'frozen_model_equals_original_test_commit': True,
    'old_workflow_jobs_and_producers_preserved': True,
    'required_producers': jobs['process-proof']['needs'],
    'additions': {k: v for k, v in additions.items() if v},
    'old_case_ids': {k: v['cases'] for k, v in old['suites'].items()},
    'partial_actual_raw_reports_verified': {'ci-shards': 24, 'wms686-model': 11},
    'real_TAP_read_through_artifact_verifier_with_synthetic_API_identity': True,
    'runtime': {'node': subprocess.check_output(['node', '--version'], text=True).strip(), 'python': sys.version.split()[0]},
    'negative_receipts': negatives,
    'product_reference_P': P, 'final_P': 'pending', 'final_S': 'pending',
    'synthetic_negatives_are_not_release_receipts': True,
    'full_CI_or_final_release_approval': False,
}
(HERE / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k not in ['old_case_ids', 'additions']}, ensure_ascii=False, indent=2))
