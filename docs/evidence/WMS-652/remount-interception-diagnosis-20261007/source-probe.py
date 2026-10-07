#!/usr/bin/env python3
"""Offline saved-receipt/source diagnosis. No test, browser, network or source mutation."""
import collections
import hashlib
import json
from pathlib import Path
import subprocess

BASE = '55d8d08aa11adbb111ec4a999b59b6e59cdbfb1b'
HEAD = 'eabfad3656ec7ac923c6014657d4bf8ba5e63400'
MERGE = 'ac845328b27b5be265962695e10766efddef339e'
ETALON = '4b298efc95be7b4b6b7fe5665be9f3671f1fe747'
OLD = 'd61805978b3e7878d1056c99b4e6e0823edf49a5'
ACCEPTED = '9dae4b19f6d4dca554200e08282579414a110848'
RAW = 'docs/evidence/WMS-652/common-ci-37548248403/print/'
BROWSER = 'frontend/tests-e2e/wms652-critical/browser.mjs'
inputs = []


def git(*args):
    return subprocess.check_output(['git', *args], stderr=subprocess.DEVNULL)


def read(sha, path):
    raw = git('show', sha + ':' + path)
    inputs.append({'sha': sha, 'path': path, 'bytes': len(raw),
                   'blob': git('rev-parse', sha + ':' + path).decode().strip(),
                   'sha256': hashlib.sha256(raw).hexdigest()})
    return raw


def changed(a, b, *paths):
    return git('diff', '--name-only', a, b, '--', *paths).decode().splitlines()


browser = read(BASE, BROWSER)
assert browser == read(HEAD, BROWSER) == read(ACCEPTED, BROWSER)
lines = browser.decode().splitlines()
ids = json.loads(read(BASE, 'frontend/tests-e2e/wms652-critical/cases.json'))
assert ids == json.loads(read(HEAD, 'frontend/tests-e2e/wms652-critical/cases.json'))
result = json.loads(read(BASE, RAW + 'critical-fbs/result.json'))
assert [c['id'] for c in result['cases']] == ids and len(ids) == 43
assert result['sha'] == MERGE
counts = dict(collections.Counter(c['status'] for c in result['cases']))
assert counts == {'PASS': 42, 'FAIL': 1}
download = json.loads(read(BASE, RAW + 'download.json'))
assert download['tested_sha'] == MERGE and download['artifact_id'] == 11451563468
job = read(BASE, RAW + 'job.log').decode().splitlines()
assert len(read(BASE, RAW + 'job.log')) == 151768
cases = []
for suffix in ['supply_id-A', 'supply_ids-A', 'supply_ids-A-B']:
    path = RAW + 'critical-fbs/WMS652-realQrFlags-remount-after-lost-ack-' + suffix + '-.json'
    case = json.loads(read(BASE, path))
    requests = case['requestLog']
    selections = [r for r in requests if r['path'].endswith('/scan-auto-print')
                  and (r['body'] or {}).get('order_id')]
    packs = [r for r in requests if r['path'].endswith('/pack')]
    commits = [r for r in requests if r['path'] == '/operations/fbs-orders/kiz/commit']
    jobs = [{'key': j['idempotencyKey'], 'widthMm': j['widthMm'], 'heightMm': j['heightMm'],
             'image_data_url_sha256': hashlib.sha256(j['imageDataUrl'].encode()).hexdigest()}
            for j in case['printLog']]
    cases.append({'entry': suffix, 'raw_path': path, 'request_count': len(requests),
                  'blocked': case['blocked'], 'errors': case['errors'], 'trace': case['trace'],
                  'selections': selections, 'commits': commits, 'packs': packs,
                  'print_jobs_without_base64': jobs, 'accepted_print_keys': case['acceptedPrintKeys'],
                  'restored_selection_reuses_nonempty_initial_key': bool(selections[0]['body']['idempotency_key'])
                  and selections[0]['body']['idempotency_key'] == selections[1]['body']['idempotency_key'],
                  'request_counts': [{'method': m, 'path': p, 'count': n} for (m, p), n in sorted(
                      collections.Counter((r['method'], r['path'].split('?')[0]) for r in requests).items())]})
assert cases[0]['blocked'] == []
assert cases[0]['errors'] == ['Error: {"code":-32602,"message":"Invalid InterceptionId."}']
assert cases[1]['errors'] == cases[2]['errors'] == []
assert cases[0]['trace'] == cases[1]['trace'] == cases[2]['trace']
assert cases[0]['print_jobs_without_base64'] == cases[1]['print_jobs_without_base64'] == cases[2]['print_jobs_without_base64']
assert cases[0]['packs'] == cases[1]['packs']
product_changes = changed(OLD, HEAD, 'frontend/src', 'backend/app')
assert product_changes == ['frontend/src/screens/ff/FfInboundRequestView.tsx', 'frontend/src/utils/printBarcodeLabel.ts']
assert changed(HEAD, BASE, 'frontend/src', 'backend/app', 'frontend/tests-e2e/wms652-critical') == []
subprocess.run(['git', 'merge-base', '--is-ancestor', ETALON, HEAD], check=True)
merge_available = subprocess.run(['git', 'cat-file', '-e', MERGE + '^{commit}'],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
for path in ['frontend/tests-e2e/wms652-critical/main.tsx', 'scripts/ci/run_critical_fbs_browser.sh',
             'frontend/src/screens/v2/FfFbsOrdersScreen.tsx', 'frontend/src/screens/v2/fbsSequentialPacking.ts',
             'frontend/src/utils/printDirectQr.ts']:
    assert read(BASE, path) == read(HEAD, path)
    if path.startswith('frontend/src/'):
        assert read(HEAD, path) == read(OLD, path)
tap_counts = {}
for name, n in [('672.tap', 11), ('672-remaining.tap', 6), ('672-native-errors.tap', 7),
                ('672-peer-drain.tap', 2), ('672-raster-resource.tap', 3)]:
    raw = read(BASE, RAW + name).decode()
    values = {key: [(float if key == 'duration_ms' else int)(l.split()[-1]) for l in raw.splitlines() if l.startswith('# ' + key + ' ')]
              for key in ['tests', 'pass', 'fail', 'cancelled', 'skipped', 'todo', 'duration_ms']}
    assert values['tests'] == values['pass'] == [n]
    assert all(values[k] == [0] for k in ['fail', 'cancelled', 'skipped', 'todo'])
    tap_counts[name] = values
out = {'verdict': 'PROTOCOL_LISTENER_FAILURE_CONFIRMED; EXACT_REQUEST_AND_CANCELLATION_CAUSE_UNPROVEN',
       'immutable_evidence_base': BASE, 'ci_head': HEAD, 'tested_merge': MERGE,
       'run': 37548248403, 'attempt': 1, 'job': 112557363776, 'artifact': download,
       'tested_merge_object_available_locally': merge_available,
       'source_binding': 'Local CI head read directly; saved checkout log identifies merge of head into ancestor etalon. Merge blob not directly available; no fetch performed.',
       'etalon_is_ancestor_of_ci_head': True, 'browser_equal_base_head_accepted9dae': True,
       'frozen_case_count': len(ids), 'case_ids_sha256': hashlib.sha256(json.dumps(ids).encode()).hexdigest(),
       'result_counts': counts, 'failed_cases': [c for c in result['cases'] if c['status'] == 'FAIL'],
       'business_assertions_reached_before_line444': 'Inferred from sequential source and final 1!==0 with blocked=[]/errors length1; raw business observations agree. Intermediate pre-remount timing/storage values are not separately logged.',
       'cases': cases, 'product_changes_vs_d618': product_changes,
       'product_and_critical_fixture_diff_ci_head_to_evidence_base': [], 'saved_tap_counts': tap_counts,
       'source_excerpts': {str(a) + '-' + str(b): '\n'.join(f'{i}: {lines[i-1]}' for i in range(a, b+1))
                           for a, b in [(33,47), (60,63), (75,91), (159,162), (388,403), (437,447)]},
       'raw_job_excerpts': {str(i): job[i-1] for i in [669,672,932,1235,1237,1239,1240,1251,1252,1289]},
       'inputs': list({(i['sha'], i['path']): i for i in inputs}.values()),
       'new_executions': {'tests': 0, 'browser': 0, 'build': 0, 'dispatch': 0},
       'source_pin_approved': False, 'fixture_fix_approved': False, 'release_approved': False}
Path(__file__).with_name('source-checks.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
print('Offline diagnosis recorded: 43 saved cases = 42 PASS / 1 protocol-collector FAIL; no test execution.')
