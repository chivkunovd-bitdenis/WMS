"""Additional real process fixtures; imported by the guarded disposable seed only."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.fbs_assembly_task import FbsAssemblyTask, FbsAssemblyTaskSupply
from app.models.fbs_order import (
    FbsOrder,
    FbsOrderProduct,
    FbsOrderProductReservation,
    FbsOrderReservation,
)
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.inventory_count import InventoryCount, InventoryCountCreatedContainer
from app.models.pallet import Pallet
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.services.inventory_service import record_movement_and_adjust_balance
from app.services.sorting_location_service import get_or_create_sorting_location

EXTENDED = [
    "nested-container",
    "unlocated-container",
    "foreign-reserve",
    "foreign-location",
    "modal-scanner",
    "scanner-button",
    "paste-blur",
    "outside-no-suffix",
    "special-barcode",
    "server-5xx",
    "group-manual",
    "group-conflict",
    "group-partial-set",
    "group-lost-set",
    "print-fallback",
    "print-context-failure",
    "print-group-warehouses",
    "print-ozon-route",
    "exhausted-source-return",
    "ozon-handover",
    "ozon-group-scan",
    "full-plan-overflow",
    "manual-invalid",
    "tree-order-photo",
    "load-detail-error",
    "load-options-error",
    "catalog-error",
    "group-stage-persistence",
    "local-slow-input",
    "photo-failure",
    "print-picked",
    "next-and-history",
    "scanner-status-audio",
    "loading-busy",
    "date-controls",
    "operator-denied",
    "source-undo-history",
    "special-ru-layout",
    "multi-source-undo",
    "wb-source-banner",
]
GROUPS = {
    "group-manual",
    "group-conflict",
    "group-partial-set",
    "group-lost-set",
    "print-group-warehouses",
    "ozon-group-scan",
    "group-stage-persistence",
}
OZON = {"print-ozon-route", "ozon-handover", "ozon-group-scan"}


async def add_extended(session, tenant, seller, warehouse, warehouse2, actor_id):
    """Use normal inbound balances, explicit planned orders and real per-unit reserves."""
    result = {}
    sorting = await get_or_create_sorting_location(session, tenant, warehouse)
    for index, name in enumerate(EXTENDED, start=100):
        f = {
            "name": name,
            "products": [],
            "sources": [],
            "supplies": [],
            "orders": [],
            "positions": [],
            "marketplace": "ozon" if name in OZON else "wb",
        }
        product_count = 3 if name in {"tree-order-photo", "photo-failure"} else (2 if name == "ozon-group-scan" else 1)
        for pi in range(product_count):
            barcode = str(4900000000000 + index * 100 + pi)
            alt = str(5900000000000 + index * 100 + pi)
            sku = f"EXT-{index}-{pi}"
            title = (
                (
                    "Очень длинное название товара для проверки читаемости "
                    "колонок и сохранения контекста " * 3
                )[:240]
                if name == "tree-order-photo" and pi == 0
                else f"Extended {name} product {pi}"
            )
            p = Product(
                id=uuid.uuid4(),
                tenant_id=tenant,
                seller_id=seller,
                name=title,
                sku_code=sku,
                wb_barcode=None if name in OZON else barcode,
                wb_vendor_code=None if name in OZON else f"ART-EXT-{index}-{pi}",
            )
            session.add(p)
            await session.flush()
            session.add(
                ProductBarcode(
                    tenant_id=tenant, seller_id=seller, product_id=p.id, barcode=alt, source="wb"
                )
            )
            f["products"].append(
                {
                    "id": str(p.id),
                    "sku": sku,
                    "name": title,
                    "barcode": barcode,
                    "alt": alt,
                    "offer": f"OZ-EXT-{index}-{pi}",
                }
            )
            if name in OZON:
                session.add(
                    ProductMarketplaceLink(
                        tenant_id=tenant,
                        seller_id=seller,
                        product_id=p.id,
                        marketplace="ozon",
                        external_sku=str(880000 + index * 10 + pi),
                        external_offer_id=f"OZ-EXT-{index}-{pi}",
                        external_barcodes=[barcode],
                        is_active=True,
                    )
                )
            if name == "local-slow-input":
                short = f"X{index}"
                f["products"][-1]["short"] = short
                session.add(
                    ProductBarcode(
                        tenant_id=tenant,
                        seller_id=seller,
                        product_id=p.id,
                        barcode=short,
                        source="wb",
                    )
                )
            if name in {"special-barcode", "special-ru-layout"}:
                special = f"SKU/EXT?{index}&A"
                session.add(
                    ProductBarcode(
                        tenant_id=tenant,
                        seller_id=seller,
                        product_id=p.id,
                        barcode=special,
                        source="wb",
                    )
                )
                f["products"][-1]["special"] = special
                f["products"][-1]["gs"] = f"UNKNOWN-GS-{index}\x1d12345"
            if name in {"tree-order-photo", "photo-failure"}:
                nm = 9990000 + index * 10 + pi
                p.wb_nm_id = nm
                image = (
                    "http://127.0.0.1:25174/fixture-photo.svg"
                    if pi == 0
                    else "http://127.0.0.1:25174/missing-test-photo.png"
                    if pi == 1
                    else None
                )
                # Catalog enrichment accepts photo URLs from real imported card records.
                session.add(
                    SellerWildberriesImportedCard(
                        tenant_id=tenant,
                        seller_id=seller,
                        nm_id=nm,
                        raw_json={
                            "nmID": nm,
                            "vendorCode": p.wb_vendor_code,
                            "photos": [{"big": image}] if image else [],
                            "sizes": [{"techSize": "XL", "skus": [barcode]}],
                        },
                    )
                )
        locations = []
        for li in range(
            3
            if name == "tree-order-photo"
            else 2
            if name in {"print-group-warehouses", "multi-source-undo"}
            else 1
        ):
            if name == "unlocated-container":
                loc = sorting
            else:
                loc = StorageLocation(
                    id=uuid.uuid4(),
                    tenant_id=tenant,
                    warehouse_id=warehouse2
                    if name == "print-group-warehouses" and li == 1
                    else warehouse,
                    code=f"EXT-{index}-A-{[2, 10, 1][li]}",
                    barcode=f"EXT-LOC-{index}-{li}",
                )
                session.add(loc)
            locations.append(loc)
        await session.flush()
        sources = [(loc, None, None) for loc in locations]
        if name == "nested-container":
            pallet = Pallet(
                id=uuid.uuid4(),
                tenant_id=tenant,
                warehouse_id=warehouse,
                storage_location_id=locations[0].id,
                code=f"PAL-{index}",
                barcode=f"PAL-{index}",
            )
            session.add(pallet)
            await session.flush()
            box = WarehouseBox(
                id=uuid.uuid4(),
                tenant_id=tenant,
                warehouse_id=warehouse,
                storage_location_id=locations[0].id,
                pallet_id=pallet.id,
                internal_barcode=f"NEST-BOX-{index}",
            )
            session.add(box)
            await session.flush()
            sources = [(locations[0], "pallet", pallet), (locations[0], "box", box)]
        elif name == "unlocated-container":
            box = WarehouseBox(
                id=uuid.uuid4(),
                tenant_id=tenant,
                warehouse_id=warehouse,
                storage_location_id=None,
                container_kind="cargo_place",
                internal_barcode=f"CARGO-{index}",
            )
            session.add(box)
            await session.flush()
            sources = [(sorting, "cargo_place", box)]
        for loc, kind, container in sources:
            sf = {
                "location_id": str(loc.id),
                "code": loc.code,
                "barcode": loc.barcode,
                "container_kind": kind,
                "container_id": str(container.id) if container else None,
                "scan": (container.barcode if kind == "pallet" else container.internal_barcode)
                if container
                else loc.barcode,
                "initial": {},
                "sortingAlready": loc.id == sorting.id,
            }
            for p in f["products"]:
                quantity = (
                    0
                    if kind == "pallet"
                    else 3
                    if name == "exhausted-source-return"
                    else 1
                    if name == "foreign-reserve"
                    else 30
                )
                if quantity:
                    await record_movement_and_adjust_balance(
                        session,
                        tenant_id=tenant,
                        product_id=uuid.UUID(p["id"]),
                        storage_location_id=loc.id,
                        quantity_delta=quantity,
                        movement_type="inbound_intake",
                        actor_user_id=actor_id,
                        container_kind=kind,
                        container_id=container.id if container else None,
                    )
                sf["initial"][p["id"]] = quantity
            f["sources"].append(sf)
        if name == "print-picked":
            # Three real document origins, plus the ordinary loose unlinked balance.
            f["print_origins"] = []
            product_id = uuid.UUID(f["products"][0]["id"])
            for origin_index, operation in enumerate(("inbound", "return", "inventory")):
                request = None
                line = None
                label = f"CI-{operation.upper()}"
                if operation != "inventory":
                    request = InboundIntakeRequest(
                        id=uuid.uuid4(),
                        tenant_id=tenant,
                        seller_id=seller,
                        warehouse_id=warehouse,
                        status="completed",
                        operation_type=operation,
                        display_number=label,
                        posted_at=datetime.now(UTC),
                    )
                    session.add(request)
                    await session.flush()
                    line = InboundIntakeLine(
                        id=uuid.uuid4(),
                        request_id=request.id,
                        product_id=product_id,
                        expected_qty=5,
                        actual_qty=5,
                        posted_qty=5,
                        storage_location_id=locations[0].id,
                    )
                    session.add(line)
                    await session.flush()
                box = WarehouseBox(
                    id=uuid.uuid4(),
                    tenant_id=tenant,
                    warehouse_id=warehouse,
                    storage_location_id=locations[0].id,
                    inbound_request_id=request.id if request else None,
                    internal_barcode=f"ORIGIN-{index}-{origin_index}",
                )
                session.add(box)
                await session.flush()
                if operation == "inventory":
                    count = InventoryCount(
                        id=uuid.uuid4(),
                        tenant_id=tenant,
                        warehouse_id=warehouse,
                        seller_id=seller,
                        status="posted",
                        source="planned",
                        created_by_user_id=actor_id,
                        posted_by_user_id=actor_id,
                        posted_at=datetime.now(UTC),
                    )
                    session.add(count)
                    await session.flush()
                    session.add(
                        InventoryCountCreatedContainer(
                            tenant_id=tenant,
                            count_id=count.id,
                            container_kind="box",
                            container_id=box.id,
                        )
                    )
                    label = f"И: {str(count.id)[:8]}"
                else:
                    label = f"{'В' if operation == 'return' else 'П'}: {label}"
                await record_movement_and_adjust_balance(
                    session,
                    tenant_id=tenant,
                    product_id=product_id,
                    storage_location_id=locations[0].id,
                    quantity_delta=5,
                    movement_type="inventory_count"
                    if operation == "inventory"
                    else "inbound_intake",
                    actor_user_id=actor_id,
                    container_kind="box",
                    container_id=box.id,
                    inbound_intake_line_id=line.id if line else None,
                )
                f["print_origins"].append({"title": label, "barcode": box.internal_barcode})
        for si in range(2 if name in GROUPS or name == "foreign-reserve" else 1):
            supply_warehouse = (
                warehouse2 if name == "print-group-warehouses" and si == 1 else warehouse
            )
            supply = FbsSupply(
                id=uuid.uuid4(),
                tenant_id=tenant,
                seller_id=seller,
                warehouse_id=supply_warehouse,
                marketplace="ozon" if name in OZON else "wb",
                wb_supply_id=None if name in OZON else f"WB-EXT-{index}-{si}",
                name=f"Extended CI {name} {si}",
                source="wb" if name == "wb-source-banner" else "wms",
                status="assembling",
                delivery_type="warehouse_sc",
            )
            session.add(supply)
            await session.flush()
            f["supplies"].append(str(supply.id))
            plan = 1 if name == "foreign-reserve" else 3
            order_ozon = None
            for pi, p in enumerate(f["products"]):
                if name == "ozon-group-scan":
                    plan = 2 + pi
                for oi in range(1 if name in OZON else plan):
                    order = FbsOrder(
                        id=uuid.uuid4(),
                        tenant_id=tenant,
                        seller_id=seller,
                        warehouse_id=supply_warehouse,
                        supply_id=supply.id,
                        product_id=uuid.UUID(p["id"]),
                        marketplace="ozon" if name in OZON else "wb",
                        external_order_id=f"OZ-EXT-{index}-{si}" if name in OZON else None,
                        wb_order_id=970000000 + index * 1000 + si * 100 + pi * 10 + oi,
                        wb_barcode=p["barcode"],
                        wb_article=p["sku"],
                        wb_warehouse_id=501001,
                        created_at_wb=datetime.now(UTC) - timedelta(hours=1),
                        deadline_at=datetime.now(UTC) + timedelta(days=2),
                        meta_details_json={
                            "ozon_delivery_method_name": "Ozon Courier CI",
                            "ozon_delivery_method_id": "CI-DELIVERY",
                        }
                        if name in OZON
                        else None,
                        mapping_status="mapped",
                        reserve_status="no_stock"
                        if name == "foreign-reserve" and si == 0
                        else "reserved",
                        status="in_supply",
                    )
                    if name in OZON and order_ozon is not None:
                        order = order_ozon
                    else:
                        session.add(order)
                        await session.flush()
                        order_ozon = order
                    f["orders"].append(
                        {"id": str(order.id), "supply": str(supply.id), "product": p["id"]}
                    )
                    if name in OZON:
                        pos = FbsOrderProduct(
                            id=uuid.uuid4(),
                            order_id=order.id,
                            product_id=uuid.UUID(p["id"]),
                            ozon_sku=880000 + index * 10 + pi,
                            offer_id=p["offer"],
                            name=p["name"],
                            quantity=plan,
                            reserved_quantity=plan,
                            position_index=pi,
                        )
                        session.add(pos)
                        await session.flush()
                        session.add(
                            FbsOrderProductReservation(
                                tenant_id=tenant,
                                order_product_id=pos.id,
                                product_id=pos.product_id,
                                warehouse_id=supply_warehouse,
                                quantity=plan,
                            )
                        )
                        f["positions"].append(
                            {
                                "id": str(pos.id),
                                "order": str(order.id),
                                "product": p["id"],
                                "supply": str(supply.id),
                                "warehouse": str(supply_warehouse),
                                "quantity": plan,
                            }
                        )
                    elif name != "foreign-reserve" or si != 0:
                        session.add(
                            FbsOrderReservation(
                                tenant_id=tenant,
                                fbs_order_id=order.id,
                                product_id=uuid.UUID(p["id"]),
                                warehouse_id=supply_warehouse,
                                quantity=1,
                            )
                        )
            if name == "ozon-handover":
                session.add(
                    FbsWbOperation(
                        tenant_id=tenant,
                        seller_id=seller,
                        operation_kind="supply_deliver",
                        idempotency_key=f"ci-confirmed-{index}",
                        local_entity_type="fbs_supply",
                        local_entity_id=supply.id,
                        state="confirmed",
                        confirmed_at=datetime.now(UTC),
                        request_summary_json={"marketplace": "ozon"},
                    )
                )
        if name in GROUPS:
            task = FbsAssemblyTask(
                id=uuid.uuid4(),
                tenant_id=tenant,
                number=f"EX-{index}",
                idempotency_key=f"ex-{index}",
            )
            session.add(task)
            await session.flush()
            for sid in f["supplies"]:
                session.add(FbsAssemblyTaskSupply(task_id=task.id, supply_id=uuid.UUID(sid)))
            f["task"] = str(task.id)
        if name == "foreign-location":
            outsider = Tenant(
                id=uuid.uuid4(),
                name="Foreign browser fixture",
                slug=f"foreign-ci-{uuid.uuid4().hex[:8]}",
            )
            session.add(outsider)
            await session.flush()
            wh = Warehouse(id=uuid.uuid4(), tenant_id=outsider.id, name="Foreign", code="FOREIGN")
            session.add(wh)
            await session.flush()
            loc = StorageLocation(
                id=uuid.uuid4(),
                tenant_id=outsider.id,
                warehouse_id=wh.id,
                code=f"FOREIGN-{index}",
                barcode=f"FOREIGN-{index}",
            )
            session.add(loc)
            await session.flush()
            f["foreign_code"] = loc.barcode
        result[name] = f
    return result
