Локально реализовано и сохранено в Git, но не опубликовано: push заблокирован отсутствием DNS-доступа к `github.com`.

В оба `pick-options` добавлено поле `sources`:

```json
{
  "storage_location_id": "uuid",
  "location_code": "СТЕЛЛАЖ 1.1",
  "quantity": 14,
  "reserved": 0,
  "available": 14,
  "picked": 0,
  "sources": [
    {
      "quantity": 4,
      "is_loose": false,
      "source_label": "Короб КР-000041",
      "container_path": [
        {
          "kind": "pallet",
          "id": "uuid",
          "code": "П-000131",
          "label": "Палета П-000131"
        },
        {
          "kind": "box",
          "id": "uuid",
          "code": "КР-000041",
          "label": "Короб КР-000041"
        }
      ]
    }
  ]
}
```

Точные новые поля:

- `sources[].quantity` — количество товара в конкретном физическом источнике;
- `sources[].is_loose` — `true`, если товар лежит россыпью;
- `sources[].source_label` — готовая подпись: `Россыпью`, `Палета …`, `Короб …`, `Грузоместо …`;
- `sources[].container_path` — путь тары снаружи внутрь;
- `container_path[].kind` — `pallet`, `box` или `cargo_place`;
- `container_path[].id`, `code`, `label` — UUID, человеческий номер и готовое название.

Короб и грузоместо на палете возвращаются двумя ступенями. Для россыпи `container_path: []`. Служебный `__SORTING__` заменяется в `location_code` на `Без ячеек`. Неразрешимая или чужая тара даёт `409 invalid_container_reference`.

Все прежние поля сохранены. Их агрегированные значения не распределяются по таре, поэтому действующий экран не получит удвоенные `quantity`, `reserved`, `available` или `picked`. Общая реализация находится в [pick_option_location_service.py](/Users/deniscivkunov/Projects/WMS/.worktrees/codex-tara/backend/app/services/pick_option_location_service.py:27), API-контракты — в [marketplace_unload_requests.py](/Users/deniscivkunov/Projects/WMS/.worktrees/codex-tara/backend/app/api/marketplace_unload_requests.py:224) и [fbs_supplies.py](/Users/deniscivkunov/Projects/WMS/.worktrees/codex-tara/backend/app/api/fbs_supplies.py:171).

Проверено:

- 10 целевых тестов — прошли;
- `ruff check .` — прошёл;
- `mypy .` — прошёл, 388 файлов;
- полный pytest, npm и Playwright не запускались;
- `frontend/` в коммит не попал.

Git:

- ветка: `codex/pick-containers-20260829`;
- commit: `ae9b407ecc0244edfb26e68cd84e9a12b45b8af9`;
- pushed: нет — `Could not resolve host: github.com`;
- deployed: нет;
- browser-tested: нет — экран ещё не подключён к новым полям, поэтому product browser gate имеет статус `PRODUCT_BROWSER_BLOCKED`.

Чужие незакоммиченные изменения в `backend/app/api/warehouses.py` и нижней части `warehouse_map_service.py` сохранены и в этот коммит не включены.

| Метрика | Количество |
|---|---:|
| total_cards | 1 |
| ba_ready | 1 |
| product_approved_for_dev | 1 |
| dev_done | 1 |
| code_review_passed | 1 |
| product_browser_approved | 0 |
| product_browser_blocked | 1 |
| integrated | 0 |
| final_regression_passed | 0 |