"""Read existing documents for chat; never execute warehouse operations."""

from __future__ import annotations

import uuid
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
    models: dict[
        str,
        type[FbsOrder]
        | type[FbsSupply]
        | type[InboundIntakeRequest]
        | type[MarketplaceUnloadRequest]
        | type[OutboundShipmentRequest],
    ] = {
        "fbs_order": FbsOrder,
        "fbs_supply": FbsSupply,
        "inbound_intake": InboundIntakeRequest,
        "marketplace_unload": MarketplaceUnloadRequest,
        "outbound_shipment": OutboundShipmentRequest,
    }
    model = models.get(kind)
    if model is None:
        raise ChatError("bad_document_kind")
    if user.role == FULFILLMENT_SELLER:
        if (
            seller_id != effective_seller_id
            or not (await get_seller_permissions(session, user)).documents
        ):
            raise ChatError("forbidden")
    elif user.role != FULFILLMENT_ADMIN:
        permission = (
            "packaging"
            if kind.startswith("fbs_")
            else ("reception" if kind == "inbound_intake" else "mp_shipments")
        )
        if not (await get_staff_permissions(session, user)).has(permission):
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
    if isinstance(doc, FbsOrder):
        title = f"{doc.marketplace.upper()} №{doc.external_order_id or doc.wb_order_id}"
        lines = [{"product": doc.wb_article or doc.wb_barcode or title, "quantity": 1}]
    else:
        title = str(
            getattr(doc, "display_number", None)
            or getattr(doc, "document_number", None)
            or getattr(doc, "name", None)
            or str(doc.id)[:8]
        )
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
    return {"document": card.to_json(), "status": doc.status, "lines": lines}
