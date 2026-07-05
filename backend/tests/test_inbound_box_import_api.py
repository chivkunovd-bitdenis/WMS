"""BOX-BE-IN: inbound import-boxes preview/apply API."""

from __future__ import annotations

import io
import time
import uuid

import pytest
from httpx import AsyncClient
from openpyxl import Workbook  # type: ignore[import-untyped]

from app.db.session import SessionLocal
from app.services import inbound_intake_box_service as box_svc
from app.services.tokens import decode_access_token

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_bytes(rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def _register_admin(
    async_client: AsyncClient, suffix: str
) -> tuple[dict[str, str], uuid.UUID]:
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"BoxImp {suffix}",
            "slug": f"boximp-{suffix}",
            "admin_email": f"boximp-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = reg.json()["access_token"]
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
    return {"Authorization": f"Bearer {token}"}, tenant_id


async def _submitted_request_with_barcode(
    async_client: AsyncClient,
    ah: dict[str, str],
    suffix: str,
) -> tuple[str, str]:
    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "W", "code": f"w-{suffix}"},
    )
    wid = wh.json()["id"]
    seller = await async_client.post(
        "/sellers",
        headers=ah,
        json={"name": "S", "email": f"s-{suffix}@example.com"},
    )
    assert seller.status_code == 201, seller.text
    sid = seller.json()["id"]
    barcode = f"2047892{suffix[-6:]}"
    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Import product",
            "sku_code": barcode,
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
            "wb_barcode": barcode,
            "seller_id": sid,
        },
    )
    assert pr.status_code == 200, pr.text
    pid = pr.json()["id"]

    cr = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=ah,
        json={"warehouse_id": wid},
    )
    assert cr.status_code == 201, cr.text
    rid = cr.json()["id"]

    ln = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/lines",
        headers=ah,
        json={"product_id": pid, "expected_qty": 10},
    )
    assert ln.status_code == 201, ln.text

    sub = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/submit",
        headers=ah,
    )
    assert sub.status_code == 200, sub.text
    return rid, barcode


@pytest.mark.asyncio
async def test_inbound_import_boxes_preview_and_apply(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    ah, tenant_id = await _register_admin(async_client, suffix)
    rid, barcode = await _submitted_request_with_barcode(async_client, ah, suffix)
    base = f"/operations/inbound-intake-requests/{rid}/import-boxes"
    content = _xlsx_bytes(
        [
            ["Штрих-код", "Кол-во", "Адрес"],
            [barcode, 2, "1"],
            [barcode, 1, "2"],
        ]
    )

    preview = await async_client.post(
        f"{base}/preview",
        headers=ah,
        files={"file": ("boxes.xlsx", content, XLSX_MIME)},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["summary"]["boxes_count"] == 2
    assert body["summary"]["total_units"] == 3

    apply = await async_client.post(
        f"{base}/apply",
        headers=ah,
        data={"ignore_errors": "false"},
        files={"file": ("boxes.xlsx", content, XLSX_MIME)},
    )
    assert apply.status_code == 200, apply.text
    assert apply.json()["boxes_created"] == 2

    async with SessionLocal() as session:
        boxes = await box_svc.list_boxes_with_lines(session, tenant_id, uuid.UUID(rid))
    assert len(boxes) == 2
    assert sum(sum(ln.quantity for ln in b.lines) for b in boxes) == 3


@pytest.mark.asyncio
async def test_inbound_import_boxes_bad_file_no_boxes(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    ah, tenant_id = await _register_admin(async_client, suffix)
    rid, _barcode = await _submitted_request_with_barcode(async_client, ah, suffix)
    base = f"/operations/inbound-intake-requests/{rid}/import-boxes"
    bad = _xlsx_bytes([["Штрих-код", "Кол-во"], ["x", 1]])

    preview = await async_client.post(
        f"{base}/preview",
        headers=ah,
        files={"file": ("bad.xlsx", bad, XLSX_MIME)},
    )
    assert preview.status_code == 422, preview.text

    async with SessionLocal() as session:
        boxes = await box_svc.list_boxes_with_lines(session, tenant_id, uuid.UUID(rid))
    assert boxes == []
