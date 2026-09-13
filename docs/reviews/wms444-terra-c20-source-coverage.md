# WMS-444 — C20: source-class coverage for absolute `pick/set`

13.09.2026. Исправление подготовлено поверх независимого замечания Astra `615795da1f4f1f3efe38c0f61b9dd3a28767788f`. Это отчёт исполнителя: он не заменяет повторное Astra review, BA-приёмку, проверку веб-интерфейса или деплой.

## Инвариант и изменение

Коробочный состав покрывается оставшимися allocation отдельно в трёх физических source-классах:

- proven packed;
- proven known-unpacked;
- historical unknown.

`_trim_box_lines_to_remaining_pick` больше не использует только общий предел `boxed <= picked`. Для каждого класса он снимает `max(0, boxed_class - picked_class)`. Поэтому allocation unpacked, ещё не разложенная в короб, не оставляет в коробе уже возвращённую packed или unknown единицу. Сумма снятий классов может быть больше общего `boxed - picked`: оставшийся подбор другого класса законно остаётся вне коробов. Корректировка коробов не создаёт второй возврат stock.

После такого снятия упаковочный факт сначала возвращается к persisted historical baseline. Это нужно для случая, когда после удаления known части остаётся только historical unknown: существующий box sync намеренно не переписывает факт для полностью unknown короба. Затем обычная синхронизация добавляет только известную часть, которая действительно ещё находится в коробе. R13 меняет baseline только на `unknown_removed`.

Новых API, UI, операторских ограничений, сущностей, миграций или изменений требований нет.

## Локальная матрица

`backend/tests/test_wms444_historical_provenance.py` теперь покрывает публичный service-путь `set_pick_allocation` с независимыми классами:

- boxed packed2 и unboxed known-unpacked2: `set packed=0` убирает packed короб, но сохраняет allocation unpacked;
- boxed packed2 + historical unknown1 и unboxed known-unpacked1: `set packed=0` оставляет только unknown1, historical baseline `1/0`, без ложного `insufficient_picked`;
- boxed known-unpacked2 и unboxed historical unknown2: `set known-unpacked=0` очищает короб, но оставляет unknown allocation;
- boxed historical unknown2 и unboxed known-unpacked1: уменьшение снимает только непокрытый unknown1 и применяет R13 `ready1/work1 → ready1/work0`.

Во всех случаях проверяются source-preserving box/allocation остатки и ровно один stock return по `delta`.

## Проверка

Выполнено локально:

- `pytest -q tests/test_wms444_historical_provenance.py tests/test_marketplace_unload_box_source.py tests/test_marketplace_unload_pick_from_container.py` — **13 passed**;
- `ruff check .` — **passed**;
- `mypy .` — **Success: no issues found in 445 source files**.

Исходная Astra-проба `wms444_c20_review.py` выполнена с явным `DATABASE_URL` только в новой isolated PostgreSQL БД `wms444_terra_c20_classes3_20260913`.

- исходный C20: `box 3→2→0→0`, stock `0→1→3→3`; новый unpacked pick даёт `ready0/work1`, complete начисляет **700** копеек;
- reviewer case A: после `set packed=0` — `alloc2/packed0`, `box0`, stock `2/packed2`, один дополнительный movement;
- reviewer case B: операция успешна, после `set packed=0` — `alloc2/packed0`, `box1/packed0/known0`, `ready1/work0`, stock `2/packed2`, один дополнительный movement.

Shared DB/runtime/API, внешние площадки, Gradle и устройства не использовались. Release: commit и push будут сообщены при передаче на повторное focused Astra review; деплой не выполнялся.
