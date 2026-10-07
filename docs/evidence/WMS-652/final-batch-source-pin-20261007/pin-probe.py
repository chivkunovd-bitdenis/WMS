"""Read immutable Git objects only. Run from the repository with Python stdlib:
python3 -B docs/evidence/WMS-652/final-batch-source-pin-20261007/pin-probe.py
No test, document gate, native command, build, browser, CI or network replay.
"""
import collections
import hashlib
import json
import subprocess

BASE = '4b298efc95be7b4b6b7fe5665be9f3671f1fe747'
SOURCE = '90744e4b8dde3cc69a951269c00f6f1daa0a4d00'
REVIEWED = '3867d9e74cce3807b5e719c3f2c912fc0cfbd8d6'
REVIEW = '830e8ad6de4faa6cf6c23e6936994f2cb9c8e134'
PRODUCT = '1cf85fc500bc6ee7a5f4ef283b250c4bf59c5333'
ANALYST = '7e671452408563b6091555cf6287d4eff4b0f758'
IMPORT = '07b49705462eeb2f4da934b1a946afe751a82b43'
LEDGER_COMMIT = '353b711dd10297ae86f9cd8184de52d99c33df5a'
POLICY = 'guards/PROCESS_CONTRACTS.json'
EVIDENCE = 'docs/evidence/WMS-652/batch-exact-pair-review-20261007/'
ACCEPTANCE = 'docs/evidence/WMS-652/batch-release-acceptance-20261007/'
LEDGER = 'docs/reviews/contract-corrections/WMS-662.json'
ARTIFACT = 'docs/reviews/wms652-batch-exact-fixture-review-20261007.md'


def git(*args):
    return subprocess.check_output(['git', *args])


def blob(path, ref=SOURCE):
    return git('show', ref + ':' + path)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tree(ref):
    result = {}
    for row in git('ls-tree', '-r', '-z', ref).split(b'\0'):
        if row:
            header, path = row.split(b'\t', 1)
            result[path.decode()] = header.decode().split()
    return result


actual, reviewed = tree(SOURCE), tree(REVIEWED)
assert POLICY not in tree(BASE)
git('merge-base', '--is-ancestor', BASE, SOURCE)
raw = blob(POLICY)
assert raw == blob(POLICY, REVIEWED)
policy_hash = sha(raw)
assert policy_hash == '58a95dc526e15dff10999925d33f8ed935c2100b6231f0bfb70ab2b7985ed6e8'
policy = json.loads(raw)
prior_raw = blob(EVIDENCE + 'proof.json')
assert prior_raw == blob(EVIDENCE + 'proof.json', REVIEW)
assert blob(EVIDENCE + 'review.md') == blob(EVIDENCE + 'review.md', REVIEW)
prior = json.loads(prior_raw)
assert prior['SOURCE'] == REVIEWED and prior['policy_sha256'] == policy_hash
rows = []
for path, digest in sorted(policy['files'].items()):
    assert actual[path] == reviewed[path], path
    mode, kind, oid = actual[path]
    assert kind == 'blob' and mode in ('100644', '100755'), path
    assert sha(blob(path)) == digest, path
    rows.append([path, mode, oid, digest])
assert len(rows) == 238
modes = dict(collections.Counter(row[1] for row in rows))
assert modes == {'100644': 230, '100755': 8}
assert len(policy['suites']) == 22
assert sum(len(s['cases']) for s in policy['suites'].values()) == 1192
assert all(len(s['cases']) == len(set(s['cases'])) for s in policy['suites'].values())
retention = {}
for ref in ('93b0757103fbd29fb00d4f198f6baab8def85172',
            'b815b166fbcd4db9d014ed1a9d961d7c56225130',
            '5b9df5acfba055bf94d5b3b21793ce2a233edff6'):
    old = json.loads(blob(POLICY, ref))
    old_tree = tree(ref)
    assert set(old['files']) <= set(policy['files'])
    assert all(actual[p][:2] == old_tree[p][:2] for p in old['files'])
    for name, definition in old['suites'].items():
        now = policy['suites'][name]
        assert {k: v for k, v in definition.items() if k != 'cases'} == {
            k: v for k, v in now.items() if k != 'cases'}
        assert set(definition['cases']) <= set(now['cases'])
        assert [c for c in now['cases'] if c in set(definition['cases'])] == definition['cases']
    retention[ref] = {
        'files': len(old['files']),
        'IDs': sum(len(s['cases']) for s in old['suites'].values()),
        'paths_modes_IDs_order_and_suite_definitions_retained': True,
        'existing_digest_migrations': {
            p: {'before': d, 'after': policy['files'][p]}
            for p, d in old['files'].items() if policy['files'][p] != d},
    }
backend = policy['suites']['backend-fbs']
assert len(backend['cases']) == 627 and backend['report'] == 'backend-all.xml'
assert backend['exact'] is False and backend['format'] == 'junit'
assert git('diff', '--name-only', PRODUCT, SOURCE, '--', 'backend/app', 'frontend/src') == b''
changed = git('diff', '--name-only', REVIEWED, SOURCE).decode().splitlines()
assert all(p.startswith('docs/') for p in changed)

ledger_raw = blob(LEDGER)
assert ledger_raw == blob(LEDGER, LEDGER_COMMIT)
ledger = json.loads(ledger_raw)
expected = prior['proposed_complete_ledger']
expected = json.loads(json.dumps(expected))
for item in expected['fixture_corrections']:
    item['review']['evidence_commit'] = IMPORT
assert ledger == expected
assert ledger['owner_supersessions'] == json.loads(blob(LEDGER, REVIEWED))['owner_supersessions']
assert ledger_raw[ledger_raw.index(b'  "owner_supersessions"'):] == blob(LEDGER, REVIEWED)[
    blob(LEDGER, REVIEWED).index(b'  "owner_supersessions"'):]
assert actual[ARTIFACT][2] == 'b566e9896a7571ce46cde3ffe385c3800867b66e'
assert tree(IMPORT)[ARTIFACT] == actual[ARTIFACT]
assert ARTIFACT in git('diff-tree', '--no-commit-id', '--name-only', '-r', IMPORT).decode().splitlines()
git('merge-base', '--is-ancestor', IMPORT, SOURCE)

actor_hashes = {}
for path in (ACCEPTANCE + 'README.md', ACCEPTANCE + 'source-probe.json',
             'docs/requirements/WMS-652.md', 'docs/requirements/WMS-662.md',
             'docs/KANONICHESKIY_BACKLOG.md'):
    content = blob(path)
    assert content == blob(path, ANALYST), path
    actor_hashes[path] = sha(content)
a = json.loads(blob(ACCEPTANCE + 'source-probe.json'))
assert a['analyst_session'] == '01a11390-1014-76a0-9302-fbe0fd46ed1f'
assert a['reviewed_source'] == REVIEWED and a['review_import_commit'] == IMPORT
assert a['accepted_PRODUCT_reference_unchanged'] == PRODUCT
assert a['both_exact_fixture_corrections'] == ledger['fixture_corrections']
assert a['software_acceptance'].startswith('PASS bounded PID fixture/exact pairs/ledger')
assert a['release_accepted'] is False and a['final_SOURCE_pin_approval'] is False
assert a['successful_R51_C65_timing_goal_proven'] is False
for path, digest in a['input_sha256'].items():
    assert sha(blob(path)) == digest, path
pg = 'docs/evidence/WMS-652/all-pg-comparison-37563300572/'
for name in ('actual-command-outcomes.json', 'verified-raw-reports.json'):
    assert blob(pg + name) == blob(pg + name, REVIEWED)

print(json.dumps({
    'verdict': 'APPROVED exact bootstrap BASE/SOURCE pair; accepted prepared candidate only',
    'BASE': BASE, 'SOURCE': SOURCE, 'PRODUCT': PRODUCT, 'policy_sha256': policy_hash,
    'regular_Git_files': 238, 'modes': modes, 'suites': 22, 'required_IDs': 1192,
    'backend_required_cases': 627,
    'all238_actual_hashes_match_policy_and_Git_objects_identical_to': REVIEWED,
    'actual_git_rows_sha256': sha(json.dumps(rows, separators=(',', ':')).encode()),
    'old_retention_and_previously_reviewed_hash_migrations': retention,
    'docs_only_delta_from_reviewed_source': changed,
    'previous_independent_review': REVIEW, 'ledger_commit': LEDGER_COMMIT,
    'ledger_sha256': sha(ledger_raw), 'ledger_matches_approved_complete_template': True,
    'owner_supersessions_verbatim_preserved': True,
    'actual_review_import_changed_artifact': IMPORT,
    'artifact_blob': actual[ARTIFACT][2], 'whole_APP_equal_PRODUCT': True,
    'distinct_analyst_commit': ANALYST, 'analyst_source': a['acceptance_source'],
    'actor_documents_sha256': actor_hashes,
    'native_PG_receipts_unchanged_and_prior_verdict_retained': a['native_PG'],
    'historical_full_CI': a['latest_full_CI']['run'],
    'historical_full_CI_conclusion': a['latest_full_CI']['conclusion'],
    'successful_full_CI_10_to_15_minutes_proven': False,
    'historical_SQLite_lock_owner': 'UNKNOWN',
    'new_tests_build_PG_browser_CI_document_gate_runs': [],
    'main_pin_activation_release_deploy_or_physical_proof': 'NOT performed or claimed',
    'next': 'ordinary configuration-only PR pins exact SOURCE90744e; fresh full candidate CI remains mandatory',
}, ensure_ascii=False, indent=2))
