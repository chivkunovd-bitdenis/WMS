# ARCH-P2-005 — seller-shop manager capability is partly derived from email text

## Result

**Severity: P2. Status: CONFIRMED_STATIC_POLICY_DEBT; NO_CROSS_SELLER_BYPASS_PROVED.** A seller can receive shop-management capability not only from the explicit database flag/configured list, but also when the email contains one of several hard-coded name markers (`backend/app/services/seller_shop_service.py:21-58`). Test-domain/prefix classification is likewise derived from email text at `:21-41`.

Acting as another seller still requires an enabled `SellerShopDelegation` and a same-tenant target (`:150-173`). Therefore the review did not find a direct cross-tenant or automatic cross-seller bypass. The defect is policy ownership: access is partly controlled by mutable user-facing text and code constants rather than one explicit stored assignment.

## Runtime boundary and countermeasure

The seller first-login path was executed successfully, but manager delegation and cross-seller denial were not exercised. The full authorization and two-tenant runtime scenarios remain `NOT_RUN`.

The minimal correction is to make `can_manage_seller_shops` plus explicit same-tenant delegations the only runtime authority. Keep test classification in deployment/test fixtures rather than production access logic, and add direct API tests for a marker-containing ordinary email and an unlisted target shop.
