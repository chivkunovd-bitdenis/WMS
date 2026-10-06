"""Immutable Git/source/receipt accounting only; no tests/build/browser replay."""
import ast
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = '9dae4b19f6d4dca554200e08282579414a110848'
BASE = '4b298efc95be7b4b6b7fe5665be9f3671f1fe747'
OLD = '93b0757103fbd29fb00d4f198f6baab8def85172'
PIN = '0151a555ac429957d0eee591317cc4326e909dfd'
PREVIOUS = 'b82238ec678350f20373bb3f873ac663dcadacd5'
REVIEW = 'bfba7536566962de5c6bb16667b3ce80420d6302'
PRODUCT = '25ebc6fe13384a55cf1f2b7e5e4054bb862d002d'
D618 = 'd61805978b3e7878d1056c99b4e6e0823edf49a5'
ACCEPTANCE = '4eb81c378babf081b3342f3bf36ac17bf136a8bf'
POLICY = 'guards/PROCESS_CONTRACTS.json'
E = 'docs/evidence/WMS-652/'
L = 'docs/evidence/WMS-672/raster-resource-linux-comparison-20261007/raw/'


def git(*args):
    return subprocess.check_output(['git', *args])


def raw(path, ref=SOURCE):
    return git('show', ref + ':' + path)


def obj(path, ref=SOURCE):
    return json.loads(raw(path, ref))


def sha(data):
    return hashlib.sha256(data).hexdigest()


policy = obj(POLICY)
assert set(policy) == {'version', 'files', 'suites'} and policy['version'] == 1
assert git('ls-tree', '-r', '--name-only', BASE, '--', POLICY) == b''
tree = {}
for row in git('ls-tree', '-r', '-z', SOURCE).split(b'\0'):
    if row:
        metadata, path = row.decode().split('\t', 1)
        mode, kind, blob_id = metadata.split()
        tree[path] = (mode, kind, blob_id)
checked = []
for path, expected in policy['files'].items():
    mode, kind, blob_id = tree[path]
    assert kind == 'blob' and mode in {'100644', '100755'}, path
    assert sha(raw(path)) == expected, path
    checked.append({'path': path, 'mode': mode, 'blob': blob_id, 'sha256': expected})
assert len(checked) == 229 and len(policy['suites']) == 21
assert sum(len(s['cases']) for s in policy['suites'].values()) == 1173
assert len({s['report'] for s in policy['suites'].values()}) == 21
for suite in policy['suites'].values():
    assert set(suite) == {'report', 'format', 'exact', 'cases'}
    assert len(set(suite['cases'])) == len(suite['cases'])
comparisons = []
for ref, expected_files, expected_cases in [(OLD, 210, 955), (PIN, 222, 1146), (PREVIOUS, 229, 1173)]:
    prior = obj(POLICY, ref)
    assert len(prior['files']) == expected_files
    assert sum(len(s['cases']) for s in prior['suites'].values()) == expected_cases
    assert prior['files'].keys() <= policy['files'].keys()
    for name, suite in prior['suites'].items():
        current = policy['suites'][name]
        assert all(current[k] == suite[k] for k in ['format', 'exact', 'report'])
        assert set(suite['cases']) <= set(current['cases'])
    changed = [{'path': p, 'before_sha256': d, 'after_sha256': policy['files'][p]}
               for p, d in prior['files'].items() if policy['files'][p] != d]
    comparisons.append({'ref': ref, 'retained_files': expected_files, 'retained_cases': expected_cases,
                        'changed_old_hashes': changed,
                        'added_paths': sorted(policy['files'].keys() - prior['files'].keys())})
assert [r['path'] for r in comparisons[0]['changed_old_hashes']] == [
    '.github/workflows/ci.yml', 'frontend/tests-e2e/wms652-critical/browser.mjs',
    'frontend/tests-e2e/wms652-critical/cases.json', 'scripts/ops/tests/wms517-mac-dom.test.cjs',
    'scripts/ops/tests/wms517-mac-launcher.test.cjs']
assert [r['path'] for r in comparisons[1]['changed_old_hashes']] == ['.github/workflows/ci.yml']
assert [r['path'] for r in comparisons[2]['changed_old_hashes']] == ['.github/workflows/ci.yml']
assert policy['suites'] == obj(POLICY, PREVIOUS)['suites']
for path in policy['files']:
    if path != '.github/workflows/ci.yml':
        assert raw(path) == raw(path, PREVIOUS), path
workflow = raw('.github/workflows/ci.yml')
assert workflow.count(PRODUCT.encode()) == 1
assert workflow.replace(PRODUCT.encode(), D618.encode()) == raw('.github/workflows/ci.yml', PREVIOUS)
for p in ['AGENTS.md', 'CLAUDE.md', 'docs/reviews/2026-09-11-analyst-draft/owner-cases.md',
          'docs/reviews/2026-09-11-analyst-draft/failure-cases.md']:
    assert raw(p) == raw(p, PREVIOUS)
assert raw('AGENTS.md', BASE) == raw('AGENTS.md') == raw('CLAUDE.md')
for p in ['scripts/ci/product_scope.py', 'scripts/ci/tests/test_product_scope.py']:
    assert raw(p) == raw(p, PIN) == raw(p, PREVIOUS)
assert len(policy['suites']['product-scope']['cases']) == 51
app_paths = ['backend/app', 'backend/alembic', 'frontend/src', 'frontend/package.json', 'frontend/package-lock.json']
assert git('diff', '--name-only', PRODUCT, SOURCE, '--', *app_paths) == b''
changed_app = git('diff', '--name-only', D618, SOURCE, '--', *app_paths).decode().splitlines()
assert set(changed_app) == {'frontend/src/utils/printBarcodeLabel.ts', 'frontend/src/screens/ff/FfInboundRequestView.tsx'}
acceptance_path = 'docs/evidence/WMS-672/raster-resource-analyst-acceptance-20261007/acceptance.json'
acceptance = obj(acceptance_path, ACCEPTANCE)
assert raw(acceptance_path) == raw(acceptance_path, ACCEPTANCE)
assert acceptance['product_reference_approval']['to'] == PRODUCT and acceptance['review_commit'] == REVIEW
for p in acceptance['product_paths']:
    assert sha(raw(p['path'])) == p['sha256'] and tree[p['path']][2] == p['blob']


def junit(path, ref=SOURCE):
    tree_xml = ET.fromstring(raw(path, ref))
    rows = list(tree_xml.iter('testcase'))
    assert rows and not any(list(tree_xml.iter(tag)) for tag in ['failure', 'error', 'skipped'])
    names = [f"{r.get('classname', '')}::{r.get('name', '')}" for r in rows]
    assert len(names) == len(set(names))
    return names


def tap(path):
    text = raw(path).decode()
    rows = re.findall(r'^(ok|not ok) (\d+) - (.+)$', text, re.M)
    assert rows and all(status == 'ok' for status, _, _ in rows)
    assert [int(n) for _, n, _ in rows] == list(range(1, len(rows) + 1))
    assert re.findall(r'^1\.\.(\d+)$', text, re.M) == [str(len(rows))]
    assert all(re.findall(r'^# ' + k + r' (\d+)$', text, re.M) == ['0'] for k in ['fail', 'cancelled', 'skipped', 'todo'])
    names = [name for _, _, name in rows]
    assert len(names) == len(set(names)) and not any(re.search(r'\s+#\s*(SKIP|TODO)', n, re.I) for n in names)
    return names


receipts = []
for path in [E + 'process-gates-20261006/integrated-ci-scope-71.xml',
             E + 'process-gates-20261006/integrated-mac-110.tap',
             E + 'critical-fbs-contracts-20261006/geometry-final-green/result.json']:
    assert raw(path) == raw(path, PIN) == raw(path, PREVIOUS)
    receipts.append({'path': path, 'sha256': sha(raw(path)), 'unchanged_from_0151': True})
combined = junit(receipts[0]['path'])
assert set(combined) == set(policy['suites']['ci-shards']['cases'] + policy['suites']['product-scope']['cases'])
assert len(combined) == 71
assert tap(receipts[1]['path']) == policy['suites']['mac-517-helper']['cases']
browser = obj(receipts[2]['path'])
assert browser['status'] == 'PASS' and all(c['status'] == 'PASS' for c in browser['cases'])
assert [c['id'] for c in browser['cases']] == policy['suites']['real-fbs-browser']['cases']
assert len(browser['cases']) == 43
for name, report, n in [('print-672-native-errors', '672-native-errors.tap', 7),
                        ('print-672-peer-drain', '672-peer-drain.tap', 2),
                        ('print-672-raster-resource', '672-raster-resource.tap', 3)]:
    names = tap(L + report)
    assert len(names) == n and names == policy['suites'][name]['cases']
    assert raw(L + report) == raw(L + report, PREVIOUS)
    receipts.append({'path': L + report, 'sha256': sha(raw(L + report)), 'cases': n, 'pass': n, 'skip': 0})
assert len(tap(L + '672-c5.tap')) == 1 and raw(L + '672-c5.tap') == raw(L + '672-c5.tap', PREVIOUS)
backup = 'backend/tests/test_prod_deploy_backup.py'
new_backup = 'backend/tests/test_prod_deploy_backup_gate_boundary.py'
assert raw(backup) == raw(backup, 'd736a02427c916979b2117ebecc1ace10dc9cc07')
assert raw(new_backup) == raw(new_backup, '030d75c01549b32a67ed4af405fea984b5974025')
fn = next(n for n in ast.parse(raw(backup)).body if isinstance(n, ast.FunctionDef)
          and n.name == 'test_deploy_requires_verified_backup_before_migration')
params = next(n for n in fn.decorator_list if isinstance(n, ast.Call))
assert ast.literal_eval(params.args[1]) == ['', 'dump', 'archive', 'listing', 'empty', 'network', 'retry']
assertions = [ast.dump(n, include_attributes=False) for n in ast.walk(fn) if isinstance(n, ast.Assert)]
assert len(assertions) == 23 and sha(json.dumps(assertions, ensure_ascii=False).encode()) == 'ddbfe3e8447dd54825fadf01f437a1adb6fa18f2ed583f58172cb1ed962fc3da'
backup_report = E + 'backup-fixture-independent-review-20261007/targeted.xml'
backup_cases = junit(backup_report)
assert len(backup_cases) == 15 and set(backup_cases) <= set(policy['suites']['backend-fbs']['cases'])
assert sum('test_prod_deploy_backup_gate_boundary::' in n for n in backup_cases) == 6
receipts.append({'path': backup_report, 'sha256': sha(raw(backup_report)), 'cases': 15, 'new_cases': 6, 'skip': 0})
for p in ['scripts/ci/trusted_process_check.py', '.github/workflows/process-integrity.yml']:
    assert raw(p, '045272b51f28829b6220410856e9216a3054ce33') == raw(p, '4e7b8abf12077e9e100730c6557507dc20a665b2')
assert raw('scripts/ci/trusted_process_check.py', '045272b51f28829b6220410856e9216a3054ce33') == raw('scripts/ci/trusted_process_check.py', 'b096cd12916e63e8ee7507f508f00dd8526c15fa')
saved_barriers = []
for p in [E + 'process-gates-20261006/installed-independent-anchor.json',
          E + 'process-gates-20261006/actual-negative-canary.json',
          E + 'process-gates-20261006/production-entry-protection.md',
          E + 'process-gates-20261006/production-env-canary-job.json']:
    assert raw(p) == raw(p, PREVIOUS)
    saved_barriers.append({'path': p, 'sha256': sha(raw(p)), 'unchanged_from_b822': True})
result = subprocess.run([sys.executable, '-c', raw('scripts/ci/product_scope.py').decode(),
                         '--root', str(Path.cwd()), '--trusted-ref', PRODUCT],
                        capture_output=True, text=True, check=False)
assert result.returncode == 0 and json.loads(result.stdout) == {'unapproved_product_paths': []}, result.stderr
output = {'verdict': 'APPROVE exact BASE/SOURCE pair only',
          'approvedBootstrap': {'base_sha': BASE, 'source_sha': SOURCE},
          'accepted_product_reference': PRODUCT, 'policySha256': sha(raw(POLICY)),
          'protectedFiles': 229, 'suites': 21, 'exactCases': 1173,
          'verified_regular_blobs': checked, 'comparisons': comparisons,
          'all_other_228_protected_blobs_unchanged_since_b822': True,
          'all_21_suite_definitions_unchanged_since_b822': True,
          'scope51_and_cli_unchanged': True, 'scope_cli_exit': result.returncode,
          'scope_cli_output': json.loads(result.stdout), 'product_delta_from_d618': changed_app,
          'product_delta_from_25eb': [], 'analyst_acceptance': ACCEPTANCE,
          'preserved_receipts': receipts, 'saved_barriers': saved_barriers,
          'previous_review_preserved': REVIEW,
          'tests_build_browser_C5_repeated': False, 'main_config_edited': False,
          'final_pin_activation_fullCI_deploy_physical_claimed': False}
(HERE / 'source-pin-probe.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: v for k, v in output.items() if k in {'verdict', 'approvedBootstrap', 'policySha256',
                  'protectedFiles', 'suites', 'exactCases', 'scope_cli_exit', 'scope_cli_output'}}, indent=2))
