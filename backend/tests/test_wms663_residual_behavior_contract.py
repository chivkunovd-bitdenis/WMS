"""Analyst residual C3/C5/C7/C12/C13/C14; isolated SQLite, fake external I/O."""

import uuid
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select
from test_ozon_box_assembly import seed_boxes
from test_wms663_astra_regressions import SET, SNAPSHOT, STATUS, _accept_a, _exemplar, _scan
from test_wms663_customs_documents_contract import (
    POSTING_NUMBER,
    SKU_ONE,
    SKU_TWO,
    _remote_snapshot,
    _seed_order,
    _transport,
)

from app.api import fbs_supplies as supply_api
from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.seller import Seller
from app.services import fbs_autopoll_service as autopoll
from app.services import ozon_box_assembly_service as assembly
from app.services import ozon_exemplar_documents_service as documents
from app.services.marketplace_account_service import MarketplaceAccountService
from app.services.marketplace_provider import OzonMarketplaceProvider
from app.services.ozon_fbs_errors import OzonFbsProcessError
from app.services.ozon_marketplace_transport import HttpxOzonMarketplaceTransport


@pytest.fixture(autouse=True)
def sqlite_only(db_session):
    assert db_session.get_bind().dialect.name == "sqlite"


def _kwargs(order, transport):
    return dict(
        tenant_id=order.tenant_id,
        order_id=order.id,
        provider=OzonMarketplaceProvider(transport=transport),
        client_id="fake-client",
        api_key="fake-key",
    )


async def _save(session, order, transport, **choice):
    return await documents.save_exemplar_documents(
        session,
        **_kwargs(order, transport),
        product_id=SKU_ONE,
        exemplar_id=81,
        expected_version=documents.document_data(order).get("version"),
        **choice,
    )


def _writes(transport):
    return [deepcopy(payload) for path, payload in transport.endpoint_calls if path == SET]


@pytest.mark.asyncio
async def test_c3_three_exemplars_and_other_orders_sellers_wb_are_isolated(db_session):
    order, first, _ = await _seed_order(db_session)
    first.quantity = 3
    other_seller = Seller(tenant_id=order.tenant_id, name="Other seller")
    db_session.add(other_seller)
    await db_session.flush()
    neighbors = []
    for index, (seller_id, marketplace) in enumerate(
        [
            (order.seller_id, "ozon"),
            (other_seller.id, "ozon"),
            (order.seller_id, "wb"),
        ]
    ):
        neighbor = FbsOrder(
            tenant_id=order.tenant_id,
            seller_id=seller_id,
            warehouse_id=order.warehouse_id,
            product_id=order.product_id,
            marketplace=marketplace,
            external_order_id=f"OTHER-{index}",
            wb_order_id=-100 - index,
            created_at_wb=order.created_at_wb,
            deadline_at=order.deadline_at,
            meta_details_json={"neighbor": index},
            reserve_status=order.reserve_status,
            mapping_status=order.mapping_status,
        )
        db_session.add(neighbor)
        neighbors.append(neighbor)
    await db_session.commit()
    before = [(n.id, deepcopy(n.meta_details_json), n.reserve_status) for n in neighbors]
    snapshot = _remote_snapshot()
    third = deepcopy(_exemplar(snapshot, exemplar_id=82))
    third.update(exemplar_id=83, rnpt="000-RNPT/83", weight=1.75)
    snapshot["products"][0]["exemplars"].append(third)
    transport = _transport(status={**snapshot, "status": "validation_in_process"})
    transport.endpoint_responses[SNAPSHOT] = snapshot
    await _save(
        db_session,
        order,
        transport,
        gtd="000/NEW-81",
        is_gtd_absent=False,
        rnpt=None,
        is_rnpt_absent=True,
    )
    sent = _writes(transport)[0]
    assert len(sent["products"][0]["exemplars"]) == 3
    for sku, exemplar_id in [(SKU_ONE, 82), (SKU_ONE, 83), (SKU_TWO, 91)]:
        assert _exemplar(sent, sku, exemplar_id) == _exemplar(snapshot, sku, exemplar_id)
    assert {payload["posting_number"] for _, payload in transport.endpoint_calls} == {
        POSTING_NUMBER
    }
    for neighbor, (identity, metadata, reserve) in zip(neighbors, before, strict=True):
        await db_session.refresh(neighbor)
        assert (neighbor.id, neighbor.meta_details_json, neighbor.reserve_status) == (
            identity,
            metadata,
            reserve,
        )
        calls = len(transport.endpoint_calls)
        with pytest.raises(OzonFbsProcessError) as foreign:
            await documents.get_exemplar_documents(
                db_session,
                **{
                    **_kwargs(neighbor, transport),
                    "tenant_id": uuid.uuid4(),
                },
            )
        assert foreign.value.status_code == 404
        assert len(transport.endpoint_calls) == calls
        with pytest.raises(OzonFbsProcessError) as foreign_write:
            await documents.save_exemplar_documents(
                db_session,
                **{**_kwargs(neighbor, transport), "tenant_id": uuid.uuid4()},
                product_id=SKU_ONE,
                exemplar_id=81,
                expected_version=None,
                gtd="FOREIGN",
                is_gtd_absent=False,
                rnpt=None,
                is_rnpt_absent=False,
            )
        assert foreign_write.value.status_code == 404
        assert len(transport.endpoint_calls) == calls
    calls = len(transport.endpoint_calls)
    with pytest.raises(OzonFbsProcessError):
        await _save(
            db_session,
            neighbors[-1],
            transport,
            gtd="WB",
            is_gtd_absent=False,
            rnpt=None,
            is_rnpt_absent=False,
        )
    assert len(transport.endpoint_calls) == calls


@pytest.mark.asyncio
async def test_c5_gtd_then_kiz_then_rnpt_preserves_each_complete_set(db_session):
    order, first, _ = await _seed_order(db_session)
    transport = _transport(status={**_remote_snapshot(), "status": "ship_available"})
    await _accept_a(db_session, order, transport)
    initial = _writes(transport)[0]
    # Fake cabinet readbacks follow the acknowledged full payload, never partial positives.
    transport.endpoint_responses[SNAPSHOT] = initial
    transport.endpoint_responses[STATUS] = {**initial, "status": "ship_available"}
    await _scan(db_session, order, first, transport, 81)
    marked = _writes(transport)[1]
    transport.endpoint_responses[SNAPSHOT] = marked
    transport.endpoint_responses[STATUS] = {**marked, "status": "ship_available"}
    await _save(
        db_session,
        order,
        transport,
        gtd="001/ABC-09",
        is_gtd_absent=False,
        rnpt="000/RNPT-NEW",
        is_rnpt_absent=False,
    )
    final = _writes(transport)[2]
    assert len(_writes(transport)) == 3
    assert (
        _exemplar(initial)["gtd"]
        == _exemplar(marked)["gtd"]
        == _exemplar(final)["gtd"]
        == "001/ABC-09"
    )
    assert _exemplar(marked)["marks"][-1]["mark"].endswith("81")
    assert _exemplar(final)["marks"] == _exemplar(marked)["marks"]
    assert _exemplar(final)["rnpt"] == "000/RNPT-NEW"
    assert _exemplar(final)["is_rnpt_absent"] is False
    for sent in (initial, marked, final):
        assert sent["multi_box_qty"] == 3
        assert _exemplar(sent)["weight"] == 1.25
        for sku, exemplar_id in [(SKU_ONE, 82), (SKU_TWO, 91)]:
            assert _exemplar(sent, sku, exemplar_id) == _exemplar(
                _remote_snapshot(), sku, exemplar_id
            )


@pytest.mark.asyncio
async def test_c7_foreign_exemplar_id_cannot_accept_and_status_can_resolve(db_session):
    order, _, _ = await _seed_order(db_session)
    foreign = _remote_snapshot()
    _exemplar(foreign)["exemplar_id"] = 99981
    transport = _transport(status={**foreign, "status": "ship_available"})
    view = await _save(
        db_session,
        order,
        transport,
        gtd="001/ABC-09",
        is_gtd_absent=False,
        rnpt=None,
        is_rnpt_absent=True,
    )
    assert view["state"] != "accepted"
    assert _exemplar(view)["gtd"] == "001/ABC-09"
    transport.endpoint_responses[STATUS] = {**_remote_snapshot(), "status": "ship_available"}
    calls = len(transport.endpoint_calls)
    resolved = await documents.resume_exemplar_document_check(
        db_session, **_kwargs(order, transport)
    )
    assert [path for path, _ in transport.endpoint_calls[calls:]] == [STATUS]
    assert len(_writes(transport)) == 1
    assert resolved["state"] == "accepted", {
        "view_state": resolved["state"],
        "stored_state": documents.document_data(order)["state"],
        "snapshot_ids": [
            e["exemplar_id"]
            for e in documents.document_data(order)["snapshot"]["products"][0]["exemplars"]
        ],
        "current_ids": [
            e["exemplar_id"]
            for e in documents.document_data(order)["last_status"]["products"][0]["exemplars"]
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("optional", ["missing", "null"])
async def test_c12_optional_missing_nullable_preserves_input_and_rejection(db_session, optional):
    order, _, _ = await _seed_order(db_session)
    raw = _remote_snapshot()
    for product in raw["products"]:
        for exemplar in product["exemplars"]:
            for field in [
                "weight",
                "marks",
                "gtd_check_status",
                "rnpt_check_status",
                "rnpt_error_codes",
            ]:
                if optional == "null":
                    exemplar[field] = None
                else:
                    exemplar.pop(field, None)
    _exemplar(raw)["gtd_error_codes"] = ["gtd_invalid"]
    transport = _transport(status={**raw, "status": "ship_not_available"})
    view = await _save(
        db_session,
        order,
        transport,
        gtd="001/ABC-09",
        is_gtd_absent=False,
        rnpt=None,
        is_rnpt_absent=True,
    )
    assert view["state"] != "accepted"
    assert _exemplar(view)["gtd"] == "001/ABC-09"
    assert "gtd_invalid" in _exemplar(view)["errors"]
    assert documents.document_data(order)["choices"][f"{SKU_ONE}:81"]["gtd"] == "001/ABC-09"


@pytest.mark.asyncio
async def test_c12_real_json_decode_failure_is_bounded_unknown_with_saved_choice(db_session):
    order, _, _ = await _seed_order(db_session)
    transport = _transport()
    await _save(
        db_session,
        order,
        transport,
        gtd="001/ABC-09",
        is_gtd_absent=False,
        rnpt=None,
        is_rnpt_absent=True,
    )
    requests = []

    def malformed(request):
        requests.append(request.url.path)
        return httpx.Response(
            200, content=b'{"broken":', headers={"Content-Type": "application/json"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(malformed)) as client:
        provider = OzonMarketplaceProvider(
            transport=HttpxOzonMarketplaceTransport(
                base_url="https://ozon.invalid",
                client=client,
            )
        )
        view = await documents.resume_exemplar_document_check(
            db_session,
            **{
                **_kwargs(order, transport),
                "provider": provider,
            },
        )
    assert requests == [STATUS]
    assert view["state"] == "unknown"
    assert view["errors"]
    assert _exemplar(view)["gtd"] == "001/ABC-09"
    assert documents.document_data(order)["choices"][f"{SKU_ONE}:81"]["gtd"] == "001/ABC-09"
    assert len(_writes(transport)) == 1


@pytest.mark.asyncio
async def test_c13_background_restart_selects_gtd_only_without_marking(db_session, monkeypatch):
    order, _, _ = await _seed_order(db_session)
    transport = _transport()
    await _save(
        db_session,
        order,
        transport,
        gtd="001/ABC-09",
        is_gtd_absent=False,
        rnpt=None,
        is_rnpt_absent=True,
    )
    identities = order.tenant_id, order.seller_id, order.id
    saved_choices = deepcopy(documents.document_data(order)["choices"])
    assert await db_session.scalar(select(func.count()).select_from(FbsOrderMarking)) == 0
    await db_session.close()

    async def credentials(*args):
        return "fake-client", "fake-key"

    monkeypatch.setattr(MarketplaceAccountService, "stored_credentials", credentials)

    # Ordinary status synchronization is outside this document-only regression.
    async def ordinary_sync(*args):
        return 0

    monkeypatch.setattr(autopoll, "sync_ozon_order_statuses", ordinary_sync)
    transport.endpoint_responses[STATUS] = {**_remote_snapshot(), "status": "ship_available"}
    calls = len(transport.endpoint_calls)
    async with (
        SessionLocal() as restarted,
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: pytest.fail("unexpected real HTTP path"))
        ) as client,
    ):
        await autopoll.sync_marketplace_order_statuses_for_target(
            restarted,
            autopoll.SellerPollTarget(identities[0], identities[1], "ozon"),
            client,
            ozon_provider=OzonMarketplaceProvider(transport=transport),
        )
        restored = await documents.document_order(restarted, identities[0], identities[2])
        assert documents.document_data(restored)["state"] == "accepted"
        assert documents.document_data(restored)["choices"] == saved_choices
        assert await restarted.scalar(select(func.count()).select_from(FbsOrderMarking)) == 0
    assert [path for path, _ in transport.endpoint_calls[calls:]] == [STATUS]
    assert len(_writes(transport)) == 1


@pytest.mark.asyncio
async def test_c14_existing_qr_after_accepted_preserves_documents_and_local_accounting(
    db_session, monkeypatch
):
    order, first, second = await _seed_order(db_session)
    supply = FbsSupply(
        tenant_id=order.tenant_id,
        seller_id=order.seller_id,
        warehouse_id=order.warehouse_id,
        marketplace="ozon",
        name="QR residual",
        status="assembling",
        delivery_type="warehouse_sc",
    )
    db_session.add(supply)
    await db_session.flush()
    order.supply_id = supply.id
    await db_session.commit()
    boxes = await seed_boxes(db_session, order, supply)
    transport = _transport(status={**_remote_snapshot(), "status": "ship_available"})
    before = (
        order.reserve_status,
        order.status,
        order.pick_status,
        order.pack_status,
        first.picked_quantity,
        second.picked_quantity,
    )
    accounting_before = {
        model: await db_session.scalar(select(func.count()).select_from(model))
        for model in (InventoryBalance, InventoryMovement)
    }
    await _accept_a(db_session, order, transport)
    accepted = deepcopy(documents.document_data(order))
    assert (
        order.reserve_status,
        order.status,
        order.pick_status,
        order.pack_status,
        first.picked_quantity,
        second.picked_quantity,
    ) == before
    assert await db_session.scalar(select(func.count()).select_from(FbsPrintAsset)) == 0
    assert not any(path.endswith("/ship") for path, _ in transport.endpoint_calls)
    assert not transport.calls and not transport.published_stocks
    for model, count in accounting_before.items():
        assert await db_session.scalar(select(func.count()).select_from(model)) == count
    transport.endpoint_responses.update(
        {
            SNAPSHOT: accepted["snapshot"],
            STATUS: {**accepted["snapshot"], "status": "ship_available"},
            "/v3/posting/fbs/get": {
                "result": {
                    "posting_number": POSTING_NUMBER,
                    "status": "awaiting_packaging",
                    "requirements": {"products_requiring_gtd": [SKU_ONE]},
                }
            },
            "/v1/posting/fbs/restrictions": {"result": {"posting_number": POSTING_NUMBER}},
            "/v4/posting/fbs/ship": {"result": [POSTING_NUMBER + "-1", POSTING_NUMBER + "-2"]},
        }
    )

    async def credentials(*args):
        return "fake-client", "fake-key"

    monkeypatch.setattr(MarketplaceAccountService, "stored_credentials", credentials)
    monkeypatch.setattr(assembly, "ozon_live_api_enabled", lambda: True)
    monkeypatch.setattr(
        assembly, "build_ozon_provider", lambda: OzonMarketplaceProvider(transport=transport)
    )
    labels = []

    async def fake_label_batch(*args, **kwargs):
        labels.append(kwargs["order_ids"])
        return SimpleNamespace(order_errors=[], ready=1)

    monkeypatch.setattr(supply_api, "request_supply_print_batch", fake_label_batch)
    await supply_api.retry_fbs_packing_box_qr(
        supply.id,
        boxes[0].id,
        SimpleNamespace(tenant_id=order.tenant_id),
        db_session,
    )
    await db_session.refresh(order)
    ships = [payload for path, payload in transport.endpoint_calls if path.endswith("/ship")]
    assert ships == [
        {
            "posting_number": POSTING_NUMBER,
            "packages": [
                {"products": [{"product_id": SKU_ONE, "quantity": 2}]},
                {"products": [{"product_id": SKU_TWO, "quantity": 1}]},
            ],
            "with": {"additional_data": True},
        }
    ]
    assert labels == [[order.id]]
    assert documents.document_data(order)["choices"] == accepted["choices"]
    assert documents.document_data(order)["snapshot"] == accepted["snapshot"]
    for payload in _writes(transport):
        for sku, exemplar_id in [(SKU_ONE, 81), (SKU_ONE, 82), (SKU_TWO, 91)]:
            assert _exemplar(payload, sku, exemplar_id) == _exemplar(
                accepted["payload"], sku, exemplar_id
            )
    assert order.reserve_status == before[0]
    for model, count in accounting_before.items():
        assert await db_session.scalar(select(func.count()).select_from(model)) == count
    assert not transport.published_stocks
    assert await db_session.scalar(select(func.count()).select_from(FbsPrintAsset)) == 0
