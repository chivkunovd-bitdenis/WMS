from __future__ import annotations

import csv
import io
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_marking_ledger_import_aggregate import _import_codes_to_pool
from test_packaging_tasks import _register_admin

from app.db.session import SessionLocal
from app.models.marking_code import MarkingCode, MarkingCodeEvent


@pytest.mark.asyncio
async def test_ledger_and_export_include_external_events_with_existing_scope_filters(
    async_client: AsyncClient,
) -> None:
    headers, seller_id, product_id, _ = await _import_codes_to_pool(async_client, code_count=2)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    async with SessionLocal() as session:
        pool_code = await session.scalar(
            select(MarkingCode).where(MarkingCode.tenant_id == tenant_id)
        )
        assert pool_code and pool_code.pool_id
        pool_id = pool_code.pool_id
        code = MarkingCode(
            tenant_id=tenant_id,
            seller_id=uuid.UUID(seller_id),
            product_id=uuid.UUID(product_id),
            cis_code="010460043993125321KIZEXTERNAL084",
            source="external_fbs",
            status="void",
        )
        session.add(code)
        await session.flush()
        code_id = code.id
        for event_type in ["applied", "voided", "wb_orphaned"]:
            session.add(
                MarkingCodeEvent(
                    tenant_id=tenant_id,
                    seller_id=code.seller_id,
                    code_id=code.id,
                    event_type=event_type,
                    document_number="PKG-084",
                    reason=f"existing-{event_type}-reason",
                )
            )
        await session.commit()
    url = "/operations/marking-codes/ledger"
    ledger = await async_client.get(url, headers=headers)
    assert ledger.status_code == 200, ledger.text
    assert ledger.json()["total"] == 4  # Two pool imports remain collapsed into one row.
    assert {r["event_type"] for r in ledger.json()["rows"]} == {
        "imported",
        "applied",
        "voided",
        "wb_orphaned",
    }
    filtered = await async_client.get(
        url,
        headers=headers,
        params={
            "seller_id": seller_id,
            "product_id": product_id,
            "document": "PKG-084",
            "event_type": "voided",
        },
    )
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["total"] == 1
    assert filtered.json()["rows"][0]["pool_title"] is None
    pooled = await async_client.get(url, headers=headers, params={"pool_id": str(pool_id)})
    assert pooled.json()["total"] == 1
    assert pooled.json()["rows"][0]["event_type"] == "imported"
    for param in ["seller_id", "product_id", "pool_id"]:
        absent = await async_client.get(url, headers=headers, params={param: str(uuid.uuid4())})
        assert absent.json()["total"] == 0
    history = await async_client.get(
        f"/operations/marking-codes/codes/{code_id}/history", headers=headers
    )
    assert history.status_code == 200, history.text
    assert {row["reason"] for row in history.json()} == {
        f"existing-{kind}-reason" for kind in ["applied", "voided", "wb_orphaned"]
    }
    exported = await async_client.get(
        url + "/export", headers=headers, params={"document": "PKG-084"}
    )
    assert exported.status_code == 200, exported.text
    data = list(csv.reader(io.StringIO(exported.text.lstrip("\ufeff"))))
    assert len(data) == 4
    assert {row[1] for row in data[1:]} == {"applied", "voided", "wb_orphaned"}
    other_headers = await _register_admin(async_client)
    hidden = await async_client.get(url, headers=other_headers)
    assert hidden.json()["total"] == 0
    hidden_export = await async_client.get(url + "/export", headers=other_headers)
    assert len(list(csv.reader(io.StringIO(hidden_export.text.lstrip("\ufeff"))))) == 1
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, code_id)
        assert code and code.status == "void" and code.source == "external_fbs"
