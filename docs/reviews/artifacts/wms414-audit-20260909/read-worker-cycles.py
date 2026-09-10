import subprocess,re,json,datetime
r=subprocess.run(['docker','logs','--since','30m','--timestamps','wms_prod-celery_worker-1'],capture_output=True,text=True)
patterns={
'orders':r'fbs autopoll orders done: sellers=\d+ upserted=\d+ created=\d+ statuses=\d+ stocks_bindings=\d+ stock_errors=\d+ errors=\d+',
'statuses':r'fbs autopoll statuses done: sellers=\d+ statuses=\d+ errors=\d+'
}
results=[]
for line in (r.stdout+'\n'+r.stderr).splitlines():
 for key,pattern in patterns.items():
  m=re.search(pattern,line)
  if m:results.append({'kind':key,'at':line.split(' ',1)[0],'counts':m.group(0)})
print(json.dumps({'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'window':'30m','exit_code':r.returncode,'cycles':results},indent=2))
