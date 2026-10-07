"""Read immutable saved Git blobs only; no runner or native commands.
Run from the repository: python3 -B <this-file> > ledger.json
"""
import collections
import hashlib
import json
import subprocess

EVIDENCE = '896b9a3fee446728c44b62af7c8bf8422d1e5e08'
SOURCE = '4c532f0cccfb8f99b34d68d9630a3763038fbc5f'
ROOT = 'docs/evidence/WMS-652/etalon-ci-37567017373/'
hashes = {}


def read(path, ref=EVIDENCE):
    data = subprocess.check_output(['git', 'show', ref + ':' + path])
    hashes[ref + ':' + path] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return data


def load(path):
    return json.loads(read(ROOT + path))


run = load('run-current.json')
assert (run['id'], run['run_attempt'], run['head_sha'], run['event'], run['conclusion']) == (
    37567017373, 1, SOURCE, 'push', 'failure')
transport = load('raw/print/critical-fbs/cdp-transport.json')
events = transport['events']
assert len(events) == 43443 and transport['pendingCommandIds'] == []
assert all(a['utcMs'] <= b['utcMs'] for a, b in zip(events, events[1:]))
sends = {}; results = {}; paused = collections.defaultdict(list)
for i, event in enumerate(events):
    kind = event['kind']
    if kind in ('command-send', 'command-result'):
        dest = sends if kind == 'command-send' else results
        assert event['commandId'] not in dest
        dest[event['commandId']] = (i, event)
    elif kind == 'request-paused':
        paused[event['requestId']].append((i, event))
assert len(sends) == len(results) == 11582 and sends.keys() == results.keys()
for cid, (i, send) in sends.items():
    j, result = results[cid]
    assert i < j
    for field in ('method', 'requestId', 'networkId', 'frameId', 'generation', 'caseId', 'cancellation'):
        assert send.get(field) == result.get(field), (cid, field)
errors = {cid for cid, (_, r) in results.items() if r.get('nativeError')}
assert errors == {2730, 7689}
assert not any(e['kind'] in ('command-timeout', 'retired-canceled-request') for e in events)
missing = []
for request_id, observations in paused.items():
    if observations[0][1].get('networkId'):
        continue
    assert len(observations) == 1
    i, pause = observations[0]
    commands = [(cid, j, e) for cid, (j, e) in sends.items() if e.get('requestId') == request_id]
    assert len(commands) == 1
    cid, j, send = commands[0]; k, result = results[cid]
    assert i < j < k and send['attempt'] == 1 and send['method'] == 'Fetch.fulfillRequest'
    assert not any(e['kind'] == 'generation-boundary' or e.get('method') == 'Page.navigate'
                   or e.get('generation', pause['generation']) != pause['generation']
                   or e.get('caseId', pause['caseId']) != pause['caseId']
                   for e in events[i:k+1])
    assert all(field not in pause for field in ('url', 'method', 'resourceType', 'networkId'))
    missing.append({'command': cid, 'raw_indexes_zero_based': [i, j, k],
                    'records': [pause, send, result],
                    'one_observation_one_first_fulfill': True,
                    'recorded_generation_case_unchanged_through_reply': True,
                    'native_outcome': 'rejected' if cid in errors else 'success'})
assert len(missing) == 6 and sum(m['native_outcome'] == 'success' for m in missing) == 4
assert not any(e['kind'] == 'network-terminal' and not e.get('networkId') for e in events)
prepared = load('invalid-id-ledger.json')
for row in prepared:
    mine = next(m for m in missing if m['command'] == row['command'])
    assert row['records'] == mine['records'] and row['networkId_present'] is False
report = load('raw/print/critical-fbs/result.json')
assert report['sha'] == SOURCE and len(report['cases']) == 43
assert collections.Counter(c['status'] for c in report['cases']) == {'PASS': 41, 'FAIL': 2}
failures = {}
for name in ('WMS652-realQrFlags-qr-supply_ids-A-B-.json',
             'WMS652-realQrFlags-remount-after-lost-ack-supply_id-A-.json'):
    case = load('raw/print/critical-fbs/' + name)
    assert case['blocked'] == [] and case['errors'] == ['Error: {"code":-32602,"message":"Invalid InterceptionId."}']
    failures[name] = {'errors': case['errors'], 'blocked': [], 'trace': case['trace'],
                      'acceptedPrintKeys': case['acceptedPrintKeys'], 'print_attempts': len(case['printLog'])}
read(ROOT + 'jobs/print-regressions.log')
source = read('frontend/tests-e2e/wms652-critical/browser.mjs', SOURCE)
assert hashlib.sha256(source).hexdigest() == '24f146ba0e038645114edb882a85686dc834f8c338d1324c10426b7648bd6dd6'
assert source == read('frontend/tests-e2e/wms652-critical/browser.mjs', '972da18be97cab8c41b14b0aa00a3d30773e4492')
prior_path = 'docs/evidence/WMS-652/realqr-cdp-lifecycle-linux-20261007/raw/selected/cdp-lifecycle.json'
prior = json.loads(read(prior_path))
prior_events = prior['lifecycle']
prior_pauses = [e for e in prior_events if e.get('method') == 'Fetch.requestPaused']
assert prior_pauses and all(e.get('networkId') for e in prior_pauses)
print(json.dumps({'verdict': 'Existing finite rejection correct; exact retirement cause UNKNOWN; insufficient identity for a handling change',
    'source': SOURCE, 'evidence': EVIDENCE, 'run': 37567017373, 'attempt': 1,
    'transport_events': len(events), 'kinds': dict(collections.Counter(e['kind'] for e in events)),
    'all_native_command_pairs_verified': len(sends), 'pending': [], 'native_error_commands': sorted(errors),
    'missing_network_paused_records': missing, 'failed_case_business_receipts': failures,
    'browser_cases': {'PASS': 41, 'FAIL': 2}, 'existing_R1_source_bytes_identical': True,
    'prior_selected_fullURL_capture': {'run': 37550768806, 'paused': len(prior_pauses), 'missing_network_pauses': 0},
    'input_hashes': hashes, 'new_native_test_CI_browser_runs': [], 'fix_or_SOURCE_approval': False,
}, ensure_ascii=False, indent=2))
