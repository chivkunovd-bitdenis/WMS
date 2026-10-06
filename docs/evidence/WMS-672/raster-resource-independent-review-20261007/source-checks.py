"""Bounded immutable Git/source/receipt accounting; no product or tests executed."""
import collections
import gzip
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEAD = 'b82238ec678350f20373bb3f873ac663dcadacd5'
CONTRACT = '40df0d2d17187cc86d63cb5fbe0efef2b5ae47a1'
COMMON = '61c6c5f09843329dcaebbd098cec6351754cdd76'
PRODUCT = '25ebc6fe13384a55cf1f2b7e5e4054bb862d002d'
LINUX = 'docs/evidence/WMS-672/raster-resource-linux-comparison-20261007/'
FROZEN = 'docs/evidence/WMS-672/raster-resource-test-contract-20261007/'
LOCAL = 'docs/evidence/WMS-672/raster-resource-fix-20261007/'


def git(*args):
    return subprocess.check_output(['git', *args])


def blob(path, ref=HEAD):
    return git('show', f'{ref}:{path}')


def obj(path, ref=HEAD):
    return json.loads(blob(path, ref))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def tap(path, expected):
    text = blob(path).decode()
    counters = {key: int(re.findall(r'^# ' + key + r' (\d+)$', text, re.M)[0])
                for key in ['tests', 'pass', 'fail', 'cancelled', 'skipped', 'todo']}
    assert counters == expected, (path, counters)
    cases = re.findall(r'^(?:not )?ok \d+ - (.+)$', text, re.M)
    assert len(cases) == counters['tests']
    return {'path': path, 'sha256': digest(blob(path)), 'counters': counters, 'cases': cases}


policy = obj('guards/PROCESS_CONTRACTS.json')
previous = obj('guards/PROCESS_CONTRACTS.json', 'fa6409a22^')
verified = []
for path, expected in policy['files'].items():
    actual = digest(blob(path))
    assert actual == expected, path
    verified.append({'path': path, 'sha256': actual})
assert len(verified) == 229
assert previous['files'].keys() <= policy['files'].keys()
changed = [p for p, d in previous['files'].items() if policy['files'][p] != d]
assert set(changed) == {'.github/workflows/ci.yml', 'frontend/src/utils/printBarcodeLabel.ts'}
for name, suite in previous['suites'].items():
    assert policy['suites'][name] == suite, name
old_text = blob('guards/PROCESS_CONTRACTS.json', 'fa6409a22^').decode()
new_text = blob('guards/PROCESS_CONTRACTS.json').decode()
# The original suite section is retained verbatim, followed by the new suite.
old_section = old_text.split('  "suites": {\n', 1)[1].rsplit('\n  }\n}', 1)[0]
assert new_text.split('  "suites": {\n', 1)[1].startswith(old_section + ',\n')
assert len(previous['files']) == 228 and len(previous['suites']) == 20
assert sum(len(s['cases']) for s in previous['suites'].values()) == 1170
assert len(policy['suites']) == 21 and sum(len(s['cases']) for s in policy['suites'].values()) == 1173
contract = obj(FROZEN + 'contract.json')
cases = obj(FROZEN + 'cases.json')
assert cases == contract['case_ids'] == policy['suites']['print-672-raster-resource']['cases']
assert policy['suites']['print-672-raster-resource'] == {
    'report': 'print/672-raster-resource.tap', 'format': 'node-tap', 'exact': True, 'cases': cases}
closure = contract['test_closure']
assert len(closure) == 4 and all(p in policy['files'] for p in closure)
for p in closure:
    assert digest(blob(p, CONTRACT)) == contract['closure_sha256'][p]
    assert blob(p, CONTRACT) == blob(p, COMMON)
test_path = closure[0]
assert digest(blob(test_path)) == '6796b1579438d6915c8a63a8a2c1a985a0ae2f737872dd25197c903b51e42a79'
assert blob(test_path) == blob(test_path, CONTRACT)
utility = 'frontend/src/utils/printBarcodeLabel.ts'
assert blob(utility) == blob(utility, PRODUCT)
assert git('rev-parse', PRODUCT + '^').decode().strip() == COMMON
assert git('diff', '--name-only', PRODUCT + '^', PRODUCT).decode().splitlines() == [utility]
assert git('diff', '--name-only', COMMON, HEAD, '--', 'frontend/src', 'backend/app').decode().splitlines() == [utility]
frozen = obj(FROZEN + 'frozen-original-hashes.json')
assert len(frozen['files']) == 31
for row in frozen['files']:
    p = row['path']
    assert digest(blob(p, CONTRACT)) == row['base_sha256']
    if p != utility:
        assert digest(blob(p)) == row['base_sha256'], p
assert blob(utility, COMMON) == blob(utility, '47817f76589701ea36ba1f8b30fca84b6a136208')
workflow = blob('.github/workflows/ci.yml').decode()
old_workflow = blob('.github/workflows/ci.yml', 'fa6409a22^').decode()
added = '          node --test --test-reporter=tap frontend/tests-e2e/wms672-raster-resource.test.mjs > "$RUNNER_TEMP/release-print/672-raster-resource.tap"\n'
assert workflow.count(added) == 1 and workflow.replace(added, '') == old_workflow
assert 'path: ${{ runner.temp }}/process-proof/print' in workflow
runner = blob('scripts/ci/run_release_print.sh').decode()
assert 'rm ' not in runner and 'mkdir -p "$evidence"' in runner
assert '--trusted-ref d61805978b3e7878d1056c99b4e6e0823edf49a5' in workflow

receipts = []
def expected(n, passed, failed=0):
    return {'tests': n, 'pass': passed, 'fail': failed, 'cancelled': 0, 'skipped': 0, 'todo': 0}


before = tap(FROZEN + 'before.tap', expected(3, 2, 1))
assert before['cases'] == cases
receipts.append(before)
mutation = tap(FROZEN + 'mutation-style-leak.tap', expected(2, 0, 2))
assert mutation['cases'] == cases[1:]
receipts.append(mutation)
receipts.append(tap(LOCAL + 'all-twelve.tap', expected(12, 12)))
for report, n in [('672-raster-resource.tap', 3), ('672-native-errors.tap', 7), ('672-peer-drain.tap', 2), ('672-c5.tap', 1)]:
    receipt = tap(LINUX + 'raw/' + report, expected(n, n))
    if report == '672-raster-resource.tap':
        assert receipt['cases'] == cases
    receipts.append(receipt)
manifest = obj(LINUX + 'manifest.json')
manifest_rows = []
for row in manifest['files']:
    raw = blob(LINUX + row['path'])
    assert len(raw) == row['bytes'] and digest(raw) == row['sha256'], row['path']
    original = gzip.decompress(raw) if row['path'].endswith('.html.gz') else raw
    if 'original_bytes' in row:
        assert len(original) == row['original_bytes'] and digest(original) == row['original_sha256']
    manifest_rows.append({'path': row['path'], 'sha256': row['sha256']})
assert len(manifest_rows) == 37
assert blob(LINUX + 'raw/source-before.sha256') == blob(LINUX + 'raw/source-after.sha256')
summary = obj(LINUX + 'raw/672/summary.json')
assert [(x['nativeFulfilled'], x['nativeRejected'], x['nativeTotalPending']) for x in summary] == [
    (459, 0, 0), (300, 0, 0), (599, 0, 0), (300, 0, 0)]
assert summary[0]['transfers'] == summary[2]['transfers'] == 1

# Reconstruct affirmative first fixture-2 preparation proof, excluding retry.
events = json.loads(gzip.decompress(blob(LINUX + 'raw/672/engine/cache-events.json.gz')))
events.sort(key=lambda e: e['ts'])
page = obj(LINUX + 'raw/672/fixture-2/page-0.json')
native = [e for e in page['events'] if e['kind'] == 'native-start']
catch = next(e for e in page['events'] if e['kind'] == 'screen-catch')
retry = native[299]
assert catch['wallTime'] == 1791328515632.1 and retry['wallTime'] == 1791328519367.3
markers = obj(LINUX + 'raw/672/engine/memory-and-markers.json')['markers']
samples = obj(LINUX + 'raw/672/engine/clock-sync.json')
bands = []
for marker in markers:
    sample = next(s for s in samples if s['syncId'] == marker['args']['sync_id'])
    bands.append([sample['epochBeforeMs'] - 1 - marker['ts'] / 1000,
                  sample['epochAfterMs'] + 1 - marker['ts'] / 1000])
low, high = max(b[0] for b in bands), min(b[1] for b in bands)
assert len(bands) == 2 and low <= high
mid = (low + high) / 2
cutoff_epoch = catch['wallTime'] + 1000
assert cutoff_epoch + (high - low) < retry['wallTime']
start_ts = (native[0]['wallTime'] - 5 - mid) * 1000
cutoff_ts = (cutoff_epoch - mid) * 1000
prefix = [e for e in events if start_ts <= e['ts'] <= cutoff_ts]
queues = [e for e in prefix if e['name'] == 'DecodedImageTracker::QueueImageDecode']
assert len(queues) == 299 and len({e['pid'] for e in queues}) == 1
pid = queues[0]['pid']
keys = {e['args']['frame_key'] for e in queues}
assert len(keys) == 299
clock_deltas = []
for n, q in zip(native[:299], queues):
    assert int(re.search(r'content_id: (\d+)', q['args']['frame_key'])[1]) == 299 + n['index']
    clock_deltas.append(q['ts'] / 1000 + mid - n['wallTime'])
assert max(abs(d) for d in clock_deltas) < 2


def field(key, name):
    return re.search(re.escape(name) + r'\[(.*?)\]', key)[1]


keyed = [e for e in prefix if e['pid'] == pid and 'key' in e['args']
         and field(e['args']['key'], 'frame_key') in keys]
groups = collections.defaultdict(list)
live = set()
peak_original = peak_scaled = 0
counts_by_size = collections.Counter()
for e in keyed:
    k = e['args']['key']
    groups[field(k, 'frame_key')].append(e)
    name = e['name'].split('::')[-1]
    if name not in ['AddBudgetForImage', 'RemoveBudgetForImage']:
        continue
    counts_by_size[(name, field(k, 'target_size'))] += 1
    if name == 'AddBudgetForImage':
        assert k not in live
        live.add(k)
    else:
        assert k in live
        live.remove(k)
    peak_original = max(peak_original, sum(field(k, 'target_size') == '836x356' for k in live))
    peak_scaled = max(peak_scaled, sum(field(k, 'target_size') == '1x1' for k in live))
assert not live
assert all(counts_by_size[(name, size)] == 299 for name in ['AddBudgetForImage', 'RemoveBudgetForImage'] for size in ['836x356', '1x1'])
chains = []
for n, q in zip(native[:299], queues):
    g = groups[q['args']['frame_key']]
    originals = {e['args']['key'] for e in g if field(e['args']['key'], 'target_size') == '836x356'}
    scaled = {e['args']['key'] for e in g if field(e['args']['key'], 'target_size') == '1x1'}
    assert len(originals) == len(scaled) == 1
    original, small = originals.pop(), scaled.pop()
    assert field(original, 'target_color_params') == field(small, 'target_color_params')
    assert field(original, 'src_rect') == field(small, 'src_rect') == '0,0 836x356'
    assert field(original, 'type') == 'Original' and field(small, 'type') == 'SubrectAndScale'
    def one(suffix, key):
        hits = [e for e in g if e['name'].endswith('::' + suffix) and e['args']['key'] == key]
        assert len(hits) == 1, (suffix, key, len(hits))
        return hits[0]['ts']
    row = {'native_index': n['index'], 'frame_key': q['args']['frame_key'],
           'original_key': original, 'scaled_key': small,
           'original_add_ts': one('AddBudgetForImage', original),
           'scaled_get_ts': one('GetTaskForImageAndRefInternal', small),
           'scaled_draw_ts': one('GetDecodedImageForDrawInternal', small),
           'original_unref_ts': one('UnrefImage', original),
           'original_remove_ts': one('RemoveBudgetForImage', original),
           'scaled_remove_ts': one('RemoveBudgetForImage', small)}
    assert row['original_add_ts'] < row['scaled_get_ts'] <= row['original_unref_ts'] <= row['original_remove_ts']
    next_index = ((n['index'] - 1) // 16 + 1) * 16 + 1
    later = next((v for v in native[:299] if v['index'] == next_index), None)
    row['before_next_cohort_with_clock_bounds'] = bool(later and row['original_remove_ts'] / 1000 + high < later['wallTime'])
    row['remove_after_scaled_get_ms'] = (row['original_remove_ts'] - row['scaled_get_ts']) / 1000
    chains.append(row)
fast = [r for r in chains if r['remove_after_scaled_get_ms'] <= 1]
assert len(fast) == 224 and len(chains) - len(fast) == 75 and peak_original == 55
assert any(r['before_next_cohort_with_clock_bounds'] for r in fast)
completion = obj(LINUX + 'raw/672/engine/trace-completion.json')
result = {
    'reviewed_head': HEAD, 'contract': CONTRACT, 'common': COMMON, 'product': PRODUCT,
    'origin_etalon': git('rev-parse', 'origin/etalon').decode().strip(),
    'protected_files_verified': verified,
    'policy': {'files': 229, 'suites': 21, 'case_ids': 1173, 'retained_old_files': 228,
               'retained_old_suites_verbatim_and_semantically': 20, 'retained_old_case_ids': 1170,
               'changed_existing_digests': changed, 'closure': closure, 'new_cases': cases},
    'source': {'product_only_delta': utility, 'current_equals_product_blob': True,
               'frozen31_only_utility_changed': True, 'contract_common_blobs_identical': True,
               'workflow_only_additive_command': True, 'product_ref_still_d618': True},
    'preserved_receipts': receipts, 'linux_manifest_verified': manifest_rows,
    'linux_native_summaries': summary,
    'prefix': {'renderer_pid': pid, 'clock_offset_intersection_ms': [low, high],
               'retained_clock_samples': 2, 'requested_clock_samples': 3,
               'known_catch_epoch_ms': catch['wallTime'], 'cutoff_epoch_ms': cutoff_epoch,
               'retry_first_native_epoch_ms': retry['wallTime'], 'native_queue_count': 299,
               'queue_native_epoch_delta_ms': [min(clock_deltas), max(clock_deltas)],
               'first_native_start_span_ms': native[298]['wallTime'] - native[0]['wallTime'],
               'first_engine_queue_span_ms': (queues[-1]['ts'] - queues[0]['ts']) / 1000,
               'counts': {f'{n}:{s}': v for (n, s), v in counts_by_size.items()},
               'residual_keys': 0, 'peak_original_entries': peak_original, 'peak_scaled_entries': peak_scaled,
               'remove_within_1ms_scaled_get': len(fast), 'later_removals': 75,
               'before_next_cohort_positive_chains': sum(r['before_next_cohort_with_clock_bounds'] for r in chains),
               'examples': [fast[0], next(r for r in fast if r['before_next_cohort_with_clock_bounds']),
                            next(r for r in chains if r['remove_after_scaled_get_ms'] > 1)]},
    'trace_global': {'dataLossOccurred': completion['dataLossOccurred'],
                     'maxBufferUsage': max(e['percentFull'] for e in completion['usage']),
                     'whole_trace_completeness_claim': False},
    'limits': ['Only positive matched prefix events support the mechanism; lost-event absence proves nothing.',
               'OnImagesUsedInDraw routing is source-backed inference from preserved exact141 source identities/proposal and prior independent source review, not an emitted runtime call/private enum.',
               'No product/test/build/browser/provider/deploy execution by this reviewer.',
               'Typecheck/build success read from preserved developer receipt, not independently repeated.',
               'Not analyst acceptance, SOURCE/ref migration approval, fullCI, release or physical-paper proof.'],
}
(HERE / 'source-checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'protected_files': 229, 'old_suites_retained': 20, 'case_ids': 1173,
                  'manifest_files': len(manifest_rows), 'prefix': {k: v for k, v in result['prefix'].items() if k != 'examples'}}, indent=2))
