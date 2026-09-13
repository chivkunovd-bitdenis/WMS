"""Only latest geometry and installer delta at frozen e85; no OS mutations."""
import json
from pathlib import Path
import subprocess
import sys
import types
from unittest.mock import patch
SHA="e85fd924cd737e843fdce9e8f21ff00215406447"
ROOT=Path(__file__).resolve().parents[4]
def source(path):
    return subprocess.check_output(["git","show",f"{SHA}:{path}"],cwd=ROOT,text=True)
def frozen(name,path):
    module=types.ModuleType(name); module.__file__=str(ROOT/path); sys.modules[name]=module
    exec(compile(source(path),f"{SHA}:{path}","exec"),module.__dict__)
    return module
frozen("wms_print_agent","tools/print-agent/wms_print_agent.py")
r=frozen("wms_print_runtime","tools/print-agent/wms_print_runtime.py")
results={"source_commit":SHA,"native_windows_or_printer_exercised":False}
class DC:
    caps={88:203,90:203,110:464,111:320,8:440,10:300,112:12,113:10}
    def CreatePrinterDC(self,queue): pass
    def GetDeviceCaps(self,cap): return self.caps[cap]
    def DeleteDC(self): pass
adapter=r.WindowsAdapter({"win32ui":types.SimpleNamespace(CreateDC=DC)})
for name,dimensions in [("smaller_printable_area",(58,40)),("missing_dimensions",(None,None))]:
    try:
        adapter.validate_layout("Synthetic",*dimensions)
        results[name]="unexpected pass"
    except ValueError as e:
        results[name]={"rejected_before_submit":True,"message":str(e)}
DC.caps.update({8:464,10:320,112:0,113:0})
adapter.validate_layout("Synthetic",58,40)
results["matching_full_page"]="pass"
installer=source("tools/print-agent/windows-installer.nsi")
results["installer_source_guards"]={"explicit_no_connection_branch":'have_connection no_connection' in installer,"uninstall_exit_code_guard":'  ExecWait \'"$INSTDIR\\wms-print-setup.exe" --uninstall\' $0\n  StrCmp $0 "0" +2\n  Abort' in installer}
print(json.dumps(results,ensure_ascii=False,indent=2))
