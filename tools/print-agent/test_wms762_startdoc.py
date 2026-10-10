"""WMS-762: Windows StartDoc does not return a spooler job number.

Real pywin32 (win32ui PyCDC.StartDoc) returns None on success and raises on
failure; this was observed on GitHub windows-latest / windows-2022 (see
docs/requirements/WMS-762.md).  A fake that returns an int hides that, so every
fake here is configurable and the main cases use None, like the real library.
"""

import base64
import io
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import wms_print_agent as agent
import wms_print_runtime as runtime
from wms_print_direct import DefaultWindowsAdapter, Printer

PNG = b"\x89PNG\r\n\x1a\nsynthetic"
RAISE = object()


class FakeDc:
    """Records GDI calls.  ``start_doc`` is the value StartDoc returns (or RAISE)."""

    def __init__(self, calls, start_doc, fail_at=None):
        self.calls = calls
        self.start_doc = start_doc
        self.fail_at = fail_at

    def _call(self, name):
        self.calls.append(name)
        if self.fail_at == name:
            raise RuntimeError(name + " failed")

    def StartDoc(self, name):
        self.calls.append("StartDoc")
        if self.start_doc is RAISE:
            raise RuntimeError("StartDoc failed")
        return self.start_doc

    def GetDeviceCaps(self, index):
        return {8: 464, 10: 320, 88: 203, 90: 203, 110: 464, 111: 320, 112: 0, 113: 0}[index]

    def StartPage(self):
        self._call("StartPage")

    def GetHandleOutput(self):
        return 17

    def EndPage(self):
        self._call("EndPage")

    def EndDoc(self):
        self._call("EndDoc")

    def AbortDoc(self):
        self.calls.append("AbortDoc")

    def DeleteDC(self):
        self.calls.append("DeleteDC")


class FakeImage:
    width = 464
    height = 320
    info = {"dpi": (203, 203)}

    def convert(self, mode):
        return self


def modules(calls):
    class ImageModule:
        @staticmethod
        def open(stream):
            assert isinstance(stream, io.BytesIO)
            return FakeImage()

    class ImageWin:
        class Dib:
            def __init__(self, image):
                pass

            def draw(self, handle, target):
                calls.append("draw")

    return {"Image": ImageModule, "ImageWin": ImageWin}


class DirectAdapter(DefaultWindowsAdapter):
    def __init__(self, calls, start_doc, fail_at=None):
        super().__init__(modules(calls))
        self.dc = FakeDc(calls, start_doc, fail_at)

    def _create_printer_dc(self, queue):
        return self.dc


class RuntimeAdapter(runtime.WindowsAdapter):
    def __init__(self, calls, start_doc, fail_at=None):
        super().__init__(modules(calls))
        self.dc = FakeDc(calls, start_doc, fail_at)

    def queues(self):
        return ["Queue"]

    def _create_printer_dc(self, queue):
        return self.dc


def direct(start_doc, fail_at=None):
    calls = []
    adapter = DirectAdapter(calls, start_doc, fail_at)
    return calls, lambda: adapter.submit_default(PNG, "Queue")


def runtime_submit(start_doc, fail_at=None):
    calls = []
    adapter = RuntimeAdapter(calls, start_doc, fail_at)
    return calls, lambda: adapter.submit(PNG, "image/png", "Queue", 1, 58, 40)


FLOWS = {"direct": direct, "runtime": runtime_submit}


class StartDocWithoutJobNumberTest(unittest.TestCase):
    def for_each_flow(self, check):
        for name, make in FLOWS.items():
            with self.subTest(flow=name):
                check(make)

    def test_none_from_startdoc_is_success_with_nonempty_receipt(self):
        def check(make):
            calls, submit = make(None)
            receipt = submit()
            self.assertIsInstance(receipt, str)
            self.assertTrue(receipt.strip())
            self.assertTrue(receipt.startswith("windows-"))
            self.assertEqual(
                [c for c in calls if c in {"StartDoc", "StartPage", "draw", "EndPage", "EndDoc", "AbortDoc", "DeleteDC"}],
                ["StartDoc", "StartPage", "draw", "EndPage", "EndDoc", "DeleteDC"],
            )

        self.for_each_flow(check)

    def test_positive_job_number_is_used_when_driver_returns_one(self):
        self.for_each_flow(lambda make: self.assertEqual(make(442)[1](), "windows-442"))

    def test_two_prints_without_job_number_get_distinct_receipts(self):
        self.for_each_flow(lambda make: self.assertNotEqual(make(None)[1](), make(None)[1]()))

    def test_unusable_startdoc_value_is_error_and_document_is_aborted(self):
        def check(make):
            for bad in (0, -1, "abc"):
                calls, submit = make(bad)
                with self.assertRaises(agent.UnknownPrintOutcome):
                    submit()
                self.assertIn("AbortDoc", calls)
                self.assertNotIn("StartPage", calls)
                self.assertEqual(calls[-1], "DeleteDC")

        self.for_each_flow(check)

    def test_startdoc_exception_is_clear_error_without_page_and_with_cleanup(self):
        def check(make):
            calls, submit = make(RAISE)
            with self.assertRaises(agent.UnknownPrintOutcome) as caught:
                submit()
            self.assertIn("Windows", str(caught.exception))
            self.assertNotIn("StartPage", calls)
            self.assertNotIn("EndDoc", calls)
            self.assertEqual(calls[-1], "DeleteDC")

        self.for_each_flow(check)

    def test_failure_after_startdoc_without_number_still_aborts_document(self):
        def check(make):
            for stage in ("StartPage", "EndPage", "EndDoc"):
                calls, submit = make(None, stage)
                with self.assertRaises(agent.UnknownPrintOutcome):
                    submit()
                self.assertIn("AbortDoc", calls)
                self.assertEqual(calls[-1], "DeleteDC")

        self.for_each_flow(check)


class DirectPrinterReceiptTest(unittest.TestCase):
    def test_label_print_through_agent_stores_and_returns_nonempty_receipt(self):
        calls = []
        adapter = DirectAdapter(calls, None)
        job = {
            "idempotencyKey": "scan-762",
            "imageDataUrl": "data:image/png;base64," + base64.b64encode(PNG).decode(),
        }
        with tempfile.TemporaryDirectory() as root:
            printer = Printer(Path(root), lambda data: adapter.submit_default(data, "Queue"))
            receipt = printer.print(job)
            self.assertTrue(receipt)
            self.assertEqual(printer.print(job), receipt)
            with closing(sqlite3.connect(Path(root) / "direct-jobs.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT receipt FROM jobs").fetchall(), [(receipt,)])
        self.assertEqual(calls.count("StartDoc"), 1)


if __name__ == "__main__":
    unittest.main()
