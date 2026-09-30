"""Local Chrome -> default OS printer. No server account or pairing configuration."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import wms_print_agent as agent
from wms_print_runtime import WindowsAdapter, state_directory

PORT = 17843
ORIGIN = f"http://127.0.0.1:{PORT}"
ALLOWED_ORIGINS = {ORIGIN, "https://sellerfocus.pro", "https://www.sellerfocus.pro"}
ASSETS = Path(__file__).resolve().parent / "direct-web"


class DefaultWindowsAdapter(WindowsAdapter):
    """Fit one label proportionally to the installed driver's printable page."""
    @staticmethod
    def _validate_page_size(dc, width_mm, height_mm):
        if min(dc.GetDeviceCaps(8), dc.GetDeviceCaps(10)) <= 0:
            raise ValueError("Драйвер принтера не вернул печатаемую область")

    def submit_default(self, data, queue):
        image = self.modules["Image"].open(io.BytesIO(data)).convert("RGB")
        dc = self._create_printer_dc(queue)
        try:
            self._validate_page_size(dc, None, None)
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
        self.adapter = DefaultWindowsAdapter() if submit is None and sys.platform == "win32" else None
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, hash TEXT, receipt TEXT)")

    def _submit(self, data, queue):
        if sys.platform == "win32":
            return self.adapter.submit_default(data, queue)
        return agent.submit_to_queue(data, "image/png", queue,
                                     executable=["/usr/bin/lp", "-o", "fit-to-page", "-o", "number-up=1"])

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
        with self.lock, sqlite3.connect(self.db) as db:
            old = db.execute("SELECT hash, receipt FROM jobs WHERE id=?", (key,)).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError("Содержимое этого задания изменилось")
                if old[1] is None:
                    raise agent.UnknownPrintOutcome("Задание уже передавалось. Проверьте очередь принтера; повтор автоматически не отправлен.")
                return old[1]
            # Validate before crossing the irreversible OS-print boundary.
            queue = default_printer() if self.submit is None else None
            db.execute("INSERT INTO jobs VALUES (?, ?, NULL)", (key, digest))
            db.commit()
            receipt = self.submit(data) if self.submit else self._submit(data, queue)
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


def open_chrome():
    if sys.platform == "darwin":
        subprocess.run(["/usr/bin/open", "-a", "Google Chrome", ORIGIN], check=True)
    elif sys.platform == "win32":
        import winreg
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root, r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as key:
                    chrome, _ = winreg.QueryValueEx(key, None)
                subprocess.Popen([chrome, ORIGIN])
                return
            except OSError:
                continue
        raise RuntimeError("Установите Google Chrome")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        assert (ASSETS / "packing-scan-check.html").is_file()
        print("WMS Print Direct: package OK")
        return
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        if not args.serve:
            open_chrome()
        return
    server.printer = Printer(state_directory() / "direct")
    if not args.serve:
        open_chrome()
    server.serve_forever()


if __name__ == "__main__":
    main()
