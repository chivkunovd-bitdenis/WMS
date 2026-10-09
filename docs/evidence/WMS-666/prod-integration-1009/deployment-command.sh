set -e
scp -i ~/.ssh/wms_github_deploy docs/evidence/WMS-666/prod-integration-1009/final-ci-verification.json root@194.87.96.144:/opt/wms/.deploy-backups/wms666-packing/final-ci-fbd5f228b36b.json
ssh -i ~/.ssh/wms_github_deploy root@194.87.96.144 'bash -s' <<'REMOTE'
set -euo pipefail
cd /opt/wms
release=fbd5f228b36be5894b3981bc5bbf4135ea303e1b
baseline=9971abed35e003abd5be8d2bc3e0032f3ca9f5c7
root=/opt/wms/.deploy-backups/wms666-packing
rollback="$root/rollback-fbd5f228b36b.sh"
compose=(docker compose --env-file /opt/wms/.env -p wms_prod -f /opt/wms/docker-compose.prod.yml -f /opt/wms/docker-compose.wms-host-8088.yml)
[[ "$(git rev-parse HEAD)" == "$baseline" ]]
git diff --quiet
source "$root/$release.state"
[[ "$status" == prepared && "$before_source_sha" == "$baseline" ]]
for service in api celery_worker celery_beat web; do
 old_var="${service}_before"
 [[ "$(docker inspect --format '{{.Image}}' "$("${compose[@]}" ps -q "$service")")" == "${!old_var}" ]]
done
db_before="$("${compose[@]}" ps -q db)"
redis_before="$("${compose[@]}" ps -q redis)"
python3 scripts/deploy/verify-wms-host-network.py "$db_before"
python3 - "$release" "$root" <<'PY'
import json,subprocess,sys
from pathlib import Path
sha,root=sys.argv[1:]
ci=json.loads(Path(root,'final-ci-fbd5f228b36b.json').read_text())
assert ci['release_sha']==sha and ci['production_baseline']=='9971abed35e003abd5be8d2bc3e0032f3ca9f5c7' and ci['ci_run']==37867596525 and ci['all_mandatory_cases_pass']
proof=json.loads(Path(root,'built-source-'+sha+'.json').read_text())
assert proof['release_sha']==sha and proof['source_files']==352
for service,details in proof['services'].items():
 actual=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',f'wms666-packing-candidate:{sha}-{service}'],text=True).strip()
 assert actual==details['image_id'],(service,'candidate image changed')
PY
git checkout -B codex/wms666-prod-integration-1009 "$release" >/dev/null
armed=false
recover() {
 exit_status=$?
 trap - ERR
 if [[ "$armed" == true ]]; then
   "$rollback" rollback "$release" || printf '%s\n' 'Automatic rollback needs a readback and idempotent retry'
 else
   for service in api celery_worker celery_beat web; do old_var="${service}_before"; docker image tag "${!old_var}" "wms_prod-${service}:latest"; done
   git checkout fix/wms709-fbs-pick-done-places >/dev/null
 fi
 exit "$exit_status"
}
trap recover ERR
for service in api celery_worker celery_beat web; do docker image tag "wms666-packing-candidate:$release-$service" "wms_prod-$service:latest"; done
"$rollback" arm "$release"
armed=true
"${compose[@]}" up -d --no-deps --no-build api celery_worker celery_beat web
healthy=false
for attempt in {1..30}; do
 if curl --fail --silent --max-time 5 https://wms.sellerfocus.pro/api/health >"$root/health-$release.json"; then healthy=true; break; fi
 sleep 2
done
[[ "$healthy" == true ]]
[[ "$("${compose[@]}" ps -q db)" == "$db_before" && "$("${compose[@]}" ps -q redis)" == "$redis_before" ]]
python3 - "$release" "$root" "$db_before" "$redis_before" <<'PY'
import hashlib,json,re,subprocess,sys,urllib.request,datetime
from pathlib import Path
sha,root,db_before,redis_before=sys.argv[1:]
compose=['docker','compose','--env-file','/opt/wms/.env','-p','wms_prod','-f','/opt/wms/docker-compose.prod.yml','-f','/opt/wms/docker-compose.wms-host-8088.yml']
proof=json.loads(Path(root,'built-source-'+sha+'.json').read_text())
containers={}
for service,details in proof['services'].items():
 cid=subprocess.check_output(compose+['ps','-q',service],text=True).strip()
 info=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
 assert info['Image']==details['image_id'] and info['State']['Running'],service
 containers[service]={'id':cid,'image_id':info['Image'],'running':True}
paths=subprocess.check_output(['git','ls-tree','-r','--name-only',sha,'backend/app'],text=True).splitlines()
expected={p.removeprefix('backend/'):hashlib.sha256(subprocess.check_output(['git','show',sha+':'+p])).hexdigest() for p in paths}
code='import hashlib,json; from pathlib import Path; print(json.dumps({p:hashlib.sha256(Path("/app",p).read_bytes()).hexdigest() for p in '+repr(list(expected))+'}))'
for service in ('api','celery_worker','celery_beat'):
 actual=json.loads(subprocess.check_output(['docker','exec',containers[service]['id'],'python','-c',code]))
 assert actual==expected,service
 containers[service]['source_files_verified']=len(expected)
base='https://wms.sellerfocus.pro'
def get(path):
 return urllib.request.urlopen(urllib.request.Request(base+path,headers={'Cache-Control':'no-cache'}),timeout=12).read()
index=get('/?wms-release='+sha)
image_index=subprocess.check_output(['docker','exec',containers['web']['id'],'cat','/srv/index.html'])
assert index==image_index,'public index differs from installed image'
manifest=json.loads(Path(root,'assets-'+sha,'manifest.json').read_text())
asset_hashes={**manifest['previous'],**manifest['candidate']}
for name,digest in asset_hashes.items():
 assert hashlib.sha256(get('/'+name+'?wms-release='+sha)).hexdigest()==digest,name
assert json.loads(get('/api/health'))['status']=='ok'
db_code="""import asyncio,json
from sqlalchemy import text
from app.db.session import engine
from app.core.settings import settings
async def check():
 async with engine.connect() as c: assert (await c.execute(text('SELECT 1'))).scalar_one()==1
 await engine.dispose()
 print(json.dumps({'database_read':True,'app_env':settings.app_env,'public_registration':settings.allow_public_registration}))
asyncio.run(check())"""
try:
 db_result=json.loads(subprocess.check_output(['docker','exec',containers['api']['id'],'python','-c',db_code],stderr=subprocess.PIPE))
except subprocess.CalledProcessError:
 raise AssertionError('Read-only production database/config check did not complete') from None
assert db_result['database_read'] and db_result['app_env']=='production' and db_result['public_registration'] is False
ping_code="import json; from app.celery_app import celery_app; print(json.dumps(celery_app.control.ping(timeout=5.0)))"
try:
 replies=json.loads(subprocess.check_output(['docker','exec',containers['celery_worker']['id'],'python','-c',ping_code],stderr=subprocess.PIPE))
except subprocess.CalledProcessError:
 raise AssertionError('Production worker did not complete its control ping') from None
assert any(reply.get('ok')=='pong' for row in replies for reply in row.values()),'worker did not answer'
receipt={'release_sha':sha,'before_source_sha':'9971abed35e003abd5be8d2bc3e0032f3ca9f5c7','verified_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'containers':containers,'database_container_unchanged':db_before,'redis_container_unchanged':redis_before,'public_index_sha256':hashlib.sha256(index).hexdigest(),'public_asset_hashes_verified':len(asset_hashes),'previous_assets_retained':len(manifest['previous']),'health':'ok','database_read_only_check':db_result,'worker_ping':'pong','migrations_run':False,'stock_or_order_test_mutations':False,'ci_run':37867596525,'rollback_script':str(Path(root,'rollback-fbd5f228b36b.sh'))}
Path(root,'deployed-'+sha+'.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
PY
"$rollback" seal "$release"
trap - ERR
printf '%s\n' 'Production release verified and rollback sealed'
REMOTE
