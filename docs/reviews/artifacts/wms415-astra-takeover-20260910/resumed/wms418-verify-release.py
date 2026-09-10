#!/usr/bin/env python3
"""Read-only proof of the exact WMS-418 API/web deployment; no credentials output."""
import hashlib, json, subprocess, sys, urllib.request
from pathlib import Path

sha = sys.argv[1]
assert len(sha) == 40 and all(c in "0123456789abcdef" for c in sha)
root = Path(__file__).resolve().parents[5]
app_files = ["backend/app/api/products.py", "backend/app/services/seller_wb_catalog_service.py"]
remote = r'''import hashlib,json,subprocess
from pathlib import Path

def run(*args):
 return subprocess.check_output(args,text=True).strip()
r={"server_sha":run("git","-C","/opt/wms","rev-parse","HEAD"),"api_files":{},"containers":{}}
for f in ["app/api/products.py","app/services/seller_wb_catalog_service.py"]:
 code="import hashlib;from pathlib import Path;print(hashlib.sha256(Path("+repr("/app/"+f)+").read_bytes()).hexdigest())"
 r["api_files"]["backend/"+f]=run("docker","exec","wms_prod-api-1","python","-c",code)
for name in ["api","web","celery_worker","celery_beat"]:
 data=json.loads(run("docker","inspect","wms_prod-"+name+"-1","--format",'{{json .State}}'))
 r["containers"][name]={"image":run("docker","inspect","wms_prod-"+name+"-1","--format","{{.Image}}"),"started":data["StartedAt"],"running":data["Running"]}
r["web_hashes"]={}
for line in run("docker","exec","wms_prod-web-1","sh","-c","sha256sum /srv/index.html /srv/assets/FfProductsCatalogScreen-*.js").splitlines():
 h,f=line.split();r["web_hashes"][f.removeprefix("/srv")]=h
r["schema"]=run("docker","exec","wms_prod-db-1","sh","-c",'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "select version_num from alembic_version"')
print(json.dumps(r))
'''
r=json.loads(subprocess.check_output(["ssh","-o","BatchMode=yes","-o","ConnectTimeout=10","root@194.87.96.144","python3","-"],input=remote.encode()))
assert r["server_sha"]==sha,r["server_sha"]
r["expected_sha"]=sha
for f in app_files:
 expected=hashlib.sha256(subprocess.check_output(["git","show",sha+":"+f],cwd=root)).hexdigest()
 assert r["api_files"][f]==expected,f
r["api_hashes_match_git"]=True
r["frontend_source_sha256"]=hashlib.sha256(subprocess.check_output(["git","show",sha+":frontend/src/screens/v2/FfProductsCatalogScreen.tsx"],cwd=root)).hexdigest()
r["public"]={}
base="https://wms.sellerfocus.pro"
def public_get(path):
 # Use system curl's configured trust store; keep certificate validation enabled.
 return subprocess.check_output(["curl","--fail","--silent","--show-error","--max-time","30",base+path])
for path in ["/","/seller/","/api/health","/api/openapi.json"]:
 data=public_get(path);r["public"][path]={"status":200,"sha256":hashlib.sha256(data).hexdigest()}
 if path=="/api/openapi.json":
  params=json.loads(data)["paths"]["/products/ff-catalog-page"]["get"]["parameters"]
  r["stock_publication_parameter"]=next(p for p in params if p["name"]=="stock_publication")
for path,expected in r["web_hashes"].items():
 actual=hashlib.sha256(public_get(path)).hexdigest()
 assert actual==expected,path
 r["public"][path]={"status":200,"sha256":actual}
assert r["schema"]=="20260908_0257",r["schema"]
assert all(c["running"] for c in r["containers"].values())
r["verified"]=True
output=Path(__file__).with_name("wms418-production-verification-20260910.json")
output.write_text(json.dumps(r,indent=2)+"\n")
print(json.dumps(r,indent=2))
