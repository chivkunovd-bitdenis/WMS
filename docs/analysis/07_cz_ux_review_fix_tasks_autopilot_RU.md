# CZ UX fixes — задачи по итогам составного ревью для Cursor Autopilot

> **Контракт (читает orchestrator):**
> - Задача = строка таблицы; **id — первая ячейка**.
> - **Закрыто** = `.cursor/state/<id>.done` (создаёт orchestrator после verifier). **Таблицу не редактируем.**
> - **Заблокировано** = `.cursor/state/<id>.blocked` (3 фейла подряд).
> - **depends_on** — id-предшественники; задача runnable, когда все они `.done`.
> - **files** — что задача правит; две задачи с пересечением `files` **не** идут параллельно.
> - **gate** — команда проверки (зелёная = задача готова к `.done`).
> - Изоляция: каждый builder в `git worktree .cursor/wt/<id>`, коммит там.
> - Контекст/обоснование — ниже в «Детали задач». Берёшь **одну** задачу, не начинаешь следующую, пока текущая не зелёная.

## Зачем это (одно предложение)

Закрыть блокеры и важные риски, найденные составным review ветки `feat/cz-ux-fixes`: достоверность факта приёмки, сохранность разкладки сортировки, рабочий handoff в упаковку, корректность ЧЗ-витрины и минимальное контрактное покрытие.

## Инварианты (НЕ нарушать)

- **И1. Приёмка:** итоговый факт товара = loose-факт + факт в коробах, без двойного счёта и без потери loose-части.
- **И2. Короба приёмки:** количество в коробах хранится как box-lines; `InboundIntakeLine.actual_qty` не должен одновременно быть и итогом, и loose-компонентой.
- **И3. Сортировка:** ошибка загрузки сохранённой разкладки не должна превращаться в пустой editable draft и не должна позволять перезатереть данные.
- **И4. Упаковка:** путь из сортировки должен вести на реально смонтированный FF route `/app/ff/packaging`.
- **И5. ЧЗ:** остаток общей корзины физически общий на пул/корзину; не показывать его как per-SKU остаток товара.
- **И6. Tenant/seller isolation:** новые ЧЗ-фильтры и lookup не должны видеть данные другого tenant/seller даже при совпадающих SKU/title.
- **И7. Минимальный diff:** фиксить только заявленный scope задачи; не делать параллельно соседние P2/P3 без зависимости.

## Карта потоков

| ID | Поток | Что защищаем |
|----|-------|--------------|
| F1 | Inbound receiving | Факт приёмки, ручная правка, расхождения по товарам и коробам |
| F2 | Inbound sorting | Сохранённая разкладка, переход в упаковку |
| F3 | Marketplace unload | HTTP contract completion/discrepancy ack |
| F4 | Честный знак | Ledger, shared basket UI, thresholds, seller/tenant isolation |
| F5 | E2E/contracts | Негативные кейсы и устойчивость селекторов |

## Задачи

| id | depends_on | files | gate | task |
|----|-----------|-------|------|------|
| REV-IN-BE-01 | - | backend/app/services/inbound_intake_service.py, backend/app/services/inbound_intake_box_service.py, backend/app/api/inbound_intake.py, backend/tests/test_inbound_intake_service_be01.py, backend/tests/test_inbound_intake_service_sort_be01.py, backend/tests/test_inbound_intake_api_be03.py | cd backend && ruff check . && mypy . && pytest tests/test_inbound_intake_service_be01.py tests/test_inbound_intake_service_sort_be01.py tests/test_inbound_intake_api_be03.py | P1: исправить двойной счёт/потерю факта при смешанной приёмке loose + box |
| REV-IN-FE-01 | REV-IN-BE-01 | frontend/src/screens/ff/FfInboundRequestView.tsx, frontend/src/screens/ff/inboundReceivingHelpers.ts, frontend/tests-e2e/inbound-receiving-v2.spec.ts | cd frontend && npm run build && npm run test:e2e -- tests-e2e/inbound-receiving-v2.spec.ts | P1: ручная правка приёмки не должна сохранять total как raw loose и задваивать коробочный факт |
| REV-SORT-FE-01 | - | frontend/src/screens/ff/FfInboundSortingPanel.tsx, frontend/src/App.tsx, frontend/tests-e2e/ff-sorting-product-centric.spec.ts | cd frontend && npm run build && npm run test:e2e -- tests-e2e/ff-sorting-product-centric.spec.ts | P1: кнопка «Упаковать» из сортировки должна вести на `/app/ff/packaging` |
| REV-SORT-FE-02 | REV-SORT-FE-01 | frontend/src/screens/ff/FfInboundSortingPanel.tsx, frontend/tests-e2e/ff-sorting-product-centric.spec.ts | cd frontend && npm run build && npm run test:e2e -- tests-e2e/ff-sorting-product-centric.spec.ts | P1: failed load `/distribution-lines` не должен сбрасывать draft в пустые строки и разрешать save/apply |
| REV-CZ-BE-LEDGER-01 | - | backend/app/services/marking_code_service.py, backend/tests/test_marking_ledger_import_aggregate.py | cd backend && ruff check . && mypy . && pytest tests/test_marking_ledger_import_aggregate.py | P2: ledger pagination/total не должны считаться после raw cap 10000 без явного capped-state |
| REV-IN-BE-BOX-01 | REV-IN-BE-01 | backend/app/services/inbound_intake_box_service.py, backend/tests/test_inbound_intake_box_ondemand.py | cd backend && ruff check . && mypy . && pytest tests/test_inbound_intake_box_ondemand.py | P2: concurrent on-demand box creation не должен давать 500/сломанный transaction при гонке box_number |
| REV-CZ-FE-01 | - | frontend/src/screens/shared/HonestSignProductPage.tsx, frontend/src/screens/shared/HonestSignPoolPage.tsx, frontend/tests-e2e/ff-honest-sign.spec.ts, frontend/tests-e2e/ff-honest-sign-pool.spec.ts | cd frontend && npm run build && npm run test:e2e -- tests-e2e/ff-honest-sign.spec.ts tests-e2e/ff-honest-sign-pool.spec.ts | P2: вернуть рабочее место настройки threshold для товара с несколькими personal pools |
| REV-CZ-FE-02 | REV-CZ-FE-01 | frontend/src/screens/shared/HonestSignPoolPage.tsx, frontend/tests-e2e/ff-honest-sign-pool.spec.ts | cd frontend && npm run build && npm run test:e2e -- tests-e2e/ff-honest-sign-pool.spec.ts | P2: в общей корзине не показывать общий остаток как per-SKU `Доступно` в каждой строке товара |
| REV-IN-FE-02 | REV-IN-FE-01 | frontend/src/screens/ff/FfInboundRequestView.tsx, frontend/tests-e2e/inbound-receiving-v2.spec.ts | cd frontend && npm run build && npm run test:e2e -- tests-e2e/inbound-receiving-v2.spec.ts | P2: вернуть явное отображение и предупреждение по расхождению количества коробов в receiving flow |
| REV-IN-TEST-01 | REV-IN-BE-01,REV-IN-FE-02 | backend/tests/test_inbound_box_acceptance.py | cd backend && pytest tests/test_inbound_box_acceptance.py | P2: восстановить тест контракта `actual_box_count` / `boxes_discrepancy` |
| REV-IN-TEST-02 | REV-IN-BE-01 | backend/tests/test_inbound_intake_api_be03.py | cd backend && pytest tests/test_inbound_intake_api_be03.py | P2: добавить negative API coverage для `receiving/scan` и `complete-receiving` |
| REV-OUT-TEST-01 | - | backend/tests/test_marketplace_unload_completion.py, backend/app/api/marketplace_unload_requests.py | cd backend && ruff check . && mypy . && pytest tests/test_marketplace_unload_completion.py | P2: покрыть HTTP contract completion/discrepancy ack для marketplace unload |
| REV-CZ-TEST-01 | REV-CZ-BE-LEDGER-01 | backend/tests/test_marking_inventory_cz_filter.py, backend/tests/test_marking_product_codes_pool_filter.py | cd backend && pytest tests/test_marking_inventory_cz_filter.py tests/test_marking_product_codes_pool_filter.py | P2: добавить tenant/seller isolation кейсы для ЧЗ inventory и product-code lookup |
| REV-MP-E2E-01 | REV-OUT-TEST-01 | frontend/tests-e2e/ff-mp-tabs.spec.ts | cd frontend && npm run test:e2e -- tests-e2e/ff-mp-tabs.spec.ts | P3: укрепить `ff-mp-tabs` селекторы и вернуть явный assert tab/ship state после navigation |
| REV-SORT-E2E-01 | REV-SORT-FE-02 | frontend/tests-e2e/ff-sorting-product-centric.spec.ts | cd frontend && npm run test:e2e -- tests-e2e/ff-sorting-product-centric.spec.ts | P3: `sortingRowByQty` не должен выбирать строку только по quantity при duplicate quantities |

<!--
Дорожки:
- IN-BE: REV-IN-BE-01 -> REV-IN-BE-BOX-01 -> REV-IN-TEST-01/02.
- IN-FE: REV-IN-BE-01 -> REV-IN-FE-01 -> REV-IN-FE-02.
- SORT-FE: REV-SORT-FE-01 -> REV-SORT-FE-02 -> REV-SORT-E2E-01.
- CZ-BE: REV-CZ-BE-LEDGER-01 -> REV-CZ-TEST-01.
- CZ-FE: REV-CZ-FE-01 -> REV-CZ-FE-02.
- OUT/MP: REV-OUT-TEST-01 -> REV-MP-E2E-01.

Параллелизм:
- Сначала можно параллелить REV-IN-BE-01, REV-SORT-FE-01, REV-CZ-BE-LEDGER-01, REV-CZ-FE-01, REV-OUT-TEST-01.
- Не запускать одновременно задачи с одним и тем же файлом из `files`.
- P1 задачи REV-IN-BE-01, REV-IN-FE-01, REV-SORT-FE-01, REV-SORT-FE-02 должны закрыться до финального merge в main.
-->

---

# Детали задач

Для каждой: **Цель / Сейчас (баг) / Что сделать / Acceptance / Тест**. Слои по AGENTS.md. Definition of Done общий:
ruff+mypy+pytest зелёные (BE), `npm run build` зелёный (FE), добавлены тесты из «Тест», инварианты выше целы.

## REV-IN-BE-01 — смешанная приёмка loose + box без двойного счёта

**Цель.** Сделать единый корректный расчёт факта приёмки, когда часть товара принята россыпью, а часть — через короб.

**Сейчас (баг).** Box scan синхронизирует totals в `line.actual_qty`, а `effective_actual_qty()` дальше трактует `actual_qty` как loose-факт и прибавляет box totals ещё раз. В зависимости от порядка операций можно получить потерю loose-части или double count. Пример риска: 6 шт. в короб + ручная/loose правка до 4 шт. → итог может стать 16 вместо 10.

**Что сделать.**
- Развести raw loose-факт и box aggregate. `actual_qty` не должен одновременно быть итогом и loose-компонентой.
- Выбрать минимально совместимую модель:
  - либо перестать писать box totals в `line.actual_qty` до финального completion;
  - либо ввести явную helper-семантику, где `actual_qty` хранит loose, а итог считается только через `effective_actual_qty`;
  - либо мигрировать на отдельное поле, если без этого нельзя сохранить обратную совместимость.
- Проверить `complete_receiving`, `receiving/scan`, manual qty endpoint и переход в sorting: везде один и тот же итог.
- Не ломать legacy тесты inbound intake, если они всё ещё нужны для старого flow.

**Acceptance.**
- Given request line planned=10.
- When оператор сканирует 6 шт. в короб и затем принимает/правит loose=4.
- Then итоговый факт = 10, discrepancy=false, в sorting уходит 10.
- When порядок обратный: loose=4, потом box=6.
- Then итоговый факт также = 10.
- When box=6 и loose=0.
- Then итоговый факт = 6, discrepancy=true при planned=10.

**Тест.**
- Дописать pytest в `test_inbound_intake_service_be01.py` и/или `test_inbound_intake_service_sort_be01.py`: два порядка операций `box -> loose` и `loose -> box`.
- API-level smoke в `test_inbound_intake_api_be03.py` для `receiving/scan` + manual edit + `complete-receiving`.
- Gate: `cd backend && ruff check . && mypy . && pytest tests/test_inbound_intake_service_be01.py tests/test_inbound_intake_service_sort_be01.py tests/test_inbound_intake_api_be03.py`.

## REV-IN-FE-01 — ручная правка receiving не сохраняет displayed total как raw loose

**Цель.** UI должен редактировать ровно ту величину, которую оператор понимает, без hidden double count после коробов.

**Сейчас (баг).** UI показывает `effectiveActualQty` (loose + box lines), но при manual save патчит сырой `actual_qty`. Если в коробах уже 5 и оператор меняет показанное «Принято» на 6, backend может интерпретировать это как loose=6 + box=5 = 11.

**Что сделать.**
- После REV-IN-BE-01 согласовать UI с backend semantics.
- Варианты допустимого решения:
  - показывать и редактировать только loose-часть с явной подписью, отдельно показывая «в коробах» и «итого»;
  - или при сохранении total вычитать текущий box total и отправлять loose delta;
  - или перейти на новый endpoint «set total fact», если он добавлен в REV-IN-BE-01.
- В модалке/инлайн правке не должно быть двусмысленного поля, где operator видит total, а сохраняется loose.

**Acceptance.**
- Given в коробах 5 шт., shown total=5.
- When оператор выставляет «Принято» = 6.
- Then итог после reload/completion = 6, а не 11.
- UI явно показывает, сколько уже в коробах и что именно редактируется.

**Тест.**
- Расширить `inbound-receiving-v2.spec.ts`: scan/add to box, manual edit, reload/complete, assert final fact.
- Gate: `cd frontend && npm run build && npm run test:e2e -- tests-e2e/inbound-receiving-v2.spec.ts`.

## REV-SORT-FE-01 — handoff из сортировки в упаковку ведёт на рабочий route

**Цель.** После создания packaging task из сортировки оператор должен попадать на экран упаковки.

**Сейчас (баг).** `FfInboundSortingPanel.tsx` делает `navigate('/ff/packaging', ...)`, но FF routes смонтированы внутри `/app/*`; реальный путь — `/app/ff/packaging`.

**Что сделать.**
- Заменить путь на `/app/ff/packaging`.
- Лучше вынести route builder/constant, если рядом уже есть паттерн, чтобы не плодить строку.
- Сохранить передачу `taskId`/state/query, если она нужна packaging page.

**Acceptance.**
- Given сортировка завершена/создано задание упаковки.
- When оператор нажимает «Упаковать».
- Then приложение открывает `/app/ff/packaging`, а созданный task доступен/выбран.

**Тест.**
- Дополнить `ff-sorting-product-centric.spec.ts` или существующий sorting/packaging e2e: click «Упаковать», assert URL `/app/ff/packaging` и наличие packaging task.
- Gate: `cd frontend && npm run build && npm run test:e2e -- tests-e2e/ff-sorting-product-centric.spec.ts`.

## REV-SORT-FE-02 — failed load разкладки не превращается в пустой saveable draft

**Цель.** Защитить сохранённую разкладку от случайного обнуления при сетевой/API ошибке.

**Сейчас (баг).** Если `GET /distribution-lines` возвращает `500/403` или временно падает, компонент делает `setProductStates(...rows: [])`, считает загрузку успешной и оставляет save/apply доступными. Следующий save может отправить пустой payload и снести уже сохранённую разкладку.

**Что сделать.**
- На `!res.ok` не сбрасывать product states в пустые строки.
- Показать error state/Alert с retry.
- Заблокировать save/apply до успешного reload.
- Если старое состояние уже было загружено, сохранить его как last-known-good и не заменять пустым результатом failed request.

**Acceptance.**
- Given у request уже есть сохранённые distribution lines.
- When reload distribution-lines падает.
- Then UI показывает ошибку, не показывает пустой draft как норму, save/apply disabled или работают только с last-known-good.
- When retry успешен.
- Then строки возвращаются и save/apply снова доступны.

**Тест.**
- E2E с route interception на `GET /distribution-lines` → 500: assert error visible, save/apply disabled, payload save не отправляется.
- Gate: `cd frontend && npm run build && npm run test:e2e -- tests-e2e/ff-sorting-product-centric.spec.ts`.

## REV-CZ-BE-LEDGER-01 — ledger pagination/total после aggregation без ложного total

**Цель.** Ledger ЧЗ не должен молча терять историю и показывать неверный `total` при большом количестве raw events.

**Сейчас (баг).** `list_ledger()` берёт только `_LEDGER_EXPORT_MAX` raw rows, схлопывает imports в памяти и ставит `total = len(collapsed)`. При историях >10000 raw events старые rows исчезают, pagination после cap неполная, `total` не отражает реальный filtered total.

**Что сделать.**
- Предпочтительно: перенести aggregation/count в SQL или сделать отдельный корректный count collapsed rows.
- Если полный SQL aggregation слишком дорогой, явно вернуть capped/error state и не выдавать ложный `total`.
- Pagination должна быть определена по collapsed rows, а не случайно по raw cap.

**Acceptance.**
- Given >10000 raw ledger events с import aggregation.
- When запрашиваем page после первых 10000 raw events.
- Then API либо возвращает корректные collapsed rows/total, либо явно сообщает capped-state; не допускается тихий неверный `total`.

**Тест.**
- Добавить тест в `test_marking_ledger_import_aggregate.py` на raw events > `_LEDGER_EXPORT_MAX` или monkeypatch cap меньшим числом.
- Gate: `cd backend && ruff check . && mypy . && pytest tests/test_marking_ledger_import_aggregate.py`.

## REV-IN-BE-BOX-01 — concurrent on-demand inbound box creation

**Цель.** Два оператора/TSD не должны получать 500 из-за гонки `box_number`.

**Сейчас (баг).** `_next_box_number()` берёт `max(box_number)+1` без lock. Две транзакции могут выбрать одинаковый номер; loser ловит `IntegrityError`, handler не rollback и retry идёт с тем же номером как будто это barcode collision.

**Что сделать.**
- Заблокировать request row или другой stable parent на время open-box check + next-number allocation.
- Обработать `IntegrityError` через rollback/nested transaction.
- Различать barcode collision и гонку box_number/open_box.
- По возможности добавить DB-инвариант для одного open box per request, если это продуктово верно для inbound on-demand.

**Acceptance.**
- Given две параллельные попытки создать open box на один request.
- Then результат детерминированный: один box создан, второй получает ожидаемый domain error (`open_box_exists`) или clean retry; нет 500 и сломанной session.

**Тест.**
- Добавить pytest с двумя sessions/tasks или последовательной симуляцией conflict.
- Gate: `cd backend && ruff check . && mypy . && pytest tests/test_inbound_intake_box_ondemand.py`.

## REV-CZ-FE-01 — threshold editor для multi-pool товара

**Цель.** У товара с несколькими personal pools должно оставаться рабочее место настройки порогов.

**Сейчас (баг).** Product page показывает threshold editor только для `singlePersonalPool`; multi-pool case оставлен как `TODO`. При этом pool page threshold-блок убран, поэтому workflow настройки порога исчезает.

**Что сделать.**
- Выбрать продуктовую модель:
  - вернуть per-pool threshold editor на `HonestSignPoolPage`;
  - или показать список personal pools на `HonestSignProductPage`, у каждого свой threshold editor.
- Не добавлять threshold на общий shared basket как per-product threshold, если backend этого не поддерживает.
- Убрать `TODO` из пользовательского workflow.

**Acceptance.**
- Given товар с 2 personal pools.
- When FF открывает карточку товара или пул.
- Then можно изменить threshold хотя бы для одного конкретного personal pool и увидеть сохранённое значение после reload.

**Тест.**
- E2E: seed/mocks multi-pool product, открыть UI, изменить threshold, reload, assert value.
- Gate: `cd frontend && npm run build && npm run test:e2e -- tests-e2e/ff-honest-sign.spec.ts tests-e2e/ff-honest-sign-pool.spec.ts`.

## REV-CZ-FE-02 — общий остаток корзины не показывается как per-SKU availability

**Цель.** Не вводить пользователя в заблуждение: общий остаток корзины относится к корзине, а не к каждой строке товара.

**Сейчас (баг).** В `HonestSignPoolPage` на вкладке «Товары» каждая строка товара показывает `detail.available`. Для общей корзины это одно и то же число напротив каждого SKU, что легко читается как per-product availability.

**Что сделать.**
- Убрать колонку `Доступно` из таблицы товаров общей корзины.
- Показать общий остаток один раз в header/summary корзины.
- Если колонка нужна для личного пула, рендерить её только при `!is_shared` или явно подписать «Общий остаток корзины» вне строк товаров.

**Acceptance.**
- Given shared pool на 3 товара с available=1000.
- When открыта вкладка «Товары».
- Then `1000` не повторяется как `Доступно` в каждой SKU-строке; пользователь видит один basket-level остаток.

**Тест.**
- E2E/assert в `ff-honest-sign-pool.spec.ts`: shared pool показывает basket summary и не показывает per-row available.
- Gate: `cd frontend && npm run build && npm run test:e2e -- tests-e2e/ff-honest-sign-pool.spec.ts`.

## REV-IN-FE-02 — факт/расхождение по количеству коробов видно в receiving UI

**Цель.** Оператор должен видеть mismatch по коробам до завершения приёмки.

**Сейчас (баг).** API всё ещё отдаёт `actual_box_count` и `boxes_discrepancy`, но новая inbound UI показывает только planned boxes; completion confirm завязан на line discrepancy и может пропустить mismatch по коробам почти незаметно.

**Что сделать.**
- Показать planned vs actual box count в receiving flow.
- При `boxes_discrepancy=true` показать warning до завершения.
- Если completion требует acknowledge для line discrepancy, включить box discrepancy в тот же confirm или отдельное явное предупреждение.

**Acceptance.**
- Given planned_box_count=3, actual closed boxes=2.
- When оператор завершает receiving.
- Then до завершения виден mismatch по коробам; completion требует явного понимания/ack или показывает warning согласно текущему UX-паттерну.

**Тест.**
- E2E в `inbound-receiving-v2.spec.ts`: создать planned boxes mismatch, assert UI warning/fact count.
- Gate: `cd frontend && npm run build && npm run test:e2e -- tests-e2e/inbound-receiving-v2.spec.ts`.

## REV-IN-TEST-01 — восстановить contract test по box discrepancy

**Цель.** Тесты должны ловить регрессии `actual_box_count` / `boxes_discrepancy`.

**Сейчас (gap).** Переписанный `test_inbound_box_acceptance.py` проверяет наличие коробов, но больше не проверяет старый discrepancy contract. Баг в подсчёте коробов или response fields пройдёт.

**Что сделать.**
- Вернуть один явный mismatch case.
- Assert response body: `actual_box_count`, `planned_box_count` если есть, `boxes_discrepancy`.
- Не дублировать e2e; это контрактный backend/API тест.

**Acceptance.**
- Given planned_box_count != actual_box_count.
- Then API/service response явно содержит mismatch.

**Тест.**
- Gate: `cd backend && pytest tests/test_inbound_box_acceptance.py`.

## REV-IN-TEST-02 — negative API coverage для receiving endpoints

**Цель.** Новые `receiving/scan` и `complete-receiving` должны быть закреплены негативными контрактами.

**Сейчас (gap).** `test_inbound_intake_api_be03.py` в основном happy-path: removed route 404, foreign barcode 422, completion flows. Нет empty barcode, over-scan, scan-after-close/status, response-shape fields.

**Что сделать.**
- Добавить минимум:
  - empty/blank barcode → expected 4xx/detail;
  - over-scan или invalid qty → expected 4xx/detail;
  - scan after `complete-receiving` / wrong status → expected 4xx/detail;
  - response shape для полей, на которые полагается frontend.

**Acceptance.**
- Негативные сценарии возвращают стабильные status/detail.
- Frontend-critical fields закреплены assert-ами.

**Тест.**
- Gate: `cd backend && pytest tests/test_inbound_intake_api_be03.py`.

## REV-OUT-TEST-01 — HTTP contract для unload completion/discrepancy ack

**Цель.** Router/API слой marketplace unload completion должен быть покрыт, а не только service-level.

**Сейчас (gap).** `test_marketplace_unload_completion.py` проверяет service-level completion. Regression в route mapping, status code или response fields может пройти.

**Что сделать.**
- Добавить API-level тест успешного `complete_unload`.
- Добавить API-level тест partial/discrepancy flow: без acknowledge expected rejection, с acknowledge success или актуальное доменное поведение.
- Assert status codes и body fields, включая `has_discrepancy` если поле публичное.

**Acceptance.**
- HTTP endpoint contract закреплён для success и discrepancy/ack.

**Тест.**
- Gate: `cd backend && ruff check . && mypy . && pytest tests/test_marketplace_unload_completion.py`.

## REV-CZ-TEST-01 — tenant/seller isolation для ЧЗ filters и product-code lookup

**Цель.** ЧЗ inventory и product code lookup не должны подтягивать чужие данные при совпадающих SKU/title.

**Сейчас (gap).** `test_marking_inventory_cz_filter.py` и `test_marking_product_codes_pool_filter.py` сидят в одном tenant/seller. Cross-tenant/seller leak не поймается.

**Что сделать.**
- Seed second tenant/seller.
- Создать совпадающий SKU, pool title или GTIN-like данные у другого seller.
- Assert, что inventory/filter/code lookup текущего seller не видит чужие rows/codes.
- Проверить delegated seller scope, если рядом есть helper.

**Acceptance.**
- Same SKU/title в другом tenant/seller не влияет на ответ текущего seller.

**Тест.**
- Gate: `cd backend && pytest tests/test_marking_inventory_cz_filter.py tests/test_marking_product_codes_pool_filter.py`.

## REV-MP-E2E-01 — укрепить `ff-mp-tabs` selectors и state asserts

**Цель.** E2E должен выбирать нужную отгрузку/строку устойчиво, а не первую попавшуюся.

**Сейчас (gap).** `ff-mp-tabs.spec.ts` использует `[data-doc-kind="marketplace_unload"]`, `first()` и exact tab/button state после reload. При изменении DOM order тест может проходить/падать не по тому документу; часть box/ship assertions была урезана.

**Что сделать.**
- Привязать выбор к unload id или стабильному row label/testid.
- Убрать `first()` там, где есть риск выбрать чужую строку.
- Вернуть один явный assert tab/ship state после navigation/reload.

**Acceptance.**
- Тест не зависит от DOM order при нескольких unload docs.
- Есть явный assert, что нужная отгрузка и нужное состояние вкладки/ship-кнопки выбраны.

**Тест.**
- Gate: `cd frontend && npm run test:e2e -- tests-e2e/ff-mp-tabs.spec.ts`.

## REV-SORT-E2E-01 — sorting row identity вместо quantity-only matcher

**Цель.** E2E сортировки должен проверять source label у конкретной строки товара/короба, а не у любой строки с таким quantity.

**Сейчас (gap).** Helper `sortingRowByQty` ищет строки только по quantity. При duplicate quantities source-label asserts могут относиться к другой строке.

**Что сделать.**
- Матчить row по стабильному product/box identifier, SKU, barcode или data-testid.
- Quantity оставить дополнительным assert, не identity.
- Обновить source label assertions на exact row.

**Acceptance.**
- При двух строках с одинаковым quantity тест всё равно выбирает правильную строку.

**Тест.**
- Gate: `cd frontend && npm run test:e2e -- tests-e2e/ff-sorting-product-centric.spec.ts`.

---

## Запуск (новый чат Cursor)

```text
orchestrator, continuous, queue mode, 5 агентов. backlog: docs/analysis/07_cz_ux_review_fix_tasks_autopilot_RU.md
Worker pool: 1 id = 1 builder, refill on free slot.
Изоляция: git worktree .cursor/wt/<id> на задачу, коммит в нём.
Готово = touch .cursor/state/<id>.done после verifier. Бэклог не редактировать.
builder → verifier → fix (max 3).
```

## Минимальный финальный gate после всех P1

```bash
cd "/Users/deniscivkunov/Desktop/WMS "
cd backend && ruff check . && mypy . && pytest tests/test_inbound_intake_service_be01.py tests/test_inbound_intake_service_sort_be01.py tests/test_inbound_intake_api_be03.py tests/test_inbound_intake_box_ondemand.py
cd ../frontend && npm run build && npm run test:e2e -- tests-e2e/inbound-receiving-v2.spec.ts tests-e2e/ff-sorting-product-centric.spec.ts
```

## Минимальный финальный gate после всех задач

```bash
cd "/Users/deniscivkunov/Desktop/WMS "
cd backend && ruff check . && mypy . && pytest tests/test_inbound_box_acceptance.py tests/test_inbound_intake_api_be03.py tests/test_inbound_intake_box_ondemand.py tests/test_inbound_intake_service_be01.py tests/test_inbound_intake_service_sort_be01.py tests/test_marketplace_unload_completion.py tests/test_marking_inventory_cz_filter.py tests/test_marking_ledger_import_aggregate.py tests/test_marking_product_codes_pool_filter.py
cd ../frontend && npm run build && npm run test:unit -- src/utils/printPackagingInstructions.test.ts && npm run test:e2e -- tests-e2e/inbound-receiving-v2.spec.ts tests-e2e/ff-reception-sorting.spec.ts tests-e2e/ff-sorting-product-centric.spec.ts tests-e2e/ff-mp-tabs.spec.ts tests-e2e/ff-honest-sign.spec.ts tests-e2e/ff-honest-sign-pool.spec.ts
```
