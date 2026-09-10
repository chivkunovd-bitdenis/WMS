import subprocess
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from wms_print_agent import UnknownPrintOutcome, submit_to_cups, validate_job


class PrintAgentTest(unittest.TestCase):
    def job(self):
        return {
            "id": str(uuid.uuid4()),
            "job_type": "fbs_network_print",
            "status": "running",
            "payload_json": {
                "asset_id": str(uuid.uuid4()),
                "queue": "Warehouse_58",
                "copies": 2,
                "checksum": "a" * 64,
                "content_type": "application/pdf",
            },
        }

    def test_only_claimed_job_for_configured_queue(self):
        job = self.job()
        self.assertEqual(validate_job(job, "Warehouse_58")["copies"], 2)
        job["payload_json"]["checksum"] = "sha256:" + "a" * 64
        self.assertEqual(validate_job(job, "Warehouse_58")["checksum"], "a" * 64)
        for field, value in [
            ("queue", "other"),
            ("copies", True),
            ("copies", 0),
            ("content_type", "text/html"),
            ("checksum", "bad"),
        ]:
            changed = self.job()
            changed["payload_json"][field] = value
            with self.assertRaises(ValueError):
                validate_job(changed, "Warehouse_58")
        job["status"] = "pending"
        with self.assertRaises(ValueError):
            validate_job(job, "Warehouse_58")

    def test_receipt_means_spooled_and_temp_file_is_removed(self):
        paths = []

        def run(args, **kwargs):
            self.assertEqual(args[:6], ["lp", "-d", "Warehouse_58", "-n", "2", "--"])
            self.assertNotIn("shell", kwargs)
            paths.append(Path(args[-1]))
            self.assertEqual(paths[0].read_bytes(), b"%PDF-test")
            return SimpleNamespace(
                returncode=0, stdout="request id is Warehouse_58-42 (1 file(s))"
            )

        result = submit_to_cups(
            b"%PDF-test", self.job()["payload_json"], "Warehouse_58", run
        )
        self.assertEqual(result["stage"], "spooled")
        self.assertEqual(result["receipt"], "Warehouse_58-42")
        self.assertFalse(paths[0].exists())

    def test_timeout_or_unconfirmed_result_never_retries(self):
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            raise subprocess.TimeoutExpired(args, 60)

        with self.assertRaises(UnknownPrintOutcome):
            submit_to_cups(
                b"%PDF-test", self.job()["payload_json"], "Warehouse_58", run
            )
        self.assertEqual(len(calls), 1)
        with self.assertRaises(UnknownPrintOutcome):
            submit_to_cups(
                b"%PDF-test",
                self.job()["payload_json"],
                "Warehouse_58",
                lambda *a, **kw: SimpleNamespace(returncode=1, stdout=""),
            )


if __name__ == "__main__":
    unittest.main()
