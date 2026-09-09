# WMS-401 — окончательный Opus Max code review после перезагрузки

Дата: 09.09.2026. Результат CLI: **PASS**, обязательных замечаний нет.
Это проверка кода. Из неё не следует приёмка APK, браузерного сценария, CI,
Railway staging или production.

## Зафиксированная область и результат запуска

Проверенный Opus application diff: `aa7de3de8a965d1088ec44db1bb5f41a766d9dc5`
относительно `a75ed98a03e0500e41a69e5b617a27587bed9792`.
Он меняет только `backend/app/services/fbs_picking_service.py` и
`backend/tests/test_fbs_pick_unload_contract.py`.
Worktree: `.worktrees/wms401-source-switch`, ветка `codex/wms401-source-switch`,
PR [211](https://github.com/chivkunovd-bitdenis/WMS/pull/211).
При запуске HEAD совпадал с frozen SHA, рабочее дерево было чистым;
`git ls-remote` подтвердил тот же SHA ветки в origin.

Предыдущий пустой `outputs/wms401-source-switch-20260909/opus-review.json`
не принят за результат. Выполнен новый запуск сохранённого prompt через stdin.
Установленный Claude Code `2.1.123`; параметры сверены с `claude --help`.

```sh
claude -p --model claude-opus-4-7 --effort max \
  --permission-mode plan --tools Read,Grep,Glob --allowedTools Read,Grep,Glob \
  --strict-mcp-config --mcp-config '{"mcpServers":{}}' --output-format json \
  < /Users/deniscivkunov/Projects/WMS/outputs/wms401-source-switch-20260909/opus-prompt.txt \
  > /Users/deniscivkunov/Projects/WMS/outputs/wms401-source-switch-20260909/opus-review-resumed.json \
  2> /Users/deniscivkunov/Projects/WMS/outputs/wms401-source-switch-20260909/opus-review-resumed.stderr
```

Процесс завершился с exit code `0`, JSON: `subtype=success`, `is_error=false`,
`terminal_reason=completed`, `permission_denials=[]`. Stderr пустой.
Session: `1e620214-0492-490a-bf72-2b29e4cb6d35`. Длительность `463005` ms,
`16` turns. `modelUsage` содержит `claude-opus-4-7`
и вспомогательный `claude-haiku-4-5-20251001`; основной review выполнялся Opus.
CLI сообщил стоимость `$1.49365025`; это поле ответа CLI.

Полный неизменённый ответ: [result.json](result.json).
Исходный prompt с frozen diff: [prompt.json](prompt.json), поле `prompt`.
JSON-обёртка сохраняет текст без изменений, включая пробелы внутри frozen diff.
SHA256 результата: `669606a608b329af1ff2ef66290a338277900b79092cd190571f109b6bb3ada5`.
SHA256 исходного текста prompt: `c66658f20a405bf763a9dac1d81c51ed304551eb25c0e4229a0021ba1d93cc67`.
Фразы Opus о записи plan-файла — часть сырого ответа; запись не разрешалась и
не выполнялась. Для завершённого code review дополнительные разрешения не нужны.

## Независимая сверка результата по коду

Обязательных замечаний Opus нет. Ответ сопоставлен с самостоятельно прочитанным
кодом; ссылки на строки ниже относятся к frozen application code.

- В `fbs_picking_service.py:650–686` неполная пара container kind/id отклоняется,
  затем новый barcode разрешается как B до валидации сохранённого A. Ранний ответ
  возвращает id B и его место хранения, без вызова `scan_pick_product`.
  Для следующего скана клиент должен принять оба возвращённых значения.
- `inventory_container_service.py:37–132` сохраняет фильтры tenant/warehouse
  и ошибку неоднозначности. `warehouse_map_service.py:782–854` повторно вызывает
  прежний `validate_container`. Выбор источника не создаёт подбор,
  резерв или движение товара; прежний fallback может создать запись зоны сортировки,
  если её ещё нет. Поэтому весь путь нельзя называть абсолютно свободным от записей в БД.
- При товарном barcode сохранённый источник проверяется в
  `fbs_picking_service.py:687–716`. Поиск через `order.wb_barcode` сохранён в
  `:1685–1691`, container B передаётся в `scan_pick_product` в `:778–790`.
  Повторный idempotency key обрабатывается прежним кодом `:931–933` и `:1720–1732`.
- Прочитан regression test `test_fbs_pick_scan_switches_source_and_keeps_it_on_product_alias`:
  `test_fbs_pick_unload_contract.py:533–591` проверяет XOR-422, A→B, неизменность
  снимка остатка/резервов, отсутствие picks после source scan, alias-подбор из B
  и повтор без второго pick. Тесты в рамках этого review повторно не запускались.
- Packing diff отсутствует. Прочитанный WB путь
  `fbs_packaging_integration_service.py:593–718` записывает факт упаковки и
  `qty_packed_in_task`; складские остатки и резервы в этой ветке не меняются.
  `fbs_workspace_service.py:419–442` возвращает пустой список навигационных blockers.

## Уточнения к формулировкам Opus

В raw review есть неточность «only two SQL selects»: сам `resolve_container_scan`
выполняет **четыре** SELECT, затем есть запросы разрешения местоположения.
Прирост именно на товарном скане с сохранённым источником — четыре запроса
по barcode; измерения задержки в этом review не проводились.

Утверждение Opus, что пересечение product/container barcode на практике исключено
разными namespace, здесь **не подтверждено**. В прочитанных моделях WarehouseBox,
Pallet и inbound-тары уникальность barcode ограничена собственной таблицей/tenant.
При точном совпадении barcode товара и тары container lookup теперь имеет приоритет
и при сохранённом источнике. Это явная граница действующего контракта;
существование такого случая в production не проверялось и не утверждается.
Нет основания превращать её в выдуманный производственный инцидент.

## Отдельная сверка последующей тестовой правки

Пока Opus выполнялся, владелец основного задания добавил
`14c3d7989f80009c92c9af3fabcae4b14728c1f8` — только
`backend/tests/test_fbs_stock_availability.py`. Это **не** часть frozen Opus review.
Дельта прочитана отдельно: listener SQL-запросов перенесён с общего engine на
`(await session.connection()).sync_connection`, удаляется с того же соединения
в `finally`. Порог `query_count <= 6` остался прежним.

Проверяемая функция `fbs_available_qty_by_product` и её прочитанные зависимости
используют переданную session для всех пяти batch-запросов; они не создают
собственную session и не меняют соединение коммитом. Поэтому новая область
измерения продолжает считать SQL самого расчёта. В fixture вызывается
`inventory_service.record_movement_and_adjust_balance`, который в строке 963
планирует публикацию остатков после commit; посторонние соединения больше
не попадают в измерение. По коду обязательных замечаний к тестовой правке нет.
Повторный запуск тестов не выполнялся; результаты основного задания сюда
не переатрибутированы. `git diff aa7de3de..14c3d798 -- backend/app frontend`
пустой, application code frozen review сохранён.

В этом review не менялся application code, не запускались серверы/AVD,
не выполнялись действия с ключами, production или внешними складскими данными.
Канонический статус WMS-401 обновляет основное задание отдельно от этого отчёта.
