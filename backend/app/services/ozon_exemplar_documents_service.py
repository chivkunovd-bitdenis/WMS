"""Durable per-posting exemplar writes; no database lock spans an Ozon call."""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.schemas.ozon_fbs_api import (
    OzonPostingv3GetFbsPostingRequest,
    OzonV3GetFbsPostingResponseV3,
    OzonV5FbsPostingProductExemplarStatusV5Request,
    OzonV5FbsPostingProductExemplarStatusV5Response,
    OzonV6FbsPostingProductExemplarCreateOrGetV6Request,
    OzonV6FbsPostingProductExemplarCreateOrGetV6Response,
    OzonV6FbsPostingProductExemplarSetV6Request,
)
from app.services.marketplace_provider import MarketplaceProviderError, OzonMarketplaceProvider
from app.services.ozon_fbs_errors import OzonFbsProcessError

DOCUMENT_KEY = "ozon_exemplar_documents"
PENDING_STATES = {"preparing", "checking", "unknown"}
EXEMPLAR_FIELDS = {
    "exemplar_id",
    "gtd",
    "rnpt",
    "is_gtd_absent",
    "is_rnpt_absent",
    "marks",
    "weight",
}


def document_data(order: FbsOrder) -> dict[str, Any]:
    raw = (order.meta_details_json or {}).get(DOCUMENT_KEY)
    return copy.deepcopy(raw) if isinstance(raw, dict) else {}


async def document_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID, *, lock: bool = False
) -> FbsOrder:
    stmt = select(FbsOrder).where(FbsOrder.id == order_id, FbsOrder.tenant_id == tenant_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    order = await session.scalar(stmt)
    if order is None:
        raise OzonFbsProcessError("order_not_found", "Заказ не найден.", status_code=404)
    if order.marketplace != "ozon" or not order.external_order_id:
        raise OzonFbsProcessError("ozon_order_required", "Нужен заказ Ozon.", status_code=400)
    return order


def store_document_data(order: FbsOrder, data: dict[str, Any]) -> None:
    order.meta_details_json = {**(order.meta_details_json or {}), DOCUMENT_KEY: copy.deepcopy(data)}


async def claim_exemplar_write(
    session: AsyncSession,
    order: FbsOrder,
    expected_version: int | None,
    *,
    kind: str,
    choice: dict[str, Any],
) -> dict[str, Any]:
    order = await document_order(session, order.tenant_id, order.id, lock=True)
    data = document_data(order)
    version = int(data.get("version", 0))
    if expected_version is not None and expected_version != version:
        raise OzonFbsProcessError(
            "ozon_exemplar_documents_conflict",
            "Сведения изменились. Перечитайте заказ.",
            status_code=409,
        )
    acknowledged_marking = (
        kind == "marking"
        and data.get("kind") == "marking"
        and data.get("state") == "checking"
        and not data.get("in_flight")
        and data.get("set_acknowledged") is True
    )
    if data.get("state") in PENDING_STATES and not acknowledged_marking:
        raise OzonFbsProcessError(
            "ozon_exemplar_documents_conflict",
            "Предыдущий запрос ещё проверяется в Ozon.",
            status_code=409,
        )
    if data.get("status") == "update_not_available":
        raise OzonFbsProcessError(
            "ozon_exemplar_documents_conflict",
            "Ozon пока не разрешает изменять сведения.",
            status_code=409,
        )
    data.update(
        version=version + 1,
        state="preparing",
        kind=kind,
        choice=choice,
        errors=[],
        lease_until=(datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
        in_flight=True,
        set_acknowledged=False,
        last_status={},
        status=None,
        document_errors={},
    )
    if kind == "documents" and not choice.get("all_required_absent"):
        data["choices"] = {
            f"{choice['product_id']}:{choice['exemplar_id']}": {
                key: choice[key] for key in ("gtd", "rnpt", "is_gtd_absent", "is_rnpt_absent")
            }
        }
    store_document_data(order, data)
    await session.commit()
    return data


async def checkpoint(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID, data: dict[str, Any]
) -> bool:
    order = await document_order(session, tenant_id, order_id, lock=True)
    current = document_data(order)
    if current.get("version") != data.get("version"):
        await session.commit()
        return False
    store_document_data(order, data)
    await session.commit()
    return True


def snapshot_products(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    for product in snapshot.get("products", []) or []:
        exemplars = []
        for remote in product.get("exemplars", []) or []:
            exemplar = {
                key: copy.deepcopy(value)
                for key, value in remote.items()
                if key in EXEMPLAR_FIELDS and value is not None
            }
            if "marks" in exemplar:
                exemplar["marks"] = [
                    {
                        key: value
                        for key, value in mark.items()
                        if key in {"mark", "mark_type"} and value is not None
                    }
                    for mark in exemplar["marks"]
                ]
            exemplars.append(exemplar)
        products.append({"product_id": product["product_id"], "exemplars": exemplars})
    return products


async def validate_exemplar_snapshot(
    session: AsyncSession, order: FbsOrder, snapshot: dict[str, Any]
) -> None:
    """Never replace a posting with a partial response or invented exemplar IDs."""
    products = snapshot.get("products") or []
    by_sku = {product.get("product_id"): product for product in products}
    if len(by_sku) != len(products):
        raise OzonFbsProcessError("ozon_exemplar_missing", "Ozon вернул повторяющиеся товары.")
    positions = list(
        (
            await session.scalars(
                select(FbsOrderProduct).where(FbsOrderProduct.order_id == order.id)
            )
        ).all()
    )
    for position in positions:
        product = by_sku.get(position.ozon_sku)
        exemplars = product.get("exemplars") or [] if product else []
        ids = [exemplar.get("exemplar_id") for exemplar in exemplars]
        if (
            product is None
            or len(exemplars) != position.quantity
            or any(not isinstance(value, int) or value <= 0 for value in ids)
            or len(set(ids)) != len(ids)
        ):
            raise OzonFbsProcessError(
                "ozon_exemplar_missing",
                "Ozon не вернул полный состав экземпляров. Сведения не отправлены.",
                status_code=409,
            )


async def fetch_exemplar_snapshot(
    provider: OzonMarketplaceProvider, *, posting_number: str, client_id: str, api_key: str
) -> dict[str, Any]:
    from app.services.ozon_fbs_process_service import _call

    response = await _call(
        provider,
        client_id=client_id,
        api_key=api_key,
        path="/v6/fbs/posting/product/exemplar/create-or-get",
        request=OzonV6FbsPostingProductExemplarCreateOrGetV6Request(posting_number=posting_number),
        response_type=OzonV6FbsPostingProductExemplarCreateOrGetV6Response,
        read=False,
    )
    if response.posting_number and response.posting_number != posting_number:
        raise OzonFbsProcessError("ozon_exemplar_missing", "Ozon вернул другое отправление.")
    return response.model_dump(exclude_none=True)


def apply_saved_documents(products: list[dict[str, Any]], data: dict[str, Any]) -> None:
    # Only the current document intent may override a fresh cabinet snapshot.
    if data.get("kind") != "documents" or data.get("state") == "accepted":
        return
    choice = data.get("choice", {})
    target = f"{choice.get('product_id')}:{choice.get('exemplar_id')}"
    for product in products:
        for exemplar in product["exemplars"]:
            key = f"{product['product_id']}:{exemplar['exemplar_id']}"
            saved = (
                data.get("choices", {}).get(key)
                if key == target or choice.get("all_required_absent")
                else None
            )
            if isinstance(saved, dict):
                exemplar.update(saved)


def status_exemplars(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        f"{product['product_id']}:{exemplar['exemplar_id']}": exemplar
        for product in raw.get("products", []) or []
        for exemplar in product.get("exemplars", []) or []
    }


def exemplar_document_errors(exemplar: dict[str, Any]) -> list[str]:
    return [code for doc in ("gtd", "rnpt") for code in exemplar.get(f"{doc}_error_codes") or []]


def current_document_state(
    status: str | None, exemplars: list[dict[str, Any]], errors: list[str]
) -> str:
    """Describe current readback, independently of a completed writer's intent."""
    if status == "validation_in_process":
        return "checking"
    if errors:
        return "rejected" if status == "ship_not_available" else "unknown"
    if any(
        exemplar.get(f"{doc}_check_status")
        for exemplar in exemplars
        for doc in ("gtd", "rnpt")
    ):
        return "unknown"
    if status == "ship_available" and exemplars:
        return "accepted"
    if status in {"update_available", "update_not_available"}:
        return "editable"
    return "unknown"


def requirements_snapshot_complete(
    positions: list[FbsOrderProduct], products: list[dict[str, Any]]
) -> bool:
    by_sku = {product.get("product_id"): product for product in products}
    if not positions or len(by_sku) != len(products) or by_sku.keys() != {
        position.ozon_sku for position in positions
    }:
        return False
    for position in positions:
        exemplars = by_sku[position.ozon_sku].get("exemplars") or []
        ids = [exemplar.get("exemplar_id") for exemplar in exemplars]
        if len(exemplars) != position.quantity or not all(
            isinstance(value, int) and value > 0 for value in ids
        ) or len(set(ids)) != len(ids):
            return False
    return True


def absent_documents_selected(data: dict[str, Any]) -> bool:
    # The durable choice map survives a later marking claim, unlike its current
    # operation marker. A claim still preparing expresses an explicit new intent.
    if data.get("choice", {}).get("all_required_absent"):
        return True
    targets = []
    for product in data.get("snapshot", {}).get("products", []):
        required = [doc for doc in ("gtd", "rnpt") if product.get(f"is_{doc}_needed")]
        for exemplar in product.get("exemplars", []):
            key = f"{product['product_id']}:{exemplar['exemplar_id']}"
            saved = data.get("choices", {}).get(key)
            for doc in required:
                targets.append(isinstance(saved, dict) and saved.get(f"is_{doc}_absent") is True)
    return bool(targets) and all(targets)


async def document_view(session: AsyncSession, order: FbsOrder) -> dict[str, Any]:
    data = document_data(order)
    positions = list(
        (
            await session.scalars(
                select(FbsOrderProduct).where(FbsOrderProduct.order_id == order.id)
            )
        ).all()
    )
    by_sku = {position.ozon_sku: position for position in positions}
    products = copy.deepcopy(data.get("snapshot", {}).get("products", []))
    apply_saved_documents(products, data)
    errors = data.get("document_errors", {})
    completed = data.get("state") == "accepted"
    remote = status_exemplars(data.get("last_status", {}))
    document_error_codes = {code for codes in errors.values() for code in codes}
    read_errors = [error for error in data.get("errors", []) if error not in document_error_codes]
    view_errors = data.get("errors", [])
    state = data.get("state", "editable")
    if completed:
        errors = {
            key: codes for key, exemplar in remote.items()
            if (codes := exemplar_document_errors(exemplar))
        }
        view_errors = read_errors + [code for codes in errors.values() for code in codes]
        state = "unknown" if read_errors else current_document_state(
            data.get("status"), list(remote.values()), view_errors
        )
        # A retained snapshot is not fresh acceptance evidence for omitted exemplars.
        expected = status_exemplars({"products": products})
        if state == "accepted" and (not expected or not expected.keys() <= remote.keys()):
            state = "unknown"
    for product in products:
        position = by_sku.get(product["product_id"])
        product.update(
            name=position.name if position else str(product["product_id"]),
            sku=str(product["product_id"]),
        )
        for index, exemplar in enumerate(product.get("exemplars", []) or []):
            key = f"{product['product_id']}:{exemplar['exemplar_id']}"
            exemplar_state = state
            if completed and not read_errors:
                current = remote.get(key)
                exemplar_state = current_document_state(
                    data.get("status"), [current] if current else [], errors.get(key, [])
                )
            exemplar.update(
                ordinal=index + 1,
                gtd_required=bool(product.get("is_gtd_needed")),
                rnpt_required=bool(product.get("is_rnpt_needed")),
                state=exemplar_state,
                errors=errors.get(key, []),
            )
    return {
        "posting_number": order.external_order_id,
        "version": data.get("version", 0),
        "state": state,
        "status": data.get("status"),
        "absence_selected": absent_documents_selected(data),
        "requirements_complete": requirements_snapshot_complete(positions, products),
        "editable": data.get("state") not in PENDING_STATES
        and data.get("status") != "update_not_available",
        "products": products,
        "errors": view_errors,
    }


async def get_exemplar_documents(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    provider: OzonMarketplaceProvider,
    client_id: str,
    api_key: str,
) -> dict[str, Any]:
    order = await document_order(session, tenant_id, order_id)
    data = document_data(order)
    if data.get("state") in PENDING_STATES or data.get("snapshot"):
        return await resume_exemplar_document_check(
            session,
            tenant_id=tenant_id,
            order_id=order_id,
            provider=provider,
            client_id=client_id,
            api_key=api_key,
        )
    if not data.get("snapshot"):
        # A status read is safe on open. create-or-get is reserved for explicit Save.
        from app.services.ozon_fbs_process_service import _call

        response = await _call(
            provider,
            client_id=client_id,
            api_key=api_key,
            path="/v5/fbs/posting/product/exemplar/status",
            request=OzonV5FbsPostingProductExemplarStatusV5Request(
                posting_number=order.external_order_id or ""
            ),
            response_type=OzonV5FbsPostingProductExemplarStatusV5Response,
            read=True,
        )
        snapshot = response.model_dump(exclude_none=True)
        posting = await _call(
            provider,
            client_id=client_id,
            api_key=api_key,
            path="/v3/posting/fbs/get",
            request=OzonPostingv3GetFbsPostingRequest.model_validate(
                {"posting_number": order.external_order_id}
            ),
            response_type=OzonV3GetFbsPostingResponseV3,
            read=True,
        )
        requirements = posting.result.requirements if posting.result else None
        for product in snapshot.get("products", []) or []:
            product["is_gtd_needed"] = bool(
                requirements
                and str(product["product_id"]) in (requirements.products_requiring_gtd or [])
            )
            product["is_rnpt_needed"] = bool(
                requirements
                and str(product["product_id"]) in (requirements.products_requiring_rnpt or [])
            )
        order = await document_order(session, tenant_id, order_id, lock=True)
        data = document_data(order)
        if not data.get("snapshot"):
            data.update(
                snapshot=snapshot,
                state="checking" if response.status == "validation_in_process" else "editable",
                version=0,
                status=response.status,
            )
            store_document_data(order, data)
        await session.commit()
    return await document_view(session, order)


def classify_document_status(data: dict[str, Any], raw: dict[str, Any]) -> None:
    status = raw.get("status")
    completed = data.get("state") == "accepted"
    rejected = data.get("state") == "rejected" and data.get("choice", {}).get(
        "all_required_absent"
    ) is True
    rejection_errors = data.get("errors", [])
    data.update(
        status=status, state="accepted" if completed else "unknown",
        errors=[], document_errors={}, last_status=raw,
    )
    # Completed choices are history. Inspect all fresh documents for display,
    # while unresolved writes still require strict matching of their own targets.
    targets = data.get("choices", {}) if data.get("kind") == "documents" and not completed else {}
    remote = status_exemplars(raw)
    matches = bool(targets)
    known = True
    for key in remote if completed else targets:
        exemplar = remote.get(key)
        if exemplar is None:
            matches = False
            continue
        choice = targets.get(key, {})
        errors = exemplar_document_errors(exemplar)
        for doc in ("gtd", "rnpt"):
            # Blank never means absence. Its false flag must also match readback.
            if not completed and (
                (exemplar.get(doc) or "") != (choice.get(doc) or "") or bool(
                    exemplar.get(f"is_{doc}_absent")
                ) != bool(choice.get(f"is_{doc}_absent"))
            ):
                matches = False
            if exemplar.get(f"{doc}_check_status"):
                known = False
        if errors:
            data["document_errors"][key] = errors
            data["errors"].extend(errors)
    if not completed:
        if status == "validation_in_process":
            data["state"] = "checking"
        elif status == "ship_not_available" and data["errors"] and matches:
            data["state"] = "rejected"
        elif status == "update_available" and (data.get("set_acknowledged") or matches):
            data["state"] = "editable"
        elif status == "ship_available" and matches and known and not data["errors"]:
            data["state"] = "accepted"
        if not targets and data.get("kind") != "marking" and status in {
            "ship_available", "update_available", "update_not_available"
        }:
            data["state"] = "editable"
        # The legacy marking result is independent; documents always use strict matching.
        if data.get("kind") == "marking" and not targets:
            data["state"] = {
                "ship_available": "accepted",
                "ship_not_available": "rejected",
                "validation_in_process": "checking",
                "update_available": "editable",
            }.get(str(status), "unknown")
        if data.get("kind") == "marking" and not data.get("set_acknowledged"):
            choice = data.get("choice", {})
            exemplar = remote.get(f"{choice.get('product_id')}:{choice.get('exemplar_id')}", {})
            confirmed = any(
                mark.get("mark") == choice.get("mark")
                and mark.get("mark_type") == choice.get("mark_type")
                and mark.get("check_status") in {None, "", "passed"}
                and not mark.get("error_codes")
                for mark in exemplar.get("marks", []) or []
            )
            if not confirmed and status != "validation_in_process":
                data["state"] = "unknown"
        # A stale readback cannot erase an already proven refusal. Keep that
        # explicit retry reachable, while reads never make an unknown SET retryable.
        if rejected and data["state"] in {"unknown", "editable"}:
            data["state"] = "rejected"
        if rejected and data["state"] == "rejected" and not data["errors"]:
            data["errors"] = rejection_errors


async def resume_exemplar_document_check(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    provider: OzonMarketplaceProvider,
    client_id: str,
    api_key: str,
) -> dict[str, Any]:
    from app.services.ozon_fbs_process_service import _call

    order = await document_order(session, tenant_id, order_id)
    data = document_data(order)
    completed = data.get("state") == "accepted"
    rejected = data.get("state") == "rejected" and data.get("choice", {}).get(
        "all_required_absent"
    ) is True
    # Preparing has not checkpointed /set; a reader cannot release the writer's claim.
    if data.get("in_flight"):
        lease_until = datetime.fromisoformat(data["lease_until"])
        if datetime.now(UTC) < lease_until:
            return await document_view(session, order)
        if data.get("state") == "preparing":
            # /set was never checkpointed. Fence the interrupted preparer.
            data.update(state="editable", in_flight=False, version=int(data["version"]) + 1)
            if data.get("choice", {}).get("all_required_absent"):
                # No SET was checkpointed: release only this unsent batch intent.
                data.update(choice={}, choices={})
            order = await document_order(session, tenant_id, order_id, lock=True)
            current = document_data(order)
            if (
                current.get("version") == data["version"] - 1
                and current.get("state") == "preparing"
            ):
                store_document_data(order, data)
            await session.commit()
            return await document_view(session, order)
        data["in_flight"] = False
    if not data:
        return await get_exemplar_documents(
            session,
            tenant_id=tenant_id,
            order_id=order_id,
            provider=provider,
            client_id=client_id,
            api_key=api_key,
        )
    try:
        response = await _call(
            provider,
            client_id=client_id,
            api_key=api_key,
            path="/v5/fbs/posting/product/exemplar/status",
            request=OzonV5FbsPostingProductExemplarStatusV5Request(
                posting_number=order.external_order_id or ""
            ),
            response_type=OzonV5FbsPostingProductExemplarStatusV5Response,
            read=True,
        )
        raw = response.model_dump(exclude_none=True)
        if response.posting_number and response.posting_number != order.external_order_id:
            data.update(
                state="accepted" if completed else "rejected" if rejected else "unknown",
                errors=["ozon_posting_mismatch"],
            )
        else:
            classify_document_status(data, raw)
            # Refresh remote values while retaining requirement flags and fields
            # omitted by /status. Local input remains in the current choices.
            snapshot = copy.deepcopy(data.get("snapshot", {}))
            previous_products = {
                product["product_id"]: product
                for product in snapshot.get("products", []) or []
            }
            for product in raw.get("products", []) or []:
                previous = previous_products.get(product["product_id"])
                if previous is None:
                    continue
                previous_exemplars = {
                    exemplar["exemplar_id"]: exemplar
                    for exemplar in previous.get("exemplars", []) or []
                }
                for exemplar in product.get("exemplars", []) or []:
                    # STATUS refreshes known IDs; a foreign ID must not become
                    # a retained exemplar required by every subsequent read.
                    previous_exemplar = previous_exemplars.get(exemplar["exemplar_id"])
                    if previous_exemplar is not None:
                        previous_exemplar.update(exemplar)
                previous.update(
                    {key: value for key, value in product.items() if key != "exemplars"}
                )
                previous["exemplars"] = list(previous_exemplars.values())
            snapshot["products"] = list(previous_products.values())
            data["snapshot"] = snapshot
    except (MarketplaceProviderError, OzonFbsProcessError) as exc:
        # A failed read cannot undo a previously confirmed write. An unresolved
        # write still stays unknown and cannot be repeated blindly.
        data.update(
            state="accepted" if completed else "rejected" if rejected else "unknown",
            errors=[exc.code],
        )
    await checkpoint(session, tenant_id, order_id, data)
    order = await document_order(session, tenant_id, order_id)
    return await document_view(session, order)


async def send_exemplar_payload(
    session: AsyncSession,
    order: FbsOrder,
    data: dict[str, Any],
    payload: dict[str, Any],
    *,
    provider: OzonMarketplaceProvider,
    client_id: str,
    api_key: str,
) -> dict[str, Any]:
    request = OzonV6FbsPostingProductExemplarSetV6Request.model_validate(payload)
    data.update(
        state="checking",
        payload=request.model_dump(exclude_none=True),
        lease_until=(datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
    )
    if not await checkpoint(session, order.tenant_id, order.id, data):
        raise OzonFbsProcessError(
            "ozon_exemplar_documents_conflict", "Сведения изменились.", status_code=409
        )
    try:
        await provider.call(
            client_id=client_id,
            api_key=api_key,
            path="/v6/fbs/posting/product/exemplar/set",
            payload=data["payload"],
        )
        data["set_acknowledged"] = True
    except MarketplaceProviderError as exc:
        if exc.status_code in {400, 401, 403, 404, 409, 422, 429}:
            data.update(state="rejected", in_flight=False, errors=[exc.code])
            await checkpoint(session, order.tenant_id, order.id, data)
            return await document_view(session, order)
        data.update(state="unknown", errors=[exc.code])
        await checkpoint(session, order.tenant_id, order.id, data)
    data["in_flight"] = False
    await checkpoint(session, order.tenant_id, order.id, data)
    return await resume_exemplar_document_check(
        session,
        tenant_id=order.tenant_id,
        order_id=order.id,
        provider=provider,
        client_id=client_id,
        api_key=api_key,
    )


async def save_exemplar_documents(
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
) -> dict[str, Any]:
    order = await document_order(session, tenant_id, order_id)
    choice = {
        "gtd": "" if is_gtd_absent else (gtd or ""),
        "is_gtd_absent": is_gtd_absent,
        "rnpt": "" if is_rnpt_absent else (rnpt or ""),
        "is_rnpt_absent": is_rnpt_absent,
    }
    position = await session.scalar(
        select(FbsOrderProduct).where(
            FbsOrderProduct.order_id == order_id, FbsOrderProduct.ozon_sku == product_id
        )
    )
    if position is None:
        raise OzonFbsProcessError(
            "ozon_exemplar_missing", "Товар не найден в заказе.", status_code=400
        )
    previous = document_data(order)
    if previous.get("state") in {"checking", "unknown"}:
        await resume_exemplar_document_check(
            session,
            tenant_id=tenant_id,
            order_id=order_id,
            provider=provider,
            client_id=client_id,
            api_key=api_key,
        )
    data = await claim_exemplar_write(
        session,
        order,
        expected_version,
        kind="documents",
        choice={"product_id": product_id, "exemplar_id": exemplar_id, **choice},
    )
    try:
        snapshot = await fetch_exemplar_snapshot(
            provider,
            posting_number=order.external_order_id or "",
            client_id=client_id,
            api_key=api_key,
        )
        await validate_exemplar_snapshot(session, order, snapshot)
        products = snapshot_products(snapshot)
        target = next(
            (
                exemplar
                for product in products
                if product["product_id"] == product_id
                for exemplar in product["exemplars"]
                if exemplar["exemplar_id"] == exemplar_id
            ),
            None,
        )
        if target is None:
            raise OzonFbsProcessError(
                "ozon_exemplar_missing", "Экземпляр не найден в Ozon.", status_code=409
            )
        data.setdefault("choices", {})[f"{product_id}:{exemplar_id}"] = choice
        data["snapshot"] = snapshot
        apply_saved_documents(products, data)
        # Local marks may be newer than the remote snapshot; the same merger is used by scans.
        from app.services.ozon_fbs_process_service import merge_local_exemplar_marks

        await merge_local_exemplar_marks(session, order, products)
        payload = {"posting_number": order.external_order_id, "products": products}
        if snapshot.get("multi_box_qty") is not None:
            payload["multi_box_qty"] = snapshot["multi_box_qty"]
    except (MarketplaceProviderError, OzonFbsProcessError) as exc:
        data.update(state="editable", in_flight=False, errors=[exc.code])
        await checkpoint(session, tenant_id, order_id, data)
        raise
    return await send_exemplar_payload(
        session, order, data, payload, provider=provider, client_id=client_id, api_key=api_key
    )


async def save_absent_exemplar_documents(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    expected_version: int | None,
    provider: OzonMarketplaceProvider,
    client_id: str,
    api_key: str,
) -> dict[str, Any]:
    """One explicit posting choice; every required document shares the same SET."""
    order = await document_order(session, tenant_id, order_id)
    previous = document_data(order)
    if previous.get("state") in PENDING_STATES or (
        absent_documents_selected(previous) and previous.get("state") != "rejected"
    ):
        return await resume_exemplar_document_check(
            session,
            tenant_id=tenant_id,
            order_id=order_id,
            provider=provider,
            client_id=client_id,
            api_key=api_key,
        )
    data = await claim_exemplar_write(
        session,
        order,
        expected_version,
        kind="documents",
        choice={"all_required_absent": True},
    )
    try:
        snapshot = await fetch_exemplar_snapshot(
            provider,
            posting_number=order.external_order_id or "",
            client_id=client_id,
            api_key=api_key,
        )
        await validate_exemplar_snapshot(session, order, snapshot)
        products = snapshot_products(snapshot)
        requirements = {product["product_id"]: product for product in snapshot.get("products", [])}
        choices = {}
        for product in products:
            required = requirements[product["product_id"]]
            for exemplar in product["exemplars"]:
                changes = {
                    key: exemplar[key]
                    for key in ("gtd", "rnpt", "is_gtd_absent", "is_rnpt_absent")
                    if key in exemplar
                }
                has_required = False
                for doc in ("gtd", "rnpt"):
                    if required.get(f"is_{doc}_needed"):
                        changes.update({doc: "", f"is_{doc}_absent": True})
                        has_required = True
                if has_required:
                    choices[f"{product['product_id']}:{exemplar['exemplar_id']}"] = changes
        data.update(snapshot=snapshot, choices=choices)
        if not choices:
            data.update(state="editable", in_flight=False, choice={})
            await checkpoint(session, tenant_id, order_id, data)
            return await document_view(session, order)
        apply_saved_documents(products, data)
        from app.services.ozon_fbs_process_service import merge_local_exemplar_marks

        await merge_local_exemplar_marks(session, order, products)
        payload = {"posting_number": order.external_order_id, "products": products}
        if snapshot.get("multi_box_qty") is not None:
            payload["multi_box_qty"] = snapshot["multi_box_qty"]
    except (MarketplaceProviderError, OzonFbsProcessError) as exc:
        data.update(state="editable", in_flight=False, choice={}, errors=[exc.code])
        await checkpoint(session, tenant_id, order_id, data)
        raise
    return await send_exemplar_payload(
        session,
        order,
        data,
        payload,
        provider=provider,
        client_id=client_id,
        api_key=api_key,
    )
