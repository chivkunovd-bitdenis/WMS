#!/usr/bin/env python3
"""Run the candidate WMS Print Direct handler with only its printer adapter injected.

The HTTP Handler and SQLite idempotency ledger come from the exact candidate
checkout. The injected sink stores every accepted PNG and a stable synthetic
receipt without reaching CUPS, GDI, or a physical queue.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sys
import threading
from datetime import UTC, datetime
from http.server import ThreadingHTTPServer


EXPECTED_CANDIDATE = "28a7999fefd886de41f6ffda5b05b69cd49aa496"
EXPECTED_SOURCE_BLOBS = {
    "tools/print-agent/wms_print_direct.py": "81ebff2bb9c638f1d6d41e2f22f618282a5ba476",
    "frontend/src/utils/printDirectQr.ts": "0a8ceaf8b7018ef1be3278b8d9f2806630f04050",
    "frontend/src/utils/printPreparedQr.ts": "e62caa36019cca656716a9947bbab487713a1f5b",
    "frontend/src/screens/v2/fbsSequentialPacking.ts": "82a6ad9f4584532c85b763b8d409a29d4ffd93a2",
    "frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx": "4de19896e0242264405ed3972a55657f08b4d3ed",
}
TEST_ORIGIN = "http://127.0.0.1:16696"


def write_json_line(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def build_handler(checkout: Path, output: Path):
    import subprocess

    candidate = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True,
    ).strip()
    if candidate != EXPECTED_CANDIDATE:
        raise RuntimeError(f"Expected candidate {EXPECTED_CANDIDATE}, found {candidate}")

    direct_dir = checkout / "tools" / "print-agent"
    sys.path.insert(0, str(direct_dir))
    import wms_print_direct as native

    for path, expected_blob in EXPECTED_SOURCE_BLOBS.items():
        source_blob = subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", f"HEAD:{path}"], text=True,
        ).strip()
        if source_blob != expected_blob:
            raise RuntimeError(f"Unexpected candidate source blob for {path}: {source_blob}")

    output.mkdir(parents=True, exist_ok=True)
    sink_dir = output / "sink"
    sink_dir.mkdir(exist_ok=True)
    ledger_dir = output / "ledger"
    (output / "requests.jsonl").touch(exist_ok=True)
    (output / "sink-receipts.jsonl").touch(exist_ok=True)

    native.ALLOWED_ORIGINS.add(TEST_ORIGIN)

    class EmulatedPrinter(native.Printer):
        def __init__(self):
            self.current_key: str | None = None
            self.submit_lock = threading.Lock()
            self.accepted = 0
            super().__init__(ledger_dir, submit=self.capture)

        def print(self, body):
            self.current_key = body.get("idempotencyKey")
            return super().print(body)

        def capture(self, png: bytes) -> str:
            from PIL import Image

            with Image.open(io.BytesIO(png)) as image:
                image.verify()
            with self.submit_lock:
                self.accepted += 1
                digest = hashlib.sha256(png).hexdigest()
                receipt = f"emulator-{self.accepted:04d}-{digest[:12]}"
                name = f"job-{self.accepted:04d}-{digest[:12]}.png"
                (sink_dir / name).write_bytes(png)
                write_json_line(output / "sink-receipts.jsonl", {
                    "accepted_at_utc": datetime.now(UTC).isoformat(),
                    "job_key": self.current_key,
                    "sha256": digest,
                    "png": f"sink/{name}",
                    "bytes": len(png),
                    "receipt": receipt,
                })
                return receipt

    class EvidenceHandler(native.Handler):
        def do_POST(self):
            if self.path == "/_proof/drop-next-response":
                self.server.drop_next_response = True
                self.respond(200, {"armed": True})
                return
            if self.path == "/_proof/status":
                self.respond(200, {
                    "drop_next_response": self.server.drop_next_response,
                    "accepted_png_count": self.server.printer.accepted,
                })
                return
            if self.path == "/print":
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw)
                    record = {
                        "received_at_utc": datetime.now(UTC).isoformat(),
                        "path": self.path,
                        "origin": self.headers.get("Origin"),
                        "body": body,
                    }
                    write_json_line(output / "requests.jsonl", record)
                finally:
                    self.rfile = io.BytesIO(raw)
            return super().do_POST()

        def respond(self, status, value):
            if (
                status == 200
                and isinstance(value, dict)
                and value.get("receipt")
                and self.server.drop_next_response
            ):
                self.server.drop_next_response = False
                self.close_connection = True
                self.connection.close()
                return
            return super().respond(status, value)

    class EvidenceServer(ThreadingHTTPServer):
        allow_reuse_address = True

        def __init__(self, address):
            super().__init__(address, EvidenceHandler)
            self.printer = EmulatedPrinter()
            self.drop_next_response = False

    return EvidenceServer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=17843)
    args = parser.parse_args()
    server = build_handler(args.checkout.resolve(), args.output.resolve())((args.host, args.port))
    print(f"WMS Print Direct handler listening on {args.host}:{args.port}; synthetic sink enabled")
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
