"""Offline review of immutable saved Git evidence; no browser or test execution."""
import gzip
import hashlib
import json
import subprocess
from pathlib import Path

BASE = '2bc57f83440c79458b67928ba9269ea72dfe3ede'
SOURCE = '4c532f0cccfb8f99b34d68d9630a3763038fbc5f'
PREFIX = 'docs/evidence/WMS-652/etalon-error-context-37571409533/'
OUT = Path(__file__).parent

def blob(ref, path):
    return subprocess.check_output(['git', 'show', f'{ref}:{path}'])

def saved(path):
    data = blob(BASE, PREFIX + path)
    return gzip.decompress(data) if path.endswith('.gz') else data

def obj(path):
    return json.loads(saved(path))

def sha(data):
    return hashlib.sha256(data).hexdigest()

run = obj('run-current.json')
assert run['id'] == 37571409533 and run['run_attempt'] == 1
assert run['head_sha'] == '8e6c2f6a28b64009b7f896420d3ef95808759b07'
assert run['status'] == 'completed' and run['conclusion'] == 'failure'
manifest = obj('raw-manifest.json')
verified = []
for member in manifest['members']:
    stored = blob(BASE, PREFIX + member['stored_path'])
    recovered = gzip.decompress(stored) if member['encoding'] == 'gzip' else stored
    assert len(stored) == member['stored_bytes'] and sha(stored) == member['stored_sha256']
    assert len(recovered) == member['original_bytes'] and sha(recovered) == member['original_sha256']
    verified.append({'path': member['stored_path'], 'stored_sha256': sha(stored),
                     'original_sha256': sha(recovered)})
assert len(verified) == manifest['member_count'] == 18
prep = obj('raw/wms652-identity-diagnostic/preparation.json.gz')
after = obj('raw/wms652-identity-diagnostic/source-after.json.gz')
assert prep['source_sha256'] == after
browser_path = 'frontend/tests-e2e/wms652-critical/browser.mjs'
shell_path = 'scripts/ci/run_critical_fbs_browser.sh'
frozen = saved('raw/wms652-identity-diagnostic/frozen-browser-source.mjs')
generated = saved('raw/wms652-identity-diagnostic/generated-browser.mjs')
insertions = [
    b"import { createErrorContextObserver } from './identity-observer.untracked.mjs';\nconst errorContext=createErrorContextObserver();\n",
    b'      if (msg.error || msg.method) errorContext.message(this,msg);\n',
    b'  await writeFile(`${dir}/error-context.json`,errorContext.serialize(cdp,report));\n',
]
reverse = generated
for insertion in insertions:
    assert reverse.count(insertion) == 1
    reverse = reverse.replace(insertion, b'', 1)
assert reverse == frozen == blob(SOURCE, browser_path)
original_shell = saved('raw/wms652-identity-diagnostic/original-shell.sh')
generated_shell = saved('raw/wms652-identity-diagnostic/generated-shell.sh')
assert generated_shell.replace(b'browser.identity-diagnostic.untracked.mjs', b'browser.mjs') == original_shell
assert original_shell == blob(SOURCE, shell_path)
assert sha(frozen) == prep['source_browser_sha256']
assert sha(generated) == prep['generated_browser_sha256']
assert sha(original_shell) == prep['source_shell_sha256']
assert sha(generated_shell) == prep['generated_shell_sha256']
observer = saved('raw/wms652-identity-diagnostic/generated-observer.mjs')
assert sha(observer) == prep['generated_observer_sha256']
context = obj('raw/release-print/critical-fbs/error-context.json.gz')
transport = obj('raw/release-print/critical-fbs/cdp-transport.json.gz')
result = obj('raw/release-print/critical-fbs/result.json.gz')
sends = [e for e in transport['events'] if e['kind'] == 'command-send']
replies = [e for e in transport['events'] if e['kind'] == 'command-result']
assert len(sends) == len(replies) == 11665
assert len({e['commandId'] for e in sends}) == len(sends)
assert len({e['commandId'] for e in replies}) == len(replies)
assert {e['commandId'] for e in sends} == {e['commandId'] for e in replies}
assert not transport['pendingCommandIds'] and not context['pendingCommandIds']
assert all(v == 0 for v in context['dropped'].values())
assert not [e for e in transport['events'] if e['kind'] == 'command-timeout']
assert [e['id'] for e in result['cases']] == prep['cases']
assert len(prep['cases']) == len(set(prep['cases'])) == 43
assert result['status'] == 'FAIL'
assert sum(e['status'] == 'PASS' for e in result['cases']) == 41
assert sum(e['status'] == 'FAIL' for e in result['cases']) == 2
native = [e for e in replies if e.get('nativeError')]
errors = [e for e in context['events'] if e['kind'] == 'native-error-context']
assert [e['commandId'] for e in native] == [e['commandId'] for e in errors] == [5931, 8720]
assert context['nativeErrorsObserved'] == 2
paused = {}
for e in context['events']:
    if e.get('method') == 'Fetch.requestPaused':
        paused.setdefault(e['requestId'], []).append(e)
failures = []
for error in errors:
    identity = error['pendingIdentity']
    seen = paused[identity['requestId']]
    assert len(seen) == 1 and seen[0]['requestMethod'] == 'GET'
    assert seen[0]['resourceType'] == 'XHR' and 'networkId' not in seen[0]
    assert error['networkRecordIndices'] == []
    assert identity['generation'] == error['currentGeneration'] == error['send']['generation']
    assert identity['caseId'] == error['currentCaseId'] == error['send']['caseId']
    assert error['send']['attempt'] == 1
    assert error['nativeError'] == {'code': -32602, 'message': 'Invalid InterceptionId.'}
    failures.append({'command_id': error['commandId'], 'paused': seen[0],
                     'send': error['send'], 'reply_utc_ms': error['utcMs'],
                     'native_error': error['nativeError'], 'matched_network_records': 0})
no_network_successes = []
endpoint = failures[0]['paused']['url']
for reply in replies:
    if reply['method'] != 'Fetch.fulfillRequest' or reply.get('nativeError'):
        continue
    seen = paused.get(reply.get('requestId'), [])
    if len(seen) == 1 and 'networkId' not in seen[0]:
        no_network_successes.append({'command_id': reply['commandId'], 'paused': seen[0]})
workspace_successes = [e for e in no_network_successes if e['paused'].get('url') == endpoint
                       and e['paused'].get('resourceType') == 'XHR'
                       and e['paused'].get('requestMethod') == 'GET']
assert workspace_successes
source_paths = [browser_path, shell_path, 'frontend/src/screens/v2/fbsApi.ts',
                'frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx',
                'frontend/src/screens/v2/FfFbsSupplyAssembly.tsx']
proof = {
    'review_base': BASE, 'product_fixture_source': SOURCE,
    'diagnostic_head': prep['diagnostic_head'], 'run_id': manifest['run_id'],
    'attempt': manifest['attempt'], 'artifact_id': manifest['artifact_id'],
    'saved_run_conclusion': run['conclusion'], 'saved_run_head': run['head_sha'],
    'saved_member_verification': verified,
    'original_browser_exact_git_equal': True, 'three_insertions_reverse_byte_equal': True,
    'original_shell_exact_git_equal': True, 'shell_runner_substitution_only': True,
    'saved_before_after_hash_maps_equal': True, 'saved_before_after_paths': len(after),
    'source_files': {p: {'git_blob': subprocess.check_output(['git', 'rev-parse', f'{SOURCE}:{p}']).decode().strip(),
                         'sha256': sha(blob(SOURCE, p))} for p in source_paths},
    'observer_sha256': sha(observer), 'cases': 43, 'pass': 41, 'fail': 2,
    'native_command_sends': len(sends), 'native_command_replies': len(replies),
    'unique_equal_command_ids': True, 'pending': 0, 'timeouts': 0,
    'context_records': len(context['events']), 'dropped': context['dropped'],
    'failures': failures,
    'successful_no_network_id_owned_fulfill_count': len(no_network_successes),
    'successful_same_workspace_get_xhr_no_network_id_count': len(workspace_successes),
    'successful_same_workspace_example': workspace_successes[0],
    'verdict': 'Saved reproduction/provenance verified; cancellation cause UNKNOWN; no handling migration approved',
}
(OUT / 'proof.json').write_text(json.dumps(proof, indent=2) + '\n')
print(json.dumps({k: proof[k] for k in ['cases', 'pass', 'fail', 'native_command_sends',
 'context_records', 'successful_no_network_id_owned_fulfill_count',
 'successful_same_workspace_get_xhr_no_network_id_count', 'successful_same_workspace_example']}))
