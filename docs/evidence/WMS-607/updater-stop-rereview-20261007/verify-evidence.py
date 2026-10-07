"""Read-only independent Git/receipt checks for the finite WMS-607 P1 closure."""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
PRODUCT = 'bdd5a8eee8606d667a90a3b61da299b4097dc877'
BEFORE = '32c3212406eaf57b904c207bfb45d7acfd25a0b0'
RECEIPTS = '2022d0de2321fca352789a496d11413a7a816b06'
REVIEW = '30ffc6bce9fffcdc1b4e0b95b9c8782bfb41896c'
FREEZE = '040e94c956b8cc99d69d04e8cc90499a01e61a95'
SHELL = 'tools/print-agent/update_macos_direct.sh'
TEST = 'tools/print-agent/test_macos_direct_updater_stop_contract.py'
PREFIX = 'docs/evidence/WMS-607/updater-stop-fix-20261007/'


def command(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def git(ref, path):
    return command('show', ref + ':' + path)


def sha(data):
    return hashlib.sha256(data).hexdigest()


changed = command('diff-tree', '--no-commit-id', '--name-only', '-r', PRODUCT).decode().splitlines()
assert changed == [SHELL]
numstat = command('diff', '--numstat', PRODUCT + '^', PRODUCT).decode().strip()
assert numstat == '11\t5\t' + SHELL
before = git(BEFORE, SHELL)
after = git(PRODUCT, SHELL)
assert after == git(RECEIPTS, SHELL) == git('HEAD', SHELL)
assert before == git(PRODUCT + '^', SHELL)
prior = json.loads(git(REVIEW, 'docs/evidence/WMS-607/updater-independent-review-20261007/source-checks.json'))
preserved = []
for row in prior['unchanged']:
    data = git(RECEIPTS, row['path'])
    assert sha(data) == row['sha256'], row['path']
    preserved.append(row)
for path in ('tools/print-agent/wms_print_direct_macos.swift', 'tools/print-agent/build_console.py'):
    data = git(BEFORE, path)
    assert data == git(PRODUCT, path) == git(RECEIPTS, path)
    preserved.append({'path': path, 'sha256': sha(data), 'byte_equal_before_P1_fix': True})
frozen = []
for path in command('ls-tree', '-r', '--name-only', FREEZE, '--', TEST,
                    'docs/evidence/WMS-607/updater-stop-test-contract-20261007').decode().splitlines():
    data = git(FREEZE, path)
    assert data == git(RECEIPTS, path) == git('HEAD', path), path
    frozen.append({'path': path, 'sha256': sha(data)})
assert (ROOT / TEST).read_bytes() == git(FREEZE, TEST)

contract = json.loads(git(FREEZE, 'docs/evidence/WMS-607/updater-stop-test-contract-20261007/contract.json'))
old_contract = json.loads(git(RECEIPTS, 'docs/evidence/WMS-607/updater-test-contract-20261007/contract.json'))
reports = {}
for name, count, failures in [('precode', 4, 2), ('green', 4, 0), ('updater', 10, 0), ('existing', 19, 0)]:
    data = git(RECEIPTS, PREFIX + name + '.xml')
    report = ET.fromstring(data)
    assert tuple(report.get(k) for k in ('tests', 'failures', 'errors', 'skipped')) == (str(count), str(failures), '0', '0')
    ids = [c.get('classname') + '::' + c.get('name') for c in report.findall('testcase')]
    assert len(set(ids)) == count
    reports[name] = {'sha256': sha(data), 'counts': report.attrib, 'IDs': ids}
    if name == 'existing':
        continue
    assert sorted(ids) == sorted((old_contract if name == 'updater' else contract)['suite']['xml_ids'])
    for case in ids:
        raw = json.loads(git(RECEIPTS, PREFIX + name + '/' + case.split('::')[1] + '.json'))
        if name == 'updater':
            assert raw['entry_sha256'] == sha(after)
            assert raw['source_sha256'] == sha(git(PRODUCT, 'tools/print-agent/wms_print_direct_macos.swift'))
            assert raw['test_sha256'] == sha(git(RECEIPTS, 'tools/print-agent/test_macos_direct_updater_contract.py'))
        else:
            assert raw['source_sha256'] == sha(before if name == 'precode' else after)
            assert raw['test_sha256'] == sha(git(FREEZE, TEST))
            if name == 'green' and raw['mode'] in ('survives', 'term_error'):
                assert raw['before'] == raw['after'] and raw['intent_unchanged']
                assert raw['transaction'] == 1 and raw['process_alive']
                assert 'foreign' not in raw['stderr'].lower()

local = ET.parse(OUT / 'updater-stop.xml').getroot()
assert tuple(local.get(k) for k in ('tests', 'failures', 'errors', 'skipped')) == ('4', '0', '0', '0')
ids = [c.get('classname') + '::' + c.get('name') for c in local.findall('testcase')]
assert sorted(ids) == sorted(contract['suite']['xml_ids'])
local_cases = []
for case in ids:
    path = OUT / 'raw' / (case.split('::')[1] + '.json')
    raw = json.loads(path.read_bytes())
    assert raw['source_sha256'] == sha(after) and raw['test_sha256'] == sha(git(FREEZE, TEST))
    if raw['mode'] in ('survives', 'term_error'):
        assert raw['before'] == raw['after'] and raw['intent_unchanged'] and raw['transaction'] == 1
        assert raw['process_alive'] and raw['signals'].count('-TERM 42424242') == 1
    elif raw['mode'] == 'foreign':
        assert raw['signals'] == [] and raw['process_alive'] and raw['native_exit'] != 0
    local_cases.append({'case': case, 'raw_sha256': sha(path.read_bytes()), 'mode': raw['mode'],
                        'rollback_return': raw['native_exit'], 'transaction': raw['transaction'],
                        'intent_unchanged': raw['intent_unchanged'], 'process_alive': raw['process_alive']})
http_raw = []
for path in command('ls-tree', '-r', '--name-only', RECEIPTS, '--', PREFIX + 'http').decode().splitlines():
    data = git(RECEIPTS, path)
    raw = json.loads(data)
    assert raw['provenance']['source_sha256'] == sha(git(PRODUCT, 'tools/print-agent/wms_print_direct_macos.swift'))
    http_raw.append({'path': path, 'sha256': sha(data), 'source_sha256': raw['provenance']['source_sha256']})
assert len(http_raw) == 5
libraries = []
for name in ('owner-cases.md', 'failure-cases.md'):
    path = 'docs/reviews/2026-09-11-analyst-draft/' + name
    data = git('origin/etalon', path)
    assert data == git(prior['fresh_origin_etalon'], path)
    libraries.append({'path': path, 'sha256': sha(data), 'entire_prior_read_reused_byte_unchanged': True})
result = {'verdict': 'PASS: finite owned-stop P1 closed; not analytical acceptance or distribution proof',
          'product_source': PRODUCT, 'receipt_base': RECEIPTS, 'test_freeze': FREEZE, 'prior_review': REVIEW,
          'fresh_origin_etalon': command('rev-parse', 'origin/etalon').decode().strip(),
          'source_only_delta': changed, 'numstat': numstat, 'updater_before_sha256': sha(before),
          'updater_after_sha256': sha(after), 'preserved_previous_paths': preserved,
          'frozen_new_contract_paths': frozen, 'saved_reports_not_rerun': reports,
          'saved_HTTP_raw_not_rerun': http_raw,
          'independent_rerun': {'counts': local.attrib, 'cases': local_cases}, 'libraries': libraries,
          'old_ARM_package_is_final_source': False, 'analytical_acceptance': False,
          'packages_built_or_published': False, 'client_install_or_physical_print_verified': False}
(OUT / 'source-checks.json').write_text(json.dumps(result, indent=2) + '\n')
print('PASS: exact one-file 11+/5- delta; frozen 14 case expectations; saved precode2RED/green4/updater10/existing19; independent4PASS; unchanged prior15+Swift/build.')
