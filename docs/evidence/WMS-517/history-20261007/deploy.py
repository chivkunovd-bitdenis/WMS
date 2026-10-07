import subprocess,json,pathlib,datetime,hashlib,sys
BASE='4e7fb438aff4a82d8a332b1e1ae82b1d1aeb9240'
TARGET='d686e19678f7714f4d552ce281453327efbf3ade'
ROOT=pathlib.Path('/opt/wms')
OUT=pathlib.Path('/opt/wms-backups/wms517-history-20261007')
OUT.mkdir(parents=True,exist_ok=True)
def run(args):
 p=subprocess.run(args,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 print(p.stdout,flush=True)
 if p.returncode: raise RuntimeError(f'command failed: {args[0:3]}')
 return p.stdout.strip()
def inspect(service):
 return json.loads(subprocess.check_output(['docker','inspect',f'wms_prod-{service}-1'],text=True))[0]
receipt={'target':TARGET,'base':BASE,'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'mode':'owner-requested direct backend-only release; no CI or new agents; no migrations or business writes'}
try:
 assert run(['git','rev-parse','HEAD'])==BASE,'Concurrent release: stopped before modification'
 assert not run(['git','diff','--name-only']), 'Tracked worktree changes present'
 services=['api','celery_worker','celery_beat']
 prior={s:inspect(s) for s in services}
 receipt['previous_images']={s:v['Image'] for s,v in prior.items()}
 receipt['compose_files']={s:v['Config']['Labels']['com.docker.compose.project.config_files'].split(',') for s,v in prior.items()}
 (OUT/'before.json').write_text(json.dumps(receipt,indent=2))
 run(['git','-c','protocol.version=1','-c','http.version=HTTP/1.1','fetch','origin','codex/wms517-history-guide-20261007'])
 assert run(['git','rev-parse','FETCH_HEAD'])==TARGET
 context=OUT/'context';context.mkdir(exist_ok=True)
 files={'wb_sales_report.py':'backend/app/services/wb_sales_report.py','withdrawal_repository.py':'backend/app/db/withdrawal_repository.py'}
 hashes={}
 for name,path in files.items():
  blob=subprocess.check_output(['git','show',TARGET+':'+path],cwd=ROOT)
  (context/name).write_bytes(blob); hashes[path]=hashlib.sha256(blob).hexdigest()
 for s in services:
  old=prior[s]['Image']; base_tag='wms517-history-base-'+s+':20261007'
  run(['docker','tag',old,base_tag])
  dockerfile=context/('Dockerfile.'+s)
  dockerfile.write_text('FROM '+base_tag+'\nCOPY wb_sales_report.py /app/app/services/wb_sales_report.py\nCOPY withdrawal_repository.py /app/app/db/withdrawal_repository.py\nRUN python -m py_compile /app/app/services/wb_sales_report.py /app/app/db/withdrawal_repository.py\n')
  run(['docker','build','-f',str(dockerfile),'-t','wms_prod-'+s+':latest',str(context)])
 assert run(['git','rev-parse','HEAD'])==BASE,'Concurrent release during build'
 for s in services: assert inspect(s)['Image']==prior[s]['Image'],'Concurrent service change'
 run(['git','checkout','-b','codex/wms517-history-live-20261007',TARGET])
 for s in services:
  command=['docker','compose','-p','wms_prod']
  for f in receipt['compose_files'][s]:command+=['-f',f]
  run(command+['up','-d','--no-deps','--no-build',s])
 receipt['source_hashes']=hashes
 receipt['services']={s:{'image':inspect(s)['Image'],'running':inspect(s)['State']['Running']} for s in services}
 for s in services:
  for path,expected in hashes.items():
   actual=run(['docker','exec','wms_prod-'+s+'-1','sha256sum','/app/'+path.removeprefix('backend/')]).split()[0]
   assert actual==expected,(s,path)
 receipt['source_hashes_match_all_three']=True
 receipt['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 receipt['status']='deployed_runtime_sources_verified'
except BaseException as e:
 receipt['status']='failed';receipt['error']=str(e)
 raise
finally:(OUT/'receipt.json').write_text(json.dumps(receipt,indent=2))
