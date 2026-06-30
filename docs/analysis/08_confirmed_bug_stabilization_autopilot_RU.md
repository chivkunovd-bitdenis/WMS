# WMS — confirmed bug stabilization backlog for Cursor Autopilot

> **Назначение:** короткий P0/P1 backlog только по багам, которые уже подтверждены скринами/комментами владельца 2026-06-30.  
> **Не является полным реестром требований.** Полный tracker остаётся в `WMS_REQUIREMENTS_TRACKER_RU.md`, но задачи со статусом `❓` сюда намеренно не включены.  
> **Цель:** стабилизировать продукт без повторного расползания scope: приёмка → сортировка/отгрузка → ЧЗ UI/печать.

---

## КОНТРАКТ ДЛЯ ОРКЕСТРАТОРА

1. **Задача = строка таблицы.** `id` — первая ячейка. Таблицу после старта не редактировать.
2. **Статус только файлами:** `.cursor/state/<id>.done`, `.cursor/state/<id>.integrated`, `.cursor/state/<id>.blocked`.
3. **Не запускать одновременно задачи с пересекающимися `files`.** Если хотя бы один файл совпадает — задачи идут последовательно.
4. **Соблюдать `depends_on`.** Задача runnable только когда все зависимости закрыты `.done`.
5. **Изоляция:** каждый builder работает в `git worktree .cursor/wt/<id>` на ветке `task/<id>` от integration branch.
6. **Готово = verifier прошёл gate + runtime proof.** `build green` без живого сценария не считается готовностью.
7. **Минимальный diff.** Не чинить соседние `❓` требования из tracker, не переписывать процесс шире указанного бага.
8. **Перед merge:** builder пишет строку в `TASKLOG.md` с пользовательским сценарием, а не только списком файлов.

**Рекомендуемый старт:**

```text
orchestrator, continuous, queue mode, 4 агента. backlog: docs/analysis/08_confirmed_bug_stabilization_autopilot_RU.md
Worker pool: 1 id = 1 builder, refill on free slot.
Изоляция: git worktree .cursor/wt/<id> на задачу, коммит в нём.
Готово = touch .cursor/state/<id>.done после verifier.
builder → verifier → fix (max 3).
```

---

## Что входит

Входит только подтверждённое:

- **IN-01:** приёмочные короба ошибочно работают как `open/close`, короб не виден, повторное создание блокируется.
- **IN-02:** в приёмке нет явной кнопки завершения/принятия товара.
- **IN-03:** скан в документ должен идти в общую приёмку, а не в текущий/последний короб.
- **IN-11:** модалка добавления в короб разъезжается и не показывает нормальную товарную строку.
- **SO-02/SO-04:** после приёмки сортировка пустая, хотя задания должны появляться.
- **SO-03/BUG-01:** товар, принятый на воротах/в зоне приёмки, можно отгрузить без раскладки; ошибка “недостаточно остатка в выбранной ячейке” не должна блокировать такой поток.
- **CZ-06:** пороги/прогноз снова показаны на карточке пула, хотя должны жить на товаре.
- **CZ-13:** список товаров ЧЗ без фото/названия/размера/печати, с пустой таблицей и провалами.
- **PR-01/PR-02:** печать значка и ЧЗ-печать должны использовать полный понятный конструктор, а не урезанный WB dialog и не “кашу”.
- **PRC-01:** перепечатки КМ не должны быть отдельным пунктом верхнего меню.

Не входит:

- Всё со статусом `❓` из `WMS_REQUIREMENTS_TRACKER_RU.md`.
- Полная переработка ЧЗ, сортировки, приёмки или отгрузки.
- Чистка `.cursor/wt/*` и `task/*` веток.
- Новые фичи, которые не нужны для закрытия багов выше.

---

## Инварианты

- **I1. Приёмка:** короб — обычная созданная сущность в документе, а не modal-state “открытый короб”. Нельзя требовать от оператора “закрыть короб” для продолжения приёмки.
- **I2. Приёмка:** можно создать несколько коробов подряд; каждый короб виден и имеет своё действие наполнения.
- **I3. Приёмка:** товар может быть принят россыпью в общий документ и/или добавлен в конкретный короб. Эти количества не должны задваиваться и не должны теряться.
- **I4. Завершение приёмки:** оператор всегда видит явное действие завершения, если документ в состоянии, где приёмку можно провести.
- **I5. Сортировка:** завершённая приёмка создаёт/показывает задание на раскладку.
- **I6. Отгрузка:** сортировка помогает разложить товар, но не является обязательной блокировкой упаковки/отгрузки только что принятого товара.
- **I7. Остатки:** товар в зоне приёмки/сортировки/на воротах является доступным для упаковки/отгрузки, если бизнес-процесс это разрешает; нельзя требовать конкретную адресную ячейку, когда товар ещё не разложен.
- **I8. ЧЗ:** карточка пула не показывает товарные пороги/прогноз как основной блок настройки; эти настройки должны быть на товаре или на конкретном личном пуле внутри товарного контекста.
- **I9. Печать:** единый конструктор печати переиспользуется в упаковке, печати значка и строке товара ЧЗ. Не плодить второй диалог с отличающейся логикой.
- **I10. UX:** строки товаров в операционных таблицах должны показывать фото, артикул, название и размер, если эти данные уже есть в проекте.

---

## Карта потоков

| ID | Поток | Что исправляем |
|----|-------|----------------|
| F1 | Приёмка | Короба, общий скан, завершение приёмки, модалка добавления в короб |
| F2 | Сортировка | Видимость заданий после приёмки |
| F3 | Отгрузка/упаковка | Возможность отгрузить принятый, но не разложенный товар |
| F4 | Честный Знак | Пороги на пуле, список товаров, печать, перепечатки |

---

## Задачи

| id | depends_on | files | gate | task |
|----|-----------|-------|------|------|
| STAB-IN-BE-01 | - | backend/app/services/inbound_intake_box_service.py, backend/app/services/inbound_intake_service.py, backend/app/api/inbound_intake.py, backend/tests/test_inbound_intake_box_ondemand.py, backend/tests/test_inbound_box_acceptance.py, backend/tests/test_inbound_intake_api_be03.py | cd backend && ruff check . && mypy . && pytest tests/test_inbound_intake_box_ondemand.py tests/test_inbound_box_acceptance.py tests/test_inbound_intake_api_be03.py | P0: заменить ошибочную модель open/close коробов приёмки на on-demand короба: create creates visible box, можно создать N, каждый короб наполняется отдельно |
| STAB-IN-FE-01 | STAB-IN-BE-01 | frontend/src/screens/ff/FfInboundRequestView.tsx, frontend/src/screens/ff/FfInboundBoxAddDialog.tsx, frontend/tests-e2e/inbound-receiving-v2.spec.ts, frontend/tests-e2e/ff-inbound-boxes.spec.ts, frontend/tests-e2e/ff-inbound-box-intake.spec.ts | cd frontend && npm run build && npm run test:e2e -- tests-e2e/inbound-receiving-v2.spec.ts tests-e2e/ff-inbound-boxes.spec.ts tests-e2e/ff-inbound-box-intake.spec.ts | P0: UI приёмки показывает созданные короба, позволяет создать несколько, у каждого отдельное наполнение; нет текста/логики “закройте короб” |
| STAB-IN-FE-02 | STAB-IN-FE-01 | frontend/src/screens/ff/FfInboundRequestView.tsx, frontend/tests-e2e/inbound-receiving-v2.spec.ts | cd frontend && npm run build && npm run test:e2e -- tests-e2e/inbound-receiving-v2.spec.ts | P0: вернуть явную кнопку завершения приёмки; факт руками/сканом можно провести, при расхождении есть подтверждение |
| STAB-IN-FE-03 | STAB-IN-FE-01 | frontend/src/screens/ff/FfInboundBoxAddDialog.tsx, frontend/src/screens/ff/FfInboundRequestView.tsx, frontend/tests-e2e/ff-inbound-box-intake.spec.ts | cd frontend && npm run build && npm run test:e2e -- tests-e2e/ff-inbound-box-intake.spec.ts | P1: модалка добавления товаров в короб — ровные колонки, фото, название, артикул, размер, hover preview; добавление идёт в выбранный короб |
| STAB-SORT-BE-01 | STAB-IN-BE-01 | backend/app/services/inbound_intake_service.py, backend/app/services/sorting_location_service.py, backend/app/api/inbound_intake.py, backend/tests/test_inbound_intake_service_sort_be01.py, backend/tests/test_inbound_distribution.py | cd backend && ruff check . && mypy . && pytest tests/test_inbound_intake_service_sort_be01.py tests/test_inbound_distribution.py | P0: завершённая приёмка создаёт/сохраняет остаток в зоне сортировки и API отдаёт её как задание на раскладку |
| STAB-SORT-FE-01 | STAB-SORT-BE-01 | frontend/src/screens/ff/FfInboundQueuePage.tsx, frontend/src/screens/ff/FfInboundSortingPanel.tsx, frontend/tests-e2e/ff-reception-sorting.spec.ts, frontend/tests-e2e/ff-sorting-product-centric.spec.ts | cd frontend && npm run build && npm run test:e2e -- tests-e2e/ff-reception-sorting.spec.ts tests-e2e/ff-sorting-product-centric.spec.ts | P0: экран сортировки не пустой после приёмки; показывает принятый товар как задание на раскладку |
| STAB-OUT-BE-01 | STAB-SORT-BE-01 | backend/app/services/marketplace_unload_collect_service.py, backend/app/services/marketplace_unload_pick_service.py, backend/app/services/marketplace_unload_service.py, backend/app/services/inventory_service.py, backend/app/api/marketplace_unload_requests.py, backend/tests/test_marketplace_unload_address_storage.py, backend/tests/test_marketplace_unload_and_discrepancy_acts.py, backend/tests/test_marketplace_unload_tsd_scan_contract.py | cd backend && ruff check . && mypy . && pytest tests/test_marketplace_unload_address_storage.py tests/test_marketplace_unload_and_discrepancy_acts.py tests/test_marketplace_unload_tsd_scan_contract.py | P0: товар в зоне приёмки/сортировки доступен для упаковки/отгрузки без предварительной раскладки в адресную ячейку; убрать ошибку “недостаточно остатка в выбранной ячейке” для этого сценария |
| STAB-OUT-FE-01 | STAB-OUT-BE-01 | frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx, frontend/tests-e2e/ff-mp-ship-pick.spec.ts, frontend/tests-e2e/ff-mp-full-flow.spec.ts, frontend/tests-e2e/ff-mp-box-add-modal.spec.ts | cd frontend && npm run build && npm run test:e2e -- tests-e2e/ff-mp-ship-pick.spec.ts tests-e2e/ff-mp-full-flow.spec.ts tests-e2e/ff-mp-box-add-modal.spec.ts | P0: UI упаковки/отгрузки не требует сортировку как обязательный шаг; принятый товар можно добавить в короб/упаковать из буфера |
| STAB-CZ-FE-01 | - | frontend/src/screens/shared/HonestSignPoolPage.tsx, frontend/src/screens/shared/HonestSignProductPage.tsx, frontend/tests-e2e/ff-honest-sign-pool.spec.ts, frontend/tests-e2e/ff-honest-sign.spec.ts | cd frontend && npm run build && npm run test:e2e -- tests-e2e/ff-honest-sign-pool.spec.ts tests-e2e/ff-honest-sign.spec.ts | P1: убрать пороги/прогноз с карточки пула; настройки должны быть доступны из товарного контекста, без дубля на пуле |
| STAB-CZ-FE-02 | STAB-CZ-FE-01 | frontend/src/screens/shared/HonestSignScreen.tsx, frontend/src/screens/shared/HonestSignProductPage.tsx, frontend/src/components/ProductBarcodePrintButton.tsx, frontend/src/components/ProductPhotoThumb.tsx, frontend/tests-e2e/ff-honest-sign.spec.ts | cd frontend && npm run build && npm run test:e2e -- tests-e2e/ff-honest-sign.spec.ts | P1: список товаров ЧЗ показывает фото, артикул, название, размер, hover preview и иконку печати; убрать пустую таблицу/провалы |
| STAB-PRINT-FE-01 | STAB-CZ-FE-02 | frontend/src/components/MarkingPrintDialog.tsx, frontend/src/components/ProductBarcodePrintDialog.tsx, frontend/src/components/ProductBarcodePrintButton.tsx, frontend/src/utils/useMarkingCodePrint.tsx, frontend/src/utils/productBarcodePrint.ts, frontend/tests-e2e/ff-marking-print-constructor.spec.ts, frontend/tests-e2e/ff-marking-packaging.spec.ts, frontend/tests-e2e/ff-product-barcode-print.spec.ts | cd frontend && npm run build && npm run test:e2e -- tests-e2e/ff-marking-print-constructor.spec.ts tests-e2e/ff-marking-packaging.spec.ts tests-e2e/ff-product-barcode-print.spec.ts | P1: единый конструктор печати: два количества (ЧЗ и ШК ВБ) + визуальная лента с drag/drop; печать значка и строка товара открывают тот же конструктор |
| STAB-REPRINTS-FE-01 | - | frontend/src/App.tsx, frontend/src/screens/ff/FfHonestSignReprintsPage.tsx, frontend/src/screens/ff/FfHonestSignPage.tsx, frontend/src/screens/ff/FfPackagingPage.tsx, frontend/tests-e2e/ff-marking-defect.spec.ts | cd frontend && npm run build && npm run test:e2e -- tests-e2e/ff-marking-defect.spec.ts | P2: убрать “Перепечатки” из верхнего меню/общей навигации; оставить перепечатку как контекстное действие там, где есть товар/код/задание |
| STAB-E2E-01 | STAB-IN-FE-02,STAB-SORT-FE-01,STAB-OUT-FE-01 | frontend/tests-e2e/stab-inbound-sort-outbound.spec.ts | cd frontend && npm run test:e2e -- tests-e2e/stab-inbound-sort-outbound.spec.ts | P0 final proof: сквозной сценарий приёмка → сортировка visible → отгрузка без раскладки |
| STAB-E2E-02 | STAB-CZ-FE-02,STAB-PRINT-FE-01,STAB-REPRINTS-FE-01 | frontend/tests-e2e/stab-cz-ui-print.spec.ts | cd frontend && npm run test:e2e -- tests-e2e/stab-cz-ui-print.spec.ts | P1 final proof: ЧЗ товарная строка + печать через единый конструктор + нет перепечаток в меню |

<!--
Параллельные дорожки:
- IN: STAB-IN-BE-01 -> STAB-IN-FE-01 -> STAB-IN-FE-02 / STAB-IN-FE-03.
- SORT/OUT: STAB-SORT-BE-01 -> STAB-SORT-FE-01; STAB-OUT-BE-01 -> STAB-OUT-FE-01.
- CZ: STAB-CZ-FE-01 -> STAB-CZ-FE-02 -> STAB-PRINT-FE-01.
- REPRINTS: STAB-REPRINTS-FE-01 можно делать параллельно, если App/FfPackagingPage не занят.
- Final e2e: STAB-E2E-01 и STAB-E2E-02 после соответствующих цепочек.

Стартовать можно параллельно:
1) STAB-IN-BE-01
2) STAB-CZ-FE-01
3) STAB-REPRINTS-FE-01

Не стартовать STAB-SORT-BE-01 до STAB-IN-BE-01: сортировка зависит от корректного факта приёмки.
Не стартовать STAB-OUT-BE-01 до STAB-SORT-BE-01: нужно единообразно понять “буфер/зона сортировки”.
-->

---

# Детали задач

Для каждой задачи builder обязан выдать:

- изменённые файлы;
- что именно было сломано;
- какие сценарии руками/Playwright прошёл;
- какие тесты добавил или изменил;
- что проверил как “не сломать”.

## STAB-IN-BE-01 — on-demand короба приёмки без open/close

**Цель.** Убрать регрессию, где приёмочные короба работают как один “открытый короб”, требуют закрытия и блокируют повторное создание.

**Сейчас (баг).**

- Нажатие “Создать короб” не даёт нормальный видимый короб в списке.
- Повторное нажатие недоступно.
- Появляется текст вида “Открыт короб № 1. Закройте его в модалке «Добавить в короб» перед завершением приёмки.”
- Это противоречит целевой модели: короб просто создаётся, может быть много коробов, каждый наполняется отдельно.

**Что сделать.**

1. Найти текущую backend-модель создания коробов приёмки в `inbound_intake_box_service.py` и API в `inbound_intake.py`.
2. Убрать продуктовую зависимость от состояния “один открытый короб на документ” для приёмки.
3. `POST create box` должен:
   - создать новый короб для request;
   - присвоить следующий номер;
   - вернуть короб в response;
   - не требовать закрытия предыдущего;
   - не блокировать создание второго/третьего/N-го короба.
4. Сохранить box-lines как принадлежность к конкретному `box_id`.
5. Скан/ручное добавление в короб должно принимать явный `box_id` или использовать endpoint конкретного короба; не использовать “текущий открытый короб” как скрытый глобальный state.
6. Скан в общий документ должен остаться отдельным от добавления в короб.
7. Убрать/не использовать backend errors `open_box_exists`, `open_box_required` именно в пользовательском потоке приёмки, если они относятся к старой модели.

**Acceptance.**

- Given черновик/активная приёмка с одним товаром.
- When оператор вызывает create box три раза подряд.
- Then backend возвращает 3 разных короба: №1, №2, №3.
- When оператор добавляет 2 шт. товара в короб №2.
- Then строки меняются только у короб №2.
- When оператор сканирует товар в общий документ без выбора короба.
- Then количество попадает в loose/general receiving, а не в короб №2 и не в последний созданный короб.
- В response/detail нет обязательного пользовательского состояния “закрыть короб перед завершением”.

**Не ломать.**

- Подсчёт факта приёмки: итог = loose + box lines.
- Завершение приёмки.
- Переход принятого товара в сортировку.
- Существующие коробочные тесты, если они проверяют физические box-lines, а не старую open/close модель.

**Тест.**

- `test_inbound_intake_box_ondemand.py`: можно создать N коробов подряд, нет `open_box_exists`.
- `test_inbound_box_acceptance.py`: box-lines привязаны к конкретному box_id.
- `test_inbound_intake_api_be03.py`: scan в общий document не пишет в короб.

## STAB-IN-FE-01 — UI приёмки показывает много коробов и не требует “закрыть”

**Цель.** Пользовательский экран приёмки должен соответствовать модели из STAB-IN-BE-01.

**Сейчас (баг).**

- После “Создать короб” короб не виден как нормальная сущность.
- Кнопка “Создать короб” гаснет.
- UI показывает сообщение про “открытый короб” и “закройте его”.
- У пользователя нет очевидной кнопки наполнения напротив каждого короба.

**Что сделать.**

1. В `FfInboundRequestView.tsx` заменить UI-состояние “открыт короб” на список коробов документа.
2. Кнопка “Создать короб” всегда доступна в активной приёмке, если пользователь имеет право создавать короба.
3. После успешного создания:
   - обновить detail/list;
   - показать новый короб в списке;
   - не открывать автоматически обязательный modal-state, если это ломает повторное создание.
4. У каждого короба показать:
   - номер;
   - суммарное количество;
   - строки/состав или краткую сводку;
   - отдельную кнопку “Добавить товары”.
5. Убрать видимый текст “закройте короб” и любые disable-state, завязанные на “open box”.
6. Скан в общий документ оставить на уровне документа, не превращать в добавление в последний короб.

**Acceptance.**

- Открываю форму приёмки.
- Нажимаю “Создать короб” 3 раза.
- Вижу 3 коробa.
- У каждого есть своя кнопка “Добавить товары”.
- Нажимаю “Добавить товары” у второго — модалка открывается для второго.
- Добавляю товар — меняется второй.
- Кнопка “Создать короб” после этого всё ещё доступна.
- На экране нет текста “закройте короб”.

**Не ломать.**

- Ручной ввод факта по товару.
- Скан в общий документ.
- Отображение расхождений.
- Завершение приёмки.

**Тест.**

- `inbound-receiving-v2.spec.ts`: smoke для create 3 boxes + no close warning.
- `ff-inbound-boxes.spec.ts` / `ff-inbound-box-intake.spec.ts`: наполнение конкретного короба.

## STAB-IN-FE-02 — явная кнопка завершения приёмки

**Цель.** Вернуть оператору явное действие, которое проводит приёмку после ручного ввода или скана факта.

**Сейчас (баг).**

- Пользователь прописал фактические штуки руками.
- На форме нет понятной кнопки, которая завершает приёмку/принимает товар.
- Это блокирует весь процесс: сортировка и отгрузка не получают нормальный завершённый документ.

**Что сделать.**

1. Найти текущий completion flow (`complete-receiving`) в `FfInboundRequestView.tsx`.
2. Показать основную кнопку:
   - “Завершить приёмку” или текущий термин проекта;
   - в нижней панели или в стандартном месте действий документа;
   - только для статусов, где completion разрешён.
3. Кнопка должна работать после:
   - ручного ввода факта;
   - скана в общий документ;
   - добавления в короба;
   - смешанного сценария loose + boxes.
4. При расхождении факт != план показать явное подтверждение “Есть расхождения, провести приёмку?”.
5. После успешного completion обновить статус/detail и показать, что товар передан дальше.

**Acceptance.**

- Given приёмка planned=10.
- When оператор руками вводит fact=10.
- Then видна кнопка завершения; click проводит приёмку без лишней модалки.
- Given planned=10.
- When fact=8.
- Then click показывает confirmation по расхождению; после подтверждения приёмка проводится.
- Given есть 2 шт. в коробе и 8 loose.
- Then completion проводит итог 10.

**Не ломать.**

- Нельзя автоматически проводить приёмку без клика оператора.
- Нельзя терять расхождение.
- Нельзя требовать закрытия коробов.

**Тест.**

- `inbound-receiving-v2.spec.ts`: manual fact → complete; discrepancy → confirm → complete; box+loose → complete.

## STAB-IN-FE-03 — модалка добавления в короб

**Цель.** Сделать модалку добавления товаров в конкретный короб читаемой и недвусмысленной.

**Сейчас (баг).**

- Колонки разъезжаются.
- Нет нормальной товарной строки.
- Не хватает фото, названия, артикула, размера.
- Непонятно, в какой короб добавляется товар.

**Что сделать.**

1. В `FfInboundBoxAddDialog.tsx` сделать стабильную таблицу/список товаров.
2. В header модалки явно показать номер выбранного короба.
3. В строке товара показать:
   - фото через `ProductPhotoThumb`;
   - артикул/SKU;
   - название;
   - размер, если есть в данных;
   - план/уже принято/доступно для добавления;
   - контрол количества для добавления именно в этот короб.
4. Фото должно увеличиваться при hover тем же паттерном, что в других формах.
5. Столбцы не должны прыгать при вводе количества или hover.
6. После подтверждения обновить только выбранный короб и общий detail.

**Acceptance.**

- Открываю “Добавить товары” у короб №2.
- Вижу заголовок “Короб №2”.
- Вижу строки товаров с фото, названием, артикулом, размером.
- Навожу на фото — preview увеличивается.
- Ввожу количество, подтверждаю.
- Количество добавлено в короб №2, не в №1 и не в общий loose.

**Тест.**

- `ff-inbound-box-intake.spec.ts`: открыть модалку второго короба, assert product fields, add qty, assert target box changed.

## STAB-SORT-BE-01 — принятый товар появляется как сортировочное задание

**Цель.** После завершения приёмки товар должен быть виден в сортировке как задание на раскладку.

**Сейчас (баг).**

- Пользователь видит пустую сортировку: “нет приёмок/заданий”.
- При этом приёмки есть.
- Это разрывает процесс: после приёмки непонятно, куда делся товар.

**Что сделать.**

1. Проверить `complete_receiving` и движение остатков в `inbound_intake_service.py`.
2. Убедиться, что после completion создаётся/обновляется остаток в зоне сортировки или эквивалентном буфере.
3. `GET` данных сортировки должен возвращать принятые, но не разложенные товары.
4. Если товар принят частично loose и частично box, сортировочное задание должно учитывать обе части без дубля.
5. Если товар уже отгружен до сортировки, задание должно уменьшиться/исчезнуть корректно.

**Acceptance.**

- Given новая приёмка planned=4.
- When оператор завершает приёмку fact=4.
- Then backend summary/detail для сортировки показывает 4 к раскладке.
- When часть товара разложена, remaining уменьшается.
- When товар забрали в отгрузку из буфера до раскладки, sorting remaining не показывает фантомный остаток.

**Не ломать.**

- Существующую раскладку по ячейкам.
- Смешанный источник loose/box.
- Резервы/остатки.

**Тест.**

- `test_inbound_intake_service_sort_be01.py`: completion creates sorting remaining.
- `test_inbound_distribution.py`: distribution consumes remaining correctly.

## STAB-SORT-FE-01 — экран сортировки не пустой после приёмки

**Цель.** UI сортировки должен показывать задания, которые backend отдаёт после STAB-SORT-BE-01.

**Сейчас (баг).**

- На экране сортировки пусто, хотя приёмка завершена.
- Пользователь не видит строку товара и не может начать раскладку.

**Что сделать.**

1. Проверить `FfInboundQueuePage.tsx`: фильтры статусов, workspace `sorting`, `sorting_remaining_qty`.
2. Проверить `FfInboundSortingPanel.tsx`: загрузка detail/distribution-lines.
3. Убедиться, что очередь сортировки показывает документы со статусом/остатком, который появился после completion.
4. В строке очереди показать количество к сортировке.
5. При открытии задания показать товар-центричный вид: товар, принято, осталось разложить, строки раскладки.
6. Empty state показывать только когда backend действительно вернул 0 заданий.

**Acceptance.**

- Завершил приёмку 4 шт.
- Перехожу в сортировку.
- Вижу документ/строку с `4`.
- Открываю — вижу товар и могу добавить ячейку для раскладки.
- Empty state не появляется, пока есть remaining > 0.

**Тест.**

- `ff-reception-sorting.spec.ts`: приёмка → sorting queue qty.
- `ff-sorting-product-centric.spec.ts`: открыть задание и увидеть product card.

## STAB-OUT-BE-01 — отгрузка из буфера без обязательной сортировки

**Цель.** Разрешить отгрузить товар, который уже принят, но ещё не разложен по адресным ячейкам.

**Сейчас (баг).**

- Система может требовать остаток в конкретной выбранной ячейке.
- В проде возникает ошибка “Недостаточно доступного остатка в выбранной ячейке”.
- Но физически товар может быть на воротах/в зоне приёмки, и его нужно сразу упаковать/отгрузить.

**Что сделать.**

1. Найти общий путь проверки доступности в `marketplace_unload_collect_service.py`, `marketplace_unload_pick_service.py`, `inventory_service.py`.
2. Ввести/использовать источник “sorting/buffer location” как валидный источник для collect/pack/ship.
3. Если адресное хранение включено, не требовать реальную адресную ячейку для товара, который ещё находится в зоне приёмки/сортировки.
4. При добавлении в короб/упаковку из буфера корректно списывать/резервировать именно этот буферный остаток.
5. Ошибка `insufficient available at selected cell` должна оставаться только когда пользователь действительно выбрал ячейку и там не хватает, а не когда товар доступен в буфере.

**Acceptance.**

- Given товар принят fact=5 и не разложен.
- When создаём/подтверждаем отгрузку на этот товар.
- Then backend позволяет добавить товар в короб/упаковку из буфера.
- Then ship/complete не падает с ошибкой по выбранной ячейке.
- Given товара нет ни в ячейках, ни в буфере.
- Then backend по-прежнему возвращает честную ошибку нехватки остатка.

**Не ломать.**

- Обычную отгрузку из адресных ячеек.
- Резервирование.
- Списание при collect/ship согласно текущей модели.

**Тест.**

- `test_marketplace_unload_address_storage.py`: buffer/sorting stock valid source.
- `test_marketplace_unload_and_discrepancy_acts.py`: collect/ship from buffer.
- `test_marketplace_unload_tsd_scan_contract.py`: scan flow не требует location для buffer case или даёт правильный guided flow.

## STAB-OUT-FE-01 — UI отгрузки не блокирует товар без сортировки

**Цель.** Пользователь может из интерфейса упаковать/отгрузить принятый товар без предварительной раскладки.

**Сейчас (баг).**

- UI/flow может вести пользователя к выбору ячейки как обязательному шагу.
- При отсутствии разложенного остатка сценарий ломается, хотя backend после STAB-OUT-BE-01 должен поддерживать буфер.

**Что сделать.**

1. Проверить `FfSuppliesShipmentsPage.tsx`: модалки добавления в короб, scan, manual pick, подсказки по ячейкам.
2. Если товар доступен в буфере/зоне сортировки, показать его как доступный источник.
3. Не показывать ошибку/блокировку “нет в ячейке”, если есть buffer availability.
4. В модалке/строке подсказать источник: “Зона приёмки/сортировки” или текущий термин проекта.
5. Сохранить обычный сценарий выбора конкретной ячейки.

**Acceptance.**

- Принял товар.
- Не раскладывал.
- Открыл отгрузку/упаковку.
- Вижу товар доступным.
- Добавляю его в короб/упаковку.
- Ошибки по выбранной ячейке нет.

**Тест.**

- `ff-mp-ship-pick.spec.ts` или `ff-mp-full-flow.spec.ts`: accepted-not-sorted → unload/pack/ship.
- `ff-mp-box-add-modal.spec.ts`: buffer source виден и selectable.

## STAB-CZ-FE-01 — убрать пороги/прогноз с карточки пула

**Цель.** Убрать подтверждённый UI-регресс: настройки порога и прогноза снова показаны на пуле, хотя пользователь договорился видеть их на товаре.

**Сейчас (баг).**

- На карточке пула есть блок “Пороги остатка”, “Предупреждать за N дней”.
- Это дублирует/переносит товарную настройку на технический объект “пул/корзина”.

**Что сделать.**

1. В `HonestSignPoolPage.tsx` убрать видимый threshold block с карточки пула.
2. Если backend endpoint threshold остаётся pool-level, не удалять API, а убрать только неправильную поверхность.
3. В `HonestSignProductPage.tsx` убедиться, что настройка доступна из товарного контекста:
   - для одного personal pool — текущий editor;
   - для нескольких personal pools — список personal pools с настройкой каждого или понятный переход к настройке конкретного личного пула.
4. Для shared basket не показывать threshold как per-product настройку, если backend этого не поддерживает.

**Acceptance.**

- Открываю карточку пула.
- Не вижу блока “Пороги остатка” и поля “Предупреждать за N дней”.
- Открываю карточку товара.
- Вижу место, где можно настроить порог для товара/его personal pool.

**Тест.**

- `ff-honest-sign-pool.spec.ts`: threshold block отсутствует на pool page.
- `ff-honest-sign.spec.ts`: threshold доступен на product page.

## STAB-CZ-FE-02 — список товаров ЧЗ с фото/названием/размером/печатью

**Цель.** Главный список ЧЗ должен быть товарным и узнаваемым, а не безликой таблицей с артикулом.

**Сейчас (баг).**

- Видно только безликий артикул.
- Нет фото, названия, размера.
- Таблица визуально пустая, с большими провалами.
- Нет иконки печати в строке товара.

**Что сделать.**

1. В `HonestSignScreen.tsx` привести строку товара к паттерну каталога/других форм.
2. В колонке товара показать:
   - `ProductPhotoThumb`;
   - артикул/SKU;
   - название;
   - размер, если поле есть в row/product;
   - понятный compact layout без огромных пустых провалов.
3. Добавить иконку печати в строку товара.
4. Иконка печати должна открывать общий print flow, который STAB-PRINT-FE-01 доведёт до полного конструктора.
5. Фото должно увеличиваться при hover тем же образом, как в остальных формах.
6. Не возвращать главный экран к pool-first модели.

**Acceptance.**

- На главном экране ЧЗ каждая строка выглядит как товар.
- Есть фото, название, артикул, размер.
- Hover по фото увеличивает preview.
- Есть compact print icon.
- Нет пустой таблицы с провалами.

**Тест.**

- `ff-honest-sign.spec.ts`: assert photo/name/sku/size/print action.

## STAB-PRINT-FE-01 — единый конструктор печати

**Цель.** Убрать раздробленную/непонятную печать: печать значка, строка товара и упаковка должны использовать один полный конструктор.

**Сейчас (баг).**

- Печать значка открывает простой WB dialog 58x40.
- Конструктор выглядит как “каша”.
- Пользователь ожидает простую систему: сколько ЧЗ, сколько ШК ВБ, затем визуальная лента с drag/drop.

**Что сделать.**

1. Определить один canonical component: `MarkingPrintDialog`.
2. Убрать использование `ProductBarcodePrintDialog` в ЧЗ-контекстах, где должен быть полный конструктор.
3. UI конструктора:
   - числовой контрол “ЧЗ”;
   - числовой контрол “ШК ВБ”;
   - визуальная лента/preview порядка печати;
   - элементы ленты можно перетаскивать мышкой;
   - порядок на ленте = порядок печати.
4. Тот же компонент открыть из:
   - упаковки;
   - печати значка;
   - иконки печати в строке товара ЧЗ.
5. Не ломать печать не-ЧЗ товара, если там по текущему решению нужен только простой ШК ВБ.
6. Не менять backend-модель кодов, если задача решается фронтом.

**Acceptance.**

- Открываю печать из упаковки ЧЗ-товара — вижу полный конструктор.
- Открываю печать значка — вижу тот же полный конструктор.
- Открываю печать из строки товара ЧЗ — вижу тот же полный конструктор.
- Выставляю ЧЗ=2, ШК ВБ=3.
- На ленте 5 элементов.
- Перетаскиваю элементы мышкой.
- Preview/print использует новый порядок.

**Тест.**

- `ff-marking-print-constructor.spec.ts`: counts + drag/drop + order.
- `ff-marking-packaging.spec.ts`: packaging entry opens same constructor.
- `ff-product-barcode-print.spec.ts`: non-CZ simple print не сломан.

## STAB-REPRINTS-FE-01 — убрать перепечатки из верхнего меню

**Цель.** Перепечатки не должны быть отдельным глобальным пунктом верхней навигации.

**Сейчас (баг).**

- “Перепечатки” видны в общем списке/верхнем меню как отдельный экран.
- Пользователь считает это мусором в навигации.

**Что сделать.**

1. Найти route/nav item в `App.tsx` / FF navigation.
2. Убрать пункт “Перепечатки” из верхнего меню.
3. Не удалять сам экран/route, если он используется как internal/context page или нужен shift lead.
4. Оставить действия перепечатки в контексте:
   - код;
   - товар;
   - задание упаковки;
   - брак/замена, если это текущая модель.
5. Если route остаётся доступен по прямой ссылке для роли, он не должен светиться как основной раздел.

**Acceptance.**

- Открываю FF верхнее меню.
- Не вижу отдельный пункт “Перепечатки”.
- В контексте кода/брака/упаковки возможность перепечатать не потеряна.

**Тест.**

- `ff-marking-defect.spec.ts`: reprint context flow still works.
- Дополнить assert, что nav item “Перепечатки” отсутствует.

## STAB-E2E-01 — финальный сквозной proof приёмка → сортировка → отгрузка без раскладки

**Цель.** Зафиксировать главный продуктовый сценарий, который сломался: принял товар, увидел сортировку, но при необходимости сразу отгрузил.

**Сценарий.**

1. Создать/открыть приёмку.
2. Ввести/сканировать факт.
3. Создать 2 коробa приёмки, добавить часть товара во второй короб.
4. Завершить приёмку.
5. Перейти в сортировку и убедиться, что задание видно.
6. Не выполнять раскладку.
7. Создать/открыть отгрузку на этот товар.
8. Добавить товар в короб/упаковку из буфера.
9. Убедиться, что нет ошибки “недостаточно остатка в выбранной ячейке”.

**Acceptance.**

- Сценарий проходит одним e2e без ручных шагов.
- В тесте явно проверены:
  - короба приёмки видны;
  - кнопка завершения есть;
  - сортировка видит товар;
  - отгрузка доступна до раскладки.

## STAB-E2E-02 — финальный proof ЧЗ UI + печать

**Цель.** Зафиксировать, что исправления ЧЗ не разъехались обратно.

**Сценарий.**

1. Открыть главный экран ЧЗ.
2. Убедиться, что список по товарам, строка содержит фото/название/артикул/размер.
3. Открыть карточку пула.
4. Убедиться, что на пуле нет threshold block.
5. Вернуться к товару и открыть печать из строки.
6. Убедиться, что открыт полный конструктор.
7. Выставить ЧЗ/ШК ВБ, перетащить элементы ленты.
8. Убедиться, что в верхнем меню нет “Перепечатки”.

**Acceptance.**

- Один e2e доказывает все перечисленные UI-контракты.
- Если drag/drop нестабилен в браузере CI, тест должен проверять доступный keyboard/mouse fallback, но не заменять проверку на “dialog visible”.

---

## Финальные gates

### P0 после ядра

```bash
cd "/Users/deniscivkunov/Desktop/WMS "
cd backend && ruff check . && mypy . && pytest tests/test_inbound_intake_box_ondemand.py tests/test_inbound_box_acceptance.py tests/test_inbound_intake_api_be03.py tests/test_inbound_intake_service_sort_be01.py tests/test_inbound_distribution.py tests/test_marketplace_unload_address_storage.py tests/test_marketplace_unload_and_discrepancy_acts.py tests/test_marketplace_unload_tsd_scan_contract.py
cd ../frontend && npm run build && npm run test:e2e -- tests-e2e/inbound-receiving-v2.spec.ts tests-e2e/ff-inbound-boxes.spec.ts tests-e2e/ff-inbound-box-intake.spec.ts tests-e2e/ff-reception-sorting.spec.ts tests-e2e/ff-sorting-product-centric.spec.ts tests-e2e/ff-mp-ship-pick.spec.ts tests-e2e/ff-mp-full-flow.spec.ts tests-e2e/ff-mp-box-add-modal.spec.ts tests-e2e/stab-inbound-sort-outbound.spec.ts
```

### P1/P2 после ЧЗ

```bash
cd "/Users/deniscivkunov/Desktop/WMS "
cd frontend && npm run build && npm run test:e2e -- tests-e2e/ff-honest-sign-pool.spec.ts tests-e2e/ff-honest-sign.spec.ts tests-e2e/ff-marking-print-constructor.spec.ts tests-e2e/ff-marking-packaging.spec.ts tests-e2e/ff-product-barcode-print.spec.ts tests-e2e/ff-marking-defect.spec.ts tests-e2e/stab-cz-ui-print.spec.ts
```

