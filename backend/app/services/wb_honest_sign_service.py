from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.seller_wildberries_imported_card import (
    SellerWildberriesImportedCard,
)


@dataclass(frozen=True)
class WbCategoryCatalog:
    parent_by_subject: dict[int, int]
    clothing_parent_ids: set[int]
    source: str


@dataclass(frozen=True)
class MarkingRequirementDecision:
    required: bool
    reason: str | None


class BackfillPlanChanged(RuntimeError):
    pass


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _response_rows(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("data")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


async def fetch_category_catalog(
    client: httpx.AsyncClient,
    *,
    api_token: str,
) -> WbCategoryCatalog:
    headers = {"Authorization": api_token}
    base_url = "https://content-api.wildberries.ru"
    parents_response = await client.get(
        f"{base_url}/content/v2/object/parent/all",
        headers=headers,
    )
    parents_response.raise_for_status()
    subject_rows: list[dict[str, Any]] = []
    page_limit = 1000
    offset = 0
    while True:
        subjects_response = await client.get(
            f"{base_url}/content/v2/object/all",
            headers=headers,
            params={"limit": page_limit, "offset": offset},
        )
        subjects_response.raise_for_status()
        page_rows = _response_rows(subjects_response.json())
        subject_rows.extend(page_rows)
        if len(page_rows) < page_limit:
            break
        offset += page_limit

    clothing_parent_ids = {
        parent_id
        for row in _response_rows(parents_response.json())
        if (parent_id := _integer(row.get("id"))) is not None
        and isinstance(row.get("name"), str)
        and str(row["name"]).strip().casefold() == "одежда"
    }
    parent_by_subject: dict[int, int] = {}
    for row in subject_rows:
        subject_id = _integer(row.get("subjectID", row.get("subjectId")))
        parent_id = _integer(row.get("parentID", row.get("parentId")))
        if subject_id is not None and parent_id is not None:
            parent_by_subject[subject_id] = parent_id
    return WbCategoryCatalog(
        parent_by_subject=parent_by_subject,
        clothing_parent_ids=clothing_parent_ids,
        source="GET /content/v2/object/all + /content/v2/object/parent/all",
    )


def derive_marking_requirement(
    card: dict[str, object],
    catalog: WbCategoryCatalog | None,
) -> MarkingRequirementDecision:
    if card.get("needKiz") is True:
        return MarkingRequirementDecision(True, "needKiz")
    subject_id = _integer(card.get("subjectID", card.get("subjectId")))
    if subject_id is not None and catalog is not None:
        parent_id = catalog.parent_by_subject.get(subject_id)
        if parent_id in catalog.clothing_parent_ids:
            return MarkingRequirementDecision(True, "clothing_parent")
    return MarkingRequirementDecision(False, None)


def _raw_nm_id(card: dict[str, Any]) -> int | None:
    return _integer(card.get("nmID", card.get("nmId")))


def _backfill_fingerprint(
    apply_rows: list[dict[str, object]],
    skipped_rows: list[dict[str, object]],
) -> str:
    # `before` is deliberately excluded: a successful apply must be safely
    # repeatable with the same evidence plan.
    evidence = {
        "apply": [
            {
                "product_id": row["product_id"],
                "nmID": row["nmID"],
                "subjectID": row["subjectID"],
                "reason": row["reason"],
            }
            for row in apply_rows
        ],
        "skipped": skipped_rows,
    }
    encoded = json.dumps(
        evidence,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def build_backfill_plan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    catalog: WbCategoryCatalog,
) -> dict[str, object]:
    rows = (
        await session.execute(
            select(Product, SellerWildberriesImportedCard)
            .outerjoin(
                SellerWildberriesImportedCard,
                and_(
                    SellerWildberriesImportedCard.tenant_id == Product.tenant_id,
                    SellerWildberriesImportedCard.seller_id == Product.seller_id,
                    SellerWildberriesImportedCard.nm_id == Product.wb_nm_id,
                ),
            )
            .where(
                Product.tenant_id == tenant_id,
                Product.seller_id == seller_id,
                Product.wb_nm_id.is_not(None),
            )
            .order_by(Product.wb_nm_id, Product.id)
        )
    ).all()

    apply_rows: list[dict[str, object]] = []
    skipped_rows: list[dict[str, object]] = []
    for product, imported_card in rows:
        nm_id = int(product.wb_nm_id) if product.wb_nm_id is not None else None
        raw = imported_card.raw_json if imported_card is not None else None
        missing: str | None = None
        subject_id: int | None = None
        if not isinstance(raw, dict):
            missing = "raw_card"
        elif _raw_nm_id(raw) is None:
            missing = "nmID"
        else:
            subject_id = _integer(raw.get("subjectID", raw.get("subjectId")))
            if subject_id is None:
                missing = "subjectID"
            elif not isinstance(raw.get("needKiz"), bool):
                missing = "needKiz"
            elif subject_id not in catalog.parent_by_subject:
                missing = "subject_catalog_link"
        if missing is not None:
            skipped_rows.append(
                {
                    "product_id": str(product.id),
                    "tenant_id": str(product.tenant_id),
                    "seller_id": str(product.seller_id),
                    "nmID": nm_id,
                    "missing": missing,
                }
            )
            continue
        assert isinstance(raw, dict) and subject_id is not None
        decision = derive_marking_requirement(raw, catalog)
        if not decision.required:
            continue
        apply_rows.append(
            {
                "product_id": str(product.id),
                "tenant_id": str(product.tenant_id),
                "seller_id": str(product.seller_id),
                "nmID": nm_id,
                "subjectID": subject_id,
                "reason": decision.reason,
                "before": bool(product.requires_honest_sign),
            }
        )

    return {
        "apply": apply_rows,
        "skipped": skipped_rows,
        "fingerprint": _backfill_fingerprint(apply_rows, skipped_rows),
        "catalog_source": catalog.source,
    }


async def _lock_backfill_evidence(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> dict[uuid.UUID, Product]:
    """Lock and refresh the product/card evidence used by a backfill apply."""
    products = list(
        (
            await session.scalars(
                select(Product)
                .where(
                    Product.tenant_id == tenant_id,
                    Product.seller_id == seller_id,
                    Product.wb_nm_id.is_not(None),
                )
                .order_by(Product.wb_nm_id, Product.id)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        ).all()
    )
    nm_ids = [int(product.wb_nm_id) for product in products if product.wb_nm_id is not None]
    if nm_ids:
        # Product rows are locked first in the same stable order used by the
        # plan. Existing WB evidence is then locked and refreshed before the
        # fingerprint is rebuilt. A concurrent evidence update either commits
        # before this read and changes the fingerprint, or waits until apply
        # has committed; it can never race between validation and the flag
        # write.
        list(
            (
                await session.scalars(
                    select(SellerWildberriesImportedCard)
                    .where(
                        SellerWildberriesImportedCard.tenant_id == tenant_id,
                        SellerWildberriesImportedCard.seller_id == seller_id,
                        SellerWildberriesImportedCard.nm_id.in_(nm_ids),
                    )
                    .order_by(
                        SellerWildberriesImportedCard.nm_id,
                        SellerWildberriesImportedCard.id,
                    )
                    .execution_options(populate_existing=True)
                    .with_for_update()
                )
            ).all()
        )
    return {product.id: product for product in products}


async def apply_backfill_plan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    catalog: WbCategoryCatalog,
    fingerprint: str,
    product_ids: list[str],
) -> dict[str, object]:
    locked_products = await _lock_backfill_evidence(session, tenant_id, seller_id)
    current = await build_backfill_plan(session, tenant_id, seller_id, catalog=catalog)
    current_apply = current.get("apply")
    if not isinstance(current_apply, list) or not all(
        isinstance(row, dict) and "product_id" in row for row in current_apply
    ):
        raise BackfillPlanChanged("backfill_plan_invalid")
    current_ids = [str(row["product_id"]) for row in current_apply]
    requested_ids = [str(value) for value in product_ids]
    if current["fingerprint"] != fingerprint or current_ids != requested_ids:
        raise BackfillPlanChanged("backfill_plan_changed")

    parsed_ids = [uuid.UUID(value) for value in current_ids]
    by_id = {
        product_id: locked_products[product_id]
        for product_id in parsed_ids
        if product_id in locked_products
    }
    if set(by_id) != set(parsed_ids):
        raise BackfillPlanChanged("backfill_product_scope_changed")
    changed: list[str] = []
    for product_id in parsed_ids:
        product = by_id[product_id]
        if not product.requires_honest_sign:
            product.requires_honest_sign = True
            changed.append(str(product.id))
    await session.commit()

    saved = set(
        (
            await session.scalars(
                select(Product.id).where(
                    Product.tenant_id == tenant_id,
                    Product.seller_id == seller_id,
                    Product.id.in_(parsed_ids),
                    Product.requires_honest_sign.is_(True),
                )
            )
        ).all()
    )
    if saved != set(parsed_ids):
        raise RuntimeError("backfill_verification_failed")
    return {"changed_product_ids": changed, "verified_product_ids": current_ids}
