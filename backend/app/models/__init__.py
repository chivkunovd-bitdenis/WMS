"""ORM models — import side effects register metadata for Alembic."""

from app.models.base import Base
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse

__all__ = [
    "Base",
    "InboundIntakeLine",
    "InboundIntakeRequest",
    "Product",
    "Seller",
    "StorageLocation",
    "Tenant",
    "User",
    "Warehouse",
]
