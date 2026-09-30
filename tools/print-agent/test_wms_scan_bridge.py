"""Real loopback HTTP and durable receipts, with no physical printer involved."""

import base64
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from types import SimpleNamespace

import fitz
from PIL import Image
import wms_scan_bridge as bridge
import wms_print_agent as agent


class Adapter:
    def __init__(self):
        self.jobs = []
        self.fail = False

    def queues(self):
        return ["WMS604_Test"]

    def submit(self, data, mime, queue, copies, width_mm, height_mm):
        self.jobs.append((data, mime, queue, copies, width_mm, height_mm))
        if self.fail:
            raise agent.UnknownPrintOutcome("timeout after submit")
        return "WMS604_Test-7"


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.adapter = Adapter()
        self.bridge = bridge.PrinterBridge(self.directory, "WMS604_Test", self.adapter)
        png = io.BytesIO()
        Image.new("RGB", (64, 64), "black").save(png, "PNG")
        self.payload = dict(
            job_id=str(uuid.uuid4()),
            image_data_url="data:image/png;base64,"
            + base64.b64encode(png.getvalue()).decode(),
            width_mm=58,
            height_mm=40,
        )

    def tearDown(self):
        self.bridge.db.close()
        self.temp.cleanup()

    def test_pdf_has_exact_size_lossless_image_and_fixed_queue(self):
        receipt = self.bridge.print_image(self.payload)
        self.assertEqual(receipt["receipt"], "WMS604_Test-7")
        data, mime, queue, copies, width, height = self.adapter.jobs[0]
        self.assertEqual(
            (mime, queue, copies, width, height),
            ("application/pdf", "WMS604_Test", 1, 58, 40),
        )
        with fitz.open(stream=data, filetype="pdf") as document:
            self.assertAlmostEqual(document[0].rect.width * 25.4 / 72, 58, places=3)
            self.assertAlmostEqual(document[0].rect.height * 25.4 / 72, 40, places=3)
            self.assertNotIn(b"/DCTDecode", data)

    def test_duplicate_after_restart_never_submits_again(self):
        first = self.bridge.print_image(self.payload)
        self.bridge.db.close()
        self.bridge = bridge.PrinterBridge(self.directory, "WMS604_Test", self.adapter)
        self.assertEqual(self.bridge.print_image(self.payload), first)
        self.assertEqual(len(self.adapter.jobs), 1)
        with self.assertRaises(bridge.BridgeError):
            self.bridge.print_image({**self.payload, "width_mm": 60})
        self.assertEqual(len(self.adapter.jobs), 1)

    def test_unknown_receipt_not_retried_after_restart(self):
        self.adapter.fail = True
        with self.assertRaises(bridge.BridgeError):
            self.bridge.print_image(self.payload)
        self.bridge.db.close()
        self.bridge = bridge.PrinterBridge(self.directory, "WMS604_Test", self.adapter)
        with self.assertRaisesRegex(bridge.BridgeError, "предыдущей"):
            self.bridge.print_image(self.payload)
        self.assertEqual(len(self.adapter.jobs), 1)

    def test_parallel_duplicate_submits_only_once(self):
        threads = [
            threading.Thread(target=self.bridge.print_image, args=(self.payload,))
            for _ in range(5)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(self.adapter.jobs), 1)

    def test_input_cannot_choose_queue_file_url_or_bad_image(self):
        cases = [
            dict(queue="another"),
            dict(image_data_url="https://example.com/x.png"),
            dict(image_data_url="data:image/png;base64,bm90cG5n"),
            dict(job_id="../../x"),
            dict(width_mm=59),
            dict(width_mm=True),
        ]
        for update in cases:
            with self.subTest(update=update), self.assertRaises(bridge.BridgeError):
                self.bridge.print_image({**self.payload, **update})
        self.assertEqual(self.adapter.jobs, [])

    def test_real_http_origin_host_preflight_and_submission(self):
        server = bridge.make_server(self.bridge, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def request(method, headers, body=None, path="/print-image"):
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            result = (response.status, dict(response.getheaders()), response.read())
            connection.close()
            return result

        try:
            headers = {
                "Origin": "https://sellerfocus.pro",
                "Content-Type": "application/json",
            }
            for origin in ("https://evil.example", "null", ""):
                self.assertEqual(
                    request(
                        "POST", {**headers, "Origin": origin}, json.dumps(self.payload)
                    )[0],
                    403,
                )
            self.assertEqual(
                request(
                    "POST",
                    {**headers, "Host": "evil.example"},
                    json.dumps(self.payload),
                )[0],
                403,
            )
            self.assertEqual(
                request(
                    "POST",
                    {**headers, "Content-Type": "text/plain"},
                    json.dumps(self.payload),
                )[0],
                400,
            )
            status, cors, _ = request(
                "OPTIONS",
                {
                    "Origin": headers["Origin"],
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                    "Access-Control-Request-Private-Network": "true",
                },
            )
            self.assertEqual(status, 204)
            self.assertEqual(cors["Access-Control-Allow-Origin"], headers["Origin"])
            self.assertEqual(cors["Access-Control-Allow-Private-Network"], "true")
            status, _, data = request("POST", headers, json.dumps(self.payload))
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data)["receipt"], "WMS604_Test-7")
            self.assertEqual(len(self.adapter.jobs), 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_localized_native_discovery_and_receipt(self):
        commands = []

        def run(command, **_kwargs):
            commands.append(command)
            return SimpleNamespace(
                returncode=0,
                stdout="WMS604_Test принимает запросы с момента сегодня\n"
                if command[0].endswith("lpstat")
                else "id запроса WMS604_Test-10 (файлов 1)",
            )

        adapter = bridge.SizedCupsAdapter(run=run, platform="darwin")
        self.assertEqual(adapter.queues(), ["WMS604_Test"])
        self.assertEqual(
            adapter.submit(b"%PDF-test", "application/pdf", "WMS604_Test", 1, 58, 40),
            "WMS604_Test-10",
        )
        self.assertIn("media=Custom.58x40mm", commands[-1])
        self.assertEqual(commands[0], ["/usr/bin/lpstat", "-a"])

    def test_multiple_or_other_queue_receipts_are_unknown(self):
        for output in ("id запроса Other-10", "WMS604_Test-10 WMS604_Test-11"):
            with self.assertRaises(agent.UnknownPrintOutcome):
                agent.submit_to_queue(
                    b"%PDF",
                    "application/pdf",
                    "WMS604_Test",
                    run=lambda *_a, **_kw: SimpleNamespace(returncode=0, stdout=output),
                )


if __name__ == "__main__":
    unittest.main()
