"""WMS-762: the same flows on a real Windows with the real pywin32.

Only runs on Windows with the built-in "Microsoft Print to PDF" queue (a
GitHub windows runner has it).  The queue writes a file instead of showing a
dialog when StartDoc is given an output path, so the proxy below only adds that
path; every other GDI call is the real one.
"""

import base64
import io
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

QUEUE = "Microsoft Print to PDF"


def available():
    if sys.platform != "win32":
        return False
    try:
        import win32print
    except ImportError:
        return False
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return QUEUE in [record[2] for record in win32print.EnumPrinters(flags)]


def png():
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (232, 160), "black").save(buffer, "PNG")
    return buffer.getvalue()


def wait_size(path):
    for _ in range(100):
        if path.exists() and path.stat().st_size > 0:
            return path.stat().st_size
        time.sleep(0.2)
    return -1


@unittest.skipUnless(available(), "needs Windows with Microsoft Print to PDF")
class RealWindowsPrintTest(unittest.TestCase):
    def test_real_startdoc_returns_none_not_a_job_number(self):
        import win32ui

        with tempfile.TemporaryDirectory() as root:
            dc = win32ui.CreateDC()
            dc.CreatePrinterDC(QUEUE)
            try:
                self.assertIsNone(dc.StartDoc("WMS-762", str(Path(root) / "a.pdf")))
                dc.StartPage()
                dc.EndPage()
                dc.EndDoc()
            finally:
                dc.DeleteDC()

    def test_agent_prints_label_to_pdf_with_nonempty_receipt(self):
        from wms_print_direct import DefaultWindowsAdapter, Printer

        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "label.pdf"
            adapter = DefaultWindowsAdapter()
            create = adapter._create_printer_dc

            class ToFile:
                def __init__(self, dc):
                    self.dc = dc

                def StartDoc(self, name):
                    return self.dc.StartDoc(name, str(target))

                def __getattr__(self, name):
                    return getattr(self.dc, name)

            adapter._create_printer_dc = lambda queue: ToFile(create(queue))
            job = {
                "idempotencyKey": "wms762-real",
                "imageDataUrl": "data:image/png;base64," + base64.b64encode(png()).decode(),
            }
            printer = Printer(Path(root), lambda data: adapter.submit_default(data, QUEUE))
            receipt = printer.print(job)
            self.assertTrue(receipt.strip())
            self.assertGreater(wait_size(target), 0)
            self.assertEqual(target.read_bytes()[:4], b"%PDF")


if __name__ == "__main__":
    unittest.main()
