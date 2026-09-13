"""Safe native queue substitute and crash/restart proof; never touches a real printer."""

import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
import uuid
from xml.etree import ElementTree
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

            def submit(self, data, mime, queue, copies, width_mm, height_mm):
                owner.submissions.append(
                    (data, mime, queue, copies, width_mm, height_mm)
                )
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
        self.assertEqual(self.submissions[0][3], 3)
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
        if os.name != "nt":
            self.assertIn("уже запущена", result.stderr)

    def test_private_state_survives_new_reader_and_is_not_world_readable(self):
        path = self.directory / "connection.json"
        runtime.write_private(path, {"fixture": "очередь склада 58"})
        self.assertEqual(runtime.read_private(path), {"fixture": "очередь склада 58"})
        if os.name != "nt":
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
        if os.name == "nt":
            self.skipTest(
                "Windows uses the .cmd synthetic queue in packaged --self-test"
            )
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

    def test_windows_cmd_synthetic_queue_receipt(self):
        if os.name != "nt":
            self.skipTest("Windows-only command invocation")
        executable = self.directory / "synthetic-spooler.cmd"
        spool = self.directory / "accepted.bin"
        executable.write_text(
            '@echo off\ncopy /Y "%4" "'
            + str(spool)
            + '" >NUL\necho request id is Synthetic_442-1 (1 file(s))\n'
        )
        receipt = agent.submit_to_queue(
            self.content,
            "application/pdf",
            "Synthetic_442",
            executable=[os.environ["COMSPEC"], "/c", str(executable)],
        )
        self.assertEqual(receipt, "Synthetic_442-1")
        self.assertEqual(spool.read_bytes(), self.content)

    def test_actual_process_exit_after_spool_acceptance_recovers_without_second_submit(
        self,
    ):
        if os.name == "nt":
            self.skipTest("Windows recovery boundary is covered by process_once mocks")
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
            patch.object(
                runtime.subprocess, "run", return_value=SimpleNamespace(returncode=0)
            ),
        ):
            path = runtime.enable_autostart(self.directory, executable)
        config = plistlib.loads(path.read_bytes())
        self.assertEqual(config["ProgramArguments"], [str(executable), "--run"])
        self.assertTrue(config["RunAtLoad"])
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_windows_adapter_uses_exact_unicode_queue_and_spooler_receipt(self):
        calls = []

        class FakePrint:
            PRINTER_ENUM_LOCAL = 2
            PRINTER_ENUM_CONNECTIONS = 4

            @staticmethod
            def EnumPrinters(flags):
                self.assertEqual(flags, 6)
                return [(0, "", "Принтер склада 58", "")]

        class FakeDc:
            def CreatePrinterDC(self, queue):
                calls.append(("queue", queue))

            def StartDoc(self, name):
                calls.append(("document", name))
                return 442

            def GetDeviceCaps(self, index):
                return {88: 203, 90: 203, 110: 464, 111: 320}[index]

            def StartPage(self):
                calls.append(("start-page",))

            def GetHandleOutput(self):
                return 17

            def EndPage(self):
                calls.append(("end-page",))

            def EndDoc(self):
                calls.append(("end-document",))

            def AbortDoc(self):
                calls.append(("abort",))

            def DeleteDC(self):
                calls.append(("delete",))

        class FakeImage:
            width = 464
            height = 320
            info = {"dpi": (203, 203)}

            def convert(self, mode):
                assert mode == "RGB"
                return self

        class FakeImageModule:
            @staticmethod
            def open(stream):
                self.assertIsInstance(stream, io.BytesIO)
                return FakeImage()

        class FakeImageWin:
            class Dib:
                def __init__(self, image):
                    self.image = image

                def draw(self, handle, target):
                    calls.append(("draw", handle, target))

        adapter = runtime.WindowsAdapter(
            {
                "win32print": FakePrint,
                "win32ui": SimpleNamespace(CreateDC=lambda: FakeDc()),
                "Image": FakeImageModule,
                "ImageWin": FakeImageWin,
                "fitz": None,
            }
        )
        adapter.validate_layout("Принтер склада 58", 58, 40)
        with self.assertRaises(ValueError):
            adapter.validate_layout("Принтер склада 58", 60, 40)
        receipt = adapter.submit(
            b"\x89PNG\r\n\x1a\nsynthetic", "image/png", "Принтер склада 58", 2
        )
        self.assertEqual(receipt, "windows-442")
        self.assertEqual(calls[0], ("queue", "Принтер склада 58"))
        self.assertEqual(sum(call[0] == "draw" for call in calls), 2)
        self.assertNotIn(("abort",), calls)

    def test_windows_task_restart_count_is_in_scheduler_schema_range(self):
        namespace = {"task": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        task = ElementTree.fromstring(
            runtime._windows_task_xml(
                Path(r"C:\WMS Print\wms-print.exe"), "S-1-5-21-442"
            )
        )
        count = int(
            task.findtext(
                "task:Settings/task:RestartOnFailure/task:Count", namespaces=namespace
            )
        )
        self.assertGreaterEqual(count, 1)
        self.assertLessEqual(count, 255)

    def test_windows_installer_stops_and_restores_before_supervised_start(self):
        installer = (Path(__file__).parent / "windows-installer.nsi").read_text()
        self.assertIn("--stop --wait-stop", installer)
        self.assertIn("$INSTDIR.previous", installer)
        self.assertIn("--ensure-autostart", installer)
        self.assertNotIn('wms-print.exe" --run', installer)

    def test_windows_state_directory_and_task_do_not_put_token_in_autostart(self):
        executable = self.directory / "wms-print.exe"
        with (
            patch.object(runtime.sys, "platform", "win32"),
            patch.object(runtime.sys, "frozen", True, create=True),
            patch.dict(os.environ, {"LOCALAPPDATA": str(self.directory)}),
            patch.object(runtime, "restrict_private_directory"),
            patch.object(runtime, "_windows_user_sid", return_value="S-1-5-21-442"),
            patch.object(
                runtime.subprocess, "run", return_value=SimpleNamespace(returncode=0)
            ) as run,
        ):
            self.assertEqual(runtime.state_directory(), self.directory / "WMS Print")
            target = runtime.enable_autostart(self.directory, executable)
        self.assertEqual(target, Path("schtasks://") / runtime.WINDOWS_TASK_NAME)
        create = run.call_args_list[0].args[0]
        self.assertEqual(
            create[:4], ["schtasks", "/Create", "/TN", runtime.WINDOWS_TASK_NAME]
        )
        self.assertNotIn("device_token", " ".join(map(str, create)))

    def test_queue_names_allow_windows_display_text_but_not_controls(self):
        self.assertEqual(agent.check_queue("Принтер склада 58"), "Принтер склада 58")
        for value in ("", "   ", "queue\nname", "-queue"):
            with self.assertRaises(ValueError):
                agent.check_queue(value)

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
