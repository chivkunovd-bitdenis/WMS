"""Read-only broker metadata aggregation. Run inside existing wb-finance worker; never prints message args, IDs, URLs or env."""
import collections,datetime,json
import redis
from celery_app.celery import celery_app
r=redis.Redis.from_url(celery_app.conf.broker_url)
roots=collections.Counter();parents=collections.Counter();tasks=collections.Counter();retries=collections.Counter();redelivered=collections.Counter();etas=collections.Counter();origins=collections.Counter();ids=set();parent_ids=set();roots_set=set();parent_to_root={};eta_epochs=[];missing=collections.Counter();seen_delivery=set();rows=0
for tag,raw in r.hscan_iter('unacked',count=200):
 if tag in seen_delivery:continue
 seen_delivery.add(tag)
 msg=json.loads(raw)[0];h=msg.get('headers',{});props=msg.get('properties',{});rows+=1
 tasks[h.get('task','?')]+=1;retries[str(h.get('retries'))]+=1;redelivered[str(props.get('delivery_info',{}).get('redelivered',False))]+=1
 tid=h.get('id');root=h.get('root_id');parent=h.get('parent_id');eta=h.get('eta')
 if tid:ids.add(tid)
 if root:roots[root]+=1;roots_set.add(root)
 else:missing['root_id']+=1
 if parent:
  parents[parent]+=1;parent_ids.add(parent);parent_to_root[parent]=root
 else:missing['parent_id']+=1
 if eta:
  etas[eta]+=1;eta_epochs.append(datetime.datetime.fromisoformat(eta).timestamp())
 else:missing['eta']+=1
 origins[str(h.get('origin','')).split('@')[0]]+=1
out={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'rows':rows,'unique_task_ids':len(ids),'tasks':dict(tasks),'retries':dict(retries),'redelivered':dict(redelivered),'missing':dict(missing),'roots_distinct':len(roots),'root_sizes_desc':sorted(roots.values(),reverse=True),'parents_distinct':len(parents),'parent_children_histogram':dict(collections.Counter(parents.values())),'max_children_same_parent':max(parents.values(),default=0),'parents_also_current_tasks':len(parent_ids&ids),'roots_also_current_tasks':len(roots_set&ids),'eta_min_utc':datetime.datetime.fromtimestamp(min(eta_epochs),datetime.timezone.utc).isoformat() if eta_epochs else None,'eta_max_utc':datetime.datetime.fromtimestamp(max(eta_epochs),datetime.timezone.utc).isoformat() if eta_epochs else None,'origin_process_counts':dict(origins),'timestamp_headers_present_note':'Task protocol ETA inspected, no message arguments decoded or printed.'}
print(json.dumps(out,indent=2))
