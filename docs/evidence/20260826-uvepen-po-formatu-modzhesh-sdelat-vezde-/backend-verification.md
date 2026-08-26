# Доказательства · WB-совместимые ШК коробов

Дата проверки: 26.08.2026.

## Проверка результата

Целевой набор охватывает общий генератор `WHB`/`INB`, API-ответы, уникальность серии
и старые сохранённые форматы. FBS строго исключён из изменения.

```text
30 passed in 44.21s
```

Ruff по всем изменённым Python-файлам:

```text
All checks passed!
```

Mypy для нового общего модуля:

```text
Success: no issues found in 1 source file
```

Примеры реально сгенерированных значений:

```text
WHB WHB-3N5DWWDH3T8WG9HXM05MTXTEB6 30 True
INB INB-6BHHZQ5RSF9A3RMMZ4J0EAABA6 30 True
```

Проверка отсутствия изменений FBS относительно `origin/etalon`:

```text
git diff origin/etalon -- \
  backend/app/services/fbs_packing_box_service.py \
  backend/tests/test_fbs_packing_box.py
# пустой вывод
```

Получение и печать официальных QR грузомест и QR поставки FBS не изменялись.

## Полный backend-гейт

Полный `ruff check .` не прошёл: 69 ошибок в несвязанных существующих файлах.

Полный `mypy .` не прошёл: 19 ошибок в четырёх несвязанных существующих файлах.

Полный `pytest -q` завершился так:

```text
6 failed, 1042 passed, 5 skipped, 9 warnings in 1413.96s (0:23:33)
```

Упавшие тесты:

- `test_exported_fbs_openapi_file_matches_live_schema` — экспорт OpenAPI не содержит уже
  существующий route `boxes-without-distribution`.
- `test_fbs_cutoff_autoplans_supply_manual_date_and_calendar` — тестовая дата 15.08.2026
  стала прошедшей относительно текущей даты.
- `test_marketplace_unload_pick_set_allocation_increase_decrease_zero` — `MissingGreenlet`.
- `test_marketplace_unload_pick_allocations_admin_only` — `MissingGreenlet`.
- `test_marketplace_unload_packaging_one_row_per_product_across_cells` — `MissingGreenlet`.
- `test_marketplace_unload_box_remove_copy_delete` — `MissingGreenlet`.

Ни одно падение не проходит через изменённый генератор ШК. По правилам проекта общий
красный гейт всё равно блокирует живую браузерную приёмку и релизный статус.

## Повторное code review · 27.08.2026

Сильная изолированная модель нашла и после rework перепроверила два тестовых дефекта:

- e2e ожидал старый `INB-` + 12 hex-символов;
- mocked lookup не доказывал сканирование старых сохранённых ШК.

После rework regex точно проверяет 128-битный суффикс
`[0-7][0-9A-HJKMNP-TV-Z]{25}`, а старые `WHB-ABCDEF123456` и
`INB-ABCDEF123456` реально сохраняются в SQLite и проходят production
`attach_existing_box_by_barcode`.

```text
22 passed in 1.02s
Ruff: All checks passed!
CODE_REVIEW_PASSED
```
