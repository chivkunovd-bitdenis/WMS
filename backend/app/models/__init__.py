"""ORM models — import side effects register metadata for Alembic."""

from app.models.background_job import BackgroundJob
from app.models.base import Base
from app.models.discrepancy_act import DiscrepancyAct, DiscrepancyActLine
from app.models.document_sequence import DocumentSequence
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
    MarkingPool,
    MarkingPoolProduct,
)
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.models.seller import Seller
from app.models.seller_shop_delegation import SellerShopDelegation
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.seller_wildberries_imported_supply import SellerWildberriesImportedSupply
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
    "DocumentSequence",
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
    "MarkingPool",
    "MarkingPoolProduct",
    "OutboundShipmentLine",
    "OutboundShipmentRequest",
    "PackagingTask",
    "PackagingTaskLine",
    "Product",
    "Seller",
    "SellerShopDelegation",
    "SellerWildberriesCredentials",
    "SellerWildberriesImportedCard",
    "SellerWildberriesImportedSupply",
    "StorageLocation",
    "Tenant",
    "TenantWbMpWarehouse",
    "User",
    "Warehouse",
    "WarehouseBox",
    "WarehouseStorageRack",
]
