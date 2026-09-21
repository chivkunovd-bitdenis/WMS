"""Read retained Celery result metadata for current unacked parents; output aggregates only."""
import json,collections,datetime
import redis
from celery_app.celery import celery_app
r=redis.Redis.from_url(celery_app.conf.broker_url);parents=collections.Counter();roots=collections.Counter();current_ids=set()
for tag,raw in r.hscan_iter('unacked',count=200):
 h=json.loads(raw)[0].get('headers',{});parents[h.get('parent_id')]+=1;roots[h.get('root_id')]+=1;current_ids.add(h.get('id'))
backend=celery_app.backend
ids=list(parents);statuses=collections.Counter();msgs=collections.Counter();errors=collections.Counter();delays=[];dates=[];found=0;status_children=collections.Counter();expiries=[]
for start in range(0,len(ids),100):
 chunk=ids[start:start+100];keys=[backend.get_key_for_task(tid) for tid in chunk]
 vals=r.mget(keys)
 for tid,raw in zip(chunk,vals):
  if raw is None:statuses['not_retained']+=1;continue
  d=json.loads(raw);found+=1;status=d.get('status');statuses[str(status)]+=1
  result=d.get('result') or {};result=result if isinstance(result,dict) else {}
  msg=result.get('message');msgs[str(msg) if msg in ('cooldown','already_running','idle','complete') else 'other']+=1
  err=result.get('error');errors[str(err) if err in ('wb_retry_scheduled','user_not_found','no_wb_api_key',None) else 'other']+=1
  if isinstance(result.get('delay_sec'),(int,float)):delays.append(result['delay_sec'])
  if d.get('date_done'):dates.append(d['date_done'])
  status_children[f'{status}:children={parents[tid]}']+=1
out={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'current_task_ids':len(current_ids),'parents':len(parents),'retained_parents':found,'statuses':dict(statuses),'messages':dict(msgs),'errors':dict(errors),'delay_min_s':min(delays) if delays else None,'delay_max_s':max(delays) if delays else None,'date_done_min':min(dates) if dates else None,'date_done_max':max(dates) if dates else None,'status_children':dict(status_children)}
print(json.dumps(out,indent=2))
