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
from urllib.parse import unquote
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

import wms_print_agent as agent
from wms_print_runtime import WindowsAdapter, state_directory

PORT = 17843
ORIGIN = f"http://127.0.0.1:{PORT}"
ALLOWED_ORIGINS = {
    ORIGIN,
    "https://sellerfocus.pro",
    "https://www.sellerfocus.pro",
    "https://wms.sellerfocus.pro",
    "https://web-production-9e7c1.up.railway.app",
}
ASSETS = Path(__file__).resolve().parent / "direct-web"


class CupsOption(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char_p), ("value", ctypes.c_char_p)]


class MacPrinter:
    def __init__(self):
        self.lib = ctypes.CDLL("/usr/lib/libcups.2.dylib")
        self.lib.cupsPrintFile.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.POINTER(CupsOption),
        ]
        self.lib.cupsPrintFile.restype = ctypes.c_int
        self.lib.cupsGetDefault.argtypes = []
        self.lib.cupsGetDefault.restype = ctypes.c_char_p

    def default(self):
        value = self.lib.cupsGetDefault()
        return value.decode() if value else ""

    def submit_default(
        self, data, queue, width_mm=None, height_mm=None, title="WMS QR"
    ):
        options = (CupsOption * 4)(
            CupsOption(b"fit-to-page", b"true"),
            CupsOption(b"copies", b"1"),
            CupsOption(b"number-up", b"1"),
            CupsOption(b"media", f"Custom.{width_mm:g}x{height_mm:g}mm".encode()),
        )
        with tempfile.TemporaryDirectory(prefix="wms-qr-") as directory:
            path = Path(directory) / "label.png"
            path.write_bytes(data)
            job_id = self.lib.cupsPrintFile(
                queue.encode(), os.fsencode(path), title.encode(), 4, options
            )
        if job_id <= 0:
            raise agent.UnknownPrintOutcome(
                "macOS не подтвердила приём задания. Проверьте очередь принтера."
            )
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
                if devmode.Copies != 1 or not devmode.Fields & 0x00000100:
                    raise ValueError("Драйвер не подтвердил одну копию задания печати")
                handle = self.modules["win32gui"].CreateDC("WINSPOOL", queue, devmode)
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
        if (
            min(
                dpi_x,
                dpi_y,
                physical_width_px,
                physical_height_px,
                printable_width_px,
                printable_height_px,
            )
            <= 0
        ):
            raise ValueError("Драйвер принтера не вернул размер страницы")
        physical_width = physical_width_px / dpi_x * 25.4
        physical_height = physical_height_px / dpi_y * 25.4
        if (
            abs(physical_width - width_mm) > 1.5
            or abs(physical_height - height_mm) > 1.5
        ):
            raise ValueError(
                f"Драйвер не применил размер этикетки {width_mm} x {height_mm} мм"
            )

    def submit_default(self, data, queue, width_mm, height_mm, title="WMS QR"):
        dc = None
        started = False
        try:
            image = self.modules["Image"].open(io.BytesIO(data)).convert("RGB")
            dc = self._create_sized_printer_dc(queue, width_mm, height_mm)
            self._validate_page_size(dc, width_mm, height_mm)
            width, height = dc.GetDeviceCaps(8), dc.GetDeviceCaps(10)
            ratio = min(width / image.width, height / image.height)
            w, h = (
                max(1, round(image.width * ratio)),
                max(1, round(image.height * ratio)),
            )
            x, y = (width - w) // 2, (height - h) // 2
            # Before entering StartDoc no external job exists. From this line onward
            # any exception type is ambiguous unless a receipt is retained.
            started = True
            receipt = dc.StartDoc(title)
            if not isinstance(receipt, int) or receipt <= 0:
                raise agent.UnknownPrintOutcome("Windows не вернула номер задания")
            dc.StartPage()
            self.modules["ImageWin"].Dib(image).draw(
                dc.GetHandleOutput(), (x, y, x + w, y + h)
            )
            dc.EndPage()
            dc.EndDoc()
            return f"windows-{receipt}"
        except Exception as exc:
            if started:
                try:
                    dc.AbortDoc()
                except Exception:
                    pass
                raise agent.UnknownPrintOutcome(
                    f"Исход печати неизвестен. {exc}"
                ) from exc
            raise BeforeSubmitError(str(exc)) from exc
        finally:
            if dc is not None:
                try:
                    dc.DeleteDC()
                except Exception:
                    pass  # Cleanup cannot turn a known pre-submit failure into ambiguity.


def default_printer():
    if sys.platform == "win32":
        import win32print

        name = win32print.GetDefaultPrinter()
    else:
        result = subprocess.run(
            ["/usr/bin/lpstat", "-d"],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "LC_ALL": "C"},
        )
        name = result.stdout.partition(":")[2].strip()
    if not name:
        raise ValueError("В системе не выбран принтер по умолчанию")
    return agent.check_queue(name)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class BeforeSubmitError(RuntimeError):
    pass


def native_command(*args):
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command.append(str(Path(__file__).resolve()))
    return command + list(args)


def helper(*args, timeout=12):
    try:
        result = subprocess.run(
            native_command(*args),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise BeforeSubmitError(f"Системная команда не запустилась: {exc}") from exc
    if result.returncode:
        raise agent.UnknownPrintOutcome(
            "Системная команда завершилась без подтверждённого результата"
        )
    value = json.loads(result.stdout)
    if value.get("error"):
        error = (
            BeforeSubmitError
            if value.get("beforeSubmit")
            else agent.UnknownPrintOutcome
        )
        raise error(value["error"])
    return value


def observe_windows(job):
    import win32print

    queue = job.get("queue")
    if not queue:
        return {"error": "Сохранённая очередь отсутствует"}
    handle = win32print.OpenPrinter(queue)
    try:
        items = win32print.EnumJobs(handle, 0, 10000, 1)
        wanted = int(job["receipt"].rsplit("-", 1)[1]) if job.get("receipt") else None
        matches = [
            item
            for item in items
            if (
                item["JobId"] == wanted
                if wanted
                else item.get("pDocument") == job.get("title")
            )
            and (not job.get("title") or item.get("pDocument") == job["title"])
        ]
        details = win32print.GetPrinter(handle, 2)
        result = {
            "matches": len(matches),
            "printerStatus": details.get("Status"),
            "physicalConfirmationSupported": False,
        }
        if len(matches) == 1:
            item = matches[0]
            flags = item.get("Status", 0)
            # JOB_STATUS_* values: deleted/errors/paused must not become success.
            state = (
                "canceled"
                if flags & (4 | 256)
                else "stopped"
                if flags & (2 | 32 | 64 | 512 | 1024)
                else "held"
                if flags & 1
                else "completed"
                if flags & (128 | 4096)
                else "processing"
                if flags & 16
                else "pending"
            )
            result.update(
                receipt=f"windows-{item['JobId']}",
                status=state,
                jobStatus=flags,
                jobStateMessage=item.get("pStatus") or "",
            )
        return result
    finally:
        win32print.ClosePrinter(handle)


class Printer:
    def __init__(
        self, directory, submit=None, queue=None, observe=None, auto_work=True
    ):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = directory / "direct-jobs.sqlite3"
        self.lock = threading.RLock()
        self.submit = submit
        self.queue = queue or (lambda: helper("--system-default", timeout=5)["queue"])
        self.observe = observe or (
            lambda job: helper(
                "--observe-job", str(self.db), job["idempotencyKey"], timeout=8
            )
        )
        self.auto_work = auto_work
        self.active = set()
        self.observing = set()
        self.diagnostics = []
        self.storage_error = None
        self.worker = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="print-submit"
        )
        self._lock_file = open(directory / "runtime.lock", "a+b")
        try:
            if sys.platform == "win32":
                import msvcrt

                self._lock_file.seek(0)
                if not self._lock_file.read(1):
                    self._lock_file.write(b"0")
                    self._lock_file.flush()
                self._lock_file.seek(0)
                msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lock_file.close()
            raise RuntimeError(
                "Журнал уже открыт другой программой WMS Print"
            ) from None
        try:
            with closing(self.connect()) as db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, hash TEXT, receipt TEXT)"
                )
                columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
                if "image" not in columns:
                    db.execute("ALTER TABLE jobs ADD COLUMN image BLOB")
                if "metadata" not in columns:
                    db.execute("ALTER TABLE jobs ADD COLUMN metadata TEXT")
                db.commit()
                if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise RuntimeError("Проверка целостности журнала не пройдена")
                for (key,) in db.execute("SELECT id FROM jobs").fetchall():
                    try:
                        job = self._read(db, key)
                        if job["status"] == "submitting":
                            self._save(
                                db,
                                self._change(
                                    job,
                                    "unknown",
                                    "Программа завершилась во время передачи; требуется сверка очереди",
                                ),
                            )
                    except (ValueError, KeyError, TypeError) as exc:
                        self.diagnostics.append(
                            f"Повреждена запись {key}: {exc}; исходник сохранён"
                        )
                saved = [
                    row[0]
                    for row in db.execute("SELECT id FROM jobs").fetchall()
                    if self._safe_status(db, row[0]) == "saved"
                ]
        except Exception as exc:
            self.storage_error = (
                f"Журнал недоступен; печать остановлена для защиты от дублей: {exc}"
            )
            self.diagnostics.append(self.storage_error)
            saved = []
        if auto_work:
            for key in saved:
                self._schedule(key)

    def connect(self):
        db = sqlite3.connect(self.db, timeout=10)
        try:
            db.execute("PRAGMA synchronous=FULL")
        except Exception:
            db.close()
            raise
        return db

    def close(self):
        self.worker.shutdown(wait=True)
        self._lock_file.close()

    def _safe_status(self, db, key):
        try:
            return self._read(db, key)["status"]
        except Exception:
            return "corrupt"

    def _read(self, db, key):
        row = db.execute(
            "SELECT hash,receipt,image IS NOT NULL,metadata FROM jobs WHERE id=?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        if row[3] is not None:
            job = json.loads(row[3])
            if (
                not isinstance(job, dict)
                or job.get("idempotencyKey") != key
                or job.get("hash") != row[0]
            ):
                raise ValueError(
                    "Ключ или содержимое записи повреждены; повтор запрещён"
                )
            if job.get("status") not in (
                "saved",
                "submitting",
                "unknown",
                "accepted",
                "pending",
                "held",
                "processing",
                "stopped",
                "canceled",
                "aborted",
                "completed",
                "failed_before_submit",
            ):
                raise ValueError("Повреждено состояние задания")
            if not job.get("legacy"):
                DefaultWindowsAdapter._label_size(
                    job.get("widthMm"), job.get("heightMm")
                )
                if not row[2] or not str(job.get("title", "")).startswith("WMS-"):
                    raise ValueError("Повреждены изображение или имя задания")
            return job
        return dict(
            idempotencyKey=key,
            hash=row[0],
            receipt=row[1],
            legacy=True,
            status="accepted" if row[1] else "unknown",
            createdAt="unknown",
            updatedAt="unknown",
            reason="Старый журнал: изображение, размер, очередь и физический результат отсутствуют",
            context={},
            observations=[],
            queue=None,
        )

    def _save(self, db, job):
        db.execute(
            "UPDATE jobs SET receipt=?,metadata=? WHERE id=?",
            (
                job.get("receipt"),
                json.dumps(job, ensure_ascii=False),
                job["idempotencyKey"],
            ),
        )
        db.commit()

    @staticmethod
    def _change(job, status, reason):
        job = {**job, "observations": list(job.get("observations", []))}
        if job.get("status") != status or job.get("reason") != reason:
            job["observations"].append(f"{timestamp()} {status}: {reason}")
        job.update(status=status, reason=reason, updatedAt=timestamp())
        return job

    def _writable(self):
        if self.storage_error:
            raise RuntimeError(self.storage_error)

    def get(self, key, include_reprints=True):
        with self.lock, closing(self.connect()) as db:
            job = self._read(db, key)
            if job is None:
                self._writable()
                return None
            result = {
                **job,
                "imageAvailable": not job.get("legacy", False),
                "paperStatus": "unconfirmed",
                "physicalConfirmationSupported": False,
            }
            if include_reprints:
                children = []
                for (child_key,) in db.execute("SELECT id FROM jobs").fetchall():
                    try:
                        child = self._read(db, child_key)
                        if child.get("parentKey") == key:
                            children.append({**child, "paperStatus": "unconfirmed"})
                    except (ValueError, KeyError, TypeError):
                        continue
                found = {child["idempotencyKey"] for child in children}
                for child in job.get("reprintIntentKeys", []):
                    if child not in found:
                        children.append(
                            dict(
                                idempotencyKey=child,
                                parentKey=key,
                                hash=job["hash"],
                                status="unknown",
                                reason="Сохранено намерение повторной печати, но описание дочернего задания недоступно; автоматического повтора нет",
                                paperStatus="unconfirmed",
                                imageAvailable=False,
                                legacy=False,
                            )
                        )
                result["reprints"] = children
            return result

    def list(self):
        with self.lock:
            jobs = []
            try:
                with closing(self.connect()) as db:
                    for (key,) in db.execute("SELECT id FROM jobs"):
                        try:
                            jobs.append(self.get(key, include_reprints=False))
                        except Exception as exc:
                            message = (
                                f"Повреждена запись {key}: {exc}; исходник сохранён"
                            )
                            if message not in self.diagnostics:
                                self.diagnostics.append(message)
            except sqlite3.DatabaseError as exc:
                message = f"Журнал недоступен: {exc}"
                if message not in self.diagnostics:
                    self.diagnostics.append(message)
            return {
                "jobs": sorted(jobs, key=lambda j: j["updatedAt"], reverse=True),
                "diagnostics": list(self.diagnostics),
            }

    def image(self, key):
        with self.lock, closing(self.connect()) as db:
            job = self._read(db, key)
            row = db.execute("SELECT image FROM jobs WHERE id=?", (key,)).fetchone()
            if not job or not row or row[0] is None:
                raise ValueError("Исходное изображение отсутствует в старом журнале")
            if (
                hashlib.sha256(
                    row[0] + f"|{job['widthMm']:g}x{job['heightMm']:g}".encode()
                ).hexdigest()
                != job["hash"]
            ):
                raise ValueError("Сохранённое изображение повреждено; повтор запрещён")
            return row[0]

    def enqueue(self, body, parent=None, schedule_now=True):
        key, image = body.get("idempotencyKey"), body.get("imageDataUrl")
        if (
            not isinstance(key, str)
            or not 1 <= len(key) <= 200
            or not isinstance(image, str)
            or not image.startswith("data:image/png;base64,")
        ):
            raise ValueError("Некорректное задание печати")
        data = base64.b64decode(image.split(",", 1)[1], validate=True)
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 4_000_000:
            raise ValueError("Некорректная PNG-этикетка")
        from PIL import Image

        with Image.open(io.BytesIO(data)) as decoded:
            if decoded.format != "PNG" or decoded.width * decoded.height > 20_000_000:
                raise ValueError("Некорректный размер PNG-этикетки")
            decoded.verify()
        width, height = body.get("widthMm"), body.get("heightMm")
        DefaultWindowsAdapter._label_size(width, height)
        digest = hashlib.sha256(data + f"|{width:g}x{height:g}".encode()).hexdigest()
        with self.lock, closing(self.connect()) as db:
            self._writable()
            old = self._read(db, key)
            if old:
                # Legacy pre-size hashes carry no evidence of a size. Never re-submit them.
                if old["hash"] != digest and not (
                    old.get("legacy")
                    and old["hash"]
                    in (
                        hashlib.sha256(data).hexdigest(),
                        hashlib.sha256(
                            data + f"|{float(width)}x{float(height)}".encode()
                        ).hexdigest(),
                    )
                ):
                    raise ValueError("Содержимое или размер этого задания изменились")
                if old.get("parentKey") != parent:
                    raise ValueError("Ключ принадлежит другой операции восстановления")
                return self.get(key)
            # A parent's durable intent still reserves a lost child's key across
            # every entry point, including a plain POST /print.
            for (parent_metadata,) in db.execute(
                "SELECT metadata FROM jobs WHERE instr(metadata, '\"reprintIntentKeys\"') > 0"
            ):
                try:
                    reserved = json.loads(parent_metadata).get("reprintIntentKeys", [])
                except (ValueError, AttributeError, TypeError):
                    continue
                if key in reserved:
                    raise ValueError(
                        "Исход повторной операции неизвестен: её описание утрачено. Прежний ключ повторно не отправлен"
                    )
            context = {}
            supplied = body.get("context", {})
            if isinstance(supplied, dict):
                for name in (
                    "tenantId",
                    "userId",
                    "wbOrderId",
                    "scanId",
                    "orderId",
                    "supplyId",
                    "marketplace",
                    "productId",
                    "barcode",
                    "orderNumber",
                    "sellerId",
                    "sellerName",
                    "scan_id",
                    "order_id",
                    "supply_id",
                ):
                    if isinstance(supplied.get(name), (str, int, float)):
                        context[name] = (
                            supplied[name][:500]
                            if isinstance(supplied[name], str)
                            else supplied[name]
                        )
            job = dict(
                idempotencyKey=key,
                hash=digest,
                widthMm=width,
                heightMm=height,
                context=context,
                createdAt=timestamp(),
                updatedAt=timestamp(),
                status="saved",
                reason="Изображение сохранено; ожидает передачи в системную очередь",
                receipt=None,
                queue=None,
                title="WMS-" + hashlib.sha256(f"{key}|{digest}".encode()).hexdigest(),
                legacy=False,
                parentKey=parent,
                duplicateRiskAcknowledged=bool(parent),
                observations=[f"{timestamp()} saved"],
            )
            db.execute(
                "INSERT INTO jobs(id,hash,receipt,image,metadata) VALUES(?,?,NULL,?,?)",
                (key, digest, data, json.dumps(job, ensure_ascii=False)),
            )
            db.commit()
            if self.auto_work and schedule_now:
                self._schedule(key)
            return self.get(key)

    def _schedule(self, key):
        with self.lock:
            if key in self.active:
                return
            self.active.add(key)
            self.worker.submit(self._process_and_release, key)

    def _process_and_release(self, key):
        try:
            self.process(key)
        finally:
            with self.lock:
                self.active.discard(key)
                if not self.storage_error and self.get(key)["status"] == "saved":
                    self._schedule(key)

    def _ensure_parent_intent(self, db, job):
        parent_key = job.get("parentKey")
        if not parent_key:
            return
        parent = self._read(db, parent_key)
        if not parent:
            raise BeforeSubmitError("Исходное задание восстановления недоступно")
        key = job["idempotencyKey"]
        if key not in parent.get("reprintIntentKeys", []):
            parent["reprintIntentKeys"] = parent.get("reprintIntentKeys", []) + [key]
            parent["updatedAt"] = timestamp()
            parent["observations"] = parent.get("observations", []) + [
                f"{parent['updatedAt']} explicit-reprint: {key}; оператор подтвердил риск дубликата"
            ]
            self._save(db, parent)

    def process(self, key):
        with self.lock, closing(self.connect()) as db:
            self._writable()
            job = self._read(db, key)
            if not job or job["status"] != "saved":
                return
        try:
            data = self.image(key)
            job["queue"] = self.queue()
            if not job["queue"]:
                raise BeforeSubmitError("В системе не выбран принтер по умолчанию")
            with self.lock, closing(self.connect()) as db:
                self._ensure_parent_intent(db, job)
                job = self._change(
                    job, "submitting", "Начата передача в системную очередь"
                )
                self._save(db, job)
        except Exception as exc:
            with self.lock, closing(self.connect()) as db:
                try:
                    self._save(db, self._change(job, "failed_before_submit", str(exc)))
                except Exception as disk_error:
                    self.storage_error = f"Запись задания недоступна: {disk_error}"
                    self.diagnostics.append(self.storage_error)
            return
        try:
            receipt = (
                self.submit(data, job)
                if self.submit
                else helper("--submit-job", str(self.db), key)["receipt"]
            )
            job.update(receipt=receipt)
            job = self._change(
                job,
                "accepted",
                "Системная очередь приняла задание; бумага не подтверждена",
            )
        except Exception as exc:
            job = self._change(
                job,
                "failed_before_submit"
                if isinstance(exc, BeforeSubmitError)
                else "unknown",
                str(exc),
            )
        with self.lock, closing(self.connect()) as db:
            try:
                self._save(db, job)
            except Exception as exc:
                self.storage_error = f"Не удалось сохранить результат отправки: {exc}"
                self.diagnostics.append(self.storage_error)

    def retry(self, key):
        with self.lock, closing(self.connect()) as db:
            self._writable()
            job = self._read(db, key)
            if (
                not job
                or job.get("legacy")
                or job["status"] not in ("saved", "failed_before_submit")
                or self.get(key).get("reprints")
            ):
                raise ValueError(
                    "Исход может быть неизвестен; сначала сверьте очередь. Автоматического повтора нет"
                )
            self.image(key)
            self._save(
                db,
                self._change(
                    job, "saved", "Оператор повторил доказанно неотправленное задание"
                ),
            )
            if self.auto_work:
                self._schedule(key)
            return self.get(key)

    def reprint(self, key, body):
        with self.lock, closing(self.connect()) as db:
            self._writable()
            job = self._read(db, key)
            child = body.get("idempotencyKey")
            if (
                not job
                or job.get("legacy")
                or body.get("acknowledgeDuplicateRisk") is not True
                or not isinstance(child, str)
                or not 1 <= len(child) <= 200
                or child == key
            ):
                raise ValueError(
                    "Нужны новый ключ и явное подтверждение риска второй этикетки"
                )
            if key in self.active or job["status"] == "submitting":
                raise ValueError(
                    "Передача ещё выполняется; дождитесь результата и сверьте очередь"
                )
            data = self.image(key)
            existing = self._read(db, child)
            if existing and existing.get("parentKey") != key:
                raise ValueError("Ключ принадлежит другой операции восстановления")
            if not existing and child in job.get("reprintIntentKeys", []):
                raise ValueError(
                    "Исход повторной операции неизвестен: её описание утрачено. Прежний ключ повторно не отправлен"
                )
            self.enqueue(
                dict(
                    idempotencyKey=child,
                    imageDataUrl="data:image/png;base64,"
                    + base64.b64encode(data).decode(),
                    widthMm=job["widthMm"],
                    heightMm=job["heightMm"],
                    context=job["context"],
                ),
                parent=key,
                schedule_now=False,
            )
            saved_child = self._read(db, child)
            self._ensure_parent_intent(db, saved_child)
            if self.auto_work and saved_child["status"] == "saved":
                self._schedule(child)
            return self.get(child)

    def reconcile(self, key):
        with self.lock, closing(self.connect()) as db:
            job = self._read(db, key)
            if not job:
                raise ValueError("Задание не найдено")
            if (
                key in self.active
                or key in self.observing
                or job["status"] in ("saved", "failed_before_submit")
            ):
                return self.get(key)
            self.observing.add(key)
        try:
            try:
                observation = self.observe(job)
            except Exception as exc:
                observation = {"error": str(exc)}
            with self.lock, closing(self.connect()) as db:
                current = self._read(db, key)
                if current != job:
                    return self.get(key)
                if (
                    observation.get("matches") == 1
                    and observation.get("receipt")
                    and observation.get("status")
                ):
                    current.update(receipt=observation["receipt"])
                    current = self._change(
                        current,
                        observation["status"],
                        "Состояние системной очереди; бумага не подтверждена",
                    )
                else:
                    current = self._change(
                        current,
                        current["status"] if current.get("receipt") else "unknown",
                        observation.get(
                            "error",
                            "Однозначная запись в очереди отсутствует; прошлый физический исход неизвестен",
                        ),
                    )
                current["queueObservation"] = observation
                self._save(db, current)
                return self.get(key)
        finally:
            with self.lock:
                self.observing.discard(key)

    def poll(self):
        while True:
            for job in self.list()["jobs"]:
                if job["status"] not in (
                    "saved",
                    "failed_before_submit",
                    "completed",
                    "canceled",
                    "aborted",
                ):
                    try:
                        self.reconcile(job["idempotencyKey"])
                    except Exception:
                        pass
            time.sleep(15)

    def print(self, body):
        job = self.enqueue(body)
        deadline = time.monotonic() + 18
        while (
            not job.get("receipt")
            and job["status"] in ("saved", "submitting")
            and time.monotonic() < deadline
        ):
            time.sleep(0.1)
            job = self.get(body["idempotencyKey"])
        if not job.get("receipt") or job["status"] in (
            "held",
            "canceled",
            "aborted",
            "stopped",
        ):
            raise agent.UnknownPrintOutcome(
                f"Задание сохранено, приём очередью не подтверждён. История: {ORIGIN}"
            )
        return job


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def allowed(self):
        return (
            self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"
            and self.headers.get("Origin", ORIGIN) in ALLOWED_ORIGINS
        )

    def respond(self, status, value, mime="application/json; charset=utf-8"):
        data = (
            value
            if isinstance(value, bytes)
            else json.dumps(value, ensure_ascii=False).encode()
        )
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers", "Content-Type, X-WMS-Print"
            )
            self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.respond(200 if self.allowed() else 403, {})

    def do_POST(self):
        if not self.allowed() or self.headers.get("X-WMS-Print") != "1":
            self.respond(403, {"error": "Источник печати не разрешён"})
            return
        try:
            self.connection.settimeout(20)
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 6_000_000:
                raise ValueError("Некорректный размер задания")
            body = json.loads(self.rfile.read(length)) if length else {}
            if not isinstance(body, dict):
                raise ValueError("Некорректное задание")
            if self.path == "/print":
                modern = body.get("protocolVersion") == 2
                self.respond(
                    202 if modern else 200,
                    self.server.printer.enqueue(body)
                    if modern
                    else self.server.printer.print(body),
                )
                return
            parts = self.path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "jobs":
                key = unquote(parts[1])
                if self.server.printer.get(key) is None:
                    self.respond(404, {})
                    return
                if parts[2] == "reconcile":
                    result = self.server.printer.reconcile(key)
                elif parts[2] == "retry":
                    result = self.server.printer.retry(key)
                elif parts[2] == "reprint":
                    result = self.server.printer.reprint(key, body)
                else:
                    self.respond(404, {})
                    return
                self.respond(200, result)
                return
            self.respond(404, {})
        except Exception as exc:
            self.respond(409, {"error": str(exc)})

    def do_GET(self):
        if not self.allowed():
            self.respond(403, {})
            return
        try:
            if self.path == "/health":
                self.respond(
                    200,
                    {
                        "app": "WMS Print Direct",
                        "protocolVersion": 2,
                        "historyUrl": ORIGIN,
                        "physicalConfirmationSupported": False,
                    },
                )
                return
            if self.path == "/":
                self.respond(
                    200,
                    (Path(__file__).resolve().parent / "history.html").read_bytes(),
                    "text/html; charset=utf-8",
                )
                return
            parts = self.path.strip("/").split("/")
            if parts == ["jobs"]:
                self.respond(200, self.server.printer.list())
                return
            if len(parts) >= 2 and parts[0] == "jobs":
                key = unquote(parts[1])
                job = self.server.printer.get(key)
                if job is None:
                    self.respond(404, {})
                    return
                if len(parts) == 2:
                    self.respond(200, job)
                    return
                if parts[2:] == ["image"]:
                    self.respond(200, self.server.printer.image(key), "image/png")
                    return
            self.respond(404, {})
        except Exception as exc:
            self.respond(409, {"error": str(exc)})


def native_operation(args):
    entered_submit = False
    try:
        if args[0] == "--system-default":
            return {"queue": default_printer()}
        with closing(sqlite3.connect(args[1])) as db:
            row = db.execute(
                "SELECT image,metadata FROM jobs WHERE id=?", (args[2],)
            ).fetchone()
        job = json.loads(row[1])
        if args[0] == "--observe-job":
            return (
                observe_windows(job)
                if sys.platform == "win32"
                else {"error": "Use native macOS package for CUPS observation"}
            )
        adapter = DefaultWindowsAdapter() if sys.platform == "win32" else MacPrinter()
        entered_submit = True
        return {
            "receipt": adapter.submit_default(
                row[0], job["queue"], job["widthMm"], job["heightMm"], job["title"]
            )
        }
    except BeforeSubmitError as exc:
        return {"error": str(exc), "beforeSubmit": True}
    except Exception as exc:
        return {"error": str(exc), "beforeSubmit": not entered_submit}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) > 1 and sys.argv[1] in (
        "--system-default",
        "--submit-job",
        "--observe-job",
    ):
        print(json.dumps(native_operation(sys.argv[1:]), ensure_ascii=False))
        return
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        DefaultWindowsAdapter() if sys.platform == "win32" else MacPrinter()
        print("WMS Print Direct: package OK")
        return
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print("WMS Print уже запущена либо локальный порт занят.", flush=True)
        return
    server.printer = Printer(state_directory() / "direct")
    threading.Thread(target=server.printer.poll, daemon=True).start()
    print(
        f"WMS Print запущена. История и восстановление: {ORIGIN}. Оставьте окно открытым.",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
