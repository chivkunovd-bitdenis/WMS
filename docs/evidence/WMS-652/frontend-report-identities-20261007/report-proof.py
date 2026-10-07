"""Offline report identity proof using the unchanged real strict Vitest parser."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[4]
evidence = Path(__file__).resolve().parent
sys.path.insert(0, str(root / 'scripts/ci'))
from process_contracts import vitest_results

base = 'dbeabe2fd1cbb6a1cff996e379d281258bf5f0aa'
old_path = 'docs/evidence/WMS-652/common-ci-37548248403/frontend/frontend-all.json'
old_raw = subprocess.check_output(['git', 'show', base + ':' + old_path], cwd=root)
old_data = json.loads(old_raw)
old_suite = next(s for s in old_data['testResults'] if s['name'].endswith('/src/integrations/cryptoProCades.test.ts'))
old_title = 'CryptoPro CAdES readiness rejects a CryptoPro runtime below the tested baseline'
new_file = evidence / 'after-module.json'
new_raw = new_file.read_bytes()
new_data = json.loads(new_raw)
assert len(new_data['testResults']) == 1
new_suite = new_data['testResults'][0]
assert len(old_suite['assertionResults']) == len(new_suite['assertionResults']) == 37
assert all(c['status'] == 'passed' for c in new_suite['assertionResults'])
result = vitest_results(new_raw)
assert len(result) == 37 and set(result.values()) == {'passed'}
new_cases = [c for c in new_suite['assertionResults'] if c['fullName'].startswith(old_title + ': ')]
assert len(new_cases) == 2 and len({c['fullName'] for c in new_cases}) == 2
assert {c['fullName'] for c in new_cases} == {
    old_title + ': {"pluginVersion":"2.0.14999"}',
    old_title + ': {"cspVersion":"5.0.12999"}',
}
normalize = lambda name: old_title if name.startswith(old_title + ': ') else name
assert Counter(c['fullName'] for c in old_suite['assertionResults']) == Counter(normalize(c['fullName']) for c in new_suite['assertionResults'])
(evidence / 'after-parser.log').write_text('Actual unchanged process_contracts.vitest_results(after-module.json):37 unique cases accepted;37 passed,0 skipped.\n' + '\n'.join(c['fullName'] for c in new_cases) + '\n')
duplicate_data = json.loads(new_raw)
for case in duplicate_data['testResults'][0]['assertionResults']:
    if case['fullName'].startswith(old_title + ': '):
        case['fullName'] = old_title
        case['title'] = old_title.removeprefix('CryptoPro CAdES readiness ')
with tempfile.TemporaryDirectory(prefix='.raw-report-copy-', dir=evidence) as directory:
    copy = Path(directory) / 'duplicate.json'
    copy.write_text(json.dumps(duplicate_data))
    try:
        vitest_results(copy.read_bytes())
    except ValueError as error:
        assert str(error) == 'Duplicate executed case: src/integrations/cryptoProCades.test.ts::' + old_title
        (evidence / 'negative-parser.log').write_text('Actual unchanged process_contracts.vitest_results(untracked duplicate report COPY)\nValueError: ' + str(error) + '\n')
    else:
        raise AssertionError('Restored duplicate names must be refused')
assert new_file.read_bytes() == new_raw
assert subprocess.check_output(['git', 'show', base + ':' + old_path], cwd=root) == old_raw
(evidence / 'case-identities.json').write_text(json.dumps({
    'old_duplicate_fullName': old_title,
    'new_distinct_fullNames': [c['fullName'] for c in new_cases],
    'module_cases': list(result), 'module_count_before': 37, 'module_count_after': 37,
    'all_other_names_and_case_multiplicities_retained': True,
    'pass': 37, 'fail': 0, 'skipped': 0,
    'negative_control': 'Restored only two old title/fullName values in an untracked raw report copy; same parser rejects duplicate.',
    'temporary_copy_removed': True, 'tracked_reports_unchanged': True,
    'old_raw_sha256': hashlib.sha256(old_raw).hexdigest(),
    'after_raw_sha256': hashlib.sha256(new_raw).hexdigest(),
    'reproduce': 'python3 -B docs/evidence/WMS-652/frontend-report-identities-20261007/report-proof.py',
}, indent=2, ensure_ascii=False) + '\n')
print('Strict parser:37 unique PASS; original two inputs preserved; duplicate-name copy refused; raw reports unchanged.')
