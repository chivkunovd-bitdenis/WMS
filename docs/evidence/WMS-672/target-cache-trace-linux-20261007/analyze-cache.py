"""Offline complete trace ledger, no browser/API or product execution."""
import collections
import gzip
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / 'raw'
events = json.loads(gzip.decompress((RAW / '672/engine/trace.json.gz').read_bytes()))['traceEvents']
events.sort(key=lambda e: e.get('ts', 0))
completion = json.loads((RAW / '672/engine/trace-completion.json').read_text())
assert completion['dataLossOccurred'] is False
samples = json.loads((RAW / '672/engine/clock-sync.json').read_text())
clock_events = [e for e in events if e['name'] == 'clock_sync']
clock_bands = []
for sample in samples:
    event = next(e for e in clock_events if e['args']['sync_id'] == sample['syncId'])
    clock_bands.append(dict(sample, ts=event['ts'], low=sample['epochBeforeMs'] - 1 - event['ts'] / 1000,
                            high=sample['epochAfterMs'] + 1 - event['ts'] / 1000))
low = max(s['low'] for s in clock_bands)
high = min(s['high'] for s in clock_bands)
assert low <= high
midpoint = (low + high) / 2
page = json.loads((RAW / '672/fixture-2/page-0.json').read_text())
starts = [e for e in page['events'] if e['kind'] == 'native-start']
queues = [e for e in events if e['name'] == 'LayerTreeHostImpl::QueueImageDecode']
assert len(starts) == len(queues) == 555
live = {}
timeline = []
for event in events:
    if event['name'] not in ['SoftwareImageDecodeCache::AddBudgetForImage', 'SoftwareImageDecodeCache::RemoveBudgetForImage']:
        continue
    key = event['args']['key']
    width, height = map(int, re.search(r'target_size\[(\d+)x(\d+)\]', key).groups())
    identity = (event['pid'], key)
    if event['name'].endswith('AddBudgetForImage'):
        assert identity not in live, 'ambiguous duplicate allocation'
        live[identity] = 4 * width * height
    else:
        assert identity in live, 'missing initial allocation'
        del live[identity]
    timeline.append({'ts': event['ts'], 'pid': event['pid'], 'action': event['name'].split('::')[-1],
                     'key': key, 'target_width': width, 'target_height': height,
                     'entry_bytes': 4 * width * height, 'live_entries': len(live), 'live_bytes': sum(live.values())})
assert not live
assert max(row['live_bytes'] for row in timeline) == 267854400
get_requests = [e for e in events if e['name'] == 'SoftwareImageDecodeCache::GetTaskForImageAndRefInternal'
                and 'target_size[836x356]' in e['args']['key']]
assert len(get_requests) == 555
full_keys = {re.search(r'frame_key\[(.*?)\]', e['args']['key'])[1]: e['args']['key'] for e in get_requests}
workers = [e for e in events if e['name'] == 'SoftwareImageDecodeCache::DecodeImageIfNecessary']
low_level = [e for e in events if e['name'] == 'SoftwareImageDecodeCacheUtils::DoDecodeImage - decode']
rows = []
for ordinal, (native, queue) in enumerate(zip(starts, queues), 1):
    frame_key = queue['args']['frame_key']
    key = full_keys[frame_key]
    label = native['index'] if native['nativeFrameId'] == 3 else native['index'] - 300
    assert int(re.search(r'content_id: (\d+)', frame_key)[1]) == 299 + label
    following_same_key = next((q['ts'] for q in queues if q['ts'] > queue['ts'] and q['args']['frame_key'] == frame_key), float('inf'))
    req = next(e for e in get_requests if e['args']['key'] == key and queue['ts'] <= e['ts'] < following_same_key)
    before = max((r for r in timeline if r['ts'] <= req['ts']), key=lambda r: r['ts'], default={'live_entries': 0, 'live_bytes': 0})
    allocated = [r for r in timeline if r['action'] == 'AddBudgetForImage' and r['key'] == key and queue['ts'] <= r['ts'] < following_same_key]
    work = [w for w in workers if w['args']['key'] == key and queue['ts'] <= w['ts'] < following_same_key]
    actual_decode = [d for d in low_level if any(d['pid'] == w['pid'] and d['tid'] == w['tid'] and w['ts'] <= d['ts'] <= w['ts'] + w.get('dur', 0) for w in work)]
    prior = [r for r in rows if r['key'] == key]
    row = {'ordinal': ordinal, 'phase': 'injected299' if native['nativeFrameId'] == 3 else 'corrected-retry',
           'native_index': native['index'], 'label': label, 'native_frame_id': native['nativeFrameId'],
           'native_start_epoch_ms': native['wallTime'], 'queue_ts': queue['ts'], 'get_task_ts': req['ts'],
           'queue_to_native_epoch_ms_midpoint': queue['ts'] / 1000 - (native['wallTime'] - midpoint),
           'frame_key': frame_key, 'key': key, 'bytes_before_request': before['live_bytes'],
           'entries_before_request': before['live_entries'], 'allocations': len(allocated),
           'worker_entries': len(work), 'low_level_decodes': len(actual_decode),
           'prior_same_key_success': bool(prior and prior[-1]['allocations'] and prior[-1]['low_level_decodes'])}
    assert len(allocated) <= 1 and len(work) <= 1 and len(actual_decode) <= 1
    rows.append(row)
denied = [r for r in rows if not r['allocations']]
assert len(denied) == 15
assert [r['label'] for r in denied] == list(range(242, 257))
assert all(r['bytes_before_request'] == 267854400 and r['entries_before_request'] == 225 and r['worker_entries'] == 0 and r['prior_same_key_success'] for r in denied)
retry_start = queues[299]['ts']
finish = next(e['ts'] for e in events if e['name'] == 'DecodedImageTracker::ImageDecodeFinished' and e['ts'] >= retry_start)
releases = [r for r in timeline if r['action'] == 'RemoveBudgetForImage' and r['ts'] >= retry_start]
first_reject = next(e for e in page['events'] if e['kind'] == 'native-reject')
summary = {'dataLossOccurred': False, 'maxBufferUsage': max(x['percentFull'] for x in completion['usage']),
           'clock_markers': len(clock_events), 'clock_bands_with_1ms_Date_precision': clock_bands,
           'clock_offset_intersection_ms': [low, high], 'native_calls': len(starts), 'engine_queues': len(queues),
           'allocations': sum(r['allocations'] for r in rows), 'worker_entries': sum(r['worker_entries'] for r in rows),
           'actual_low_level_decodes': sum(r['low_level_decodes'] for r in rows), 'peak_live_entries': 225,
           'peak_live_bytes': 267854400, 'entry_bytes': 1190464, 'default_256Mi_remaining_bytes': 268435456 - 267854400,
           'denied_requests': len(denied), 'denied_labels': [r['label'] for r in denied], 'ending_live_entries': 0,
           'first_retry_release_after_first_decode_finished_ms': (releases[0]['ts'] - finish) / 1000,
           'first_reject_after_retry_queue_ms': (first_reject['wallTime'] - midpoint) - retry_start / 1000,
           'next_release_after_first_reject_ms': min((r['ts'] / 1000 - (first_reject['wallTime'] - midpoint)) for r in releases if r['ts'] / 1000 >= first_reject['wallTime'] - midpoint),
           'retry_release_groups_10ms_buckets': dict(collections.Counter(str(round((r['ts'] - retry_start) / 1000, -1)) for r in releases)),
           'initial_global_dump': json.loads((RAW / '672/engine/initial-memory-dump.json').read_text()),
           'bound': 'Runtime private result enum/max limit are not directly emitted; admission reason inferred from complete matched keys, failed-reservation paths and exact141 source. Initial explicit global dump returnedfalse; periodic snapshots/all allocations are preserved.'}
for name, value in [('key-ledger.json', rows), ('budget-ledger.json', timeline), ('denied-keys.json', denied), ('accounting-summary.json', summary)]:
    (HERE / name).write_text(json.dumps(value, indent=2) + '\n')
print(json.dumps({k: v for k, v in summary.items() if not k.startswith('clock')}, indent=2))
