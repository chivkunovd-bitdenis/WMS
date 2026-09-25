"""Frozen delta probes; only temporary state and mocked OS boundaries are used."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
from unittest.mock import patch
import xml.etree.ElementTree as ET

SHA = "de8deca9fffbfbff7ae48c71410beb1680cc284e"
ROOT = Path(__file__).resolve().parents[4]
def frozen(name, relative):
    source = subprocess.check_output(["git", "show", f"{SHA}:{relative}"], cwd=ROOT, text=True)
    module = types.ModuleType(name)
    module.__file__ = str(ROOT / relative)
    sys.modules[name] = module
    exec(compile(source, f"{SHA}:{relative}", "exec"), module.__dict__)
    return module

agent = frozen("wms_print_agent", "tools/print-agent/wms_print_agent.py")
runtime = frozen("wms_print_runtime", "tools/print-agent/wms_print_runtime.py")
results = {"source_commit": SHA, "native_windows_or_printer_exercised": False}
xml = ET.fromstring(runtime._windows_task_xml(Path("C:/WMS/wms-print.exe"), "S-1-5-21-442"))
results["restart_count"] = int(xml.find(".//{*}Count").text)
with tempfile.TemporaryDirectory(prefix="wms442-delta-review-") as folder:
    directory = Path(folder)
    config = directory / "connection.json"
    outbox = directory / "inflight.json"
    with patch.object(runtime, "restrict_private_directory"):
        runtime.write_private(config, {"queue_name": "Принтер склада"})
        results["utf8_roundtrip"] = runtime.read_private(config)["queue_name"]
    outbox.write_text('{"phase":"submitting"}', encoding="utf-8")
    for args in [["--reconnect"], ["--reset-state", "--confirm-reset"], ["--uninstall"]]:
        with patch.object(runtime, "state_directory", return_value=directory), patch.object(runtime, "printer_adapter", return_value=object()), patch.object(runtime, "request_stop", return_value=True), patch.object(runtime, "wait_for_stop", return_value=False), patch.object(runtime, "disable_autostart") as disable, redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            code = runtime.main(args)
            results["stop_timeout_" + args[0]] = {"code": code, "config_retained": config.exists(), "outbox_retained": outbox.exists(), "disable_called": disable.called}
    with runtime.single_instance(directory):
        with patch.object(runtime, "state_directory", return_value=directory), patch.object(runtime, "printer_adapter", return_value=object()), redirect_stderr(io.StringIO()):
            results["ordinary_setup_with_worker_lock_exit"] = runtime.main([])
    with patch.object(runtime, "state_directory", return_value=directory), patch.object(runtime, "printer_adapter", return_value=object()), patch.object(runtime, "stop_background_before_mutation") as stop, patch.object(runtime, "start_registered_background") as restart, redirect_stderr(io.StringIO()):
        code = runtime.main(["--reconnect"])
        results["reconnect_with_pending_receipt"] = {"code": code, "stop_called": stop.called, "restart_called": restart.called, "config_retained": config.exists()}

calls = []
class DC:
    def CreatePrinterDC(self, queue): calls.append(["queue", queue])
    def GetDeviceCaps(self, cap):
        calls.append(["cap", cap])
        return {88:203, 90:203, 110:464, 111:320, 8:440, 10:300, 112:12, 113:10}[cap]
    def StartDoc(self, title): calls.append(["StartDoc"]); return 442
    def StartPage(self): pass
    def EndPage(self): pass
    def EndDoc(self): pass
    def DeleteDC(self): pass
    def GetHandleOutput(self): return 1
class Dib:
    def __init__(self, image): pass
    def draw(self, handle, rect): calls.append(["draw", list(rect)])
adapter = runtime.WindowsAdapter({"win32ui": types.SimpleNamespace(CreateDC=DC), "ImageWin": types.SimpleNamespace(Dib=Dib)})
with patch.object(adapter, "queues", return_value=["Принтер склада"]), patch.object(adapter, "_pages", return_value=[(object(),58.0,40.0)]):
    adapter.validate_layout("Принтер склада",58,40)
    receipt=adapter.submit(b"synthetic","application/pdf","Принтер склада",1,58,40)
results["printable_area_smaller_than_physical_page"] = {"receipt":receipt,"physical_pixels":[464,320],"printable_pixels":[440,300],"offset_pixels":[12,10],"calls":calls}
print(json.dumps(results, ensure_ascii=False, indent=2))
