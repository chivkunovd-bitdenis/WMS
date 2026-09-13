"""Safe native queue substitute and crash/restart proof; never touches a real printer."""

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import wms_print_agent as agent
import wms_print_runtime as runtime


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.config = {
            "connection_id": str(uuid.uuid4()),
            "warehouse_id": str(uuid.uuid4()),
            "queue_name": "Synthetic_442",
        }
        self.content = b"%PDF-synthetic-no-printer"
        self.job = {
            **self.config,
            "id": str(uuid.uuid4()),
            "claim_id": str(uuid.uuid4()),
            "asset_id": str(uuid.uuid4()),
            "status": "running",
            "copies": 3,
            "content_type": "application/pdf",
            "content_bytes": len(self.content),
            "checksum": hashlib.sha256(self.content).hexdigest(),
        }
        self.submissions = []
        self.acks = []
        self.queue = [self.job]
        owner = self

        class Client:
            fail_ack = False

            def api(self, path, body=None):
                if path == "/agent/next":
                    return {"job": owner.queue.pop(0) if owner.queue else None}
                if self.fail_ack:
                    raise OSError("synthetic lost response")
                owner.acks.append(body)
                return {}

            def fetch(self, job, expected):
                return owner.content

        class Adapter:
            def queues(self):
                return [owner.config["queue_name"]]

            def submit(self, data, mime, queue, copies):
                owner.submissions.append((data, mime, queue, copies))
                return "Synthetic_442-17"

        self.client, self.adapter = Client(), Adapter()

    def tearDown(self):
        self.temp.cleanup()

    def run_once(self):
        return runtime.process_once(
            self.config, self.directory, self.client, self.adapter
        )

    def test_queue_acceptance_lost_ack_restart_only_replays_receipt(self):
        self.client.fail_ack = True
        with self.assertRaises(OSError):
            self.run_once()
        self.assertEqual(len(self.submissions), 1)
        marker = json.loads((self.directory / "inflight.json").read_text())
        self.assertEqual(marker["result"]["queue_receipt"], "Synthetic_442-17")
        self.client.fail_ack = False
        self.assertIn("повторной передачи", self.run_once())
        self.assertEqual(len(self.submissions), 1)
        self.assertEqual(self.submissions[0][-1], 3)
        self.assertEqual(self.acks[0]["queue_receipt"], "Synthetic_442-17")
        self.assertFalse((self.directory / "inflight.json").exists())

    def test_crash_after_os_acceptance_before_receipt_persistence_never_resubmits(self):
        original = runtime.write_private

        def save(path, value):
            if value.get("phase") == "result":
                raise OSError("synthetic disk failure after OS accepted")
            original(path, value)

        with patch.object(runtime, "write_private", save), self.assertRaises(OSError):
            self.run_once()
        self.assertEqual(len(self.submissions), 1)
        self.assertIn("неизвестен", self.run_once())
        self.assertEqual(self.acks, [])
        self.assertEqual(self.run_once(), "")
        self.assertEqual(len(self.submissions), 1)

    def test_unknown_native_response_never_reports_false_failure(self):
        def unknown(*args):
            self.submissions.append(args)
            raise agent.UnknownPrintOutcome()

        self.adapter.submit = unknown
        self.assertIn("неизвестен", self.run_once())
        self.assertIn("неизвестен", self.run_once())
        self.assertEqual(len(self.submissions), 1)
        self.assertEqual(self.acks, [])

    def test_destination_and_size_mismatch_are_rejected_before_native_call(self):
        self.job["queue_name"] = "Another"
        self.assertIn("Не передано", self.run_once())
        self.assertEqual(self.submissions, [])
        self.assertFalse(self.acks[0]["handed_to_queue"])

    def test_two_instances_have_exclusive_profile_lock(self):
        with runtime.single_instance(self.directory):
            result = subprocess.run(
                [
                    os.sys.executable,
                    "-c",
                    (
                        "import sys; from pathlib import Path; "
                        "from wms_print_runtime import single_instance; "
                        "single_instance(Path(sys.argv[1])).__enter__()"
                    ),
                    str(self.directory),
                ],
                cwd=Path(__file__).parent,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("уже запущена", result.stderr)

    def test_private_state_survives_new_reader_and_is_not_world_readable(self):
        path = self.directory / "connection.json"
        runtime.write_private(path, {"fixture": "local synthetic value"})
        self.assertEqual(
            runtime.read_private(path), {"fixture": "local synthetic value"}
        )
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_native_adapter_exact_fixed_command_copies_and_receipt(self):
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            self.assertNotIn("shell", kwargs)
            if args[0] == "/usr/bin/lpstat":
                return SimpleNamespace(
                    returncode=0, stdout="printer Synthetic_442 is idle\n"
                )
            self.assertEqual(
                args[:6], ["/usr/bin/lp", "-d", "Synthetic_442", "-n", "3", "--"]
            )
            self.assertEqual(Path(args[-1]).read_bytes(), self.content)
            return SimpleNamespace(
                returncode=0, stdout="request id is Synthetic_442-72 (1 file(s))"
            )

        adapter = runtime.CupsAdapter(run=run, platform="darwin")
        self.assertEqual(
            adapter.submit(self.content, "application/pdf", "Synthetic_442", 3),
            "Synthetic_442-72",
        )
        self.assertEqual(len(calls), 2)
        with self.assertRaises(ValueError):
            runtime.CupsAdapter(platform="win32")

    def test_safe_synthetic_queue_runs_real_child_process_once(self):
        # Real subprocess/spooler boundary with a local synthetic queue executable.
        # No lp, OS queue, USB device or network printer can be reached here.
        executable = self.directory / "synthetic-spooler"
        spool = self.directory / "accepted.bin"
        executable.write_text(
            '#!/bin/sh\ncat "$4" > "' + str(spool) + '"\n'
            "echo 'request id is Synthetic_442-1 (1 file(s))'\n"
        )
        executable.chmod(0o700)
        receipt = agent.submit_to_queue(
            self.content, "application/pdf", "Synthetic_442", executable=str(executable)
        )
        self.assertEqual(receipt, "Synthetic_442-1")
        self.assertEqual(spool.read_bytes(), self.content)

    def test_actual_process_exit_after_spool_acceptance_recovers_without_second_submit(
        self,
    ):
        spooler = self.directory / "synthetic-spooler"
        accepted = self.directory / "accepted.txt"
        spooler.write_text(
            '#!/bin/sh\necho accepted >> "'
            + str(accepted)
            + '"\necho "request id is Synthetic_442-1 (1 file(s))"\n'
        )
        spooler.chmod(0o700)
        script = (
            "import os,sys; from pathlib import Path; import wms_print_agent as a; "
            "from wms_print_runtime import write_private; p=Path(sys.argv[1]); "
            "write_private(p/'inflight.json', {'phase':'submitting','job_id':sys.argv[2]}); "
            "a.submit_to_queue(b'%PDF-synthetic', 'application/pdf', 'Synthetic_442', "
            "executable=str(p/'synthetic-spooler')); os._exit(27)"
        )
        exited = subprocess.run(
            [os.sys.executable, "-c", script, str(self.directory), self.job["id"]],
            cwd=Path(__file__).parent,
            check=False,
            capture_output=True,
        )
        self.assertEqual(exited.returncode, 27)
        self.assertEqual(accepted.read_text().splitlines(), ["accepted"])
        self.assertIn("неизвестен", self.run_once())
        self.assertEqual(self.submissions, [])
        self.assertEqual(self.acks, [])
        self.assertEqual(accepted.read_text().splitlines(), ["accepted"])

    def test_autostart_writes_fixed_executable_arguments_in_synthetic_profile(self):
        import plistlib

        executable = self.directory / "installed app" / "wms-print"
        with (
            patch.object(runtime.sys, "platform", "darwin"),
            patch.object(runtime.sys, "frozen", True, create=True),
            patch.object(runtime.Path, "home", return_value=self.directory),
        ):
            path = runtime.enable_autostart(self.directory, executable)
        config = plistlib.loads(path.read_bytes())
        self.assertEqual(config["ProgramArguments"], [str(executable), "--run"])
        self.assertTrue(config["RunAtLoad"])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_fetch_rejects_checksum_mime_signature_and_oversize(self):
        expected = {
            "checksum": hashlib.sha256(self.content).hexdigest(),
            "content_type": "application/pdf",
        }
        for payload, mime in [
            (b"%PDF-changed", "application/pdf"),
            (self.content, "text/html"),
            (b"x" * (agent.MAX_BYTES + 1), "application/pdf"),
        ]:
            with (
                patch.object(agent, "_open", return_value=(payload, mime)),
                self.assertRaises(ValueError),
            ):
                agent.fetch_label(
                    "https://wms.example",
                    "synthetic",
                    self.job["id"],
                    self.config["warehouse_id"],
                    expected,
                    claim_id=self.job["claim_id"],
                )


if __name__ == "__main__":
    unittest.main()
