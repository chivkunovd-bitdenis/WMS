# Review-only probe: real Printer/HTTP code; fake queue, never calls a physical printer.
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[4]
out=Path(__import__('tempfile').mkdtemp(prefix='wms625-review-rollback-'))
png='iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8//8/AwMDEwMDAwMDAwAkBgMB/DXemwAAAABJRU5ErkJggg=='
common='''
let directory=URL(fileURLWithPath:CommandLine.arguments[1])
let mode=CommandLine.arguments[2]
let key=CommandLine.arguments.count>3 ? CommandLine.arguments[3]:"key"
let body:[String:Any]=["idempotencyKey":key,"imageDataUrl":"data:image/png;base64,PNG","widthMm":58,"heightMm":40]
var submissions=0
'''.replace('PNG',png)
old=subprocess.check_output(['git','show','9a33b651c:tools/print-agent/wms_print_direct_macos.swift'],cwd=root,text=True).split('private struct HTTPRequest')[0]
old+=common+'''
do {
 let p=try Printer(directory:directory,submit:{_,_,_,_ in submissions+=1;return "old-1"},queue:{"old"})
 do { print("receipt=\\(try p.printJob(body))") } catch { print("error=\\(error)") }
 print("submissions=\\(submissions)")
} catch { print("init_error=\\(error)");exit(1) }
'''
new=subprocess.check_output(['git','show','20ab8fa83:tools/print-agent/wms_print_direct_macos.swift'],cwd=root,text=True).rsplit('\ndo {\n    if CommandLine.arguments',1)[0]
new+=common+'''
do {
 let p=try Printer(directory:directory,autoWork:false,submit:{_,_ in submissions+=1;return "new-1"},queue:{ if mode=="fail" { throw PrintError.beforeSubmit("no printer") };return "new"})
 _=try p.printJob(body)
 if mode=="retry" { _=try p.retry(key) }
 if mode != "saved" && mode != "inspect" { p.process(key) }
 let detail=try p.detail(key)!
 print("status=\\(detail["status"]!) receipt=\\(detail["receipt"] ?? "nil") submissions=\\(submissions)")
} catch { print("error=\\(error)");exit(1) }
'''
(out/'old.swift').write_text(old);(out/'new.swift').write_text(new)
subprocess.run(['clang','-c',str(root/'tools/print-agent/wms_cups_observe.c'),'-o',str(out/'cups.o')],check=True)
for name in ['old','new']:
 cmd=['/usr/bin/swiftc','-module-cache-path','/private/tmp/wms625-review-module-cache','-O',str(out/(name+'.swift')),'-o',str(out/name)]
 if name=='new':cmd+=['-Xlinker',str(out/'cups.o'),'-lcups']
 subprocess.run(cmd,check=True)
for case,steps in [('accepted',[('new','print'),('old','print'),('old','print','other'),('new','inspect')]),('saved',[('new','saved'),('old','print'),('new','inspect')]),('failed',[('new','fail'),('old','print'),('new','inspect'),('new','retry')])]:
 directory=out/case
 print('CASE',case,flush=True)
 for step in steps:
  command=[str(out/step[0]),str(directory),*step[1:]]
  r=subprocess.run(command,text=True,capture_output=True)
  print(step,r.returncode,r.stdout.strip(),r.stderr.strip(),flush=True)
