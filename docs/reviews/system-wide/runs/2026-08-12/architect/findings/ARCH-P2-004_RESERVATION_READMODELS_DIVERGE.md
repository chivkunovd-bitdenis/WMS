# ARCH-P2-004 — availability is calculated differently across reservation contours

## Result

**Severity: P2. Status: CONFIRMED_STATIC_DIVERGENCE; CROSS-CONTOUR OVERBOOKING NOT_RUNTIME_REPRODUCED.** There is no single reservation ownership calculation shared by inventory, FBS, outbound, and marketplace unload.

- FBS availability explicitly subtracts outbound and FBS reservations but excludes `MarketplaceUnloadReservation` (`backend/app/services/fbs_stock_availability_service.py:123-155`).
- Marketplace-unload availability subtracts outbound, marketplace-unload, and FBS reservations (`backend/app/services/marketplace_unload_service.py:391-418`, `:466-490`).
- Location-level inventory availability subtracts only `InventoryReservation` for outbound (`backend/app/services/inventory_service.py:102-155`).
- Inventory summary includes FBS reservations only when a `warehouse_id` is supplied (`backend/app/services/inventory_service.py:232-250`). The FF catalog calls the summary without one (`frontend/src/screens/v2/FfProductsCatalogScreen.tsx:130-140`), so its default reserved/available display omits FBS.

The immediate confirmed defect is semantic divergence between read models: the same physical stock can yield different reserved/available values depending on the screen or process. A more serious order-dependent overbooking is plausible when an MP reservation already exists and FBS availability ignores it, but the review did not inject a synthetic FBS order and live WB mutation was forbidden; that part remains a static risk, not a confirmed runtime defect.

## Minimal countermeasure

Define one tested availability function per warehouse/product that subtracts all active reservation owners, with explicit inclusion/exclusion parameters only for editing the current object. Reuse it for FBS intake/publish, MP planning, stock transfer validation, and inventory read models. Add a permutation test that reserves the same stock in every contour order.
