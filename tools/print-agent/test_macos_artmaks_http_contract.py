"""WMS-607 real Swift HTTP contract; only external lp/lpstat and storage isolated.

No self-test Printer, frontend changes, retry endpoint or physical printer.
WMS607_SWIFT_SOURCE permits a disposable source-copy mutation control.
"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get("WMS607_SWIFT_SOURCE", ROOT / "wms_print_direct_macos.swift"))
PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8//8/"
    "AwMDEwMDAwMDAwAkBgMB/DXemwAAAABJRU5ErkJggg=="
)


@unittest.skipUnless(platform.system() == "Darwin", "Requires actual macOS Swift runtime")
class ArtMaksHTTPContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compilation = tempfile.TemporaryDirectory(prefix="wms607-http-compile-")
        cls.compile_root = Path(cls.compilation.name)
        lpstat = cls.compile_root / "lpstat"
        lpstat.write_text("#!" + sys.executable + "\n" + r'''
import json, os, sys
from pathlib import Path
root = Path(os.environ['WMS607_HTTP_ROOT'])
with (root/'commands.jsonl').open('a') as out:
    out.write(json.dumps(['lpstat']+sys.argv[1:])+'\n')
if not (root/'queue-ready').exists(): sys.exit(1)
print('system default destination: Label_Printer' if sys.argv[1:] == ['-d'] else 'printer Label_Printer is idle')
''')
        lp = cls.compile_root / "lp"
        lp.write_text("#!" + sys.executable + "\n" + r'''
import json, os, sys, time
from pathlib import Path
root = Path(os.environ['WMS607_HTTP_ROOT'])
with (root/'commands.jsonl').open('a') as out:
    out.write(json.dumps(['lp']+sys.argv[1:])+'\n')
if (root/'hold-lp').exists():
    (root/'lp-entered').touch()
    deadline = time.monotonic()+8
    while not (root/'release-lp').exists():
        if time.monotonic() > deadline: sys.exit(3)
        time.sleep(.01)
if (root/'unknown-lp').exists():
    print('External receipt lost; submission outcome unknown')
    sys.exit(1)
print('request id is Label_Printer-41 (1 file)')
''')
        lpstat.chmod(0o700)
        lp.chmod(0o700)
        original = SOURCE.read_text()
        source = original.replace('"/usr/bin/lpstat"', json.dumps(str(lpstat)))
        source = source.replace('"/usr/bin/lp"', json.dumps(str(lp)))
        storage = "FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]"
        if original.count(storage) != 1:
            raise AssertionError("Expected actual normal-server storage boundary exactly once")
        source = source.replace(
            storage,
            'URL(fileURLWithPath: ProcessInfo.processInfo.environment["WMS607_HTTP_ROOT"]!)',
        )
        # External CUPS symbol only. Passive /print never calls --observe.
        source += '\n@_cdecl("wms_cups_observe")\nfunc contractObserve(_ queue: UnsafePointer<CChar>, _ receipt: UnsafePointer<CChar>, _ title: UnsafePointer<CChar>) -> Int32 { fatalError("Unexpected CUPS observer in lp/lpstat-only HTTP contract") }\n'
        probe = cls.compile_root / "probe.swift"
        probe.write_text(source)
        cls.executable = cls.compile_root / "probe"
        subprocess.run(
            ["swiftc", str(probe), "-o", str(cls.executable)],
            check=True, capture_output=True, timeout=60,
        )
        cls.provenance = {
            "source_sha256": hashlib.sha256(original.encode()).hexdigest(),
            "transformed_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "swift": subprocess.check_output(["swiftc", "--version"], text=True).strip(),
            "patches": ["lpstat path", "lp path", "isolated app-support root", "unused CUPS symbol"],
            "server": "normal entrypoint; entire HTTP and Printer retained",
        }

    @classmethod
    def tearDownClass(cls):
        cls.compilation.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="wms607-http-case-")
        self.root = Path(self.directory.name)
        (self.root / "commands.jsonl").write_text("")
        self.responses = []
        self.process = None
        self.start()

    def tearDown(self):
        try:
            (self.root / "release-lp").touch()
            self.stop()
            evidence = os.environ.get("WMS607_HTTP_EVIDENCE_DIR")
            if evidence:
                out = Path(evidence)
                out.mkdir(parents=True, exist_ok=True)
                journals = [json.loads(p.read_text()) for p in sorted(
                    (self.root / "WMS Print/direct/jobs-v2").glob("*.json")
                )]
                record = {
                    "case": self.id(), "provenance": self.provenance,
                    "responses": self.responses, "commands": self.commands(), "jobs": journals,
                }
                text = json.dumps(record, ensure_ascii=False, indent=2)
                (out / (self._testMethodName + ".json")).write_text(text.replace(str(self.root), "$CASE"))
        finally:
            self.directory.cleanup()

    def start(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.base = f"http://127.0.0.1:{port}"
        self.process = subprocess.Popen(
            [str(self.executable)],
            env={**os.environ, "WMS607_HTTP_ROOT": str(self.root), "WMS_PRINT_PORT": str(port)},
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        self.until(lambda: self.request("/health")[0] == 200)

    def stop(self):
        if self.process is not None:
            self.process.terminate()
            self.process.wait(timeout=3)
            self.process.stderr.close()
            self.process = None

    def until(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                if predicate():
                    return
            except OSError:
                pass
            time.sleep(.02)  # Test observes readiness; no altered product timer.
        self.fail("Actual server/external boundary did not reach expected state")

    def request(self, path, body=None):
        req = Request(
            self.base + path, data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "X-WMS-Print": "1",
                     "Origin": "https://wms.sellerfocus.pro"},
        )
        try:
            with urlopen(req, timeout=25) as response:
                result = response.status, json.load(response)
        except HTTPError as error:
            with error:
                result = error.code, json.load(error)
        self.responses.append({"path": path, "protocolVersion": (body or {}).get("protocolVersion"),
                               "http": result[0], "body": result[1]})
        return result

    @staticmethod
    def body(key):
        return {"idempotencyKey": key, "imageDataUrl": "data:image/png;base64," + PNG,
                "widthMm": 58, "heightMm": 40}

    def commands(self):
        return [json.loads(line) for line in (self.root / "commands.jsonl").read_text().splitlines()]

    def submissions(self):
        return [c for c in self.commands() if c[0] == "lp"]

    def test_legacy_same_key_recovers_only_after_proven_pre_submit_failure(self):
        body = self.body("same-scan")
        status, failure = self.request("/print", body)
        self.assertEqual((status, failure["status"]), (409, "failed_before_submit"))
        self.assertEqual(self.submissions(), [])
        (self.root / "queue-ready").touch()
        control_status, control = self.request("/print", self.body("recovery-control"))
        self.assertEqual((control_status, control["status"]), (200, "accepted"))
        first = self.request("/print", body)
        second = self.request("/print", body)
        self.assertEqual(first[0], 200, "Restored queue must recover the original explicit scan/key")
        self.assertEqual(second[0], 200)
        self.assertEqual(first[1]["receipt"], second[1]["receipt"])
        self.assertEqual(first[1]["idempotencyKey"], "same-scan")
        self.assertEqual(len(self.submissions()), 2, "Control + original each submit exactly once")
        for command in self.submissions():
            self.assertIn("media=Custom.58x40mm", command)
            self.assertIn("copies=1", command)

    def test_legacy_error_preserves_specific_pre_submit_reason(self):
        status, failure = self.request("/print", self.body("reason-scan"))
        self.assertEqual((status, failure["status"]), (409, "failed_before_submit"))
        self.assertIn("Недоступна служба печати macOS", failure["reason"])
        self.assertIn("Этикетка не отправлена", failure["reason"])
        self.assertEqual(self.submissions(), [])
        self.assertIn(failure["reason"], failure["error"], "Legacy frontend reads error, not reason")

    def test_unknown_same_key_never_resubmits_after_queue_recovery(self):
        (self.root / "queue-ready").touch()
        (self.root / "unknown-lp").touch()
        body = self.body("unknown-scan")
        status, first = self.request("/print", body)
        self.assertEqual((status, first["status"]), (409, "unknown"))
        self.assertEqual(len(self.submissions()), 1)
        (self.root / "unknown-lp").unlink()
        before = self.commands()
        for _ in range(2):
            status, repeat = self.request("/print", body)
            self.assertEqual((status, repeat["status"]), (409, "unknown"))
            self.assertNotIn("receipt", repeat)
            self.assertEqual(self.commands(), before, "Unknown outcome must not query/resubmit automatically")

    def test_submitting_same_key_has_one_live_external_submission(self):
        (self.root / "queue-ready").touch()
        (self.root / "hold-lp").touch()
        body = self.body("live-scan")
        status, _ = self.request("/print", {**body, "protocolVersion": 2})
        self.assertEqual(status, 202)
        self.until(lambda: (self.root / "lp-entered").exists())
        self.assertEqual(self.request("/jobs/live-scan")[1]["status"], "submitting")
        before = self.commands()
        status, replay = self.request("/print", {**body, "protocolVersion": 2})
        self.assertEqual((status, replay["status"]), (202, "submitting"))
        self.assertEqual(self.commands(), before)
        self.assertEqual(len(self.submissions()), 1)
        # Legacy POST must return this same pending job's receipt after release.
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.request, "/print", body)
            (self.root / "release-lp").touch()
            status, accepted = future.result(timeout=25)
        self.assertEqual((status, accepted["status"]), (200, "accepted"))
        self.assertEqual(accepted["receipt"], "Label_Printer-41")
        self.assertEqual(len(self.submissions()), 1)

    def test_accepted_receipt_same_key_never_resubmits(self):
        (self.root / "queue-ready").touch()
        body = self.body("receipt-scan")
        status, accepted = self.request("/print", body)
        self.assertEqual((status, accepted["status"]), (200, "accepted"))
        self.assertEqual(accepted["receipt"], "Label_Printer-41")
        self.assertEqual(len(self.submissions()), 1)
        before = self.commands()
        for _ in range(2):
            status, repeat = self.request("/print", body)
            self.assertEqual((status, repeat["status"]), (200, "accepted"))
            self.assertEqual(repeat["receipt"], accepted["receipt"])
            self.assertEqual(self.commands(), before)


if __name__ == "__main__":
    unittest.main()
