"""Acceptance source/receipt readback only; never executes tests or product."""
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = '49da13fd2a0d22f207818248f274cf5ff400e39f'
PRODUCT = 'bdd5a8eee8606d667a90a3b61da299b4097dc877'
OLD = 'a40bf5b9a2f833a16cb9ff8c941c46c02a0b9d72'
NEW = '040e94c956b8cc99d69d04e8cc90499a01e61a95'
PREFIX = 'docs/evidence/WMS-607/'

def blob(path, ref=BASE):
    return subprocess.check_output(['git', 'show', f'{ref}:{path}'])

def obj(path):
    return json.loads(blob(PREFIX + path))

def sha(data):
    return hashlib.sha256(data).hexdigest()

sources = {}
for name in ['update_macos_direct.sh', 'build_console.py', 'wms_print_direct_macos.swift']:
    p = 'tools/print-agent/' + name
    assert blob(p) == blob(p, PRODUCT)
    sources[p] = {'sha256': sha(blob(p)), 'git_blob': subprocess.check_output(
        ['git', 'rev-parse', f'{BASE}:{p}']).decode().strip()}
frozen_counts = {}
for folder, ref, module in [('updater-test-contract-20261007', OLD, 'test_macos_direct_updater_contract.py'),
                            ('updater-stop-test-contract-20261007', NEW, 'test_macos_direct_updater_stop_contract.py')]:
    members = obj(folder + '/manifest.json')['members']
    for m in members:
        data = blob(m['path'])
        assert data == blob(m['path'], ref)
        assert sha(data) == m['sha256'] and len(data) == m['bytes']
    p = 'tools/print-agent/' + module
    assert blob(p) == blob(p, ref)
    frozen_counts[folder] = {'manifest_members_verified': len(members), 'test_sha256': sha(blob(p))}
old_ids = obj('updater-test-contract-20261007/contract.json')['suite']['xml_ids']
new_ids = obj('updater-stop-test-contract-20261007/contract.json')['suite']['xml_ids']
reports = {}
for path, ids, failures in [
    ('updater-stop-fix-20261007/precode.xml', new_ids, 2),
    ('updater-stop-fix-20261007/green.xml', new_ids, 0),
    ('updater-stop-fix-20261007/updater.xml', old_ids, 0),
    ('updater-stop-fix-20261007/existing.xml', None, 0),
    ('updater-stop-rereview-20261007/updater-stop.xml', new_ids, 0),
]:
    root = ET.fromstring(blob(PREFIX + path))
    cases = list(root.iter('testcase'))
    actual = [c.get('classname') + '::' + c.get('name') for c in cases]
    assert len(actual) == len(set(actual))
    if ids is not None:
        assert set(actual) == set(ids)
    else:
        assert len(actual) == 19
    assert sum(c.find('failure') is not None for c in cases) == failures
    assert not any(c.find('error') is not None or c.find('skipped') is not None for c in cases)
    reports[path] = {'tests': len(cases), 'pass': len(cases) - failures,
                     'fail': failures, 'error': 0, 'skip': 0, 'xml_ids': actual,
                     'sha256': sha(blob(PREFIX + path))}
raw_hashes = {}
for case_id in old_ids:
    name = case_id.split('::')[1]
    path = 'updater-stop-fix-20261007/updater/' + name + '.json'
    record = obj(path)
    assert record['entry_sha256'] == sources['tools/print-agent/update_macos_direct.sh']['sha256']
    assert record['source_sha256'] == sources['tools/print-agent/wms_print_direct_macos.swift']['sha256']
    assert record['test_sha256'] == frozen_counts['updater-test-contract-20261007']['test_sha256']
    raw_hashes[path] = sha(blob(PREFIX + path))
for case_id in new_ids:
    name = case_id.split('::')[1]
    for folder in ['updater-stop-fix-20261007/green', 'updater-stop-rereview-20261007/raw']:
        path = folder + '/' + name + '.json'
        record = obj(path)
        assert record['source_sha256'] == sources['tools/print-agent/update_macos_direct.sh']['sha256']
        assert record['test_sha256'] == frozen_counts['updater-stop-test-contract-20261007']['test_sha256']
        if 'TERM_' in name:
            assert record['native_exit'] != 0 and record['process_alive']
            assert record['transaction'] == 1 and record['intent_unchanged']
            assert record['before'] == record['after']
        if name.startswith('test_foreign'):
            assert not record['signals'] and record['process_alive']
        raw_hashes[path] = sha(blob(PREFIX + path))
review = obj('updater-stop-rereview-20261007/source-checks.json')
assert review['product_source'] == PRODUCT and review['verdict'].startswith('PASS:')
for item in review['preserved_previous_paths']:
    assert sha(blob(item['path'])) == item['sha256']
native = obj('updater-implementation-20261007/native-start.json')
assert native['provenance']['source_sha256'] == sources['tools/print-agent/wms_print_direct_macos.swift']['sha256']
assert native['pass'] and native['startup_submissions'] == native['readiness_submissions'] == 0
assert native['explicit_new_scan_submissions'] == 1 and not native['physical_print']
proof = {'accepted_software_base': BASE, 'corrected_product': PRODUCT,
         'independent_review': BASE, 'original_updater_contract': OLD, 'additive_stop_contract': NEW,
         'source_files': sources, 'frozen_manifests': frozen_counts, 'reports': reports,
         'raw_source_bound_records': raw_hashes, 'review_preserved_paths_verified': len(review['preserved_previous_paths']),
         'native_launch_no_submit_saved_receipt_verified': True,
         'mechanism_acceptance': 'PASS U-C1..U-C8; distribution and U-C9/U-C10 pending',
         'tests_build_browser_install_or_provider_executed_here': False}
Path(__file__).with_name('source-probe.json').write_text(json.dumps(proof, indent=2) + '\n')
print(json.dumps({'sources': sources, 'reports': {k:{n:v[n] for n in ['tests','pass','fail','error','skip']} for k,v in reports.items()}}))
