"""Deterministic local WMS-441 response-loss harness.

The control file starts as ``{"document": "<uuid>", "gate": "armed"}``.
After the first successful loose-putaway the proxy records its operation UUID,
closes the gate, and drops that response.  While the gate is closed, later GETs
and POSTs for exactly that document and operation do not reach the API.  Change
``gate`` to ``released`` to allow the persisted operation to be replayed.

Only forwards to the explicitly isolated localhost:18082 API. Never logs auth.
"""
import http.client
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONTROL = Path('/tmp/wms441-response-loss-control.json')
EVENTS = Path('/tmp/wms441-response-loss-events.jsonl')


def control() -> dict[str, str]:
    if not CONTROL.exists():
        return {}
    try:
        raw = json.loads(CONTROL.read_text())
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def log(event: str, **fields: object) -> None:
    EVENTS.write_text(
        EVENTS.read_text() + json.dumps({'event': event, **fields}) + '\n'
        if EVENTS.exists() else json.dumps({'event': event, **fields}) + '\n'
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.forward()

    def do_POST(self):
        self.forward()

    def do_PATCH(self):
        self.forward()

    def do_PUT(self):
        self.forward()

    def forward(self):
        raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        try:
            body = json.loads(raw) if raw else {}
        except ValueError:
            body = {}
        gate = control()
        document = str(body.get('inbound_request_id', ''))
        if '/inbound-intake-requests/' in self.path:
            document = self.path.split('/inbound-intake-requests/')[1].split('/')[0].split('?')[0]
        operation_id = body.get('operation_id') or body.get('operationId')
        applies = document == gate.get('document')
        same_operation = operation_id and operation_id == gate.get('first_operation_id')
        if self.command == 'GET' and applies and gate.get('gate') == 'closed':
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'{"detail":"fixture GET outage"}')
            return
        if self.command == 'POST' and applies and same_operation and gate.get('gate') == 'closed':
            log('post_blocked', document=document, operation_id=operation_id)
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'{"detail":"fixture POST gate closed"}')
            return
        upstream = http.client.HTTPConnection('127.0.0.1', 18082, timeout=30)
        upstream.request(self.command, self.path, raw, dict(self.headers))
        response = upstream.getresponse()
        result = response.read()
        if self.command == 'POST' and applies and gate.get('gate') == 'armed' and 200 <= response.status < 300:
            CONTROL.write_text(json.dumps({
                'document': document,
                'gate': 'closed',
                'first_operation_id': operation_id,
                'first_status': response.status,
            }) + '\n')
            log('response_dropped_after_upstream_success', document=document,
                operation_id=operation_id, status=response.status)
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            upstream.close()
            return
        if self.command == 'POST' and operation_id:
            log('response_delivered', document=document, operation_id=operation_id,
                status=response.status)
        self.send_response(response.status)
        for key, value in response.getheaders():
            if key.lower() not in {'connection', 'transfer-encoding', 'content-length'}:
                self.send_header(key, value)
        self.send_header('Content-Length', str(len(result)))
        self.end_headers()
        self.wfile.write(result)
        upstream.close()


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 18086), Handler).serve_forever()
