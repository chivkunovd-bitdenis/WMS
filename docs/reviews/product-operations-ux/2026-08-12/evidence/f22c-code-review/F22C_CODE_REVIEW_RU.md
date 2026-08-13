# F22C Code Review: seller catalog read-model fix

Дата: 2026-08-13
Роль: независимый Code Review Agent
Review commit: `5c1ab614e11c075543f95edac1361e70cdc1c1b2`
Verdict: `CODE_REVIEW_PASSED`

## Контекст

F22 browser QA провалился из-за расхождения между фактическим readback WB и seller UI: backend/WB подтвердили опубликованный остаток `7`, но seller catalog показывал ошибку. Диагноз dev agent: read-model каталога выбирал последнюю строку `FbsStockSyncItem` по паре seller + chrt без отсева нерелевантных bindings, поэтому более свежая safe-error из другой или уже неактуальной привязки могла перекрыть подтвержденный readback.

Ревью проводилось только по файлам:

- `backend/app/services/seller_wb_catalog_service.py`
- `backend/tests/test_fbs_stock_sync.py`

Код в рамках ревью не редактировался.

## Проверка по требованиям

### 1. Каталог учитывает только релевантные active/enabled bindings

Passed. В `_load_fbs_sync_state_by_seller_chrt` запрос теперь соединяет `FbsStockSyncItem` с `FbsWarehouseBinding` и фильтрует:

- `FbsWarehouseBinding.tenant_id == tenant_id`;
- `FbsWarehouseBinding.is_active.is_(True)`;
- `FbsWarehouseBinding.stock_sync_enabled.is_(True)`;
- `FbsStockSyncItem.chrt_id.in_(chrt_ids)`;
- при seller catalog дополнительно `FbsWarehouseBinding.seller_id == seller_id`.

Это убирает из read-model выключенные или неактивные warehouse bindings и сохраняет seller scope. Для FF-каталога без явного `seller_id` helper берет seller ids из уже tenant-scoped products и затем читает состояния только по этим sellers.

### 2. Confirmed readback с amount выигрывает у нерелевантной или stale error

Passed. Новый `_is_preferred_fbs_sync_state` сначала проверяет, является ли состояние подтвержденным readback: `status == confirmed` и `published_amount is not None`. Если один кандидат confirmed-with-amount, а другой нет, выбирается confirmed-with-amount независимо от `updated_at`. Только между равными классами состояний применяется выбор по более свежему `updated_at`.

Это прямо закрывает исходный сбой: свежая error без `last_confirmed_amount` больше не может вытеснить подтвержденное значение `7`, если подтвержденная строка пришла из активной включенной привязки.

### 3. Настоящая active safe error остается error без confirmed readback

Passed. Если confirmed-with-amount отсутствует, helper возвращает наиболее свежую active/enabled строку по `updated_at`. Тест `test_seller_catalog_keeps_active_safe_error_without_confirmed_readback` фиксирует, что active safe-error остается видимой как `fbs_sync_status == error`, а `fbs_published_amount` остается `None`.

### 4. Tenant/seller isolation

Passed. Tenant isolation держится на `FbsWarehouseBinding.tenant_id == tenant_id`, а seller isolation в seller catalog держится на `FbsWarehouseBinding.seller_id == seller_id` и lookup по ключу `(seller_id, chrt_id)`. Карточки WB также читаются отдельно по `SellerWildberriesImportedCard.seller_id == seller_id` и `tenant_id == tenant_id`, поэтому изменение не расширяет видимость карточек между продавцами.

Остаточный неblocking-риск: новые тесты покрывают inactive-binding override и active-error path, но не добавляют отдельный negative-case на другой tenant/seller с тем же `chrt_id`. По коду фильтры изоляции выглядят корректно; для будущей страховки можно добавить такой regression test в соседнем dev-проходе, если F22 станет зоной частых правок.

### 5. F22 safe-zero behavior не ослаблен

Passed. Commit не меняет `fbs_stock_sync_service.py`, где safe-zero блокируется до WB PUT: отсутствие FBS pool дает `ERROR_UNSAFE_STOCK_UNKNOWN`, явный ноль дает `ERROR_UNSAFE_ZERO_BLOCKED`, а stale published absent product не отправляется как автоматический PUT `0`. Существующие F22-тесты на эти ограничения остаются в том же файле и прошли при запуске.

Важно: изменение касается только read-model каталога, то есть того, что показывается пользователю в seller UI. Логика публикации остатков в WB не стала разрешать нули и не стала повторно отправлять старые chrt как `0`.

### 6. Тесты meaningful и pass

Passed. Новые тесты проверяют именно пользовательски важный read-model результат:

- `test_seller_catalog_prefers_active_confirmed_readback_over_irrelevant_error`: inactive binding с более свежей safe-error не перебивает active confirmed readback `7`;
- `test_seller_catalog_keeps_active_safe_error_without_confirmed_readback`: active safe-error остается ошибкой, если confirmed readback отсутствует.

Дополнительно сохраняются старые F22 safe-zero регрессии в `test_fbs_stock_sync.py`.

## Запущенные проверки

Из `backend/`:

```bash
pytest -q tests/test_fbs_stock_sync.py
```

Результат: `23 passed in 7.93s`.

```bash
pytest -q tests/test_product_fbs_stock_sync_api.py
```

Результат: `3 passed in 3.85s`.

Первый технический запуск был с неверным относительным путем `backend/tests/test_fbs_stock_sync.py` из каталога `backend/` и завершился `file or directory not found`; затем тест был перезапущен корректным путем `tests/test_fbs_stock_sync.py`.

## Итог

`CODE_REVIEW_PASSED`

Блокирующих замечаний по commit `5c1ab614e11c075543f95edac1361e70cdc1c1b2` не найдено. Изменение соответствует F22C-диагнозу: seller catalog больше не должен показывать нерелевантную safe-error вместо подтвержденного WB readback amount.
