"""ORM models — import side effects register metadata for Alembic."""

from app.models.background_job import BackgroundJob
from app.models.base import Base
from app.models.discrepancy_act import DiscrepancyAct, DiscrepancyActLine
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_reservation import InventoryReservation
from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.product import Product
from app.models.seller import Seller
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.seller_wildberries_imported_supply import SellerWildberriesImportedSupply
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse

__all__ = [
    "BackgroundJob",
    "Base",
    "DiscrepancyAct",
    "DiscrepancyActLine",
    "InboundIntakeLine",
    "InboundIntakeRequest",
    "InventoryBalance",
    "InventoryMovement",
    "InventoryReservation",
    "MarketplaceUnloadLine",
    "MarketplaceUnloadRequest",
    "OutboundShipmentLine",
    "OutboundShipmentRequest",
    "Product",
    "Seller",
    "SellerWildberriesCredentials",
    "SellerWildberriesImportedCard",
    "SellerWildberriesImportedSupply",
    "StorageLocation",
    "Tenant",
    "User",
    "Warehouse",
]
