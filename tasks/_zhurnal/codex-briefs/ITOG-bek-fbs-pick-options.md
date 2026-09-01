Локально реализовано и сохранено в Git, но ветка не опубликована: `git push` не прошёл из-за недоступности DNS для `github.com`.

Контракт для фронтенда:

```http
GET /operations/fbs-supplies/{supply_id}/pick-options
Authorization: Bearer …
```

Права те же, что у остальных ручек подбора ФБС — `require_fbs_operator_access`.

Ответ полностью совпадает с формой отгрузки:

```json
[
  {
    "product_id": "uuid",
    "sku_code": "SKU-001",
    "product_name": "Название товара",
    "planned_qty": 3,
    "picked_qty": 1,
    "locations": [
      {
        "storage_location_id": "uuid",
        "location_code": "A-01-02",
        "quantity": 5,
        "reserved": 1,
        "available": 4,
        "picked": 1
      }
    ]
  }
]
```

Значения:

- `planned_qty` — количество единиц товара в заказах поставки;
- `picked_qty` — суммарное число активных подборов товара;
- `quantity` — физический остаток в месте;
- `reserved` — резерв в этом месте;
- `available` — доступно после резерва, минимум `0`;
- `picked` — сколько активных записей `FbsOrderPick` снято именно из этой ячейки;
- отменённые подборы с заполненным `undone_at` не учитываются;
- исходная ячейка с остатком `0` остаётся в `locations`, если из неё есть активный подбор;
- пустая поставка возвращает `[]`;
- чужая или несуществующая поставка возвращает `404 supply_not_found`.

Реализация: [fbs_picking_service.py](/Users/deniscivkunov/Projects/WMS/.worktrees/codex-fbspick/backend/app/services/fbs_picking_service.py:142), схема и ручка: [fbs_supplies.py](/Users/deniscivkunov/Projects/WMS/.worktrees/codex-fbspick/backend/app/api/fbs_supplies.py:1110).

Проверки:

- новый точечный pytest: `5 passed`;
- `ruff check .` — зелёный;
- `mypy .` — `Success: no issues found in 387 source files`;
- полный pytest, npm и Playwright не запускались;
- `frontend/` не изменялся.

Коммит: `9a867a4512e3236825098bb01ce305a8726d54a0`  
Ветка: `codex/fbs-pick-options-20260829`

Для публикации при восстановлении сети:

```bash
git push -u origin codex/fbs-pick-options-20260829
```

CI, merge и деплой не выполнялись.

