"""Provider-neutral aggregate result for one seller's stock publication."""

from dataclasses import dataclass


@dataclass
class SellerStockSyncResult:
    bindings_processed: int = 0
    products_targeted: int = 0
    products_confirmed: int = 0
    products_zeroed: int = 0
    conflicts: int = 0
    errors: int = 0
    binding_errors: int = 0
