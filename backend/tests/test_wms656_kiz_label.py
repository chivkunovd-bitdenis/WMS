from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.fbs_supply import FbsSupply
from app.models.marking_code import MarkingCode
from app.services.kiz_reprint_service import reprint_label_metadata
from tests.test_wms514_scan_auto_print import _bind_canonical_kiz, _seed_wb_supply

pytestmark = pytest.mark.asyncio
KIZ = "010460000000000121WMS656-FULL"


@pytest.mark.parametrize("artifact", [b"saved-seller-label", None, b""])
async def test_reprints_return_scoped_existing_label_metadata(
    async_client: AsyncClient, artifact: bytes | None
) -> None:
    headers, supply_id, barcode = await _seed_wb_supply(async_client, order_count=1)
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        tenant_id, seller_id = supply.tenant_id, supply.seller_id
        code = MarkingCode(
            tenant_id=tenant_id,
            seller_id=seller_id,
            cis_code=KIZ,
            label_artifact_pdf=artifact,
        )
        session.add(code)
        await session.commit()
        code_id = str(code.id)
        assert await reprint_label_metadata(session, uuid.uuid4(), seller_id, KIZ) == (None, False)
        assert await reprint_label_metadata(session, tenant_id, uuid.uuid4(), KIZ) == (None, False)
        assert await reprint_label_metadata(session, tenant_id, seller_id, KIZ + "OTHER") == (
            None,
            False,
        )

    base = f"/operations/fbs-supplies/{supply_id}"
    for _ in range(2):
        direct = await async_client.post(
            f"{base}/scan-kiz-reprint",
            headers=headers,
            json={"kiz": KIZ, "idempotency_key": "full-label-direct"},
        )
        assert direct.status_code == 201, direct.text
        assert direct.json()["code_id"] == code_id
        assert direct.json()["has_label_artifact"] is bool(artifact)
    selected = await async_client.post(
        f"{base}/scan-auto-print",
        headers=headers,
        json={
            "barcode": barcode,
            "idempotency_key": "full-label-copy",
            "print_qr": False,
            "print_chz": False,
            "reprint_chz": True,
        },
    )
    assert selected.status_code == 200, selected.text
    scan_id = uuid.UUID(selected.json()["scan_id"])
    await _bind_canonical_kiz(supply_id, KIZ, scan_id=scan_id)
    for _ in range(2):
        claim = await async_client.post(
            f"{base}/scan-auto-print/{scan_id}/reprint-claim",
            headers=headers,
            json={"attempt_key": "full-label-attempt"},
        )
        assert claim.status_code == 200, claim.text
        assert claim.json()["kiz"] == KIZ
        assert claim.json()["code_id"] == code_id
        assert claim.json()["has_label_artifact"] is bool(artifact)
    async with SessionLocal() as session:
        unchanged = await session.get(MarkingCode, uuid.UUID(code_id))
        assert unchanged is not None
        assert unchanged.status == "available"
        assert unchanged.label_artifact_pdf == artifact
