"""Replay corrected F1/F3 against deliberately broken SALES HTTP evidence only.

Run with the backend test interpreter from any cwd. This is a diagnostic, not
part of normal pytest discovery. It never changes product files or helpers.
"""

import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent
TARGETS = {
    "test_create_reload_and_overlap_resume_without_duplicate",
    "test_retry_retains_old_price_error_and_new_attempt",
}
BOUNDARY = """
import json
import uuid
from datetime import UTC, datetime, timedelta
import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from test_withdrawal_ledger import seed, legacy_sales_http, _SYNTHETIC_SALES
from app.db.session import SessionLocal
from app.db.withdrawal_repository import (
    WithdrawalScope, WithdrawalError, current_items, get_operation,
)
from app.models.marking_withdrawal import WithdrawalOperation, WithdrawalItem
from app.services.wb_order_price_service import capture_wb_price_snapshot
from app.services.withdrawal_service import create_operation, retry_operation

@pytest.fixture(autouse=True)
def broken_sale_source(monkeypatch, legacy_sales_http):
    original_send = httpx.AsyncClient.send

    async def send(client, request, **kwargs):
        response = await original_send(client, request, **kwargs)
        if request.url.path == "/api/v1/supplier/sales":
            rows = response.json()
            for row in rows:
                row["finishedPrice"] = None
            return httpx.Response(response.status_code, json=rows, request=request)
        return response

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
"""


def main() -> None:
    source = (TESTS / "test_withdrawal_ledger.py").read_text()
    tree = ast.parse(source)
    functions = [
        ast.get_source_segment(source, node)
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name in TARGETS
    ]
    if len(functions) != 2:
        raise RuntimeError("Expected exactly two corrected real entrypoint tests")
    with tempfile.NamedTemporaryFile(
        mode="w",
        prefix="wms517_source_negative_",
        suffix=".py",
        dir=TESTS,
        delete=False,
    ) as probe:
        probe.write(BOUNDARY + "\n\n" + "\n\n".join(functions) + "\n")
        probe_path = Path(probe.name)
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                str(probe_path),
                "--tb=short",
                "-p",
                "no:cacheprovider",
            ],
            cwd=TESTS.parent,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            check=False,
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.returncode != 1 or "2 failed" not in result.stdout:
            raise RuntimeError(
                "Negative control must fail both business checks, without setup errors"
            )
        if "ERROR " in result.stdout or " errors" in result.stdout:
            raise RuntimeError("Infrastructure/collection failure is not a negative proof")
        print("NEGATIVE CONTROL VERIFIED: broken HTTP finishedPrice fails both corrected F1/F3.")
    finally:
        probe_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
