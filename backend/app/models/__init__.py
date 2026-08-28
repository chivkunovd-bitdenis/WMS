"""ORM models — import side effects register metadata for Alembic."""

from app.models.background_job import BackgroundJob
from app.models.base import Base
from app.models.billing import (
    BillingInvoice,
    BillingInvoiceV2,
    BillingInvoiceV2Idempotency,
    BillingInvoiceV2Line,
    BillingInvoiceV2Source,
    BillingLedgerEntry,
    BillingLedgerLine,
    BillingProfile,
    BillingRunIssue,
    BillingTariffMatrixConfig,
    BillingTariffServiceState,
    BillingTariffVersion,
    BillingTariffVersionV2,
)
from app.models.discrepancy_act import DiscrepancyAct, DiscrepancyActLine
from app.models.document_event import DocumentEvent
from app.models.document_sequence import DocumentDisplaySequence, DocumentSequence
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_order import (
    FbsOrder,
    FbsOrderMarking,
    FbsOrderProduct,
    FbsOrderProductPick,
    FbsOrderProductReservation,
    FbsOrderReservation,
)
from app.models.fbs_order_pick import FbsOrderPick, FbsOrderPickEvent
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_packing_box import FbsPackingBox, FbsPackingBoxItem
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_stock_pool_debit import FbsStockPoolDebit
from app.models.fbs_stock_sync_item import FbsStockSyncItem
from app.models.fbs_supply import FbsSupply
from app.models.fbs_trbx import FbsTrbx
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.ff_staff_permissions import FfStaffPermissions
from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeCargoPlace,
    InboundIntakeCargoPlaceLine,
    InboundIntakeLine,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_count import InventoryCount, InventoryCountLine
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_reservation import InventoryReservation
from app.models.marketplace_account import MarketplaceAccount
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
from app.models.operation_fact import OperationFact, OperationFactCutover, OperationFactLine
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.ozon_return import InboundOzonReturnGiveout, InboundOzonReturnItem
from app.models.packaging_task import PackagingTask, PackagingTaskEvent, PackagingTaskLine
from app.models.pallet import Pallet
from app.models.print_template import PrintTemplate
from app.models.product import Product
from app.models.product_dimension_event import ProductDimensionEvent
from app.models.product_marketplace_link import ProductMarketplaceLink
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
from app.models.storage_measurement import StorageMeasurement
from app.models.storage_statement import StorageStatement
from app.models.tenant import Tenant
from app.models.tenant_wb_mp_warehouse import TenantWbMpWarehouse
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.models.warehouse_map_event import WarehouseMapEvent
from app.models.warehouse_storage_rack import WarehouseStorageRack

__all__ = [
    "BackgroundJob",
    "Base",
    "BillingInvoice",
    "BillingInvoiceV2",
    "BillingInvoiceV2Idempotency",
    "BillingInvoiceV2Line",
    "BillingInvoiceV2Source",
    "BillingLedgerEntry",
    "BillingLedgerLine",
    "BillingProfile",
    "BillingRunIssue",
    "BillingTariffMatrixConfig",
    "BillingTariffServiceState",
    "BillingTariffVersion",
    "BillingTariffVersionV2",
    "DiscrepancyAct",
    "DiscrepancyActLine",
    "DocumentDisplaySequence",
    "DocumentEvent",
    "DocumentSequence",
    "FbsBindingStockPool",
    "FbsOrder",
    "FbsOrderMarking",
    "FbsOrderPick",
    "FbsOrderPickEvent",
    "FbsOrderProduct",
    "FbsOrderProductPick",
    "FbsOrderProductReservation",
    "FbsOrderReservation",
    "FbsPackagingFulfillment",
    "FbsPackingBox",
    "FbsPackingBoxItem",
    "FbsPrintAsset",
    "FbsShipmentReversalLedger",
    "FbsStockPoolDebit",
    "FbsStockSyncItem",
    "FbsSupply",
    "FbsTrbx",
    "FbsWarehouseBinding",
    "FbsWbOperation",
    "FfStaffPermissions",
    "InboundIntakeBox",
    "InboundIntakeBoxLine",
    "InboundIntakeCargoPlace",
    "InboundIntakeCargoPlaceLine",
    "InboundIntakeLine",
    "InboundIntakeRequest",
    "InboundOzonReturnGiveout",
    "InboundOzonReturnItem",
    "InventoryBalance",
    "InventoryCount",
    "InventoryCountLine",
    "InventoryMovement",
    "InventoryReservation",
    "MarketplaceAccount",
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
    "OperationFact",
    "OperationFactCutover",
    "OperationFactLine",
    "OutboundShipmentLine",
    "OutboundShipmentRequest",
    "PackagingTask",
    "PackagingTaskEvent",
    "PackagingTaskLine",
    "Pallet",
    "PrintTemplate",
    "Product",
    "ProductDimensionEvent",
    "ProductMarketplaceLink",
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
    "StorageMeasurement",
    "StorageStatement",
    "Tenant",
    "TenantWbMpWarehouse",
    "User",
    "Warehouse",
    "WarehouseBox",
    "WarehouseMapEvent",
    "WarehouseStorageRack",
]
