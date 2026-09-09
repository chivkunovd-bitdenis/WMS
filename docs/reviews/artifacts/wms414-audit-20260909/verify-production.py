"""Read-only artifact verification. Run post-deploy mode only after root's READY."""
import argparse
import datetime
import hashlib
import json
import pathlib
import shlex
import subprocess

parser = argparse.ArgumentParser()
mode = parser.add_mutually_exclusive_group(required=True)
mode.add_argument("--baseline", action="store_true")
mode.add_argument("--expected-production-sha")
args = parser.parse_args()
directory = pathlib.Path(__file__).resolve().parent
services = ["wms_prod-api-1", "wms_prod-celery_worker-1", "wms_prod-celery_beat-1"]
remote = '''import subprocess,json,datetime
run=lambda command: subprocess.check_output(command,text=True)
result={"checked_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"production_sha":run(["git","-c","safe.directory=/opt/wms","-C","/opt/wms","rev-parse","HEAD"]).strip(),"containers":{}}
for name in ["wms_prod-api-1","wms_prod-celery_worker-1","wms_prod-celery_beat-1","wms_prod-web-1"]:
 result["containers"][name]={"image":json.loads(run(["docker","inspect","--format","{{json .Image}}",name])),"state":run(["docker","inspect","--format","running={{.State.Running}} restarting={{.State.Restarting}}",name]).strip()}
raw=run(["docker","exec","wms_prod-web-1","sh","-c","cd /srv && find . -type f -exec sha256sum {} \\;"])
result["frontend_files"]={line.split("  ",1)[1].removeprefix("./"):line.split("  ",1)[0] for line in raw.splitlines()}
'''
if not args.baseline:
    remote += '''
result["python_files"]={}
code='import pathlib,hashlib,json;root=pathlib.Path("/app");print(json.dumps({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for d in ("app","alembic") for p in sorted((root/d).rglob("*.py"))}))'
for name in ["wms_prod-api-1","wms_prod-celery_worker-1","wms_prod-celery_beat-1"]:
 result["python_files"][name]=json.loads(run(["docker","exec",name,"python","-c",code]))
'''
remote += '\nprint(json.dumps(result))\n'
raw = subprocess.check_output([
    "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "root@sellerfocus.pro",
    "python3 -c " + shlex.quote(remote),
], text=True)
runtime = json.loads(raw)
if args.baseline:
    (directory / "baseline.json").write_text(json.dumps(runtime, indent=2) + "\n")
    print(json.dumps({"baseline_sha": runtime["production_sha"], "frontend_count": len(runtime["frontend_files"]), "containers": runtime["containers"]}, indent=2))
    raise SystemExit(0)

baseline = json.loads((directory / "baseline.json").read_text())
expected = json.loads((directory / "expected-python.json").read_text())
def compare(before, after):
    return {"expected_count": len(before), "runtime_count": len(after), "missing": sorted(set(before) - set(after)), "extra": sorted(set(after) - set(before)), "mismatch": [path for path in before if path in after and before[path] != after[path]]}

result = {
    "verified_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "production_sha": runtime["production_sha"],
    "expected_production_sha": args.expected_production_sha,
    "python_source_sha": expected["source_sha"],
    "baseline_frontend_sha": baseline["production_sha"],
    "python": {name: compare(expected["files"], runtime["python_files"][name]) for name in services},
    "frontend": compare(baseline["frontend_files"], runtime["frontend_files"]),
    "containers": runtime["containers"],
}
public = {}
for path in ("/api/health", "/"):
    answer = subprocess.check_output(["curl", "--silent", "--show-error", "--max-time", "30", "--write-out", "\n%{http_code}", "https://wms.sellerfocus.pro" + path])
    body, status = answer.rsplit(b"\n", 1)
    public[path] = {"status": int(status), "sha256": hashlib.sha256(body).hexdigest()}
    if path == "/api/health":
        public[path]["body"] = body.decode()
    else:
        public[path]["runtime_hash_match"] = hashlib.sha256(body).hexdigest() == runtime["frontend_files"]["index.html"]
result["public"] = public
try:
    health_ok = json.loads(public["/api/health"]["body"]) == {"status": "ok"}
except ValueError:
    health_ok = False
result["pass"] = (
    runtime["production_sha"] == args.expected_production_sha
    and all(not any(check[key] for key in ("missing", "extra", "mismatch")) for check in [*result["python"].values(), result["frontend"]])
    and all(container["state"] == "running=true restarting=false" for container in runtime["containers"].values())
    and all(response["status"] == 200 for response in public.values())
    and public["/"]["runtime_hash_match"]
    and health_ok
)
(directory / "runtime.json").write_text(json.dumps(runtime, indent=2) + "\n")
(directory / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
raise SystemExit(0 if result["pass"] else 1)
