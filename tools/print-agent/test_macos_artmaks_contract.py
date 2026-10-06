"""WMS-607 frozen ArtMaks contract: real Swift/Printer, fake OS commands only.

WMS607_SWIFT_SOURCE selects a candidate for RED/GREEN evidence without changing
product files. The installed .4 producer is pinned to its actual Git source;
its persisted journal is consumed by the candidate in another process.
"""

import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get("WMS607_SWIFT_SOURCE", ROOT / "wms_print_direct_macos.swift"))
INSTALLED_SOURCE = "9a33b651c309796707053e1056c7f80dff7194d5"
PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8//8/"
    "AwMDEwMDAwMDAwAkBgMB/DXemwAAAABJRU5ErkJggg=="
)


@unittest.skipUnless(platform.system() == "Darwin", "Native macOS Swift contract")
class ArtMaksMacContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="wms607-artmaks-contract-")
        cls.root = Path(cls.tmp.name)
        cls.lpstat = cls.root / "lpstat"
        cls.lp = cls.root / "lp"
        cls.lpstat.write_text(
            "#!" + sys.executable + "\n" + r'''
import json, os, sys, time
with open(os.environ['WMS_COMMAND_LOG'], 'a') as log:
    log.write(json.dumps(['lpstat'] + sys.argv[1:]) + '\n')
case = os.environ.get('WMS_RESOLVER_CASE', 'normal')
args = sys.argv[1:]
if (case == 'default_timeout' and args == ['-d']) or (case == 'queue_timeout' and len(args) == 2 and args[0] == '-p') or (case == 'list_timeout' and args == ['-p']):
    time.sleep(30)  # Actual Process timeout/termination, not a timedOut stub.
if args == ['-d']:
    if case == 'list_timeout': print('no system default destination')
    else: print('system default destination: Label_Printer')
else:
    print('printer Label_Printer is idle')
'''
        )
        cls.lp.write_text(
            "#!" + sys.executable + "\n" + r'''
import json, os, sys
with open(os.environ['WMS_COMMAND_LOG'], 'a') as log:
    log.write(json.dumps(['lp'] + sys.argv[1:]) + '\n')
print('request id is Label_Printer-41 (1 file)')
'''
        )
        cls.lpstat.chmod(0o700)
        cls.lp.chmod(0o700)
        installed = subprocess.check_output(
            ["git", "show", INSTALLED_SOURCE + ":tools/print-agent/wms_print_direct_macos.swift"],
            cwd=ROOT, text=True,
        )
        cls.installed = cls.compile(installed, "installed")
        cls.candidate = cls.compile(SOURCE.read_text(), "candidate")

    @classmethod
    def compile(cls, source, name):
        # Only remove the HTTP/server entrypoint and replace OS command paths.
        # Resolver, Process timer, dimensions, digest and Printer are unmodified.
        source = source.split("private struct HTTPRequest {")[0]
        source = source.replace('"/usr/bin/lpstat"', json.dumps(str(cls.lpstat)))
        source = source.replace('"/usr/bin/lp"', json.dumps(str(cls.lp)))
        journal_runtime = "autoWork:Bool" in source.replace(" ", "")
        if journal_runtime:
            # The unused observer symbol is an external CUPS boundary, never called.
            source += '''
@_cdecl("wms_cups_observe")
func testObserve(_ queue: UnsafePointer<CChar>, _ receipt: UnsafePointer<CChar>, _ title: UnsafePointer<CChar>) -> Int32 { return 1 }
'''
            operation = '''
let printer = try Printer(directory: dir, autoWork: false)
_ = try printer.printJob(body)
if let existing = try printer.detail("same-key"), existing["status"] as? String == "failed_before_submit" {
    _ = try printer.retry("same-key")
}
printer.process("same-key")
let result = try printer.detail("same-key")!
if let receipt = result["receipt"] as? String { print("RECEIPT:" + receipt) }
else { print("ERROR:" + (result["reason"] as? String ?? "missing reason")) }
print("STATUS:" + (result["status"] as? String ?? "missing status"))
'''
        else:
            operation = '''
let printer = try Printer(directory: dir)
print("RECEIPT:" + (try printer.printJob(body)))
'''
        source += '''
let dir = URL(fileURLWithPath: CommandLine.arguments[1])
let body: [String: Any] = [
    "idempotencyKey": "same-key",
    "imageDataUrl": "data:image/png;base64," + ''' + json.dumps(PNG_BASE64) + ''',
    "widthMm": Double(CommandLine.arguments[2])!, "heightMm": Double(CommandLine.arguments[3])!,
]
do {
''' + operation + '''
} catch { print("ERROR:" + String(describing: error)) }
'''
        probe = cls.root / (name + ".swift")
        probe.write_text(source)
        exe = cls.root / name
        result = subprocess.run(
            ["swiftc", str(probe), "-o", str(exe)], capture_output=True, text=True,
            timeout=60,
        )
        if result.returncode:
            raise RuntimeError("Swift contract compile failed:\n" + result.stderr)
        return exe

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.store = self.root / self._testMethodName
        self.log = self.root / (self._testMethodName + ".jsonl")
        self.log.write_text("")

    def run_probe(self, exe=None, case="normal", width=58, height=40):
        result = subprocess.run(
            [str(exe or self.candidate), str(self.store), str(width), str(height)],
            env={**os.environ, "WMS_RESOLVER_CASE": case, "WMS_COMMAND_LOG": str(self.log)},
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def assert_timeout_retry(self, case, expected_command):
        output = self.run_probe(case=case)
        self.assertIn(expected_command, self.commands(), "target branch was not exercised")
        self.assertIn("ERROR:", output)
        self.assertRegex(output.lower(), r"(не ответила вовремя|таймаут|время ожидания)")
        self.assertNotIn("не определила принтер по умолчанию", output)
        self.assertNotIn("не выбран принтер по умолчанию", output)
        self.assertFalse(any(command[0] == "lp" for command in self.commands()))
        journal = self.store / "direct-jobs.json"
        self.assertFalse(journal.exists() and "same-key" in json.loads(journal.read_text()),
                         "pre-submit timeout must not leave a legacy uncertain job")
        self.assertIn("RECEIPT:Label_Printer-41", self.run_probe())
        self.assertIn("RECEIPT:Label_Printer-41", self.run_probe())
        self.assertEqual(sum(command[0] == "lp" for command in self.commands()), 1,
                         "same-key recovery/restart must submit exactly once")

    def test_queue_validation_timeout_is_distinct_and_retryable(self):
        self.assert_timeout_retry("queue_timeout", ["lpstat", "-p", "Label_Printer"])

    def test_printer_list_timeout_is_distinct_and_retryable(self):
        self.assert_timeout_retry("list_timeout", ["lpstat", "-p"])

    def test_default_timeout_is_distinct_and_retryable(self):
        self.assert_timeout_retry("default_timeout", ["lpstat", "-d"])

    def test_new_label_passes_58x40_to_actual_lp(self):
        self.assertIn("RECEIPT:Label_Printer-41", self.run_probe())
        submits = [command for command in self.commands() if command[0] == "lp"]
        self.assertEqual(len(submits), 1)
        self.assertIn("media=Custom.58x40mm", submits[0])
        self.assertIn("copies=1", submits[0])

    def seed_installed_receipt(self):
        self.assertIn("RECEIPT:Label_Printer-41", self.run_probe(self.installed))
        self.assertIn("media=Custom.58x40mm", self.commands()[-1])
        self.log.write_text("")

    def test_installed_size_aware_receipt_replays_after_upgrade_and_restart(self):
        self.seed_installed_receipt()
        for _ in range(2):
            self.assertIn("RECEIPT:Label_Printer-41", self.run_probe())
        self.assertEqual(self.commands(), [], "persisted receipt must bypass resolver and lp")

    def test_same_png_with_changed_size_is_rejected(self):
        self.assertIn("RECEIPT:Label_Printer-41", self.run_probe())
        self.log.write_text("")
        output = self.run_probe(width=60)
        self.assertIn("ERROR:", output)
        self.assertRegex(output, r"(Содержимое|размер).*(изменил|изменилось)")
        self.assertEqual(self.commands(), [], "changed dimensions must not submit")


if __name__ == "__main__":
    unittest.main()
