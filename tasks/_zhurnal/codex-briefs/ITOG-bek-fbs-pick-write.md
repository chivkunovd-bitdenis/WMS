Локально реализовано и сохранено в Git, но ветка не опубликована: `git push` не прошёл из-за недоступного DNS GitHub (`Could not resolve host: github.com`).

Контракт для подключения экрана:

### Задать итоговое количество

```http
POST /operations/fbs-supplies/{supply_id}/pick/set
Idempotency-Key: <необязательный ключ повтора>
Content-Type: application/json
```

```json
{
  "product_id": "uuid",
  "storage_location_id": "uuid",
  "quantity": 2
}
```

Ответ:

```json
{
  "id": "uuid",
  "product_id": "uuid",
  "sku_code": "SKU-1",
  "product_name": "Товар",
  "storage_location_id": "uuid",
  "location_code": "A-01",
  "quantity": 2
}
```

`quantity` — итог, не прибавка. Увеличение распределяется по ожидающим заказам через существующий `/pick/manual`; уменьшение снимает последние назначения через существующий `undo`. При выключенном адресном хранении поля места в ответе равны `null`.

### Сканировать место или товар

```http
POST /operations/fbs-supplies/{supply_id}/pick/scan
Idempotency-Key: <необязательный ключ повтора>
Content-Type: application/json
```

```json
{
  "barcode": "4600000000000",
  "product_id": "uuid или отсутствует",
  "storage_location_id": "uuid, null или отсутствует"
}
```

Если распознано место:

```json
{
  "kind": "location",
  "storage_location_id": "uuid",
  "location_code": "A-01",
  "product_id": null,
  "sku_code": null,
  "product_name": null,
  "picked_qty": null,
  "allocation_quantity": null
}
```

Если распознан товар:

```json
{
  "kind": "product",
  "storage_location_id": "uuid или null",
  "location_code": "A-01 или null",
  "product_id": "uuid",
  "sku_code": "SKU-1",
  "product_name": "Товар",
  "picked_qty": 1,
  "allocation_quantity": 1
}
```

Повтор с тем же `Idempotency-Key` не создаёт второе назначение. Без заголовка существующий экран также работает. Товар без видимой ячейки подбирается через виртуальную зону «Сортировка», включая товар в таре без ячейки.

Превышение потребности возвращает HTTP 409 с кодом `pick_quantity_exceeds_demand` и контекстом `requested`/`maximum`. Чужой арендатор получает HTTP 404 `supply_not_found`.

Код находится в [fbs_supplies.py](/Users/deniscivkunov/Projects/WMS/.worktrees/codex-fbswrite/backend/app/api/fbs_supplies.py:1180), логика — в [fbs_picking_service.py](/Users/deniscivkunov/Projects/WMS/.worktrees/codex-fbswrite/backend/app/services/fbs_picking_service.py:356), проверки — в [test_fbs_pick_unload_contract.py](/Users/deniscivkunov/Projects/WMS/.worktrees/codex-fbswrite/backend/tests/test_fbs_pick_unload_contract.py:111).

Проверено:

- новые точечные тесты: 7 passed;
- связанные старые FBS/OpenAPI-тесты: 13 passed;
- `ruff check .` — зелёный;
- `mypy .` — зелёный;
- полный pytest, npm и Playwright не запускались;
- `frontend/` не изменён.

Commit: `3ef9d68998b7f5e57668385a0ad0dc78b269c582`  
Ветка: `codex/fbs-pick-write-20260829`

Для публикации, когда GitHub снова доступен:

```bash
git push -u origin codex/fbs-pick-write-20260829
```

