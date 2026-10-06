"""Existing printing-boundary contracts; all OS submission is mocked by those tests."""
from pathlib import Path
import json, subprocess, os, signal
ROOT=Path('/Users/deniscivkunov/Projects/WMS/.worktrees/wms652-printing-audit-mutants')
OUT=Path(__file__).resolve().parent
results=[]
def run(name,args,cwd):
 p=subprocess.Popen(args,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
 try: output,_=p.communicate(timeout=45)
 except subprocess.TimeoutExpired:
  os.killpg(p.pid,signal.SIGKILL); output,_=p.communicate(); output+='\nAUDIT TIMEOUT 45 seconds; not product RED\n'
 (OUT/f'{name}.log').write_text(output)
 results.append({'name':name,'command':args,'exit_code':p.returncode})
 (OUT/'boundary-results.json').write_text(json.dumps(results,indent=2)+'\n')
 print(name,p.returncode,flush=True)
 return p.returncode
vitest=['node','node_modules/vitest/vitest.mjs','run','--maxWorkers=1','--no-file-parallelism','--no-cache','src/utils/printPreparedQr.test.ts']
assert run('baseline-print-receipt',vitest,ROOT/'frontend')==0
path=ROOT/'frontend/src/utils/printDirectQr.ts'; original=path.read_bytes()
try:
 old="if (!response.ok || !result.receipt) throw new Error(result.error || 'Принтер не подтвердил приём этикетки')"
 assert original.decode().count(old)==1
 path.write_text(original.decode().replace(old,'void result // mutant: treat absent OS receipt as success'))
 (OUT/'mutant-accept-no-receipt.diff').write_text(subprocess.check_output(['git','diff','--',str(path.relative_to(ROOT))],cwd=ROOT,text=True))
 assert run('mutant-accept-no-receipt',vitest,ROOT/'frontend')!=0
finally: path.write_bytes(original)
py=['python3','-m','unittest','test_wms_print_direct.DirectPrintTest.test_receipt_survives_restart_without_duplicate','test_wms_print_direct.DirectPrintTest.test_uncertain_submission_not_repeated','test_wms_print_direct.DirectPrintTest.test_changed_content_rejected','-v']
assert run('baseline-native-recovery',py,ROOT/'tools/print-agent')==0
path=ROOT/'tools/print-agent/wms_print_direct.py'; original=path.read_bytes()
try:
 old='            if old:\n                if old[0] != digest:'
 new='            if old and old[1] is None:\n                db.execute("DELETE FROM jobs WHERE id=?", (key,))\n                old = None  # mutant: blindly resubmit unknown outcome\n            if old:\n                if old[0] != digest:'
 assert original.decode().count(old)==1
 path.write_text(original.decode().replace(old,new))
 (OUT/'mutant-resubmit-unknown.diff').write_text(subprocess.check_output(['git','diff','--',str(path.relative_to(ROOT))],cwd=ROOT,text=True))
 assert run('mutant-resubmit-unknown',py,ROOT/'tools/print-agent')!=0
finally: path.write_bytes(original)
assert subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)==''
