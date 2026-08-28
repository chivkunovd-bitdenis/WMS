# A-3: независимый breaking-test review

```yaml
feature_id: A-3
agent_name: "/root/a3_breaking_tester — независимый Terra-тестировщик"
isolated_agent: yes
review_stage: breaking_tests_after_code_review_rework
production_code_changed_by_tester: false
test_code_changed_by_tester:
  - "frontend/src/screens/ff/FfInboundRequestView.test.ts"
  - "frontend/src/screens/ff/FfInboundRequestData.runtime.test.ts"
  - "frontend/src/screens/ff/FfInboundRequestScanner.lifecycle.test.ts"
  - "frontend/src/screens/ff/FfInboundRequestController.contract.test.ts"
  - "frontend/src/screens/ff/FfInboundRequestViewTypes.test.ts"
  - "frontend/tests-e2e/ff-inbound-barcode-add.spec.ts"
verdict: TESTS_GREEN
rework_required: false
current_blocking_defect: null
previous_runtime_flake:
  id: A3-RUNTIME-NET-001
  severity: P0-at-first-observation
  observed: >-
    При параллельной нагрузке два из 29 browser-сценариев не увидели успешные
    POST mutation за 60 секунд: inbound-intake (.../boxes) и inbound-receiving-v2
    (.../begin-receiving).
  resolution: >-
    Оба сценария отдельно прошли на чистых БД/портах (21.8s и 24.3s), затем
    весь утверждённый набор прошёл 29/29 на свежих 18011/5199 без pytest.
resolved_blocking_defect:
  id: A3-CR-004-TYPE
  severity: P0
  observed: >-
    Production build раньше падал с TS2721, поскольку scanToReceiving мог быть
    null внутри queued callback.
  resolution: "Исправлено dev; повторный `npm run build` завершился PASS."
previous_blocking_defect:
  id: A3-MONOLITH-001
  severity: P0
  observed: >-
    Новый FfInboundRequestViewController.ts содержит 1753 строк при ограничении
    600. Это перенос монолита из TSX в TS, а не декомпозиция: правило карточки
    запрещает скрыть монолит расширением вне сканирования UI guard.
  reproducer: >-
    cd frontend && npm run test:unit -- src/screens/ff/FfInboundRequestView.test.ts
  actual: "Первая проверка: 8 тестов, 7 passed / 1 failed; controller: 1753 > 600."
  expected: "Каждая новая часть A-3, включая controller/hook, не превышает 600 строк."
  resolution: >-
    После type-rework controller разделён: полный size scan всех созданных
    FfInboundRequest*.ts/.tsx и useFfInboundRequest*.ts проходит.
```

## Добавленные ломающие проверки

В `FfInboundRequestView.test.ts` добавлены исполняемые проверки, которые намеренно
ломаются при удалении/переименовании public export, selector-contract или попытке
спрятать новый экран-монолит в другом расширении:

- runtime export `FfInboundRequestView` и compile-time exports
  `InboundRequestWorkspace`/`WbCatalogRow`;
- полный multiset baseline из 100 статических `data-testid` (98 уникальных), включая
  две исходные ссылки на `ff-inbound-doc-error`;
- динамические семейства строк, коробов, грузомест и testid, передаваемые дочерним
  компонентам;
- максимум 600 строк для каждого `FfInboundRequest*.tsx`;
- тот же максимум для **всех** созданных `FfInboundRequest*.ts/.tsx` и
  `useFfInboundRequest*.ts`, чтобы смена `.tsx` на `.ts` не стала обходом механической
  цели A-3;
- нулевое число `@ts-nocheck`, `@ts-ignore`, `@ts-expect-error`, `eslint-disable` и
  небезопасных `any` в новых A-3 source-модулях.

## Нумерованные кейсы

### 1. TC-NEW-A3-001 — структурная декомпозиция

- Слой и приоритет: unit/static, P0.
- Цель: не допустить сохранение или маскировку экранного монолита.
- Предусловия: checkout содержит A-3 split и лимит карточки 600 строк.
- Точные действия: запустить `npm run test:unit -- src/screens/ff/FfInboundRequestView.test.ts`.
- Ожидаемый наблюдаемый результат: каждый созданный A-3 TSX, TS-controller и hook не
  длиннее 600 строк; type/ESLint suppression и `any` отсутствуют.
- Данные: исходники `FfInboundRequest*.tsx` и `FfInboundRequestViewController.ts`.
- Способ выполнения: Vitest читает исходники как raw-модули и считает physical lines.
- Автоматизирован: да.
- Фактический результат: **PASS после rework** — 9/9 unit tests. Исторический первый
  прогон был RED: `FfInboundRequestViewController.ts: 1753 > 600`; именно он вернул
  implementation на декомпозицию.

### 2. TC-NEW-A3-002 — public API и DOM-selector parity

- Слой и приоритет: unit/static, P0.
- Цель: сохранить import-contract App и стабильные селекторы пользовательских E2E.
- Предусловия: baseline SHA `7783a27c8c49a60706bac70a155c0721601fbfbb`.
- Точные действия: импортировать public component/types; извлечь static `data-testid` из
  всех A-3 source-модулей; сравнить multiset и required dynamic prefixes с baseline.
- Ожидаемый наблюдаемый результат: `FfInboundRequestView`, `InboundRequestWorkspace`,
  `WbCatalogRow`, 100/98 static selectors и все dynamic families сохранены.
- Данные: baseline source и актуальные sibling-модули A-3.
- Способ выполнения: Vitest.
- Автоматизирован: да.
- Фактический результат: **PASS**. Это не доказывает DOM nesting или видимость само по
  себе; их покрывают browser cases ниже и будущий живой product review.

### 3. TC-S06-001 / TC-S06-002 / TC-S06-004 — draft и передача на склад

- Слой и приоритет: browser E2E, P0.
- Цель: оператор создаёт/открывает черновик, добавляет позицию и передаёт её на склад
  теми же действиями и с теми же status/disabled states.
- Предусловия: чистая Playwright SQLite, FF-пользователь с reception access.
- Точные действия: выполнить `ff-reception-sorting.spec.ts`,
  `ff-inbound-barcode-add.spec.ts`, `inbound-intake.spec.ts` через UI.
- Ожидаемый наблюдаемый результат: видны очередь, документ, состав и прежние действия;
  недопустимые/дублирующиеся действия остаются ограниченными.
- Данные: E2E fixture селлера, склада, товара и черновика.
- Способ выполнения: Playwright, реальные клики и visible assertions.
- Автоматизирован: да.
- Фактический результат: в историческом прогоне до code-review rework было 29/29,
  но актуальный прогон **RED**: `inbound-intake.spec.ts >> create inbound request,
  add line, submit — UI and API` ждёт успешный `POST
  /api/operations/inbound-intake-requests/<requestId>/boxes` при primary accept и
  истекает через 60 секунд. Видимое состояние остаётся `receiving`, при этом
  отображается `Короб № 1`, а факт равен `0`. Артефакт: `frontend/test-results/
  inbound-intake-create-inbo-8029a-dd-line-submit-—-UI-and-API-chromium/
  error-context.md`.

### 4. TC-S06-007 / TC-NEW-IN-01 / TC-NEW-C01-C02 — receiving, scan, boxes и расхождение

- Слой и приоритет: browser E2E, P0.
- Цель: сохранить serial scanner path, ручной факт, наполнение нескольких коробов,
  проверку с расхождением и переход в sorting.
- Предусловия: документ в receiving, оператор с FF-правом, валидный и чужой barcode.
- Точные действия: выполнить `ff-inbound-box-intake.spec.ts`,
  `ff-inbound-boxes.spec.ts`, `ff-inbound-dimensions.spec.ts`,
  `ff-inbound-discrepancy-acts.spec.ts`, `inbound-receiving-v2.spec.ts`.
- Ожидаемый наблюдаемый результат: сканы сериализованы, ошибка чужого barcode видима,
  повторный scan не создаёт вторую физическую операцию, факт/короба/read-back и
  discrepancy dialog сохраняются, status приходит к прежнему sorting state.
- Данные: receiving fixture с двумя коробами, расхождением и barcode-наборами.
- Способ выполнения: Playwright UI; API используется только тестовыми fixture helpers.
- Автоматизирован: да.
- Фактический результат: в историческом прогоне до code-review rework было 29/29,
  но актуальный прогон **RED**: `inbound-receiving-v2.spec.ts >> inbound receiving
  v2 — scan, manual edit, finish with discrepancy` ждёт успешный `POST
  /api/operations/inbound-intake-requests/<requestId>/begin-receiving` после клика
  `Начать приёмку` и истекает через 60 секунд. В документе по-прежнему видны
  статус `Передано на склад` и активная кнопка `Начать приёмку`.
  Артефакт: `frontend/test-results/inbound-receiving-v2-inbou-34238-dit-finish-
  with-discrepancy-chromium/error-context.md`.

### 5. Роли, scope и пустые/ошибочные состояния

- Слой и приоритет: browser/manual product, P1.
- Цель: после split не расширить доступы и не изменить error/empty текст и место показа.
- Предусловия: FF operator/admin и пользователь без reception permission; несуществующий
  requestId; имитированный API error каталога/ячеек.
- Точные действия: открыть reception/sorting/full с каждой ролью, запросить недоступный
  документ, вызвать ошибку load/retry, закрыть dirty-document.
- Ожидаемый наблюдаемый результат: restricted user не получает FF actions; видны прежние
  «Заявка не найдена или недоступна» и конкретные ошибки; close не теряет dirty state.
- Данные: role fixtures, invalid requestId, controlled failed responses.
- Способ выполнения: после rework — Playwright плюс обязательный живой Product Browser Review.
- Автоматизирован: частично существующим набором; полный parity-pass ещё не выполнен.

### 6. Параллельность, восстановление и совместимость API

- Слой и приоритет: integration/browser, P1.
- Цель: один быстрый burst scan сохраняет порядок и не оставляет debounce после unmount;
  повторное открытие читает сохранённый факт без дубликата запросов.
- Предусловия: receiving document с scanner focus и контролируемым delayed reload.
- Точные действия: послать два scan подряд, закрыть/reopen, сравнить mutation count,
  network order, факт и selected box.
- Ожидаемый наблюдаемый результат: ровно одна операция на физический scan, порядок
  arrival сохранён, cancelled reconciler не обновляет закрытый документ, read-back тот же.
- Данные: два barcode одного/разных products, delayed API fixture.
- Способ выполнения: unit runtime tests есть; network-trace browser parity выполнить
  после устранения P0.
- Автоматизирован: частично; итоговый end-to-end trace **не запускался**.

### 7. Desktop/mobile visual parity и релевантная нагрузка

- Слой и приоритет: visual/manual product, P1.
- Цель: без нового wrapper/элемента сохранить порядок DOM, focus, отсутствие document-level
  horizontal overflow и читаемость длинных SKU/ШК при 1600×1000 и 390×844.
- Предусловия: одна закреплённая fixture в draft, receiving with boxes/discrepancy и sorting.
- Точные действия: снять before/after на обоих viewport, пройти scan, box fill, manual fact,
  discrepancy, dirty close, sorting; открыть документ с ~300 строками.
- Ожидаемый наблюдаемый результат: нет новой панели/кнопки/wrapper, нет перекрытия действий
  или document-level horizontal overflow; строка scan не вызывает full-table regression.
- Данные: baseline fixture, long name/SKU/barcode, 300-line document.
- Способ выполнения: обязательный после rework Product Browser Review в живой вкладке.
- Автоматизирован: нет; **не запускался**, поэтому не считается пройденным.

## Выполненные команды и точные результаты

```text
Первый прогон до rework:
cd frontend && npm run test:unit -- src/screens/ff/FfInboundRequestView.test.ts
8 tests: 7 passed, 1 failed
FAIL: FfInboundRequestViewController.ts: expected 1753 <= 600

Повтор после rework:
cd frontend && npm run test:unit -- src/screens/ff/FfInboundRequestView.test.ts
9 tests: 9 passed

cd frontend && E2E_API_PORT=18002 E2E_WEB_PORT=5176 \
  E2E_DB_FILE=a3-inbound-rework-e2e.db npm run test:e2e -- [8 approved specs]
Running 29 tests using 1 worker
final frontend/test-results/.last-run.json: {"status":"passed","failedTests":[]}

cd frontend && npm run build
PASS

cd frontend && python3 ../scripts/ui/ui_guard.py
PASS: новых отступлений нет

git diff --check
PASS
```

Первый запуск E2E на default ports не был тестовым результатом: он корректно остановился,
потому что `localhost:18000` уже занимал параллельный storage-spec. Последний зачётный
прогон выполнен после rework на изолированных `18002/5176`.

## Граница и вывод

Проверенный diff не содержит изменений в `warehouse-map/`, `sorting-objects/` или `ui-kit/`.
После устранения найденного structural defect сборка, ui_guard, все 9 breaking/unit checks и
восемь browser specs (29 tests) не обнаружили регрессию. Manual visual parity, нагрузочный
300-line документ и обязательный живой Product Browser Review не выполнялись этим тестовым
прогоном и не названы пройденными.

**Исторический tester verdict после type-rework: `TESTS_GREEN`.** Он был техническим
verdict и не заменял Code Review или `PRODUCT_BROWSER_APPROVED`.

## Повтор после Code Review rework — runtime/network scope

Добавлены test-only исполняемые проверки:

- `FfInboundRequestData.runtime.test.ts`: actual `useFfInboundRequestData` вызывается с
  mock `fetch` и проверяет exact sequence GET locations → POST location → GET reload →
  GET locations-by-product, без `/ctx.`;
- `FfInboundRequestScanner.lifecycle.test.ts`: receiving → draft даёт ровно одну
  document-level subscription на состояние, cleanup перед следующей подпиской и cleanup
  при unmount;
- `FfInboundRequestController.contract.test.ts`: instrumented runtime controller вызывает
  scanner перед data, а mount с omitted `workspace`/`addressStorageEnabled` передаёт
  effective `full`/`true` в body surface;
- `FfInboundRequestViewTypes.test.ts`: `discrepancyActTitle` выдаёт точное
  `Акт от 28.08.26, 12:34`.

Точный прогон этих пяти unit files: **13/13 passed**. Реальный UI route trace в
`ff-inbound-barcode-add.spec.ts` также прошёл **2/2**: открытие заявки отправило ровно
`GET /api/warehouses/<warehouseId>/locations?exclude_sorting_zone=true`.

Однако `npm run build` теперь RED с `TS2721` в production controller. `ui_guard` и
`git diff --check` остаются PASS; полный approved 8-spec/29 повторно **не запускался**
на build-red дереве и потому не считается результатом этого rework.

**Текущий tester verdict заменён: `TESTS_RED`, `REWORK_REQUIRED`.** Предыдущий
`TESTS_GREEN` выше является историческим результатом до code-review rework, не текущим
вердиктом.

## Финальный повтор после type rework и runtime test additions

Type defect устранён до этого запуска. Ниже сохранены только фактически запущенные
результаты; ни один не запущенный manual/browser product check не назван пройденным.

```text
cd frontend && npm run test:unit -- \
  src/screens/ff/FfInboundRequestView.test.ts \
  src/screens/ff/FfInboundRequestData.runtime.test.ts \
  src/screens/ff/FfInboundRequestScanner.lifecycle.test.ts \
  src/screens/ff/FfInboundRequestController.contract.test.ts \
  src/screens/ff/FfInboundRequestViewTypes.test.ts
PASS: 5 files, 13 tests

cd frontend && npm run build
PASS

cd frontend && python3 ../scripts/ui/ui_guard.py
PASS: новых отступлений нет

git diff --check
PASS

cd frontend && E2E_API_PORT=18003 E2E_WEB_PORT=5177 \
  E2E_DB_FILE=a3-route-trace-e2e.db npm run test:e2e -- \
  tests-e2e/ff-inbound-barcode-add.spec.ts
PASS: 2 tests; exact request GET
/api/warehouses/<warehouseId>/locations?exclude_sorting_zone=true

cd frontend && E2E_API_PORT=18005 E2E_WEB_PORT=5181 \
  E2E_DB_FILE=a3-final-runtime-e2e.db npm run test:e2e -- \
  tests-e2e/ff-reception-sorting.spec.ts \
  tests-e2e/ff-inbound-barcode-add.spec.ts \
  tests-e2e/ff-inbound-box-intake.spec.ts \
  tests-e2e/ff-inbound-boxes.spec.ts \
  tests-e2e/ff-inbound-dimensions.spec.ts \
  tests-e2e/ff-inbound-discrepancy-acts.spec.ts \
  tests-e2e/inbound-intake.spec.ts \
  tests-e2e/inbound-receiving-v2.spec.ts
RED: 2 failed, 27 passed, 29 total
```

В полном прогоне красны ровно два сценария и их error-context сохранён Playwright:

1. `inbound-intake.spec.ts >> create inbound request, add line, submit — UI and API`.
   Сценарий подписывается до клика на успешный `POST
   /api/operations/inbound-intake-requests/<requestId>/boxes` (одновременно с PATCH
   `.../actual`), поэтому это не гонка wait-after-click. После 60 секунд snapshot
   показывает старый operation-screen в `receiving`, видимый `Короб № 1` и факт `0`.
   Артефакт: `frontend/test-results/inbound-intake-create-inbo-8029a-dd-line-submit-—-UI-and-API-chromium/error-context.md`.
2. `inbound-receiving-v2.spec.ts >> inbound receiving v2 — scan, manual edit, finish
   with discrepancy`. До клика подписывается на успешный `POST
   /api/operations/inbound-intake-requests/<requestId>/begin-receiving`. После 60
   секунд UI сохраняет статус `Передано на склад` и видимую кнопку `Начать приёмку`.
   Артефакт: `frontend/test-results/inbound-receiving-v2-inbou-34238-dit-finish-with-discrepancy-chromium/error-context.md`.

Проверка «они были зелёными до split на том же baseline и той же команде»: **нет
такого доказательства**. Baseline `7783a27c8c49a60706bac70a155c0721601fbfbb` этим
полным запуском не проверялся. Есть только исторический 29/29 на более раннем,
уже post-split дереве, поэтому он не может служить сравнением с baseline.

**Итоговый tester verdict: `TESTS_RED`, `REWORK_REQUIRED`.** Runtime static/unit
контракты, build, ui guard и route trace зелёные, но два реальных операторских
mutation path в обязательном наборе пока не прошли. Production-код тестировщиком
не изменялся. Product Browser Review, visual/nagruzka cases по-прежнему не запускались.

## Повтор без параллельной нагрузки

Предыдущий RED не был принят за дефект production автоматически. Сначала оба упавших
сценария воспроизвели изолированно на свежих БД и портах после завершения
параллельной нагрузки: они прошли за **21.8 s** и **24.3 s**, общий изолированный
результат — **2 passed (1.1 m)**, без изменения production-кода.

Затем полный набор повторён на свободных `18011/5199`, свежей SQLite
`a3-final-clean-e2e.db` и без параллельного pytest:

```text
cd frontend && E2E_API_PORT=18011 E2E_WEB_PORT=5199 \
  E2E_DB_FILE=a3-final-clean-e2e.db npm run test:e2e -- \
  tests-e2e/ff-reception-sorting.spec.ts \
  tests-e2e/ff-inbound-barcode-add.spec.ts \
  tests-e2e/ff-inbound-box-intake.spec.ts \
  tests-e2e/ff-inbound-boxes.spec.ts \
  tests-e2e/ff-inbound-dimensions.spec.ts \
  tests-e2e/ff-inbound-discrepancy-acts.spec.ts \
  tests-e2e/inbound-intake.spec.ts \
  tests-e2e/inbound-receiving-v2.spec.ts
PASS: frontend/test-results/.last-run.json = {"status":"passed","failedTests":[]}
```

Так как именно те же два кейса и затем весь набор 29/29 проходят без конкурентной
нагрузки, предыдущие два `waitForResponse` timeout классифицированы как
**resource-contention flake**, а не подтверждённая регрессия A-3. Их точные titles,
ожидаемые POST, видимое состояние и error-context paths сохранены выше как история.

**Текущий tester verdict: `TESTS_GREEN`.** Это технический verdict: он подтверждает
сохранённые breaking tests, unit/build/ui-guard/diff-check и полный Playwright набор.
Он не заменяет отдельный живой Product Browser Review; visual и нагрузочный cases всё
ещё не запускались. Production-код тестировщиком не изменялся.
