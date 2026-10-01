"""Read-only inventory of earlier video fixtures and a deterministic local reuse decision."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import (
    BillingInvoiceV2,
    BillingLedgerEntry,
    BillingProfile,
    BillingTariffVersionV2,
)
from app.models.fbs_assembly_task import FbsAssemblyTask, FbsAssemblyTaskSupply
from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.fbs_supply import FbsSupply
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_count import InventoryCount, InventoryCountLine
from app.models.inventory_movement import InventoryMovement
from app.models.marking_code import MarkingCode
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller_ozon_imported_card import SellerOzonImportedCard
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.storage_location import StorageLocation
from app.services.fbs_stock_availability_service import fbs_stock_breakdown_by_product


async def legacy_audit(
    session: AsyncSession, tenant_id: uuid.UUID, warehouse_id: uuid.UUID,
) -> dict[str, Any]:
    products = list((await session.scalars(select(Product).where(
        Product.tenant_id == tenant_id,
        (Product.sku_code.like("%VIDEO%") | Product.sku_code.like("FBS-TEST-%")
         | Product.sku_code.like("EMU-%")),
    ).order_by(Product.sku_code))).all())
    pids = [p.id for p in products]
    sids = {p.seller_id for p in products if p.seller_id is not None}
    aliases = list((await session.scalars(select(ProductBarcode).where(
        ProductBarcode.tenant_id == tenant_id, ProductBarcode.product_id.in_(pids),
    ))).all())
    balances = list((await session.scalars(select(InventoryBalance).join(
        StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id,
    ).where(InventoryBalance.tenant_id == tenant_id, InventoryBalance.product_id.in_(pids),
            StorageLocation.warehouse_id == warehouse_id))).all())
    stock_totals = await fbs_stock_breakdown_by_product(session, tenant_id, warehouse_id, pids)
    links = list((await session.scalars(select(ProductMarketplaceLink).where(
        ProductMarketplaceLink.tenant_id == tenant_id,
        ProductMarketplaceLink.product_id.in_(pids),
    ))).all())
    movements = list((await session.scalars(select(InventoryMovement).where(
        InventoryMovement.tenant_id == tenant_id, InventoryMovement.product_id.in_(pids),
        InventoryMovement.warehouse_id == warehouse_id,
    ))).all())
    orders = list((await session.scalars(select(FbsOrder).where(
        FbsOrder.tenant_id == tenant_id, FbsOrder.product_id.in_(pids),
        FbsOrder.warehouse_id == warehouse_id,
    ))).all())
    positions = list((await session.scalars(select(FbsOrderProduct).where(
        FbsOrderProduct.order_id.in_([o.id for o in orders]),
    ))).all())
    supplies = list((await session.scalars(select(FbsSupply).where(
        FbsSupply.tenant_id == tenant_id, FbsSupply.id.in_([o.supply_id for o in orders]),
    ))).all())
    count_pairs = (await session.execute(select(InventoryCount, InventoryCountLine).join(
        InventoryCountLine, InventoryCountLine.count_id == InventoryCount.id,
    ).where(InventoryCount.tenant_id == tenant_id,
            InventoryCount.warehouse_id == warehouse_id,
            InventoryCountLine.product_id.in_(pids)))).all()
    assembly_pairs = (await session.execute(select(FbsAssemblyTask, FbsAssemblyTaskSupply).join(
        FbsAssemblyTaskSupply, FbsAssemblyTaskSupply.task_id == FbsAssemblyTask.id,
    ).where(FbsAssemblyTask.tenant_id == tenant_id,
            FbsAssemblyTaskSupply.supply_id.in_([s.id for s in supplies])))).all()
    marking = list((await session.scalars(select(MarkingCode).where(
        MarkingCode.tenant_id == tenant_id, MarkingCode.product_id.in_(pids),
    ))).all())
    charges = list((await session.scalars(select(BillingLedgerEntry).where(
        BillingLedgerEntry.tenant_id == tenant_id, BillingLedgerEntry.seller_id.in_(sids),
    ))).all())
    invoices = list((await session.scalars(select(BillingInvoiceV2).where(
        BillingInvoiceV2.tenant_id == tenant_id, BillingInvoiceV2.seller_id.in_(sids),
    ))).all())
    profiles = list((await session.scalars(select(BillingProfile).where(
        BillingProfile.tenant_id == tenant_id, BillingProfile.seller_id.in_(sids),
    ))).all())
    rates = list((await session.scalars(select(BillingTariffVersionV2).where(
        BillingTariffVersionV2.tenant_id == tenant_id, BillingTariffVersionV2.seller_id.in_(sids),
    ))).all())
    wb_cards = list((await session.scalars(select(SellerWildberriesImportedCard).where(
        SellerWildberriesImportedCard.tenant_id == tenant_id,
        SellerWildberriesImportedCard.seller_id.in_(sids),
    ))).all())
    ozon_cards = list((await session.scalars(select(SellerOzonImportedCard).where(
        SellerOzonImportedCard.tenant_id == tenant_id, SellerOzonImportedCard.seller_id.in_(sids),
    ))).all())
    intake_ids = set((await session.scalars(select(InboundIntakeRequest.id).join(
        InboundIntakeLine, InboundIntakeLine.request_id == InboundIntakeRequest.id,
    ).where(InboundIntakeRequest.tenant_id == tenant_id,
            InboundIntakeRequest.status == "done",
            InboundIntakeRequest.warehouse_id == warehouse_id,
            InboundIntakeLine.product_id.in_(pids)))).all())
    report_products: list[dict[str, Any]] = []
    for p in products:
        barcodes = sorted({a.barcode for a in aliases if a.product_id == p.id})
        stock = sum(b.quantity for b in balances if b.product_id == p.id)
        reserved = stock_totals[p.id].reserved
        report_products.append({
            "id": str(p.id), "sku": p.sku_code, "seller_id": str(p.seller_id),
            "barcodes": barcodes, "primary_print_barcode": p.primary_print_barcode,
            "stock": stock, "reserved": reserved, "available": stock - reserved,
            "locations": [{"location_id": str(b.storage_location_id), "quantity": b.quantity,
                           "container_kind": b.container_kind,
                           "container_id": str(b.container_id) if b.container_id else None}
                          for b in balances if b.product_id == p.id],
            "marketplace_links": [{"marketplace": link.marketplace,
                                   "external_product_id": link.external_product_id,
                                   "external_sku": link.external_sku}
                                  for link in links if link.product_id == p.id],
            "document_movements": [{"id": str(m.id), "quantity_delta": m.quantity_delta,
                                    "inbound_line_id": str(m.inbound_intake_line_id)
                                    if m.inbound_intake_line_id else None,
                                    "count_line_id": str(m.inventory_count_line_id)
                                    if m.inventory_count_line_id else None}
                                   for m in movements if m.product_id == p.id],
        })
    count_report: dict[str, Any] = {}
    for count, line in count_pairs:
        row = count_report.setdefault(str(count.id), {"id": str(count.id),
                                                       "status": count.status, "lines": []})
        row["lines"].append({"product_id": str(line.product_id), "expected": line.expected_quantity,
                             "actual": line.actual_quantity})
    assembly_sellers: dict[uuid.UUID, set[uuid.UUID]] = {}
    for task, link in assembly_pairs:
        seller = next(s.seller_id for s in supplies if s.id == link.supply_id)
        assembly_sellers.setdefault(task.id, set()).add(seller)
    own_link_keys = {(link.seller_id, link.marketplace, link.external_product_id) for link in links}
    wb_unselected = [c.nm_id for c in wb_cards
                     if (c.seller_id, "wb", str(c.nm_id)) not in own_link_keys]
    ozon_unselected = [c.ozon_product_id for c in ozon_cards
                       if (c.seller_id, "ozon", c.ozon_product_id) not in own_link_keys]
    all_pids = {str(p.id) for p in products}
    checks = {
        "six_skus_two_barcodes_primary_stock": len(products) >= 6 and all(
            len(p["barcodes"]) >= 2 and p["primary_print_barcode"] in p["barcodes"]
            and p["available"] >= 20 for p in report_products),
        "two_sellers": len(sids) >= 2,
        "document_backed_stock": bool(intake_ids) and all(
            any(m["inbound_line_id"] for m in p["document_movements"])
            and sum(m["quantity_delta"] for m in p["document_movements"]) == p["stock"]
            for p in report_products),
        "stock_in_box": any(b.container_kind == "box" and b.quantity > 0 for b in balances),
        "wb_ozon_orders": sum(o.marketplace == "wb" for o in orders) >= 8
                          and sum(o.marketplace == "ozon" for o in orders) >= 4,
        "multi_unit_ozon": any(p.quantity > 1 and p.order_id in {
            o.id for o in orders if o.marketplace == "ozon"} for p in positions),
        "two_wb_routes": len({s.delivery_type for s in supplies
                              if s.marketplace == "wb" and s.delivery_type}) >= 2,
        "new_and_assembly": any(o.status == "new" for o in orders)
                            and any(o.status in {"in_supply", "assembling"} for o in orders),
        "common_assembly_two_sellers": any(len(sellers) >= 2
                                           for sellers in assembly_sellers.values()),
        "inventory_draft_all_skus": any(
            c["status"] == "draft" and {line["product_id"] for line in c["lines"]} >= all_pids
            and all(line["actual"] is None for line in c["lines"])
            for c in count_report.values()),
        "inventory_partial": any(c["status"] == "draft"
                                 and any(line["actual"] is not None for line in c["lines"])
                                 for c in count_report.values()),
        "marking_pool": sum(m.status == "available" for m in marking) >= 20,
        "billing_each_seller": bool(sids) and {p.seller_id for p in profiles} >= sids
                               and {r.seller_id for r in rates} >= sids
                               and any(i.status == "issued" for i in invoices)
                               and len(charges) >= 3,
        "catalog_selected_unselected_both": (
            bool(wb_cards and ozon_cards and wb_unselected and ozon_unselected)
            and {link.marketplace for link in links} >= {"wb", "ozon"}
        ),
    }
    gaps = [key for key, passed in checks.items() if not passed]
    return {
        "scope": "existing VIDEO / FBS-TEST / EMU products in the exact staging tenant",
        "products": report_products,
        "counts": {"products": len(products), "sellers": len(sids), "orders": len(orders),
                   "supplies": len(supplies), "inventory_documents": len(count_report),
                   "available_marking": sum(m.status == "available" for m in marking),
                   "charges": len(charges), "invoices": len(invoices)},
        "orders": [{"id": str(o.id), "status": o.status, "marketplace": o.marketplace,
                    "product_id": str(o.product_id), "seller_id": str(o.seller_id),
                    "supply_id": str(o.supply_id) if o.supply_id else None,
                    "wb_order_id": o.wb_order_id, "external_order_id": o.external_order_id,
                    "wb_supply_id": o.wb_supply_id, "deadline_at": o.deadline_at.isoformat()}
                   for o in orders],
        "supplies": [{"id": str(s.id), "seller_id": str(s.seller_id), "status": s.status,
                      "marketplace": s.marketplace, "wb_supply_id": s.wb_supply_id,
                      "external_supply_id": s.external_supply_id, "delivery_type": s.delivery_type}
                     for s in supplies],
        "intake_ids": sorted(str(i) for i in intake_ids),
        "inventory_documents": list(count_report.values()),
        "assembly_ids": sorted(str(i) for i in assembly_sellers),
        "billing": {"charge_ids": [str(c.id) for c in charges],
                    "invoice_ids": [str(i.id) for i in invoices],
                    "rate_ids": [str(r.id) for r in rates]},
        "catalog": {"wb_count": len(wb_cards), "ozon_count": len(ozon_cards),
                    "wb_unselected": wb_unselected, "ozon_unselected": ozon_unselected},
        "local_readiness_checks": checks,
        "decision": "reuse_local_scope" if not gaps else "additive_scope",
        "reason": "Existing local dataset covers all seed criteria" if not gaps else
                  "Existing dataset has explicit gaps; leave it unchanged and add WMS617 scope",
        "gaps": gaps,
        "provider_verification": "unverified: IDs are WMS references, not emulator readback",
    }
