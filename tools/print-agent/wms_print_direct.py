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
# The browser gives up after 30 s.  The program must answer before that, so a
# hung driver never leaves the operator without a clear message.
PRINT_TIMEOUT = 25
# How long a new job waits for the previous one to leave the OS print call.
SLOT_WAIT = 10
MAX_PIXELS = 40_000_000


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

    def submit_default(self, data, queue, mark=None):
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

    def scale(w, h):  # inches per image pixel
        return min(area_w / (w * dpi_x), area_h / (h * dpi_y))

    rotate = scale(image_h, image_w) > scale(image_w, image_h) * 1.1
    iw, ih = (image_h, image_w) if rotate else (image_w, image_h)
    t = scale(iw, ih)
    w, h = max(1, round(iw * t * dpi_x)), max(1, round(ih * t * dpi_y))
    return rotate, (area_w - w) // 2, (area_h - h) // 2, w, h


class DefaultWindowsAdapter(WindowsAdapter):
    """Fit one label proportionally to the installed driver's printable page."""
    @staticmethod
    def _validate_page_size(dc, width_mm, height_mm):
        if min(dc.GetDeviceCaps(8), dc.GetDeviceCaps(10)) <= 0:
            raise ValueError("Драйвер принтера не вернул печатаемую область")

    def submit_default(self, data, queue, mark=None):
        # Everything up to ``mark()`` may fail without any job in the OS.
        Image = self.modules["Image"]
        image = flatten_png(Image, data)
        dc = self._create_printer_dc(queue)
        try:
            self._validate_page_size(dc, None, None)
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
    def __init__(self, directory, submit=None, print_timeout=PRINT_TIMEOUT, slot_wait=SLOT_WAIT):
        directory.mkdir(parents=True, exist_ok=True)
        self.db = directory / "direct-jobs.sqlite3"
        self.lock = threading.Lock()   # short database sections only
        self.slot = threading.Lock()   # one OS print call at a time
        self.print_timeout = print_timeout
        self.slot_wait = slot_wait
        self.submit = submit
        self.adapter = (DefaultWindowsAdapter() if sys.platform == "win32" else MacPrinter()) if submit is None else None
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, hash TEXT, receipt TEXT)")

    def _submit(self, data, queue, mark):
        return self.adapter.submit_default(data, queue, mark)

    def _execute(self, sql, params=()):
        with self.lock, closing(sqlite3.connect(self.db, timeout=10)) as db:
            db.execute(sql, params)
            db.commit()

    def _lookup(self, key):
        with self.lock, closing(sqlite3.connect(self.db, timeout=10)) as db:
            return db.execute("SELECT hash, receipt FROM jobs WHERE id=?", (key,)).fetchone()

    def _work(self, key, digest, data, queue, outcome):
        """Runs the blocking OS call; owns the slot until the call really ends."""
        marked = []

        def mark():
            self._execute("INSERT INTO jobs VALUES (?, ?, NULL)", (key, digest))
            marked.append(True)

        try:
            try:
                if self.submit:
                    mark()
                    receipt = self.submit(data)
                else:
                    receipt = self._submit(data, queue, mark)
            except PrintNotSent:
                if marked:  # proven: the OS never received the job
                    self._execute("DELETE FROM jobs WHERE id=? AND receipt IS NULL", (key,))
                raise
            try:
                self._execute("UPDATE jobs SET receipt=? WHERE id=?", (receipt, key))
            except Exception:
                pass  # the job is in the OS queue; a repeat is answered as "already sent"
            outcome["receipt"] = receipt
        except BaseException as exc:
            outcome["error"] = exc
        finally:
            self.slot.release()

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
        digest = hashlib.sha256(data).hexdigest()
        if not self.slot.acquire(timeout=self.slot_wait):
            raise PrintNotSent("Принтер ещё занят предыдущим заданием. Это задание не отправлялось; повторите через минуту.")
        started = False
        try:
            old = self._lookup(key)  # after the slot: a parallel twin has finished
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
            outcome = {}
            worker = threading.Thread(target=self._work, args=(key, digest, data, queue, outcome), daemon=True)
            worker.start()
            started = True  # the worker releases the slot
        finally:
            if not started:
                self.slot.release()
        worker.join(self.print_timeout)
        if worker.is_alive():
            raise agent.UnknownPrintOutcome(
                f"Принтер не ответил за {self.print_timeout} с. Задание могло уйти в печать; "
                "проверьте очередь принтера. Повтор автоматически не отправлен.")
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
                self.respond(200, {"app": APP_NAME, "printer": default_printer()})
            except Exception as exc:
                self.respond(503, {"app": APP_NAME, "error": str(exc)})
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
    """True when a live WMS Print answers on the port (never touches the process)."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(attempts):
        try:
            try:
                with opener.open(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                    body = response.read()
            except urllib.error.HTTPError as error:  # 503 still names the program
                body = error.read()
            if json.loads(body).get("app") == APP_NAME:
                return True
        except (OSError, ValueError, AttributeError):
            pass
        if attempt + 1 < attempts:
            time.sleep(delay)
    return False


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
        DefaultWindowsAdapter() if sys.platform == "win32" else MacPrinter()
        print("WMS Print Direct: package OK")
        return
    directory = state_directory() / "direct"
    if not acquire_instance(directory):
        # Opened twice: the first copy is working, so stay quiet and succeed.
        if running_instance(attempts=10):
            print("WMS Print уже запущена и работает. Это окно можно закрыть.", flush=True)
            return
        print("WMS Print уже открыта, но не отвечает. Закройте её окно и откройте программу снова.", file=sys.stderr, flush=True)
        sys.exit(1)
    try:
        server = DirectServer(("127.0.0.1", PORT), Handler)
    except OSError:
        if running_instance(attempts=3):  # an older copy without the lock
            print("WMS Print уже запущена и работает. Это окно можно закрыть.", flush=True)
            return
        print(f"Порт {PORT} занят другой программой. WMS Print её не закрывает: "
              "закройте эту программу или перезагрузите компьютер.", file=sys.stderr, flush=True)
        sys.exit(1)
    server.printer = Printer(directory)
    print("WMS Print запущена. Сканируйте в WMS. Оставьте это окно открытым.", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
