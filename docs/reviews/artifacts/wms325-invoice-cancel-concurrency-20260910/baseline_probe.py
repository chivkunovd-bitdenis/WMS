"""Manual SAFE probe: execute only the frozen cancellation functions from 14f36a0d.

Run from backend with PYTHONPATH pointing to backend, the isolated WMS_TEST_DATABASE_URL,
and `pytest -p tests.conftest
../docs/reviews/artifacts/wms325-invoice-cancel-concurrency-20260910/baseline_probe.py`.
This file is evidence tooling, outside the regular test collection. No checkout file is replaced.
"""

from __future__ import annotations

import ast
import asyncio
import subprocess
import uuid
from datetime import date
from typing import Any

import pytest
from app.db.session import SessionLocal
from app.models.billing import BillingInvoice, BillingInvoiceV2
from app.models.document_event import DocumentEvent
from app.models.user import User
from app.services import billing_invoice_service as legacy
from app.services import billing_invoice_v2_service as v2
from app.services.document_event_service import document_event_actor
from httpx import AsyncClient
from sqlalchemy import select
from tests.test_document_events import _register_admin


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["legacy", "v2"])
async def test_frozen_unlocked_cancellation_reproduces_two_facts(
    async_client: AsyncClient,
    kind: str,
) -> None:
    name = (
        "billing_invoice_service" if kind == "legacy" else "billing_invoice_v2_service"
    )
    module = legacy if kind == "legacy" else v2
    source = await asyncio.to_thread(
        subprocess.check_output,
        [
            "git",
            "show",
            f"14f36a0d:backend/app/services/{name}.py",
        ],
        text=True,
    )
    wanted = (
        {"cancel_invoice"}
        if kind == "legacy"
        else {"get_invoice_v2", "cancel_invoice_v2"}
    )
    tree = ast.parse(source)
    functions: list[ast.stmt] = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name in wanted
    ]
    namespace: dict[str, Any] = dict(vars(module))
    exec(  # noqa: S102 -- trusted frozen Git function bodies, no request input
        compile(ast.Module(body=functions, type_ignores=[]), "frozen-14f36a0d", "exec"),
        namespace,
    )
    cancel = namespace["cancel_invoice" if kind == "legacy" else "cancel_invoice_v2"]
    h, claims = await _register_admin(async_client)
    tenant_id = uuid.UUID(str(claims["tenant_id"]))
    actor_one = uuid.UUID(str(claims["sub"]))
    seller = await async_client.post("/sellers", headers=h, json={"name": "Synthetic"})
    async with SessionLocal() as seed:
        other = User(
            tenant_id=tenant_id,
            email=f"probe-{uuid.uuid4().hex}@example.com",
            role="fulfillment_admin",
            password_hash="synthetic-unused",
        )
        seed.add(other)
        args: dict[str, Any] = {
            "tenant_id": tenant_id,
            "seller_id": uuid.UUID(seller.json()["id"]),
            "number": "PROBE",
            "status": "issued",
        }
        invoice = (
            BillingInvoice(
                **args,
                period=date(2026, 7, 1),
                total_amount=100,
                ff_profile_snapshot={},
                seller_profile_snapshot={},
                lines=[],
            )
            if kind == "legacy"
            else BillingInvoiceV2(
                **args, creation_mode="manual", total_amount_kopecks=100
            )
        )
        seed.add(invoice)
        await seed.commit()
        invoice_id, actor_two = invoice.id, other.id
    async with SessionLocal() as first, SessionLocal() as second:
        assert first.bind is not None and first.bind.dialect.name == "postgresql"
        with document_event_actor(actor_one):
            await cancel(first, tenant_id=tenant_id, invoice_id=invoice_id)
        # Both cancellations run while neither transaction has committed its status update.
        with document_event_actor(actor_two):
            await cancel(second, tenant_id=tenant_id, invoice_id=invoice_id)
        await first.commit()
        await second.commit()
    async with SessionLocal() as check:
        rows = list(
            (
                await check.scalars(
                    select(DocumentEvent).where(
                        DocumentEvent.document_id == invoice_id,
                    )
                )
            ).all()
        )
        assert len(rows) == 2
        assert {row.actor_user_id for row in rows} == {actor_one, actor_two}
        assert all(
            row.payload_json["before"]["status"] == "issued"
            and row.payload_json["after"]["status"] == "cancelled"
            for row in rows
        )
