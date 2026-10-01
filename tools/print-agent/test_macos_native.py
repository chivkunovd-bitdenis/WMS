"""Compiled native tests use fake queues only; never print on the host's printer."""

import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8//8/AwMDEwMDAwMDAwAkBgMB/DXemwAAAABJRU5ErkJggg=="
)


@unittest.skipUnless(sys.platform == "darwin", "native macOS package")
class NativeRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="wms-native-test-")
        cls.root = Path(cls.directory.name)
        cls.binary = cls.root / "wms-print"
        cls.observer = cls.root / "observe-fixture"
        subprocess.run(
            [
                "clang",
                "-c",
                str(ROOT / "wms_cups_observe.c"),
                "-o",
                str(cls.root / "cups.o"),
            ],
            check=True,
        )
        subprocess.run(
            [
                "swiftc",
                "-O",
                "-whole-module-optimization",
                str(ROOT / "wms_print_direct_macos.swift"),
                "-Xlinker",
                str(cls.root / "cups.o"),
                "-lcups",
                "-o",
                str(cls.binary),
            ],
            check=True,
        )
        subprocess.run(
            [
                "clang",
                str(ROOT / "test_wms_cups_observe.c"),
                "-lcups",
                "-o",
                str(cls.observer),
            ],
            check=True,
        )
        shutil.copyfile(ROOT / "history.html", cls.root / "history.html")

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_compiled_store_crash_faults_and_retry_self_test(self):
        result = subprocess.run(
            [str(self.binary), "--self-test"],
            capture_output=True,
            text=True,
            timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("abrupt process exits", result.stdout)

    def observe(self, count, state, title="WMS-title", receipt=""):
        return json.loads(
            subprocess.check_output(
                [str(self.observer), str(count), str(state), title, receipt], timeout=3
            )
        )

    def test_cups_unique_title_receipt_state_and_reasons(self):
        for state in range(3, 10):
            with self.subTest(state=state):
                result = self.observe(1, state)
                self.assertEqual(result["matches"], 1)
                self.assertEqual(result["receipt"], "test-printer-41")
                self.assertEqual(result["jobState"], state)
                self.assertEqual(result["jobStateReasons"], ["queued-in-device"])
                self.assertEqual(result["printerStateReasons"], ["media-empty"])
                self.assertIn('"waiting"\n', result["jobStateMessage"])
        self.assertEqual(self.observe(2, 5)["matches"], 2)
        self.assertEqual(
            self.observe(2, 5, receipt="test-printer-42")["receipt"], "test-printer-42"
        )
        self.assertEqual(
            self.observe(1, 5, title="other-title", receipt="test-printer-41")[
                "matches"
            ],
            0,
        )
        self.assertEqual(self.observe(0, 5)["matches"], 0)

    def test_http_async_legacy_recovery_and_restart(self):
        directory = self.root / "http-store"
        directory.mkdir()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {**os.environ, "WMS_PRINT_PORT": str(port)}
        base = f"http://127.0.0.1:{port}"
        process = None

        def start():
            nonlocal process
            process = subprocess.Popen(
                [str(self.binary), "--self-test-http", str(directory)],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            for _ in range(100):
                try:
                    with urlopen(base + "/health", timeout=0.2):
                        return
                except (OSError, HTTPError):
                    time.sleep(0.03)
            self.fail("native HTTP test server did not start")

        def request(path, body=None):
            req = Request(
                base + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={"X-WMS-Print": "1", "Content-Type": "application/json"},
            )
            with urlopen(req, timeout=5) as r:
                return r.status, json.load(r)

        body = dict(
            idempotencyKey="scan/key",
            imageDataUrl="data:image/png;base64," + base64.b64encode(PNG).decode(),
            widthMm=58,
            heightMm=40,
            context=dict(
                tenantId="tenant", userId="user", orderId="order", wbOrderId=654
            ),
            protocolVersion=2,
        )
        try:
            start()
            self.assertEqual(request("/health")[1]["protocolVersion"], 2)
            status, value = request("/print", body)
            self.assertEqual(status, 202)
            for _ in range(100):
                status, value = request("/jobs/scan%2Fkey")
                if value.get("receipt"):
                    break
                time.sleep(0.01)
            self.assertEqual(value["receipt"], "test-printer-1")
            self.assertEqual(value["context"]["wbOrderId"], 654)
            self.assertEqual(request("/print", body)[1]["receipt"], "test-printer-1")
            self.assertEqual((directory / "submission-count").read_text(), "1")
            with urlopen(base + "/jobs/scan%2Fkey/image") as r:
                self.assertEqual(r.read(), PNG)
            legacy = {**body, "idempotencyKey": "legacy"}
            legacy.pop("protocolVersion")
            status, value = request("/print", legacy)
            self.assertEqual(status, 200)
            self.assertEqual(value["receipt"], "test-printer-2")
            (directory / "observation.json").write_text(
                json.dumps(dict(matches=1, receipt="test-printer-1", jobState=7))
            )
            self.assertEqual(
                request("/jobs/scan%2Fkey/reconcile", {})[1]["status"], "canceled"
            )
            repeat = {**body}
            repeat.pop("protocolVersion")
            with self.assertRaises(HTTPError) as error:
                request("/print", repeat)
            self.assertEqual(error.exception.code, 409)
            error.exception.close()
            _, child = request(
                "/jobs/scan%2Fkey/reprint",
                dict(idempotencyKey="child", acknowledgeDuplicateRisk=True),
            )
            for _ in range(100):
                child = request("/jobs/child")[1]
                if child.get("receipt"):
                    break
                time.sleep(0.01)
            original = request("/jobs/scan%2Fkey")[1]
            self.assertEqual(original["status"], "canceled")
            self.assertEqual(original["reprints"][0]["hash"], original["hash"])
            self.assertEqual(original["reprints"][0]["parentKey"], "scan/key")
            self.assertEqual(original["reprints"][0]["receipt"], "test-printer-3")
            self.assertEqual(
                request(
                    "/jobs/scan%2Fkey/reprint",
                    dict(idempotencyKey="child", acknowledgeDuplicateRisk=True),
                )[1]["receipt"],
                "test-printer-3",
            )
            self.assertEqual((directory / "submission-count").read_text(), "3")
            process.kill()
            process.wait(timeout=3)
            process.stderr.close()
            (directory / "observation.json").unlink()
            start()
            self.assertEqual(
                request("/jobs/scan%2Fkey")[1]["reprints"][0]["receipt"],
                "test-printer-3",
            )
            with urlopen(base + "/") as r:
                self.assertIn("История WMS Print", r.read().decode())
            with self.assertRaises(HTTPError) as error:
                urlopen(
                    Request(base + "/jobs", headers={"Origin": "https://evil.example"}),
                    timeout=2,
                )
            self.assertEqual(error.exception.code, 403)
            error.exception.close()

            def send_batch(index):
                return request("/print", {**body, "idempotencyKey": f"batch-{index}"})

            with ThreadPoolExecutor(max_workers=16) as pool:
                replies = list(pool.map(send_batch, list(range(350)) * 2))
            self.assertTrue(all(status == 202 for status, _ in replies))
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                batch = [
                    item
                    for item in request("/jobs")[1]["jobs"]
                    if item["idempotencyKey"].startswith("batch-")
                ]
                if len(batch) == 350 and all(item.get("receipt") for item in batch):
                    break
                time.sleep(0.05)
            self.assertEqual(len(batch), 350)
            self.assertTrue(all(item.get("receipt") for item in batch))
            self.assertEqual((directory / "submission-count").read_text(), "350")
        finally:
            if process:
                process.terminate()
                process.wait(timeout=3)
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()
