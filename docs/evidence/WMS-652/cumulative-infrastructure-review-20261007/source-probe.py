#!/usr/bin/env python3
"""Offline Git/source/receipt accounting only; no test function or parser replay."""
import ast
from collections import Counter
from datetime import datetime
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

BASE = '4ce7ac351cf85072fa9cfa62a7917e93f3e2a94f'
OLD = '9dae4b19f6d4dca554200e08282579414a110848'
MERGE = 'ac845328b27b5be265962695e10766efddef339e'
CI_HEAD = 'eabfad3656ec7ac923c6014657d4bf8ba5e63400'
REF = '25ebc6fe13384a55cf1f2b7e5e4054bb862d002d'
POLICY = 'guards/PROCESS_CONTRACTS.json'
TITLE = 'frontend/src/integrations/cryptoProCades.test.ts'
BOUNDARY = 'backend/tests/test_prod_deploy_backup_gate_boundary.py'
RELEASE_TEST = 'scripts/ci/tests/test_ci_release_additions.py'
SOURCE = 'backend/tests/test_prod_deploy_backup.py'
FULL_HASH = '0632023b3ebea0de566823f112e6a1eeca5b5222a3cfd538d5624da1d4d81408'
SHORT_HASH = 'ddbfe3e8447dd54825fadf01f437a1adb6fa18f2ed583f58172cb1ed962fc3da'
CI = 'docs/evidence/WMS-652/common-ci-37548248403/'
FRONT = 'docs/evidence/WMS-652/frontend-report-identities-20261007/'
BACK = 'docs/evidence/WMS-652/portable-backup-preservation-20261007/'
inputs = {}


def git(*args):
    return subprocess.check_output(['git', *args])


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(sha, path):
    raw = git('show', sha + ':' + path)
    inputs[sha + ':' + path] = {'bytes': len(raw), 'sha256': digest(raw)}
    return raw


def data(path):
    return json.loads(read(BASE, path))


old_raw, new_raw = read(OLD, POLICY), read(BASE, POLICY)
old, new = json.loads(old_raw), json.loads(new_raw)
assert old['suites'] == new['suites'] and old['files'].keys() == new['files'].keys()
assert old_raw.split(b'  "suites":', 1)[1] == new_raw.split(b'  "suites":', 1)[1]
assert len(new['files']) == 229 and len(new['suites']) == 21
assert sum(len(s['cases']) for s in new['suites'].values()) == 1173
changed = {p: {'old': old['files'][p], 'new': h} for p, h in new['files'].items()
           if h != old['files'][p]}
assert set(changed) == {RELEASE_TEST, BOUNDARY}
tree = git('ls-tree', '-r', BASE, '--', *new['files']).decode().splitlines()
old_tree = git('ls-tree', '-r', OLD, '--', *new['files']).decode().splitlines()
def entries(lines):
    return {p: metadata.split() for metadata, p in (line.split('\t', 1) for line in lines)}
current_entries, old_entries = entries(tree), entries(old_tree)
rows = []
for p, h in new['files'].items():
    mode, kind, blob = current_entries[p]
    assert kind == 'blob' and mode in {'100644', '100755'}
    assert mode == old_entries[p][0]
    raw = git('show', BASE + ':' + p)
    assert digest(raw) == h
    if p not in changed:
        assert blob == old_entries[p][2]
    rows.append([p, mode, blob, h])
assert TITLE not in new['files']
assert not any('cryptoProCades' in c for s in new['suites'].values() for c in s['cases'])

# Exact byte substitutions prove all other TypeScript/test bytes remain unchanged.
before, after = read(OLD, TITLE), read(BASE, TITLE)
title = b'rejects a CryptoPro runtime below the tested baseline'
assert before.count(title) == 1 and before.replace(title, title + b': %j', 1) == after
assert after == read('8e02998cd6b0b3bbe4d7ec36978910dcb2d2cffb', TITLE)
release = read(BASE, RELEASE_TEST)
assert release == read('88343975e13f8819d6b81cd03cddbba1d67db078', RELEASE_TEST)
assert read(OLD, RELEASE_TEST).replace(b'd61805978b3e7878d1056c99b4e6e0823edf49a5', REF.encode(), 1) == release
before_b, after_b = read(OLD, BOUNDARY), read(BASE, BOUNDARY)
expected = before_b.replace(b'import importlib.util\n', b'import importlib.util\nimport inspect\n', 1)
expected = expected.replace(b'    assertions = [ast.dump(node, include_attributes=False)',
    b'    # Python 3.14 omits empty fields by default; the legacy CI format includes them.\n'
    b'    dump_options = (\n'
    b'        {"show_empty": True} if "show_empty" in inspect.signature(ast.dump).parameters else {}\n'
    b'    )\n    assertions = [ast.dump(node, include_attributes=False, **dump_options)', 1)
expected = expected.replace(SHORT_HASH.encode(), FULL_HASH.encode(), 1)
assert expected == after_b == read('62b8b4398cb9c7bf67b507a3f9b29803814a945c', BOUNDARY)
assert before_b.split(b'\n@pytest.mark.parametrize', 1)[1] == after_b.split(b'\n@pytest.mark.parametrize', 1)[1]
source = read(BASE, SOURCE)
assert source == read(OLD, SOURCE)
original = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)
                and n.name == 'test_deploy_requires_verified_backup_before_migration')
nodes = [n for n in ast.walk(original) if isinstance(n, ast.Assert)]
params = ast.literal_eval(next(n for n in original.decorator_list if isinstance(n, ast.Call)).args[1])
assert len(nodes) == 23 and params == ['', 'dump', 'archive', 'listing', 'empty', 'network', 'retry']
full = [ast.dump(n, include_attributes=False, show_empty=True) for n in nodes]
short = [ast.dump(n, include_attributes=False, show_empty=False) for n in nodes]
assert digest(json.dumps(full, ensure_ascii=False).encode()) == FULL_HASH
assert digest(json.dumps(short, ensure_ascii=False).encode()) == SHORT_HASH
fn = next(n for n in ast.parse(after_b).body if isinstance(n, ast.FunctionDef)
          and n.name.startswith('test_all_seven'))
previous_fn = next(n for n in ast.parse(before_b).body if isinstance(n, ast.FunctionDef)
                   and n.name == fn.name)
assert ast.dump([n for n in ast.walk(fn) if isinstance(n, ast.Assert)][0]) == ast.dump(
    [n for n in ast.walk(previous_fn) if isinstance(n, ast.Assert)][0])
assert len([n for n in ast.walk(fn) if isinstance(n, ast.Assert)]) == 3
assert after_b.count(FULL_HASH.encode()) == 1 and SHORT_HASH.encode() not in after_b
options = next(n.value for n in fn.body if isinstance(n, ast.Assign)
               and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'dump_options')
def legacy_dump(node, annotate_fields=True, include_attributes=False, *, indent=None):
    raise RuntimeError('Signature-only stub must never execute')
legacy_options = eval(compile(ast.Expression(options), '<source-options>', 'eval'),
                      {'ast': SimpleNamespace(dump=legacy_dump), 'inspect': inspect})
assert legacy_options == {}
modern_options = eval(compile(ast.Expression(options), '<source-options>', 'eval'), {'ast': ast, 'inspect': inspect})
assert modern_options == {'show_empty': True}
mutant = source.replace(b'assert stop < dump', b'assert stop <= dump', 1)
mutant_fn = next(n for n in ast.parse(mutant).body if isinstance(n, ast.FunctionDef) and n.name == original.name)
mutant_nodes = [n for n in ast.walk(mutant_fn) if isinstance(n, ast.Assert)]
mutant_hash = digest(json.dumps([ast.dump(n, include_attributes=False, show_empty=True)
                                 for n in mutant_nodes], ensure_ascii=False).encode())
assert len(mutant_nodes) == 23 and mutant_hash != FULL_HASH

# Saved reports/controls only; never import/run the strict parser or target function.
old_front = data(CI + 'frontend/frontend-all.json')
after_front = data(FRONT + 'after-module.json')
all_front_cases = [(s['name'], c['fullName'], c['status']) for s in old_front['testResults'] for c in s['assertionResults']]
assert len(all_front_cases) == 1566
duplicate_groups = [k for k, n in Counter((p, c) for p, c, _ in all_front_cases).items() if n > 1]
assert len(duplicate_groups) == 1 and duplicate_groups[0][0].endswith('/src/integrations/cryptoProCades.test.ts')
old_module = next(s for s in old_front['testResults'] if s['name'].endswith('/src/integrations/cryptoProCades.test.ts'))
new_module = after_front['testResults'][0]
assert len(after_front['testResults']) == 1 and len(new_module['assertionResults']) == 37
old_name = 'CryptoPro CAdES readiness ' + title.decode()
new_names = [c['fullName'] for c in new_module['assertionResults'] if c['fullName'].startswith(old_name + ': ')]
assert set(new_names) == {old_name + ': {"pluginVersion":"2.0.14999"}', old_name + ': {"cspVersion":"5.0.12999"}'}
assert len({c['fullName'] for c in new_module['assertionResults']}) == 37
assert all(c['status'] == 'passed' for c in new_module['assertionResults'])
assert Counter(c['fullName'] for c in old_module['assertionResults']) == Counter(
    old_name if c['fullName'].startswith(old_name + ': ') else c['fullName'] for c in new_module['assertionResults'])
for p in [FRONT + 'before-parser.log', FRONT + 'negative-parser.log']:
    assert b'Duplicate executed case' in read(BASE, p)
assert b'37 unique cases accepted' in read(BASE, FRONT + 'after-parser.log')
assert json.loads(read(BASE, FRONT + 'product-scope.log')) == {'unapproved_product_paths': []}
target = data(BACK + 'target-results.json')
assert target['after'] == {'pass': 1, 'fail': 0, 'skipped': 0} and target['negative']['assertions'] == 23
assert target['mutated_copy_sha256'] == digest(mutant)
linux_log = read(BASE, CI + 'backend/shard1-job.log')
assert digest(linux_log) == 'b7adf88aa829a1eddc9e1ef909a0f90bfb087277ce0ce35ad45b56964a5682f4'
assert b'platform linux -- Python 3.11.16' in linux_log
for p in [BACK + 'preservation-proof.py', BACK + 'after-target.log', BACK + 'negative-copy.log',
          FRONT + 'report-proof.py', FRONT + 'byte-ast-proof.json', FRONT + 'provenance.json',
          BACK + 'byte-ast-proof.json', BACK + 'serialization-proof.json']:
    read(BASE, p)

shards, selected, collections, xml_ids = [], [], [], []
import xml.etree.ElementTree as ET
for idx in [0, 1]:
    receipt = data(CI + f'backend/shard{idx}/receipt.json')
    assert receipt['sha'] == MERGE and receipt['index'] == idx
    selected.append(set(receipt['selected'])); collections.append(receipt['collection'])
    cases = list(ET.fromstring(read(BASE, CI + f'backend/shard{idx}/junit.xml')).iter('testcase'))
    ids = [c.get('classname') + '::' + c.get('name') for c in cases]
    normalize = lambda x: x.split('::', 1)[0].removesuffix('.py').replace('/', '.') + '::' + x.split('::', 1)[1]
    assert len(ids) == len(set(ids)) and set(ids) == {normalize(x) for x in receipt['selected']}
    counts = dict(Counter('failed' if c.find('failure') is not None or c.find('error') is not None
                          else 'skipped' if c.find('skipped') is not None else 'passed' for c in cases))
    failures = [c for c in cases if c.find('failure') is not None or c.find('error') is not None]
    shards.append({'index': idx, 'count': len(cases), 'counts': counts, 'receipt_exit': receipt['exit_code'],
                   'failure_ids': [c.get('classname') + '::' + c.get('name') for c in failures]})
    if failures:
        assert len(failures) == 1 and FULL_HASH in failures[0].find('failure').text and SHORT_HASH in failures[0].find('failure').text
    xml_ids.extend(ids)
assert collections[0] == collections[1] and len(collections[0]) == len(set(collections[0])) == 4631
assert not (selected[0] & selected[1]) and selected[0] | selected[1] == set(collections[0])
assert len(xml_ids) == len(set(xml_ids)) == 4631
assert shards[0]['counts'] == {'passed': 2217, 'skipped': 99}
assert shards[1]['counts'] == {'passed': 2215, 'skipped': 99, 'failed': 1}
jobs, run = data(CI + 'jobs-final.json'), data(CI + 'run-final.json')
assert run['status'] == 'completed' and run['conclusion'] == 'failure'
elapsed = (max(datetime.fromisoformat(j['completed_at']) for j in jobs['jobs'])
           - datetime.fromisoformat(run['run_started_at'])).total_seconds()
assert elapsed == 743
assert git('diff', '--name-only', MERGE, CI_HEAD).strip() == b''
assert git('diff', '--name-only', OLD, BASE, '--', '.github/workflows', 'frontend/package.json',
           'frontend/package-lock.json', 'backend/app', 'frontend/tests-e2e').strip() == b''
assert git('diff', '--name-only', REF, BASE, '--', 'frontend/src', 'backend/app').decode().splitlines() == [TITLE]

out = {'verdict': 'TECHNICAL_PASS_FIRST_THREE_INFRASTRUCTURE_CORRECTIONS', 'source': BASE,
       'comparison': OLD, 'policy_sha256': digest(new_raw), 'protected_files': 229,
       'regular_file_modes': dict(Counter(row[1] for row in rows)),
       'all_git_blob_hashes_and_modes_match': True,
       'protected_rows_sha256': digest(json.dumps(sorted(rows)).encode()), 'changed_protected_hashes': changed,
       'unchanged_protected_files': 227, 'suites': 21, 'case_ids': 1173,
       'suite_definitions_byte_identical': True, 'suite_case_counts': {k: len(v['cases']) for k, v in new['suites'].items()},
       'reference_migration': 'Frozen883 bytes; priorab0 three-unit PASS retained; no rerun',
       'titles': {'only_literal_changed': True, 'module_cases': 37, 'new_names': new_names,
                  'not_registered_in_protected_policy': True, 'strict_parser_unchanged': True,
                  'saved_negative_duplicate_copy_refused': True},
       'backup': {'original_source_byte_identical': True, 'assertions': 23, 'parameters': params,
                  'full_format_sha256': FULL_HASH, 'short_format_sha256': SHORT_HASH,
                  'saved_linux_python': '3.11.16',
                  'five_gate_bodies_and_decorators_byte_identical': True, 'fixed_single_digest': True,
                  'modern_options': modern_options, 'signature_only_legacy_options': legacy_options,
                  'legacy_target_not_reexecuted': True, 'saved_target_receipt': target,
                  'independent_offline_mutation_hash': mutant_hash},
       'ci': {'run': 37548248403, 'attempt': 1, 'merge': MERGE, 'head': CI_HEAD, 'merge_tree_equals_head': True,
              'completed_conclusion': run['conclusion'], 'elapsed_to_last_job_seconds': elapsed,
              'frontend_saved_cases': 1566, 'old_duplicate_groups': 1, 'shards': shards,
              'backend_collection_exact_union': 4631, 'passed': 4432, 'skipped': 198, 'failed': 1,
              'pg_aggregator_execution_not_proven_pass': True,
              'job_conclusions': {j['name']: j['conclusion'] for j in jobs['jobs']}},
       'fourth_cdp_correction': 'PENDING cause/test-contract/code/Linux target; prior743 diagnosis retained',
       'analyst_acceptance': 'Separate role pending; this is technical review plus bounded analytical findings',
       'final_source_approved': False, 'release_approved': False,
       'new_test_browser_build_dispatch_executions': 0, 'inputs': inputs}
Path(__file__).with_name('source-checks.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
print('Offline PASS: three bounded infrastructure corrections;229 hashes/modes;21 suites/1173 IDs; saved CI remains FAIL.')
