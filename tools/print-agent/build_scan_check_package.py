"""Build the isolated local scan-check bridge on macOS or Windows (WMS-604)."""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]


def main() -> None:
    if sys.platform not in {"darwin", "win32"}:
        raise SystemExit("Build on macOS or Windows")
    paths = ["tools/print-agent", ".github/workflows/scan-check-package.yml"]
    if subprocess.check_output(
        ["git", "status", "--porcelain", "--", *paths], cwd=REPOSITORY, text=True
    ).strip():
        raise SystemExit("Commit scan-check sources before packaging")
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True
    ).strip()
    target_name = (
        "Windows-x64"
        if sys.platform == "win32"
        else "macOS-arm64"
        if platform.machine() == "arm64"
        else "macOS-Intel-x64"
    )
    output = ROOT / "dist-scan-check"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        "wms-scan-check",
        "--distpath",
        str(output),
        "--workpath",
        str(ROOT / "build-scan-check"),
        "--specpath",
        str(ROOT / "build-scan-check"),
        "--collect-all",
        "certifi",
        "--collect-all",
        "fitz",
        "--collect-all",
        "PIL",
    ]
    if sys.platform == "win32":
        for module in ("win32gui", "win32print", "win32ui"):
            command.extend(["--collect-all", module])
    labels = ROOT / "scan-check-labels"
    if labels.exists():
        command.extend(["--add-data", str(labels) + ":scan-check-labels"])
    command.append(str(ROOT / "wms_scan_bridge.py"))
    subprocess.run(command, check=True)
    payload = output / "wms-scan-check"
    metadata = {
        "source_commit": revision,
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "target": target_name,
        "physical_print_verified": False,
    }
    (payload / "build.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (payload / "READ-ME.txt").write_text(
        "WMS scan-check. Extract the entire ZIP before starting.\n"
        "Start wms-scan-check and select your installed printer once.\n"
        "The bridge remembers the selection and runs in the background.\n"
        "Then open https://sellerfocus.pro/packing-scan-check/ in Chrome.\n"
        "No WMS account, device token, or backend connection is used.\n"
        "A queue receipt confirms OS acceptance, not physical paper output.\n"
    )
    if sys.platform == "darwin":
        launcher = payload / "Start WMS Scan Check.command"
        launcher.write_text('#!/bin/sh\ncd "$(dirname "$0")"\nexec ./wms-scan-check\n')
        launcher.chmod(0o755)
    artifact = Path(
        shutil.make_archive(
            str(output / f"WMS-Scan-Check-{target_name}"), "zip", payload
        )
    )
    checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
    artifact.with_name(artifact.name + ".sha256").write_text(
        checksum + "  " + artifact.name + "\n"
    )
    print(artifact)


if __name__ == "__main__":
    main()
