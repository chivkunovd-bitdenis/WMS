"""Build a self-contained, zero-configuration WMS Print Direct application."""
import json
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def main():
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--", "tools/print-agent", "frontend/src/utils/printDirectQr.ts", "frontend/src/packing-scan-check"], cwd=REPO, text=True).strip()
    if dirty:
        raise SystemExit("Commit the sources before building a distributable")
    subprocess.run(["npx.cmd" if sys.platform == "win32" else "npx", "vite", "build", "--config", "vite.packing-scan-check.config.ts"], cwd=REPO / "frontend", check=True)
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed", "--name", "WMS Print", "--distpath", str(ROOT / "dist-direct"), "--workpath", str(ROOT / "build-direct"), "--specpath", str(ROOT / "build-direct"), "--add-data", f"{REPO / 'frontend/dist-packing-scan-check'}{';' if sys.platform == 'win32' else ':'}direct-web", "--collect-all", "certifi"]
    if sys.platform == "win32":
        for module in ("fitz", "PIL", "win32gui", "win32print", "win32ui"):
            command += ["--collect-all", module]
    command.append(str(ROOT / "wms_print_direct.py"))
    subprocess.run(command, check=True)
    dist = ROOT / "dist-direct"
    metadata = {"source_commit": revision, "platform": sys.platform, "architecture": platform.machine(), "physical_print_verified": False}
    if sys.platform == "darwin":
        app = dist / "WMS Print.app"
        (app / "Contents/Resources/build.json").write_text(json.dumps(metadata, indent=2))
        plist = app / "Contents/Info.plist"
        info = plistlib.loads(plist.read_bytes())
        info["LSUIElement"] = True
        plist.write_bytes(plistlib.dumps(info))
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
        archive = dist / f"WMS-Print-Mac-{platform.machine()}.zip"
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(archive)], check=True)
    else:
        (dist / "WMS Print/build.json").write_text(json.dumps(metadata, indent=2))
        archive = Path(shutil.make_archive(str(dist / "WMS-Print-Windows-x64"), "zip", dist, "WMS Print"))
    print(archive)


if __name__ == "__main__":
    main()
