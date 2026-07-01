# WMS document UI fix orchestration

Дата старта: 2026-07-01 16:08 MSK

Реальный checkout: `/Users/deniscivkunov/Desktop/WMS `.

Ограничение: разработчики только `gpt-5.4-mini`. Оркестратор не вносит продуктовый код, только координирует, пишет срезы и интегрирует результаты.

## Лимиты

- 2026-07-01 16:08 MSK: в доступных инструментах нет отдельной телеметрии лимитов модели/агентов. Есть только управление агентами и обычные shell/git проверки. Поэтому обязательный контроль: после каждой завершённой задачи писать подробный срез сюда; если инструмент вернёт capacity/limit/thread-limit ошибку, сразу записать состояние и остановить запуск новых задач.

## Подтверждённые факты из кода

- Рабочий UI приёмки показывает технический `document_number` в шапке: `frontend/src/screens/ff/FfInboundRequestView.tsx`.
- Рабочий UI упаковки показывает `ID {document_number}` в шапке задания: `frontend/src/screens/ff/FfPackagingPage.tsx`.
- Рабочий UI отгрузки показывает технический `document_number` в шапке: `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`.
- Backend сейчас генерирует технические номера с префиксами `ПРИЕМ`, `ОТГР`, `УПАК` через `backend/app/services/document_number_service.py`.
- UI сейчас получает `№000001` парсингом хвоста технического номера, это не отдельная пользовательская нумерация.
- Дубли общего итога подтверждены только на рабочей форме отгрузки: `Задание на упаковку`, `План и распределение`, `План и факт не совпадают`.
- В таблице товаров отгрузки построчные `План / Распределено / Осталось` есть и должны остаться.
- Footer отгрузки содержит кнопку `Упаковка`, которая дублирует вкладку `Упаковка`.
- Блок `Сборка в короба` не входит в правки.

## Задачи

### TASK-01. Backend: пользовательские display-номера документов

Статус: completed by Godel, pending orchestrator review

Владелец: mini-worker backend.

Файлы во владении: `backend/app/models/*`, `backend/app/services/document_number_service.py`, связанные backend services/API schemas/tests/migrations.

Требование: добавить отдельный пользовательский номер для рабочих документов `Приёмка`, `Сортировка`, `Упаковка`, `Отгрузка`. Номер должен быть вида `№000001`, последовательность отдельная по типу документа, не парсинг технического `document_number`. Технический `document_number` сохранить для внутренних связей и API-совместимости, но добавить отдельное поле для UI.

Границы: если `Сортировка` не является отдельной backend-сущностью, агент должен явно зафиксировать это и предложить минимальный безопасный способ выдать отдельный display-номер без ломки процесса. Не менять бизнес-логику коробов, упаковки, отгрузки.

Готово когда: API отдаёт user-facing display number для документов, backend tests или targeted проверки покрывают отдельные последовательности.

Промежуточный срез:

- 2026-07-01 16:17 MSK / Godel: начата backend-основа отдельного UI display-номера. Изменены `backend/app/models/document_sequence.py`, `backend/app/services/document_number_service.py`, `backend/app/models/inbound_intake.py`, `backend/app/models/marketplace_unload.py`, `backend/app/models/packaging_task.py`, `backend/app/models/__init__.py`, `backend/app/services/inbound_intake_service.py`, `backend/app/services/marketplace_unload_service.py`, `backend/app/services/packaging_task_service.py`, `backend/app/api/inbound_intake.py`, `backend/app/api/marketplace_unload_requests.py`.
- Что уже сделано: добавлена отдельная сущность/механика счётчика display-номеров; начато прокидывание `display_number` в модели и автоприсваивание при создании `inbound_intake`, `marketplace_unload`, `packaging_task`; frontend/короба не трогались.
- Осталось: допрокинуть `display_number` в `packaging_tasks` API; добавить миграцию с новой таблицей display-sequence и backfill для старых документов; дописать targeted tests на сервис/API; прогнать проверки.
- Blockers/capacity: не заявлены.

Финальный срез:

- 2026-07-01 16:22 MSK / Godel: TASK-01 закрыта в backend scope.
- Файлы: `backend/app/services/document_number_service.py`, `backend/app/models/document_sequence.py`, `backend/app/models/inbound_intake.py`, `backend/app/models/marketplace_unload.py`, `backend/app/models/packaging_task.py`, `backend/app/models/__init__.py`, `backend/app/services/inbound_intake_service.py`, `backend/app/services/marketplace_unload_service.py`, `backend/app/services/packaging_task_service.py`, `backend/app/api/inbound_intake.py`, `backend/app/api/marketplace_unload_requests.py`, `backend/app/api/packaging_tasks.py`, `backend/alembic/versions/20260701_0056_document_display_sequences.py`, `backend/tests/test_document_number_service.py`.
- Что сделано: добавлена отдельная пользовательская последовательность `display_number` вида `№000001`, не завязанная на хвост технического `document_number`; `display_number` прокинут в API приёмки/сортировки через inbound request, отгрузки и packaging tasks; добавлена миграция с таблицей `document_display_sequences`, колонками `display_number` и backfill старых записей по `created_at` + `id`.
- Важная граница: отдельной backend-сущности сортировки нет, поэтому display contract для сортировки идёт через inbound request, который сейчас даёт UI этап сортировки.
- Проверки агента: `pytest -q '/Users/deniscivkunov/Desktop/WMS /backend/tests/test_document_number_service.py'` -> `10 passed`; `pytest -q '/Users/deniscivkunov/Desktop/WMS /backend/tests/test_packaging_tasks.py' -k 'packaging_task_manual_convert'` -> `1 passed`.
- Риски: backfill зависит от порядка `created_at, id`; технический `document_number` сохранён.

### TASK-02. Frontend: шапки приёмки/сортировки/упаковки без техкодов

Статус: completed by Euclid, pending orchestrator review

Владелец: mini-worker frontend-doc-headers.

Файлы во владении: `frontend/src/screens/ff/FfInboundRequestView.tsx`, `frontend/src/screens/ff/FfInboundSortingPanel.tsx`, `frontend/src/screens/ff/FfPackagingPage.tsx`, связанные e2e только для этих экранов.

Требование: в рабочих формах показывать фактическое название процесса и пользовательский номер. Не показывать `ПРИЕМ-*`, `УПАК-*`, `ID ...`, слово `Документ` как заголовок рабочей формы. Приёмка = `Приёмка`, сортировка = `Сортировка`, упаковка = `Упаковка`.

Границы: не менять таблицы, процессы, печать, ЧЗ, упаковочную бизнес-логику.

Готово когда: рабочие формы приёмки/сортировки/упаковки не показывают технические номера и используют display-number contract из backend либо безопасный временный fallback с явной пометкой.

Срез результата:

- 2026-07-01 16:16 MSK / Euclid: изменены `frontend/src/screens/ff/FfInboundRequestView.tsx`, `frontend/src/screens/ff/FfPackagingPage.tsx`, добавлен helper `frontend/src/screens/ff/documentDisplay.ts`, обновлены `frontend/tests-e2e/ff-inbound-box-intake.spec.ts` и `frontend/tests-e2e/ff-packaging-page.spec.ts`.
- Что сделано: из рабочей формы приёмки убрана видимая строка технического номера под пользовательским номером; из рабочей формы упаковки убран `ID ...`; отображение номера переведено на приоритет `display_number/public_number/human_number` с fallback на старый `document_number`.
- Проверки агента: целевые e2e по двум затронутым сценариям прошли, `8 passed`.
- Риски/остаток: `npm run build` у агента упал не по TASK-02, а на текущем состоянии `FfSuppliesShipmentsPage.tsx` и записи `tsbuildinfo` в sandbox. Требуется оркестраторская интеграционная проверка после завершения TASK-03.

### TASK-03. Frontend: отгрузка - шапка, один общий summary, footer без кнопки Упаковка

Статус: completed by Maxwell, pending orchestrator review

Владелец: mini-worker frontend-shipment.

Файлы во владении: `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`, связанные e2e по отгрузке.

Требование: на форме отгрузки показывать `Отгрузка` + пользовательский номер, убрать видимый `ОТГР-*`. Под метаданными отгрузки оставить один серый summary-блок с общим итогом: `План`, `В коробах/Распределено`, `Осталось`, `Упаковано`. Убрать отдельные дубли `Задание на упаковку`, `План и распределение`, `План и факт не совпадают`, если они повторяют общий итог. Построчные колонки таблицы товаров `План / Распределено / Осталось` сохранить. В footer убрать кнопку `Упаковка`; переход в упаковку только через вкладку.

Границы: блок `Сборка в короба` не менять: поля, кнопки, scan, список, меню, модалки и API вызовы должны остаться без продуктовых изменений.

Готово когда: на отгрузке один общий итог сверху, таблица товаров сохраняет построчные числа, footer не дублирует вкладку, короба не изменены.

Промежуточный срез:

- 2026-07-01 16:16 MSK / Maxwell: изменён `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`, в работе `frontend/tests-e2e/ff-mp-tabs.spec.ts`; агент сообщил, что ещё нужно добить `frontend/tests-e2e/ff-mp-full-flow.spec.ts` и `frontend/tests-e2e/ff-mp-packaging-gate.spec.ts`.
- Что уже сделано: убран видимый raw `ОТГР-*` из рабочей шапки; добавлен fallback на `display_number/public_number/human_number`; собран один серый summary-блок под метаданными; из footer убрана кнопка `Упаковка`.
- Граница: агент подтвердил, что блок `Сборка в короба` по продуктовой части не трогал.
- Осталось: довести e2e ожидания под новый UI и выполнить проверки. Blockers/capacity не заявлены.

Финальный/неполный срез:

- 2026-07-01 16:23 MSK / Maxwell: e2e ожидания добиты в `frontend/tests-e2e/ff-mp-tabs.spec.ts`, `frontend/tests-e2e/ff-mp-full-flow.spec.ts`, `frontend/tests-e2e/ff-mp-packaging-gate.spec.ts`.
- Что сделано: проверки переведены на заголовок `Отгрузка №...`, новый `ff-mp-shipment-summary`, удалены ожидания старых `ff-mp-collect-*` и `ff-mp-packaging-progress`. UI-файл оставался в рамках шапка/summary/footer; блок `Сборка в короба` по словам агента не менялся.
- Проверка агента: `npm run test:e2e -- tests-e2e/ff-mp-tabs.spec.ts tests-e2e/ff-mp-full-flow.spec.ts tests-e2e/ff-mp-packaging-gate.spec.ts` -> 5/6 passed, 1 failure.
- Не закрыто: `ff-mp-full-flow.spec.ts` упал на timeout `page.waitForResponse` в шаге подтверждения даты/создания документа. Агент считает, что это не напрямую новый summary, но full-flow остаётся неподтверждённым.
- Следующее действие: вернуть Maxwell на точечный разбор этого timeout в том же scope, без новых UI-правок и без изменений блока коробов.

Финальный срез:

- 2026-07-01 16:29 MSK / Maxwell: TASK-03 закрыта в frontend shipment scope.
- Что дополнительно сделано: failing `ff-mp-full-flow.spec.ts` оказался тестовым timeout в `frontend/tests-e2e/wms-date-field-helpers.ts`; helper календаря теперь двигается по месяцам в обе стороны. Продуктовый UI и блок `Сборка в короба` не менялись.
- Что дополнительно сделано по review: `ff-mp-shipment-summary-remaining` снова получает warning-акцент `warning.main`, когда остаток ненулевой; добавлена e2e-проверка цвета в `frontend/tests-e2e/ff-mp-tabs.spec.ts`.
- Проверки агента: `npm run test:e2e -- tests-e2e/ff-mp-full-flow.spec.ts` -> passed; `npm run test:e2e -- tests-e2e/ff-mp-tabs.spec.ts` -> passed, 4/4.
- Риски: тест цвета завязан на стандартный MUI `warning.main` (`rgb(237, 108, 2)`), при смене темы ожидание нужно обновить вместе с визуальным решением.

### TASK-04. Verification and integration

Статус: planned

Владелец: оркестратор после возврата mini-workers.

Проверить: `rg` по видимым техкодам в рабочих формах, targeted frontend build/typecheck/tests, backend targeted tests по нумерации, сохранность коробов по diff review. Не запускать широкие рискованные правки вне scope.

## Журнал срезов

- 2026-07-01 16:08 MSK: создан документ оркестрации. Рабочее дерево до старта: `main...origin/main [ahead 1]`, `git status --short` без изменений. Подтверждено: real checkout `/Users/deniscivkunov/Desktop/WMS `. Следующий шаг: запуск mini-workers по TASK-01..TASK-03.
- 2026-07-01 16:09 MSK: запущены mini-workers строго на `gpt-5.4-mini`: Godel / TASK-01 backend display-нумерация; Euclid / TASK-02 frontend headers приёмка-сортировка-упаковка; Maxwell / TASK-03 frontend отгрузка summary/footer. Оркестрационный документ во владении оркестратора, агентам запрещено его редактировать. Области записи разведены: backend vs inbound/packaging headers vs shipment page. Лимит-телеметрия модели недоступна в инструментах; жду сигналов capacity/limit от agent tool и не запускаю новые задачи до первого результата.
- 2026-07-01 16:11 MSK: минутный контроль лимитов. Отдельной quota-телеметрии нет; `wait_agent` не вернул capacity/limit/thread-limit, только timeout без завершённых агентов. `git status --short`: пока изменён только этот документ (`?? docs/analysis/12_wms_document_ui_fix_orchestration_RU.md`). Продолжение: ждать первый результат Godel/Euclid/Maxwell.
- 2026-07-01 16:12 MSK: минутный контроль лимитов. Отдельной quota-телеметрии нет; `wait_agent` снова timeout, capacity/limit ошибок нет. В рабочем дереве уже появились изменения от агентов: `FfInboundRequestView.tsx`, `FfPackagingPage.tsx`, `FfSuppliesShipmentsPage.tsx`, `ff-inbound-box-intake.spec.ts`, `ff-packaging-page.spec.ts`, новый `frontend/src/screens/ff/documentDisplay.ts`. Не интегрировал и не правил поверх: жду финальные ответы агентов, чтобы зафиксировать авторство, завершённость и риски.
- 2026-07-01 16:14 MSK: минутный контроль лимитов. Отдельной quota-телеметрии нет; `wait_agent` timeout без limit/capacity. `git status --short` показывает тот же набор изменённых frontend-файлов и этот документ. Backend-файлов пока в status нет, значит TASK-01 либо ещё анализируется, либо не записал diff. Если следующий wait снова вернёт timeout, запрошу у агентов промежуточный статус.
- 2026-07-01 16:15 MSK: контроль лимитов и состояния. Четвёртый `wait_agent` также timeout без limit/capacity. Отправлен промежуточный status request всем mini-workers: Godel, Euclid, Maxwell. Новые задачи не запускались.
- 2026-07-01 16:16 MSK: получены промежуточные/финальные статусы от Euclid и Maxwell. Euclid закрыл TASK-02 в своём scope; Maxwell сделал UI TASK-03, но ещё не завершил e2e. Отдельных limit/capacity сигналов нет. Следующий шаг: вернуть Maxwell к завершению исходной TASK-03 и ждать Godel/TASK-01.
- 2026-07-01 16:17 MSK: получен промежуточный статус Godel. TASK-01 не завершена: нет packaging API, миграции/backfill и тестов. Отдельных limit/capacity сигналов нет. Следующий шаг: отправить Godel и Maxwell добивать незавершённые пункты в исходном scope.
- 2026-07-01 16:17 MSK: Godel отправлен добивать только TASK-01: packaging API, миграция/backfill, targeted tests/checks. Maxwell отправлен добивать только TASK-03 e2e ожидания. Euclid не перезапускался. Новые агенты не запускались.
- 2026-07-01 16:18 MSK: минутный контроль. Отдельной quota-телеметрии нет; `wait_agent` timeout без limit/capacity. `git status` показывает backend TASK-01 изменения, frontend TASK-02 изменения и TASK-03 e2e изменения (`ff-mp-full-flow`, `ff-mp-packaging-gate`, `ff-mp-tabs`). Финальные ответы Godel/Maxwell ещё не получены, ручная интеграция поверх не выполнялась.
- 2026-07-01 16:19 MSK: минутный контроль. `wait_agent` снова timeout без limit/capacity. Отправлен промежуточный status request Godel и Maxwell после добивки. Новые задачи не запускались.
- 2026-07-01 16:20 MSK: минутный контроль. Ответов на status request пока нет; limit/capacity нет. `git status` показывает, что Godel, вероятно, дописал packaging API, backend test и миграцию: появились `backend/app/api/packaging_tasks.py`, `backend/tests/test_document_number_service.py`, `backend/alembic/versions/20260701_0056_document_display_sequences.py`. Если следующий wait снова timeout, оркестратор начнёт read-only review текущего diff без правок поверх.
- 2026-07-01 16:22 MSK: Godel завершил TASK-01. Limit/capacity не было. Следующий шаг: ждать Maxwell/TASK-03, затем оркестраторский diff review и общие проверки.
- 2026-07-01 16:23 MSK: Maxwell вернул TASK-03 с частичным e2e результатом: 5/6 passed, `ff-mp-full-flow.spec.ts` timeout на `page.waitForResponse`. Limit/capacity не было. Следующий шаг: отправить Maxwell на точечную добивку failing e2e в исходном scope.
- 2026-07-01 16:24 MSK: Maxwell отправлен на точечную добивку только failing `ff-mp-full-flow.spec.ts` timeout. Запрещено менять продуктовый UI, блок коробов и расширять scope. Оркестратор начинает read-only diff review завершённых частей.
- 2026-07-01 16:26 MSK: минутный контроль. Maxwell ещё не вернулся; limit/capacity нет. Read-only review: миграционная цепочка выглядит корректно (`down_revision = 20260630_0055`); блок коробов в diff продуктово не менялся; найден потенциальный хвост TASK-03 — новое значение `Осталось` в `ff-mp-shipment-summary` пока не подсвечивается предупреждающим цветом при ненулевом остатке, хотя старое значение это делало. В `git diff --name-only` появился `frontend/tests-e2e/wms-date-field-helpers.ts`, вероятно как точечная добивка таймаута даты в full-flow.
- 2026-07-01 16:27 MSK: Maxwell добил failing full-flow. Причина timeout была в `frontend/tests-e2e/wms-date-field-helpers.ts`: helper календаря двигался только вперёд, а календарь мог открыться на более позднем месяце. Изменение только в тестовой утилите, продуктовый UI и блок коробов не трогались. Проверка агента: `npm run test:e2e -- tests-e2e/ff-mp-full-flow.spec.ts` -> passed. Остался оркестраторский finding по TASK-03: подсветить `Осталось` в новом summary при ненулевом остатке.
- 2026-07-01 16:28 MSK: минутный контроль. Maxwell ещё не вернул финал, limit/capacity нет. Read-only check показывает, что точечная подсветка уже появилась в `FfSuppliesShipmentsPage.tsx`: `ff-mp-shipment-summary-remaining` получает `warning.main` при ненулевом остатке. Жду финальный ответ агента с проверкой.
- 2026-07-01 16:29 MSK: Maxwell завершил TASK-03. Limit/capacity не было. Все mini-workers завершили свои задачи. Следующий шаг: закрыть агентов, выполнить оркестраторский review и общие проверки.
