"""Exercise the shipped Swift resolver with a controlled lpstat subprocess.

No printer configuration changes, no OS submissions. The copied production
functions are untouched except lpstat's executable path (fault injection).
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tools/print-agent/wms_print_direct_macos.swift"
CASES = {
    "english": ("system default destination: Label_Printer\n", "", 0, 0),
    "russian": ("назначение системы по умолчанию: Label_Printer\n", "", 0, 0),
    "crlf": ("system default destination: Label_Printer\r\n", "", 0, 0),
    "no_default": ("no system default destination\n", "", 0, 0),
    "scheduler_down": ("", "lpstat: Scheduler is not running.\n", 1, 0),
    "valid_default_with_stderr": (
        "system default destination: Label_Printer\n",
        "warning: diagnostic\n",
        0,
        0,
    ),
    "nonzero_with_default": ("system default destination: Label_Printer\n", "", 1, 0),
    "empty_name": ("system default destination: \n", "", 0, 0),
    "name_128": ("system default destination: " + "A" * 128 + "\n", "", 0, 0),
    "timeout": ("", "", 0, 11),
}
DRIVER = r"""
let args = CommandLine.arguments
if args[1] == "lookup" {
    do { print("QUEUE:" + (try defaultPrinter())) }
    catch { print("ERROR:" + String(describing: error)) }
} else {
    let dir = URL(fileURLWithPath: args[2])
    var submits = 0
    let printer = try Printer(directory: dir, submit: { _, _ in submits += 1; return "fake-1" })
    let body: [String: Any] = ["idempotencyKey": "same-scan", "imageDataUrl": "data:image/png;base64," + pngPrefix.base64EncodedString()]
    setenv("WMS_PRINTER_CASE", "no_default", 1)
    do { _ = try printer.printJob(body); fatalError("Expected failure") }
    catch { print("first_error:" + String(describing: error)) }
    print("journal_after_failed_lookup:" + String(FileManager.default.fileExists(atPath: dir.appendingPathComponent("direct-jobs.json").path)))
    setenv("WMS_PRINTER_CASE", "english", 1)
    print("retry:" + (try printer.printJob(body)))
    print("repeat:" + (try printer.printJob(body)))
    print("submissions:" + String(submits))
}
"""


def main():
    source = SOURCE.read_text()
    results = {
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "cases": {},
    }
    with tempfile.TemporaryDirectory(prefix="wms607-default-") as tmp:
        root = Path(tmp)
        (root / "cases.json").write_text(json.dumps(CASES))
        fake = root / "lpstat"
        fake.write_text(
            "#!"
            + sys.executable
            + "\n"
            + """import json,os,sys,time
from pathlib import Path
out,err,rc,delay=json.loads(Path(__file__).with_name('cases.json').read_text())[os.environ['WMS_PRINTER_CASE']]
if delay:time.sleep(delay)
sys.stderr.write(err);sys.stderr.flush();sys.stdout.write(out);sys.stdout.flush();sys.exit(rc)
"""
        )
        fake.chmod(0o700)
        prefix = source.split("private struct HTTPRequest {")[0]
        probe = root / "probe.swift"
        probe.write_text(
            prefix.replace('"/usr/bin/lpstat"', json.dumps(str(fake))) + DRIVER
        )
        binary = root / "probe"
        subprocess.run(
            ["swiftc", str(probe), "-o", str(binary)], check=True, capture_output=True
        )
        for case in CASES:
            env = dict(os.environ, WMS_PRINTER_CASE=case)
            run = subprocess.run(
                [str(binary), "lookup"],
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            results["cases"][case] = {
                "returncode": run.returncode,
                "result": run.stdout.strip(),
            }
        recovery = subprocess.run(
            [str(binary), "recovery", str(root / "journal")],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        results["recovery"] = recovery.stdout.splitlines()
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
