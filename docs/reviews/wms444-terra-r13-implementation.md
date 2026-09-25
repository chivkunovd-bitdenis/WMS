# WMS-444 — реализация R13/C19/C20

Реализовано в продолжение `2670639f` и WIP `b9c3696`: корректировка
historical-части при штатном уменьшении состава короба и обнуление факта
упаковки при последнем удалении.

## Инварианты полей

`MarketplaceUnloadBoxLine.quantity` и
`MarketplaceUnloadPickAllocation.quantity` — физическое количество.
`quantity_packed` содержит только доказанно готовую долю нового known-source,
а `quantity_source_known` — количество единиц с доказанным источником. `NULL`
у исторической строки не превращается в доказательство при переносе между
allocation и box.

`PackagingTaskLine.qty_legacy_confirmed_packed` и
`qty_legacy_packed_in_task` — один сохранённый расчёт historical unknown
части. При снятии `d` исторических единиц с текущим
`H = legacy_ready + legacy_work` сервис сохраняет старый ready-first расчёт:
`remaining = H - d`, `ready = min(legacy_ready, remaining)`,
`work = remaining - ready`. Это не меняет physical source. Когда box line для
товара больше нет, факт и legacy baseline сбрасываются в ноль; последующий
доказанный подбор формирует только новый результат.

## Проверка

На изолированной тестовой БД выполнено:

- `pytest -n 1 tests/test_wms444_historical_provenance.py tests/test_packaging_tasks.py -k 'historical_provenance or mp_box_packaging_uses_source_captured_in_box or mp_unload_pack_counter_without_inventory'` — 7 passed.
- C19: historical ready1/work1 плюс fresh unpacked1, remove historical1:
  task ready1/work1, legacy1/0, source fields historical остаются unknown,
  возвращена unpacked1; `complete_task` создаёт 1 unit и 700 kopecks.
- C20: old2 ready1/work1 удаляется по одному до ready0/work0; новый unpacked
  подбор даёт ready0/work1, старый ready не возвращается; cancel удаляет
  allocation и сохраняет stock total2/packed0.
- Выполнены сохранённые Astra edges: P1-S1 даёт ready1/work1 и 700 kopecks;
  historical pre-pick переносится как `known=0` и удаляется штатно.
- `ruff check .` — PASS; `mypy .` — PASS, 445 source files.

Требования и отчёты ревьюера не изменялись. Этот отчёт фиксирует реализацию и
самопроверку, но не является независимым ревью или приёмкой.
