"""C6: independent OS workers, real PostgreSQL locks, shared loopback WB HTTP.

Run only on an isolated WMS_TEST_DATABASE_URL (the conftest safety gate applies).
The subprocess entrypoint does not run pytest or rebuild the shared schema.
"""
# ruff: noqa: E402  # stdout must be redirected before application imports in worker mode.

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from collections.abc import AsyncIterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# Keep the parent's stdout as a strict JSON-lines protocol before importing the
# application: import-time libraries may print diagnostics to stdout. Worker
# diagnostics belong on stderr; only _emit_worker_receipt may use this handle.
_C6_WORKER_MODE = "--c6-worker" in sys.argv
_C6_PROTOCOL_STDOUT = sys.stdout
if _C6_WORKER_MODE:
    sys.stdout = sys.stderr
if (
    _C6_WORKER_MODE
    and os.environ.get("WMS681_C6_TEST_STARTUP_DIAGNOSTIC") == "1"
):
    print("warning: C6 controlled worker startup diagnostic", flush=True)

from app.core.settings import settings
from app.db.session import SessionLocal, engine, get_db
from app.models.fbs_packing_box import FbsPackingBox
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.fbs_trbx import FbsTrbx
from app.models.fbs_wb_operation import FbsWbOperation
from app.services.wildberries_client import _TINY_PNG_BASE64
from tests.test_fbs_packing_box import (
    _legacy_unlinked_box_group,
    _packed_supply,
    _physical_group_snapshot,
)


class _SharedWB:
    """One external state for both processes; do not replace recovery services."""

    def __init__(self) -> None:
        self.created: list[str] = []
        self.create_amounts: list[int] = []
        self.sticker_requests: list[list[str]] = []
        self.create_entered = threading.Event()
        self.release_create = threading.Event()
        self.two_stickers = threading.Event()
        self.sticker_entered = threading.Event()
        self.release_stickers = threading.Event()
        self.mutex = threading.Lock()

    def handler(self) -> type[BaseHTTPRequestHandler]:
        state = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                pass  # Never log authorization headers or query bodies.

            def respond(self, data: object, status: int = 200) -> None:
                payload = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:
                if self.path.endswith("/trbx"):
                    with state.mutex:
                        ids = list(state.created)
                    self.respond({"trbxIds": ids})
                else:
                    self.respond({"unexpected_path": self.path}, 500)

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path.endswith("/trbx"):
                    with state.mutex:
                        state.create_amounts.append(body["amount"])
                    state.create_entered.set()
                    if not state.release_create.wait(20):
                        self.respond({"barrier_timeout": "create"}, 500)
                        return
                    with state.mutex:
                        ids = [f"WB-MP-C6-{len(state.created) + i}" for i in range(body["amount"])]
                        state.created.extend(ids)
                    self.respond({"trbxIds": ids})
                elif "/trbx/stickers?" in self.path:
                    with state.mutex:
                        state.sticker_requests.append(body["trbxIds"])
                        state.sticker_entered.set()
                        if len(state.sticker_requests) >= 2:
                            state.two_stickers.set()
                    if not state.release_stickers.wait(20):
                        self.respond({"barrier_timeout": "stickers"}, 500)
                        return
                    self.respond({"stickers": [
                        {"trbxId": wb_id, "file": _TINY_PNG_BASE64}
                        for wb_id in body["trbxIds"]
                    ]})
                else:
                    self.respond({"unexpected_path": self.path}, 500)

        return Handler


def _emit_worker_receipt(receipt: dict[str, Any]) -> None:
    """Emit the sole structured stdout line; diagnostics use redirected stderr."""
    print(json.dumps(receipt), file=_C6_PROTOCOL_STDOUT, flush=True)


async def _worker() -> None:
    """Real endpoint in its own process and pinned physical PG connection."""
    from httpx import ASGITransport

    from app.main import create_app

    config = json.loads(sys.stdin.readline())
    settings.wildberries_marketplace_api_base = config["wb_url"]
    settings.e2e_mock_wb_marketplace_supplies = False
    async with (
        engine.connect() as connection,
        AsyncSession(bind=connection, expire_on_commit=False) as session,
    ):
        pid = await session.scalar(text("SELECT pg_backend_pid()"))
        _emit_worker_receipt({"ready": True, "os_pid": os.getpid(), "pg_pid": pid})
        await asyncio.to_thread(sys.stdin.readline)

        async def database() -> AsyncIterator[AsyncSession]:
            yield session

        app = create_app()
        app.dependency_overrides[get_db] = database
        result: dict[str, Any] = {"os_pid": os.getpid(), "pg_pid": pid}
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://isolated-c6.test",
            ) as client:
                response = await client.post(config["path"], headers=config["headers"])
                result.update(status=response.status_code, body=response.json())
        except Exception as exc:
            # SQLSTATE + exception class prove the boundary without dumping
            # a connection URL, token, SQL parameters, or environment.
            original = getattr(exc, "orig", None)
            result.update(
                status=500, error=type(exc).__name__,
                sqlstate=getattr(original, "sqlstate", None),
                constraint=getattr(getattr(original, "diag", None), "constraint_name", None),
            )
            await session.rollback()
        result["final_pg_pid"] = await session.scalar(text("SELECT pg_backend_pid()"))
        _emit_worker_receipt(result)
    await engine.dispose()


async def _line(process: asyncio.subprocess.Process, receipt: str) -> dict[str, Any]:
    """Read exactly one worker protocol line, rejecting any protocol corruption."""
    assert process.stdout is not None
    try:
        raw = await asyncio.wait_for(process.stdout.readline(), timeout=30)
    except TimeoutError as exc:
        raise AssertionError(f"{receipt}: timed out waiting for worker receipt") from exc
    if not raw:
        raise AssertionError(
            f"{receipt}: worker exited before producing its structured receipt "
            f"(returncode={process.returncode})",
        )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"{receipt}: malformed worker stdout protocol line: {raw!r}",
        ) from exc
    if not isinstance(parsed, dict):
        raise AssertionError(f"{receipt}: worker receipt is not an object: {parsed!r}")
    return parsed


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires real PostgreSQL")
async def test_wms681_postgres_two_workers_recover_one_group_across_qr_checkpoint(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    record_property: Any,
) -> None:
    """C6: wait on supply row, then overlap QR fetch after the confirmed commit."""
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    headers, supply_id, order_ids = await _packed_supply(async_client)
    ids, _, _ = await _legacy_unlinked_box_group(supply_id, order_ids, count=5)
    other_ids, _, _ = await _legacy_unlinked_box_group(
        supply_id, order_ids, count=1, key="c6-other-group", first_box_number=6,
        assigned_order_id=order_ids[1],
    )
    physical_before = await _physical_group_snapshot(supply_id)
    shared = _SharedWB()
    server = ThreadingHTTPServer(("127.0.0.1", 0), shared.handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    processes: list[asyncio.subprocess.Process] = []
    config = {
        "wb_url": f"http://127.0.0.1:{server.server_port}",
        "path": f"/operations/fbs-supplies/{supply_id}/boxes/{ids[2]}/retry-qr",
        "headers": headers,
    }

    async def launch() -> tuple[asyncio.subprocess.Process, dict[str, Any]]:
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).resolve()), "--c6-worker",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
        )
        processes.append(process)
        assert process.stdin is not None
        process.stdin.write((json.dumps(config) + "\n").encode())
        await process.stdin.drain()
        ready = await _line(process, "ready")
        assert ready["ready"]
        process.stdin.write(b"start\n")
        await process.stdin.drain()
        return process, ready

    try:
        first, first_ready = await launch()
        assert await asyncio.to_thread(shared.create_entered.wait, 15), "WB create not reached"
        second, second_ready = await launch()
        assert first_ready["os_pid"] != second_ready["os_pid"]
        assert first_ready["pg_pid"] != second_ready["pg_pid"]
        async with SessionLocal() as observer:
            async with asyncio.timeout(10):
                while True:
                    blockers = await observer.scalar(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": second_ready["pg_pid"]},
                    )
                    await observer.rollback()
                    if first_ready["pg_pid"] in blockers:
                        break
                    assert second.returncode is None, "second worker did not wait on PG"
                    await asyncio.sleep(0.01)
        record_property("first_worker", json.dumps(first_ready))
        record_property("second_worker", json.dumps(second_ready))
        record_property("blocking_pids", json.dumps(blockers))
        shared.release_create.set()
        assert await asyncio.to_thread(shared.sticker_entered.wait, 15), "QR fetch not reached"
        # Accept a fix that keeps the real row lock through the QR checkpoint,
        # as well as a fix that safely tolerates both HTTP fetches. Do not force
        # duplicate fetches or prescribe a locking implementation to pass C6.
        async with SessionLocal() as observer:
            async with asyncio.timeout(10):
                while not shared.two_stickers.is_set():
                    qr_blockers = await observer.scalar(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": second_ready["pg_pid"]},
                    )
                    await observer.rollback()
                    if first_ready["pg_pid"] in qr_blockers:
                        break
                    assert second.returncode is None
                    await asyncio.sleep(0.01)
        record_property("qr_boundary", "overlap" if shared.two_stickers.is_set() else "PG lock")
        shared.release_stickers.set()
        results = await asyncio.gather(
            _line(first, "first final"),
            _line(second, "second final"),
        )
        record_property("worker_results", json.dumps(results))
        record_property("wb_create_amounts", json.dumps(shared.create_amounts))
        record_property("sticker_requests", json.dumps(shared.sticker_requests))
        assert shared.create_amounts == [5], "concurrent retry duplicated the WB create"
        assert all(r["pg_pid"] == r["final_pg_pid"] for r in results)
        assert await _physical_group_snapshot(supply_id) == physical_before
        async with SessionLocal() as check:
            boxes = list(await check.scalars(select(FbsPackingBox).where(
                FbsPackingBox.id.in_(ids),
            )))
            trbxes = list(await check.scalars(select(FbsTrbx).where(
                FbsTrbx.supply_id == supply_id,
            )))
            operations = list(await check.scalars(select(FbsWbOperation).where(
                FbsWbOperation.local_entity_id == supply_id,
                FbsWbOperation.state == "confirmed",
            )))
            assets = list(await check.scalars(select(FbsPrintAsset).where(
                FbsPrintAsset.fbs_trbx_id.in_([t.id for t in trbxes]),
                FbsPrintAsset.status == "ready",
            )))
            assert len(trbxes) == 5 and len(operations) == 1
            assert len({t.packaging_box_id for t in trbxes}) == 5
            assert all(b.trbx_id in {t.id for t in trbxes} for b in boxes)
            for box_id in other_ids:
                other_box = await check.get(FbsPackingBox, box_id)
                assert other_box is not None and other_box.trbx_id is None
            assert len(assets) == 5
        assert [r["status"] for r in results] == [200, 200], results
    finally:
        shared.release_create.set()
        shared.release_stickers.set()
        for process in processes:
            if process.returncode is None:
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except TimeoutError:
                    process.terminate()
                    await process.wait()
            assert process.stderr is not None
            await process.stderr.read()
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__" and "--c6-worker" in sys.argv:
    asyncio.run(_worker())
