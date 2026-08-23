from __future__ import annotations

import time
import uuid
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.warehouse import Warehouse

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/20260822_0094_warehouse_operational_barcode.py"
)
_migration_spec = spec_from_file_location("warehouse_operational_migration", _MIGRATION_PATH)
assert _migration_spec is not None and _migration_spec.loader is not None
_migration = module_from_spec(_migration_spec)
_migration_spec.loader.exec_module(_migration)


def test_migration_does_not_promote_tenant_only_technical_warehouse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        SimpleNamespace(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            name="FBS WB Legacy",
            code="fbs-wb-legacy",
        )
    ]

    class Result:
        def __init__(self, values: list[SimpleNamespace] | None = None) -> None:
            self.values = values or []

        def fetchall(self) -> list[SimpleNamespace]:
            return self.values

    class Connection:
        def __init__(self) -> None:
            self.calls = 0
            self.update_params: list[dict[str, object]] = []

        def execute(self, statement: object) -> Result:
            self.calls += 1
            if self.calls == 1:
                return Result(rows)
            self.update_params.append(statement.compile().params)  # type: ignore[attr-defined]
            return Result()

    connection = Connection()
    monkeypatch.setattr(_migration.op, "add_column", lambda *args, **kwargs: None)
    monkeypatch.setattr(_migration.op, "get_bind", lambda: connection)
    monkeypatch.setattr(_migration.op, "alter_column", lambda *args, **kwargs: None)
    monkeypatch.setattr(_migration.op, "create_index", lambda *args, **kwargs: None)

    _migration.upgrade()

    assert len(connection.update_params) == 1
    assert connection.update_params[0]["is_operational"] is False


@pytest.mark.asyncio
async def test_operational_warehouse_list_and_scan_resolver(async_client: AsyncClient) -> None:
    suffix = str(time.time_ns())
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Warehouse Scan Co",
            "slug": f"warehouse-scan-{suffix}",
            "admin_email": f"warehouse-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    warehouse = await async_client.post(
        "/warehouses", headers=headers, json={"name": "Основной", "code": "main"}
    )
    assert warehouse.status_code == 200, warehouse.text
    body = warehouse.json()
    assert body["is_operational"] is True
    assert body["barcode"].startswith("WH-")

    async with SessionLocal() as session:
        stored_warehouse = await session.get(Warehouse, uuid.UUID(body["id"]))
        assert stored_warehouse is not None
        technical = Warehouse(
            tenant_id=stored_warehouse.tenant_id,
            name="FBS WB Legacy",
            code="fbs-wb-legacy",
            is_operational=False,
        )
        session.add(technical)
        await session.commit()

    listed = await async_client.get("/warehouses", headers=headers)
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [body["id"]]

    warehouse_scan = await async_client.get(
        "/warehouses/resolve", headers=headers, params={"barcode": body["barcode"]}
    )
    assert warehouse_scan.status_code == 200, warehouse_scan.text
    assert warehouse_scan.json()["type"] == "warehouse"

    location = await async_client.post(
        f"/warehouses/{body['id']}/locations", headers=headers, json={"code": "A-01"}
    )
    assert location.status_code == 200, location.text
    location_scan = await async_client.get(
        "/warehouses/resolve",
        headers=headers,
        params={"barcode": location.json()["barcode"]},
    )
    assert location_scan.status_code == 200, location_scan.text
    assert location_scan.json()["type"] == "location"

    second = await async_client.post(
        "/warehouses", headers=headers, json={"name": "Юг", "code": "A-01"}
    )
    assert second.status_code == 200, second.text
    collision = await async_client.get(
        "/warehouses/resolve", headers=headers, params={"barcode": "A-01"}
    )
    assert collision.status_code == 409
    assert collision.json()["detail"] == "barcode_ambiguous"
