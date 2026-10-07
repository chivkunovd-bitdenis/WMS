from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
import subprocess

checkout = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser()
parser.add_argument("--case", default="run-28a799")
args = parser.parse_args()
case_dir = Path(__file__).resolve().parent / args.case
out = case_dir / "mac-cups-stub"
source = checkout / "tools/print-agent/wms_print_direct.py"
expected = "81ebff2bb9c638f1d6d41e2f22f618282a5ba476"
blob = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD:tools/print-agent/wms_print_direct.py"], text=True).strip()
if blob != expected:
    raise SystemExit(f"unexpected handler source {blob}")
sys.path.insert(0, str(source.parent))
import wms_print_direct as native
out.mkdir(parents=True, exist_ok=True)
rows = []
class CupsCommandStub:
    def cupsPrintFile(self, queue, path, title, option_count, options):
        payload = Path(path.decode() if isinstance(path, bytes) else path).read_bytes()
        name = Path(path.decode() if isinstance(path, bytes) else path).name
        dest = out / f"{len(rows)+1}-{name}"
        dest.write_bytes(payload)
        rows.append({"queue": queue.decode(), "title": title.decode(), "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload), "stub_file": dest.name, "option_count": option_count})
        return 700 + len(rows)

printer = native.MacPrinter.__new__(native.MacPrinter)
printer.lib = CupsCommandStub()
sink_dir = case_dir / "native" / "sink" if (case_dir / "native" / "sink").exists() else case_dir / "sink"
for input_path in sorted(sink_dir.glob("job-*.png")):
    name = input_path.name
    data = input_path.read_bytes()
    receipt = printer.submit_default(data, "SYNTHETIC_ONLY")
    rows[-1]["source_sha256"] = hashlib.sha256(data).hexdigest()
    rows[-1]["receipt"] = receipt
    rows[-1]["identical_input_output"] = rows[-1]["source_sha256"] == rows[-1]["sha256"]
    if not rows[-1]["identical_input_output"]:
        raise AssertionError("Mac CUPS adapter changed the input PNG before the CUPS boundary")
report = {"source_blob": blob, "candidate_head": subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip(), "physical_printer_called": False, "adapter": "actual MacPrinter.submit_default; cupsPrintFile replaced by file-copy/receipt stub", "outputs": rows}
(out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
