# Browser evidence · 06-picking-list-order

Дата: 2026-08-23.

Проверен один целевой Chromium-сценарий:

```text
npx playwright test ff-fbs-supply.spec.ts \
  -g "full tape keeps packing name order but previews server tape order"
1 passed (7.2s)
```

Сценарий намеренно задаёт два разных порядка. Видимые строки упаковки остаются в
прежнем порядке по названию: `Альфа -> Яблоко`. Предпросмотр полной ленты и
`order_ids` запроса используют серверный порядок: `Яблоко -> Альфа`. Mock ответа
печати возвращает заранее заданный серверный порядок и не повторяет порядок
запроса.

Скриншот живого Chromium перед подтверждением печати:
`full-tape-preview-order.png`.

## Инварианты геометрии

В этом же состоянии выполнен `scripts/ui/invariants.js`:

```json
{
  "ok": false,
  "count": 3,
  "violations": [
    {"rule": "R-36", "sample": "Склад селлера / WB"},
    {"rule": "R-36", "sample": "Создан WB / в сборке"},
    {"rule": "R-32", "sample": "34/40"}
  ]
}
```

Все три нарушения относятся к существующему фоновому списку поставок и
унаследованной панели действий. Финальный diff карточки не меняет их JSX, layout
или ui-kit. В новой зоне порядка ленты наползаний, обрезки или нового окрашивания
строк не обнаружено.

## Остальные подтверждения

- `ruff` по затронутым Python-файлам: зелёный.
- `backend/tests/test_fbs_packaging_integration.py`: `24 passed`.
- TypeScript: зелёный.
- Frontend unit: `138 passed`.
- Независимый Sol-review: `ВЕРДИКТ: ЧИСТО` в `REVIEW-FINAL.md`.
