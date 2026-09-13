"""Build on the target OS; the operator package includes its own Python runtime."""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    if sys.platform != "darwin":
        raise SystemExit(
            "This distribution is verified on macOS only. Do not label another OS supported."
        )
    dirty = subprocess.check_output(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            "tools/print-agent",
            ".github/workflows/print-agent-package.yml",
        ],
        cwd=ROOT.parents[1],
        text=True,
    ).strip()
    if dirty:
        raise SystemExit(
            "Commit the package sources before building a distributable artifact."
        )
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--name",
            "wms-print",
            "--distpath",
            str(ROOT / "dist"),
            "--workpath",
            str(ROOT / "build"),
            "--specpath",
            str(ROOT / "build"),
            str(ROOT / "wms_print_runtime.py"),
        ],
        check=True,
    )
    target = ROOT / "dist" / "WMS-Print-macOS"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir()
    shutil.copytree(ROOT / "dist" / "wms-print", target / "wms-print")
    launcher = target / "Подключить WMS.command"
    launcher.write_text(
        '#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\n'
        'target="$HOME/Applications/WMS Print"\nmkdir -p "$target"\n'
        'ditto "wms-print" "$target/wms-print"\n'
        'exec "$target/wms-print/wms-print"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    shutil.copy(ROOT / "README.md", target / "README.md")
    (target / "build.json").write_text(
        json.dumps(
            {
                "source_commit": revision,
                "platform": platform.platform(),
                "architecture": platform.machine(),
                "python": platform.python_version(),
                "physical_print_verified": False,
            },
            indent=2,
        )
    )
    archive = Path(
        shutil.make_archive(str(ROOT / "dist" / "WMS-Print-macOS"), "zip", target)
    )
    (archive.with_suffix(".zip.sha256")).write_text(
        hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name + "\n"
    )
    print(archive)


if __name__ == "__main__":
    main()
