"""WMS-663: contract for per-exemplar Ozon GTD/RNPT choices.

The product implementation intentionally does not exist when this file is
committed.  The tests freeze two public service operations and, separately,
exercise the already existing KIZ path so a later scan cannot erase customs
data returned by Ozon.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models.fbs_order import (
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
    FbsOrderMarking,
    FbsOrderProduct,
)
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.schemas.ozon_fbs_api import (
    OzonV3GetFbsPostingResponseV3,
    OzonV5FbsPostingProductExemplarStatusV5Response,
    OzonV6FbsPostingProductExemplarSetV6Request,
)
from app.services import ozon_fbs_process_service as process_svc
from app.services.marketplace_provider import (
    FakeMarketplaceTransport,
    MarketplaceProviderError,
    OzonMarketplaceProvider,
)

POSTING_NUMBER = "019663-0001-1"
SKU_ONE = 663001
SKU_TWO = 663002


class _SaveDocuments(Protocol):
    async def __call__(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        product_id: int,
        exemplar_id: int,
        gtd: str | None,
        is_gtd_absent: bool,
        rnpt: str | None,
        is_rnpt_absent: bool,
        expected_version: int | None,
        provider: OzonMarketplaceProvider,
        client_id: str,
        api_key: str,
    ) -> object: ...


class _ResumeDocuments(Protocol):
    async def __call__(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        provider: OzonMarketplaceProvider,
        client_id: str,
        api_key: str,
    ) -> object: ...


def _operation(name: str, protocol: type[_SaveDocuments] | type[_ResumeDocuments]) -> Any:
    operation = getattr(process_svc, name, None)
    assert callable(operation), (
        f"WMS-663 requires process_svc.{name}: the explicit GTD/RNPT operation "
        "is absent, so the operator choice cannot be saved or resumed"
    )
    return cast(protocol, operation)


def _result_value(result: object, name: str) -> object:
    if isinstance(result, Mapping):
        return result.get(name)
    return getattr(result, name, None)


async def _seed_order(
    db_session: AsyncSession,
) -> tuple[FbsOrder, FbsOrderProduct, FbsOrderProduct]:
    tenant = Tenant(name="WMS-663", slug=f"wms-663-{uuid.uuid4().hex[:8]}")
    seller = Seller(tenant=tenant, name="Ozon seller")
    warehouse = Warehouse(tenant=tenant, name="FBS", code=f"wms663-{uuid.uuid4().hex[:8]}")
    first_product = Product(
        tenant=tenant,
        seller=seller,
        name="Товар с ГТД",
        sku_code=f"wms663-a-{uuid.uuid4().hex[:8]}",
    )
    second_product = Product(
        tenant=tenant,
        seller=seller,
        name="Товар с РНПТ",
        sku_code=f"wms663-b-{uuid.uuid4().hex[:8]}",
    )
    now = datetime.now(UTC)
    order = FbsOrder(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        product=first_product,
        marketplace="ozon",
        external_order_id=POSTING_NUMBER,
        wb_order_id=-1,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
        price=10000,
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
    )
    db_session.add_all([tenant, seller, warehouse, first_product, second_product, order])
    await db_session.flush()
    first = FbsOrderProduct(
        order_id=order.id,
        product_id=first_product.id,
        ozon_sku=SKU_ONE,
        offer_id="OFFER-GTD",
        name=first_product.name,
        quantity=2,
        position_index=0,
        provider_data_json={"sku": SKU_ONE, "quantity": 2},
    )
    second = FbsOrderProduct(
        order_id=order.id,
        product_id=second_product.id,
        ozon_sku=SKU_TWO,
        offer_id="OFFER-RNPT",
        name=second_product.name,
        quantity=1,
        position_index=1,
        provider_data_json={"sku": SKU_TWO, "quantity": 1},
    )
    db_session.add_all([first, second])
    await db_session.commit()
    return order, first, second


def _remote_snapshot() -> dict[str, object]:
    return {
        "posting_number": POSTING_NUMBER,
        "multi_box_qty": 3,
        "products": [
            {
                "product_id": SKU_ONE,
                "is_gtd_needed": True,
                "exemplars": [
                    {
                        "exemplar_id": 81,
                        "gtd": "001/ABC-09",
                        "is_gtd_absent": False,
                        "rnpt": "",
                        "is_rnpt_absent": True,
                        "weight": 1.25,
                        "marks": [{"mark": "010460000000000121OLD", "mark_type": "mandatory_mark"}],
                    },
                    {
                        "exemplar_id": 82,
                        "gtd": "",
                        "is_gtd_absent": True,
                        "rnpt": "000-RNPT/82",
                        "is_rnpt_absent": False,
                        "weight": 1.5,
                        "marks": [{"mark": "123456789012345", "mark_type": "imei"}],
                    },
                ],
            },
            {
                "product_id": SKU_TWO,
                "is_rnpt_needed": True,
                "exemplars": [
                    {
                        "exemplar_id": 91,
                        "gtd": "",
                        "is_gtd_absent": True,
                        "rnpt": "000-RNPT/91",
                        "is_rnpt_absent": False,
                        "weight": 2.0,
                        "marks": [{"mark": "UIN-91", "mark_type": "jw_uin"}],
                    }
                ],
            },
        ],
    }


def _transport(*, status: object | None = None) -> FakeMarketplaceTransport:
    return FakeMarketplaceTransport(
        endpoint_responses={
            "/v6/fbs/posting/product/exemplar/create-or-get": _remote_snapshot(),
            "/v5/fbs/posting/product/exemplar/validate": {
                "products": [{"product_id": SKU_ONE, "valid": True, "exemplars": []}]
            },
            "/v6/fbs/posting/product/exemplar/set": {},
            "/v5/fbs/posting/product/exemplar/status": status
            if status is not None
            else {
                "posting_number": POSTING_NUMBER,
                "status": "validation_in_process",
                "products": [],
            },
        }
    )


class _AppliedThenLostTransport(FakeMarketplaceTransport):
    """Ozon applied `/set`, but the HTTP result never reached WMS."""

    async def call(
        self,
        *,
        client_id: str,
        api_key: str,
        path: str,
        payload: Mapping[str, object],
    ) -> object:
        if path == "/v6/fbs/posting/product/exemplar/set":
            self.endpoint_calls.append((path, dict(payload)))
            raise MarketplaceProviderError("ozon", None, code="transport_error")
        return await super().call(
            client_id=client_id,
            api_key=api_key,
            path=path,
            payload=payload,
        )


@pytest.mark.asyncio
async def test_wms663_gtd_absent_is_explicit_and_does_not_send_a_number(
    db_session: AsyncSession,
) -> None:
    """C1: merely opening or leaving a field blank never selects GTD absence."""
    order, _, _ = await _seed_order(db_session)
    transport = _transport()
    save = _operation("save_exemplar_documents", _SaveDocuments)

    await save(
        db_session,
        tenant_id=order.tenant_id,
        order_id=order.id,
        product_id=SKU_ONE,
        exemplar_id=81,
        gtd=None,
        is_gtd_absent=True,
        rnpt=None,
        is_rnpt_absent=False,
        expected_version=None,
        provider=OzonMarketplaceProvider(transport=transport),
        client_id="client",
        api_key="key",
    )

    payload = next(
        payload
        for path, payload in transport.endpoint_calls
        if path == "/v6/fbs/posting/product/exemplar/set"
    )
    target = next(
        exemplar
        for product in payload["products"]
        if product["product_id"] == SKU_ONE
        for exemplar in product["exemplars"]
        if exemplar["exemplar_id"] == 81
    )
    assert target["is_gtd_absent"] is True
    assert target.get("gtd") in {None, ""}


@pytest.mark.asyncio
async def test_wms663_explicit_choice_is_saved_exactly_and_resumes_after_restart(
    db_session: AsyncSession,
) -> None:
    """C1/C2/C6/C13: explicit values survive readback; blank is not absent."""
    order, _, _ = await _seed_order(db_session)
    transport = _transport()
    transport.endpoint_response_queues["/v5/fbs/posting/product/exemplar/status"] = [
        {
            "posting_number": POSTING_NUMBER,
            "status": "validation_in_process",
            "products": [],
        },
        {
            "posting_number": POSTING_NUMBER,
            "status": "ship_available",
            "products": [
                {
                    "product_id": SKU_ONE,
                    "exemplars": [
                        {
                            "exemplar_id": 81,
                            "gtd": "001/ABC-09",
                            "is_gtd_absent": False,
                            "rnpt": "",
                            "is_rnpt_absent": True,
                            "gtd_check_status": "",
                            "rnpt_check_status": "",
                            "gtd_error_codes": [],
                            "rnpt_error_codes": [],
                        }
                    ],
                }
            ],
        },
    ]
    save = _operation("save_exemplar_documents", _SaveDocuments)

    result = await save(
        db_session,
        tenant_id=order.tenant_id,
        order_id=order.id,
        product_id=SKU_ONE,
        exemplar_id=81,
        gtd="001/ABC-09",
        is_gtd_absent=False,
        rnpt=None,
        is_rnpt_absent=True,
        expected_version=None,
        provider=OzonMarketplaceProvider(transport=transport),
        client_id="client",
        api_key="key",
    )

    set_payloads = [
        payload
        for path, payload in transport.endpoint_calls
        if path == "/v6/fbs/posting/product/exemplar/set"
    ]
    assert len(set_payloads) == 1
    target = next(
        exemplar
        for product in set_payloads[0]["products"]
        if product["product_id"] == SKU_ONE
        for exemplar in product["exemplars"]
        if exemplar["exemplar_id"] == 81
    )
    assert target["gtd"] == "001/ABC-09"
    assert target.get("is_gtd_absent") is not True
    assert target.get("rnpt") in {None, ""}
    assert target["is_rnpt_absent"] is True
    assert _result_value(result, "state") == "checking"

    db_session.expire_all()
    resume = _operation("resume_exemplar_document_check", _ResumeDocuments)
    resumed = await resume(
        db_session,
        tenant_id=order.tenant_id,
        order_id=order.id,
        provider=OzonMarketplaceProvider(transport=transport),
        client_id="client",
        api_key="key",
    )
    assert _result_value(resumed, "state") == "accepted"
    assert sum(
        path == "/v6/fbs/posting/product/exemplar/set"
        for path, _ in transport.endpoint_calls
    ) == 1


@pytest.mark.asyncio
async def test_wms663_kiz_scan_preserves_remote_customs_fields_and_every_exemplar(
    db_session: AsyncSession,
) -> None:
    """C4/C5/C14: the existing KIZ operation must merge, never replace, the snapshot."""
    order, first, _ = await _seed_order(db_session)
    current = FbsOrderMarking(
        tenant_id=order.tenant_id,
        order_id=order.id,
        order_product_id=first.id,
        kind="sgtin",
        value="010460000000000121NEW",
        meta_details_json={"exemplar_id": 81},
    )
    db_session.add(current)
    await db_session.commit()
    transport = _transport(
        status={
            "posting_number": POSTING_NUMBER,
            "status": "ship_available",
            "products": _remote_snapshot()["products"],
        }
    )

    await process_svc.submit_marking(
        db_session,
        order=order,
        marking=current,
        provider=OzonMarketplaceProvider(transport=transport),
        client_id="client",
        api_key="key",
    )

    payload = next(
        payload
        for path, payload in transport.endpoint_calls
        if path == "/v6/fbs/posting/product/exemplar/set"
    )
    assert payload["multi_box_qty"] == 3
    assert [product["product_id"] for product in payload["products"]] == [SKU_ONE, SKU_TWO]
    exemplars = {
        (product["product_id"], exemplar["exemplar_id"]): exemplar
        for product in payload["products"]
        for exemplar in product["exemplars"]
    }
    assert exemplars[(SKU_ONE, 81)] == {
        "exemplar_id": 81,
        "gtd": "001/ABC-09",
        "is_gtd_absent": False,
        "rnpt": "",
        "is_rnpt_absent": True,
        "weight": 1.25,
        "marks": [{"mark": "010460000000000121NEW", "mark_type": "mandatory_mark"}],
    }
    assert exemplars[(SKU_ONE, 82)]["rnpt"] == "000-RNPT/82"
    assert exemplars[(SKU_ONE, 82)]["marks"] == [
        {"mark": "123456789012345", "mark_type": "imei"}
    ]
    assert exemplars[(SKU_TWO, 91)]["gtd"] == ""
    assert exemplars[(SKU_TWO, 91)]["is_gtd_absent"] is True
    assert exemplars[(SKU_TWO, 91)]["rnpt"] == "000-RNPT/91"
    assert exemplars[(SKU_TWO, 91)]["marks"] == [{"mark": "UIN-91", "mark_type": "jw_uin"}]
    paths = [path for path, _ in transport.endpoint_calls]
    assert not any("/ship" in path or "stock" in path or "label" in path for path in paths)
    assert order.reserve_status == RESERVE_STATUS_RESERVED
    assert order.status != "done"


@pytest.mark.asyncio
async def test_wms663_write_is_tenant_isolated_and_rejects_a_stale_version(
    db_session: AsyncSession,
) -> None:
    """C3/C10/C11/C15: one posting/version is the atomicity and isolation boundary."""
    order, _, _ = await _seed_order(db_session)
    save = _operation("save_exemplar_documents", _SaveDocuments)
    transport = _transport()

    first = await save(
        db_session,
        tenant_id=order.tenant_id,
        order_id=order.id,
        product_id=SKU_ONE,
        exemplar_id=81,
        gtd="GTD-v1",
        is_gtd_absent=False,
        rnpt=None,
        is_rnpt_absent=False,
        expected_version=None,
        provider=OzonMarketplaceProvider(transport=transport),
        client_id="client",
        api_key="key",
    )
    version = _result_value(first, "version")
    assert isinstance(version, int)
    first_payload = next(
        payload
        for path, payload in transport.endpoint_calls
        if path == "/v6/fbs/posting/product/exemplar/set"
    )
    neighbors = {
        (product["product_id"], exemplar["exemplar_id"]): exemplar
        for product in first_payload["products"]
        for exemplar in product["exemplars"]
        if (product["product_id"], exemplar["exemplar_id"]) != (SKU_ONE, 81)
    }
    assert neighbors[(SKU_ONE, 82)]["rnpt"] == "000-RNPT/82"
    assert neighbors[(SKU_TWO, 91)]["rnpt"] == "000-RNPT/91"

    with pytest.raises(process_svc.OzonFbsProcessError) as stale:
        await save(
            db_session,
            tenant_id=order.tenant_id,
            order_id=order.id,
            product_id=SKU_ONE,
            exemplar_id=81,
            gtd="GTD-stale",
            is_gtd_absent=False,
            rnpt=None,
            is_rnpt_absent=False,
            expected_version=version - 1,
            provider=OzonMarketplaceProvider(transport=transport),
            client_id="client",
            api_key="key",
        )
    assert stale.value.code == "ozon_exemplar_documents_conflict"

    foreign_tenant = uuid.uuid4()
    calls_before_foreign = len(transport.endpoint_calls)
    with pytest.raises(process_svc.OzonFbsProcessError) as foreign:
        await save(
            db_session,
            tenant_id=foreign_tenant,
            order_id=order.id,
            product_id=SKU_ONE,
            exemplar_id=81,
            gtd="FOREIGN",
            is_gtd_absent=False,
            rnpt=None,
            is_rnpt_absent=False,
            expected_version=None,
            provider=OzonMarketplaceProvider(transport=transport),
            client_id="client",
            api_key="key",
        )
    assert foreign.value.code in {"order_not_found", "access_denied"}
    assert len(transport.endpoint_calls) == calls_before_foreign


@pytest.mark.asyncio
async def test_wms663_lost_set_response_reads_status_before_any_repeat(
    db_session: AsyncSession,
) -> None:
    """C9/C11: an unknown write is reconciled by status, never blindly repeated."""
    order, _, _ = await _seed_order(db_session)
    save = _operation("save_exemplar_documents", _SaveDocuments)
    matching = _remote_snapshot()
    matching["products"] = [
        {
            "product_id": SKU_ONE,
            "exemplars": [
                {
                    "exemplar_id": 81,
                    "gtd": "001/ABC-09",
                    "is_gtd_absent": False,
                    "rnpt": "",
                    "is_rnpt_absent": False,
                    "gtd_check_status": "",
                    "gtd_error_codes": [],
                }
            ],
        }
    ]
    transport = _AppliedThenLostTransport(
        endpoint_responses={
            "/v6/fbs/posting/product/exemplar/create-or-get": _remote_snapshot(),
            "/v5/fbs/posting/product/exemplar/status": {
                **matching,
                "status": "ship_available",
            },
        }
    )

    result = await save(
        db_session,
        tenant_id=order.tenant_id,
        order_id=order.id,
        product_id=SKU_ONE,
        exemplar_id=81,
        gtd="001/ABC-09",
        is_gtd_absent=False,
        rnpt=None,
        is_rnpt_absent=False,
        expected_version=None,
        provider=OzonMarketplaceProvider(transport=transport),
        client_id="client",
        api_key="key",
    )

    paths = [path for path, _ in transport.endpoint_calls]
    assert paths.count("/v6/fbs/posting/product/exemplar/set") == 1
    assert paths.count("/v5/fbs/posting/product/exemplar/status") >= 1
    assert _result_value(result, "state") == "accepted"


@pytest.mark.asyncio
async def test_wms663_two_sessions_commit_one_posting_version_once(
    db_session: AsyncSession,
) -> None:
    """C10: two clients race on one version; exactly one mutation reaches Ozon."""
    if engine.dialect.name != "postgresql":
        pytest.skip("row-lock concurrency contract requires PostgreSQL")
    order, _, _ = await _seed_order(db_session)
    save = _operation("save_exemplar_documents", _SaveDocuments)
    first_transport = _transport()
    second_transport = _transport()

    async def write(value: str, transport: FakeMarketplaceTransport) -> object:
        async with SessionLocal() as session:
            return await save(
                session,
                tenant_id=order.tenant_id,
                order_id=order.id,
                product_id=SKU_ONE,
                exemplar_id=81,
                gtd=value,
                is_gtd_absent=False,
                rnpt=None,
                is_rnpt_absent=False,
                expected_version=0,
                provider=OzonMarketplaceProvider(transport=transport),
                client_id="client",
                api_key="key",
            )

    outcomes = await asyncio.gather(
        write("GTD-client-A", first_transport),
        write("GTD-client-B", second_transport),
        return_exceptions=True,
    )
    successful = [item for item in outcomes if not isinstance(item, BaseException)]
    conflicts = [
        item
        for item in outcomes
        if isinstance(item, process_svc.OzonFbsProcessError)
        and item.code == "ozon_exemplar_documents_conflict"
    ]
    assert len(successful) == 1
    assert len(conflicts) == 1
    sent = sum(
        path == "/v6/fbs/posting/product/exemplar/set"
        for transport in (first_transport, second_transport)
        for path, _ in transport.endpoint_calls
    )
    assert sent == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_payload", "expected_state"),
    [
        ({"status": "validation_in_process", "products": []}, "checking"),
        (
            {
                "status": "ship_available",
                "products": [
                    {
                        "product_id": SKU_ONE,
                        "exemplars": [
                            {
                                "exemplar_id": 81,
                                "gtd": "001/ABC-09",
                                "is_gtd_absent": False,
                                "gtd_check_status": "",
                                "gtd_error_codes": [],
                            }
                        ],
                    }
                ],
            },
            "accepted",
        ),
        ({"status": "ship_available", "products": []}, "unknown"),
        (
            {
                "status": "ship_available",
                "products": [
                    {
                        "product_id": SKU_ONE,
                        "exemplars": [
                            {
                                "exemplar_id": 81,
                                "gtd": "OLD",
                                "gtd_check_status": "mystery",
                                "gtd_error_codes": [],
                            }
                        ],
                    }
                ],
            },
            "unknown",
        ),
        (
            {
                "status": "ship_not_available",
                "products": [
                    {
                        "product_id": SKU_ONE,
                        "exemplars": [
                            {
                                "exemplar_id": 81,
                                "gtd": "001/ABC-09",
                                "gtd_error_codes": ["gtd_invalid"],
                            }
                        ],
                    }
                ],
            },
            "rejected",
        ),
        ({"status": "update_available", "products": []}, "editable"),
        ({"status": "update_not_available", "products": []}, "unknown"),
        ({"status": None, "products": None}, "unknown"),
        ({"status": "future_status", "products": []}, "unknown"),
    ],
)
async def test_wms663_status_accepts_only_matching_and_keeps_other_results_nonaccepted(
    db_session: AsyncSession,
    status_payload: dict[str, object],
    expected_state: str,
) -> None:
    """C7/C8/C9/C12: status and editability do not invent document acceptance."""
    order, _, _ = await _seed_order(db_session)
    save = _operation("save_exemplar_documents", _SaveDocuments)
    payload = {"posting_number": POSTING_NUMBER, **status_payload}
    result = await save(
        db_session,
        tenant_id=order.tenant_id,
        order_id=order.id,
        product_id=SKU_ONE,
        exemplar_id=81,
        gtd="001/ABC-09",
        is_gtd_absent=False,
        rnpt=None,
        is_rnpt_absent=False,
        expected_version=None,
        provider=OzonMarketplaceProvider(transport=_transport(status=payload)),
        client_id="client",
        api_key="key",
    )
    assert _result_value(result, "state") == expected_state


def test_wms663_saved_openapi_keeps_customs_fields_and_statuses_untyped() -> None:
    """C17: the local official schema is the boundary; mark enums are not copied."""
    set_schema = OzonV6FbsPostingProductExemplarSetV6Request.model_json_schema()
    exemplar_ref = set_schema["$defs"]["OzonFbsPostingProductExemplarSetV6RequestExemplars"]
    assert {"gtd", "rnpt", "is_gtd_absent", "is_rnpt_absent", "marks", "weight"} <= set(
        exemplar_ref["properties"]
    )
    status_schema = OzonV5FbsPostingProductExemplarStatusV5Response.model_json_schema()
    status_exemplar = status_schema["$defs"][
        "OzonV5FbsPostingProductExemplarStatusV5ResponseProductExemplar"
    ]
    for field in ("gtd_check_status", "rnpt_check_status"):
        assert "enum" not in status_exemplar["properties"][field]


def test_wms663_requirement_skus_accept_numbers_and_strings_without_cross_document_absence(
) -> None:
    """C15: WMS-638 normalization remains valid for both customs documents."""
    response = OzonV3GetFbsPostingResponseV3.model_validate(
        {
            "result": {
                "posting_number": POSTING_NUMBER,
                "status": "awaiting_packaging",
                "requirements": {
                    "products_requiring_gtd": [SKU_ONE, str(SKU_TWO)],
                    "products_requiring_rnpt": [SKU_TWO, str(SKU_ONE)],
                    "products_requiring_mandatory_mark": [SKU_ONE],
                    "products_requiring_imei": [SKU_TWO],
                    "products_requiring_jw_uin": [SKU_TWO],
                    "products_requiring_country": [SKU_ONE],
                },
            }
        }
    )
    requirements = response.result.requirements
    assert requirements.products_requiring_gtd == [str(SKU_ONE), str(SKU_TWO)]
    assert requirements.products_requiring_rnpt == [str(SKU_TWO), str(SKU_ONE)]
    assert requirements.products_requiring_mandatory_mark == [str(SKU_ONE)]
    assert requirements.products_requiring_imei == [str(SKU_TWO)]
    assert requirements.products_requiring_jw_uin == [str(SKU_TWO)]
    assert requirements.products_requiring_country == [str(SKU_ONE)]
