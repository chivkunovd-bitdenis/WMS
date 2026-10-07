"""Bounded local audit; changes are restored immediately, no printer/network I/O."""
from pathlib import Path
import json, subprocess

ROOT=Path('/Users/deniscivkunov/Projects/WMS/.worktrees/wms652-printing-audit-mutants')
OUT=Path(__file__).resolve().parent
BASE='d61805978b3e7878d1056c99b4e6e0823edf49a5'
results=[]
VITEST=['node','node_modules/vitest/vitest.mjs','run','--maxWorkers=1','--no-file-parallelism','--no-cache']

def run(name,args,cwd):
 p=subprocess.run(args,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
 (OUT/f'{name}.log').write_text(p.stdout)
 results.append({'name':name,'command':args,'exit_code':p.returncode})
 (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
 print(name,p.returncode,flush=True)
 return p.returncode

def mutate(path,old,new,name,args,cwd):
 p=ROOT/path
 original=p.read_bytes()
 try:
  text=original.decode(); assert text.count(old)==1,(path,text.count(old))
  p.write_text(text.replace(old,new))
  (OUT/f'{name}.diff').write_text(subprocess.check_output(['git','diff','--',path],cwd=ROOT,text=True))
  return run(name,args,cwd)
 finally:
  p.write_bytes(original)

frontend=ROOT/'frontend'
guards=VITEST+['src/guards/scan-print']
integration=VITEST+['src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx','-t','uses the visible standalone WB settings changed immediately before the physical scan']
assert run('baseline-guards',guards,frontend)==0
# A separate baseline integration attempt timed out at 90s locally; no mutation verdict is inferred.
assert mutate('frontend/src/screens/v2/fbsSequentialPacking.ts',
 'const printQr = current.preferences.printQr && live.printQr','const printQr = false',
 'mutant-no-qr',VITEST+['src/guards/scan-print/fbsSequentialPacking.test.ts','-t','preloads after barcode, waits for KIZ'],frontend)!=0
path=ROOT/'frontend/src/screens/v2/FbsPackingScanBar.tsx'
original=path.read_bytes()
try:
 old="void routePackingScan(controllers, raw, 'сборке', serialQueue)"
 assert original.decode().count(old)==1
 path.write_text(original.decode().replace(old,'void Promise.resolve()'))
 (OUT/'mutant-disconnected-input.diff').write_text(subprocess.check_output(['git','diff','--',str(path.relative_to(ROOT))],cwd=ROOT,text=True))
 assert run('mutant-disconnected-input-guards',guards,frontend)==0
 # Integration mutation not executed after its baseline timed out locally.
finally:
 path.write_bytes(original)
checker=['python3','scripts/ci/check_regression_guards.py','--base',BASE]
assert run('baseline-integrity',checker,ROOT)==0
assert mutate('frontend/src/guards/scan-print/fbsSequentialPacking.test.ts',
 "expect(deps.preload).toHaveBeenCalledTimes(1)","expect(true).toBe(true)",
 'mutant-weaken-guard',checker,ROOT)!=0
assert mutate('.github/workflows/ci.yml','npx vitest run src/guards','echo guard execution disabled',
 'mutant-disable-guard-run',checker,ROOT)==0
assert subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)==''
