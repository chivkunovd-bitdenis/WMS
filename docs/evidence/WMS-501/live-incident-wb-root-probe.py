"""Read six retained root results and aggregate parent delays; no IDs/arguments printed."""
import json,collections,datetime
import redis
from celery_app.celery import celery_app
r=redis.Redis.from_url(celery_app.conf.broker_url);roots=collections.Counter();parents=set();seen=set()
for tag,raw in r.hscan_iter('unacked',count=200):
 if tag in seen:continue
 seen.add(tag);h=json.loads(raw)[0].get('headers',{});roots[h['root_id']]+=1;parents.add(h['parent_id'])
backend=celery_app.backend;out=[]
for root,n in roots.most_common():
 raw=r.get(backend.get_key_for_task(root)); row={'current_descendants':n,'retained':raw is not None}
 if raw:
  d=json.loads(raw);res=d.get('result');row['status']=d.get('status');row['date_done']=d.get('date_done');row['children_count']=len(d.get('children') or [])
  if isinstance(res,dict):
   row['result_keys']=sorted(res)
   for k in ['ok','status','message','error','http_code','delay_sec','blocked_op','continue_with']:
    v=res.get(k)
    if k in ['ok','http_code','delay_sec'] and isinstance(v,(bool,int,float)):row[k]=v
    elif k in ['status','message','error'] and v in ['scheduled','running','idle','cooldown','complete','already_running','wb_retry_scheduled']:row['result_'+k]=v
    elif k=='blocked_op' and v in ['finance','funnel']:row[k]=v
 out.append(row)
delays=collections.Counter();datehours=collections.Counter();parentgroups=collections.Counter()
ids=list(parents)
for start in range(0,len(ids),100):
 for raw in r.mget([backend.get_key_for_task(tid) for tid in ids[start:start+100]]):
  if not raw:continue
  d=json.loads(raw);res=d.get('result') or {};res=res if isinstance(res,dict) else {}
  if isinstance(res.get('delay_sec'),(int,float)):delays[res['delay_sec']]+=1
  date=d.get('date_done')
  if date:datehours[datetime.datetime.fromisoformat(date).astimezone(datetime.timezone.utc).isoformat()[:13]]+=1
print(json.dumps({'roots':out,'parent_delay_histogram_top':delays.most_common(15),'parents_delay_at_least1hour':sum(n for delay,n in delays.items() if delay>=3600),'parents_delay_below1hour':sum(n for delay,n in delays.items() if delay<3600),'parent_date_hours_utc':dict(datehours)},indent=2))
