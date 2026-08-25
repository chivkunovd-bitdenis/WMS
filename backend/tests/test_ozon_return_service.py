"""Contract coverage for importing Ozon return giveouts without network access."""

from __future__ import annotations

import base64
import uuid
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models import Base
from app.models.inbound_intake import InboundIntakeRequest
from app.models.marketplace_account import MarketplaceAccount
from app.models.ozon_return import InboundOzonReturnGiveout
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services.integration_fernet import encrypt_secret
from app.services.marketplace_provider import MarketplaceProviderError, OzonMarketplaceProvider
from app.services.ozon_return_service import (
    OzonReturnError,
    build_preview,
    get_giveout_pass_pdf,
    import_selected_giveouts,
    imported_groups,
)


@dataclass
class ReturnScope:
    tenant_id: uuid.UUID
    seller_id: uuid.UUID
    request_id: uuid.UUID
    warehouse_id: uuid.UUID


@dataclass
class FakeOzonReturnsTransport:
    """Stateful Ozon fake that pages solely from the request payload."""

    enabled: bool = True
    giveouts: list[dict[str, object]] = field(default_factory=list)
    returns_by_warehouse: dict[int, list[dict[str, object]]] = field(default_factory=dict)
    errors: dict[str, MarketplaceProviderError] = field(default_factory=dict)
    pdf_response: dict[str, object] = field(default_factory=dict)

    async def call(
        self,
        *,
        client_id: str,
        api_key: str,
        path: str,
        payload: Mapping[str, object],
    ) -> object:
        _ = client_id, api_key
        if error := self.errors.get(path):
            raise error
        if path == "/v1/return/giveout/is-enabled":
            return {"enabled": self.enabled}
        if path == "/v1/return/giveout/list":
            return {"giveouts": self._page(self.giveouts, payload)}
        if path == "/v1/return/giveout/info":
            giveout_id = int(payload["giveout_id"])
            giveout = next(item for item in self.giveouts if item["giveout_id"] == giveout_id)
            return {
                "giveout_id": giveout_id,
                "giveout_status": giveout["giveout_status"],
                "warehouse_name": giveout["warehouse_name"],
                "warehouse_address": giveout["warehouse_address"],
                "articles": [],
            }
        if path == "/v1/returns/list":
            filters = payload["filter"]
            assert isinstance(filters, Mapping)
            warehouse_id = int(filters["warehouse_id"])
            page = self._page(self.returns_by_warehouse.get(warehouse_id, []), payload)
            last_id = payload.get("last_id")
            start = 0
            if last_id is not None:
                start = next(
                    index
                    for index, item in enumerate(self.returns_by_warehouse[warehouse_id])
                    if item["id"] > int(last_id)
                )
            return {
                "returns": page,
                "has_next": start + len(page) < len(self.returns_by_warehouse[warehouse_id]),
            }
        if path == "/v1/return/giveout/get-pdf":
            return self.pdf_response
        raise AssertionError(f"Unexpected Ozon endpoint: {path}")

    @staticmethod
    def _page(
        items: list[dict[str, object]], payload: Mapping[str, object]
    ) -> list[dict[str, object]]:
        last_id = payload.get("last_id")
        start = 0
        if last_id is not None:
            start = next(
                index
                for index, item in enumerate(items)
                if int(item.get("id", item.get("giveout_id", 0))) > int(last_id)
            )
        return items[start : start + int(payload["limit"])]


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        yield session
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


async def _create_scope(session: AsyncSession) -> ReturnScope:
    suffix = uuid.uuid4().hex[:12]
    tenant = Tenant(name="Ozon return test", slug=f"ozon-return-{suffix}")
    session.add(tenant)
    await session.flush()
    seller = Seller(tenant_id=tenant.id, name="Ozon seller")
    warehouse = Warehouse(tenant_id=tenant.id, name="Returns", code=f"returns-{suffix}")
    session.add_all([seller, warehouse])
    await session.flush()
    request = InboundIntakeRequest(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        status="draft",
        operation_type="return",
        marketplace="ozon",
    )
    account = MarketplaceAccount(
        tenant_id=tenant.id,
        seller_id=seller.id,
        marketplace="ozon",
        account_slot="primary",
        external_account_id=f"client-{suffix}",
        secret_encrypted=encrypt_secret("test-api-key"),
        is_active=True,
        validation_status="valid",
    )
    session.add_all([request, account])
    await session.commit()
    return ReturnScope(tenant.id, seller.id, request.id, warehouse.id)


async def _add_product_link(
    session: AsyncSession,
    scope: ReturnScope,
    *,
    external_offer_id: str | None = None,
    external_sku: str | None = None,
) -> Product:
    suffix = uuid.uuid4().hex[:10]
    product = Product(
        tenant_id=scope.tenant_id,
        seller_id=scope.seller_id,
        name=f"WMS product {suffix}",
        sku_code=f"wms-{suffix}",
        wb_barcode=f"wb-{suffix}",
    )
    session.add(product)
    await session.flush()
    session.add(
        ProductMarketplaceLink(
            tenant_id=scope.tenant_id,
            seller_id=scope.seller_id,
            product_id=product.id,
            marketplace="ozon",
            external_product_id=f"ozon-product-{suffix}",
            external_offer_id=external_offer_id,
            external_sku=external_sku,
        )
    )
    await session.commit()
    return product


def _giveout(giveout_id: int, warehouse_id: int) -> dict[str, object]:
    return {
        "giveout_id": giveout_id,
        "giveout_status": "GIVEOUT_STATUS_APPROVED",
        "warehouse_id": warehouse_id,
        "warehouse_name": f"Ozon PVZ {giveout_id}",
        "warehouse_address": f"Street {giveout_id}",
        "approved_articles_count": 1,
        "total_articles_count": 1,
        "created_at": "2026-08-25T10:00:00Z",
    }


def _return_item(
    return_id: int,
    *,
    offer_id: str,
    sku: int,
    quantity: int = 1,
) -> dict[str, object]:
    return {
        "id": return_id,
        "posting_number": f"posting-{return_id}",
        "return_reason_name": "Buyer changed mind",
        "type": "FullReturn",
        "schema": "FBS",
        "product": {
            "offer_id": offer_id,
            "sku": sku,
            "name": f"Ozon product {return_id}",
            "quantity": quantity,
        },
        "logistic": {"barcode": f"return-barcode-{return_id}"},
        "storage": {"days": 3, "utilization_forecast_date": "2026-09-01"},
    }


def _provider(transport: FakeOzonReturnsTransport) -> OzonMarketplaceProvider:
    return OzonMarketplaceProvider(transport=transport)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_preview_reports_manual_path_when_giveout_is_disabled(
    db_session: AsyncSession,
) -> None:
    scope = await _create_scope(db_session)

    preview = await build_preview(
        db_session,
        scope.tenant_id,
        scope.request_id,
        _provider(FakeOzonReturnsTransport(enabled=False)),
    )

    assert preview == {
        "enabled": False,
        "message": "Получение возвратов по штрихкоду недоступно. Ведите документ руками.",
        "groups": [],
        "imported_giveout_ids": [],
    }


@pytest.mark.asyncio
async def test_preview_imports_one_selected_giveout_after_full_pagination(
    db_session: AsyncSession,
) -> None:
    scope = await _create_scope(db_session)
    product_by_offer = await _add_product_link(
        db_session, scope, external_offer_id="offer-linked"
    )
    product_by_sku = await _add_product_link(db_session, scope, external_sku="2002")
    giveouts = [_giveout(index, 10_000 + index) for index in range(1, 102)]
    first_warehouse_returns = [
        _return_item(1, offer_id="offer-linked", sku=1001, quantity=2),
        _return_item(2, offer_id="other-offer", sku=2002, quantity=3),
        _return_item(3, offer_id="unmatched", sku=3003),
        *[
            _return_item(index, offer_id=f"unmatched-{index}", sku=10_000 + index)
            for index in range(4, 102)
        ],
    ]
    transport = FakeOzonReturnsTransport(
        giveouts=giveouts,
        returns_by_warehouse={
            10_001: first_warehouse_returns,
            **{
                10_000 + index: [_return_item(1_000 + index, offer_id=f"other-{index}", sku=index)]
                for index in range(2, 102)
            },
        },
    )
    provider = _provider(transport)

    preview = await build_preview(db_session, scope.tenant_id, scope.request_id, provider)

    assert preview["enabled"] is True
    groups = preview["groups"]
    assert isinstance(groups, list)
    assert len(groups) == 101
    first_group = groups[0]
    assert isinstance(first_group, dict)
    assert first_group["giveout_id"] == 1
    first_items = first_group["items"]
    assert isinstance(first_items, list)
    assert len(first_items) == 101
    assert first_items[0]["product_id"] == str(product_by_offer.id)
    assert first_items[1]["product_id"] == str(product_by_sku.id)
    assert first_items[2]["matched"] is False
    assert first_items[2]["warning"] == "Товар не сопоставлен с каталогом"

    first_import = await import_selected_giveouts(
        db_session, scope.tenant_id, scope.request_id, provider, [1]
    )
    repeated_import = await import_selected_giveouts(
        db_session, scope.tenant_id, scope.request_id, provider, [1]
    )
    saved_groups = await imported_groups(db_session, scope.tenant_id, scope.request_id)

    assert first_import == {
        "giveouts_imported": 1,
        "items_imported": 101,
        "unmatched_items": 99,
    }
    assert repeated_import == {
        "giveouts_imported": 0,
        "items_imported": 0,
        "unmatched_items": 0,
    }
    assert len(saved_groups) == 1
    assert saved_groups[0]["giveout_id"] == 1
    assert len(saved_groups[0]["items"]) == 101
    assert saved_groups[0]["items"][2]["matched"] is False
    assert saved_groups[0]["items"][2]["warning"] == "Товар не сопоставлен с каталогом"


@pytest.mark.asyncio
async def test_imported_giveouts_are_isolated_by_request_and_tenant(
    db_session: AsyncSession,
) -> None:
    first_scope = await _create_scope(db_session)
    second_request = InboundIntakeRequest(
        tenant_id=first_scope.tenant_id,
        seller_id=first_scope.seller_id,
        warehouse_id=first_scope.warehouse_id,
        status="draft",
        operation_type="return",
        marketplace="ozon",
    )
    db_session.add(second_request)
    await db_session.commit()
    other_scope = await _create_scope(db_session)
    transport = FakeOzonReturnsTransport(
        giveouts=[_giveout(77, 707)],
        returns_by_warehouse={707: [_return_item(700, offer_id="unmatched", sku=700)]},
    )
    provider = _provider(transport)

    await import_selected_giveouts(
        db_session, first_scope.tenant_id, first_scope.request_id, provider, [77]
    )

    assert await imported_groups(db_session, first_scope.tenant_id, second_request.id) == []
    assert await imported_groups(db_session, other_scope.tenant_id, other_scope.request_id) == []
    with pytest.raises(OzonReturnError, match="request_not_found"):
        await build_preview(db_session, other_scope.tenant_id, first_scope.request_id, provider)


@pytest.mark.asyncio
async def test_giveout_pass_pdf_decodes_base64_payload(db_session: AsyncSession) -> None:
    scope = await _create_scope(db_session)
    expected_pdf = b"%PDF-1.7\ncontract-return-pass\n"
    provider = _provider(
        FakeOzonReturnsTransport(
            pdf_response={
                "file_content": base64.b64encode(expected_pdf).decode("ascii"),
                "file_name": "ozon-return-pass.pdf",
                "content_type": "application/pdf",
            }
        )
    )

    content, name, content_type = await get_giveout_pass_pdf(
        db_session, scope.tenant_id, scope.request_id, provider
    )

    assert content == expected_pdf
    assert name == "ozon-return-pass.pdf"
    assert content_type == "application/pdf"


@pytest.mark.asyncio
async def test_provider_failure_does_not_create_import_records(db_session: AsyncSession) -> None:
    scope = await _create_scope(db_session)
    provider = _provider(
        FakeOzonReturnsTransport(
            errors={
                "/v1/return/giveout/is-enabled": MarketplaceProviderError(
                    "ozon", 403, {"code": 7}
                )
            }
        )
    )

    with pytest.raises(MarketplaceProviderError) as raised:
        await build_preview(db_session, scope.tenant_id, scope.request_id, provider)

    assert raised.value.status_code == 403
    assert (
        await db_session.scalar(
            select(func.count()).select_from(InboundOzonReturnGiveout).where(
                InboundOzonReturnGiveout.request_id == scope.request_id
            )
        )
    ) == 0
