import subprocess
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from wms_print_agent import (
    UnknownPrintOutcome,
    check_base_url,
    check_queue,
    submit_to_queue,
    validate_job,
)

WAREHOUSE_ID = str(uuid.uuid4())


class PrintAgentTest(unittest.TestCase):
    def job(self):
        return {
            "id": str(uuid.uuid4()),
            "status": "running",
            "warehouse_id": WAREHOUSE_ID,
            "asset_id": str(uuid.uuid4()),
            "content_type": "application/pdf",
            "checksum": "a" * 64,
        }

    def test_only_claimed_job_of_this_warehouse_is_accepted(self):
        job = self.job()
        self.assertEqual(validate_job(job, WAREHOUSE_ID)["checksum"], "a" * 64)
        job["checksum"] = "sha256:" + "a" * 64
        self.assertEqual(validate_job(job, WAREHOUSE_ID)["checksum"], "a" * 64)
        for field, value in [
            ("status", "pending"),
            ("status", "done"),
            ("warehouse_id", str(uuid.uuid4())),
            ("content_type", "text/html"),
            ("checksum", "bad"),
        ]:
            changed = self.job()
            changed[field] = value
            with self.assertRaises(ValueError):
                validate_job(changed, WAREHOUSE_ID)

    def test_configuration_is_checked_before_any_call(self):
        self.assertEqual(check_base_url("https://wms.example/"), "https://wms.example")
        for bad in [
            "http://wms.example",
            "https://u:p@wms.example",
            "https://wms.example?a=1",
        ]:
            with self.assertRaises(ValueError):
                check_base_url(bad)
        self.assertEqual(check_queue("Warehouse_58"), "Warehouse_58")
        for bad in ["-d", "queue name", ""]:
            with self.assertRaises(ValueError):
                check_queue(bad)

    def test_receipt_means_spooled_and_temp_file_is_removed(self):
        paths = []

        def run(args, **kwargs):
            self.assertEqual(args[:4], ["lp", "-d", "Warehouse_58", "--"])
            self.assertNotIn("shell", kwargs)
            paths.append(Path(args[-1]))
            self.assertEqual(paths[0].read_bytes(), b"%PDF-test")
            return SimpleNamespace(
                returncode=0, stdout="request id is Warehouse_58-42 (1 file(s))"
            )

        receipt = submit_to_queue(b"%PDF-test", "application/pdf", "Warehouse_58", run)
        self.assertEqual(receipt, "Warehouse_58-42")
        self.assertFalse(paths[0].exists())

    def test_timeout_or_unconfirmed_result_never_retries(self):
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            raise subprocess.TimeoutExpired(args, 60)

        with self.assertRaises(UnknownPrintOutcome):
            submit_to_queue(b"%PDF-test", "application/pdf", "Warehouse_58", run)
        self.assertEqual(len(calls), 1)
        with self.assertRaises(UnknownPrintOutcome):
            submit_to_queue(
                b"%PDF-test",
                "application/pdf",
                "Warehouse_58",
                lambda *a, **kw: SimpleNamespace(returncode=1, stdout=""),
            )


if __name__ == "__main__":
    unittest.main()
