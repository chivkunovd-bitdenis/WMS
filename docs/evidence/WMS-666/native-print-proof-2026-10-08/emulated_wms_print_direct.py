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
import os
from pathlib import Path
import sys
import threading
from datetime import UTC, datetime
from http.server import ThreadingHTTPServer


PRODUCT_TREE_PATHS = ("backend/app", "frontend/src", "tools/print-agent")
IDENTITY_FILES = (
    "tools/print-agent/wms_print_direct.py",
    "frontend/src/utils/printDirectQr.ts",
    "frontend/src/utils/printPreparedQr.ts",
    "frontend/src/screens/v2/fbsSequentialPacking.ts",
    "frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx",
    "backend/app/services/fbs_print_binding_service.py",
    "backend/app/services/fbs_order_tape_print_service.py",
    "backend/app/api/fbs_kiz.py",
)
TEST_ORIGIN = os.environ.get("WMS666_PRINT_ALLOWED_ORIGIN", "http://127.0.0.1:16696")


def write_json_line(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def build_handler(checkout: Path, output: Path, expected_runtime: str, product_sha: str):
    import subprocess

    candidate = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True,
    ).strip()
    if candidate != expected_runtime:
        raise RuntimeError(f"Expected runtime checkout {expected_runtime}, found {candidate}")
    subprocess.run(
        ["git", "-C", str(checkout), "diff", "--quiet", product_sha, candidate, "--", *PRODUCT_TREE_PATHS],
        check=True,
    )

    direct_dir = checkout / "tools" / "print-agent"
    sys.path.insert(0, str(direct_dir))
    import wms_print_direct as native

    source_blobs = {}
    for path in IDENTITY_FILES:
        source_blobs[path] = subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", f"HEAD:{path}"], text=True,
        ).strip()

    output.mkdir(parents=True, exist_ok=True)
    sink_dir = output / "sink"
    sink_dir.mkdir(exist_ok=True)
    ledger_dir = output / "ledger"
    (output / "requests.jsonl").touch(exist_ok=True)
    (output / "sink-receipts.jsonl").touch(exist_ok=True)
    (output / "source-identity.json").write_text(json.dumps({
        "product_sha": product_sha,
        "runtime_checkout_sha": candidate,
        "product_tree_paths_compared": list(PRODUCT_TREE_PATHS),
        "product_tree_matches": True,
        "source_blobs": source_blobs,
    }, indent=2) + "\n", encoding="utf-8")

    native.ALLOWED_ORIGINS.add(TEST_ORIGIN)

    class EmulatedPrinter(native.Printer):
        def __init__(self):
            self.request_context = threading.local()
            self.submit_lock = threading.Lock()
            self.accepted = 0
            super().__init__(ledger_dir, submit=self.capture)

        def print(self, body):
            self.request_context.job_key = body.get("idempotencyKey")
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
                    "job_key": getattr(self.request_context, "job_key", None),
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
                    "product_sha": self.server.product_sha,
                    "runtime_checkout_sha": self.server.runtime_checkout_sha,
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
            self.product_sha = product_sha
            self.runtime_checkout_sha = candidate

    return EvidenceServer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--product-sha", required=True)
    parser.add_argument("--runtime-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=17843)
    args = parser.parse_args()
    server = build_handler(args.checkout.resolve(), args.output.resolve(), args.runtime_sha, args.product_sha)((args.host, args.port))
    print(f"WMS Print Direct handler listening on {args.host}:{args.port}; product={args.product_sha}; runtime={args.runtime_sha}; synthetic sink enabled")
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
