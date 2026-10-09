#!/usr/bin/env python3
"""Run real rollback shell with private fake Docker/Git/HTTP boundaries; no host access."""
import json, os, subprocess, tempfile
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[4]/"scripts/deploy/rollback-wms666-packing.sh"
RELEASE="a"*40
SERVICES=["api","celery_worker","celery_beat","web"]
BEFORE={s:"sha256:"+str(i+1)*64 for i,s in enumerate(SERVICES)}
NEW={s:"sha256:"+str(i+5)*64 for i,s in enumerate(SERVICES)}
FAKE=r'''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
p=Path(os.environ["FIXTURE_STATE"]); d=json.loads(p.read_text()); a=sys.argv[1:]; name=Path(sys.argv[0]).name
if name=="git": print(os.environ["FIXTURE_HEAD"])
elif name=="curl":
 if a[-1].endswith("/api/health") and d.get("fail_health"):
  d["fail_health"]=False;p.write_text(json.dumps(d));sys.exit(22)
 print("fixture-before-page")
elif name=="sleep": pass
elif name=="docker":
 if a[0]=="compose":
  if "ps" in a: print(a[-1])
  elif "up" in a:
   for i,s in enumerate(["api","celery_worker","celery_beat","web"]):
    d["current"][s]=d["tags"]["wms_prod-"+s+":latest"]
    if d.get("fail_up") and i==0:
     d["fail_up"]=False;p.write_text(json.dumps(d));sys.exit(1)
 elif a[0]=="inspect": print(d["current"][a[-1]])
 elif a[:2]==["image","inspect"]: print(d["tags"][a[-1]])
 elif a[:2]==["image","tag"]:
  d["tags"][a[-1]]=a[-2];d["tag_calls"]+=1
 else: raise SystemExit("unknown fake Docker command "+repr(a))
 p.write_text(json.dumps(d))
'''
with tempfile.TemporaryDirectory(prefix="wms666-rollback-fixture-") as td:
 root=Path(td); bins=root/"bin";bins.mkdir(); repo=root/"repo";repo.mkdir(); state=root/"docker.json"
 for name in ["git","curl","docker","sleep"]:
  path=bins/name;path.write_text(FAKE);path.chmod(0o755)
 env=dict(os.environ,PATH=str(bins)+os.pathsep+os.environ["PATH"],WMS_REPO_DIR=str(repo),WMS_ROLLBACK_STATE_DIR=str(repo/"records"),FIXTURE_STATE=str(state),FIXTURE_HEAD="b"*40)
 def get():return json.loads(state.read_text())
 def put(d):state.write_text(json.dumps(d))
 def setup():
  import shutil
  shutil.rmtree(repo/"records",ignore_errors=True)
  put(dict(current=BEFORE.copy(),tags={"wms_prod-"+s+":latest":BEFORE[s] for s in SERVICES},tag_calls=0))
  env["FIXTURE_HEAD"]="b"*40
 def call(mode,ok=True):
  r=subprocess.run(["bash",str(SCRIPT),mode,RELEASE],env=env,capture_output=True,text=True)
  assert (r.returncode==0)==ok,(mode,r.returncode,r.stdout,r.stderr)
 def prepare_arm():
  call("prepare");d=get();d["tags"].update({"wms_prod-"+s+":latest":NEW[s] for s in SERVICES});put(d)
  env["FIXTURE_HEAD"]=RELEASE;call("arm")
 def install_seal():d=get();d["current"]=NEW.copy();put(d);call("seal")
 setup();prepare_arm();install_seal();call("rollback");call("rollback");assert get()["current"]==BEFORE
 print("PASS normal rollback and idempotent repeat")
 setup();prepare_arm();d=get();d["current"]["api"]=NEW["api"];put(d);call("rollback");assert get()["current"]==BEFORE
 print("PASS partial deployment before seal")
 setup();prepare_arm();install_seal();d=get();d["fail_up"]=True;put(d);call("rollback",False);call("rollback");assert get()["current"]==BEFORE
 print("PASS retry after partial compose failure")
 setup();prepare_arm();install_seal();d=get();d["fail_health"]=True;put(d);call("rollback",False);call("rollback");assert get()["current"]==BEFORE
 print("PASS retry after transient health failure")
 setup();prepare_arm();install_seal();d=get();d["current"]["web"]="sha256:"+"f"*64;put(d);before_tags=d["tags"].copy();calls=d["tag_calls"];call("rollback",False)
 assert get()["tags"]==before_tags and get()["tag_calls"]==calls
 print("PASS foreign later image rejected before any tag mutation")
