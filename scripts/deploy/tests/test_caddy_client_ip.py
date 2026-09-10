"""WMS-270/377: real Caddy -> loopback upstream header regression, no app/DB.

Run: python3 scripts/deploy/tests/test_caddy_client_ip.py --caddy /path/to/caddy
The binary must be supplied explicitly; missing Caddy is never a passing skip.
"""

from __future__ import annotations

import argparse
import contextlib
import http.client
import json
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


class EchoHeaders(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({
            "xff": self.headers.get_all("X-Forwarded-For", []),
            "path": self.path,
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise AssertionError(f"Expected exactly one local fixture anchor: {old!r}")
    return text.replace(old, new, 1)


@contextlib.contextmanager
def running_proxy(binary, source, trusted):
    with tempfile.TemporaryDirectory(prefix="wms270-caddy-test-") as directory:
        root = Path(directory)
        upstream = HTTPServer(("127.0.0.1", 0), EchoHeaders)
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        process = None
        try:
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            # Retain the production routes, strict parser and header expression.
            # Only listeners/upstream and the simulated immediate edge differ.
            config = replace_once(source, "{\n  servers {",
                                  "{\n  admin off\n  auto_https off\n  persist_config off\n  servers {")
            config = replace_once(config, ":80 {", f"http://127.0.0.1:{port} {{")
            config = replace_once(config, "reverse_proxy api:8000 {",
                                  f"reverse_proxy 127.0.0.1:{upstream.server_port} {{")
            if trusted:
                config = replace_once(config, "trusted_proxies static ",
                                      "trusted_proxies static 127.0.0.1/32 ")
            config_path = root / "Caddyfile"
            config_path.write_text(config)
            with (root / "caddy.log").open("w+") as log:
                process = subprocess.Popen(
                    [binary, "run", "--config", str(config_path), "--adapter", "caddyfile"],
                    cwd=root, stdout=log, stderr=subprocess.STDOUT,
                    env={"XDG_DATA_HOME": str(root / "data"),
                         "XDG_CONFIG_HOME": str(root / "config")},
                )
                print(json.dumps({"caddy_pid": process.pid, "trusted_peer": trusted,
                                  "listen": f"127.0.0.1:{port}",
                                  "upstream": f"127.0.0.1:{upstream.server_port}"}), flush=True)
                deadline = time.monotonic() + 10
                while True:
                    if process.poll() is not None or time.monotonic() > deadline:
                        log.seek(0)
                        raise AssertionError("Isolated Caddy failed to start: " + log.read())
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                            break
                    except OSError:
                        time.sleep(0.05)
                yield port
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                print(json.dumps({"caddy_pid": process.pid, "reaped": True}), flush=True)
            upstream.shutdown()
            upstream.server_close()
            thread.join(timeout=5)


class ClientIPRegression(unittest.TestCase):
    def check_request(self, port, label, xff, expected):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            headers = {} if xff is None else {"X-Forwarded-For": xff}
            connection.request("GET", "/api/probe", headers=headers)
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            actual = json.loads(response.read())
        finally:
            connection.close()
        print(json.dumps({"case": label, "sent_xff": xff,
                          "received": actual, "expected_xff": expected}), flush=True)
        # Exact list equality catches literals, duplicate headers and raw chains.
        self.assertEqual(actual, {"xff": [expected], "path": "/probe"})

    def test_untrusted_peer_cannot_supply_client_ip(self):
        with running_proxy(BINARY, SOURCE, trusted=False) as port:
            for label, xff in [
                ("direct", None),
                ("untrusted-spoof", "198.51.100.99"),
                ("untrusted-spoof-chain", "198.51.100.99, 172.18.0.4"),
            ]:
                with self.subTest(label=label):
                    self.check_request(port, label, xff, "127.0.0.1")

    def test_trusted_peer_preserves_distinct_clients_and_rejects_spoof_prefix(self):
        with running_proxy(BINARY, SOURCE, trusted=True) as port:
            for label, xff, expected in [
                ("client-a", "203.0.113.10", "203.0.113.10"),
                ("client-b", "203.0.113.11", "203.0.113.11"),
                ("trusted-hop", "203.0.113.10, 172.18.0.4", "203.0.113.10"),
                ("spoof-prefix", "198.51.100.99, 203.0.113.10, 172.18.0.4", "203.0.113.10"),
                ("missing-forwarded-header", None, "127.0.0.1"),
            ]:
                with self.subTest(label=label):
                    self.check_request(port, label, xff, expected)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caddy", required=True, type=Path)
    parser.add_argument("--caddyfile", type=Path, default=(
        Path(__file__).resolve().parents[3] / "deploy/Caddyfile.http"))
    args = parser.parse_args()
    BINARY = str(args.caddy.resolve(strict=True))
    SOURCE = args.caddyfile.read_text()
    print(subprocess.check_output([BINARY, "version"], text=True).strip(), flush=True)
    unittest.main(argv=[__file__], verbosity=2)
