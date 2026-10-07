"""Actual new native entrypoint; existing HTTP external boundaries only."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location('http_contract', ROOT / 'tools/print-agent/test_macos_artmaks_http_contract.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
cls = module.ArtMaksHTTPContract
cls.setUpClass()
process = None
record = {}
try:
    with tempfile.TemporaryDirectory(prefix='wms607-start-proof-') as temporary:
        root = Path(temporary)
        state = root / 'direct'
        (root / 'commands.jsonl').write_text('')
        (root / 'queue-ready').touch()
        source = (ROOT / 'tools/print-agent/wms_print_direct_macos.swift').read_text().split('private struct HTTPRequest {')[0]
        source += '\n@_cdecl("wms_cups_observe")\nfunc noObserve(_ q:UnsafePointer<CChar>,_ r:UnsafePointer<CChar>,_ t:UnsafePointer<CChar>)->Int32 { fatalError("seed must never observe CUPS") }\n'
        source += '\nlet directory=URL(fileURLWithPath:CommandLine.arguments[1])\n'
        source += 'private let seed=try Printer(directory:directory,autoWork:false,submit:{_,_ in fatalError("seed must not submit")},queue:{"Label_Printer"})\n'
        body = json.dumps(module.ArtMaksHTTPContract.body('saved-before-update'))
        source += 'let body = try JSONSerialization.jsonObject(with:Data(' + json.dumps(body) + '.utf8)) as! [String:Any]\n'
        source += '_ = try seed.printJob(body)\nprint("saved without submission")\n'
        probe = root / 'seed.swift'
        probe.write_text(source)
        seed = root / 'seed'
        compiled = subprocess.run(['swiftc', str(probe), '-o', str(seed)], capture_output=True, text=True, timeout=60)
        assert compiled.returncode == 0, compiled.stderr
        subprocess.run([str(seed), str(state)], check=True, capture_output=True, timeout=5)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = {**os.environ, 'WMS607_HTTP_ROOT': str(root), 'WMS_PRINT_PORT': str(port)}
        process = subprocess.Popen([str(cls.executable), '--updater-start', str(state)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        base = f'http://127.0.0.1:{port}'
        def request(path, body=None):
            req = Request(base + path, data=json.dumps(body).encode() if body else None, headers={'Content-Type': 'application/json', 'X-WMS-Print': '1'})
            with urlopen(req, timeout=5) as response:
                return json.load(response)
        deadline = time.monotonic() + 5
        while True:
            try:
                assert request('/health')['protocolVersion'] == 2
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.02)
        time.sleep(.2)
        assert request('/jobs/saved-before-update')['status'] == 'saved'
        before = [json.loads(x) for x in (root / 'commands.jsonl').read_text().splitlines()]
        assert not any(x[0] == 'lp' for x in before), before
        ready = subprocess.run([str(cls.executable), '--readiness'], env=env, capture_output=True, text=True, timeout=10)
        assert ready.returncode == 0, ready.stderr
        commands = [json.loads(x) for x in (root / 'commands.jsonl').read_text().splitlines()]
        assert not any(x[0] == 'lp' for x in commands), commands
        new = request('/print', cls.body('explicit-new-scan'))
        assert new['status'] == 'accepted', new
        assert request('/jobs/saved-before-update')['status'] == 'saved'
        commands = [json.loads(x) for x in (root / 'commands.jsonl').read_text().splitlines()]
        assert sum(x[0] == 'lp' for x in commands) == 1, commands
        record = {'pass': True, 'provenance': cls.provenance, 'startup_submissions': 0, 'readiness_submissions': 0, 'explicit_new_scan_submissions': 1, 'saved_job_after_scan': 'saved', 'commands': commands, 'readiness': ready.stdout.strip(), 'physical_print': False}
finally:
    if process is not None:
        process.terminate()
        process.wait(timeout=3)
        process.stderr.close()
    cls.tearDownClass()
Path(__file__).with_name('native-start.json').write_text(json.dumps(record, indent=2))
print(json.dumps(record, indent=2))
