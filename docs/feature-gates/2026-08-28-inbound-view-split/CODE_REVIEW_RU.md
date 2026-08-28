# A-3: независимый повторный Code Review разделения `FfInboundRequestView`

```yaml
feature_id: A-3
agent_name: "/root/a3_review — независимый Code Reviewer"
isolated_agent: yes
review_stage: code_review_after_rework_and_clean_breaking_tests
production_or_test_code_changed_by_reviewer: false
review_document_changed_by_reviewer:
  - "docs/feature-gates/2026-08-28-inbound-view-split/CODE_REVIEW_RU.md"
baseline_sha: "e2dd8f0a67629f5edbb432c9a1517e6e57536804"
verdict: CODE_REVIEW_PASSED
blocking_findings: []
resolved_findings:
  - A3-CR-001
  - A3-CR-002
  - A3-CR-003
  - A3-CR-004
  - A3-CR-005
```

## Итог

Повторный review не нашёл оставшихся блокирующих дефектов A-3. Rework вернул
три исходных API-маршрута, публичные defaults `workspace='full'` и
`addressStorageEnabled=true`, двухзначный год акта и относительный lifecycle
scanner subscriptions до data effects. Добавленные runtime-тесты теперь ловят
именно те классы ошибок, которые прошли первый зелёный source-only прогон.

Разделение остаётся механическим: нового видимого элемента, текста, колонки,
кнопки или wrapper-узла в production diff не появилось. Исходный публичный файл
стал двухстрочным re-export, а логика распределена по тематическим модулям без
нового скрытого монолита.

## Проверка прежних находок

### A3-CR-001 — исправлено: точные API URL восстановлены

В `frontend/src/screens/ff/useFfInboundRequestData.ts:109,137,165` снова
используются:

```text
GET  /warehouses/<warehouseId>/locations?exclude_sorting_zone=true
POST /warehouses/<warehouseId>/locations
GET  /operations/inventory-balances/locations-by-product?...
```

Статическое AST-сравнение reviewer-а обнаружило 32 вызова `apiUrl` в baseline
и 32 в split-коде, без отличий аргументов после нормализации локального
`ctx.`-доступа. Литерального `/ctx.` в route больше нет.

`FfInboundRequestData.runtime.test.ts` дополнительно выполняет полный цикл
load → create → reload → cell hints и проверяет точные методы/URL четырёх
запросов. `ff-inbound-barcode-add.spec.ts` перехватывает реальный browser GET
точного складского route.

### A3-CR-002 — исправлено: публичные defaults нормализуются на границе

`FfInboundRequestViewController.ts:27-31` формирует `normalizedProps` с
`workspace: props.workspace ?? 'full'` и
`addressStorageEnabled: props.addressStorageEnabled ?? true`. Именно этот
объект передаётся в state/data/actions и возвращается UI; raw optional props
больше не перезаписывают эффективные значения.

`FfInboundRequestController.contract.test.ts` вызывает controller и public view
без обоих optional prop и проверяет значения `full/true` как в state arguments,
так и в возвращённом controller.

### A3-CR-003 — исправлено: формат даты совпадает с baseline

`FfInboundRequestViewTypes.ts:151-160` снова содержит `year: '2-digit'`.
`FfInboundRequestViewTypes.test.ts` фиксирует наблюдаемый результат:
`Акт от 28.08.26, 12:34`.

### A3-CR-004 — исправлено: scanner lifecycle снова предшествует data effects

В `FfInboundRequestViewController.ts:32-63` scanner hook вызывается сразу после
state и до `useFfInboundRequestData`, distribution/receiving/package actions.
Это восстанавливает значимый baseline-порядок setup/update/cleanup
capture-phase listeners относительно data effects и Ozon workflow.

Два render-local handler сохраняют прежнюю семантику closures: callbacks,
переданные scanner hook, читают назначенные в том же render функции после
создания action hooks; receiving handler по-прежнему ставится в
`receivingScanQueue`. Guard `if (handler)` закрывает initial type/lifecycle
границу без вызова `null`.

`FfInboundRequestScanner.lifecycle.test.ts` проверяет одну активную подписку,
переключение receiving → draft и симметричный cleanup на unmount;
`FfInboundRequestController.contract.test.ts` инструментирует порядок
state → scanner → data → actions. Существующие fast-path tests и полный inbound
Playwright-набор покрывают serial queue и реальные scan/mutation пути.

### A3-CR-005 — исправлено: тесты проверяют runtime, а не только raw source

К прежнему structural guard добавлены четыре узких runtime/contract файла:

- `FfInboundRequestData.runtime.test.ts` — точные методы и URL;
- `FfInboundRequestScanner.lifecycle.test.ts` — subscription lifecycle;
- `FfInboundRequestController.contract.test.ts` — defaults и hook order;
- `FfInboundRequestViewTypes.test.ts` — видимый формат даты.

Полный approved browser-набор после rework прошёл 29/29 на чистой SQLite и
свободных портах. Два предыдущих timeout были воспроизведены отдельно зелёными,
после чего зелёным стал весь тот же набор; сохранённые данные поддерживают
классификацию resource contention, а не production-регрессии A-3.

## Проверено без находок

- Публичный import path и exports `FfInboundRequestView`,
  `InboundRequestWorkspace`, `WbCatalogRow` сохранены.
- `FfInboundRequestView.tsx` — двухстрочный re-export. Каждый новый production
  `.ts`/`.tsx` A-3 меньше 600 строк по тому же physical-lines правилу; максимум
  `useFfInboundRequestData.ts` — 503 строки по `wc`, structural test также
  проходит. Скрытого монолита через смену расширения нет.
- В production A-3 нет `@ts-nocheck`, `@ts-ignore`, `@ts-expect-error`,
  `eslint-disable` или небезопасного `any`.
- UI guard baseline распределён без роста и без нового вида отступления:
  суммарно ровно 6 `Chip`, 36 `Button`, 4 `TableHead`; запись
  `экран-монолит` исходного файла удалена.
- `python3 scripts/ui/ui_guard.py` завершился с `новых отступлений нет`.
- Scoped diff пуст для `frontend/src/screens/ff/warehouse-map/`,
  `frontend/src/screens/ff/sorting-objects/` и `frontend/src/ui-kit/`.
- A-3 production diff не меняет backend, соседние экраны или App contract.
  Изменение `ff-inbound-barcode-add.spec.ts` относится только к точному route
  trace и не ослабляет прежний пользовательский сценарий.
- Статический multiset сохранён: 100 вхождений / 98 уникальных статических
  `data-testid`, плюс прежние динамические selector families.
- Главный DOM-порядок и nesting остаются прежними: provider/global styles,
  root, error/warning, paper, header, sorting panel, lines, sorting wait,
  discrepancies, packages, distribution и dialogs. Внутренние React component
  boundaries не создают DOM wrapper.
- Мемоизированные тяжёлые product/box line cells сохранены; нового видимого
  текста или label кроме восстановленного baseline-формата не найдено.
- AST-сравнение строковых UI literals с baseline не обнаружило нового
  пользовательского текста; дополнительный `full` относится только к явной
  нормализации прежнего default.

## Выполненные проверки

Независимо повторено reviewer-ом:

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

python3 scripts/ui/ui_guard.py
PASS: новых отступлений нет

git diff --check
PASS
```

Изучено и принято как независимое test evidence из актуального
`TEST_REVIEW_RU.md`:

```text
exact route browser trace: 2/2 PASS
approved inbound Playwright suite on clean ports/DB: 29/29 PASS
isolated rerun of the two earlier timeouts: 2/2 PASS
```

Vite build сообщил только неблокирующее существующее предупреждение о chunks
больше 500 kB; оно не создано этим mechanical split.

## Неизвестное / не засчитано этим verdict

- Code Review не является Product Browser Review и не принимает визуальное
  поведение. Живой проход в видимой вкладке, desktop/mobile geometry,
  focus/Escape/dirty-close и до/после внешний вид должен проверить отдельный
  Product Agent следующим gate.
- Reviewer не повторял 29 browser tests самостоятельно; проверены их актуальные
  команды, clean-run результат и история двух timeout в tester artifact.
- Нагрузочный документ около 300 строк и полный visual snapshot parity этим
  техническим review не запускались.
- Смешанные изменения A-1/backend и `FfStoragePage` находятся вне scope A-3 и
  этим verdict не оценивались.

## Вердикт

`CODE_REVIEW_PASSED`. Техническая реализация A-3 может переходить к отдельной
Product Browser Review After Dev. До её явного `PRODUCT_BROWSER_APPROVED`
карточка не считается закрытой и визуальное равенство не заявляется.
