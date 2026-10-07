"""Bounded complete first preparation; never promote lossy full trace to no-loss."""
import collections
import gzip
import json
import pathlib
import re

root = pathlib.Path(__file__).resolve().parent
raw = root / 'raw'
events = json.loads(gzip.decompress((raw / '672/engine/cache-events.json.gz').read_bytes()))
markers = json.loads((raw / '672/engine/memory-and-markers.json').read_text())['markers']
samples = json.loads((raw / '672/engine/clock-sync.json').read_text())
clock = {e['args']['sync_id']: e['ts'] / 1000 for e in markers}
matched = [s for s in samples if s['syncId'] in clock]
assert len(matched) == 2
low = max(s['epochBeforeMs'] - clock[s['syncId']] - 1 for s in matched)
high = min(s['epochAfterMs'] - clock[s['syncId']] + 1 for s in matched)
assert low <= high
page = json.loads((raw / '672/fixture-2/page-0.json').read_text())
failure = next(e for e in page['events'] if e['kind'] == 'screen-catch')
assert failure['message'] == 'WMS672 decode failed at 299'
cut_epoch = failure['wallTime'] + 1000
cut = (cut_epoch - (low + high) / 2) * 1000
starts = [e for e in page['events'] if e['kind'] == 'native-start']
first = [e for e in starts if e['wallTime'] < cut_epoch]
assert len(first) == 299 and starts[299]['wallTime'] > cut_epoch + 2000
queues = sorted((e for e in events if e['name'] == 'LayerTreeHostImpl::QueueImageDecode' and e['ts'] < cut), key=lambda e: e['ts'])
assert len(queues) == len(first)
ids = {int(re.search(r'content_id: (\d+)', e['args']['frame_key'])[1]) for e in queues}
assert len(ids) == 299
live, ledger, scaled, pairs = {}, [], {}, []
peak_entries = peak_bytes = 0
for e in sorted(events, key=lambda e: e['ts']):
    if e['ts'] >= cut:
        break
    text = e.get('args', {}).get('key', '')
    cid = re.search(r'content_id: (\d+)', text)
    dimensions = re.search(r'target_size\[(\d+)x(\d+)\]', text)
    if not cid or int(cid[1]) not in ids or not dimensions:
        continue
    content = int(cid[1])
    kind = re.search(r'type\[([^]]+)\]', text)[1]
    size = (int(dimensions[1]), int(dimensions[2]))
    assert (kind, size) in [('Original', (836, 356)), ('SubrectAndScale', (1, 1))]
    # Original equality ignores nearest-neighbor; preserve all other emitted fields.
    canonical = re.sub(r'\nis_nearest_neightbor\[[^]]+\]', '', text)
    canonical = re.sub(r'\nhash\[[^]]+\]', '', canonical)
    key = (e['pid'], canonical)
    name = e['name'].split('::')[-1]
    if name == 'GetTaskForImageAndRefInternal' and kind == 'SubrectAndScale':
        scaled[content] = e['ts']
    if name == 'AddBudgetForImage':
        assert key not in live
        live[key] = (e['ts'], kind, size[0] * size[1] * 4)
    elif name == 'RemoveBudgetForImage':
        assert key in live
        started, admitted_kind, _ = live.pop(key)
        assert kind == admitted_kind
        pairs.append({'content_id': content, 'kind': kind, 'pid': e['pid'], 'key': canonical,
                      'add_ts': started, 'remove_ts': e['ts'], 'duration_ms': (e['ts'] - started) / 1000,
                      'since_scaled_get_ms': (e['ts'] - scaled[content]) / 1000 if kind == 'Original' else None})
    else:
        continue
    current_original = sum(value[1] == 'Original' for value in live.values())
    current_bytes = sum(value[2] for value in live.values())
    peak_entries = max(peak_entries, current_original)
    peak_bytes = max(peak_bytes, current_bytes)
    ledger.append({'name': name, 'ts': e['ts'], 'pid': e['pid'], 'content_id': content,
                   'key': canonical, 'original_entries': current_original, 'tracked_bytes': current_bytes})
assert not live
original = [p for p in pairs if p['kind'] == 'Original']
small = [p for p in pairs if p['kind'] == 'SubrectAndScale']
assert len(original) == len(small) == 299
assert len({p['content_id'] for p in original}) == len({p['content_id'] for p in small}) == 299
summary = {'scope': 'fixture2 first299 native preparation plus1s BEFORE corrected retry; full trace is lossy',
           'clock_retained': 2, 'clock_interval_width_ms': high - low, 'cut_epoch_ms': cut_epoch,
           'retry_start_epoch_ms': starts[299]['wallTime'], 'native_starts': len(first), 'queues': len(queues),
           'original_add_remove_pairs': len(original), 'scaled_1x1_add_remove_pairs': len(small),
           'end_tracked_entries': len(live), 'peak_original_entries': peak_entries, 'peak_tracked_bytes': peak_bytes,
           'original_release_within_1ms_of_scaled_get': sum(0 <= p['since_scaled_get_ms'] < 1 for p in original),
           'original_reservation_duration_ms': [min(p['duration_ms'] for p in original), max(p['duration_ms'] for p in original)],
           'global_no_loss': False, 'whole_run_cache_accounting': False}
(root / 'first-phase-ledger.json').write_text(json.dumps({'summary': summary, 'pairs': pairs, 'ledger': ledger}, indent=2) + '\n')
(root / 'first-phase-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
