"""Build the WMS Print distribution on its target operating system."""

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


def sha256(path: Path) -> Path:
    checksum = path.with_name(path.name + ".sha256")
    checksum.write_text(
        hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
    )
    return checksum


def build_metadata(revision: str, target: str) -> dict[str, object]:
    return {
        "source_commit": revision,
        "build_platform": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "target": target,
        "supported_architecture": "arm64" if target.startswith("macOS") else "x64",
        "windows_target_matrix": ["Windows 10 22H2 x64", "Windows 11 x64"],
        "macos_target_matrix": ["macOS arm64"],
        "physical_print_verified": False,
    }


def build_executable(name: str = "wms-print", *, windowed: bool = False) -> None:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        name,
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build"),
        "--specpath",
        str(ROOT / "build"),
        "--collect-all",
        "certifi",
    ]
    if windowed:
        command.append("--windowed")
    if sys.platform == "win32":
        command.extend(
            [
                "--collect-all",
                "fitz",
                "--collect-all",
                "PIL",
                "--collect-all",
                "win32gui",
                "--collect-all",
                "win32print",
                "--collect-all",
                "win32ui",
            ]
        )
    command.append(str(ROOT / "wms_print_runtime.py"))
    subprocess.run(command, check=True)


def build_macos(revision: str) -> Path:
    target = ROOT / "dist" / "WMS-Print-macOS"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir()
    shutil.copytree(ROOT / "dist" / "wms-print", target / "wms-print")
    launcher = target / "Подключить WMS.command"
    launcher.write_text(
        '#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\n'
        'target="$HOME/Applications/WMS Print"\nmkdir -p "$target"\n'
        'if [ -x "$target/wms-print/wms-print" ]; then\n'
        '  "$target/wms-print/wms-print" --stop --wait-stop\n'
        "fi\n"
        'ditto "wms-print" "$target/wms-print"\n'
        'exec "$target/wms-print/wms-print"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    shutil.copy(ROOT / "README.md", target / "README.md")
    (target / "build.json").write_text(
        json.dumps(build_metadata(revision, "macOS arm64"), indent=2)
    )
    return Path(shutil.make_archive(str(target), "zip", target))


def build_windows(revision: str) -> Path:
    target = ROOT / "dist" / "WMS-Print-Windows"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir()
    payload = target / "wms-print"
    payload.mkdir()
    shutil.copytree(ROOT / "dist" / "wms-print-setup", payload, dirs_exist_ok=True)
    shutil.copytree(ROOT / "dist" / "wms-print", payload, dirs_exist_ok=True)
    shutil.copy(ROOT / "README.md", target / "wms-print" / "README.md")
    (target / "wms-print" / "build.json").write_text(
        json.dumps(build_metadata(revision, "Windows x64"), indent=2)
    )
    installer = ROOT / "dist" / "WMS-Print-Setup-Windows-x64.exe"
    subprocess.run(
        [
            "makensis",
            f"/DOUTFILE={installer}",
            f"/DPAYLOAD={target / 'wms-print'}",
            str(ROOT / "windows-installer.nsi"),
        ],
        check=True,
    )
    return installer


def main() -> None:
    if sys.platform not in {"darwin", "win32"}:
        raise SystemExit("Build the operator package on macOS arm64 or Windows x64.")
    dirty = subprocess.check_output(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            "tools/print-agent",
            ".github/workflows/print-agent-package.yml",
        ],
        cwd=REPOSITORY,
        text=True,
    ).strip()
    if dirty:
        raise SystemExit(
            "Commit the package sources before building a distributable artifact."
        )
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True
    ).strip()
    if sys.platform == "win32":
        # The setup executable keeps the required terminal input; the worker is
        # a separate windowless executable started only by Task Scheduler.
        build_executable("wms-print-setup")
        build_executable("wms-print", windowed=True)
        artifact = build_windows(revision)
    else:
        build_executable()
        artifact = build_macos(revision)
    sha256(artifact)
    print(artifact)


if __name__ == "__main__":
    main()
