Локально реализовано и сохранено в Git-коммите `140d9c1107c2d880578869a42de7d985c17814c2` на ветке `codex/cargo-place-lines-20260829`. Опубликовать ветку не удалось: среда не смогла разрешить `github.com`, поэтому remote пока не обновлён.

Добавлены ручки в [inbound_intake.py](/Users/deniscivkunov/Projects/WMS/.worktrees/codex-gm/backend/app/api/inbound_intake.py:981):

- `POST /operations/inbound-intake-requests/{request_id}/cargo-places/{place_id}/scan`

  Тело: `{"barcode": "SKU-or-WB-barcode", "product_id": "uuid | null"}`. `product_id` необязателен. Сканирование прибавляет ровно одну штуку.

- `PUT /operations/inbound-intake-requests/{request_id}/cargo-places/{place_id}/lines/{product_id}`

  Тело: `{"quantity": 0..100000}`. Количество абсолютное; `0` удаляет строку.

Обе ручки возвращают грузоместо целиком:

```json
{
  "id": "uuid",
  "place_number": 1,
  "internal_barcode": "ICG-...",
  "label_printed_at": "ISO-8601 | null",
  "created_at": "ISO-8601",
  "remaining_qty": 8,
  "lines": [
    {
      "id": "uuid",
      "product_id": "uuid",
      "sku_code": "SKU-...",
      "product_name": "Название",
      "quantity": 8,
      "posted_qty": 0,
      "remaining_qty": 8
    }
  ]
}
```

Строки теперь также присутствуют внутри `cargo_places` при обычном `GET` приёмки. Проверяются принадлежность товара приёмке, нижняя граница по `posted_qty`, уникальность строки и изоляция арендаторов. Понятные ошибки: `product_not_on_request` и `actual_below_posted` — 422, неизвестный штрихкод — 404 `barcode_unknown`, чужая приёмка/грузоместо — 404.

`open` и `close` сознательно не добавлял: у модели грузоместа нет состояния открытия или закрытия, поэтому такие ручки создавали бы фиктивный жизненный цикл.

Тесты: четыре API-сценария покрывают создание, изменение без дубля, сканирование, удаление нулём, оба негативных ограничения и чужого арендатора. Результаты: `4 passed`, `ruff check .` и `mypy .` зелёные. Полный pytest, npm и Playwright не запускались. Миграций и изменений `frontend/` нет.

Для публикации ветки остаётся выполнить:

```bash
git push -u origin codex/cargo-place-lines-20260829
```

