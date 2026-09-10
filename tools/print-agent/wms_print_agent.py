"""WMS-402: локальный агент печати одной готовой этикетки FBS.

Агент ходит наружу сам: забирает одно задание из очереди WMS, скачивает уже
подготовленный файл, отдаёт его в **названную оператором** очередь ОС и
возвращает её квитанцию. Входящий доступ в сеть склада не нужен.

Границы, которые нельзя размывать:

* за один запуск обрабатывается **ровно одно** задание; локального журнала
  попыток и автоматической повторной отправки здесь нет;
* квитанция очереди ОС означает «принято очередью», а не «бумага вышла»;
* если исход отправки неизвестен (таймаут, невнятный ответ ``lp``), агент
  **ничего не сообщает серверу и ничего не печатает заново**: задание остаётся
  в состоянии «выдано агенту», а решение принимает человек;
* модель принтера, адрес, драйвер и протокол агенту неизвестны и в WMS не
  хранятся. Известно только имя очереди ОС, которое задал оператор.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

MAX_BYTES = 16 * 1024 * 1024
QUEUE_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,127}")
CHECKSUM_PATTERN = re.compile(r"[0-9a-f]{64}")
RECEIPT_PATTERN = re.compile(r"\brequest id is ([A-Za-z0-9_.-]+)")
SUPPORTED_CONTENT_TYPES = {"application/pdf", "image/png"}
FILE_SIGNATURES = {"application/pdf": b"%PDF-", "image/png": b"\x89PNG\r\n\x1a\n"}


class UnknownPrintOutcome(RuntimeError):
    """Очередь ОС могла принять файл. Повторять печать автоматически нельзя."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        # Сессионный доступ WMS не должен уехать по редиректу на чужой хост.
        return None


def check_base_url(base_url: str) -> str:
    url = urllib.parse.urlsplit(base_url)
    if (
        url.scheme != "https"
        or not url.netloc
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError("Нужен HTTPS-адрес WMS без учётных данных в URL")
    return base_url.rstrip("/")


def check_queue(queue: str) -> str:
    if queue.startswith("-") or not QUEUE_PATTERN.fullmatch(queue):
        raise ValueError("Некорректное имя очереди ОС")
    return queue


def _open(request: urllib.request.Request) -> tuple[bytes, str]:
    with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
        return response.read(MAX_BYTES + 1), response.headers.get_content_type()


def _api(
    base_url: str,
    token: str,
    method: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = base_url + path + ("?" + urllib.parse.urlencode(query) if query else "")
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    payload, _ = _open(
        urllib.request.Request(url, data=data, headers=headers, method=method)
    )
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Неожиданный ответ WMS")
    return parsed


def claim_job(base_url: str, token: str, warehouse_id: str) -> dict[str, Any] | None:
    """Взять одно ожидающее задание своего склада. Сервер сам делает это атомарно."""
    answer = _api(
        base_url,
        token,
        "POST",
        "/operations/fbs-print-jobs/next",
        query={"warehouse_id": warehouse_id},
    )
    job = answer.get("job")
    return job if isinstance(job, dict) else None


def validate_job(job: dict[str, Any], warehouse_id: str) -> dict[str, Any]:
    """Проверить, что это действительно выданное нам задание с готовым файлом."""
    uuid.UUID(str(job["id"]))
    uuid.UUID(str(job["asset_id"]))
    if job.get("status") != "running":
        raise ValueError("Задание не выдано агенту")
    if str(job.get("warehouse_id")) != warehouse_id:
        raise ValueError("Задание относится к другому складу")
    if job.get("content_type") not in SUPPORTED_CONTENT_TYPES:
        raise ValueError("Неподдерживаемый формат этикетки")
    checksum = str(job.get("checksum") or "").removeprefix("sha256:")
    if not CHECKSUM_PATTERN.fullmatch(checksum):
        raise ValueError("Нужна контрольная сумма SHA256")
    return {"checksum": checksum, "content_type": job["content_type"]}


def fetch_label(
    base_url: str, token: str, job_id: str, warehouse_id: str, expected: dict[str, Any]
) -> bytes:
    # Путь собираем из проверенного UUID, а не из ссылки внутри задания.
    path = "/operations/fbs-print-jobs/" + str(uuid.UUID(job_id)) + "/content"
    url = base_url + path + "?" + urllib.parse.urlencode({"warehouse_id": warehouse_id})
    data, content_type = _open(
        urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    )
    if len(data) > MAX_BYTES or content_type != expected["content_type"]:
        raise ValueError("Неожиданный размер или тип файла")
    if hashlib.sha256(data).hexdigest() != expected["checksum"]:
        raise ValueError("Файл этикетки изменился после постановки в очередь")
    if not data.startswith(FILE_SIGNATURES[content_type]):
        raise ValueError("Файл не похож на заявленный формат")
    return data


def submit_to_queue(
    data: bytes, content_type: str, queue: str, run: Any = subprocess.run
) -> str:
    """Отдать файл в очередь ОС и вернуть её квитанцию.

    Без shell, без установки драйверов и без входящего слушателя. Один запуск —
    одна отправка: неизвестный исход наверх уходит как ``UnknownPrintOutcome``.
    """
    suffix = ".pdf" if content_type == "application/pdf" else ".png"
    directory = tempfile.mkdtemp(prefix="wms-print-")
    try:
        path = Path(directory) / ("label" + suffix)
        path.write_bytes(data)
        try:
            result = run(
                ["lp", "-d", queue, "--", str(path)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                env={**os.environ, "LC_ALL": "C"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise UnknownPrintOutcome(
                "Исход отправки в очередь ОС неизвестен; проверьте очередь вручную"
            ) from exc
        receipt = RECEIPT_PATTERN.search(result.stdout or "")
        if result.returncode != 0 or receipt is None:
            raise UnknownPrintOutcome(
                "Квитанция очереди не подтверждена; автоматический повтор запрещён"
            )
        return receipt.group(1)
    finally:
        # Once lp has returned, a cleanup failure must not turn its successful
        # queue receipt into a false failed handoff.
        shutil.rmtree(directory, ignore_errors=True)


def report_result(
    base_url: str,
    token: str,
    job_id: str,
    warehouse_id: str,
    *,
    queue_receipt: str | None,
    handed_to_queue: bool,
    error_message: str | None = None,
) -> None:
    _api(
        base_url,
        token,
        "POST",
        "/operations/fbs-print-jobs/" + str(uuid.UUID(job_id)) + "/result",
        body={
            "warehouse_id": warehouse_id,
            "queue_receipt": queue_receipt,
            "handed_to_queue": handed_to_queue,
            "error_message": error_message,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Печать одного задания FBS из очереди WMS"
    )
    parser.add_argument(
        "--warehouse-id", required=True, help="UUID склада этого принтера"
    )
    args = parser.parse_args(argv)

    job_id: str | None = None
    base_url = token = warehouse_id = ""
    try:
        base_url = check_base_url(os.environ["WMS_PRINT_API_URL"])
        token = os.environ["WMS_PRINT_TOKEN"]
        queue = check_queue(os.environ["WMS_PRINT_QUEUE"])
        warehouse_id = str(uuid.UUID(args.warehouse_id))

        job = claim_job(base_url, token, warehouse_id)
        if job is None:
            print("Очередь печати пуста.")
            return 0
        job_id = str(job["id"])
        expected = validate_job(job, warehouse_id)
        data = fetch_label(base_url, token, job_id, warehouse_id, expected)
        receipt = submit_to_queue(data, expected["content_type"], queue)
    except UnknownPrintOutcome:
        # Молчим намеренно: неизвестный исход не является ни отказом, ни успехом.
        # Задание остаётся выданным агенту, повторную печать запускает человек.
        print(
            "Исход печати неизвестен; повторять автоматически нельзя.", file=sys.stderr
        )
        return 2
    except (KeyError, ValueError, TypeError, OSError, urllib.error.URLError) as exc:
        # В очередь ничего не ушло — об этом можно сообщить честно.
        if job_id is not None:
            try:
                report_result(
                    base_url,
                    token,
                    job_id,
                    warehouse_id,
                    queue_receipt=None,
                    handed_to_queue=False,
                    error_message=type(exc).__name__,
                )
            except (ValueError, OSError, urllib.error.URLError):
                pass
        # Ни тела ответа, ни адресов, ни доступов в вывод не попадает.
        print("Задание отклонено до подтверждения очереди.", file=sys.stderr)
        return 1

    try:
        report_result(
            base_url,
            token,
            job_id,
            warehouse_id,
            queue_receipt=receipt,
            handed_to_queue=True,
        )
    except (ValueError, OSError, urllib.error.URLError):
        # Файл уже в очереди ОС. Повторять печать нельзя, поэтому просто говорим,
        # что квитанцию не удалось записать — задание останется выданным агенту.
        print(
            "Квитанция очереди не записана в WMS; печать не повторять.", file=sys.stderr
        )
        return 2
    print(json.dumps({"job_id": job_id, "queue_receipt": receipt}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
