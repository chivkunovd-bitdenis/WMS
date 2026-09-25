"""Read-only probes of frozen WMS-442 source; no printer, server or OS task is used."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
from unittest.mock import patch
import xml.etree.ElementTree as ET

SHA = 'e76c5c4b67c768039decfbb419fc32027c36f335'
ROOT = Path(__file__).resolve().parents[4]


def frozen(name, relative):
    source = subprocess.check_output(['git', 'show', f'{SHA}:{relative}'], cwd=ROOT, text=True)
    module = types.ModuleType(name)
    module.__file__ = str(ROOT / relative)
    sys.modules[name] = module
    exec(compile(source, f'{SHA}:{relative}', 'exec'), module.__dict__)
    return module


agent = frozen('wms_print_agent', 'tools/print-agent/wms_print_agent.py')
runtime = frozen('wms_print_runtime', 'tools/print-agent/wms_print_runtime.py')
build = frozen('wms_print_build_probe', 'tools/print-agent/build_package.py')
results = {'source_commit': SHA}
xml = ET.fromstring(runtime._windows_task_xml(Path('C:/Program Files/WMS/wms-print.exe'), 'S-1-5-21-442'))
count = int(xml.find('.//{*}Count').text)
results['task_restart_count'] = {'value': count, 'valid_unsigned_byte_1_255': 1 <= count <= 255}

with tempfile.TemporaryDirectory(prefix='wms442-review-') as folder:
    directory = Path(folder)
    original_fdopen = os.fdopen
    def windows_ansi_fdopen(fd, mode):
        return original_fdopen(fd, mode, encoding='cp1252')
    with patch.object(runtime.os, 'fdopen', windows_ansi_fdopen), patch.object(runtime, 'restrict_private_directory'):
        try:
            runtime.write_private(directory / 'unicode.json', {'queue_name': 'Принтер склада'})
            results['windows_ansi_json'] = 'unexpected success'
        except UnicodeEncodeError as error:
            results['windows_ansi_json'] = {'exception': type(error).__name__, 'encoding': error.encoding}

    config = directory / 'connection.json'
    config.write_text('{"synthetic": true}', encoding='utf-8')
    outbox = directory / 'inflight.json'
    outbox.write_text('{"phase": "submitting"}', encoding='utf-8')
    with runtime.single_instance(directory):
        with patch.object(runtime, 'state_directory', return_value=directory), patch.object(runtime, 'printer_adapter', return_value=object()), redirect_stderr(io.StringIO()) as errors:
            code = runtime.main(['--reconnect'])
            results['reconnect_with_active_worker_lock'] = {'exit_code': code, 'retained_config': config.exists(), 'generic_error': bool(errors.getvalue())}
        # A worker still owns the lock. A stop signal is not a joined worker.
        with patch.object(runtime, 'state_directory', return_value=directory), patch.object(runtime, 'request_stop', return_value=True), patch.object(runtime, 'disable_autostart'), redirect_stdout(io.StringIO()):
            code = runtime.main(['--reset-state', '--confirm-reset'])
            results['reset_while_worker_owns_lock'] = {'exit_code': code, 'config_deleted': not config.exists(), 'inflight_deleted': not outbox.exists()}

with patch.object(build.sys, 'platform', 'win32'), patch.object(build.subprocess, 'run') as run:
    build.build_executable()
    command = run.call_args.args[0]
    results['windows_build_worker_console'] = {'windowed_or_hide_option_present': any(x in command for x in ('--windowed', '--noconsole', '--hide-console'))}

calls = []
class DC:
    def CreatePrinterDC(self, queue): calls.append(['CreatePrinterDC', queue])
    def StartDoc(self, title): calls.append(['StartDoc']); return 442
    def GetDeviceCaps(self, cap): calls.append(['GetDeviceCaps', cap]); return 203
    def StartPage(self): calls.append(['StartPage'])
    def EndPage(self): calls.append(['EndPage'])
    def EndDoc(self): calls.append(['EndDoc'])
    def DeleteDC(self): pass
    def GetHandleOutput(self): return 1
class Dib:
    def __init__(self, image): pass
    def draw(self, handle, rectangle): calls.append(['draw', list(rectangle)])
adapter = runtime.WindowsAdapter({'win32ui': types.SimpleNamespace(CreateDC=DC), 'ImageWin': types.SimpleNamespace(Dib=Dib)})
with patch.object(adapter, 'queues', return_value=['Synthetic']), patch.object(adapter, '_pages', return_value=[(object(), 58.0, 40.0)]):
    receipt = adapter.submit(b'synthetic', 'application/pdf', 'Synthetic', 2, 58, 40)
results['gdi_call_boundary'] = {'receipt': receipt, 'calls': calls, 'native_driver_exercised': False}
print(json.dumps(results, ensure_ascii=False, indent=2))
