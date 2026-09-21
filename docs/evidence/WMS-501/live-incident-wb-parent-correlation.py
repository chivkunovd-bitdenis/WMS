"""Run read-only on host: broker task IDs stay in process memory, output only aggregates."""
import subprocess,json,collections,re,time
inner='''import redis,json\nfrom celery_app.celery import celery_app\nr=redis.Redis.from_url(celery_app.conf.broker_url)\nrows={}\nfor tag,raw in r.hscan_iter('unacked',count=200):\n h=json.loads(raw)[0].get('headers',{})\n rows[h.get('id')]=[h.get('parent_id'),h.get('root_id'),h.get('eta')]\nprint(json.dumps(rows))\n'''
p=subprocess.run(['docker','exec','-i','wb-finance-celery_worker-1','python','-'],input=inner,text=True,capture_output=True,check=True)
rows=json.loads(p.stdout);children=collections.Counter(v[0] for v in rows.values());parents=set(children);roots=set(v[1] for v in rows.values());suc=collections.Counter();rec=collections.Counter();messages=collections.Counter();delays=collections.Counter();parent_first={};parent_last={};root_events=collections.Counter();hourly=collections.Counter();matched_ids=set();root_info={};matched_seconds=collections.Counter();count=0;first=None;last=None;truncated=False
p=subprocess.Popen(['docker','logs','--timestamps','--since','2026-09-21T10:05:00Z','--until','2026-09-21T18:43:30Z','wb-finance-celery_worker-1'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
started=time.monotonic()
for line in p.stdout:
 count+=1;ts=line.split(' ',1)[0];first=first or ts;last=ts
 if time.monotonic()-started>35:truncated=True;p.terminate();break
 m=re.search(r'Task ([\w.]+)\[([^]]+)\] (received|succeeded|failed)',line)
 if not m:continue
 task,tid,event=m.groups()
 if tid in parents:
  if event=='received':rec[tid]+=1
  if event=='succeeded':
   suc[tid]+=1;matched_ids.add(tid);parent_first.setdefault(tid,ts);parent_last[tid]=ts;hourly[ts[:13]]+=1
   message=re.search(r"'message': '(cooldown|already_running|idle|complete)'",line)
   messages[message.group(1) if message else 'other']+=1
   delay=re.search(r"'delay_sec': (\d+)",line)
   if delay:delays[int(delay.group(1))]+=1
 if tid in roots:
  root_events[task+':'+event]+=1
  info=root_info.setdefault(tid,{'task':task,'received':[],'succeeded':[]})
  info[event if event in ('received','succeeded') else 'succeeded'].append(ts)
p.wait()
compare=collections.Counter()
for pid,n in children.items():compare[f'children={n},successes={suc[pid]}']+=1
out={'rows_current':len(rows),'parents_current':len(parents),'log_lines':count,'log_first':first,'log_last':last,'bounded_at35seconds':truncated,'parents_found_succeeded':len(suc),'total_parent_successes':sum(suc.values()),'parent_result_messages':dict(messages),'parent_delay_min_s':min(delays) if delays else None,'parent_delay_max_s':max(delays) if delays else None,'delay_histogram_top':delays.most_common(10),'childcount_vs_parent_successcount':dict(compare),'parent_successes_per_hour':dict(hourly),'root_task_events':dict(root_events),'root_event_details_without_ids':list(root_info.values())}
print(json.dumps(out,indent=2))
