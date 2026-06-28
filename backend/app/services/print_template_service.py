from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.print_template import (
    LAYOUT_BLOCK_CZ,
    LAYOUT_BLOCKS,
    SYSTEM_PRESET_NAME,
    USER_LAST_LAYOUT_NAME,
    PrintTemplate,
)
from app.services.catalog_service import get_product


class PrintTemplateServiceError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class LayoutUnit:
    block: str
    copies: int


@dataclass(frozen=True)
class PrintLayout:
    units: list[LayoutUnit]

    def to_dict(self) -> dict[str, Any]:
        return {
            "units": [{"block": u.block, "copies": u.copies} for u in self.units],
        }


@dataclass(frozen=True)
class PrintTemplateRow:
    id: uuid.UUID | None
    tenant_id: uuid.UUID
    seller_id: uuid.UUID | None
    product_id: uuid.UUID | None
    user_id: uuid.UUID | None
    name: str
    layout: PrintLayout
    is_default: bool
    is_system: bool


SYSTEM_PAIRS_LAYOUT = PrintLayout(units=[LayoutUnit(block=LAYOUT_BLOCK_CZ, copies=2)])


def system_pairs_template(tenant_id: uuid.UUID) -> PrintTemplateRow:
    return PrintTemplateRow(
        id=None,
        tenant_id=tenant_id,
        seller_id=None,
        product_id=None,
        user_id=None,
        name=SYSTEM_PRESET_NAME,
        layout=SYSTEM_PAIRS_LAYOUT,
        is_default=False,
        is_system=True,
    )


def parse_layout(raw: dict[str, Any] | str) -> PrintLayout:
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PrintTemplateServiceError("invalid_layout_json") from exc
    else:
        data = raw
    if not isinstance(data, dict):
        raise PrintTemplateServiceError("invalid_layout_json")
    units_raw = data.get("units")
    if not isinstance(units_raw, list) or not units_raw:
        raise PrintTemplateServiceError("invalid_layout_json")
    units: list[LayoutUnit] = []
    for item in units_raw:
        if not isinstance(item, dict):
            raise PrintTemplateServiceError("invalid_layout_json")
        block = item.get("block")
        copies = item.get("copies")
        if not isinstance(block, str) or block not in LAYOUT_BLOCKS:
            raise PrintTemplateServiceError("invalid_layout_block")
        if not isinstance(copies, int) or copies < 1 or copies > 10:
            raise PrintTemplateServiceError("invalid_layout_copies")
        units.append(LayoutUnit(block=block, copies=copies))
    return PrintLayout(units=units)


def layout_to_json(layout: PrintLayout | dict[str, Any]) -> str:
    payload = layout.to_dict() if isinstance(layout, PrintLayout) else layout
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _row_from_model(model: PrintTemplate) -> PrintTemplateRow:
    return PrintTemplateRow(
        id=model.id,
        tenant_id=model.tenant_id,
        seller_id=model.seller_id,
        product_id=model.product_id,
        user_id=model.user_id,
        name=model.name,
        layout=parse_layout(model.layout_json),
        is_default=model.is_default,
        is_system=False,
    )


async def _clear_default_flags(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    product_id: uuid.UUID | None = None,
    seller_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    exclude_id: uuid.UUID | None = None,
) -> None:
    conditions = [PrintTemplate.tenant_id == tenant_id, PrintTemplate.is_default.is_(True)]
    if user_id is not None:
        conditions.append(PrintTemplate.user_id == user_id)
        conditions.append(PrintTemplate.seller_id.is_(None))
        conditions.append(PrintTemplate.product_id.is_(None))
    elif product_id is not None:
        conditions.append(PrintTemplate.product_id == product_id)
        conditions.append(PrintTemplate.user_id.is_(None))
    elif seller_id is not None:
        conditions.append(
            and_(PrintTemplate.seller_id == seller_id, PrintTemplate.product_id.is_(None))
        )
        conditions.append(PrintTemplate.user_id.is_(None))
    stmt = update(PrintTemplate).where(*conditions).values(is_default=False)
    if exclude_id is not None:
        stmt = stmt.where(PrintTemplate.id != exclude_id)
    await session.execute(stmt)


async def _clear_user_product_default_flags(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    product_id: uuid.UUID,
    exclude_id: uuid.UUID | None = None,
) -> None:
    stmt = (
        update(PrintTemplate)
        .where(
            PrintTemplate.tenant_id == tenant_id,
            PrintTemplate.user_id == user_id,
            PrintTemplate.product_id == product_id,
            PrintTemplate.is_default.is_(True),
        )
        .values(is_default=False)
    )
    if exclude_id is not None:
        stmt = stmt.where(PrintTemplate.id != exclude_id)
    await session.execute(stmt)


async def _clear_user_seller_default_flags(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    seller_id: uuid.UUID,
    exclude_id: uuid.UUID | None = None,
) -> None:
    stmt = (
        update(PrintTemplate)
        .where(
            PrintTemplate.tenant_id == tenant_id,
            PrintTemplate.user_id == user_id,
            PrintTemplate.seller_id == seller_id,
            PrintTemplate.product_id.is_(None),
            PrintTemplate.is_default.is_(True),
        )
        .values(is_default=False)
    )
    if exclude_id is not None:
        stmt = stmt.where(PrintTemplate.id != exclude_id)
    await session.execute(stmt)


async def _validate_scope(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None,
    product_id: uuid.UUID | None,
) -> uuid.UUID | None:
    resolved_seller_id = seller_id
    if product_id is not None:
        product = await get_product(session, tenant_id, product_id)
        if product is None:
            raise PrintTemplateServiceError("product_not_found")
        if resolved_seller_id is not None and product.seller_id != resolved_seller_id:
            raise PrintTemplateServiceError("product_seller_mismatch")
        resolved_seller_id = product.seller_id
    return resolved_seller_id


async def list_print_templates(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None = None,
    seller_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
) -> list[PrintTemplateRow]:
    stmt = select(PrintTemplate).where(
        PrintTemplate.tenant_id == tenant_id,
        PrintTemplate.name != USER_LAST_LAYOUT_NAME,
    )
    if user_id is not None:
        stmt = stmt.where(
            or_(
                PrintTemplate.user_id == user_id,
                PrintTemplate.user_id.is_(None),
            )
        )
    if seller_id is not None:
        stmt = stmt.where(
            or_(
                PrintTemplate.seller_id == seller_id,
                PrintTemplate.seller_id.is_(None),
            )
        )
    if product_id is not None:
        stmt = stmt.where(
            or_(
                PrintTemplate.product_id == product_id,
                PrintTemplate.product_id.is_(None),
            )
        )
    stmt = stmt.order_by(PrintTemplate.created_at.desc())
    result = await session.execute(stmt)
    return [_row_from_model(row) for row in result.scalars().all()]


async def get_print_template(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    template_id: uuid.UUID,
) -> PrintTemplateRow:
    model = await session.get(PrintTemplate, template_id)
    if model is None or model.tenant_id != tenant_id:
        raise PrintTemplateServiceError("template_not_found")
    return _row_from_model(model)


async def create_print_template(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    name: str,
    layout: PrintLayout | dict[str, Any],
    seller_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    is_default: bool = False,
) -> PrintTemplateRow:
    clean_name = name.strip()
    if not clean_name:
        raise PrintTemplateServiceError("name_required")
    parsed_layout = parse_layout(layout) if not isinstance(layout, PrintLayout) else layout
    resolved_seller_id = await _validate_scope(
        session,
        tenant_id,
        seller_id=seller_id,
        product_id=product_id,
    )
    if is_default:
        if user_id is not None and product_id is None and resolved_seller_id is None:
            await _clear_default_flags(session, tenant_id, user_id=user_id)
        elif product_id is not None and user_id is not None:
            await _clear_user_product_default_flags(
                session, tenant_id, user_id=user_id, product_id=product_id
            )
        elif product_id is not None:
            await _clear_default_flags(session, tenant_id, product_id=product_id)
        elif resolved_seller_id is not None and user_id is not None:
            await _clear_user_seller_default_flags(
                session, tenant_id, user_id=user_id, seller_id=resolved_seller_id
            )
        elif resolved_seller_id is not None:
            await _clear_default_flags(session, tenant_id, seller_id=resolved_seller_id)
    model = PrintTemplate(
        tenant_id=tenant_id,
        seller_id=resolved_seller_id,
        product_id=product_id,
        user_id=user_id,
        name=clean_name,
        layout_json=layout_to_json(parsed_layout),
        is_default=is_default,
    )
    session.add(model)
    await session.flush()
    await session.commit()
    return _row_from_model(model)


async def update_print_template(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    template_id: uuid.UUID,
    *,
    name: str | None = None,
    layout: PrintLayout | dict[str, Any] | None = None,
    is_default: bool | None = None,
) -> PrintTemplateRow:
    model = await session.get(PrintTemplate, template_id)
    if model is None or model.tenant_id != tenant_id:
        raise PrintTemplateServiceError("template_not_found")
    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise PrintTemplateServiceError("name_required")
        model.name = clean_name
    if layout is not None:
        parsed_layout = parse_layout(layout) if not isinstance(layout, PrintLayout) else layout
        model.layout_json = layout_to_json(parsed_layout)
    if is_default is not None:
        if is_default:
            if model.user_id is not None and model.product_id is None and model.seller_id is None:
                await _clear_default_flags(
                    session,
                    tenant_id,
                    user_id=model.user_id,
                    exclude_id=model.id,
                )
            elif model.product_id is not None and model.user_id is not None:
                await _clear_user_product_default_flags(
                    session,
                    tenant_id,
                    user_id=model.user_id,
                    product_id=model.product_id,
                    exclude_id=model.id,
                )
            elif model.product_id is not None:
                await _clear_default_flags(
                    session,
                    tenant_id,
                    product_id=model.product_id,
                    exclude_id=model.id,
                )
            elif model.seller_id is not None and model.user_id is not None:
                await _clear_user_seller_default_flags(
                    session,
                    tenant_id,
                    user_id=model.user_id,
                    seller_id=model.seller_id,
                    exclude_id=model.id,
                )
            elif model.seller_id is not None:
                await _clear_default_flags(
                    session,
                    tenant_id,
                    seller_id=model.seller_id,
                    exclude_id=model.id,
                )
        model.is_default = is_default
    await session.flush()
    await session.commit()
    return _row_from_model(model)


async def delete_print_template(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    template_id: uuid.UUID,
) -> None:
    model = await session.get(PrintTemplate, template_id)
    if model is None or model.tenant_id != tenant_id:
        raise PrintTemplateServiceError("template_not_found")
    await session.delete(model)
    await session.commit()


async def _find_user_last_layout(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> PrintTemplate | None:
    stmt = (
        select(PrintTemplate)
        .where(
            PrintTemplate.tenant_id == tenant_id,
            PrintTemplate.user_id == user_id,
            PrintTemplate.seller_id.is_(None),
            PrintTemplate.product_id.is_(None),
            PrintTemplate.name == USER_LAST_LAYOUT_NAME,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def save_user_last_print_layout(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    layout: PrintLayout | dict[str, Any],
) -> PrintTemplateRow:
    parsed_layout = parse_layout(layout) if not isinstance(layout, PrintLayout) else layout
    existing = await _find_user_last_layout(session, tenant_id, user_id)
    if existing is not None:
        existing.layout_json = layout_to_json(parsed_layout)
        existing.is_default = True
        await session.flush()
        await session.commit()
        return _row_from_model(existing)

    await _clear_default_flags(session, tenant_id, user_id=user_id)
    model = PrintTemplate(
        tenant_id=tenant_id,
        seller_id=None,
        product_id=None,
        user_id=user_id,
        name=USER_LAST_LAYOUT_NAME,
        layout_json=layout_to_json(parsed_layout),
        is_default=True,
    )
    session.add(model)
    await session.flush()
    await session.commit()
    return _row_from_model(model)


async def resolve_default_print_template(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    seller_id: uuid.UUID | None = None,
) -> PrintTemplateRow:
    if user_id is not None:
        user_last = await _find_user_last_layout(session, tenant_id, user_id)
        if user_last is not None:
            return _row_from_model(user_last)

    if product_id is not None:
        product = await get_product(session, tenant_id, product_id)
        if product is None:
            raise PrintTemplateServiceError("product_not_found")
        if seller_id is not None and product.seller_id != seller_id:
            raise PrintTemplateServiceError("product_seller_mismatch")
        seller_id = product.seller_id
        if user_id is not None:
            stmt = (
                select(PrintTemplate)
                .where(
                    PrintTemplate.tenant_id == tenant_id,
                    PrintTemplate.product_id == product_id,
                    PrintTemplate.user_id == user_id,
                    PrintTemplate.is_default.is_(True),
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            user_product_default = result.scalar_one_or_none()
            if user_product_default is not None:
                return _row_from_model(user_product_default)
        stmt = (
            select(PrintTemplate)
            .where(
                PrintTemplate.tenant_id == tenant_id,
                PrintTemplate.product_id == product_id,
                PrintTemplate.user_id.is_(None),
                PrintTemplate.is_default.is_(True),
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        product_default = result.scalar_one_or_none()
        if product_default is not None:
            return _row_from_model(product_default)

    if seller_id is not None:
        if user_id is not None:
            stmt = (
                select(PrintTemplate)
                .where(
                    PrintTemplate.tenant_id == tenant_id,
                    PrintTemplate.seller_id == seller_id,
                    PrintTemplate.product_id.is_(None),
                    PrintTemplate.user_id == user_id,
                    PrintTemplate.is_default.is_(True),
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            user_seller_default = result.scalar_one_or_none()
            if user_seller_default is not None:
                return _row_from_model(user_seller_default)
        stmt = (
            select(PrintTemplate)
            .where(
                PrintTemplate.tenant_id == tenant_id,
                PrintTemplate.seller_id == seller_id,
                PrintTemplate.product_id.is_(None),
                PrintTemplate.user_id.is_(None),
                PrintTemplate.is_default.is_(True),
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        seller_default = result.scalar_one_or_none()
        if seller_default is not None:
            return _row_from_model(seller_default)

    return system_pairs_template(tenant_id)
