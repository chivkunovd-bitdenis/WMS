"""Local WMS-441 test proxy. Arm file: document UUID; then block its GETs.

Only forwards to the explicitly isolated localhost:18082 API. Never logs auth.
Remove the arm file to resume normal replies; clients retain their server URL.
"""
import http.client
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ARM = Path('/tmp/wms441-response-loss-arm')


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
        armed = ARM.read_text().strip() if ARM.exists() else ''
        document = str(body.get('inbound_request_id', ''))
        if '/inbound-intake-requests/' in self.path:
            document = self.path.split('/inbound-intake-requests/')[1].split('/')[0].split('?')[0]
        applies = bool(armed) and (document == armed.removeprefix('blocked:') or armed.removeprefix('blocked:') in self.path)
        if self.command == 'GET' and applies and armed.startswith('blocked:'):
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'{"detail":"fixture GET outage"}')
            return
        upstream = http.client.HTTPConnection('127.0.0.1', 18082, timeout=30)
        upstream.request(self.command, self.path, raw, dict(self.headers))
        response = upstream.getresponse()
        result = response.read()
        if self.command == 'POST' and applies and 200 <= response.status < 300 and not armed.startswith('blocked:'):
            ARM.write_text('blocked:' + armed)
            print(json.dumps({'event': 'response_dropped_after_upstream_success', 'document': document,
                              'operation_id': body.get('operation_id'), 'status': response.status}), flush=True)
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            upstream.close()
            return
        if self.command == 'POST' and body.get('operation_id'):
            print(json.dumps({'event': 'response_delivered', 'document': document,
                              'operation_id': body['operation_id'], 'status': response.status}), flush=True)
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
