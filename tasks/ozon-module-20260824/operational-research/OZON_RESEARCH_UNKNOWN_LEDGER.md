# Ozon research unknown ledger: concrete account facts only

**Call:** `35-ozon-operational-research-live-evidence-correction-path-authorized`  
**Admission rule:** `UNKNOWN_EXHAUSTED` is used only for a concrete account, supply, return or delivery-method fact that requires authenticated readback and cannot be obtained because Client-Id is missing. Live public docs are not unknown.

## Shared blocker and attempts

- The owner-designated shared Git marker exists.
- Only variable name `OZON_TEST_API_KEY` was found and its nonempty state was checked; the value was not printed or stored.
- `Client-Id` was not found in that marker.
- Ozon Seller API requires both `Client-Id` and `Api-Key`; a complete authenticated header pair cannot be formed.
- Executed provider calls: **0**. No read, mutation, task creation, label generation or stock update was attempted.
- The 61 read-only candidates and 29 mutation/task denylist entries remain classified in [`OZON_READ_ONLY_CAPABILITY_EVIDENCE.json`](./OZON_READ_ONLY_CAPABILITY_EVIDENCE.json).

## UNKNOWN-001 — concrete owner-account read capability

- **Missing fact:** which of the 61 allowlisted read operations the owner test account is permitted to call and which provider capability flags are enabled.
- **What is already confirmed:** all 90 operation identities/methods/paths exist in live Seller API documentation; auth header names are `Client-Id` and `Api-Key`.
- **Exhausted attempt:** inspected only the designated marker's existence, variable names and nonempty state without exposing values. API key exists; Client-Id does not.
- **Classification:** `UNKNOWN_EXHAUSTED`.
- **Reason:** concrete account result requires an authenticated call, impossible without Client-Id.
- **Not a conclusion:** no endpoint is labelled unsupported by the account merely because it was not called.

## UNKNOWN-002 — concrete FBS delivery-method/point handover capability

- **Missing fact:** for the owner's actual FBS warehouse and delivery method, whether the posting is handed over at a point one-by-one, piecewise to courier, or via entrusted acceptance; whether transport documents are enabled.
- **What is already confirmed:** point handover can omit shipment/carriage formation and use posting labels; piecewise courier and entrusted acceptance require shipment formation; old carriage remains applicable for transport documents.
- **Exhausted attempt:** live official assembly and handover pages were captured; account delivery-method reads are allowlisted but cannot run without Client-Id.
- **Classification:** `UNKNOWN_EXHAUSTED`.
- **Reason:** route/method selection is account and warehouse specific.
- **Operational consequence:** handover is `CAPABILITY_CONDITIONAL`; no universal carriage action may be inferred.

## UNKNOWN-003 — concrete FBO supply GM/TGM rules

- **Missing fact:** for a specific owner supply, required GM count/type and distribution, whether TGM is enabled/required, and whether local WMS boxes map deterministically to Ozon GM.
- **What is already confirmed:** live guide shows TGM activation, pallet creation, GM binding and pallet labels for large-volume flows; live Seller API exposes cargo rules/readback paths.
- **Exhausted attempt:** public docs and TGM guide are complete for operation existence/process; `/v1/cargoes/rules/get`, `/v1/cargoes/supplies/get` and cargo status reads cannot be executed for a concrete supply without Client-Id.
- **Classification:** `UNKNOWN_EXHAUSTED`.
- **Reason:** applicability is supply/capability specific.
- **Operational consequence:** TGM is not universal; ordinary GM scope also remains supply-specific.

## UNKNOWN-004 — concrete FBO beta act requirement

- **Missing fact:** whether a specific owner supply reaches an act state requiring manual `/v1/supply-order/act/accept`, or completes without that action.
- **What is already confirmed:** four beta act methods exist in live official documentation and official release evidence.
- **Exhausted attempt:** public operation sections are captured; no existing supply state/act summary can be read without Client-Id.
- **Classification:** `UNKNOWN_EXHAUSTED`.
- **Reason:** mandatory scope is account/supply specific.
- **Safety boundary:** `/accept` is a mutation and remains forbidden in research even if credentials later exist.

## Removed from UNKNOWN after live correction

- Live official documentation availability and 90 operation method/path identity: confirmed, not unknown.
- 41 requested core operation sections: confirmed present, not unknown.
- FBS assembly, FBS handover and FBO TGM official process pages: confirmed live, not unknown.
- Universal label symbology/dimensions, universal key TTL and a universal automatic-restock rule are not recast as `UNKNOWN_EXHAUSTED`; the available evidence simply does not support those broader claims.

## Resolution boundary

Resolving these four items would require an explicitly authorised Client-Id paired with the already designated API key, concrete existing account/supply/delivery-method entities and read-only calls only. Concrete return giveout eligibility, if later needed, is covered by the general account-capability item rather than promoted into a separate broader claim. Call 35 does not grant that authority and makes no provider call.
