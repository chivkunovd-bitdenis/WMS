"""Real Swift resolver, controlled lpstat process; no printer/OS settings changed."""

import json
import os
import platform
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).with_name("wms_print_direct_macos.swift")


@unittest.skipUnless(platform.system() == "Darwin", "Native macOS helper")
class DefaultPrinterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="wms607-resolver-test-")
        cls.root = Path(cls.tmp.name)
        fake = cls.root / "lpstat"
        fake.write_text(
            "#!"
            + sys.executable
            + "\n"
            + r"""
import os, sys
case = os.environ['WMS_RESOLVER_CASE']
if sys.argv[1] == '-p':
    if case == 'unreachable': sys.exit(1)
    if len(sys.argv) > 2 and sys.argv[2] != 'Label_Printer': sys.exit(1)
    print('printer Label_Printer is idle')
    sys.exit(0)
if case == 'unreachable' or case == 'stale':
    print('no system default destination')
elif case == 'invalid_override':
    print('lpstat: error - LPDEST environment variable names non-existent destination Ghost.')
elif case == 'localized':
    print('назначение системы по умолчанию: Label_Printer')
else:
    print('system default destination: Label_Printer')
    if case == 'warning': print('warning: diagnostic', file=sys.stderr)
"""
        )
        fake.chmod(0o700)
        # The journal runtime validates complete PNGs and returns job records.
        # Adapt only invocation/fixtures; the original five assertions stay intact.
        driver = r"""
@_cdecl("wms_cups_observe")
func testObserve(_ queue: UnsafePointer<CChar>, _ receipt: UnsafePointer<CChar>, _ title: UnsafePointer<CChar>) -> Int32 { return 1 }
let dir = URL(fileURLWithPath: CommandLine.arguments[1])
var submits = 0
private let printer = try Printer(directory: dir, autoWork: false, submit: { _, _ in submits += 1; return "Label_Printer-1" })
let body: [String: Any] = ["idempotencyKey":"same-key", "imageDataUrl":"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8//8/AwMDEwMDAwMDAwAkBgMB/DXemwAAAABJRU5ErkJggg==", "widthMm":58, "heightMm":40]
func attempt() throws -> String {
    _ = try printer.printJob(body)
    if try printer.detail("same-key")?["status"] as? String == "failed_before_submit" {
        _ = try printer.retry("same-key")
    }
    printer.process("same-key")
    let result = try printer.detail("same-key")!
    guard let receipt = result["receipt"] as? String else {
        throw PrintError.message(result["reason"] as? String ?? "missing reason")
    }
    return receipt
}
do { print("RECEIPT:" + (try attempt())) }
catch { print("ERROR:" + String(describing:error)) }
print("journal:" + String(FileManager.default.fileExists(atPath:dir.appendingPathComponent("direct-jobs.json").path)))
setenv("WMS_RESOLVER_CASE", "normal", 1)
print("retry:" + (try attempt()))
print("repeat:" + (try attempt()))
print("submits:" + String(submits))
"""
        source = SOURCE.read_text().split("private struct HTTPRequest {")[0]
        probe = cls.root / "probe.swift"
        probe.write_text(
            source.replace('"/usr/bin/lpstat"', json.dumps(str(fake))) + driver
        )
        cls.exe = cls.root / "probe"
        subprocess.run(
            ["swiftc", str(probe), "-o", str(cls.exe)], check=True, capture_output=True
        )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, case):
        p = subprocess.run(
            [str(self.exe), str(self.root / case)],
            env=dict(os.environ, WMS_RESOLVER_CASE=case),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout

    def test_valid_default_with_warning_still_prints(self):
        output = self.run_case("warning")
        self.assertIn("RECEIPT:Label_Printer-1", output)
        self.assertIn("submits:1", output)

    def test_localized_default_and_replay(self):
        output = self.run_case("localized")
        self.assertIn("RECEIPT:Label_Printer-1", output)
        self.assertIn("submits:1", output)

    def test_error_text_is_not_a_queue_or_uncertain_job(self):
        output = self.run_case("invalid_override")
        self.assertIn("ERROR:", output)
        self.assertIn("journal:false", output)
        self.assertIn("submits:1", output)

    def test_cups_unreachable_is_not_missing_default(self):
        output = self.run_case("unreachable")
        self.assertIn("Недоступна служба печати macOS", output)
        self.assertIn("journal:false", output)
        self.assertIn("submits:1", output)

    def test_stale_default_keeps_same_key_recoverable(self):
        output = self.run_case("stale")
        self.assertIn("macOS не определила принтер по умолчанию", output)
        self.assertIn("journal:false", output)
        self.assertIn("submits:1", output)


if __name__ == "__main__":
    unittest.main()
