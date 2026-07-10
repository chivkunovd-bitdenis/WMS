# BUGLOG

## BUG-7 — 2026-07-10 — MP-подбор завышал доступность в статусе collecting

- Symptom: readonly MP availability мог вернуть товар как доступный, хотя количество уже было зарезервировано другой отгрузкой на МП в статусе `collecting`.
- Cause: endpoint использовал агрегат `inventory_service.MP_UNLOAD_RESERVE_STATUSES`, где отсутствовал `collecting`, вместо канонического `marketplace_unload_service.RESERVE_STATUSES`.
- Root cause category: `contract`.
- Fix: общий контракт `marketplace_unload_status.RESERVE_STATUSES` используется и MP-сервисом, и inventory summary; endpoint и серверная проверка строки используют общие batch-функции резервов, а `exclude_request_id` исключает только текущую заявку.
- Prevention: regression test создаёт текущий `collecting`-резерв и второй `confirmed`-резерв; доступность равна 4 без исключения и 7 при исключении только текущей заявки.
- Commit: pending.

## BUG-6 — 2026-07-10 — Параллельные приходы могли потерять увеличение остатка

- Symptom: два разных импорта, одновременно добавляющие количество одного товара в одну ячейку, могли оба прочитать старый баланс и сохранить только одно увеличение.
- Cause: положительный остаток менялся через ORM read-modify-write без блокировки строки или атомарного SQL.
- Root cause category: `race`.
- Fix: все изменения корзин выполняются атомарно на одной DB-строке: приход — `INSERT ... ON CONFLICT DO UPDATE`, упаковка и списание — условные `UPDATE ... RETURNING`. PostgreSQL сериализует конфликтующие row mutations; SQLite использует совместимые SQL paths.
- Prevention: два barrier-теста реально запускают import + package и import + deduct параллельно, проверяя движения, обе корзины и инвариант. Они помечены `postgresql_concurrency` и могут быть перезапущены через изолированный `WMS_TEST_DATABASE_URL`; SQLite marker run 2/2 green. UI stale-response paths используют sequence guard согласно существующему `ui-engineering-checklist`.
- Commit: pending.

## BUG-5 — 2026-07-09 — ИП на этикетке ШК ВБ визуально сплющена / слипается с названием

- Symptom: на физической этикетке (фото с прода) строка «ИП Горячкина Т И» выглядит сжатой по вертикали и почти вплотную к названию товара; цифры ШК тоже близко к ИП. Остальные строки могут быть нормальнее.
- Cause: (1) `labelScale.font = sqrt(w×h)` раздувал шрифт на 60×80/70×120 сильнее, чем зазор между строками; (2) `-webkit-line-clamp` на `.name` в Chromium print давал наезд на строку ИП; (3) предыдущий «фикс» PR #94 (trim снизу) не лечил межстрочный интервал — на высоких размерах trim не срабатывал, баг оставался.
- Fix: отдельный `labelTextFontScale` с потолком; `line-height: 1.35`; `min-height` у `.seller`; зазор и отступ от цифр масштабируются с текстом; обрезка названия через `max-height`, не `-webkit-line-clamp`; превью в `ProductBarcodePrintDialog` выровнено.
- Verification: vitest `printProductThermalLabel.test.ts` 12/12; Playwright metrics script `verify-seller-line-height.mts` — gap seller→name ≥ 3.5px на всех размерах; PNG в `output/pdf/_verify/seller-line-fix/`.
- Commit: pending

## BUG-4 — 2026-07-06 — Факт приёмки сбрасывается в 0 при уходе с поля

- Symptom: в приёмке оператор вводит «Принято» (например 100), уводит курсор с поля — значение становится 0.
- Cause: при `onBlur` сохранение читало устаревший React state (`draftQtyByProductId` / `actualDraftByLineId`) из замыкания; последний ввод ещё не попадал в state, на сервер уходил 0. Дополнительно: клик по карандашу давал blur+click — второй save без значения перезаписывал 0.
- Fix: ref синхронно в `onChange`; `onBlur` на `htmlInput`; `onMouseDown preventDefault` на карандаше; fallback на draft state.
- Verification: `npm run build`; e2e `inbound-receiving-v2.spec.ts`, `ff-inbound-box-intake.spec.ts` (pressSequentially + blur).
- Commit: `f62b590` (PR #73)

## BUG-3 — 2026-06-24 — Дата отгрузки сбрасывается после выбора в календаре

- Symptom: в заявке на отгрузку на МП пользователь выбирает дату в календаре, но поле сразу очищается.
- Cause: `WmsDateField` на `onBlur` вызывал `onChange(null)` при пустом значении секции поля; после закрытия календаря MUI X v9 blur срабатывал на пустой секции и отправлял PATCH с `planned_shipment_date: null`. Дополнительно: `DatePicker.onChange(null)` при закрытии календаря гонял второй PATCH с null поверх сохранённой даты.
- Fix: пустой blur не сбрасывает дату; коммит даты через `onAccept`/blur; PATCH-обработчики игнорируют null.
- Verification: `npm run build`; e2e `seller-mp-unload.spec.ts` (TC-NEW-DATE-01, no null PATCH), `ff-dashboard.spec.ts`, `ff-inbound-boxes.spec.ts`.
- Commit: 962a2fd (PR #44); prod `194.87.96.144:8088` — `prod-update.sh`.

## BUG-2 — 2026-05-03 — FF could add no-stock products to WB shipment

- Symptom: while adding products to a WB marketplace shipment, FF saw catalog products that did not have actual warehouse stock and could add them to the document.
- Cause: the shipment UI used the full product catalog for the picker, and `marketplace-unload` line creation only checked tenant/seller ownership, not available warehouse stock.
- Fix: the FF shipment picker is fed from inventory availability, and backend line creation rejects products/quantities without enough available stock in the shipment warehouse.
- Verification: `pytest tests/test_marketplace_unload_and_discrepancy_acts.py`; targeted `ruff`/`mypy`; `npm run build`; `npm run test:e2e -- ff-dashboard.spec.ts`.
- Commit: pending

## BUG-1 — 2026-05-03 — Accepted seller products missing from FF catalog

- Symptom: after FF completed seller inbound acceptance/distribution, products did not appear in the FF products catalog.
- Cause: `/products/ff-catalog` correctly listed products with inventory movements, but `distribution-complete` only locked distribution lines and did not create inventory movements or balances.
- Fix: completing distribution now posts distributed actual quantities into inventory movements/balances and updates inbound `posted_qty`; the catalog can then include those products.
- Verification: `pytest tests/test_inbound_distribution.py tests/test_products_wb_catalog.py`; targeted `ruff`/`mypy`.
- Commit: d5a954f
