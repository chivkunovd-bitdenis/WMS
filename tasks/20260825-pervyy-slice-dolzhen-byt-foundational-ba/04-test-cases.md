# CALL74 · Behavior-focused test contract

Все provider interactions в тестах fake/contract-only. Ни один test не использует настоящий Client-Id/Api-Key, сеть Ozon или mutation endpoint. Playwright проверяет видимую работу пользователя, backend tests — permission/tenant/data/API semantics, migration test — совместимость. TC IDs должны быть упомянуты в test title или comment.

## Traceability

| TC-ID | Layer | User-visible or safety outcome |
|---|---|---|
| TC-S32-OZON-001 | Playwright + API | Authorized seller connects Ozon inside existing S-32. |
| TC-S32-OZON-002 | Playwright + API | Missing Client-Id/Api-Key is blocked before provider call. |
| TC-S32-OZON-003 | API | Invalid candidate does not replace existing connection. |
| TC-S32-OZON-004 | API | Provider outage is distinct from invalid credentials. |
| TC-S32-OZON-005 | API + service | PUT and DELETE are idempotent. |
| TC-S32-OZON-006 | API | Permission boundary matches current seller `settings`. |
| TC-S32-OZON-007 | API + service | Tenant/seller isolation is fail-closed. |
| TC-S32-OZON-008 | Service + API | Api-Key is encrypted and no secret/account value is output or logged. |
| TC-S32-OZON-009 | Client contract | Connection validation is read-only and mutation-free. |
| TC-S32-OZON-010 | Playwright + API | Manual test exposes valid/invalid/unavailable states with exact words. |
| TC-S32-OZON-011 | Playwright | Disconnect confirmation stays inline and returns card to disconnected state. |
| TC-S32-OZON-012 | Playwright regression | WB and Честный Знак behavior remain unchanged; no new screen/tab/modal. |
| TC-S32-OZON-013 | Migration | Additive migration preserves WB data and supports downgrade/re-upgrade. |
| TC-S32-OZON-014 | API/schema | Public response never exposes hidden account multiplicity or unsupported facts. |

## TC-S32-OZON-001 — подключение в существующем S-32

**Given** seller owner or seller staff has effective seller and permission `settings`, no primary Ozon account exists, fake `POST /v1/seller/info` returns 2xx.  
**When** user opens `/seller/settings`, fills `Client-Id` and password `Api-Key` in `seller-settings-ozon-card`, and clicks `Подключить`.  
**Then** the browser stays on `/seller/settings`; card shows `Подключено` and last validation time; both inputs are cleared; exactly one primary Ozon account exists; no account selector, dashboard, sync action or external mutation is visible.  
**Expected restriction:** WB-card and Честный Знак remain visible with their existing copy/actions/testids.

## TC-S32-OZON-002 — обязательные поля

**Given** authorized seller sees disconnected Ozon card and provider fake counts calls.  
**When** user submits with missing/whitespace `Client-Id`, then with missing/whitespace `Api-Key`.  
**Then** field-level text is respectively `Введите Client-Id.` and `Введите Api-Key.`; provider call count remains zero; database row count remains zero.  
**Negative:** unknown request fields, wrong types and over-limit values return 422 without echoing the rejected values.

## TC-S32-OZON-003 — неверная candidate-пара не ломает рабочую

**Given** an active primary account contains working encrypted credentials and public status `valid`; fake read-only validator returns 401/403 for a replacement candidate.  
**When** user chooses `Заменить данные` and submits the candidate.  
**Then** UI says `Ozon не подтвердил Client-Id и Api-Key. Проверьте оба значения.`; stored ciphertext/external account id/status/timestamps for the working pair are unchanged; response contains no candidate or stored values.  
**Negative:** first-time invalid candidate creates no account row.

## TC-S32-OZON-004 — временная недоступность не равна неверному ключу

**Given** a valid stored connection or first-time candidate and validator produces timeout, network error, 429 or 5xx.  
**When** save or manual test runs.  
**Then** API maps it to `ozon_validation_unavailable`; UI shows `Не удалось проверить подключение Ozon. Сохранённые данные не изменены; попробуйте ещё раз.`  
**Expected:** failed candidate save preserves old record entirely; failed manual test preserves ciphertext and sets only stored status/error/time to `unavailable` with safe code. Provider response body is not returned.

## TC-S32-OZON-005 — idempotent create/update/delete

**Given** two sequential or concurrent authorized PUTs carry the same normalized pair and fake validation succeeds.  
**When** requests finish.  
**Then** unique primary key scope contains one row, same account id and one ciphertext; identical replay does not move `credentials_updated_at`; public responses are equivalent.  
**When** DELETE is sent twice.  
**Then** both calls return 204; ciphertext is null, account inactive, one disconnect audit remains, and no provider call occurs.  
**Negative:** different valid replacement is last-writer-wins under row/seller lock and never creates a second `primary` row.

## TC-S32-OZON-006 — permission boundary

**Given** fixtures for unauthenticated user, fulfillment admin, seller staff with `settings=false`, seller staff with `settings=true`, and seller owner.  
**When** each calls GET/PUT/POST-test/DELETE self routes and opens S-32.  
**Then** unauthenticated is 401; FF admin and no-settings seller are 403 and Ozon card is not available; settings-enabled seller and owner can perform all four actions.  
**Restriction:** no new role or permission is created; stock permissions are irrelevant.

## TC-S32-OZON-007 — tenant и seller isolation

**Given** tenant A/seller A has Ozon credentials and tenant B/seller B is authenticated.  
**When** B calls every self route, manipulates payloads, or an internal service is invoked with mismatched `tenant_id/seller_id`.  
**Then** B can only read/change B primary row; A ciphertext/status/audit are byte-for-byte unchanged; service returns not-found/fail-closed for mismatch.  
**Negative:** self API accepts no seller id, account id or slot capable of selecting A.

## TC-S32-OZON-008 — encryption and no-secret-output

**Given** known fake values `client-id-canary` and `api-key-canary`, success validation and captured DB/API/log output.  
**When** connection is saved, read, tested, fails once, and disconnected.  
**Then** plaintext Api-Key never appears in DB ciphertext, responses, OpenAPI response schemas, logs, exceptions or snapshots; Client-Id never appears in public responses/logs; decrypting only inside service reproduces Api-Key before disconnect; after disconnect ciphertext is null.  
**Negative:** provider response body containing a canary is ignored and absent from output/logs.

## TC-S32-OZON-009 — read-only validation and zero mutations

**Given** fake HTTP transport records method/path/body/headers and fails any request outside the allowlist.  
**When** PUT validation and POST test-connection execute.  
**Then** each user action makes at most one `POST /v1/seller/info` with `{}` and the two auth headers; redirects across host are not followed; no stock/product/order/supply/label/ship/cancel endpoint is called; no background task is enqueued.  
**Restriction:** assert credential values at the fake transport boundary without printing them in failure output.

## TC-S32-OZON-010 — visible manual-check states

**Given** connected card and fake validator scenarios 2xx, 401, timeout/429/5xx.  
**When** user clicks `Проверить подключение` once per scenario.  
**Then** button is disabled with `Проверяем…` while pending; success shows `Подключено` and time; 401 shows exact invalid text; temporary failures show exact unavailable text.  
**Expected:** raw status, response body, Client-Id and Api-Key are never visible; actions to retry/replace remain present.

## TC-S32-OZON-011 — отключение без нового modal

**Given** connected account.  
**When** user clicks `Отключить`.  
**Then** confirmation `Отключить Ozon от этого селлера?` appears inline inside the same card; `Отмена` restores connected summary; confirm calls DELETE and renders disconnected inputs plus `Ozon отключён.`  
**Negative:** no MUI Dialog, browser navigation or provider call occurs.

## TC-S32-OZON-012 — WB regression and unchanged zones

**Given** current `seller-settings.spec.ts` WB flow and S-32 with permission `settings`.  
**When** seller saves/syncs WB through existing controls and independently interacts with Ozon card.  
**Then** existing testids `seller-settings-wb-card`, `seller-settings-add-key`, `seller-settings-key-dialog`, `seller-settings-key-input`, `seller-settings-save`, `seller-settings-sync-products` retain current copy, enablement and endpoints; Честный Знак testids/actions remain unchanged.  
**Expected layout:** Ozon is one Paper between WB and Честный Знак at the same width; route/shell/nav/staff panel unchanged; no new page/tab/modal/workspace exists.

## TC-S32-OZON-013 — migration compatibility

**Given** database upgraded through `20260823_0100` with one seller, encrypted WB credential row and its status fields.  
**When** `20260825_0101` upgrades.  
**Then** `marketplace_accounts` and exact constraints/indexes exist; WB row and existing tables are unchanged.  
**When** migration downgrades and re-upgrades.  
**Then** only the new table disappears/reappears; WB row remains byte-for-byte equivalent; model metadata can create the new schema in SQLite E2E.  
**Negative:** migration contains no credential backfill, decrypt/encrypt loop or provider call.

## TC-S32-OZON-014 — schema compatibility and hidden multiplicity

**Given** disconnected, valid, invalid and unavailable account rows.  
**When** authorized GET/PUT/test responses are serialized.  
**Then** response keys exactly match public status contract; `id`, slot, seller/tenant ids, external id, credential/ciphertext and provider body are absent; expiry/capabilities are absent.  
**Expected forward rule:** null `last_synced_at/last_sync_error` stay hidden in UI; account collection/selector is not exposed in S0.

## Required local gates after developer implementation

- Backend focused first: `pytest backend/tests/test_marketplace_account_service.py backend/tests/test_ozon_integration_api.py backend/tests/test_marketplace_accounts_migration.py backend/tests/test_wildberries_tokens_api.py`.
- Backend full gate from `backend/`: `ruff check . && mypy . && pytest`.
- Frontend focused: existing and extended `frontend/tests-e2e/seller-settings.spec.ts` with fake Ozon transport only.
- Frontend full gate from `frontend/`: `npm run build && npm run test:e2e`.
- Browser product review must use live visible S-32 and record role, URL, clicks and states. It must explicitly verify WB unchanged and no new screen/tab/modal. Automated Playwright does not replace that gate.
