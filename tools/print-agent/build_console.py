"""Package the current direct-print runtime as a console executable."""
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def main():
    if sys.platform not in {"darwin", "win32"}:
        raise SystemExit("Build on macOS or Windows")
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--", "tools/print-agent",
         ".github/workflows/print-console-package.yml"], cwd=REPO, text=True).strip()
    if dirty:
        raise SystemExit("Commit the package sources before building")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    dist = ROOT / "dist-console"
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
               "--onedir", "--console", "--name", "wms-print",
               "--distpath", str(dist), "--workpath", str(ROOT / "build-console"),
               "--specpath", str(ROOT / "build-console"), "--collect-all", "certifi"]
    if sys.platform == "win32":
        for module in ("fitz", "PIL", "win32gui", "win32print", "win32ui"):
            command += ["--collect-all", module]
    command.append(str(ROOT / "wms_print_direct.py"))
    subprocess.run(command, check=True)
    package = dist / "wms-print"
    (package / "build.json").write_text(json.dumps({
        "source_commit": revision, "platform": sys.platform,
        "architecture": platform.machine(), "runtime": "direct", "console": True,
        "physical_print_verified": False,
    }, indent=2))
    (package / "README.txt").write_text(
        "Распакуйте всю папку. Запустите wms-print (на Windows wms-print.exe).\n"
        "Оставьте окно открытым и сканируйте в WMS через Chrome.\n"
        "Адреса, коды подключения и выбор очереди не нужны.\n"
        "Используется установленный системный принтер по умолчанию.\n"
        "Chrome может запросить разрешение доступа к локальной программе.\n"
        "Сборка без Developer ID/notarization: macOS может запросить разрешение запуска.\n",
        encoding="utf-8")
    target = f"Mac-{platform.machine()}" if sys.platform == "darwin" else "Windows-x64"
    if sys.platform == "darwin":
        # PyInstaller can collect a Python framework without its original
        # resources. Sign the collected bundle, and preserve its symlinks in ZIP.
        for framework in (package / "_internal").glob("*.framework"):
            subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(framework)], check=True)
            subprocess.run(["codesign", "--verify", "--deep", "--strict", str(framework)], check=True)
        archive = dist / f"WMS-Print-Console-{target}.zip"
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(package), str(archive)], check=True)
        unpacked = ROOT / "build-console" / "archive-check"
        if unpacked.exists():
            shutil.rmtree(unpacked)
        subprocess.run(["ditto", "-xk", str(archive), str(unpacked)], check=True)
        for framework in (unpacked / "wms-print/_internal").glob("*.framework"):
            subprocess.run(["codesign", "--verify", "--deep", "--strict", str(framework)], check=True)
        subprocess.run([str(unpacked / "wms-print/wms-print"), "--self-test"], check=True)
        print(archive)
    else:
        print(shutil.make_archive(str(dist / f"WMS-Print-Console-{target}"), "zip", dist, "wms-print"))


if __name__ == "__main__":
    main()
