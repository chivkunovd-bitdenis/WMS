"""WMS-402: single configured CUPS queue adapter for a claimed BackgroundJob.

Does not claim jobs, issue credentials or assert physical printing. A caller must
persist running BEFORE invoking this adapter and persist its receipt afterward.
An interrupted/failed subprocess has an unknown outcome and MUST NOT be replayed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
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


class UnknownPrintOutcome(RuntimeError):
    """The OS may have accepted the job. Do not print it again automatically."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        # A WMS session credential must never follow a redirect to another host.
        return None


def validate_job(job: dict[str, Any], queue: str) -> dict[str, Any]:
    uuid.UUID(job["id"])
    if job.get("job_type") != "fbs_network_print" or job.get("status") != "running":
        raise ValueError(
            "An already claimed fbs_network_print BackgroundJob is required"
        )
    payload = dict(job["payload_json"])
    payload["checksum"] = str(payload.get("checksum", "")).removeprefix("sha256:")
    uuid.UUID(payload["asset_id"])
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,127}", queue) or queue.startswith("-"):
        raise ValueError("Invalid configured CUPS queue")
    if payload.get("queue") != queue:
        raise ValueError("Job is not assigned to this configured queue")
    if type(payload.get("copies")) is not int or not 1 <= payload["copies"] <= 100:
        raise ValueError("Invalid copy count")
    if payload.get("content_type") not in {"application/pdf", "image/png"}:
        raise ValueError("Unsupported label format")
    if not re.fullmatch(r"[0-9a-f]{64}", payload.get("checksum", "")):
        raise ValueError("A SHA256 snapshot is required")
    return payload


def fetch_label(
    base_url: str, token: str, job_id: str, payload: dict[str, Any]
) -> bytes:
    url = urllib.parse.urlsplit(base_url)
    if (
        url.scheme != "https"
        or not url.netloc
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError("Configure an HTTPS WMS API base URL without credentials")
    # Path comes only from a validated UUID, never from the job's URL/storage path.
    job_id = str(uuid.UUID(job_id))
    request = urllib.request.Request(
        base_url.rstrip("/") + "/operations/fbs-print-jobs/" + job_id + "/content",
        headers={"Authorization": "Bearer " + token},
    )
    with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
        content_type = response.headers.get_content_type()
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or content_type != payload["content_type"]:
        raise ValueError("Unexpected file size or content type")
    if hashlib.sha256(data).hexdigest() != payload["checksum"]:
        raise ValueError("The label changed after the job was created")
    if content_type == "application/pdf" and not data.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF signature")
    if content_type == "image/png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Invalid PNG signature")
    return data


def submit_to_cups(
    data: bytes, payload: dict[str, Any], queue: str, run: Any = subprocess.run
) -> dict[str, str]:
    # No shell, command strings, driver installation or inbound network listener.
    suffix = ".pdf" if payload["content_type"] == "application/pdf" else ".png"
    with tempfile.TemporaryDirectory(prefix="wms-print-") as directory:
        path = Path(directory) / ("label" + suffix)
        path.write_bytes(data)
        try:
            result = run(
                ["lp", "-d", queue, "-n", str(payload["copies"]), "--", str(path)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                env={**os.environ, "LC_ALL": "C"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise UnknownPrintOutcome(
                "OS queue outcome unknown; inspect the queue before retrying"
            ) from exc
        receipt = re.search(r"\brequest id is ([A-Za-z0-9_.-]+)", result.stdout)
        if result.returncode != 0 or receipt is None:
            raise UnknownPrintOutcome(
                "No confirmed OS queue receipt; automatic retry is forbidden"
            )
        return {"stage": "spooled", "queue": queue, "receipt": receipt.group(1)}


def main() -> int:
    try:
        # Prototype transport boundary: stdin is ONE already-claimed BackgroundJob.
        # There is deliberately no local retry journal or automatic resubmission.
        job = json.loads(sys.stdin.read(64 * 1024 + 1))
        queue = os.environ["WMS_PRINT_QUEUE"]
        payload = validate_job(job, queue)
        data = fetch_label(
            os.environ["WMS_PRINT_API_URL"],
            os.environ["WMS_PRINT_TOKEN"],
            job["id"],
            payload,
        )
        result = submit_to_cups(data, payload, queue)
        print(json.dumps({"job_id": job["id"], "result_json": result}))
        return 0
    except UnknownPrintOutcome:
        print(
            "Print outcome unknown; do not replay this job automatically.",
            file=sys.stderr,
        )
        return 2
    except (KeyError, ValueError, TypeError, OSError, urllib.error.URLError):
        # Do not print response bodies, URLs, session credentials or full job payloads.
        print("Print job rejected before a confirmed queue receipt.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
