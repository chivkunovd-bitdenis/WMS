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
import socket
import sqlite3
import subprocess
import sys
import threading
import tempfile
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import wms_print_agent as agent
from wms_print_runtime import WindowsAdapter, state_directory

PORT = 17843
ORIGIN = f"http://127.0.0.1:{PORT}"
ALLOWED_ORIGINS = {ORIGIN, "https://sellerfocus.pro", "https://www.sellerfocus.pro", "https://wms.sellerfocus.pro", "https://web-production-9e7c1.up.railway.app"}
ASSETS = Path(__file__).resolve().parent / "direct-web"
APP_NAME = "WMS Print Direct"
# The browser gives up after 30 s.  One deadline per request, counted from its
# start, covers waiting for the queue, the default printer lookup, preparation
# and the OS call, so the operator always gets an answer in time.
PRINT_TIMEOUT = 25
# A job is never started when less than this is left of the budget.
MINIMUM_TO_START = 6
MAX_PIXELS = 40_000_000
UNKNOWN_TEXT = "Исход печати неизвестен: задание уже отправлялось на принтер. Проверьте принтер; повтор автоматически не отправлен."
IN_PROGRESS_TEXT = "Это задание уже в работе, исход пока неизвестен. Проверьте принтер; повтор автоматически не отправлен."
HUNG_TEXT = "Принтер не отвечает. Перезапустите WMS Print и проверьте принтер."


def build_id():
    """Source commit from build.json next to the program, "dev" outside a package."""
    for base in (Path(sys.executable).parent, Path(__file__).resolve().parent):
        try:
            value = json.loads((base / "build.json").read_text(encoding="utf-8")).get("source_commit")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(value, str) and value:
            return value
    return "dev"


BUILD = build_id()


class PrintNotSent(ValueError):
    """Proven: nothing has reached the OS print system, a retry is safe."""


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

    def submit_default(self, data, queue, mark=None, width_mm=None, height_mm=None):
        options = (CupsOption * 3)(CupsOption(b"fit-to-page", b"true"),
                                  CupsOption(b"copies", b"1"),
                                  CupsOption(b"number-up", b"1"))
        with tempfile.TemporaryDirectory(prefix="wms-qr-") as directory:
            path = Path(directory) / "label.png"
            path.write_bytes(data)
            if mark is not None:
                mark()  # last step before the OS can receive the job
            job_id = self.lib.cupsPrintFile(queue.encode(), os.fsencode(path), b"WMS QR", 3, options)
        if job_id <= 0:
            raise agent.UnknownPrintOutcome("macOS не подтвердила приём задания. Проверьте очередь принтера.")
        return f"{queue}-{job_id}"


def flatten_png(Image, data):
    """Decode a label completely; paint transparency on white (never black)."""
    image = Image.open(io.BytesIO(data))
    if image.width * image.height > MAX_PIXELS:
        raise PrintNotSent("PNG-этикетка слишком большая")
    image.load()
    transparent = (image.mode in ("RGBA", "LA", "PA")
                   or (image.mode in ("P", "L", "RGB") and "transparency" in image.info))
    if transparent:
        rgba = image.convert("RGBA")
        canvas = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        canvas.alpha_composite(rgba)
        return canvas.convert("RGB")
    return image.convert("RGB")


def fit_layout(image_w, image_h, area_w, area_h, dpi_x, dpi_y):
    """Place one label proportionally *in millimetres*, not in device pixels.

    Printers may have different resolution on the two axes, so equal pixel
    scale would stretch the code.  The label is turned by 90 degrees only when
    the printable page has the other orientation and the turned label is
    clearly larger (more than 10 %).  Returns ``(rotate, x, y, w, h)`` in
    device pixels, where ``w``/``h`` already describe the turned label.
    """
    dpi_x = dpi_x if isinstance(dpi_x, int) and dpi_x > 0 else 1
    dpi_y = dpi_y if isinstance(dpi_y, int) and dpi_y > 0 else 1

    def scale(w, h):  # device pixels (x axis) per image pixel
        if dpi_x == dpi_y:  # the installed release's exact formula
            return min(area_w / w, area_h / h)
        return min(area_w / w, area_h / h * dpi_x / dpi_y)

    rotate = scale(image_h, image_w) > scale(image_w, image_h) * 1.1
    iw, ih = (image_h, image_w) if rotate else (image_w, image_h)
    t = scale(iw, ih)
    w, h = max(1, round(iw * t)), max(1, round(ih * t * dpi_y / dpi_x))
    return rotate, (area_w - w) // 2, (area_h - h) // 2, w, h


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

    def submit_default(self, data, queue, mark=None, width_mm=None, height_mm=None):
        # Everything up to ``mark()`` may fail without any job in the OS.
        Image = self.modules["Image"]
        image = flatten_png(Image, data)
        dc = self._create_sized_printer_dc(queue, width_mm, height_mm)
        try:
            self._validate_page_size(dc, width_mm, height_mm)
            width, height = dc.GetDeviceCaps(8), dc.GetDeviceCaps(10)
            rotate, x, y, w, h = fit_layout(
                image.width, image.height, width, height,
                dc.GetDeviceCaps(88), dc.GetDeviceCaps(90))  # LOGPIXELSX/Y
            if rotate:
                image = image.transpose(Image.Transpose.ROTATE_90)
            if mark is not None:
                mark()  # StartDoc is the point of no return
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
    def __init__(self, directory, submit=None, print_timeout=PRINT_TIMEOUT, minimum_to_start=MINIMUM_TO_START):
        directory.mkdir(parents=True, exist_ok=True)
        self.db = directory / "direct-jobs.sqlite3"
        self.lock = threading.Lock()   # short database sections only
        self.slot = threading.Lock()   # one OS print call at a time
        self.hung = False              # a worker outlived its deadline and still holds the slot
        self.inflight = set()          # keys being processed right now, guarded by self.lock
        self.print_timeout = print_timeout
        self.minimum_to_start = minimum_to_start
        self.submit = submit
        self.adapter = (DefaultWindowsAdapter() if sys.platform == "win32" else MacPrinter()) if submit is None else None
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, hash TEXT, receipt TEXT)")

    def _submit(self, data, queue, mark, width_mm, height_mm):
        return self.adapter.submit_default(data, queue, mark, width_mm, height_mm)

    def _execute(self, sql, params=(), timeout=10):
        with self.lock, closing(sqlite3.connect(self.db, timeout=max(0.05, timeout))) as db:
            db.execute(sql, params)
            db.commit()

    def _begin(self, key, digest, deadline):
        """Stored receipt, an error for a possibly sent or in-progress job, or None for a
        new key, which is registered as in progress under the same lock."""
        with self.lock:
            with closing(sqlite3.connect(self.db, timeout=max(0.05, min(10, deadline - time.monotonic())))) as db:
                old = db.execute("SELECT hash, receipt FROM jobs WHERE id=?", (key,)).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError("Содержимое этого задания изменилось")
                if old[1] is None:
                    raise agent.UnknownPrintOutcome(UNKNOWN_TEXT)
                return old[1]
            if key in self.inflight:
                raise agent.UnknownPrintOutcome(IN_PROGRESS_TEXT)
            self.inflight.add(key)
            return None

    def _lookup(self, key):
        with self.lock, closing(sqlite3.connect(self.db, timeout=10)) as db:
            return db.execute("SELECT hash, receipt FROM jobs WHERE id=?", (key,)).fetchone()

    def _work(self, key, digest, data, size, deadline, gate, outcome):
        """Runs the blocking OS call; owns the slot until the call really ends.

        ``gate`` guards the point of no return: once the request has timed out
        no job may be started, and the answer given to the browser stays true.
        """
        try:
            def mark():
                late = PrintNotSent("Время ожидания истекло. Это задание не отправлялось; повторите.")
                with gate["lock"]:
                    if gate["cancelled"] or deadline - time.monotonic() < self.minimum_to_start:
                        raise late
                    # The wait for a locked journal is part of the same budget.
                    self._execute("INSERT INTO jobs VALUES (?, ?, NULL)", (key, digest),
                                  timeout=deadline - time.monotonic())
                    if gate["cancelled"] or deadline - time.monotonic() < self.minimum_to_start:
                        self._execute("DELETE FROM jobs WHERE id=? AND receipt IS NULL", (key,), timeout=2)
                        raise late  # the budget went on the journal: not sent, mark removed
                    gate["marked"] = True

            try:
                if self.submit:
                    mark()
                    receipt = self.submit(data)
                else:
                    queue = self.adapter.default() if sys.platform == "darwin" else default_printer()
                    if not queue:
                        raise ValueError("В системе не выбран принтер по умолчанию")
                    receipt = self._submit(data, queue, mark, size[0] / 10, size[1] / 10)
            except PrintNotSent:
                if gate["marked"]:  # proven: the OS never received the job
                    self._execute("DELETE FROM jobs WHERE id=? AND receipt IS NULL", (key,), timeout=2)
                    gate["marked"] = False
                raise
            try:
                self._execute("UPDATE jobs SET receipt=? WHERE id=?", (receipt, key))
            except Exception:
                pass  # the job is in the OS queue; a repeat is answered as "already sent"
            outcome["receipt"] = receipt
        except BaseException as exc:
            outcome["error"] = exc
        finally:
            self.hung = False
            with self.lock:
                self.inflight.discard(key)
            self.slot.release()

    def print(self, body, started=None):
        deadline = (time.monotonic() if started is None else started) + self.print_timeout
        key = body.get("idempotencyKey")
        image = body.get("imageDataUrl", "")
        if not isinstance(key, str) or not 1 <= len(key) <= 200 or not isinstance(image, str):
            raise ValueError("Некорректное задание печати")
        if not image.startswith("data:image/png;base64,"):
            raise ValueError("Ожидается PNG-этикетка")
        data = base64.b64decode(image.split(",", 1)[1], validate=True)
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 4_000_000:
            raise ValueError("Некорректная PNG-этикетка")
        width_tenths, height_tenths = DefaultWindowsAdapter._label_size(body.get("widthMm"), body.get("heightMm"))
        # The size is part of the job identity (same formula as the installed 1bdd6cdf release).
        digest = hashlib.sha256(data + f"|{width_tenths}x{height_tenths}".encode()).hexdigest()
        size = (width_tenths, height_tenths)
        # The key's own history is answered first, never behind the print queue; a new
        # key is registered as in progress at once, so a parallel repeat hears "unknown".
        known = self._begin(key, digest, deadline)
        if known is not None:
            return known
        started_worker = False
        try:
            if not self.slot.acquire(timeout=max(0.0, deadline - time.monotonic())):
                if self.hung:
                    raise PrintNotSent(HUNG_TEXT + " Это задание не отправлялось.")
                raise PrintNotSent("Принтер занят предыдущим заданием. Это задание не отправлялось; повторите.")
            try:
                if deadline - time.monotonic() < self.minimum_to_start:
                    raise PrintNotSent("Время ожидания истекло. Это задание не отправлялось; повторите.")
                outcome = {}
                gate = {"lock": threading.Lock(), "cancelled": False, "marked": False}
                worker = threading.Thread(target=self._work, args=(key, digest, data, size, deadline, gate, outcome), daemon=True)
                worker.start()
                started_worker = True  # the worker releases the slot and the in-progress mark
            finally:
                if not started_worker:
                    self.slot.release()
        finally:
            if not started_worker:
                with self.lock:
                    self.inflight.discard(key)
        worker.join(max(0.0, deadline - time.monotonic()))
        if worker.is_alive():
            with gate["lock"]:
                gate["cancelled"] = True  # a worker still before its mark can no longer start the job
                marked = gate["marked"]
            self.hung = True
            if marked:
                raise agent.UnknownPrintOutcome(HUNG_TEXT + " Задание могло уйти в печать; повтор автоматически не отправлен.")
            raise PrintNotSent(HUNG_TEXT + " Это задание не отправлялось.")
        if "error" in outcome:
            raise outcome["error"]
        return outcome["receipt"]


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
        started = time.monotonic()
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
            receipt = self.server.printer.print(body, started)
            self.respond(200, {"receipt": receipt})
        except Exception as exc:
            self.respond(409, {"error": str(exc)})

    def do_GET(self):
        if not self.allowed():
            self.respond(403, {})
            return
        if self.path == "/health":
            try:
                if self.server.printer.hung:
                    raise RuntimeError(HUNG_TEXT)
                self.respond(200, {"app": APP_NAME, "build": BUILD, "printer": default_printer()})
            except Exception as exc:
                self.respond(503, {"app": APP_NAME, "build": BUILD, "error": str(exc)})
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


class DirectServer(ThreadingHTTPServer):
    """Local HTTP server that refuses a port already owned by someone else.

    On Windows SO_REUSEADDR lets a second process bind the same port and steal
    connections, so it is replaced by SO_EXCLUSIVEADDRUSE.
    """
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self):
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", -5), 1)
        super().server_bind()


_instance_guard = []  # keeps the lock/mutex alive until the process exits


def acquire_instance(directory):
    """Take the per-user "one WMS Print" lock; False when another copy holds it."""
    directory.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        name = "Local\\WMSPrintDirect-" + hashlib.sha256(str(directory).encode()).hexdigest()[:24]
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            raise OSError("Windows не смогла создать блокировку программы печати")
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(ctypes.c_void_p(handle))
            return False
        _instance_guard.append(handle)
        return True
    import fcntl
    lock = open(directory / "instance.lock", "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        return False
    _instance_guard.append(lock)
    return True


def running_instance(port=PORT, attempts=1, delay=0.3):
    """(build id, /health was OK) of a live WMS Print on the port, else None (never touches the process)."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(attempts):
        try:
            healthy = True
            try:
                with opener.open(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                    body = response.read()
            except urllib.error.HTTPError as error:  # 503 still names the program
                body, healthy = error.read(), False
            value = json.loads(body)
            if value.get("app") == APP_NAME:
                return str(value.get("build", "")), healthy
        except (OSError, ValueError, AttributeError):
            pass
        if attempt + 1 < attempts:
            time.sleep(delay)
    return None


def existing_copy_is_current(attempts):
    """True: the running copy is this very build (quiet exit).  False: nothing answers.
    Another build: SystemExit with an instruction, the running copy is never touched."""
    found = running_instance(attempts=attempts)
    if found is None:
        return False
    running, healthy = found
    if running != BUILD:
        print("Запущена другая версия WMS Print. Закройте её и откройте эту снова.", file=sys.stderr, flush=True)
        sys.exit(1)
    if not healthy:  # a /health error (no printer, hung driver) is not "working"
        print("Эта версия WMS Print уже запущена, но проверка принтера (/health) не проходит. "
              "Проверьте принтер или закройте программу и откройте её снова.", file=sys.stderr, flush=True)
        sys.exit(1)
    print("WMS Print уже запущена и работает. Это окно можно закрыть.", flush=True)
    return True


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
    directory = state_directory() / "direct"
    if not acquire_instance(directory):
        # Opened twice: the first copy is working, so stay quiet and succeed.
        if existing_copy_is_current(10):
            return
        print("WMS Print уже открыта, но не отвечает. Закройте её окно и откройте программу снова.", file=sys.stderr, flush=True)
        sys.exit(1)
    try:
        server = DirectServer(("127.0.0.1", PORT), Handler)
    except OSError:
        if existing_copy_is_current(3):  # an older copy without the lock is another build
            return
        print(f"Порт {PORT} занят другой программой. WMS Print её не закрывает: "
              "закройте эту программу или перезагрузите компьютер.", file=sys.stderr, flush=True)
        sys.exit(1)
    server.printer = Printer(directory)
    print("WMS Print запущена. Сканируйте в WMS. Оставьте это окно открытым.", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
