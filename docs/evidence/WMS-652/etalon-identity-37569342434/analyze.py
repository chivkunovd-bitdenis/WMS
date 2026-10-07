import collections,gzip,hashlib,json
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path('docs/evidence/WMS-652/etalon-identity-37569342434')
def load(name):
 matches=list((ROOT/'raw').rglob(name))+list((ROOT/'raw').rglob(name+'.gz'))
 assert len(matches)==1,(name,matches)
 p=matches[0];return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
d=load('identity-telemetry.json');e=d['events'];sends={r['commandId']:r for r in e if r['kind']=='native-send'}
pauses=[r for r in e if r.get('method')=='Fetch.requestPaused']
errors=[r for r in e if r['kind']=='native-result' and r.get('outcome')=='error']
rows=[]
for r in errors:
 s=sends.get(r['commandId']);p=[x for x in pauses if x.get('requestId')==r.get('requestId') and x['nodeMonoMs']<=r['nodeMonoMs']]
 p=p[-1] if p else None
 network=[x for x in e if p and p.get('networkId') and x.get('requestId')==p['networkId'] and x.get('method','').startswith('Network.')]
 same_url=[x for x in e if p and p.get('url') and x.get('url')==p['url'] and x.get('method')=='Network.requestWillBeSent' and abs(x['nodeMonoMs']-p['nodeMonoMs'])<1000]
 rows.append({'reply':r,'send':s,'exact_id_paused':p,'send_to_reply_mono_ms':r['nodeMonoMs']-s['nodeMonoMs'] if s else None,'exact_network_identity_records':network,'nearby_same_url_requestWillBeSent_observations_NOT_identity_proof':same_url})
missing=[p for p in pauses if not p.get('networkId')]
counts=collections.Counter((p.get('requestMethod'),p.get('resourceType'),urlsplit(p.get('url','')).path) for p in missing)
prep=load('preparation.json');after=load('source-after.json');result=load('result.json');exits=load('exit-results.json')
summary={'source':prep['source'],'diagnostic_head':prep['diagnostic_head'],'case_count':len(result['cases']),'case_outcomes':dict(collections.Counter(x['status'] for x in result['cases'])),'strict_status':result['status'],'exit_results':exits,'source_after_equals_before':after==prep['source_sha256'],'telemetry':{k:v for k,v in d.items() if k!='events'},'record_kind_counts':dict(collections.Counter(x['kind'] for x in e)),'send_method_counts':dict(collections.Counter(x['method'] for x in sends.values())),'native_error_count':len(errors),'native_errors':rows,'missing_network_id_count':len(missing),'missing_network_types':[{'requestMethod':m,'resourceType':t,'urlPath':p,'count':n} for (m,t,p),n in counts.items()]}
(ROOT/'analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ['native_errors','telemetry','missing_network_types','send_method_counts']},indent=2))
print('MISSING_NETWORK_TYPES',json.dumps(summary['missing_network_types']))
for row in rows:print('NATIVE_ERROR',json.dumps(row))
missing_rows=[]
for p in missing:
 commands=[x for x in e if x['kind']=='native-send' and x.get('requestId')==p['requestId']]
 replies=[x for x in e if x['kind']=='native-result' and x.get('requestId')==p['requestId']]
 assert len(commands)==len(replies)==1
 s,r=commands[0],replies[0];assert s['commandId']==r['commandId']
 missing_rows.append({'paused':p,'sole_native_send':s,'sole_native_reply':r,'send_to_reply_node_mono_ms':r['nodeMonoMs']-s['nodeMonoMs'],'redirectedRequestId_present':'redirectedRequestId' in p,'exact_network_join':'UNAVAILABLE: paused event has no networkId; URL/time coincidence is not identity proof'})
changed=[r for r in e if r['kind']=='native-result' and (r.get('generation')!=r.get('currentGeneration') or r.get('caseId')!=r.get('currentCaseId'))]
fetch_changed=[]
for r in changed:
 if r.get('method')=='Fetch.fulfillRequest':
  s=sends[r['commandId']];p=[p for p in pauses if p['requestId']==r['requestId']][-1]
  fetch_changed.append({'paused':p,'send':s,'reply':r,'send_to_reply_node_mono_ms':r['nodeMonoMs']-s['nodeMonoMs']})
terminals=[r for r in e if r.get('method')=='Network.loadingFailed']
original=load('cdp-transport.json');results=[r for r in e if r['kind']=='native-result']
assert len(results)==len(sends)==len({r['commandId'] for r in results}) and set(sends)=={r['commandId'] for r in results}
summary.update({'original_transport_records':len(original['events']),'original_pending_command_ids':original['pendingCommandIds'],'all_native_sends_have_exactly_one_reply':True,'missing_network_requests':missing_rows,'changed_reply_context':{'count':len(changed),'by_method':dict(collections.Counter(r['method'] for r in changed)),'fetch_fulfill_records':fetch_changed},'loading_failed':{'count':len(terminals),'kinds':[{'canceled':c,'errorText':t,'type':y,'count':n} for (c,t,y),n in collections.Counter((r.get('canceled'),r.get('errorText'),r.get('type')) for r in terminals).items()]},'redirected_paused_request_count':sum(bool(p.get('redirectedRequestId')) for p in pauses),'historical_failed_identity_mapping':'NOT_PROVEN; this run reproduced no native error','remaining_discriminator':'The historical failed FetchID lacks URL/method/resourceType and a same-ID terminal/invalidation identity. New successful requests cannot supply those missing historical facts.'})
(ROOT/'analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
