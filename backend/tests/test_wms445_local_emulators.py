"""Local fixture guards and wire state transitions used by WMS445 acceptance."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from tools import wms445_local_http as guard
from tools import wms445_ozon_emulator as emulator


@pytest.mark.asyncio
async def test_http_guard_blocks_external_and_redirect_before_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(guard, "_INSTALLED", False)
    monkeypatch.setattr(
        httpx.AsyncClient, "_send_single_request", httpx.AsyncClient._send_single_request
    )
    monkeypatch.setattr(httpx.Client, "_send_single_request", httpx.Client._send_single_request)
    guard.install_http_guard()
    calls = []

    def transport(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://example.invalid/never-contact"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(httpx.ConnectError, match="blocked"):
            await client.get("https://example.invalid/never-contact")
        assert calls == []
        with pytest.raises(httpx.ConnectError, match="blocked"):
            await client.get("http://127.0.0.1:19093/redirect", follow_redirects=True)
        assert calls == ["http://127.0.0.1:19093/redirect"]


@pytest.mark.asyncio
async def test_ozon_fixture_preserves_success_after_lost_approve(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(emulator, "STATE_PATH", tmp_path / "ozon.json")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=emulator.app), base_url="http://127.0.0.1:19093"
    ) as client:
        headers = {"Client-Id": "445a", "Api-Key": "wms445-synthetic"}
        posting: dict[str, Any] = {
            "posting_number": "445-a-1",
            "fixture_client": "445a",
            "status": "awaiting_packaging",
            "products": [{"sku": 445100, "quantity": 2}, {"sku": 445101, "quantity": 1}],
        }
        assert (await client.post("/__admin/seed", json={"postings": [posting]})).status_code == 200
        ship = await client.post(
            "/v4/posting/fbs/ship",
            headers=headers,
            json={
                "posting_number": "445-a-1",
                "packages": [
                    {
                        "products": [
                            {"product_id": 445100, "quantity": 2},
                            {"product_id": 445101, "quantity": 1},
                        ]
                    }
                ],
            },
        )
        assert ship.status_code == 200, ship.text
        created = await client.post(
            "/v1/carriage/create", headers=headers, json={"delivery_method_id": 44501}
        )
        carriage_id = created.json()["carriage_id"]
        await client.post(
            "/__admin/faults", json={"path": "/v1/carriage/approve", "timing": "after"}
        )
        failed = await client.post(
            "/v1/carriage/approve", headers=headers, json={"carriage_id": carriage_id}
        )
        assert failed.status_code == 503
        read = await client.post(
            "/v1/carriage/get", headers=headers, json={"carriage_id": carriage_id}
        )
        assert read.json()["status"] == "formed"
        state = (await client.get("/__admin/state")).json()
        assert len(state["carriages"]) == 1
        assert sum(c["path"] == "/v1/carriage/approve" for c in state["calls"]) == 1
        assert "Api-Key" not in str(state)
        label = await client.post(
            "/v2/posting/fbs/package-label/create",
            headers=headers,
            json={"posting_number": ["445-a-1"]},
        )
        assert label.status_code == 200, label.text
        task = label.json()["result"]["tasks"][0]["task_id"]
        pdf = await client.get(f"/labels/{task}.pdf")
        assert pdf.content.startswith(b"%PDF-")
