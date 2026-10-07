"""Immutable Git/source and saved-receipt checks only; no Swift compilation or tests.
Run from repository root: python3 -B <this-file> > source-checks.json
"""
import ast
import hashlib
import json
import re
import subprocess

SOURCE = 'dc652472d75812dbebc68ef4353a718b0f629cbe'
BASE = '77443e92dba2872993ee358cfb7c4c88279b47c8'
FROZEN = '443bcbdf19ec3c81c1fc04dbc53a5a9a45ead609'
SWIFT = 'tools/print-agent/wms_print_direct_macos.swift'
CONTRACT = 'docs/evidence/WMS-607/artmaks-http-test-contract-20261007/'
RAW = 'docs/evidence/WMS-607/artmaks-http-repair-20261007/'
hashes = {}


def git(*args):
    return subprocess.check_output(['git', *args])


def read(path, ref=SOURCE):
    data = git('show', ref + ':' + path)
    hashes[ref + ':' + path] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return data


def load(path):
    return json.loads(read(path))


assert git('rev-parse', SOURCE+'^').decode().strip() == FROZEN
assert git('rev-parse', FROZEN+'^').decode().strip() == BASE
old = read(SWIFT, BASE).decode(); new = read(SWIFT).decode()
assert read(SWIFT, FROZEN).decode() == old
expected = old
replacements = [
    ('scheduleNow:Bool=true) throws -> [String:Any] {',
     'scheduleNow:Bool=true,retryFailedBeforeSubmit:Bool=false) throws -> [String:Any] {'),
    ('            return try detail(key)!\n        }\n        guard !jobs.values.contains',
     '            // The explicit legacy scan may retry only a proven pre-submit failure.\n'
     '            // Keep lookup and retry under the same lock so concurrent scans cannot\n'
     '            // mistake a job already submitting/accepted for the earlier failure.\n'
     '            if retryFailedBeforeSubmit && old.status=="failed_before_submit" { return try retry(key) }\n'
     '            return try detail(key)!\n        }\n        guard !jobs.values.contains'),
    ('var result=try printer.printJob(body)',
     'var result=try printer.printJob(body,retryFailedBeforeSubmit:body["protocolVersion"] as? Int != 2)'),
    (r'''                if result["receipt"] == nil || ["held","canceled","aborted","stopped"].contains(result["status"] as? String ?? "") { result["error"]="Задание сохранено, приём очередью не подтверждён. История: \(localOrigin)";respond(descriptor,status:409,value:result,origin:origin) }''',
     r'''                if result["receipt"] == nil || ["held","canceled","aborted","stopped"].contains(result["status"] as? String ?? "") {
                    let reason=result["status"] as? String == "failed_before_submit" ? result["reason"] as? String:nil
                    result["error"]="\(reason ?? "Задание сохранено, приём очередью не подтверждён.") История: \(localOrigin)"
                    respond(descriptor,status:409,value:result,origin:origin)
                }'''),
]
for before, after in replacements:
    assert expected.count(before) == 1, before
    expected = expected.replace(before, after)
assert expected == new
assert git('diff', '--numstat', BASE, SOURCE, '--', SWIFT).decode().split()[:2] == ['11', '3']
changed = git('diff', '--name-only', BASE, SOURCE).decode().splitlines()
assert [p for p in changed if not p.startswith('docs/') and p != 'tools/print-agent/test_macos_artmaks_http_contract.py'] == [SWIFT]
contract = load(CONTRACT + 'contract.json')
provenance = load(RAW + 'source-provenance.json')
assert hashes[SOURCE+':'+SWIFT]['sha256'] == provenance['candidate_swift_sha256']
for path, digest in provenance['unchanged_test_sha256'].items():
    assert read(path) == read(path, FROZEN)
    assert hashes[SOURCE+':'+path]['sha256'] == digest
for path, entry in contract['closure'].items():
    data = read(path, FROZEN)
    assert hashlib.sha256(data).hexdigest() == entry['sha256']
    assert git('rev-parse', FROZEN+':'+path).decode().strip() == entry['git_blob']
    if path != SWIFT:
        assert data == read(path)
manifest = load(CONTRACT + 'manifest.json')
for path, entry in manifest.items():
    data = read(path)
    assert data == read(path, FROZEN)
    assert len(data) == entry['bytes'] and hashlib.sha256(data).hexdigest() == entry['sha256']
test = ast.parse(read(contract['test_file']))
methods = [n.name for n in ast.walk(test) if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
assert methods == contract['cases'] and len(set(methods)) == 5
receipts = {}
for label in ('before', 'after'):
    result = {}
    for name in methods:
        item = load(RAW + label + '/' + name + '.json')
        assert item['provenance']['source_sha256'] == hashlib.sha256((old if label=='before' else new).encode()).hexdigest()
        result[name] = {'responses': [[r['path'],r['http'],r['body'].get('status'),r['body'].get('receipt')]
                                      for r in item['responses']],
                        'external_lp_count': sum(c[0]=='lp' for c in item['commands'])}
    receipts[label] = result
name = 'test_legacy_same_key_recovers_only_after_proven_pre_submit_failure'
assert [r[1] for r in receipts['before'][name]['responses'] if r[0]=='/print'] == [409,200,409,409]
assert [r[1] for r in receipts['after'][name]['responses'] if r[0]=='/print'] == [409,200,200,200]
assert receipts['before'][name]['external_lp_count'] == 1 and receipts['after'][name]['external_lp_count'] == 2
reason = load(RAW + 'after/test_legacy_error_preserves_specific_pre_submit_reason.json')
failure = next(r['body'] for r in reason['responses'] if r['path']=='/print')
assert failure['reason'] in failure['error'] and 'Этикетка не отправлена' in failure['reason']
for name in methods[2:]:
    assert receipts['after'][name]['external_lp_count'] == 1
logs = {}
for name, count in (('http-five-green.log',5),('frozen-six-green.log',6),('resolver-five-green.log',5),('native-three-green.log',3)):
    log = read(RAW+name).decode()
    assert len(re.findall(r' \.\.\. ok$', log, re.M)) == count and '\nOK\n' in log
    assert not re.search(r'FAILED|ERROR|skipped',log)
    logs[name] = {'PASS':count,'SKIP':0,'FAIL':0,'ERROR':0}
for path in (CONTRACT+'precode-red.log',RAW+'developer-precode-red.log'):
    log = read(path).decode()
    assert 'FAILED (failures=2)' in log and 'ERROR:' not in log
mutation = load(CONTRACT+'mutation-result.json')
assert mutation['all_rejected'] and mutation['expected_failures'] == 3 and mutation['tracked_source_unchanged']
mutant_log = read(CONTRACT+'mutation-red.log').decode()
assert 'FAILED (failures=3)' in mutant_log and 'ERROR:' not in mutant_log
parallel = load(RAW+'concurrent-http-recovery.json')
assert parallel['result']=='PASS' and parallel['parallel_legacy_repeats']==8 and parallel['submissions']==1
assert parallel['provenance']['source_sha256']==provenance['candidate_swift_sha256']
assert len([c for c in parallel['commands'] if c[0]=='lp']) == 1
responses = [r for r in parallel['responses'] if r['path']=='/print']
assert (responses[0]['http'],responses[0]['body']['status'])==(409,'failed_before_submit')
assert len(responses[1:])==8 and all((r['http'],r['body']['status'],r['body']['receipt'])==(200,'accepted','Label_Printer-41') for r in responses[1:])
for path in ('docs/reviews/2026-09-11-analyst-draft/owner-cases.md',
             'docs/reviews/2026-09-11-analyst-draft/failure-cases.md'):
    assert read(path)==read(path,'4c532f0cccfb8f99b34d68d9630a3763038fbc5f')
print(json.dumps({'verdict':'TECHNICAL PASS bounded legacy HTTP P-A5/P-A6 delta',
    'SOURCE':SOURCE,'previous_acceptance_BASE':BASE,'frozen_HTTP_contract':FROZEN,
    'product_delta':'ONLY Swift 11 insertions/3 deletions; four exact textual replacements restore BASE bytes',
    'all_other_source_bytes_and_frozen_tests_preserved':True,'HTTP_test_cases':methods,
    'contract_manifest_members_verified':len(manifest),'saved_receipts':receipts,'saved_green_logs':logs,
    'meaningful_precode':{'targetFAIL':2,'preservationPASS':3,'skip':0,'error':0},
    'purposeful_copy_mutation':mutation,'concurrent_recovery':{'identical_legacy_requests':8,'accepted_responses':8,'external_lp_boundary':1},
    'input_hashes':hashes,'new_test_compile_browser_print_CI_runs':[],
    'updater_R_U1_to_8_packages_install_physical_print_and_analyst_acceptance':'NOT approved by this review'},ensure_ascii=False,indent=2))
