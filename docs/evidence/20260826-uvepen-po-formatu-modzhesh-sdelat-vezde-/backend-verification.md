# Доказательства · WB-совместимые ШК коробов

Дата проверки: 26.08.2026.

## Проверка результата

Целевой набор охватывает общий генератор, все три места создания физических коробов,
API-ответы, уникальность серии, старые сохранённые форматы и FBS idempotency key.

```text
31 passed in 11.67s
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
FBS FBS-0QHE55NHAS9AK8ZXJAK64723YX 30 True
```

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
