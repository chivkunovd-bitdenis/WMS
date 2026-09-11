"""Execute WMS-060's actual saveRule payload builder, then send it to the real ASGI API."""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.stock_direction import StockDirection
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from tests.test_product_fbs_rule_bulk_read_api import (
    _create_product,
    _create_seller,
    _register_tenant,
)

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
EXTRACT_SAVE = r"""
const fs = require('node:fs');
const ts = require('typescript');
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
const path = 'src/screens/ff/products-fbs/FfProductsFbsPage.tsx';
const file = ts.createSourceFile(path, fs.readFileSync(path, 'utf8'), ts.ScriptTarget.Latest, true,
                                 ts.ScriptKind.TSX);
let declaration, ruleDeclaration;
function visit(node) {
  if (ts.isFunctionDeclaration(node) && node.name?.text === 'saveRule') declaration = node;
  if (ts.isFunctionDeclaration(node) && node.name?.text === 'toRule') ruleDeclaration = node;
  ts.forEachChild(node, visit);
}
visit(file);
if (!declaration) throw new Error('saveRule not found');
const code = ts.transpileModule(declaration.getText(file), {
  compilerOptions: { target: ts.ScriptTarget.ES2022 }
}).outputText;
const calls = [];
const save = new Function('fetch','apiUrl','headers','token','setError','load',
                         'readApiErrorMessage',
                         code + ';return saveRule;')(
  async (url, options) => { calls.push({url, body: JSON.parse(options.body)}); return {ok:true}; },
  p => p, () => ({}), '', () => {}, async () => {}, async () => 'error');
if (data.apiRule) {
  const keyExports = {};
  const keyCode = ts.transpileModule(fs.readFileSync(
    'src/screens/ff/products-fbs/fbsWarehouseRuleKeys.ts', 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS }
    }).outputText;
  new Function('exports', keyCode)(keyExports);
  const mapper = new Function('qualifyWarehouseRuleValues', ts.transpileModule(
    ruleDeclaration.getText(file).replace(/^export /, ''), {
      compilerOptions: { target: ts.ScriptTarget.ES2022 }
    }).outputText + ';return toRule;')(keyExports.qualifyWarehouseRuleValues);
  data.rule = mapper(data.ids[0], data.apiRule, data.bindings);
  const key = keyExports.warehouseRuleKey(data.bindings[0]);
  if (data.rule.unitsByWarehouse[key] !== 5) throw new Error('WB cap not loaded as 5');
  data.rule.unitsByWarehouse[key] = 4;
}
save(data.ids, data.rule).then(() => process.stdout.write(JSON.stringify(calls)));
"""


async def _stock(session: AsyncSession, product_ids: list[str], seller_id: str) -> None:
    product = await session.get(Product, uuid.UUID(product_ids[0]))
    assert product is not None
    warehouse = Warehouse(tenant_id=product.tenant_id, code="http-stock", name="HTTP stock")
    session.add(warehouse)
    await session.flush()
    location = StorageLocation(
        tenant_id=product.tenant_id,
        warehouse_id=warehouse.id,
        code="http-cell",
        barcode="http-cell",
    )
    session.add(location)
    await session.flush()
    session.add(
        FbsWarehouseBinding(
            tenant_id=product.tenant_id,
            seller_id=uuid.UUID(seller_id),
            wms_warehouse_id=warehouse.id,
            wb_warehouse_id=501001,
        )
    )
    for pid in product_ids:
        session.add(
            InventoryBalance(
                tenant_id=product.tenant_id,
                product_id=uuid.UUID(pid),
                storage_location_id=location.id,
                quantity=5,
                quantity_unpacked=5,
            )
        )
    await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 2])
async def test_actual_frontend_save_preserves_units_through_http(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    count: int,
) -> None:
    if not shutil.which("node") or not (FRONTEND / "node_modules/typescript").exists():
        pytest.skip("requires frontend npm ci to execute the actual TypeScript saveRule")
    monkeypatch.setattr(
        "app.services.fbs_stock_rule_service.schedule_seller_stock_publish", lambda *_: None
    )
    headers, suffix = await _register_tenant(async_client, "WMS060")
    seller_id = await _create_seller(async_client, headers, name="Synthetic stock seller")
    ids = [
        await _create_product(async_client, headers, seller_id=seller_id, suffix=f"{suffix}-{i}")
        for i in range(count)
    ]
    async with SessionLocal() as session:
        await _stock(session, ids, seller_id)
    capture = subprocess.run(
        ["node", "-e", EXTRACT_SAVE],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        check=True,
        input=json.dumps(
            {
                "ids": ids,
                "rule": {
                    "publish": True,
                    "publishOzon": False,
                    "sameEverywhere": False,
                    "percent": 0,
                    "byWarehouse": {},
                    "unitsMode": True,
                    "unitsByWarehouse": {"501001": 5},
                },
            }
        ),
    )
    calls = json.loads(capture.stdout)
    assert len(calls) == 1
    response = await async_client.put(calls[0]["url"], headers=headers, json=calls[0]["body"])
    assert response.status_code == 200, response.text
    for pid in ids:
        reread = await async_client.get(f"/products/{pid}/fbs-rule", headers=headers)
        assert reread.status_code == 200, reread.text
        assert reread.json()["units_mode"] is True
        assert reread.json()["units_by_warehouse"] == {"501001": 5}
        assert reread.json()["published_now"] == 5


@pytest.mark.asyncio
async def test_manual_binding_http_uses_physical_stock_and_retains_caps_in_percent_mode(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.fbs_stock_rule_service.schedule_seller_stock_publish", lambda *_: None
    )
    headers, suffix = await _register_tenant(async_client, "LegacyCap")
    seller_id = await _create_seller(async_client, headers, name="Synthetic legacy cap seller")
    pid = await _create_product(async_client, headers, seller_id=seller_id, suffix=suffix)
    async with SessionLocal() as session:
        await _stock(session, [pid], seller_id)
    url = f"/operations/fbs-sellers/{seller_id}/warehouse-bindings/501001/stock-pool/{pid}"
    saved = await async_client.put(url, headers=headers, json={"quantity": 5})
    assert saved.status_code == 200, saved.text
    assert saved.json() == {
        "product_id": pid,
        "quantity": 5,
        "pool_limit": 5,
        "allocated_total": 5,
        "available": 5,
    }
    too_much = await async_client.put(url, headers=headers, json={"quantity": 6})
    assert too_much.status_code == 409, too_much.text
    percent = await async_client.put(
        f"/products/{pid}/fbs-rule",
        headers=headers,
        json={"publish": True, "same_everywhere": True, "percent": 50, "units_mode": False},
    )
    assert percent.status_code == 200, percent.text
    assert percent.json()["units_by_warehouse"] == {"501001": 5}
    assert percent.json()["published_now"] == 2

    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(pid))
        assert product is not None
        binding = await session.scalar(
            select(FbsWarehouseBinding).where(
                FbsWarehouseBinding.seller_id == uuid.UUID(seller_id),
            )
        )
        assert binding is not None
        other = FbsWarehouseBinding(
            tenant_id=product.tenant_id,
            seller_id=product.seller_id,
            wms_warehouse_id=binding.wms_warehouse_id,
            wb_warehouse_id=501002,
        )
        session.add(other)
        await session.flush()
        session.add(
            FbsBindingStockPool(
                tenant_id=product.tenant_id,
                product_id=product.id,
                binding_id=other.id,
                quantity=3,
            )
        )
        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.product_id == product.id,
            )
        )
        assert balance is not None
        balance.quantity = balance.quantity_unpacked = 2
        session.add(
            StockDirection(
                tenant_id=product.tenant_id,
                product_id=product.id,
                name="Synthetic reserve",
                quantity=1,
            )
        )
        await session.commit()
    # Caps 5+3 survive depletion; real free is 2 minus an ordinary reserve of 1.
    listed = await async_client.get(url.rsplit("/", 1)[0], headers=headers)
    assert listed.status_code == 200, listed.text
    row = next(row for row in listed.json() if row["product_id"] == pid)
    assert row["allocated_this_binding"] == 5
    assert row["allocated_elsewhere"] == 3
    assert row["pool_limit"] == row["available_for_this_binding"] == 1
    restored = await async_client.put(url, headers=headers, json={"quantity": 5})
    assert restored.status_code == 200, restored.text
    assert restored.json()["pool_limit"] == restored.json()["available"] == 1
    assert restored.json()["allocated_total"] == 8
    rule = await async_client.get(f"/products/{pid}/fbs-rule", headers=headers)
    assert rule.status_code == 200, rule.text
    assert rule.json()["units_mode"] is True
    assert rule.json()["units_by_warehouse"] == {"501001": 5, "501002": 3}
    assert rule.json()["free_stock"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 2])
async def test_colliding_wb_ozon_ids_survive_actual_frontend_http_edit(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    count: int,
) -> None:
    monkeypatch.setattr(
        "app.services.fbs_stock_rule_service.schedule_seller_stock_publish", lambda *_: None
    )
    headers, suffix = await _register_tenant(async_client, "Collision")
    seller_id = await _create_seller(async_client, headers, name="Synthetic collision")
    ids = [
        await _create_product(async_client, headers, seller_id=seller_id, suffix=f"{suffix}-{i}")
        for i in range(count)
    ]
    async with SessionLocal() as session:
        await _stock(session, ids, seller_id)
        wb = await session.scalar(
            select(FbsWarehouseBinding).where(FbsWarehouseBinding.seller_id == uuid.UUID(seller_id))
        )
        assert wb is not None
        wb.wb_warehouse_id = 123
        wb.stock_sync_enabled = True
        ozon = FbsWarehouseBinding(
            tenant_id=wb.tenant_id,
            seller_id=wb.seller_id,
            wms_warehouse_id=wb.wms_warehouse_id,
            marketplace="ozon",
            wb_warehouse_id=123,
            stock_sync_enabled=True,
        )
        session.add(ozon)
        await session.flush()
        for pid in ids:
            product = await session.get(Product, uuid.UUID(pid))
            assert product is not None
            product.fbs_units_mode = True
            product.fbs_stock_sync_enabled = product.fbs_ozon_stock_sync_enabled = True
            balance = await session.scalar(
                select(InventoryBalance).where(InventoryBalance.product_id == product.id)
            )
            assert balance is not None
            balance.quantity = balance.quantity_unpacked = 10
            for binding, quantity in [(wb, 5), (ozon, 3)]:
                session.add(
                    FbsBindingStockPool(
                        tenant_id=wb.tenant_id,
                        product_id=product.id,
                        binding_id=binding.id,
                        quantity=quantity,
                    )
                )
        await session.commit()
    rule = await async_client.get(f"/products/{ids[0]}/fbs-rule", headers=headers)
    assert rule.status_code == 200, rule.text
    capture = subprocess.run(
        ["node", "-e", EXTRACT_SAVE],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        check=True,
        input=json.dumps(
            {
                "ids": ids,
                "apiRule": rule.json(),
                "bindings": [
                    {"wb_warehouse_id": 123, "marketplace": "wb"},
                    {"wb_warehouse_id": 123, "marketplace": "ozon"},
                ],
            }
        ),
    )
    call = json.loads(capture.stdout)[0]
    response = await async_client.put(call["url"], headers=headers, json=call["body"])
    assert response.status_code == 200, response.text
    for pid in ids:
        reread = await async_client.get(f"/products/{pid}/fbs-rule", headers=headers)
        assert reread.status_code == 200, reread.text
        assert reread.json()["units_by_warehouse"] == {"wb:123": 4, "ozon:123": 3}
        assert reread.json()["units_mode"] is True
