"""Local Chrome -> default OS printer. No server account or pairing configuration."""
from __future__ import annotations

import argparse
import base64
import ctypes
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import wms_print_agent as agent
from wms_print_runtime import WindowsAdapter, state_directory

PORT = 17843
ORIGIN = f"http://127.0.0.1:{PORT}"
ALLOWED_ORIGINS = {ORIGIN, "https://sellerfocus.pro", "https://www.sellerfocus.pro", "https://wms.sellerfocus.pro", "https://web-production-9e7c1.up.railway.app"}
ASSETS = Path(__file__).resolve().parent / "direct-web"


class CupsOption(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char_p), ("value", ctypes.c_char_p)]


class MacPrinter:
    def __init__(self):
        self.lib = ctypes.CDLL("/usr/lib/libcups.2.dylib")
        self.lib.cupsPrintFile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                                          ctypes.c_int, ctypes.POINTER(CupsOption)]
        self.lib.cupsPrintFile.restype = ctypes.c_int
        self.lib.cupsGetDefault.argtypes = []
        self.lib.cupsGetDefault.restype = ctypes.c_char_p

    def default(self):
        value = self.lib.cupsGetDefault()
        return value.decode() if value else ""

    def submit_default(self, data, queue, width_mm=None, height_mm=None):
        options = (CupsOption * 3)(CupsOption(b"fit-to-page", b"true"),
                                  CupsOption(b"copies", b"1"),
                                  CupsOption(b"number-up", b"1"))
        with tempfile.TemporaryDirectory(prefix="wms-qr-") as directory:
            path = Path(directory) / "label.png"
            path.write_bytes(data)
            job_id = self.lib.cupsPrintFile(queue.encode(), os.fsencode(path), b"WMS QR", 3, options)
        if job_id <= 0:
            raise agent.UnknownPrintOutcome("macOS не подтвердила приём задания. Проверьте очередь принтера.")
        return f"{queue}-{job_id}"


class DefaultWindowsAdapter(WindowsAdapter):
    """Print one label using a per-job custom paper size in Windows GDI."""

    @staticmethod
    def _label_size(width_mm, height_mm):
        if (
            isinstance(width_mm, bool)
            or isinstance(height_mm, bool)
            or not isinstance(width_mm, (int, float))
            or not isinstance(height_mm, (int, float))
            or not 10 <= width_mm <= 300
            or not 10 <= height_mm <= 300
        ):
            raise ValueError("WMS не передала корректный размер этикетки")
        return round(float(width_mm) * 10), round(float(height_mm) * 10)

    def _create_sized_printer_dc(self, queue, width_mm, height_mm):
        """Create a job DC without changing the user's saved printer defaults."""
        width_tenths, height_tenths = self._label_size(width_mm, height_mm)
        printer = self.modules["win32print"].OpenPrinter(queue)
        try:
            details = self.modules["win32print"].GetPrinter(printer, 2)
            devmode = details.get("pDevMode")
            if devmode is None:
                raise ValueError("Windows не вернула параметры принтера по умолчанию")
            try:
                # DEVMODE paper dimensions use tenths of a millimetre.  PaperSize
                # must be zero when PaperWidth and PaperLength define a custom form.
                devmode.PaperSize = 0
                devmode.PaperWidth = width_tenths
                devmode.PaperLength = height_tenths
                devmode.Copies = 1
                devmode.Collate = 0
                devmode.Fields &= ~0x00000002  # DM_PAPERSIZE
                devmode.Fields |= (
                    0x00000004  # DM_PAPERLENGTH
                    | 0x00000008  # DM_PAPERWIDTH
                    | 0x00000100  # DM_COPIES
                    | 0x00008000  # DM_COLLATE
                )
                result = self.modules["win32print"].DocumentProperties(
                    0, printer, queue, devmode, devmode, 0x00000002 | 0x00000008
                )
                if result != 1:
                    raise ValueError("Драйвер не подтвердил размер задания печати")
                if (
                    devmode.Copies != 1
                    or not devmode.Fields & 0x00000100
                ):
                    raise ValueError(
                        "Драйвер не подтвердил одну копию задания печати"
                    )
                handle = self.modules["win32gui"].CreateDC(
                    "WINSPOOL", queue, devmode
                )
            except (AttributeError, TypeError) as exc:
                raise ValueError(
                    "Windows не смогла задать размер этикетки для задания печати"
                ) from exc
        finally:
            self.modules["win32print"].ClosePrinter(printer)
        return self.modules["win32ui"].CreateDCFromHandle(handle)

    @staticmethod
    def _validate_page_size(dc, width_mm, height_mm):
        dpi_x, dpi_y = dc.GetDeviceCaps(88), dc.GetDeviceCaps(90)
        physical_width_px = dc.GetDeviceCaps(110)
        physical_height_px = dc.GetDeviceCaps(111)
        printable_width_px = dc.GetDeviceCaps(8)
        printable_height_px = dc.GetDeviceCaps(10)
        if min(
            dpi_x, dpi_y, physical_width_px, physical_height_px,
            printable_width_px, printable_height_px,
        ) <= 0:
            raise ValueError("Драйвер принтера не вернул размер страницы")
        physical_width = physical_width_px / dpi_x * 25.4
        physical_height = physical_height_px / dpi_y * 25.4
        if (
            abs(physical_width - width_mm) > 1.5
            or abs(physical_height - height_mm) > 1.5
        ):
            raise ValueError(
                "Драйвер не применил размер этикетки "
                f"{width_mm} x {height_mm} мм"
            )

    def submit_default(self, data, queue, width_mm, height_mm):
        image = self.modules["Image"].open(io.BytesIO(data)).convert("RGB")
        dc = self._create_sized_printer_dc(queue, width_mm, height_mm)
        try:
            self._validate_page_size(dc, width_mm, height_mm)
            width, height = dc.GetDeviceCaps(8), dc.GetDeviceCaps(10)
            # Image aspect ratio is preserved; white margins cannot stretch QR.
            ratio = min(width / image.width, height / image.height)
            w, h = max(1, round(image.width * ratio)), max(1, round(image.height * ratio))
            x, y = (width - w) // 2, (height - h) // 2
            receipt = dc.StartDoc("WMS QR")
            if not isinstance(receipt, int) or receipt <= 0:
                raise agent.UnknownPrintOutcome("Windows не вернула номер задания")
            try:
                dc.StartPage()
                self.modules["ImageWin"].Dib(image).draw(dc.GetHandleOutput(), (x, y, x+w, y+h))
                dc.EndPage()
                dc.EndDoc()
            except BaseException:
                try:
                    dc.AbortDoc()
                except BaseException:
                    pass
                raise agent.UnknownPrintOutcome("Исход печати неизвестен. Проверьте принтер.") from None
            return f"windows-{receipt}"
        finally:
            dc.DeleteDC()


def default_printer():
    if sys.platform == "win32":
        import win32print
        name = win32print.GetDefaultPrinter()
    else:
        result = subprocess.run(["/usr/bin/lpstat", "-d"], capture_output=True,
                                text=True, timeout=10, env={**os.environ, "LC_ALL": "C"})
        name = result.stdout.partition(":")[2].strip()
    if not name:
        raise ValueError("В системе не выбран принтер по умолчанию")
    return agent.check_queue(name)


class Printer:
    def __init__(self, directory, submit=None):
        directory.mkdir(parents=True, exist_ok=True)
        self.db = directory / "direct-jobs.sqlite3"
        self.lock = threading.Lock()
        self.submit = submit
        self.adapter = (DefaultWindowsAdapter() if sys.platform == "win32" else MacPrinter()) if submit is None else None
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, hash TEXT, receipt TEXT)")

    def _submit(self, data, queue, width_mm, height_mm):
        return self.adapter.submit_default(data, queue, width_mm, height_mm)

    def print(self, body):
        key = body.get("idempotencyKey")
        image = body.get("imageDataUrl", "")
        if not isinstance(key, str) or not 1 <= len(key) <= 200 or not isinstance(image, str):
            raise ValueError("Некорректное задание печати")
        if not image.startswith("data:image/png;base64,"):
            raise ValueError("Ожидается PNG-этикетка")
        data = base64.b64decode(image.split(",", 1)[1], validate=True)
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 4_000_000:
            raise ValueError("Некорректная PNG-этикетка")
        width_mm, height_mm = DefaultWindowsAdapter._label_size(
            body.get("widthMm"), body.get("heightMm")
        )
        identity = data + f"|{width_mm}x{height_mm}".encode()
        digest = hashlib.sha256(identity).hexdigest()
        with self.lock, closing(sqlite3.connect(self.db)) as db:
            old = db.execute("SELECT hash, receipt FROM jobs WHERE id=?", (key,)).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError("Содержимое этого задания изменилось")
                if old[1] is None:
                    raise agent.UnknownPrintOutcome("Задание уже передавалось. Проверьте очередь принтера; повтор автоматически не отправлен.")
                return old[1]
            # Validate before crossing the irreversible OS-print boundary.
            queue = (self.adapter.default() if sys.platform == "darwin" else default_printer()) if self.submit is None else None
            if self.submit is None and not queue:
                raise ValueError("В системе не выбран принтер по умолчанию")
            db.execute("INSERT INTO jobs VALUES (?, ?, NULL)", (key, digest))
            db.commit()
            receipt = (
                self.submit(data)
                if self.submit
                else self._submit(data, queue, width_mm / 10, height_mm / 10)
            )
            db.execute("UPDATE jobs SET receipt=? WHERE id=?", (receipt, key))
            db.commit()
            return receipt


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Do not log labels or request bodies.

    def allowed(self):
        return (self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"
                and self.headers.get("Origin", ORIGIN) in ALLOWED_ORIGINS)

    def respond(self, status, value):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-WMS-Print")
            self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.respond(200 if self.allowed() else 403, {})

    def do_POST(self):
        if not self.allowed() or self.headers.get("X-WMS-Print") != "1":
            self.respond(403, {"error": "Источник печати не разрешён"})
            return
        if self.path != "/print":
            self.respond(404, {})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 6_000_000:
                raise ValueError("Некорректный размер задания")
            self.connection.settimeout(15)
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("Некорректное задание")
            receipt = self.server.printer.print(body)
            self.respond(200, {"receipt": receipt})
        except Exception as exc:
            self.respond(409, {"error": str(exc)})

    def do_GET(self):
        if not self.allowed():
            self.respond(403, {})
            return
        if self.path == "/health":
            try:
                self.respond(200, {"app": "WMS Print Direct", "printer": default_printer()})
            except Exception as exc:
                self.respond(503, {"app": "WMS Print Direct", "error": str(exc)})
            return
        relative = urlsplit(self.path).path.lstrip("/") or "packing-scan-check.html"
        target = (ASSETS / relative).resolve()
        if not target.is_relative_to(ASSETS.resolve()) or not target.is_file():
            self.respond(404, {})
            return
        mime = {".html": "text/html; charset=utf-8", ".js": "application/javascript",
                ".css": "text/css"}.get(target.suffix, "application/octet-stream")
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def main():
    # GitHub's English Windows runner and some operator PCs expose a legacy
    # console encoding that cannot represent Russian status text.  A status
    # line must never prevent the print service from starting.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        if sys.platform == "win32":
            DefaultWindowsAdapter._label_size(58, 40)
            DefaultWindowsAdapter()
        else:
            MacPrinter()
        print("WMS Print Direct: package OK")
        return
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print("WMS Print уже запущена либо локальный порт занят.", flush=True)
        return
    server.printer = Printer(state_directory() / "direct")
    print("WMS Print запущена. Сканируйте в WMS. Оставьте это окно открытым.", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
