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
    package = dist / "wms-print"
    if package.exists():
        shutil.rmtree(package)
    package.mkdir(parents=True)
    if sys.platform == "darwin":
        # A downloaded PyInstaller onedir package makes Gatekeeper assess its
        # embedded Python.framework separately.  Without Developer ID this can
        # still fail after the operator permits the main executable.  Compile
        # one native binary that depends only on macOS system frameworks.
        cups_object = dist / "wms_cups_observe.o"
        subprocess.run([
            "clang", "-c", str(ROOT / "wms_cups_observe.c"), "-o", str(cups_object),
        ], check=True)
        subprocess.run([
            "swiftc", "-O", "-whole-module-optimization",
            str(ROOT / "wms_print_direct_macos.swift"),
            "-Xlinker", str(cups_object), "-lcups",
            "-o", str(package / "wms-print"),
        ], check=True)
        shutil.copyfile(ROOT / "history.html", package / "history.html")
        updater = ROOT / "update_macos_direct.sh"
        if updater.is_file():
            shutil.copyfile(updater, package / updater.name)
            (package / updater.name).chmod(0o755)
        subprocess.run(["codesign", "--force", "--sign", "-", str(package / "wms-print")], check=True)
        subprocess.run(["codesign", "--verify", "--strict", str(package / "wms-print")], check=True)
    else:
        command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                   "--onedir", "--console", "--name", "wms-print",
                   "--distpath", str(dist), "--workpath", str(ROOT / "build-console"),
                   "--specpath", str(ROOT / "build-console"), "--collect-all", "certifi"]
        for module in ("fitz", "PIL", "win32gui", "win32print", "win32ui"):
            command += ["--collect-all", module]
        command.append(str(ROOT / "wms_print_direct.py"))
        subprocess.run(command, check=True)
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
        archive = dist / f"WMS-Print-Console-{target}.zip"
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(package), str(archive)], check=True)
        unpacked = ROOT / "build-console" / "archive-check"
        if unpacked.exists():
            shutil.rmtree(unpacked)
        subprocess.run(["ditto", "-xk", str(archive), str(unpacked)], check=True)
        subprocess.run(["codesign", "--verify", "--strict", str(unpacked / "wms-print/wms-print")], check=True)
        subprocess.run([str(unpacked / "wms-print/wms-print"), "--self-test"], check=True)
        print(archive)
    else:
        print(shutil.make_archive(str(dist / f"WMS-Print-Console-{target}"), "zip", dist, "wms-print"))


if __name__ == "__main__":
    main()
