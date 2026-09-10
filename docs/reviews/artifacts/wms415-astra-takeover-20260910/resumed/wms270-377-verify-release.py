#!/usr/bin/env python3
"""Exact-source runtime and bounded two-origin auth/network proof. No raw logs."""
import atexit,hashlib,json,socket,subprocess,sys,uuid
from pathlib import Path
root=Path(__file__).resolve().parents[5]
sha=sys.argv[1]
assert len(sha)==40 and all(c in "0123456789abcdef" for c in sha)

def ssh(code):
 return subprocess.check_output(["ssh","-o","BatchMode=yes","-o","ConnectTimeout=10","root@194.87.96.144","python3","-"],input=code.encode(),timeout=60).decode()
remote=r'''import subprocess,json

def run(*a): return subprocess.check_output(a,text=True).strip()
r={"server_sha":run("git","-C","/opt/wms","rev-parse","HEAD"),"api_hashes":{},"containers":{}}
for f in ["app/api/auth.py","app/services/auth_service.py","app/services/login_rate_limit.py","app/api/products.py","app/services/seller_wb_catalog_service.py"]:
 r["api_hashes"]["backend/"+f]=run("docker","exec","wms_prod-api-1","sha256sum","/app/"+f).split()[0]
r["caddy_sha256"]=run("docker","exec","wms_prod-web-1","sha256sum","/etc/caddy/Caddyfile").split()[0]
r["forwarded_allow_ips"]=run("docker","exec","wms_prod-api-1","python","-c","import os;print(os.environ.get('FORWARDED_ALLOW_IPS',''))")
r["limiter_config"]=json.loads(run("docker","exec","wms_prod-api-1","python","-c","import json;from app.services.login_rate_limit import get_config;print(json.dumps(get_config()))"))
r["web_ports"]=json.loads(run("docker","inspect","wms_prod-web-1","--format","{{json .NetworkSettings.Ports}}"))
r["legacy_running"]=run("docker","ps","-q","--filter","label=com.docker.compose.project=wms_prod","--filter","label=com.docker.compose.service=web_seller")
r["schema"]=run("docker","exec","wms_prod-db-1","sh","-c",'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "select version_num from alembic_version"')
for n in ["api","web","celery_worker","celery_beat"]:
 r["containers"][n]=run("docker","inspect","wms_prod-"+n+"-1","--format","{{.Image}}|{{.State.StartedAt}}|{{.State.Running}}")
print(json.dumps(r))
'''
r={"expected_sha":sha,"verified":False}
def save_partial():
 name="wms270-377-production-verification-20260910.json" if r["verified"] else "wms270-377-incomplete-verification-20260910.json"
 Path(__file__).with_name(name).write_text(json.dumps(r,indent=2)+"\n")
atexit.register(save_partial)
r.update(json.loads(ssh(remote)));assert r["server_sha"]==sha
for f,h in r["api_hashes"].items():
 assert hashlib.sha256(subprocess.check_output(["git","show",sha+":"+f],cwd=root)).hexdigest()==h,f
assert hashlib.sha256(subprocess.check_output(["git","show",sha+":deploy/Caddyfile.http"],cwd=root)).hexdigest()==r["caddy_sha256"]
assert r["forwarded_allow_ips"]=="172.21.0.0/16"
assert r["web_ports"]["80/tcp"]==[{"HostIp":"172.18.0.1","HostPort":"8088"}]
assert not r["legacy_running"] and r["schema"]=="20260908_0257"
r["external_ports"]={}
for port in [8088,15174]:
 try:
  with socket.create_connection(("194.87.96.144",port),timeout=5):
   r["external_ports"][str(port)]="OPEN"
 except OSError as e:r["external_ports"][str(port)]=type(e).__name__
assert "OPEN" not in r["external_ports"].values()
r["https"]={}
for path in ["/","/seller/","/api/health","/api/openapi.json"]:
 code=subprocess.check_output(["curl","--fail","--silent","--show-error","--max-time","20","--output","/dev/null","--write-out","%{http_code}","https://wms.sellerfocus.pro"+path],text=True)
 assert code=="200",(path,code);r["https"][path]=int(code)
openapi=json.loads(subprocess.check_output(["curl","--fail","--silent","--show-error","--max-time","20","https://wms.sellerfocus.pro/api/openapi.json"]))
param=next(p for p in openapi["paths"]["/products/ff-catalog-page"]["get"]["parameters"] if p["name"]=="stock_publication")
assert param["schema"]["anyOf"][0]["enum"]==["wb","ozon","both","any","none"]
r["stock_publication_preserved"]=True
prior=json.loads(Path(__file__).with_name("wms418-production-verification-20260910.json").read_text())
r["preserved_catalog_assets"]={}
for path,expected in prior["web_hashes"].items():
 data=subprocess.check_output(["curl","--fail","--silent","--show-error","--max-time","20","https://wms.sellerfocus.pro"+path])
 assert hashlib.sha256(data).hexdigest()==expected,path
 r["preserved_catalog_assets"][path]=expected
# These requests use a fresh random nonexistent example.com identity, never a customer login.
# Saturate only the server-origin bucket; the Mac makes two attempts, below the default limit.
assert r["limiter_config"]==[5,60],"Unexpected limits: do not run a different-volume live probe"
email="wms270-probe-"+uuid.uuid4().hex+"@example.com"
probe=r'''import json,subprocess
payload=json.dumps({"email":EMAIL,"password":"Synthetic-invalid-probe-270!"})
def attempt(xff=None):
 a=["curl","--silent","--show-error","--max-time","15","--write-out","\n%{http_code}","-H","Content-Type: application/json","--data-binary",payload]
 if xff:a += ["-H","X-Forwarded-For: "+xff]
 body,code=subprocess.check_output(a+["https://wms.sellerfocus.pro/api/auth/login"]).rsplit(b"\n",1)
 status=int(code);data=json.loads(body);detail=data.get("detail")
 return {"status":status,"detail":detail if detail in ("invalid_credentials","too_many_attempts") else "unexpected_response"}
'''.replace("EMAIL",repr(email))
server=probe+'\nr=[attempt() for _ in range(6)]\nr.append(attempt("198.51.100.77"))\nprint(json.dumps(r))\n'
r["server_origin"]=json.loads(ssh(server))
assert [v["status"] for v in r["server_origin"]]==[401]*5+[429,429]
local=probe+'\nprint(json.dumps([attempt(),attempt("194.87.96.144")]))\n'
r["mac_origin"]=json.loads(subprocess.check_output([sys.executable,"-c",local],text=True,timeout=40))
assert [v["status"] for v in r["mac_origin"]]==[401,401]
r["verified"]=True
Path(__file__).with_name("wms270-377-production-verification-20260910.json").write_text(json.dumps(r,indent=2)+"\n")
print(json.dumps(r,indent=2))
