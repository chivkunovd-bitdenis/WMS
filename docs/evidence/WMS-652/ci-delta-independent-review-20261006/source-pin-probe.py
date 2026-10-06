"""Read immutable Git blobs only; no test, browser or external mutation."""
import hashlib
import json
import subprocess
from pathlib import Path

from scripts.ci.process_contracts import junit_results, node_tap_results, validate_policy

ROOT = Path(__file__).resolve().parents[4]
SOURCE = '0151a555ac429957d0eee591317cc4326e909dfd'
BASE = '4b298efc95be7b4b6b7fe5665be9f3671f1fe747'
OLD = '93b0757103fbd29fb00d4f198f6baab8def85172'
POLICY = 'guards/PROCESS_CONTRACTS.json'
EVIDENCE = 'docs/evidence/WMS-652/'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def raw(sha, path):
    return git('show', sha + ':' + path)


source = json.loads(raw(SOURCE, POLICY))
prior = json.loads(raw(OLD, POLICY))
validate_policy(source)
assert git('ls-tree', '-r', '--name-only', BASE, '--', POLICY) == b''
assert len(source['files']) == 222 and len(prior['files']) == 210
assert set(prior['files']) <= set(source['files'])
for path, digest in source['files'].items():
    entry = git('ls-tree', SOURCE, '--', path).decode().strip().split()
    assert entry[:2] in [['100644', 'blob'], ['100755', 'blob']], path
    assert hashlib.sha256(raw(SOURCE, path)).hexdigest() == digest, path
assert sum(len(s['cases']) for s in source['suites'].values()) == 1146
assert sum(len(s['cases']) for s in prior['suites'].values()) == 955
for name, suite in prior['suites'].items():
    current = source['suites'][name]
    assert all(current[key] == suite[key] for key in ['format', 'exact', 'report'])
    assert set(suite['cases']) <= set(current['cases'])
changed = [path for path in prior['files'] if prior['files'][path] != source['files'][path]]
assert changed == ['.github/workflows/ci.yml',
                   'frontend/tests-e2e/wms652-critical/browser.mjs',
                   'frontend/tests-e2e/wms652-critical/cases.json',
                   'scripts/ops/tests/wms517-mac-dom.test.cjs',
                   'scripts/ops/tests/wms517-mac-launcher.test.cjs']
# The integration changes hashes for already independently reviewed bytes.
for path in ['.github/workflows/ci.yml', 'scripts/ci/backend_shards.py',
             'scripts/ci/product_scope.py']:
    assert raw(SOURCE, path) == raw(OLD, path)
for path in ['browser.mjs', 'cases.json', 'geometry.mjs', 'geometry-mutations.py']:
    full = 'frontend/tests-e2e/wms652-critical/' + path
    assert raw(SOURCE, full) == raw('1c045a4f2', full)
closure = git('ls-tree', '-r', '--name-only', SOURCE, '--',
              'frontend/tests-e2e/wms652-critical').decode().splitlines()
assert len(closure) == 12 and set(closure) <= set(source['files'])
assert 'docs/evidence/WMS-652/ci-two-shards-20261006/backend-collection.json' in source['files']
for path in ['scripts/ops/avpack-macos-launcher.js', 'scripts/ops/avpack-sold-kiz-filter.js',
             'scripts/ops/avpack-sold-kiz.command', 'scripts/ops/build-avpack-macos-command.cjs',
             'scripts/ops/tests/wms517-mac-dom.test.cjs', 'scripts/ops/tests/wms517-mac-launcher.test.cjs',
             'scripts/ops/tests/wms517-sold-kiz-filter.test.cjs']:
    assert raw(SOURCE, path) == raw('7a2fa31d83e06b2724edbcca1aaead0914ad5e56', path), path
reports = {
    'ci-shards': EVIDENCE + 'ci-two-shards-20261006/ci-shards.xml',
    'product-scope': EVIDENCE + 'ci-two-shards-20261006/product-scope.xml',
    'mac-517-helper': EVIDENCE + 'process-gates-20261006/integrated-mac-110.tap',
}
for name, path in reports.items():
    suite = source['suites'][name]
    parser = node_tap_results if suite['format'] == 'node-tap' else junit_results
    actual = parser(raw(SOURCE, path))
    assert set(actual) == set(suite['cases'])
    assert all(value == 'passed' for value in actual.values())
combined = junit_results(raw(SOURCE, EVIDENCE + 'process-gates-20261006/integrated-ci-scope-71.xml'))
assert set(combined) == set(source['suites']['ci-shards']['cases'] + source['suites']['product-scope']['cases'])
assert all(value == 'passed' for value in combined.values())
browser = json.loads(raw(SOURCE, EVIDENCE + 'critical-fbs-contracts-20261006/geometry-final-green/result.json'))
ids = json.loads(raw(SOURCE, 'frontend/tests-e2e/wms652-critical/cases.json'))
assert browser['sha'] == '1c045a4f2d6c1bb34eeed2f5e79f6e53be2a8a9d'
assert browser['status'] == 'PASS' and [case['id'] for case in browser['cases']] == ids
assert ids == source['suites']['real-fbs-browser']['cases']
assert all(case['status'] == 'PASS' for case in browser['cases'])
ci = raw(SOURCE, '.github/workflows/ci.yml').decode()
for command in ['python scripts/ci/product_scope.py --root . --trusted-ref d61805978b3e7878d1056c99b4e6e0823edf49a5',
                'python -m pytest -q scripts/ci/tests/test_product_scope.py --junitxml=',
                'python -m pytest -q scripts/ci/tests/test_backend_shards.py',
                'node --test --test-reporter=tap', 'scripts/ops/tests/wms517-mac-dom.test.cjs',
                'scripts/ops/tests/wms517-mac-launcher.test.cjs',
                'scripts/ops/tests/wms517-sold-kiz-filter.test.cjs',
                'python scripts/ci/build_process_proof.py --reports']:
    assert command in ci, command
for report in ['ci-shards.xml', 'product-scope.xml', 'wms517-mac.tap']:
    assert report in ci
assert git('diff', '--name-only', 'd61805978b3e7878d1056c99b4e6e0823edf49a5', SOURCE,
           '--', 'backend/app', 'backend/alembic', 'frontend/src', 'frontend/package.json',
           'frontend/package-lock.json') == b''
print(json.dumps(dict(approvedBootstrap=dict(base_sha=BASE, source_sha=SOURCE),
                     policySha256=hashlib.sha256(raw(SOURCE, POLICY)).hexdigest(),
                     protectedFiles=222, exactCases=1146, oldFilesPreserved=210,
                     oldCasesPreserved=955, changedPriorHashes=changed,
                     protectedBrowserClosure=len(closure), fixtureClosureFixed=True,
                     actualNewReports=dict(shards=20, scope=51, mac=110, browser=43),
                     fullCiOrActivationClaimed=False), indent=2))
