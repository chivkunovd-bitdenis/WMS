"""WMS-604: loopback-only browser → native printer bridge, without print dialogs.

A fixed local queue is selected once. No HTTP input can select queues, URLs,
files or commands. Durable UUID receipts prevent repeat native submissions.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import time
import urllib.request
import sys
import threading
import uuid

import wms_print_agent as agent
import wms_print_runtime as runtime

PORT = 17845
ORIGINS = frozenset({"https://sellerfocus.pro", "https://wms.sellerfocus.pro"})
SIZES = {(58, 40), (60, 80), (60, 40), (70, 120)}
MAX_BODY = 3_000_000
MAX_PNG = 2_000_000
MAX_PIXELS = 4_194_304


class BridgeError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def prepare_label(value: object) -> tuple[str, str, bytes, int, int]:
    """Decode bounded PNG locally and render a fixed-size PDF, never open a URL."""
    import fitz
    from PIL import Image

    if not isinstance(value, dict) or set(value) != {
        "job_id", "image_data_url", "width_mm", "height_mm"
    }:
        raise BridgeError("Неверный запрос печати")
    job_id = value["job_id"]
    try:
        if not isinstance(job_id, str) or str(uuid.UUID(job_id)) != job_id:
            raise ValueError()
    except (ValueError, AttributeError):
        raise BridgeError("Неверный идентификатор печати") from None
    width, height = value["width_mm"], value["height_mm"]
    if type(width) is not int or type(height) is not int or (width, height) not in SIZES:
        raise BridgeError("Неподдерживаемый размер этикетки")
    image_url = value["image_data_url"]
    prefix = "data:image/png;base64,"
    if not isinstance(image_url, str) or not image_url.startswith(prefix):
        raise BridgeError("Требуется PNG-этикетка")
    try:
        data = base64.b64decode(image_url[len(prefix):], validate=True)
    except ValueError:
        raise BridgeError("Неверная PNG-этикетка") from None
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > MAX_PNG:
        raise BridgeError("Недопустимый размер или формат PNG")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format != "PNG" or not (0 < source.width <= 4096 and 0 < source.height <= 4096) or source.width * source.height > MAX_PIXELS:
                raise ValueError()
            source.load()
            # Re-encode only the verified raster, discarding metadata. PDF uses
            # lossless PNG data: JPEG would blur a thermal QR's module edges.
            normalized = io.BytesIO()
            source.convert("RGBA").save(normalized, "PNG")
            with fitz.open() as document:
                page = document.new_page(width=width / 25.4 * 72, height=height / 25.4 * 72)
                page.insert_image(page.rect, stream=normalized.getvalue(), keep_proportion=True)
                pdf = document.tobytes(deflate=True)
    except (OSError, ValueError, Image.DecompressionBombError):
        raise BridgeError("PNG-этикетка повреждена или слишком велика") from None
    digest = hashlib.sha256(data + f"/{width}/{height}".encode()).hexdigest()
    return job_id, digest, pdf, width, height


class SizedCupsAdapter(runtime.CupsAdapter):
    def submit(self, data, mime, queue, copies, width_mm=None, height_mm=None):
        agent.check_queue(queue)
        if queue not in self.queues():
            raise ValueError("Назначенный принтер отсутствует в ОС")
        if (width_mm, height_mm) not in SIZES:
            raise ValueError("Неверный размер этикетки")
        return agent.submit_to_queue(
            data, mime, queue, self.run, copies=copies,
            executable=["/usr/bin/lp", "-o", f"media=Custom.{width_mm}x{height_mm}mm", "-o", "fit-to-page=false"],
        )


def printer_adapter():
    return runtime.WindowsAdapter() if sys.platform == "win32" else SizedCupsAdapter()


def validate_queue(adapter, queue: str) -> None:
    if queue not in adapter.queues():
        raise ValueError("Назначенный принтер отсутствует в ОС")
    if isinstance(adapter, runtime.WindowsAdapter):
        native = adapter.modules["win32print"]
        handle = native.OpenPrinter(queue)
        try:
            info = native.GetPrinter(handle, 2)
        finally:
            native.ClosePrinter(handle)
        port = str(info.get("pPortName", "")).upper()
        driver = str(info.get("pDriverName", "")).upper()
        if any(item in port for item in ("FILE:", "PORTPROMPT", "SHRFAX")) or any(item in driver for item in ("PRINT TO PDF", "XPS", "ONENOTE", "FAX")):
            raise ValueError("Выберите термопринтер: эта очередь может открыть окно сохранения")


class PrinterBridge:
    def __init__(self, directory: Path, queue: str, adapter):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        runtime.restrict_private_directory(directory)
        self.queue, self.adapter = agent.check_queue(queue), adapter
        self.lock = threading.Lock()
        self.db = sqlite3.connect(directory / "scan-jobs.sqlite3", check_same_thread=False)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, digest TEXT NOT NULL, state TEXT NOT NULL, receipt TEXT)")
        self.db.commit()

    def print_image(self, value: object) -> dict:
        job_id, digest, data, width, height = prepare_label(value)
        with self.lock:
            prior = self.db.execute("SELECT digest,state,receipt FROM jobs WHERE id=?", (job_id,)).fetchone()
            if prior:
                if prior[0] != digest:
                    raise BridgeError("Этот запрос уже использован для другой этикетки", 409)
                if prior[1] != "submitted":
                    raise BridgeError("Результат предыдущей печати неизвестен. Проверьте очередь принтера; повтор не отправлен", 409)
                return {"job_id": job_id, "status": "submitted", "receipt": prior[2]}
            try:
                validate_queue(self.adapter, self.queue)
                if hasattr(self.adapter, "validate_layout"):
                    self.adapter.validate_layout(self.queue, width, height)
            except (ValueError, OSError) as error:
                raise BridgeError(str(error), 503) from None
            # Commit BEFORE crossing the native boundary. A crash, timeout or
            # missing receipt must never cause a second native submission.
            self.db.execute("INSERT INTO jobs VALUES (?,?,'unknown',NULL)", (job_id, digest))
            self.db.commit()
            try:
                receipt = self.adapter.submit(data, "application/pdf", self.queue, 1, width, height)
                if not receipt:
                    raise ValueError("Missing native receipt")
                self.db.execute("UPDATE jobs SET state='submitted',receipt=? WHERE id=?", (receipt, job_id))
                self.db.commit()
            except Exception:
                raise BridgeError("Результат печати неизвестен. Проверьте очередь принтера; автоматического повтора не будет", 409) from None
            return {"job_id": job_id, "status": "submitted", "receipt": receipt}


def make_server(bridge: PrinterBridge, port: int = PORT) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def trusted(self):
            return (
                self.client_address[0] == "127.0.0.1"
                and self.headers.get("Origin") in ORIGINS
                and self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            )

        def reply(self, status: int, value: dict):
            payload = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            if self.trusted():
                self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_OPTIONS(self):
            if not self.trusted() or self.path != "/print-image" or self.headers.get("Access-Control-Request-Method") != "POST":
                self.reply(403, {"error": "Доступ запрещён"})
                return
            requested = {v.strip().lower() for v in self.headers.get("Access-Control-Request-Headers", "").split(",") if v.strip()}
            if requested - {"content-type"}:
                self.reply(403, {"error": "Доступ запрещён"})
                return
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "POST")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if not self.trusted():
                self.reply(403, {"error": "Доступ запрещён"})
                return
            self.reply(200 if self.path == "/health" else 404, {"service": "wms-scan-bridge", "version": 1} if self.path == "/health" else {"error": "Не найдено"})

        def do_POST(self):
            if not self.trusted():
                self.reply(403, {"error": "Доступ запрещён"})
                return
            if self.path != "/print-image":
                self.reply(404, {"error": "Не найдено"})
                return
            try:
                if self.headers.get("Content-Type", "").lower() != "application/json" or self.headers.get("Transfer-Encoding"):
                    raise BridgeError("Требуется JSON-запрос")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    raise BridgeError("Недопустимый размер запроса", 413)
                value = json.loads(self.rfile.read(length))
                result = bridge.print_image(value)
            except BridgeError as error:
                self.reply(error.status, {"error": str(error)})
            except (ValueError, OSError):
                self.reply(400, {"error": "Не удалось прочитать запрос"})
            else:
                self.reply(200, result)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="WMS: печать по сканированию без окна браузера")
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--list-printers", action="store_true")
    parser.add_argument("--queue")
    args = parser.parse_args(argv)
    directory = runtime.state_directory() / "scan-check"
    try:
        adapter = printer_adapter()
        if args.list_printers:
            print("\n".join(adapter.queues()) or "В ОС нет принтеров")
            return 0
        with runtime.single_instance(directory):
            path = directory / "printer.json"
            if args.queue or args.setup or (not path.exists() and not args.run):
                queues = adapter.queues()
                if not queues:
                    raise ValueError("Сначала установите принтер в настройках ОС")
                queue = args.queue
                if not queue:
                    for index, name in enumerate(queues, 1):
                        print(f"{index}. {name}")
                    chosen = int(input("Номер термопринтера: "))
                    if not 1 <= chosen <= len(queues):
                        raise ValueError("Неверный номер принтера")
                    queue = queues[chosen - 1]
                validate_queue(adapter, queue)
                runtime.write_private(path, {"queue": queue})
            queue = runtime.read_private(path)["queue"]
            validate_queue(adapter, queue)
            if args.run:
                bridge = PrinterBridge(directory, queue, adapter)
                server = make_server(bridge)
                print(f"Принтер: {queue}. Печать подключена.", flush=True)
                try:
                    server.serve_forever()
                finally:
                    server.server_close()
                    bridge.db.close()
                return 0
        # Release the profile lock before the detached worker acquires it.
        command = [sys.executable]
        if not getattr(sys, "frozen", False):
            command.append(str(Path(__file__).resolve()))
        command.append("--run")
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {"start_new_session": True}
        with (directory / "bridge.log").open("a", encoding="utf-8") as log:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log, close_fds=True, **options)
        for _ in range(40):
            if process.poll() is not None:
                raise ValueError("Фоновая программа не запустилась; проверьте bridge.log")
            try:
                request = urllib.request.Request(f"http://127.0.0.1:{PORT}/health", headers={"Origin": "https://sellerfocus.pro"})
                with urllib.request.urlopen(request, timeout=0.2) as response:
                    if json.load(response).get("service") == "wms-scan-bridge":
                        print(f"Принтер: {queue}. Программа работает в фоне.\nhttps://sellerfocus.pro/packing-scan-check/", flush=True)
                        return 0
            except OSError:
                time.sleep(0.1)
        raise ValueError("Фоновая программа не ответила; проверьте bridge.log")
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"Печать не подключена: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
