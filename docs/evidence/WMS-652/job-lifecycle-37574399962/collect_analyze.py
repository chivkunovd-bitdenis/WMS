"""Read-only artifact recovery and exact-ID ledger; never execute browser/source."""
import collections, gzip, hashlib, json, subprocess, zipfile
from pathlib import Path, PurePosixPath
ROOT=Path(__file__).resolve().parent
HEAD='bb8528b3127f3375fb29685577b2ab045d607658'
SOURCE='4c532f0cccfb8f99b34d68d9630a3763038fbc5f'
def sha(b): return hashlib.sha256(b).hexdigest()
def write(name,obj): (ROOT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
def git(*args): return subprocess.check_output(['git',*args])
def main():
    run=json.loads((ROOT/'run-final.json').read_text());arts=json.loads((ROOT/'artifacts.json').read_text())
    assert (run['id'],run['head_sha'],run['head_branch'],run['run_attempt'],run['status'])==(37574399962,HEAD,'codex/wms652-chrome141-job-lifecycle-diagnostic',1,'completed')
    artifacts=arts['artifacts'];assert len(artifacts)==1
    a=artifacts[0];assert a['name']==f'wms652-chrome141-job-lifecycle-browser43-{HEAD}-37574399962-1'
    assert a['workflow_run']['head_sha']==HEAD and not a['expired']
    archive=ROOT/'artifact.zip';zbytes=archive.read_bytes();members=[];raw={}
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if name.endswith('/'):continue
            p=PurePosixPath(name);assert not p.is_absolute() and '..' not in p.parts and name not in raw
            b=z.read(name);raw[name]=b;compress=len(b)>=262144 or name.endswith('.json')
            stored=gzip.compress(b,mtime=0) if compress else b
            target=Path('raw')/name;target=target.with_name(target.name+'.gz') if compress else target
            (ROOT/target).parent.mkdir(parents=True,exist_ok=True);(ROOT/target).write_bytes(stored)
            recovered=gzip.decompress(stored) if compress else stored;assert recovered==b
            members.append({'artifact_member':name,'stored_path':str(target),'encoding':'gzip' if compress else 'identity','original_bytes':len(b),'original_sha256':sha(b),'stored_bytes':len(stored),'stored_sha256':sha(stored),'recovered_byte_equal':True})
    write('raw-manifest.json',{'run_id':run['id'],'attempt':1,'diagnostic_sha':HEAD,'artifact_id':a['id'],'downloaded_zip_bytes':len(zbytes),'downloaded_zip_sha256':sha(zbytes),'member_count':len(members),'all_members_recoverable':True,'members':members})
    def b(suffix):
        found=[v for k,v in raw.items() if k.endswith('/'+suffix)];assert len(found)==1,suffix;return found[0]
    def j(suffix):return json.loads(b(suffix))
    report=j('result.json');ctx=j('error-context.json');transport=j('cdp-transport.json');prep=j('preparation.json');after=j('source-after.json');exit_results=j('exit-results.json')
    # Native transport has one original session; no negative auxiliary IDs belong here.
    if isinstance(transport,dict):
        records=transport.get('events',transport.get('transport'));original_pending=transport.get('pendingCommandIds')
    else:records=transport;original_pending=None
    assert isinstance(records,list)
    sends=[r for r in records if r['kind']=='command-send'];replies=[r for r in records if r['kind']=='command-result'];timeouts=[r for r in records if r['kind']=='command-timeout']
    assert all(r['commandId']>0 for r in sends+replies)
    sendmap={r['commandId']:r for r in sends};replymap={r['commandId']:r for r in replies}
    focused=ctx['focused'];lookup=ctx['lookup'];events=focused['events'];own=lookup['events']
    auxsend={r['commandId']:r for r in own if r['kind']=='aux-lookup-send'};auxreply={r['commandId']:r for r in own if r['kind']=='aux-lookup-reply'}
    assert all(i<0 for i in auxsend.keys()|auxreply.keys())
    expected=json.loads(git('show',f'{SOURCE}:frontend/tests-e2e/wms652-critical/cases.json'))
    complete=[r['id'] for r in report['cases']]==expected and len(expected)==43
    frozen=git('show',f'{SOURCE}:frontend/tests-e2e/wms652-critical/browser.mjs');generated=b('generated-browser.mjs')
    insertions=[(b'// WMS652 critical real-screen contracts.',b"import { createJobLookupObserver } from './identity-observer.untracked.mjs';\nconst errorContext=createJobLookupObserver();\n"),(b'      if (msg.id) {',b'      try { errorContext.message(this,msg); } catch { errorContext.observerFailure(); }\n'),(b'  await writeFile(`${dir}/cdp-transport.json`',b'  await writeFile(`${dir}/error-context.json`,errorContext.serialize(cdp,report));\n')]
    reverse=generated
    for anchor,insertion in reversed(insertions):assert reverse.count(insertion+anchor)==1;reverse=reverse.replace(insertion+anchor,anchor,1)
    assert reverse==frozen==b('frozen-browser-source.mjs')
    shell=git('show',f'{SOURCE}:scripts/ci/run_critical_fbs_browser.sh');assert shell==b('original-shell.sh')
    assert b('generated-shell.sh').replace(b'node frontend/tests-e2e/wms652-critical/browser.identity-diagnostic.untracked.mjs',b'node frontend/tests-e2e/wms652-critical/browser.mjs',1)==shell and b'600s' in shell
    assert prep['source']==SOURCE and prep['diagnostic_head']==HEAD and prep['source_sha256']==after and prep['reverse_byte_equal'] and prep['shell_reverse_byte_equal']
    tree={line.split(b'\t',1)[1].decode():line.split(b'\t',1)[0].decode() for line in git('ls-tree','-rz',SOURCE).split(b'\0') if line}
    expected_bindings={p:v for p,v in tree.items() if not p.startswith('docs/') and p!='.github/workflows/ci.yml'}
    assert prep['source_git_bindings']==expected_bindings
    for name,source_name in [('generated-observer.mjs','job-lookup.mjs'),('generated-error-context.mjs','error-context.mjs')]:assert b(name)==git('show',f'{HEAD}:scripts/ci/wms652-identity-diagnostic/{source_name}')
    pattern=b"  await cdp.send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});"
    assert frozen.count(pattern)==1 and sha(pattern)==prep['request_only_pattern_sha256']
    original_errors=[r for r in replies if r.get('nativeError')]
    pairs=[]
    for aid,s in auxsend.items():
        reply=auxreply.get(aid);fid=s['requestId'];assert reply is None or reply['requestId']==fid
        if reply and reply['state']=='ALIVE':assert reply['nativeError']=={'code':-32000,'message':'Can only get response body on HeadersReceived pattern matched requests.'}
        if reply and reply['state']=='ABSENT':assert reply['nativeError']=={'code':-32602,'message':'Invalid InterceptionId.'}
        exact=[{'send':r,'reply':replymap.get(r['commandId'])} for r in sends if r.get('requestId')==fid]
        # Document state at this exact auxiliary send event index, not a claimed request owner.
        active={};last_frame=None;last_nav=None
        for r in own[:own.index(s)]:
            if r.get('method')=='Runtime.executionContextsCleared':active.clear()
            elif r.get('method')=='Runtime.executionContextCreated':active[r['executionContextId']]=r
            elif r.get('method')=='Runtime.executionContextDestroyed':active.pop(r.get('executionContextId'),None)
            elif r.get('method')=='Page.frameNavigated' and r.get('frameId')==s.get('frameId'):last_frame=r
            elif r.get('kind')=='navigate-reply' and r.get('frameId')==s.get('frameId'):last_nav=r
        pairs.append({'aux_send':s,'aux_reply':reply,'exact_original_commands':exact,'active_default_frame_contexts_at_aux_send':[r for r in active.values() if r.get('frameId')==s.get('frameId') and r.get('isDefault')], 'last_frame_navigation_observed_at_aux_send':last_frame,'last_navigate_reply_observed_at_aux_send':last_nav,'request_loader_or_execution_context_binding':'UNKNOWN: paused has frameId but no networkId/loaderId/executionContextId; document state is observation only'})
    failures=[]
    for r in original_errors:
        s=sendmap[r['commandId']];fid=s.get('requestId')
        error_context=[x for x in events if x.get('kind')=='native-error-context' and x.get('commandId')==r['commandId']]
        pauses=[x for x in events if x.get('method')=='Fetch.requestPaused' and x.get('requestId')==fid]
        failures.append({'send':s,'reply':r,'native_reply_ms_after_send':r['utcMs']-s['utcMs'],'focused_error_context':error_context,'exact_paused_records':pauses,'exact_aux_pairs':[x for x in pairs if x['aux_send']['requestId']==fid]})
    ledger={'run_id':run['id'],'attempt':1,'diagnostic_sha':HEAD,'source':SOURCE,'run_conclusion':run['conclusion'],'strict_status':report['status'],'case_counts':dict(collections.Counter(r['status'] for r in report['cases'])),'exact43_complete':complete,'cases':report['cases'],'exit_results':exit_results,'environment':b('environment.txt').decode(),'source_bindings':len(prep['source_git_bindings']),'source_hashes':len(after),'source_unchanged':True,'reverse_browser_byte_equal':True,'shell_600s_runner_path_only':True,'original_transport_records':len(records),'original_positive_send_count':len(sends),'original_positive_reply_count':len(replies),'original_pair_ids_equal':sendmap.keys()==replymap.keys(),'original_send_reply_ids_unique':len(sendmap)==len(sends) and len(replymap)==len(replies),'original_timeout_count':len(timeouts),'original_pending_command_ids':focused['pendingCommandIds'],'original_native_error_count':len(original_errors),'focused_native_error_count':focused['nativeErrorsObserved'],'focused_records':len(events),'focused_drops':focused['dropped'],'auxiliary_summary':{k:lookup[k] for k in ['counts','dropped','pending','estimatedRetainedBytes']},'auxiliary_send_count':len(auxsend),'auxiliary_reply_count':len(auxreply),'auxiliary_pair_ids_equal':auxsend.keys()==auxreply.keys(),'auxiliary_records':len(own),'combined_records':len(events)+len(own),'context_file_bytes':len(b('error-context.json')),'errors':failures,'all_exact_aux_pairs':pairs,'historical_etalon_cause':'UNKNOWN','actual_retirement_reason_or_JS_caller':'UNKNOWN'}
    assert complete and len(expected_bindings)==2546 and ledger['original_send_reply_ids_unique'] and ledger['original_pair_ids_equal']
    assert len(events)+len(own)<=100000 and len(b('error-context.json'))<=64*1024*1024
    write('ledger.json',ledger)
    print(json.dumps({k:ledger[k] for k in ['strict_status','case_counts','original_positive_send_count','original_positive_reply_count','original_native_error_count','focused_drops','auxiliary_summary','source_bindings','source_unchanged']},indent=2))
    print(json.dumps([{'command':r['send']['commandId'],'FetchID':r['send'].get('requestId'),'aux_state':[p['aux_reply']['state'] if p['aux_reply'] else 'pending' for p in r['exact_aux_pairs']]} for r in failures]))
    archive.unlink() # All exact members were recovered and SHA-checked into permanent Git paths.
if __name__=='__main__':main()
