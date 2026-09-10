"""Read existing documents for chat; never execute warehouse operations."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.product import Product
from app.models.seller import Seller
from app.models.user import User
from app.services.chat_service import AttachedDocument, ChatError, resolve_seller
from app.services.seller_staff_permissions_service import get_seller_permissions
from app.services.staff_permissions_service import get_staff_permissions


async def read_document(
    session: AsyncSession,
    user: User,
    *,
    kind: str,
    document_id: uuid.UUID,
    seller_id: uuid.UUID,
    effective_seller_id: uuid.UUID | None,
) -> dict[str, Any]:
    model = DOCUMENT_MODELS.get(kind)
    if model is None:
        raise ChatError("bad_document_kind")
    if kind not in await readable_document_kinds(session, user) or (
        user.role == FULFILLMENT_SELLER and seller_id != effective_seller_id
    ):
        raise ChatError("forbidden")
    doc = (
        await session.execute(
            select(model).where(
                model.id == document_id,
                model.tenant_id == user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise ChatError("document_not_found")
    doc = cast(
        FbsOrder
        | FbsSupply
        | InboundIntakeRequest
        | MarketplaceUnloadRequest
        | OutboundShipmentRequest,
        doc,
    )
    # A NULL seller on a mixed document is resolved from actual product rows.
    # No caller-supplied title or another seller's lines are ever returned.
    line_models: dict[
        str, type[InboundIntakeLine] | type[MarketplaceUnloadLine] | type[OutboundShipmentLine]
    ] = {
        "inbound_intake": InboundIntakeLine,
        "marketplace_unload": MarketplaceUnloadLine,
        "outbound_shipment": OutboundShipmentLine,
    }
    lines: list[dict[str, Any]] = []
    if kind in line_models:
        line_model = line_models[kind]
        pairs = (
            await session.execute(
                select(line_model, Product)
                .join(
                    Product,
                    Product.id == line_model.product_id,
                )
                .where(
                    line_model.request_id == document_id,
                    Product.tenant_id == user.tenant_id,
                    Product.seller_id == seller_id,
                )
            )
        ).all()
        lines = [
            {
                "product": product.name,
                "quantity": getattr(line, "quantity", getattr(line, "expected_qty", 0)),
                "received": getattr(line, "received_qty", None),
            }
            for line, product in pairs
        ]
        if doc.seller_id != seller_id and (doc.seller_id is not None or not lines):
            raise ChatError("document_not_found")
    elif doc.seller_id != seller_id:
        raise ChatError("document_not_found")
    seller = await resolve_seller(session, user.tenant_id, seller_id)
    if seller is None:
        raise ChatError("document_not_found")
    title = document_title(doc)
    if isinstance(doc, FbsOrder):
        lines = [{"product": doc.wb_article or doc.wb_barcode or title, "quantity": 1}]
    if isinstance(doc, FbsSupply):
        orders = (
            await session.execute(
                select(FbsOrder)
                .where(
                    FbsOrder.tenant_id == user.tenant_id,
                    FbsOrder.seller_id == seller_id,
                    FbsOrder.supply_id == doc.id,
                )
                .order_by(FbsOrder.created_at)
            )
        ).scalars()
        lines = [
            {
                "product": (
                    f"{order.marketplace.upper()} №{order.external_order_id or order.wb_order_id}"
                ),
                "quantity": 1,
                "order_id": str(order.id),
            }
            for order in orders
        ]
    card = AttachedDocument(kind, document_id, title, seller_id, seller.name)
    return {
        "document": card.to_json(),
        "status": doc.status,
        "lines": lines,
        "warehouse_id": str(doc.warehouse_id) if doc.warehouse_id else None,
    }


Document = (
    FbsOrder | FbsSupply | InboundIntakeRequest | MarketplaceUnloadRequest | OutboundShipmentRequest
)
DocumentKey = tuple[str, uuid.UUID, uuid.UUID]
DOCUMENT_MODELS: dict[str, type[Document]] = {
    "fbs_order": FbsOrder,
    "fbs_supply": FbsSupply,
    "inbound_intake": InboundIntakeRequest,
    "marketplace_unload": MarketplaceUnloadRequest,
    "outbound_shipment": OutboundShipmentRequest,
}


def document_title(doc: Document) -> str:
    if isinstance(doc, FbsOrder):
        return f"{doc.marketplace.upper()} №{doc.external_order_id or doc.wb_order_id}"
    return str(
        getattr(doc, "display_number", None)
        or getattr(doc, "document_number", None)
        or getattr(doc, "name", None)
        or str(doc.id)[:8]
    )


async def readable_document_kinds(session: AsyncSession, user: User) -> set[str]:
    """Read current permissions once per request; never cache across polls."""
    if user.role == FULFILLMENT_ADMIN:
        return set(DOCUMENT_MODELS)
    if user.role == FULFILLMENT_SELLER:
        return (
            set(DOCUMENT_MODELS)
            if (await get_seller_permissions(session, user)).documents
            else set()
        )
    permissions = await get_staff_permissions(session, user)
    return {
        kind
        for kind in DOCUMENT_MODELS
        if permissions.has(
            "packaging"
            if kind.startswith("fbs_")
            else "reception"
            if kind == "inbound_intake"
            else "mp_shipments"
        )
    }


async def read_document_cards(
    session: AsyncSession,
    user: User,
    keys: Iterable[DocumentKey],
    *,
    effective_seller_id: uuid.UUID | None,
) -> dict[DocumentKey, dict[str, Any]]:
    """Batch current card ACL/headers, without fetching each document's contents.

    At most one document query and one mixed-seller membership query per kind.
    Missing/deleted/forbidden cards remain hidden; snapshots cannot restore access.
    """
    requested = set(keys)
    if not requested:
        return {}
    allowed = await readable_document_kinds(session, user)
    requested = {
        key
        for key in requested
        if key[0] in allowed and (user.role != FULFILLMENT_SELLER or key[2] == effective_seller_id)
    }
    if not requested:
        return {}
    sellers = {
        s.id: s
        for s in (
            await session.execute(
                select(Seller).where(
                    Seller.tenant_id == user.tenant_id,
                    Seller.id.in_({key[2] for key in requested}),
                )
            )
        ).scalars()
    }
    result: dict[DocumentKey, dict[str, Any]] = {}
    line_models: dict[
        str, type[InboundIntakeLine] | type[MarketplaceUnloadLine] | type[OutboundShipmentLine]
    ] = {
        "inbound_intake": InboundIntakeLine,
        "marketplace_unload": MarketplaceUnloadLine,
        "outbound_shipment": OutboundShipmentLine,
    }
    for kind in sorted({key[0] for key in requested}):
        model = DOCUMENT_MODELS[kind]
        kind_keys = {key for key in requested if key[0] == kind}
        rows = cast(
            list[Document],
            list(
                (
                    await session.execute(
                        select(model).where(
                            model.tenant_id == user.tenant_id,
                            model.id.in_({key[1] for key in kind_keys}),
                        )
                    )
                ).scalars()
            ),
        )
        docs = {doc.id: doc for doc in rows}
        mixed_ids = [doc.id for doc in docs.values() if doc.seller_id is None]
        memberships: set[tuple[uuid.UUID, uuid.UUID]] = set()
        if mixed_ids and kind in line_models:
            line_model = line_models[kind]
            memberships = {
                (rid, sid)
                for rid, sid in (
                    await session.execute(
                        select(line_model.request_id, Product.seller_id)
                        .join(
                            Product,
                            Product.id == line_model.product_id,
                        )
                        .where(
                            line_model.request_id.in_(mixed_ids),
                            Product.tenant_id == user.tenant_id,
                            Product.seller_id.in_(sellers),
                        )
                        .distinct()
                    )
                ).all()
            }
        for key in kind_keys:
            _, document_id, seller_id = key
            doc, seller = docs.get(document_id), sellers.get(seller_id)
            if doc is None or seller is None:
                continue
            if doc.seller_id != seller_id and not (
                doc.seller_id is None and (document_id, seller_id) in memberships
            ):
                continue
            result[key] = AttachedDocument(
                kind, document_id, document_title(doc), seller_id, seller.name
            ).to_json()
    return result


async def read_order_worklist(
    session: AsyncSession,
    user: User,
    document_id: uuid.UUID,
    seller_id: uuid.UUID,
    effective_seller_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Resolve an exact chat order in the existing FF worklist, without writes."""
    from datetime import UTC, datetime

    from app.services.fbs_worklist_service import STATUS_GROUP_MAP, build_worklist_items

    if user.role == FULFILLMENT_SELLER:
        raise ChatError("forbidden")
    await read_document(
        session,
        user,
        kind="fbs_order",
        document_id=document_id,
        seller_id=seller_id,
        effective_seller_id=effective_seller_id,
    )
    order = (
        await session.execute(
            select(FbsOrder).where(
                FbsOrder.id == document_id,
                FbsOrder.tenant_id == user.tenant_id,
                FbsOrder.seller_id == seller_id,
            )
        )
    ).scalar_one()
    now = datetime.now(UTC)
    group = next(
        (key for key, statuses in STATUS_GROUP_MAP.items() if order.status in statuses), "new"
    )
    if (
        group == "new"
        and (
            order.deadline_at.replace(tzinfo=UTC)
            if order.deadline_at.tzinfo is None
            else order.deadline_at.astimezone(UTC)
        )
        < now
    ):
        group = "expired"
    return {
        "order": (await build_worklist_items(session, user.tenant_id, [order], server_now=now))[0],
        "status_group": group,
        "server_now": now.isoformat(),
    }
