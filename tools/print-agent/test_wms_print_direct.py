import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request, urlopen

from PIL import Image
from wms_print_direct import (
    BeforeSubmitError,
    DefaultWindowsAdapter,
    Handler,
    Printer,
    ThreadingHTTPServer,
    default_printer,
    main,
    native_operation,
    observe_windows,
)

stream = io.BytesIO()
Image.new("RGB", (2, 2), "white").save(stream, format="PNG")
PNG = stream.getvalue()


def job(key="scan-1", data=PNG, width=58, height=40):
    return dict(
        idempotencyKey=key,
        imageDataUrl="data:image/png;base64," + base64.b64encode(data).decode(),
        widthMm=width,
        heightMm=height,
        protocolVersion=2,
        context=dict(
            tenantId="tenant-1",
            userId="user-1",
            orderId="order-1",
            scanId=key,
            wbOrderId=456,
        ),
    )


class DirectPrintTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.submit = Mock(return_value="printer-123")
        self.printers = []
        self.addCleanup(lambda: [p.close() for p in self.printers])

    def printer(self, **kwargs):
        printer = Printer(
            self.root,
            submit=kwargs.pop("submit", self.submit),
            queue=kwargs.pop("queue", lambda: "printer"),
            auto_work=kwargs.pop("auto_work", False),
            **kwargs,
        )
        self.printers.append(printer)
        return printer

    def restart(self, **kwargs):
        for printer in self.printers:
            printer.close()
        self.printers.clear()
        return self.printer(**kwargs)

    def test_both_production_domains_can_reach_local_printer(self):
        handler = object.__new__(Handler)
        handler.server = Mock(server_port=17843)
        for origin in ("https://sellerfocus.pro", "https://wms.sellerfocus.pro"):
            handler.headers = {"Host": "127.0.0.1:17843", "Origin": origin}
            self.assertTrue(handler.allowed())
        handler.headers["Origin"] = "https://unrelated.example"
        self.assertFalse(handler.allowed())

    def test_durable_handoff_contains_image_dimensions_context_before_submission(self):
        printer = self.printer()
        saved = printer.enqueue(job())
        self.assertEqual(saved["status"], "saved")
        self.assertEqual(printer.image("scan-1"), PNG)
        self.assertEqual((saved["widthMm"], saved["heightMm"]), (58, 40))
        self.assertEqual(saved["context"]["wbOrderId"], 456)
        self.submit.assert_not_called()
        printer.process("scan-1")
        self.assertEqual(self.submit.call_args.args[0], PNG)
        self.assertEqual(self.submit.call_args.args[1]["queue"], "printer")
        self.assertEqual(self.submit.call_args.args[1]["status"], "submitting")

    def test_receipt_survives_restart_and_duplicate_delivery(self):
        printer = self.printer()
        printer.enqueue(job())
        printer.process("scan-1")
        restarted = self.restart()
        self.assertEqual(restarted.enqueue(job())["receipt"], "printer-123")
        self.assertEqual(restarted.image("scan-1"), PNG)
        self.submit.assert_called_once()

    def test_uncertain_submission_not_repeated_even_by_retry(self):
        printer = self.printer(submit=Mock(side_effect=RuntimeError("lost receipt")))
        printer.enqueue(job())
        printer.process("scan-1")
        restarted = self.restart()
        self.assertEqual(restarted.enqueue(job())["status"], "unknown")
        with self.assertRaises(ValueError):
            restarted.retry("scan-1")
        self.submit.assert_not_called()

    def test_missing_default_is_saved_and_explicit_retry_same_intent(self):
        printer = self.printer(queue=Mock(side_effect=ValueError("no default")))
        printer.enqueue(job())
        printer.process("scan-1")
        self.assertEqual(printer.get("scan-1")["status"], "failed_before_submit")
        self.assertEqual(printer.image("scan-1"), PNG)
        self.submit.assert_not_called()
        restarted = self.restart()
        restarted.retry("scan-1")
        restarted.process("scan-1")
        self.assertEqual(restarted.get("scan-1")["status"], "accepted")
        self.submit.assert_called_once()

    def test_failed_launch_retry_allowed_unknown_launch_not_allowed(self):
        for exc, status in [
            (BeforeSubmitError("not launched"), "failed_before_submit"),
            (subprocess.TimeoutExpired("spooler", 12), "unknown"),
        ]:
            printer = (
                self.printer(submit=Mock(side_effect=exc))
                if not self.printers
                else self.restart(submit=Mock(side_effect=exc))
            )
            key = status
            printer.enqueue(job(key))
            printer.process(key)
            self.assertEqual(printer.get(key)["status"], status)

    def test_changed_size_or_bytes_rejected(self):
        printer = self.printer()
        printer.enqueue(job())
        printer.process("scan-1")
        for changed in (job(width=60), job(data=PNG + b"changed")):
            with self.assertRaises(ValueError):
                printer.enqueue(changed)
        self.submit.assert_called_once()

    def test_missing_invalid_size_or_fake_png_never_reaches_printer(self):
        printer = self.printer()
        invalid = job()
        del invalid["widthMm"]
        for value in (
            invalid,
            job(width=True),
            job(height=float("nan")),
            job(data=b"\x89PNG\r\n\x1a\ninvalid"),
        ):
            with self.assertRaises((ValueError, OSError, SyntaxError)):
                printer.enqueue(value)
        self.submit.assert_not_called()

    def test_oversized_decoded_image_is_rejected_before_load(self):
        printer = self.printer()
        fake = Mock(format="PNG", width=100000, height=100000)
        fake.__enter__ = Mock(return_value=fake)
        fake.__exit__ = Mock(return_value=False)
        with patch("PIL.Image.open", return_value=fake):
            with self.assertRaises(ValueError):
                printer.enqueue(job())
        fake.verify.assert_not_called()

    def test_insert_failure_does_not_poison_key_or_submit(self):
        printer = self.printer()
        with closing(printer.connect()) as db:
            db.execute(
                "CREATE TRIGGER deny BEFORE INSERT ON jobs BEGIN SELECT RAISE(ABORT,'disk failure'); END"
            )
            db.commit()
        with self.assertRaises(sqlite3.DatabaseError):
            printer.enqueue(job())
        self.assertIsNone(printer.get("scan-1"))
        self.submit.assert_not_called()
        with closing(printer.connect()) as db:
            db.execute("DROP TRIGGER deny")
            db.commit()
        printer.enqueue(job())
        printer.process("scan-1")
        self.submit.assert_called_once()

    def test_save_submitting_failure_never_calls_external_queue(self):
        printer = self.printer()
        printer.enqueue(job())
        with patch.object(printer, "_save", side_effect=OSError("disk full")):
            printer.process("scan-1")
        self.submit.assert_not_called()
        self.assertTrue(printer.list()["diagnostics"])
        self.assertEqual(self.restart().get("scan-1")["status"], "saved")

    def test_receipt_save_failure_restart_unknown_no_resubmit(self):
        printer = self.printer()
        printer.enqueue(job())
        save = printer._save

        def fail_result(db, value):
            if value["status"] == "accepted":
                raise OSError("disk full after OS accepted")
            return save(db, value)

        with patch.object(printer, "_save", side_effect=fail_result):
            printer.process("scan-1")
        self.assertTrue(printer.list()["diagnostics"])
        restarted = self.restart()
        self.assertEqual(restarted.enqueue(job())["status"], "unknown")
        self.submit.assert_called_once()

    def test_reconcile_keeps_missing_unknown_and_restores_unique_receipt(self):
        printer = self.printer(
            submit=Mock(side_effect=RuntimeError("lost response")),
            observe=lambda _: {"matches": 0},
        )
        printer.enqueue(job())
        printer.process("scan-1")
        self.assertEqual(printer.reconcile("scan-1")["status"], "unknown")
        printer.observe = lambda _: {
            "matches": 2,
            "receipt": "printer-123",
            "status": "processing",
        }
        self.assertEqual(printer.reconcile("scan-1")["status"], "unknown")
        printer.observe = lambda _: {
            "matches": 1,
            "receipt": "printer-123",
            "status": "completed",
            "jobStateMessage": "forwarded",
        }
        result = printer.reconcile("scan-1")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["paperStatus"], "unconfirmed")
        self.assertFalse(result["physicalConfirmationSupported"])

    def test_repeated_observations_keep_history_bounded(self):
        printer = self.printer(observe=lambda _: {"error": "queue unreachable"})
        printer.enqueue(job())
        printer.process("scan-1")
        once = printer.reconcile("scan-1")
        for _ in range(20):
            last = printer.reconcile("scan-1")
        self.assertEqual(len(once["observations"]), len(last["observations"]))

    def test_reprint_links_exact_source_and_duplicate_delivery_is_idempotent(self):
        printer = self.printer(
            observe=lambda _: {
                "matches": 1,
                "receipt": "printer-123",
                "status": "canceled",
            }
        )
        printer.enqueue(job())
        printer.process("scan-1")
        printer.reconcile("scan-1")
        with self.assertRaises(ValueError):
            printer.reprint("scan-1", {"idempotencyKey": "child"})
        body = {"idempotencyKey": "child", "acknowledgeDuplicateRisk": True}
        child = printer.reprint("scan-1", body)
        printer.process("child")
        same = printer.reprint("scan-1", body)
        original = printer.get("scan-1")
        self.assertEqual(original["status"], "canceled")
        self.assertEqual(child["hash"], original["hash"])
        self.assertEqual(child["context"], original["context"])
        self.assertEqual(printer.image("child"), PNG)
        self.assertEqual(child["parentKey"], "scan-1")
        self.assertTrue(child["duplicateRiskAcknowledged"])
        self.assertEqual(same["receipt"], "printer-123")
        self.assertEqual(original["reprints"][0]["status"], "accepted")
        self.assertEqual(self.submit.call_count, 2)
        restarted = self.restart()
        self.assertEqual(
            restarted.get("scan-1")["reprints"][0]["idempotencyKey"], "child"
        )

    def test_original_retry_blocked_once_linked_reprint_exists(self):
        printer = self.printer(queue=lambda: "")
        printer.enqueue(job())
        printer.process("scan-1")
        printer.reprint(
            "scan-1", {"idempotencyKey": "child", "acknowledgeDuplicateRisk": True}
        )
        with self.assertRaises(ValueError):
            printer.retry("scan-1")

    def test_corrupt_entry_does_not_hide_other_history_or_permit_reprint(self):
        printer = self.printer()
        printer.enqueue(job("good"))
        printer.enqueue(job("bad"))
        with closing(printer.connect()) as db:
            db.execute("UPDATE jobs SET metadata='broken' WHERE id='bad'")
            db.commit()
        restarted = self.restart()
        self.assertEqual(
            [j["idempotencyKey"] for j in restarted.list()["jobs"]], ["good"]
        )
        self.assertTrue(restarted.list()["diagnostics"])
        with self.assertRaises(ValueError):
            restarted.enqueue(job("bad"))
        self.assertEqual(restarted.image("good"), PNG)
        self.submit.assert_not_called()

    def test_corrupt_database_preserved_with_readable_diagnostics(self):
        self.root.joinpath("direct-jobs.sqlite3").write_bytes(b"corrupt database")
        printer = self.printer()
        self.assertEqual(printer.list()["jobs"], [])
        self.assertTrue(printer.list()["diagnostics"])
        self.assertEqual(
            self.root.joinpath("direct-jobs.sqlite3").read_bytes(), b"corrupt database"
        )
        with self.assertRaises(Exception):
            printer.enqueue(job())
        self.submit.assert_not_called()

    def test_legacy_hash_variants_preserved_without_invented_size_or_new_submit(self):
        with closing(sqlite3.connect(self.root / "direct-jobs.sqlite3")) as db:
            db.execute(
                "CREATE TABLE jobs (id TEXT PRIMARY KEY, hash TEXT, receipt TEXT)"
            )
            for key, value in [("old3", PNG), ("old5", PNG + b"|58.0x40.0")]:
                db.execute(
                    "INSERT INTO jobs VALUES (?,?,?)",
                    (key, hashlib.sha256(value).hexdigest(), "printer-5"),
                )
            db.execute(
                "INSERT INTO jobs VALUES (?,?,NULL)",
                ("uncertain", hashlib.sha256(PNG).hexdigest()),
            )
            db.commit()
        printer = self.printer()
        for key in ("old3", "old5", "uncertain"):
            result = printer.enqueue(job(key))
            self.assertTrue(result["legacy"])
            self.assertFalse(result["imageAvailable"])
            self.assertNotIn("widthMm", result)
        self.assertEqual(printer.get("uncertain")["status"], "unknown")
        self.submit.assert_not_called()

    def test_parallel_same_key_submits_once_and_350_jobs_survive_one_failure(self):
        failure = "scan-175"

        def submit(data, value):
            self.assertEqual(data, PNG)
            if value["idempotencyKey"] == failure:
                raise RuntimeError("lost queue response")
            return f"printer-{int(value['idempotencyKey'].split('-')[-1]) + 1}"

        printer = self.printer(submit=Mock(side_effect=submit), auto_work=True)
        with ThreadPoolExecutor(max_workers=16) as threads:
            list(
                threads.map(
                    lambda i: printer.enqueue(job(f"scan-{i}")), list(range(350)) * 2
                )
            )
        printer.worker.shutdown(wait=True)
        result = printer.list()["jobs"]
        self.assertEqual(len(result), 350)
        self.assertEqual(printer.submit.call_count, 350)
        self.assertEqual(printer.get(failure)["status"], "unknown")
        self.assertEqual(sum(j["status"] == "accepted" for j in result), 349)
        restarted = self.restart()
        self.assertEqual(len(restarted.list()["jobs"]), 350)
        for i in range(350):
            self.assertEqual(restarted.image(f"scan-{i}"), PNG)

    def test_reads_do_not_wait_for_blocked_submit_and_repeated_key_does_not_resubmit(
        self,
    ):
        gate = threading.Event()
        submitted = threading.Event()

        def submit(data, value):
            submitted.set()
            gate.wait(2)
            return "printer-1"

        printer = self.printer(submit=Mock(side_effect=submit), auto_work=True)
        printer.enqueue(job())
        self.assertTrue(submitted.wait(1))
        started = time.monotonic()
        result = printer.get("scan-1")
        printer.enqueue(job("second"))
        printer.enqueue(job())
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(result["status"], "submitting")
        gate.set()
        printer.worker.shutdown(wait=True)
        self.assertEqual(printer.submit.call_count, 2)

    def test_process_crash_after_save_or_after_os_boundary(self):
        script = """
import json, os, sys
from pathlib import Path
from wms_print_direct import Printer
root=Path(sys.argv[1]); phase=sys.argv[2];body=json.loads(sys.argv[3])
def submit(data,job):
    with open(root/'external-receipt','w') as out:
        out.write('printer-91');out.flush();os.fsync(out.fileno())
    os._exit(71)
p=Printer(root,submit=submit,queue=lambda:'printer',auto_work=False)
p.enqueue(body)
if phase=='saved':os._exit(70)
p.process(body['idempotencyKey'])
"""
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent)}
        for phase in ("saved", "submitted"):
            root = self.root / phase
            result = subprocess.run(
                [sys.executable, "-c", script, str(root), phase, json.dumps(job())],
                env=env,
                timeout=10,
            )
            self.assertIn(result.returncode, (70, 71))
            submit = Mock(return_value="printer-92")
            with self.subTest(phase=phase):
                printer = Printer(
                    root,
                    submit=submit,
                    queue=lambda: "printer",
                    auto_work=False,
                    observe=lambda _: dict(
                        matches=1, receipt="printer-91", status="processing"
                    ),
                )
                try:
                    self.assertEqual(printer.image("scan-1"), PNG)
                    self.assertEqual(
                        printer.get("scan-1")["status"],
                        "saved" if phase == "saved" else "unknown",
                    )
                    if phase == "submitted":
                        self.assertEqual(
                            printer.reconcile("scan-1")["receipt"], "printer-91"
                        )
                        printer.enqueue(job())
                        submit.assert_not_called()
                    else:
                        printer.process("scan-1")
                        submit.assert_called_once()
                finally:
                    printer.close()

    def test_http_lost_response_and_history_without_default_printer(self):
        printer = self.printer(auto_work=True)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.printer = printer
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        address = f"http://127.0.0.1:{server.server_port}"
        req = Request(
            address + "/print",
            data=json.dumps(job("http/key")).encode(),
            headers={"X-WMS-Print": "1", "Content-Type": "application/json"},
        )
        with urlopen(req, timeout=3) as response:
            self.assertEqual(response.status, 202)
            # Deliberately discard the accepted response before client recovery.
        printer.worker.shutdown(wait=True)
        with urlopen(address + "/jobs/http%2Fkey", timeout=3) as response:
            result = json.load(response)
        self.assertEqual(result["receipt"], "printer-123")
        with urlopen(address + "/jobs/http%2Fkey/image", timeout=3) as response:
            self.assertEqual(response.read(), PNG)
        with urlopen(req, timeout=3):
            pass
        self.submit.assert_called_once()
        with urlopen(address + "/health") as response:
            self.assertEqual(json.load(response)["protocolVersion"], 2)

    def test_old_browser_gets_real_receipt_but_not_known_failure(self):
        printer = self.printer(
            auto_work=True,
            observe=lambda _: dict(matches=1, receipt="printer-123", status="canceled"),
        )
        result = printer.print(job())
        self.assertEqual(result["receipt"], "printer-123")
        printer.worker.shutdown(wait=True)
        printer.reconcile("scan-1")
        with self.assertRaises(RuntimeError):
            printer.print(job())
        self.submit.assert_called_once()

    @patch("wms_print_direct.sys.argv", ["WMS Print"])
    @patch("wms_print_direct.threading.Thread")
    @patch("wms_print_direct.subprocess.Popen")
    @patch("wms_print_direct.subprocess.run")
    @patch("wms_print_direct.Printer")
    @patch("wms_print_direct.ThreadingHTTPServer")
    def test_start_and_reopen_never_launch_browser(
        self, server, printer, run, popen, thread
    ):
        main()
        server.return_value.serve_forever.assert_called_once()
        server.side_effect = OSError("already running")
        main()
        run.assert_not_called()
        popen.assert_not_called()

    @patch("wms_print_direct.sys.platform", "darwin")
    @patch("wms_print_direct.subprocess.run")
    def test_macos_default_uses_stable_locale(self, run):
        run.return_value.stdout = "system default destination: Label_Printer\n"
        self.assertEqual(default_printer(), "Label_Printer")
        self.assertEqual(run.call_args.kwargs["env"]["LC_ALL"], "C")

    def test_missing_child_metadata_keeps_parent_and_same_child_protected(self):
        printer = self.printer(queue=lambda: "")
        printer.enqueue(job())
        printer.process("scan-1")
        printer.queue = lambda: "printer"
        body = {"idempotencyKey": "child", "acknowledgeDuplicateRisk": True}
        printer.reprint("scan-1", body)
        printer.process("child")
        self.submit.assert_called_once()
        with closing(printer.connect()) as db:
            db.execute("DELETE FROM jobs WHERE id='child'")
            db.commit()
        printer = self.restart()
        source = printer.get("scan-1")
        self.assertEqual(source["status"], "failed_before_submit")
        self.assertEqual(source["reprints"][0]["status"], "unknown")
        self.assertNotIn("receipt", source["reprints"][0])
        with self.assertRaises(ValueError):
            printer.retry("scan-1")
        with self.assertRaisesRegex(ValueError, "утрачено"):
            printer.reprint("scan-1", body)
        with self.assertRaisesRegex(ValueError, "утрачено"):
            printer.enqueue(job("child"))
        self.submit.assert_called_once()

    def test_stale_observation_cannot_erase_reprint_intent_even_with_equal_timestamp(
        self,
    ):
        entered, release = threading.Event(), threading.Event()

        def observe(value):
            entered.set()
            release.wait(3)
            return dict(matches=1, receipt="printer-123", status="canceled")

        printer = self.printer(observe=observe)
        printer.enqueue(job())
        printer.process("scan-1")
        fixed = printer.get("scan-1")["updatedAt"]
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(printer.reconcile, "scan-1")
            self.assertTrue(entered.wait(1))
            with patch("wms_print_direct.timestamp", return_value=fixed):
                printer.reprint(
                    "scan-1",
                    dict(idempotencyKey="child", acknowledgeDuplicateRisk=True),
                )
            release.set()
            pending.result(timeout=2)
        original = printer.get("scan-1")
        self.assertEqual(original["reprintIntentKeys"], ["child"])
        self.assertEqual(original["status"], "accepted")

    def test_windows_boundary_classifies_errors_by_phase_not_python_exception_type(
        self,
    ):
        printer = self.printer()
        printer.enqueue(job())
        with closing(printer.connect()) as db:
            stored = printer._read(db, "scan-1")
            stored.update(status="submitting", queue="printer")
            printer._save(db, stored)
        for phase in (
            "prepare",
            "validate",
            "StartDoc",
            "StartPage",
            "EndDoc",
            "cleanup",
        ):
            for error_type in (OSError, ValueError):
                with self.subTest(phase=phase, error_type=error_type):
                    image = Mock(width=2, height=2)
                    image.convert.return_value = image
                    dc = Mock()
                    dc.GetDeviceCaps.return_value = 100
                    dc.StartDoc.return_value = 17
                    adapter = object.__new__(DefaultWindowsAdapter)
                    adapter.modules = {
                        "Image": Mock(open=Mock(return_value=image)),
                        "ImageWin": Mock(),
                    }
                    adapter._create_sized_printer_dc = Mock(return_value=dc)
                    adapter._validate_page_size = Mock()
                    if phase == "prepare":
                        adapter._create_sized_printer_dc.side_effect = error_type(
                            "before StartDoc"
                        )
                    elif phase == "validate":
                        adapter._validate_page_size.side_effect = error_type(
                            "before StartDoc"
                        )
                    elif phase == "cleanup":
                        dc.DeleteDC.side_effect = error_type("cleanup")
                    else:
                        getattr(dc, phase).side_effect = error_type(
                            "after entering StartDoc"
                        )
                    with (
                        patch(
                            "wms_print_direct.DefaultWindowsAdapter",
                            return_value=adapter,
                        ),
                        patch("wms_print_direct.sys.platform", "win32"),
                    ):
                        result = native_operation(
                            ["--submit-job", str(printer.db), "scan-1"]
                        )
                    if phase in ("prepare", "validate"):
                        self.assertTrue(result["beforeSubmit"])
                        dc.StartDoc.assert_not_called()
                    elif phase == "cleanup":
                        self.assertEqual(result["receipt"], "windows-17")
                    else:
                        self.assertFalse(result["beforeSubmit"])

    def test_windows_observes_unique_title_and_real_queue_flags(self):
        handle = object()
        native = SimpleNamespace(
            OpenPrinter=Mock(return_value=handle),
            ClosePrinter=Mock(),
            GetPrinter=Mock(return_value={"Status": 128}),
            EnumJobs=Mock(
                return_value=[
                    dict(
                        JobId=25, pDocument="WMS-title", Status=64, pStatus="paper out"
                    )
                ]
            ),
        )
        with patch.dict(sys.modules, {"win32print": native}):
            value = observe_windows(dict(queue="default", title="WMS-title"))
            self.assertEqual(value["status"], "stopped")
            self.assertEqual(value["receipt"], "windows-25")
            native.EnumJobs.return_value *= 2
            self.assertEqual(
                observe_windows(dict(queue="default", title="WMS-title"))["matches"], 2
            )
        self.assertFalse(value["physicalConfirmationSupported"])

    def test_windows_health_and_print_resolve_the_system_default_printer(self):
        win32print = SimpleNamespace(
            GetDefaultPrinter=Mock(return_value="Xprinter XP-420B")
        )
        with (
            patch("wms_print_direct.sys.platform", "win32"),
            patch.dict(sys.modules, {"win32print": win32print}),
        ):
            self.assertEqual(default_printer(), "Xprinter XP-420B")
        win32print.GetDefaultPrinter.assert_called_once_with()

    def test_windows_custom_size_is_applied_to_one_job_devmode(self):
        calls = []

        class FakePrint:
            @staticmethod
            def OpenPrinter(queue):
                calls.append(("open", queue))
                return queue

            @staticmethod
            def GetPrinter(handle, level):
                self.assertEqual(level, 2)
                return {
                    "pDevMode": SimpleNamespace(
                        PaperSize=9,
                        PaperWidth=2100,
                        PaperLength=2970,
                        Copies=2,
                        Collate=1,
                        Fields=0x00000002,
                    )
                }

            @staticmethod
            def DocumentProperties(hwnd, handle, queue, output, input_, mode):
                calls.append(
                    (
                        "devmode",
                        output.PaperSize,
                        output.PaperWidth,
                        output.PaperLength,
                        output.Copies,
                        output.Fields,
                    )
                )
                return 1

            @staticmethod
            def ClosePrinter(handle):
                calls.append(("close", handle))

        class FakeDc:
            def GetDeviceCaps(self, index):
                return {
                    8: 464,
                    10: 320,
                    88: 203,
                    90: 203,
                    110: 464,
                    111: 320,
                    112: 0,
                    113: 0,
                }[index]

            def StartDoc(self, title):
                calls.append(("start-doc", title))
                return 607

            def StartPage(self):
                calls.append(("start-page",))

            def GetHandleOutput(self):
                return 17

            def EndPage(self):
                calls.append(("end-page",))

            def EndDoc(self):
                calls.append(("end-doc",))

            def AbortDoc(self):
                calls.append(("abort",))

            def DeleteDC(self):
                calls.append(("delete-dc",))

        class FakeImage:
            width = 464
            height = 320

            def convert(self, mode):
                self.mode = mode
                return self

        class FakeDib:
            def __init__(self, image):
                self.image = image

            def draw(self, handle, target):
                calls.append(("draw", handle, target))

        adapter = DefaultWindowsAdapter(
            {
                "win32print": FakePrint,
                "win32gui": SimpleNamespace(CreateDC=lambda driver, queue, devmode: 17),
                "win32ui": SimpleNamespace(CreateDCFromHandle=lambda handle: FakeDc()),
                "Image": SimpleNamespace(open=lambda stream: FakeImage()),
                "ImageWin": SimpleNamespace(Dib=FakeDib),
                "fitz": None,
            }
        )

        self.assertEqual(
            adapter.submit_default(PNG, "Xprinter XP-420B", 58, 40),
            "windows-607",
        )
        devmode = next(call for call in calls if call[0] == "devmode")
        self.assertEqual(devmode[1:5], (0, 580, 400, 1))
        self.assertEqual(devmode[5] & 0x00000002, 0)
        self.assertEqual(
            devmode[5] & (0x00000004 | 0x00000008 | 0x00000100),
            0x00000004 | 0x00000008 | 0x00000100,
        )
        self.assertIn(("draw", 17, (0, 0, 464, 320)), calls)
        self.assertNotIn(("abort",), calls)


if __name__ == "__main__":
    unittest.main()
