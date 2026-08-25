# CALL74 · API/data/migration contract для marketplace account и Ozon connection

## Решение в одном абзаце

Добавляется generic `marketplace_accounts`, где каждая запись имеет стабильный account id и явные tenant/seller/marketplace/slot scopes. S0 Ozon self-service всегда адресует скрытый slot `primary`, поэтому пользователь видит один account без selector. `Api-Key` хранится только как Fernet ciphertext; `Client-Id` хранится как внешний account identifier, но не возвращается self API. WB продолжает использовать `seller_wildberries_credentials` без backfill и behavioral changes.

## Точные file boundaries

Production/migration/test developer может менять только файлы из `NARYAD.md`:

- S-32: `frontend/src/screens/v2/SellerSettingsScreen.tsx`;
- shared S-32: `frontend/src/api.ts` — включён явно, менять только если существующий `apiUrl` реально недостаточен;
- frontend regression/E2E: `frontend/tests-e2e/seller-settings.spec.ts`;
- API wiring: `backend/app/api/ozon_integration.py`, `backend/app/main.py`;
- model registration/relationship: `backend/app/models/marketplace_account.py`, `backend/app/models/seller.py`, `backend/app/models/__init__.py`;
- services: `backend/app/services/marketplace_account_service.py`, `backend/app/services/ozon_client.py`;
- migration: `backend/alembic/versions/20260825_0101_marketplace_accounts.py`, `down_revision="20260823_0100"`;
- tests: `backend/tests/test_marketplace_account_service.py`, `backend/tests/test_ozon_integration_api.py`, `backend/tests/test_marketplace_accounts_migration.py`.

`integration_fernet.py`, WB model/service/API/tests, auth/permission service and any FBS/FBO/stock files are read-only reusable dependencies and не входят в границу правки.

## Data model

### Таблица `marketplace_accounts`

| Column | Type / nullability | Contract and user work |
|---|---|---|
| `id` | UUID PK, not null | Stable account identity. Future mappings can reference an account, so seller/provider identity is not inferred from UI selection. |
| `tenant_id` | UUID FK `tenants.id` CASCADE, not null, indexed | Mandatory isolation dimension on every query. |
| `seller_id` | UUID FK `sellers.id` CASCADE, not null, indexed | Connection belongs to the seller whose settings are open. |
| `marketplace` | String(32), not null | Generic provider dimension. S0 service accepts only literal `ozon`; DB is not a provider enum so a future provider does not require rewriting account identity. |
| `account_slot` | String(64), not null, default `primary` | Hidden addressing dimension. S0 always uses `primary`; future multiplicity can add other opaque slots without changing downstream account foreign keys. Never exposed in S0 UI. |
| `external_account_id` | String(255), nullable only after disconnect | Trimmed Ozon `Client-Id`. Treated as sensitive account metadata: never returned by self status and never logged. It is not encrypted because only `Api-Key` is contractually secret, but access remains tenant-scoped. |
| `secret_encrypted` | String(4096), nullable | Fernet ciphertext of `Api-Key`. Plaintext exists only in request memory and provider client call. Set `NULL` on disconnect. |
| `is_active` | Boolean, not null, default false | True only when both identifiers were validated and persisted. |
| `validation_status` | String(24), not null | Closed values: `not_configured`, `valid`, `invalid`, `unavailable`. No provider capability is encoded here. |
| `last_validated_at` | timezone datetime, nullable | Fact from the last completed manual/save validation attempt for the stored pair. |
| `last_validation_error_code` | String(64), nullable | Only WMS-safe codes: `credentials_invalid`, `rate_limited`, `provider_unavailable`, `transport_error`, `unexpected_status`. No provider body. |
| `last_synced_at` | timezone datetime, nullable | Reserved factual audit slot for a future accepted sync producer. This slice never writes it and S-32 hides it while null. |
| `last_sync_error_code` | String(64), nullable | Same rule: this slice never writes it; no speculative error appears in UI. |
| `credentials_updated_at` | timezone datetime, nullable | When the currently stored pair actually changed; idempotent replay of identical values does not move it. |
| `created_at`, `updated_at` | timezone datetime, not null | Row audit. `updated_at` moves on factual state changes. |
| `created_by_user_id`, `updated_by_user_id` | UUID FK `users.id` SET NULL, nullable | Actor audit for successful create/update. |
| `disconnected_at`, `disconnected_by_user_id` | timezone datetime / UUID FK `users.id` SET NULL, nullable | Disconnect audit survives secret erasure. |

Constraints and indexes:

- unique `(tenant_id, seller_id, marketplace, account_slot)`; this is the database idempotency guard for S0 `primary` and the prepared multiplicity hook;
- index `(tenant_id, seller_id, marketplace, is_active)` for scoped status lookup;
- check `marketplace <> ''` and `account_slot <> ''`;
- relationship `Seller.marketplace_accounts` is one-to-many with delete-orphan/cascade; existing `Seller.wildberries_credentials` remains one-to-one and unchanged.

Migration compatibility:

- upgrade only creates the new table/constraints/indexes; it does not read, copy, encrypt, update or delete any WB row;
- no new non-null column is added to existing tables, so deployed WB/API readers remain compatible during rollout;
- downgrade drops only `marketplace_accounts`; it cannot alter WB data;
- model metadata must import `MarketplaceAccount` in `backend/app/models/__init__.py` so dev/e2e auto-create sees the same schema;
- migration test verifies clean upgrade, downgrade and re-upgrade from `20260823_0100`, plus preservation of an existing `seller_wildberries_credentials` row byte-for-byte.

## Encryption and secret handling

- Reuse `encrypt_secret`/`decrypt_secret` from `integration_fernet.py`; do not add a second crypto key or plaintext fallback.
- Normalize with `strip()` before validation. Empty after trim is rejected. Do not lowercase or otherwise transform either credential.
- Candidate `Api-Key` is encrypted only after provider validation succeeds. Identical replay may decrypt the stored value solely inside the service and compare via `hmac.compare_digest`; if identical, retain the existing ciphertext so `credentials_updated_at` stays stable.
- Plaintext credential, ciphertext, Client-Id, request headers and provider response body must never enter logger arguments, exceptions, API responses, audit messages, fixtures committed to Git or snapshots.
- Service methods that return secrets are private to the provider adapter path; public/status methods return booleans and safe status fields only.
- Disconnect sets `secret_encrypted=NULL` before commit. Historical actor/time remain; no secret tombstone remains.

## Permission and tenant contract

Every route uses `get_current_user`, `get_effective_seller_id` and then `assert_seller_permission(session, user, PERM_SETTINGS)`. After that it requires `user.role == FULFILLMENT_SELLER` and a non-null effective seller. The service scopes by `user.tenant_id` and `effective_seller_id`; self routes accept no seller id or account id from the client.

- owner with effective seller: allowed because current seller owner permission model grants settings;
- seller staff/admin with explicit `settings=true`: allowed;
- seller staff with `settings=false`: 403 `forbidden`;
- fulfillment admin, warehouse staff, unauthenticated user: 403/401;
- deleted/missing seller or tenant mismatch: 404 `seller_not_found` after fail-closed lookup, without revealing whether another tenant has an Ozon account.

## API contract

Router prefix: `/integrations/ozon`. All responses use explicit Pydantic models with `extra="forbid"` on request bodies.

### Public status shape

```json
{
  "marketplace": "ozon",
  "connected": true,
  "validation_status": "valid",
  "last_validated_at": "2026-08-25T06:00:00Z",
  "last_validation_error": null,
  "credentials_updated_at": "2026-08-25T06:00:00Z",
  "last_synced_at": null,
  "last_sync_error": null
}
```

This exact shape never contains `id`, `account_slot`, `seller_id`, `tenant_id`, `external_account_id`, `client_id`, `api_key`, `secret`, ciphertext or provider response. `expires_at` is deliberately absent because no accepted evidence proves such a field. A future fact may add an optional nullable field backward-compatibly; until then UI remains unchanged.

### `GET /integrations/ozon/self/account`

- 200 always for an authorized existing seller. If no active primary row: `connected=false`, `validation_status=not_configured`, all timestamps/errors null.
- Read-only WMS operation; no provider call and no DB update.

### `PUT /integrations/ozon/self/account`

Request:

```json
{"client_id":"<1..255 chars>","api_key":"<1..4096 chars>"}
```

Semantics:

1. Reject missing/blank `client_id` as 422 `client_id_required`; reject missing/blank `api_key` as 422 `api_key_required`; reject unknown fields/type/length as 422.
2. Validate candidate with the exact safe provider contract below before any credential DB write.
3. On validation success, lock the seller/primary row transactionally and upsert one `(tenant,seller,ozon,primary)` row. Create and update both return 200 with public status.
4. Same normalized pair replay leaves account id, row count, ciphertext and `credentials_updated_at` unchanged; it may refresh `last_validated_at` because a new read-only fact occurred.
5. Different valid pair atomically replaces both values and sets `updated_by_user_id`/`credentials_updated_at`.
6. Any failed/unavailable candidate validation does not create a row and does not mutate a previously stored pair or its public status.

### `POST /integrations/ozon/self/account/test-connection`

- No request body; unknown/non-empty body rejected 422.
- Missing active pair: 409 `ozon_not_connected`.
- Decrypt stored pair in memory and run the same read-only provider call.
- 2xx: persist `valid`, clear safe error, stamp `last_validated_at`, return 200 public status.
- 401/403: persist `invalid` + `credentials_invalid`, stamp time, return 422 `ozon_credentials_invalid`.
- network/timeout: persist `unavailable` + `transport_error`, return 503 `ozon_validation_unavailable`.
- 429: persist `unavailable` + `rate_limited`, return 503 `ozon_validation_unavailable`.
- 5xx: persist `unavailable` + `provider_unavailable`, return 503 `ozon_validation_unavailable`.
- other non-2xx: persist `unavailable` + `unexpected_status`, return 502 `ozon_validation_failed`.

Repeated calls are provider-read-only and create no account rows or provider mutations; only last factual validation status/time may change.

### `DELETE /integrations/ozon/self/account`

- No body.
- Lock primary row. If active, clear ciphertext, mark inactive/not_configured, clear validation/sync display fields, stamp `updated_at`, `disconnected_at`, `disconnected_by_user_id`.
- If already absent/inactive, do nothing.
- Always return 204 for authorized existing seller. This makes double click/retry idempotent and reveals no historical metadata.

## Safe Ozon validation adapter

The only permitted provider operation in this slice is:

- method/path: `POST /v1/seller/info`;
- request body: `{}` because accepted sanitized request shape is empty;
- headers: `Client-Id` and `Api-Key` from the candidate/stored pair; ordinary JSON headers as required by the existing HTTP client;
- semantics: read-only; success is HTTP 2xx only; response body is ignored and closed without parsing or persistence;
- redirects are not followed across hosts; base URL comes from server settings, never request/client input;
- bounded timeout; no automatic retry inside a user click, so one click cannot cause an uncontrolled provider call burst;
- no provider mutation endpoints, stock writes, product/order sync, background task or queue enqueue.

Supported fact: method/path/read-only classification and empty sanitized request shape. BLOCKED and therefore not implemented: account capability flags, nested seller-info schema, expiry, scopes, warehouse/delivery/return fields and all mutations.

## Exact API-to-UI error words

| API code | HTTP | S-32 text |
|---|---:|---|
| `client_id_required` | 422 | `Введите Client-Id.` |
| `api_key_required` | 422 | `Введите Api-Key.` |
| `ozon_credentials_invalid` | 422 | `Ozon не подтвердил Client-Id и Api-Key. Проверьте оба значения.` |
| `ozon_validation_unavailable` | 503 | `Не удалось проверить подключение Ozon. Сохранённые данные не изменены; попробуйте ещё раз.` |
| `ozon_validation_failed` | 502 | `Ozon вернул неожиданный ответ. Сохранённые данные не изменены; попробуйте позже.` |
| `ozon_not_connected` | 409 | `Сначала подключите Ozon.` |
| `forbidden` | 403 | `Нет доступа к настройкам интеграции.` |
| unexpected WMS 5xx | 500 | `Не удалось сохранить подключение Ozon. Повторите попытку.` |

Provider status/body is never interpolated into UI text. A sanitized incident ref may be added to an unexpected 5xx response, but never credential/account values.

## Backward and forward compatibility

- Existing `/integrations/wildberries/**` paths and response models are byte-for-byte contractually unchanged.
- Existing S-32 WB testids, copy, dialog and actions remain unchanged. Ozon uses only new `seller-settings-ozon-*` testids.
- `frontend/src/api.ts` keeps existing `apiUrl` behavior; no marketplace abstraction or route remap is required.
- New self API is additive. Optional future status fields may be added nullable; existing fields cannot change meaning.
- Future multi-account may add collection/account-id routes and additional `account_slot` values after a separate product decision. S0 `primary` remains backward-compatible; current UI does not infer or expose multiplicity.
- No downstream table may store only seller+marketplace when it needs external identity; future mappings/orders/bindings should FK `marketplace_accounts.id`.

## BLOCKED/unchanged provider facts

- credential expiry: not in API/model/UI response;
- scopes/capability dashboard: not parsed or shown;
- account warehouse, delivery point, return point: no fields/controls;
- posting/package/label, GM/TGM, acts, stocks, catalog, orders: no call and no data mutation;
- real test-account write: forbidden;
- any nested `/v1/seller/info` field: ignored until separately proven.
