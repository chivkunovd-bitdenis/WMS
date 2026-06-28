# Ревью: МУЛЬТИ-АРЕНДНОСТЬ / АВТОРИЗАЦИЯ / IDOR (ЧЗ-маркировка)

## Резюме
Диапазон 4e82c6b..HEAD. Проверены API маркировки, учётки, уведомления и сервисы.
Находок CRITICAL/HIGH: **0**. MEDIUM: **0**. LOW/INFO: **2** (обе — только в коде, гейтированном E2E-флагом, в проде не активны).
Измерение по сути **ЧИСТО**: tenant_id и seller-scope проведены последовательно во всех роутерах и сервисах; reprint реально гейтится `require_shift_lead` на бэке; IDOR по чужим id закрыт (объекты грузятся с проверкой tenant + seller).

---

## [LOW] E2E-сид уведомлений принимает произвольный recipient_id (только под WMS_AUTO_CREATE_SCHEMA)
- **Где:** backend/app/api/notifications.py:141-175 (эндпоинт `POST /operations/notifications/_e2e/seed`)
- **Доказательство:**
```python
if _E2E_SCHEMA:
    ...
    @router.post("/_e2e/seed", response_model=E2eSeedNotificationOut)
    async def e2e_seed_notification(...):
        if body.recipient_type == RECIPIENT_TYPE_USER:
            recipient_id = body.recipient_id or str(user.id)
        elif body.recipient_type == RECIPIENT_TYPE_SELLER:
            ...
            recipient_id = body.recipient_id or str(effective_seller_id)
        elif body.recipient_type == RECIPIENT_TYPE_FF_ROLE:
            recipient_id = body.recipient_id or FF_PORTAL_RECIPIENT_ID
        ...
        row = await notify_svc.notify(session, user.tenant_id, NotificationRecipient(body.recipient_type, recipient_id), ...)
```
- **Проблема:** клиент может подставить чужой `recipient_id` (любого user/seller внутри своего тенанта) и создать уведомление на чужой scope. Запись всё равно ограничена `user.tenant_id`, межтенантной утечки нет, и эндпоинт регистрируется только при `WMS_AUTO_CREATE_SCHEMA == "1"` (E2E/тест), поэтому в проде недоступен. Чтение этих уведомлений по-прежнему скоупится `recipient_scope_for_user`, так что отдать чужое нельзя — это лишь возможность «насыпать» уведомление чужому в рамках тенанта.
- **Фикс (по желанию, для строгости тестового стенда):** не доверять `body.recipient_id` от клиента — либо игнорировать его и всегда выводить из контекста (user.id / effective_seller_id / FF_PORTAL_RECIPIENT_ID), либо валидировать, что переданный seller/user принадлежит `user.tenant_id`. Низкий приоритет: код тест-онли.

---

## [INFO] Эндпоинты упаковки (`require_packaging_access`) видят все seller внутри тенанта
- **Где:** backend/app/api/marking_codes.py — `scan-print` (1054), `verify-pair` (1081), `pending-marking` (1104, принимает `seller_id` из query), `packaging-lines/{line_id}/print` (1140), `packaging-tasks/{task_id}/print-all` (1205), `packaging-task-lines/{line_id}/printed-codes` (1273), `codes/{code_id}/defect` (1296), все `reprint-requests/*` (1321-1417).
- **Доказательство:**
```python
@router.get("/pending-marking", response_model=PendingMarkingOut)
async def list_pending_marking(
    user: Annotated[User, Depends(require_packaging_access)],
    ...
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
) -> PendingMarkingOut:
    rows = await mc_svc.list_pending_marking_lines(session, user.tenant_id, warehouse_id=..., seller_id=seller_id)
```
- **Проблема:** это НЕ баг. `require_packaging_access` / `require_shift_lead` пускают только FULFILLMENT_ADMIN и FULFILLMENT_STAFF с соответствующим permission — роли склада, которые по дизайну работают по всем селлерам тенанта. `seller_id` здесь — фильтр, а не граница авторизации; роль seller сюда не попадает. Все нижележащие сервисы (`list_pending_marking_lines`, `scan_print_for_packaging_task`, `print_all_for_packaging_task`, `verify_pair_and_apply`, `create_defect_reprint_request`, `approve/replace/reject_reprint_request`) фильтруют по `tenant_id` и грузят PackagingTask/MarkingCode с проверкой `tenant_id`. Зафиксировано как INFO, чтобы было видно, что проверено и почему ок.

---

## Что проверено и почему ЧИСТО

### 1. tenant_id в каждом запросе к БД — ОК
- Все сервисные функции принимают `tenant_id` и фильтруют по нему:
  - `list_pools`/`_pool_status_counts`/`_products_by_pool`/`get_pool_detail`/`list_pool_codes` — `MarkingPool.tenant_id == tenant_id`, `MarkingCode.tenant_id == tenant_id`, `MarkingPoolProduct.tenant_id == tenant_id` (marking_code_service.py:1700+,1771,1830).
  - `list_ledger` — `MarkingCodeEvent.tenant_id == tenant_id` (1895), вложенный подзапрос product→pool тоже скоупится по tenant (1903).
  - `list_inventory` — Product/MarkingCode/MarkingPoolProduct все с `tenant_id` (984,996,1026).
  - `get_code_history`, `list_product_codes` — грузят MarkingCode/Product с проверкой `tenant_id` (1952,1067).
  - reprint: `_get_pending_reprint_request` (2124-2126), `approve/replace/reject` — `req.tenant_id != tenant_id` → 404; связанные code/line/task все перепроверяются по tenant (2150-2158,2191-2202).
  - `verify_pair_and_apply` — `MarkingCode.tenant_id == tenant_id` (2329).
  - Уведомления: `_scope_filter` всегда добавляет `Notification.tenant_id == tenant_id` (notification_service.py:67-68); list/count/mark_read/mark_all_read/get_for_scope все идут через него.
  - Учётки: `_seller_in_tenant` (seller_marking_credentials_service.py:59-65) гейтит get/patch/decrypt по `seller.tenant_id == tenant_id`.

### 2. Селлер видит/меняет только свой seller_id — ОК
- `tenant_id` и эффективный seller всегда берутся из токена/контекста (`get_current_user`, `get_effective_seller_id` → `resolve_effective_seller_id` в deps.py:34-66), а делегирование к чужому seller проходит через `assert_can_act_as_seller`.
- Везде, где роль seller, входной `seller_id` из query/body/form ИГНОРИРУЕТСЯ и заменяется на `effective_seller_id`:
  - `import/preview`, `import` (marking_codes.py:436-446,494-504), `create_print_template` (984-991), `inventory` (868-871), `list_product_marking_codes` (901-908, плюс проверка `product.seller_id == effective_seller_id`), `_resolve_marking_seller_scope` для ledger/pools/templates (393-404), `_assert_pool_access` для pool detail/codes/products/threshold/history (379-390).
  - `self/credentials` GET/PATCH (marking_credentials.py:239-264,285-316) используют только `effective_seller_id`, никогда не путь/боди.
- Привязка продуктов к пулу валидируется на принадлежность селлеру: `_validate_pool_products` → `product.seller_id != seller_id → product_seller_mismatch` (marking_code_service.py:497-515), вызывается из import (867), set/add pool products (549,592).

### 3. shift_lead реально гейтит reprint — ОК (бэк-гейт)
- `require_shift_lead = require_ff_permission(PERM_SHIFT_LEAD)` (deps.py:210, 157-175). Пускает только FULFILLMENT_ADMIN или FULFILLMENT_STAFF с правом `shift_lead` (проверка прав из БД через `get_staff_permissions`), иначе 403.
- Все resolve-эндпоинты перепечатки зависят от `require_shift_lead`:
  - `GET /reprint-requests` (marking_codes.py:1323)
  - `POST /reprint-requests/{id}/approve-reprint` (1373)
  - `POST /reprint-requests/{id}/replace` (1388)
  - `POST /reprint-requests/{id}/reject` (1404)
- Гейт на бэке, не обходится фронтом. Создание заявки на перепечатку (`/codes/{id}/defect`) гейтится `require_packaging_access` (упаковщик создаёт заявку, старший смены одобряет) — корректное разделение по дизайну.

### 4. IDOR по чужим id — закрыт
- pool_id: `set_pool_products`/`set_threshold`/`get_marking_pool`/`list_pool_codes` грузят пул и проверяют `pool.tenant_id != user.tenant_id` (404) + `_assert_pool_access(pool.seller_id, effective_seller_id)` ДО вызова сервиса (marking_codes.py:601-603,627-629,671-673,720-722).
- code_id: `get_marking_code_history` — `code.tenant_id != user.tenant_id` (404) + `_assert_pool_access(code.seller_id, ...)` (801-804); `create_defect_reprint_request` — `code.tenant_id != tenant_id` (service 2037).
- request_id: `_get_pending_reprint_request` — `req.tenant_id != tenant_id` → 404 (2124-2126).
- notification_id: `get_notification_for_scope` фильтрует `id == ... AND _scope_filter(tenant, scopes)` — чужой id вернёт None → 404 (notifications.py:106-110).
- product_id: `list_product_marking_codes` для seller проверяет `product.seller_id == effective_seller_id` (907-908).
- template_id: update/delete грузят PrintTemplate, проверяют `tenant_id` + `_assert_template_seller_access` (1017-1020,1044-1047).
- Нигде «голый» `session.get(id)` не отдаётся клиенту без последующей проверки tenant (и seller, где нужно).

### 5. Учётки маркировки (секреты) — ОК
- `GET/PATCH /sellers/{seller_id}/credentials` гейтятся `require_fulfillment_admin` (marking_credentials.py:229,271) и скоупятся `user.tenant_id` через `_seller_in_tenant`; чужой/несуществующий seller → 404 `seller_not_found`, межтенантного чтения нет.
- Секреты НИКОГДА не отдаются: ответ — только маски `has_cz_token`/`has_suz_oms_token`/`has_mp_api_key` (`_row_to_public`, service:86-99). Расшифровка только в `get_decrypted_credentials_for_seller` (для интеграционных джоб), тоже за `_seller_in_tenant`.
- `self/credentials` затирает `seller_id=None` в ответе, чтобы селлер даже не узнал свой внутренний id (marking_credentials.py:251-264,303-316).
