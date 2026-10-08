"""Unchanged product Handler/Printer, emulated submission boundary only."""
import hashlib, json, pathlib, sys, threading
from http.server import ThreadingHTTPServer
ROOT = pathlib.Path(__file__).resolve().parents[5]
OUT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools/print-agent'))
import wms_print_direct as direct
lock = threading.Lock()
receipts = []
def submit(data):
    digest = hashlib.sha256(data).hexdigest()
    with lock:
        receipt = f'emulated-{len(receipts)+1:04d}-{digest[:12]}'
        row = {'receipt': receipt, 'sink_png_sha256': digest, 'bytes': len(data)}
        receipts.append(row)
        with (OUT / 'sink-receipts.jsonl').open('a') as f: f.write(json.dumps(row)+'\n')
    return receipt
server = ThreadingHTTPServer(('127.0.0.1', 17843), direct.Handler)
server.printer = direct.Printer(OUT / 'ledger', submit=submit)
print(json.dumps({'port':17843,'handler_path':direct.__file__,'handler_sha256':hashlib.sha256(pathlib.Path(direct.__file__).read_bytes()).hexdigest()}),flush=True)
server.serve_forever()
