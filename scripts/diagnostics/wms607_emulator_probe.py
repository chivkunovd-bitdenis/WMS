"""Run unchanged shipped Mac printing functions against the existing IPP emulator.
Only child-process CUPS_SERVER/LPDEST vary; no printer settings are changed.
Refuses to print unless the system default is the verified localhost emulator.
"""

import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import qrcode
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = (
    ROOT / "docs/evidence/wms607-artmaks" / os.environ.get("WMS607_EVIDENCE_SUFFIX", "")
)
KIT = ROOT.parents[0] / "wms631-stand-kit"
DRIVER = r"""
let a = CommandLine.arguments
if a[1] == "lookup" {
    do { print("QUEUE:" + (try defaultPrinter())) }
    catch { print("ERROR:" + String(describing: error)) }
} else {
    let printer = try Printer(directory: URL(fileURLWithPath:a[2]))
    let data = try Data(contentsOf:URL(fileURLWithPath:a[3]))
    let body:[String:Any] = ["idempotencyKey":a[4],"imageDataUrl":"data:image/png;base64," + data.base64EncodedString()]
    do { print("RECEIPT:" + (try printer.printJob(body))) }
    catch { print("ERROR:" + String(describing:error)) }
}
"""


def main():
    default = subprocess.check_output(["/usr/bin/lpstat", "-d"], text=True)
    device = subprocess.check_output(
        ["/usr/bin/lpstat", "-v", "WMS604_Proof"], text=True
    )
    assert default.strip().endswith(": WMS604_Proof"), default
    assert device.strip().endswith("ipp://localhost:18631/ipp/print"), device
    OUT.mkdir(parents=True, exist_ok=True)
    test_id = "WMS607-" + uuid4().hex[:10]
    img = Image.new("RGB", (464, 320), "white")
    qr = qrcode.make(test_id).convert("RGB").resize((240, 240))
    img.paste(qr, (112, 20))
    ImageDraw.Draw(img).text((30, 280), test_id, fill="black")
    label = OUT / "emulator-input.png"
    img.save(label)
    before = {str(p) for p in (KIT / "printer-out").glob("**/*") if p.is_file()}
    source = (ROOT / "tools/print-agent/wms_print_direct_macos.swift").read_text()
    result = {
        "test_id": test_id,
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "device": device.strip(),
        "runs": [],
    }
    with tempfile.TemporaryDirectory(prefix="wms607-cups-") as tmp:
        d = Path(tmp)
        src = d / "probe.swift"
        exe = d / "probe"
        journal = d / "journal"
        src.write_text(source.split("private struct HTTPRequest {")[0] + DRIVER)
        subprocess.run(
            ["swiftc", str(src), "-o", str(exe)], check=True, capture_output=True
        )

        def run(name, mode, extra):
            args = (
                [str(exe), mode]
                if mode == "lookup"
                else [str(exe), mode, str(journal), str(label), test_id]
            )
            r = subprocess.run(
                args,
                env=dict(os.environ, **extra),
                capture_output=True,
                text=True,
                timeout=75,
                check=False,
            )
            answer = {
                "case": name,
                "exit": r.returncode,
                "result": r.stdout.strip(),
                "journal_exists": (journal / "direct-jobs.json").exists(),
            }
            result["runs"].append(answer)
            return answer

        run("default_valid", "lookup", {})
        run("default_invalid_process_override", "lookup", {"LPDEST": "WMS607_MISSING"})
        run(
            "default_invalid_long_override",
            "lookup",
            {"LPDEST": "WMS607_MISSING_" + "x" * 90},
        )
        failed = run(
            "CUPS_unreachable_same_emulator_still_on",
            "print",
            {"CUPS_SERVER": "127.0.0.1:18639"},
        )
        assert failed["result"].startswith("ERROR:") and not failed["journal_exists"]
        first = run("restore_CUPS_same_key", "print", {})
        assert first["result"].startswith("RECEIPT:WMS604_Proof-"), first
        second = run("repeat_same_key", "print", {})
        assert second["result"] == first["result"], second
        result["journal"] = json.loads((journal / "direct-jobs.json").read_text())
        for _ in range(30):
            created = [
                p
                for p in (KIT / "printer-out").glob("**/*")
                if p.is_file() and str(p) not in before
            ]
            if any(p.suffix == ".png" for p in created):
                break
            time.sleep(1)
        result["emulator_outputs"] = [str(p) for p in created]
        for p in created:
            if p.suffix in (".png", ".pdf", ".json"):
                (OUT / ("output-" + p.name)).write_bytes(p.read_bytes())
    (OUT / "emulator-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
