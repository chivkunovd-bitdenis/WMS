"""ORM models — import side effects register metadata for Alembic."""

from app.models.background_job import BackgroundJob
from app.models.base import Base
from app.models.discrepancy_act import DiscrepancyAct, DiscrepancyActLine
from app.models.document_sequence import DocumentDisplaySequence, DocumentSequence
from app.models.fbs_order import FbsOrder, FbsOrderMarking, FbsOrderReservation
from app.models.fbs_order_pick import FbsOrderPick, FbsOrderPickEvent
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_packing_box import FbsPackingBox, FbsPackingBoxItem
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_stock_sync_item import FbsStockSyncItem
from app.models.fbs_supply import FbsSupply
from app.models.fbs_trbx import FbsTrbx
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.ff_staff_permissions import FfStaffPermissions
from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeLine,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_reservation import InventoryReservation
from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadLine,
    MarketplaceUnloadPickAllocation,
    MarketplaceUnloadRequest,
)
from app.models.marketplace_unload_reservation import MarketplaceUnloadReservation
from app.models.marking_code import (
    MarkingCode,
    MarkingCodeEvent,
    MarkingCodeImport,
    MarkingCodeImportFile,
    MarkingPool,
    MarkingPoolProduct,
    MarkingReprintRequest,
)
from app.models.notification import Notification
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.print_template import PrintTemplate
from app.models.product import Product
from app.models.product_tz_import import ProductTzImport
from app.models.seller import Seller
from app.models.seller_marking_credentials import SellerMarkingCredentials
from app.models.seller_shop_delegation import SellerShopDelegation
from app.models.seller_staff_permissions import SellerStaffPermissions
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.seller_wildberries_imported_supply import SellerWildberriesImportedSupply
from app.models.stock_direction import StockDirection, StockMonthlySnapshot
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.tenant_wb_mp_warehouse import TenantWbMpWarehouse
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.models.warehouse_storage_rack import WarehouseStorageRack

__all__ = [
    "BackgroundJob",
    "Base",
    "DiscrepancyAct",
    "DiscrepancyActLine",
    "DocumentDisplaySequence",
    "DocumentSequence",
    "FbsOrder",
    "FbsOrderMarking",
    "FbsOrderPick",
    "FbsOrderPickEvent",
    "FbsOrderReservation",
    "FbsPackagingFulfillment",
    "FbsPackingBox",
    "FbsPackingBoxItem",
    "FbsPrintAsset",
    "FbsShipmentReversalLedger",
    "FbsStockSyncItem",
    "FbsSupply",
    "FbsTrbx",
    "FbsWarehouseBinding",
    "FbsWbOperation",
    "FfStaffPermissions",
    "InboundIntakeBox",
    "InboundIntakeBoxLine",
    "InboundIntakeLine",
    "InboundIntakeRequest",
    "InventoryBalance",
    "InventoryMovement",
    "InventoryReservation",
    "MarketplaceUnloadBox",
    "MarketplaceUnloadBoxLine",
    "MarketplaceUnloadLine",
    "MarketplaceUnloadPickAllocation",
    "MarketplaceUnloadRequest",
    "MarketplaceUnloadReservation",
    "MarkingCode",
    "MarkingCodeEvent",
    "MarkingCodeImport",
    "MarkingCodeImportFile",
    "MarkingPool",
    "MarkingPoolProduct",
    "MarkingReprintRequest",
    "Notification",
    "OutboundShipmentLine",
    "OutboundShipmentRequest",
    "PackagingTask",
    "PackagingTaskLine",
    "PrintTemplate",
    "Product",
    "ProductTzImport",
    "Seller",
    "SellerMarkingCredentials",
    "SellerShopDelegation",
    "SellerStaffPermissions",
    "SellerWildberriesCredentials",
    "SellerWildberriesImportedCard",
    "SellerWildberriesImportedSupply",
    "StockDirection",
    "StockMonthlySnapshot",
    "StorageLocation",
    "Tenant",
    "TenantWbMpWarehouse",
    "User",
    "Warehouse",
    "WarehouseBox",
    "WarehouseStorageRack",
]
