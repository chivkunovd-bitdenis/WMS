"""WMS-442: paired unattended runtime around the WMS-402 file/queue adapter.

The single inflight file is an acknowledgement outbox, not a print history.
After submitting may have begun, it is NEVER used to resubmit a document.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import os
import plistlib
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import uuid
from xml.sax.saxutils import escape
from pathlib import Path
from typing import Any

import wms_print_agent as agent

PREFIX = "/operations/print"
WINDOWS_TASK_NAME = "WMS Print"


def _profile_key(directory: Path) -> str:
    """A stable per-profile Windows object name, without storing access data."""
    return hashlib.sha256(str(directory).encode("utf-8")).hexdigest()[:24]


def state_directory() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "WMS Print"
    if sys.platform.startswith("linux"):
        return (
            Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
            / "wms-print"
        )
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "WMS Print"
    raise ValueError("Эта сборка поддерживает macOS, Windows и Linux/CUPS.")


def _windows_user_sid() -> str:
    """Resolve the current account SID for a private per-user state directory."""
    result = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise OSError("Windows не вернула идентификатор текущего пользователя")
    rows = list(csv.reader(result.stdout.splitlines()))
    if len(rows) != 1 or len(rows[0]) < 2 or not rows[0][-1].startswith("S-1-"):
        raise OSError("Windows вернула неверный идентификатор текущего пользователя")
    return rows[0][-1]


def restrict_private_directory(directory: Path) -> None:
    """Keep credentials/outbox readable by this Windows user and SYSTEM only."""
    if sys.platform != "win32":
        directory.chmod(0o700)
        return
    sid = _windows_user_sid()
    result = subprocess.run(
        [
            "icacls",
            str(directory),
            "/inheritance:r",
            "/grant:r",
            f"*{sid}:(OI)(CI)F",
            "*S-1-5-18:(OI)(CI)F",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise OSError("Windows не смогла ограничить доступ к настройке печати")


def write_private(path: Path, value: dict[str, Any]) -> None:
    """Atomic replacement with fsync, so restart cannot lose the submission boundary."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    restrict_private_directory(path.parent)
    tmp = path.with_suffix(".new")
    descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(value, output, ensure_ascii=False)
        output.flush()
        os.fsync(output.fileno())
    os.replace(tmp, path)
    if sys.platform != "win32":
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def read_private(path: Path) -> dict[str, Any]:
    with path.open() as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("Неверный файл настройки программы")  # noqa: TRY004
    return value


@contextlib.contextmanager
def single_instance(directory: Path):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    restrict_private_directory(directory)
    if sys.platform == "win32":
        import ctypes

        key = _profile_key(directory)
        mutex = ctypes.windll.kernel32.CreateMutexW(
            None, False, "Local\\WMSPrint-" + key
        )
        if not mutex:
            raise OSError("Windows не смогла создать блокировку программы печати")
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            ctypes.windll.kernel32.CloseHandle(mutex)
            raise ValueError("Программа печати уже запущена в этом профиле")
        stop_event = ctypes.windll.kernel32.CreateEventW(
            None, True, False, "Local\\WMSPrintStop-" + key
        )
        if not stop_event:
            ctypes.windll.kernel32.CloseHandle(mutex)
            raise OSError("Windows не смогла создать сигнал остановки")

        class WindowsControl:
            def wait(self, seconds: float) -> bool:
                return (
                    ctypes.windll.kernel32.WaitForSingleObject(
                        stop_event, int(seconds * 1000)
                    )
                    == 0
                )

        try:
            yield WindowsControl()
        finally:
            ctypes.windll.kernel32.CloseHandle(stop_event)
            ctypes.windll.kernel32.CloseHandle(mutex)
        return

    import fcntl

    with (directory / "runtime.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Программа печати уже запущена в этом профиле") from None

        class PosixControl:
            @staticmethod
            def wait(seconds: float) -> bool:
                time.sleep(seconds)
                return False

        try:
            yield PosixControl()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


class CupsAdapter:
    """Only installed queues, fixed executable, no shell or downloaded commands."""

    def __init__(self, run: Any = subprocess.run, platform: str = sys.platform):
        if platform not in {"darwin", "linux"}:
            raise ValueError("Очередь этой ОС не поддерживается")
        self.run = run

    def queues(self) -> list[str]:
        result = self.run(
            ["/usr/bin/lpstat", "-p"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env={**os.environ, "LC_ALL": "C"},
        )
        names = []
        for line in result.stdout.splitlines():
            words = line.split()
            if len(words) > 1 and words[0] == "printer":
                names.append(agent.check_queue(words[1]))
        return sorted(set(names))

    def submit(
        self,
        data: bytes,
        mime: str,
        queue: str,
        copies: int,
        width_mm: int | None = None,
        height_mm: int | None = None,
    ) -> str:
        agent.check_queue(queue)
        if queue not in self.queues():
            raise ValueError(
                "Назначенная очередь отсутствует в ОС. Проверьте установленный принтер."
            )
        return agent.submit_to_queue(
            data, mime, queue, self.run, copies=copies, executable="/usr/bin/lp"
        )


class WindowsAdapter:
    """Windows spooler adapter using the named queue and a real GDI job receipt.

    PDF pages are rasterized locally and PNG labels are decoded locally; neither
    is opened in a viewer or routed through the default printer.  ``StartDoc``
    returns the Windows spooler job ID only after the selected queue accepted a
    print document.  A driver still decides whether it can put paper through.
    """

    def __init__(self, modules: dict[str, Any] | None = None):
        if modules is None:
            if sys.platform != "win32":
                raise ValueError("Очередь Windows доступна только в Windows-сборке")
            try:
                import fitz
                import win32print
                import win32ui
                from PIL import Image, ImageWin
            except ImportError as exc:
                raise RuntimeError(
                    "В пакете отсутствует компонент печати Windows"
                ) from exc
            modules = {
                "fitz": fitz,
                "win32print": win32print,
                "win32ui": win32ui,
                "Image": Image,
                "ImageWin": ImageWin,
            }
        self.modules = modules

    def queues(self) -> list[str]:
        printer_flags = (
            self.modules["win32print"].PRINTER_ENUM_LOCAL
            | self.modules["win32print"].PRINTER_ENUM_CONNECTIONS
        )
        records = self.modules["win32print"].EnumPrinters(printer_flags)
        return sorted({agent.check_queue(record[2]) for record in records})

    def _pages(
        self, data: bytes, mime: str, width_mm: int | None, height_mm: int | None
    ) -> list[tuple[Any, float, float]]:
        image_module = self.modules["Image"]
        if mime == "image/png":
            image = image_module.open(io.BytesIO(data)).convert("RGB")
            dpi = image.info.get("dpi", (203, 203))
            dpi_x = float(dpi[0]) if dpi and dpi[0] else 203.0
            dpi_y = float(dpi[1]) if dpi and dpi[1] else 203.0
            return [
                (
                    image,
                    float(width_mm)
                    if width_mm is not None
                    else image.width / dpi_x * 25.4,
                    float(height_mm)
                    if height_mm is not None
                    else image.height / dpi_y * 25.4,
                )
            ]
        if mime != "application/pdf":
            raise ValueError("Неподдерживаемый формат этикетки")
        document = self.modules["fitz"].open(stream=data, filetype="pdf")
        pages: list[tuple[Any, float, float]] = []
        try:
            for page in document:
                pixmap = page.get_pixmap(
                    matrix=self.modules["fitz"].Matrix(300 / 72, 300 / 72), alpha=False
                )
                image = image_module.frombytes(
                    "RGB", (pixmap.width, pixmap.height), pixmap.samples
                )
                pages.append(
                    (
                        image,
                        float(width_mm)
                        if width_mm is not None
                        else page.rect.width / 72 * 25.4,
                        float(height_mm)
                        if height_mm is not None
                        else page.rect.height / 72 * 25.4,
                    )
                )
        finally:
            document.close()
        if not pages:
            raise ValueError("PDF-этикетка не содержит страниц")
        return pages

    def submit(
        self,
        data: bytes,
        mime: str,
        queue: str,
        copies: int,
        width_mm: int | None = None,
        height_mm: int | None = None,
    ) -> str:
        agent.check_queue(queue)
        if queue not in self.queues():
            raise ValueError(
                "Назначенная очередь отсутствует в ОС. Проверьте установленный принтер."
            )
        if type(copies) is not int or not 1 <= copies <= 999:
            raise ValueError("Некорректное число копий")
        pages = self._pages(data, mime, width_mm, height_mm)
        dc = self.modules["win32ui"].CreateDC()
        try:
            # CreatePrinterDC takes the queue name explicitly; it never falls
            # back to the default printer.
            dc.CreatePrinterDC(queue)
            receipt = dc.StartDoc("WMS label")
            if not isinstance(receipt, int) or receipt <= 0:
                raise agent.UnknownPrintOutcome(
                    "Очередь Windows не вернула номер задания"
                )
            try:
                dpi_x = dc.GetDeviceCaps(88)  # LOGPIXELSX
                dpi_y = dc.GetDeviceCaps(90)  # LOGPIXELSY
                for _ in range(copies):
                    for image, width_mm, height_mm in pages:
                        dc.StartPage()
                        try:
                            target = (
                                0,
                                0,
                                max(1, round(width_mm / 25.4 * dpi_x)),
                                max(1, round(height_mm / 25.4 * dpi_y)),
                            )
                            self.modules["ImageWin"].Dib(image).draw(
                                dc.GetHandleOutput(), target
                            )
                        finally:
                            dc.EndPage()
                dc.EndDoc()
            except BaseException:
                # A GDI document may already have reached the spooler.  The
                # runtime must keep it in the unknown state and never retry.
                try:
                    dc.AbortDoc()
                except BaseException:
                    pass
                raise agent.UnknownPrintOutcome(
                    "Исход передачи в очередь Windows неизвестен; повтор запрещён"
                ) from None
        finally:
            dc.DeleteDC()
        return f"windows-{receipt}"


def printer_adapter() -> CupsAdapter | WindowsAdapter:
    return WindowsAdapter() if sys.platform == "win32" else CupsAdapter()


class Client:
    def __init__(self, config: dict[str, Any]):
        self.base = agent.check_base_url(config["base_url"])
        self.token = config["device_token"]

    def api(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        return agent._api(self.base, self.token, "POST", PREFIX + path, body=body or {})

    def fetch(self, job: dict[str, Any], expected: dict[str, Any]) -> bytes:
        return agent.fetch_label(
            self.base,
            self.token,
            str(uuid.UUID(job["id"])),
            job["warehouse_id"],
            expected,
            claim_id=str(uuid.UUID(job["claim_id"])),
        )


def validate_destination(job: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    expected = agent.validate_job(job, config["warehouse_id"])
    uuid.UUID(job["claim_id"])
    if (
        job.get("connection_id") != config["connection_id"]
        or job.get("queue_name") != config["queue_name"]
    ):
        raise ValueError("Назначение задания отличается от сопряжённой очереди")
    copies = job.get("copies")
    if type(copies) is not int or not 1 <= copies <= 999:
        raise ValueError("Некорректное число копий")
    size = job.get("content_bytes")
    if type(size) is not int or not 1 <= size <= agent.MAX_BYTES:
        raise ValueError("Некорректный размер этикетки")
    expected["content_bytes"] = size
    width, height = job.get("width_mm"), job.get("height_mm")
    if width is not None or height is not None:
        if (
            type(width) is not int
            or type(height) is not int
            or not 1 <= width <= 1000
            or not 1 <= height <= 1000
        ):
            raise ValueError("Некорректный размер этикетки")
        expected["width_mm"] = width
        expected["height_mm"] = height
    return expected


def acknowledge(client: Client, inflight: dict[str, Any]) -> None:
    client.api(
        "/agent/jobs/" + str(uuid.UUID(inflight["job_id"])) + "/result",
        inflight["result"],
    )


def process_once(
    config: dict[str, Any], directory: Path, client: Client, adapter: Any
) -> str:
    """Caller holds the profile lock. Server independently claims across profiles/PCs."""
    outbox = directory / "inflight.json"
    if outbox.exists():
        previous = read_private(outbox)
        if previous["phase"] == "result":
            acknowledge(client, previous)
            outbox.unlink()
            return "Квитанция восстановлена; повторной передачи в ОС не было."
        # Crash in/before native call: no receipt proves rejection. WMS already
        # retains running. Discard only the local outbox and continue on next tick.
        outbox.unlink()
        return "Результат печати неизвестен. Проверьте очередь принтера; повтор не выполнялся."
    job = client.api("/agent/next").get("job")
    if job is None:
        return ""
    job_id = str(uuid.UUID(job["id"]))
    claim_id = str(uuid.UUID(job["claim_id"]))
    marker: dict[str, Any] = {
        "phase": "preparing",
        "job_id": job_id,
        "claim_id": claim_id,
    }
    write_private(outbox, marker)
    try:
        expected = validate_destination(job, config)
        content = client.fetch(job, expected)
        if len(content) != expected["content_bytes"]:
            raise ValueError("Размер этикетки изменился после создания задания")
        # Failures before the durable boundary below are known not to have spooled.
        if job["queue_name"] not in adapter.queues():
            raise ValueError("Назначенная очередь отсутствует в ОС")
    except (ValueError, KeyError, TypeError, OSError, urllib.error.URLError) as exc:
        marker["phase"] = "result"
        marker["result"] = {
            "claim_id": claim_id,
            "queue_receipt": None,
            "handed_to_queue": False,
            "error_message": (
                str(exc)
                if isinstance(exc, ValueError)
                else "Файл не получен до передачи в ОС: " + type(exc).__name__
            ),
        }
    else:
        marker["phase"] = "submitting"
        write_private(outbox, marker)
        try:
            receipt = adapter.submit(
                content,
                expected["content_type"],
                job["queue_name"],
                job["copies"],
                expected.get("width_mm"),
                expected.get("height_mm"),
            )
        except (agent.UnknownPrintOutcome, OSError, ValueError):
            # Keep the boundary until next start/tick. Neither a retry nor a
            # negative receipt is justified if the native call might have run.
            return "Результат печати неизвестен. Автоматическая повторная отправка запрещена."
        marker["phase"] = "result"
        marker["result"] = {
            "claim_id": claim_id,
            "queue_receipt": receipt,
            "handed_to_queue": True,
            "error_message": None,
        }
    write_private(outbox, marker)
    acknowledge(client, marker)
    outbox.unlink()
    return (
        "Передано в очередь принтера. Бумагу проверьте на принтере."
        if marker["result"]["handed_to_queue"]
        else "Не передано в очередь принтера."
    )


def _windows_task_xml(executable: Path, user_sid: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers><LogonTrigger><Enabled>true</Enabled></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>{escape(user_sid)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
  </Settings>
  <Actions Context="Author"><Exec><Command>{escape(str(executable))}</Command><Arguments>--run</Arguments></Exec></Actions>
</Task>"""


def _register_windows_task(directory: Path, executable: Path) -> Path:
    task_file = directory / "autostart.xml"
    task_file.write_text(
        _windows_task_xml(executable, _windows_user_sid()), encoding="utf-16"
    )
    try:
        result = subprocess.run(
            [
                "schtasks",
                "/Create",
                "/TN",
                WINDOWS_TASK_NAME,
                "/XML",
                str(task_file),
                "/F",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    finally:
        task_file.unlink(missing_ok=True)
    if result.returncode != 0:
        raise OSError("Windows не зарегистрировала фоновую программу печати")
    return Path("schtasks://") / WINDOWS_TASK_NAME


def enable_autostart(directory: Path, executable: Path) -> Path:
    if not getattr(sys, "frozen", False):
        raise ValueError("Автозапуск включается из распространяемой сборки программы")
    if sys.platform == "win32":
        return _register_windows_task(directory, executable)
    if sys.platform != "darwin":
        raise ValueError("Автозапуск этой ОС не поддерживается")
    target = Path.home() / "Library" / "LaunchAgents" / "ru.wms.print-agent.plist"
    target.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "Label": "ru.wms.print-agent",
        "ProgramArguments": [str(executable), "--run"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 15,
        "StandardOutPath": str(directory / "runtime.log"),
        "StandardErrorPath": str(directory / "runtime.log"),
    }
    target.write_bytes(plistlib.dumps(value))
    target.chmod(0o600)
    return target


def start_registered_background(directory: Path) -> None:
    """Start the registered worker only after setup releases the profile lock."""
    if sys.platform == "win32":
        result = subprocess.run(
            ["schtasks", "/Run", "/TN", WINDOWS_TASK_NAME],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise OSError("Windows не запустила фоновую программу печати")
        return
    if sys.platform == "darwin":
        target = Path.home() / "Library" / "LaunchAgents" / "ru.wms.print-agent.plist"
        result = subprocess.run(
            ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(target)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise OSError("macOS не запустила фоновую программу печати")


def disable_autostart(directory: Path) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["schtasks", "/Delete", "/TN", WINDOWS_TASK_NAME, "/F"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return
    if sys.platform == "darwin":
        target = Path.home() / "Library" / "LaunchAgents" / "ru.wms.print-agent.plist"
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}", str(target)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        target.unlink(missing_ok=True)


def request_stop(directory: Path) -> bool:
    """Tell the running Windows user task to stop before package replacement."""
    if sys.platform != "win32":
        return False
    import ctypes

    event = ctypes.windll.kernel32.OpenEventW(
        0x0002, False, "Local\\WMSPrintStop-" + _profile_key(directory)
    )
    if not event:
        return False
    try:
        return bool(ctypes.windll.kernel32.SetEvent(event))
    finally:
        ctypes.windll.kernel32.CloseHandle(event)


def setup(directory: Path, adapter: Any) -> dict[str, Any]:
    config_path = directory / "connection.json"
    if config_path.exists():
        config = read_private(config_path)
    else:
        base = agent.check_base_url(input("HTTPS-адрес API WMS: ").strip())
        queues = adapter.queues()
        if not queues:
            raise ValueError(
                "В ОС нет принтеров. Сначала установите драйвер и очередь через настройки ОС."
            )
        print("Установленные очереди принтеров:")
        for index, queue in enumerate(queues, 1):
            print(f"{index}. {queue}")
        chosen = int(input("Номер принтера: "))
        if not 1 <= chosen <= len(queues):
            raise ValueError("Номер принтера отсутствует")
        config = {
            "base_url": base,
            "queue_name": queues[chosen - 1],
            "platform": sys.platform,
            "connection_id": str(uuid.uuid4()),
            "device_token": secrets.token_urlsafe(32),
        }
        write_private(config_path, config)
    client = Client(config)
    paired = client.api(
        "/pairing",
        {
            k: config[k]
            for k in ("connection_id", "device_token", "queue_name", "platform")
        },
    )
    if not paired["paired"]:
        print(
            "В WMS выберите склад и введите код подключения: " + paired["pairing_code"]
        )
        print("Код действует 15 минут. После подтверждения программа подключится сама.")
        while True:
            time.sleep(3)
            paired = client.api("/agent/heartbeat")
            if paired["paired"]:
                break
    config["warehouse_id"] = paired["warehouse_id"]
    write_private(config_path, config)
    enable_autostart(directory, Path(sys.executable).resolve())
    return config


def self_test() -> None:
    """Packaged executable can verify its own stdlib/queue boundary without Python installed."""
    if getattr(sys, "frozen", False):
        import ssl

        import certifi

        assert (
            ssl.create_default_context(cafile=certifi.where()).cert_store_stats()[
                "x509_ca"
            ]
            > 0
        )
    with tempfile.TemporaryDirectory(prefix="wms442-package-test-") as temp:
        directory = Path(temp)
        accepted = directory / "accepted.bin"
        if sys.platform == "win32":
            executable = directory / "synthetic-spooler.cmd"
            executable.write_text(
                '@echo off\ncopy /Y "%4" "'
                + str(accepted)
                + '" >NUL\necho request id is Synthetic_442-1 (1 file(s))\n'
            )
        else:
            executable = directory / "synthetic-spooler"
            executable.write_text(
                '#!/bin/sh\ncat "$4" > "'
                + str(accepted)
                + '"\necho "request id is Synthetic_442-1 (1 file(s))"\n'
            )
            executable.chmod(0o700)
        receipt = agent.submit_to_queue(
            b"%PDF-synthetic-no-real-printer",
            "application/pdf",
            "Synthetic_442",
            executable=str(executable),
        )
        assert accepted.read_bytes() == b"%PDF-synthetic-no-real-printer"
        outbox = directory / "inflight.json"
        write_private(outbox, {"phase": "result", "queue_receipt": receipt})
        assert read_private(outbox)["queue_receipt"] == "Synthetic_442-1"
        if sys.platform != "win32":
            assert outbox.stat().st_mode & 0o777 == 0o600
        with single_instance(directory):
            pass
    print(
        "Package self-test passed: synthetic queue only; physical printing unverified."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WMS: подключение ПК и печать этикеток"
    )
    parser.add_argument(
        "--self-test", action="store_true", help="Проверка пакета без WMS/принтера"
    )
    parser.add_argument(
        "--reconnect", action="store_true", help="Настроить новую очередь и подключение"
    )
    parser.add_argument(
        "--run", action="store_true", help="Работать с сохранённым подключением"
    )
    parser.add_argument(
        "--once", action="store_true", help="Проверить соединение и одно задание"
    )
    parser.add_argument(
        "--list-printers", action="store_true", help="Показать очереди ОС и выйти"
    )
    parser.add_argument(
        "--stop", action="store_true", help="Остановить фоновую программу Windows"
    )
    parser.add_argument(
        "--uninstall", action="store_true", help="Убрать автозапуск, сохранив настройку"
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Удалить локальное подключение и квитанцию",
    )
    parser.add_argument(
        "--confirm-reset",
        action="store_true",
        help="Подтвердить удаление локального состояния",
    )
    args = parser.parse_args(argv)
    try:
        if args.self_test:
            self_test()
            return 0
        directory = state_directory()
        if args.stop:
            request_stop(directory)
            return 0
        if args.uninstall:
            request_stop(directory)
            disable_autostart(directory)
            return 0
        if args.reset_state:
            if not args.confirm_reset:
                raise ValueError(
                    "Сброс удалит подключение и незавершённую квитанцию. "
                    "Повторите с --confirm-reset."
                )
            had_inflight = (directory / "inflight.json").exists()
            request_stop(directory)
            disable_autostart(directory)
            (directory / "connection.json").unlink(missing_ok=True)
            (directory / "inflight.json").unlink(missing_ok=True)
            print(
                "Состояние подключения удалено."
                + (
                    " Незавершённая печать требует проверки очереди."
                    if had_inflight
                    else ""
                )
            )
            return 0
        adapter = printer_adapter()
        if args.list_printers:
            print(
                "\n".join(adapter.queues())
                or "В ОС нет настроенных очередей принтеров."
            )
            return 0
        start_after_setup = False
        with single_instance(directory) as control:
            if args.reconnect:
                if (directory / "inflight.json").exists():
                    raise ValueError(
                        "Сначала восстановите квитанцию прежнего подключения"
                    )
                (directory / "connection.json").unlink(missing_ok=True)
            if args.run:
                config = read_private(directory / "connection.json")
            else:
                setup(directory, adapter)
                start_after_setup = True
            if args.run:
                client = Client(config)
                while True:
                    try:
                        status = client.api("/agent/heartbeat")
                        if not status["paired"]:
                            raise ValueError("Подключение ещё не подтверждено в WMS")
                        message = process_once(config, directory, client, adapter)
                        if message:
                            print(message, flush=True)
                    except (
                        OSError,
                        ValueError,
                        KeyError,
                        TypeError,
                        urllib.error.URLError,
                    ):
                        print(
                            "Связь с WMS недоступна. Квитанция сохранена; передача в ОС не повторяется.",
                            file=sys.stderr,
                            flush=True,
                        )
                        if args.once:
                            return 2
                    if args.once:
                        return 0
                    if control.wait(3):
                        return 0
        if start_after_setup:
            start_registered_background(directory)
            print(
                "Подключено. Фоновая программа запущена и будет запускаться автоматически."
            )
            return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
        # Never dump HTTP bodies, URLs or credential-bearing configuration.
        print(
            "Программа не подключена. Проверьте адрес WMS, очередь ОС и срок кода подключения.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
