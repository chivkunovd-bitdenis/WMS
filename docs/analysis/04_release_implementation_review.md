# Ревью реализации перед релизом

> Итоговый файл прогона `release review` (init: 2026-06-27)
> Секция 2 пополняется на каждом `phase=batch`. Секции 1, 3–6 — на `phase=final`.

Источник требований: `01_normalized_process_spec.md`, `02_technical_builder_plan.md`, `03_builder_plan_review.md`  
Состояние прогона: `04_release_manifest.md`

---

## 1. Краткий вывод

> Заполнено: `phase=final` (2026-06-27)

- **Можно выкатывать:** **нет — только после правок** (2 блокера по end-to-end цепочке ФФ)
- **Главный риск:** оператор не может пройти типовой сценарий «N коробов → наполнение через модалку → ship с полным планом»: batch создаёт **закрытые** короба (S05); параллельно упаковка может «завершиться» сама без явного шага и ЧЗ-gate (S04)
- **Что обязательно исправить до релиза:**
  1. Убрать авто-`STATUS_DONE` в `_touch_task` — завершение только через `complete_task` с ЧЗ-gate (REQ-005, DEC-014)
  2. Batch create коробов — **открытые** короба (`closed_at=NULL`), чтобы «Добавить товары» работало для N≥2 (REQ-007, REQ-008)
- **Что не подтверждено по коду:** негатив `marking_not_done` на `POST .../packaging-tasks/{id}/complete` (DEC-014 на complete — логика есть, pytest на complete отсутствует); полный e2e «seller plan → FF confirm → N коробов → full ship» при N>1 не проходим из-за S05

**Сводка по 9 сценариям:** works **5** (S01, S06, S07, S08, S09) · partial **4** (S02, S03, S04, S05) · broken **0**

**Продуктовый итог:** seller plan-only (DEC-015), inventory/collect/ship (DEC-006), без общего подбора (REQ-003), финал с ack недопоставки (DEC-012) и purge пустых коробов (DEC-002) — **готовы**. Ядро WB-like отгрузки на стороне ФФ **не готово к релизу** из‑за упаковки и batch-коробов.

---

## 2. Проверенные сценарии

> На `phase=init` — пусто. На каждом batch — append два блока (S01+S02, затем S03+S04, …).

### S01 — Селлер: черновик и план отгрузки на МП (plan-only)

**Что нужно пользователю:** Сформировать план отгрузки на МП (товары и количества), отправить заявку ФФ и видеть статус — без складских операций.

**Ожидаемый бизнес-результат:** Черновик → «Запланировано»; только свой ИП; нет коробов, упаковки, ship.

**Вердикт:** works

**Продуктовая оценка:** Селлерский путь закрывает DEC-015: один fullscreen-dialog с `data-testid="seller-mp-plan-only"`, таблица плана, WB-склад, дата, «Запланировать» / «Вернуть в черновик». Коробов, упаковки, scan ячеек и ship в UI нет. Backend режет ответ для роли seller (`seller_plan_only`: пустые `boxes`, `pick_allocations`, `linked_packaging_task=None`) и отдаёт 403 на box/ship/confirm. E2e и pytest подтверждают RBAC и plan-only.

**Путь по экранам (кратко):**
- Диалог «Отгрузка на маркetплейс» → помогает: статус русским текстом, таблица с остатком и qty, picker товаров | мешает: — | не хватает: явной подсказки «дальше ждите ФФ» после «Запланировано» (некритично)

**Связанные файлы:**
- `frontend/src/components/SellerMarketplaceUnloadDialog.tsx`
- `backend/app/api/marketplace_unload_requests.py` (`_seller_plan_only`, `_require_ff_execution`)
- `backend/tests/test_seller_marketplace_unload.py`
- `frontend/tests-e2e/seller-mp-unload.spec.ts`

**Проблемы:**
- [Желательно] `SellerMarketplaceUnloadDialog.tsx:671-674` — после submit показывается только статус «Запланировано», без короткой фразы «обработка на стороне фулфилмента» — селлер может не понять следующий шаг.

---

### S02 — ФФ: создание отгрузки, выбор ИП, план товаров

**Что нужно пользователю:** Создать отгрузку от имени ИП, набрать план товаров, увидеть связь с упаковкой, без отдельного «общего подбора».

**Ожидаемый бизнес-результат:** Черновик с выбранным seller_id; план в таблице; PackagingTask при create + sync строк; нет «Начать подбор».

**Вердикт:** partial

**Продуктовая оценка:** Backend соответствует DEC-003/DEC-008: `create_request` вызывает `ensure_task_for_unload`, add/update/delete line → `_sync_packaging_from_plan` (подтверждено pytest). FF-create требует выбор селлера (`ff-mp-create-seller-filter`, кнопка disabled без ИП). Кнопка «Начать подбор» из UI убрана. Но продуктово на черновике оператор **не видит** упаковку: вкладки «Упаковка» и «Короба» disabled до `status=confirmed`, alert упаковки тоже только после confirm; сводный счётчик «план/распределено» — только на вкладке «Короба». Требование «сразу после create видна упаковка» (REQ-004) в UI не выполнено, хотя задача в БД уже есть.

**Путь по экранам (кратко):**
- «Отгрузки на МП» → помогает: обязательный выбор ИП, «Создать отгрузку» | мешает: описание страницы всё ещё про «подбор по ячейкам» | не хватает: —
- Диалог документа, вкладка «Товары» → помогает: add by barcode/picker, колонка «План», seller_name | мешает: нет сводного «план отгрузки N шт» на черновике | не хватает: доступ к упаковке на draft
- Вкладки «Упаковка»/«Короба» → помогает: есть в структуре Tabs | мешает: `disabled={!mpConfirmed}` — недоступны на draft/submitted | не хватает: видимость linked packaging сразу после create

**Связанные файлы:**
- `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`
- `backend/app/services/marketplace_unload_service.py` (`create_request`, `_sync_packaging_from_plan`)
- `backend/app/services/packaging_task_service.py` (`ensure_task_for_unload`)
- `backend/tests/test_marketplace_unload_and_discrepancy_acts.py` (packaging at draft)
- `frontend/tests-e2e/ff-mp-tabs.spec.ts`

**Проблемы:**
- [Важно] `FfSuppliesShipmentsPage.tsx:1927-1934` — вкладки «Упаковка» и «Короба» заблокированы до confirm, хотя `linked_packaging_task` создаётся при create — оператор на черновике не видит задание упаковки и не понимает следующий шаг по цепочке ТЗ.
- [Важно] `FfSuppliesShipmentsPage.tsx:1875-1877` — прогресс упаковки (`ff-mp-packaging-progress`) показывается только при `mpConfirmed`; на draft/submitted индикатор отсутствует при уже существующей задаче.
- [Желательно] `FfSuppliesShipmentsPage.tsx:1616` — описание страницы: «короба, подбор по ячейкам» — устаревшая формулировка, вводит в заблуждение после удаления общего подбора.
- [Желательно] `FfSuppliesShipmentsPage.tsx:2113-2158` — сводные счётчики плана/распределения только на вкладке «Короба»; на черновике видна лишь колонка «План» по строкам, без aggregate «план отгрузки».

---

### S03 — Настройка «Адресное хранение» в ФФ

**Что нужно пользователю:** Админ решает, работает склад с ячейками или с агрегированными остатками; от этого зависит UX приёмки и отгрузки на МП.

**Ожидаемый бизнес-результат:** Переключатель в настройках; дефолт вкл.; при выкл. — нет scan ячеек; при вкл. — ячейка обязательна или зона сортировки; нельзя выключить при остатках на ячейках.

**Вердикт:** partial

**Продуктовая оценка:** Ядро REQ-001 реализовано: поле `tenants.address_storage_enabled` (default `true`), checkbox на `FfSettingsScreen`, значение в `/auth/me`, collect API через `resolve_collect_storage_location` (без ячейки при выкл., `location_required` при вкл. без location, зона сортировки через `get_or_create_sorting_location` при вкл.). UI отгрузки и приёмки скрывают ячейки при `addressStorageEnabled=false` (e2e `ff-address-storage-mp-ui`). **DEC-019 не реализован:** `update_tenant_settings` не проверяет остатки на ячейках — можно выключить адресное хранение при живом stock.

**Путь по экранам (кратко):**
- Настройки ФФ → «Склад» → помогает: checkbox с сохранением и alert «включено/выключено» | мешает: нет предупреждения о блокировке при остатках | не хватает: guard при toggle off
- Отгрузка на МП (выкл.) → помогает: label «Штрихкод товара / короба», нет chip ячейки | мешает: — | не хватает: —
- Отгрузка на МП (вкл.) → помогает: chip «Ячейка», scan ячейка→товар | мешает: — | не хватает: —

**Связанные файлы:**
- `backend/app/models/tenant.py`, `backend/app/services/tenant_settings_service.py`
- `backend/app/services/marketplace_unload_collect_service.py` (`resolve_collect_storage_location`)
- `frontend/src/screens/ff/FfSettingsScreen.tsx`, `FfSuppliesShipmentsPage.tsx`, `FfInboundRequestView.tsx`
- `backend/tests/test_tenant_settings.py`, `backend/tests/test_marketplace_unload_address_storage.py`
- `frontend/tests-e2e/ff-address-storage-setting.spec.ts`, `ff-address-storage-mp-ui.spec.ts`

**Проблемы:**
- [Важно] `tenant_settings_service.py:33-44` — PATCH `address_storage_enabled=false` не блокируется при ненулевых остатках на ячейках (DEC-019); админ может «сломать» учёт без миграции остатков.
- [Желательно] Нет пользовательского сообщения в UI настроек о том, почему выключение может быть опасно (даже после реализации guard).

---

### S04 — Упаковка: автосоздание, синк, завершение, ЧЗ

**Что нужно пользователю:** Упаковать товар до коробов: явное «Завершить упаковку», галочка «Весь товар упакован», ЧЗ-gate, переоткрытие при правке плана.

**Ожидаемый бизнес-результат:** Вкладка «Упаковка» с `FfPackagingTaskPanel`; sync строк; complete → read-only; ЧЗ не обходится; правка плана сбрасывает done.

**Вердикт:** partial

**Продуктовая оценка:** Backend: `ensure_task_for_unload` при create, `sync_lines_from_unload_plan` на CRUD линий, reopen при смене плана после done (pytest `test_packaging_reopens_when_unload_plan_changes`), endpoint `POST .../complete` с `acknowledge_all_packed` и `_assert_marking_done_for_task` (DEC-014 в коде). UI: `FfPackagingTaskPanel` с галочкой и кнопкой «Завершить упаковку» (`ff-packaging-complete`). Но: (1) вкладка «Упаковка» disabled до confirm — оператор не попадает на панель на ранних статусах; placeholder «появится после подтверждения» противоречит факту create-at-draft. (2) `_touch_task` по-прежнему ставит `STATUS_DONE` при `is_task_complete` после pack/confirm-line — упаковка может завершиться **без** нажатия «Завершить» и без прохождения ЧЗ-gate в `complete_task` (ЧЗ проверяется на ship через `assert_unload_packaging_done`, но UX REQ-005 нарушен). Нет pytest на `marking_not_done` при complete.

**Путь по экранам (кратко):**
- Вкладка «Упаковка» → помогает: встроен `FfPackagingTaskPanel`, ЧЗ/этикетки сохранены | мешает: tab disabled до confirm; текст «появится после подтверждения» | не хватает: доступ на draft при уже созданной задаче
- Панель complete → помогает: «Весь товар уже упакован» + «Завершить упаковку» | мешает: может стать read-only от авто-done до клика | не хватает: —
- После done → помогает: `taskEditable=false`, pack blocked (422) | мешает: — | не хватает: —

**Связанные файлы:**
- `backend/app/services/packaging_task_service.py` (`_touch_task`, `complete_task`, `sync_lines_from_unload_plan`)
- `backend/app/api/packaging_tasks.py`
- `frontend/src/screens/ff/FfPackagingPage.tsx` (`FfPackagingTaskPanel`)
- `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` (вкладка packaging)
- `backend/tests/test_packaging_tasks.py`
- `frontend/tests-e2e/ff-mp-packaging-gate.spec.ts`

**Проблемы:**
- [Критично] `packaging_task_service.py:142-143` — `_touch_task` авто-ставит `STATUS_DONE` при полном pack; обходит явное «Завершить упаковку» и ЧЗ-gate в `complete_task` (DEC-014 / REQ-005). Ship частично спасает `assert_unload_packaging_done`, но оператор не проходит осознанный шаг завершения.
- [Важно] `FfSuppliesShipmentsPage.tsx:1927-1928` — вкладка «Упаковка» disabled до confirm (пересечение с S02).
- [Важно] `FfSuppliesShipmentsPage.tsx:2107-2109` — misleading copy: упаковка уже есть в БД с create, но UI говорит «после подтверждения».
- [Желательно] Нет теста `marking_not_done` на `POST .../complete` с `acknowledge_all_packed=true` для маркированного товара.

---

### S05 — Короба: batch create, gate упаковки, модалка добавления

**Что нужно пользователю:** После упаковки создать N коробов и наполнять каждый через модалку с фото, лимитами и scan.

**Ожидаемый бизнес-результат:** N коробов в списке; «Добавить товары» у каждого; gate упаковки; лимит min(план, сток).

**Вердикт:** partial

**Продуктовая оценка:** Gate упаковки работает: backend `assert_unload_packaging_done` на collect/create box (422 `packaging_not_done`), UI блокирует кнопки (`mpPackagingGateActive`), модалка показывает «Сначала завершите упаковку товара». Модалка `FfMarketplaceUnloadBoxAddDialog` (maxWidth lg) с фото, план/в коробах/доступно, `addableQty = min(planRemaining, physical)` (DEC-020) — подтверждено e2e. **Но путь «N коробов» сломан:** `create_boxes_batch` создаёт короба с `closed_at=now`, API и UI отклоняют добавление в закрытый короб; кнопка «Добавить товары» disabled при `boxClosed`. Работает только count=1 → «Открыть короб» (legacy open-box + inline scan). Параллельные N коробов с независимым «Добавить товары» недостижимы.

**Путь по экранам (кратко):**
- Вкладка «Короба» → помогает: batch UI, preset, счётчики | мешает: при N>1 короба сразу «закрыты» | не хватает: открытых N коробов для модалки
- Модалка «Добавить товары» → помогает: фото, лимиты, scan ячейка→товар, gate message | мешает: недоступна для batch-коробов | не хватает: —
- Inline «Сборка в короба» → помогает: scan в один открытый короб | мешает: дублирует модалку, не WB-like «только модалка напротив короба» | не хватает: —

**Связанные файлы:**
- `frontend/src/screens/ff/FfMarketplaceUnloadBoxAddDialog.tsx`
- `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` (`createBox`, `renderBoxActions`, `ff-mp-boxes`)
- `backend/app/services/marketplace_unload_box_service.py` (`create_boxes_batch`, `create_open_box`)
- `backend/tests/test_packaging_tasks.py` (`test_box_create_blocked_until_packaging_done`)
- `frontend/tests-e2e/ff-mp-box-add-modal.spec.ts`, `ff-mp-packaging-gate.spec.ts`

**Проблемы:**
- [Критично] `marketplace_unload_box_service.py:167-179` + `226-227`, `286-287` — batch создаёт **закрытые** короба; `scan`/`manual-line` → `box_closed`; пользователь не может наполнить N коробов (REQ-007/008).
- [Критично] `FfSuppliesShipmentsPage.tsx:1048` — «Добавить товары» disabled для `boxClosed`; batch-короба всегда closed → кнопка мёртвая.
- [Важно] `FfSuppliesShipmentsPage.tsx:705-729` — count=1 идёт в legacy `create_open_box` (один открытый короб); `open_box_exists` блокирует второй — не модель «N независимых коробов».
- [Желательно] На вкладке «Короба» нет Alert при gate — только disabled-кнопки; текст «Сначала завершите…» только в модалке (e2e проверяет disabled, не copy на tab).

---

### S06 — Добавление в короб и списание остатков

**Что нужно пользователю:** При добавлении в короб остаток и резерв меняются сразу; ship без повторного списания; cancel откатывает.

**Ожидаемый бизнес-результат:** collect → `on_hand`↓, reserve↓; ship → только статус; cancel → stock восстановлен.

**Вердикт:** works

**Продуктовая оценка:** DEC-006 реализован: `collect_into_box` вызывает `apply_marketplace_unload_pick` + `reduce_reservation_for_collect` под `FOR UPDATE` на request/allocation; `ship_request` не вызывает повторное списание (pytest `test_marketplace_unload_ship_no_double_inventory_movement`). `remove_from_box` откатывает на исходные ячейки через `_rollback_pick_allocations` + `reverse_marketplace_unload_pick` + `restore_reservation_for_remove`. Cancel (TASK-019) очищает короба и резервы; суммарный остаток склада восстанавливается (pytest `test_marketplace_unload_cancel_partial_distribution_restores_inventory`). Параллельный collect защищён (`test_marketplace_unload_concurrent_collect_same_location`). Нюанс: cancel возвращает qty в **зону сортировки**, не в исходную ячейку — тест это фиксирует как ожидаемое; для оператора total stock OK, но адресный след меняется.

**Путь по экранам (кратко):**
- (UI косвенно через модалку/scan) → помогает: после add виден состав короба и счётчики | мешает: — | не хватает: явной индикации «остаток списан» в UI

**Связанные файлы:**
- `backend/app/services/marketplace_unload_collect_service.py` (`collect_into_box`, `remove_from_box`, `rollback_all_collected_for_cancel`)
- `backend/app/services/marketplace_unload_pick_service.py` (`ship_request`)
- `backend/app/services/marketplace_unload_service.py` (`reduce_reservation_for_collect`, `cancel_request`)
- `backend/app/services/inventory_service.py` (`apply_marketplace_unload_pick`, `_lock_inventory_balance`)
- `backend/tests/test_marketplace_unload_and_discrepancy_acts.py` (no double, cancel, concurrent)

**Проблемы:**
- [Желательно] `marketplace_unload_collect_service.py:469-505` — cancel откатывает в sorting location, не в исходную ячейку collect; total qty восстанавливается, но адресный учёт смещается (осознанное решение TASK-019, не блокер ship).
- [Желательно] В UI нет явного feedback «остаток уменьшен» после add — оператор видит только состав короба.

---

### S07 — Без этапа «общий подбор в документ»

**Что нужно пользователю:** Не подбирать товар в отгрузку отдельно — только план и добавление в конкретный короб.

**Ожидаемый бизнес-результат:** Нет «Начать подбор», модалки ручного подбора, счётчика «подобрано в документ»; складской путь только через короб.

**Вердикт:** works

**Продуктовая оценка:** Legacy UI удалён: в `FfSuppliesShipmentsPage` нет `ff-mp-start-picking`, `ff-mp-picking-dialog`, блока `ff-mp-pick-saved` (e2e TC-NEW-MP-005). Счётчики переименованы в «План / Распределено по коробам / Осталось» (`mpCollectSummary`, колонки на вкладке «Товары»). `pick_allocations` в API остаётся как побочный эффект `collect_into_box` и для печати накладной — отдельного блока подбора в UI нет. `PUT .../pick-allocations` — только `FULFILLMENT_ADMIN`, без UI (pytest `test_marketplace_unload_pick_allocations_admin_only`). Складской collect идёт только в короб (inline scan при открытом коробе или модалка «Добавить товары»).

**Путь по экранам (кратко):**
- Документ отгрузки → помогает: нет кнопки «Начать подбор» | мешает: описание страницы всё ещё «подбор по ячейкам» | не хватает: —
- Вкладка «Короба» → помогает: сборка только в короб (scan/modal) | мешает: inline scan дублирует модалку, но всё равно в короб | не хватает: —

**Связанные файлы:**
- `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`
- `backend/app/api/marketplace_unload_requests.py` (`PUT pick-allocations` admin-only)
- `backend/tests/test_marketplace_unload_and_discrepancy_acts.py` (`test_marketplace_unload_pick_allocations_admin_only`)
- `frontend/tests-e2e/ff-address-storage-mp-ui.spec.ts`, `ff-mp-ship-pick.spec.ts`

**Проблемы:**
- [Желательно] `marketplace_unload_requests.py:1065-1094` — `PUT pick-allocations` всё ещё существует для admin (legacy); не виден в UI, но технически позволяет обойти «только через короб» при прямом API.
- [Желательно] `FfSuppliesShipmentsPage.tsx:2170-2248` — inline-блок «Сборка в короба» параллелен модалке; не нарушает REQ-003, но UX не «только кнопка напротив короба».
- [Желательно] `FfSuppliesShipmentsPage.tsx:1616` — устаревшее описание страницы про «подбор по ячейкам».

---

### S08 — Счётчики, предупреждения, меню короба

**Что нужно пользователю:** Видеть прогресс распределения, предупреждение при недопоставке, действия с коробом (ШК, копия, удаление пустого), откат строки.

**Ожидаемый бизнес-результат:** X из Y по **товарам**; warning на «Короба»; меню короба; delete только пустого; remove line откатывает stock.

**Вердикт:** works

**Продуктовая оценка:** Счётчики на вкладке «Короба»: `planned` / `distributed` (sum `picked_qty` по строкам плана) / `remaining` + статус упаковки (`ff-mp-collect-summary-*`). При `remaining > 0` — `Alert` `ff-mp-collect-warning` (e2e `ff-mp-tabs`). Меню короба: печать ШК (`printBoxBarcode`), копия (`POST .../copy` с plan limit), удаление (`DELETE` → `box_not_empty` если qty>0) — pytest `test_marketplace_unload_box_*` блок. UI: icon delete disabled при `totalQty > 0`; remove line с откатом inventory (тест: qty 15→13→15). Copy создаёт новый короб с тем же составом в пределах плана; повтор copy блокируется `plan_limit_exceeded`.

**Путь по экранам (кратко):**
- «Короба» → помогает: сводка план/распределено/остаток, warning, меню ⋮ | мешает: сводка только после confirm | не хватает: —
- Строка короба → помогает: ШК, удаление пустого, remove line | мешает: copied/batch короба closed — edit только через remove | не хватает: —

**Связанные файлы:**
- `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` (`mpCollectSummary`, box menu, `removeBoxLine`)
- `backend/app/services/marketplace_unload_box_service.py` (`copy_box`, `delete_box`, `remove_box_line`)
- `backend/tests/test_marketplace_unload_and_discrepancy_acts.py` (box ops test ~L1780)
- `frontend/tests-e2e/ff-mp-tabs.spec.ts`

**Проблемы:**
- [Желательно] `marketplace_unload_box_service.py:574` — copy создаёт **закрытый** короб; добавить в него нельзя без remove (пересечение с S05, для copy-сценария приемлемо).
- [Желательно] Сводка и warning видны только на вкладке «Короба» и только при `confirmed` — до confirm оператор не видит прогресс распределения.

---

### S09 — Финальная отгрузка: ШК, ship, недопоставка

**Что нужно пользователю:** На вкладке «Финальная отгрузка» указать дату и склад WB, напечатать все ШК коробов, отгрузить; при недопоставке — явное подтверждение; пустые короба удаляются; без полей водитель/машина.

**Ожидаемый бизнес-результат:** `planned_shipment_date` + `wb_mp_warehouse_id` → «Печать всех ШК» → «Отгрузить» → `shipped`; при `remaining > 0` — диалог `acknowledge_discrepancy`; пустые короба не уезжают (DEC-002); без driver/vehicle (DEC-004).

**Вердикт:** works

**Продуктовая оценка:** Вкладка «Финальная отгрузка» (`ff-mp-tab-final-shipment`): поля даты (`ff-mp-planned-shipment-date`) и склада WB (`ff-mp-wb-warehouse`, список из `GET /integrations/wildberries/mp-warehouses`), кнопки «Печать всех ШК» (`ff-mp-print-all-box-barcodes`, disabled без коробов) и «Отгрузить» (`ff-mp-ship`, disabled без даты/склада). Ship: `POST .../ship` с `planned_shipment_date`, `wb_mp_warehouse_id`, `acknowledge_discrepancy`. Backend `ship_request`: без ack при `remaining > 0` → 422 `distribution_incomplete` (pytest); с ack → 200, `status=shipped`, inventory не списывается повторно (S06). Перед ship — `delete_empty_boxes_for_ship` (DEC-002, тест ~L1272). Полей водитель/машина нет (DEC-004). UI: при 422 открывается `ff-mp-ship-discrepancy-dialog` с `remaining` и чекбоксом подтверждения → повтор ship с ack (e2e `ff-mp-ship-pick.spec.ts`). После ship — read-only, вкладки упаковка/короба скрыты.

**Путь по экранам (кратко):**
- «Финальная отгрузка» → помогает: дата, склад, массовая печать ШК, ship с ack при недопоставке | мешает: вкладка disabled до `confirmed` | не хватает: —
- Диалог недопоставки → помогает: явное подтверждение DEC-003 | мешает: — | не хватает: —

**Связанные файлы:**
- `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` (final tab, ship, discrepancy dialog, print all)
- `backend/app/services/marketplace_unload_pick_service.py` (`ship_request`)
- `backend/app/services/marketplace_unload_service.py` (`delete_empty_boxes_for_ship`)
- `backend/tests/test_marketplace_unload_and_discrepancy_acts.py` (ship blocked/ack, empty box purge)
- `frontend/tests-e2e/ff-mp-ship-pick.spec.ts`, `ff-mp-print-waybill.spec.ts`

**Проблемы:**
- [Желательно] Вкладка «Финальная отгрузка» недоступна до seller confirm — оператор не может заранее заполнить дату/склад (пересечение с S02).
- [Желательно] Массовая печать ШК требует хотя бы один короб; при batch N≥2 closed boxes печать работает, но наполнение сломано (S05) — к ship часто не дойти с полным планом.

---

## 3. Несоответствия артефактам

> `phase=final` (2026-06-27)

| Требовалось (01–03) | Реализовано | Почему проблема | Где в коде |
|---------------------|-------------|-----------------|------------|
| DEC-003 / REQ-004: упаковка видна сразу после create draft | `PackagingTask` создаётся при create, но вкладка «Упаковка» disabled до `confirmed` | Оператор не видит задание упаковки на черновике; текст «появится после подтверждения» противоречит БД | `FfSuppliesShipmentsPage.tsx` (~1927, ~2107); backend `ensure_task_for_unload` OK |
| REQ-005 / DEC-014: явное «Завершить упаковку» + ЧЗ-gate на complete | `_touch_task` ставит `STATUS_DONE` при полном pack строк | Обход кнопки «Завершить» и `_assert_marking_done_for_task` в `complete_task`; ship частично спасает `assert_unload_packaging_done`, но UX и контроль оператора нарушены | `packaging_task_service.py:142-143` |
| REQ-007 / REQ-008: N коробов, «Добавить товары» у каждого | `create_boxes_batch` ставит `closed_at=now`; add в closed → `box_closed` | Типовой путь «создал 3 короба → наполнил каждый модалкой» недостижим; работает только count=1 + open box | `marketplace_unload_box_service.py` (~167-179, ~226-227); `FfSuppliesShipmentsPage.tsx:1048` |
| DEC-019: нельзя выключить адресное хранение при остатках на ячейках | PATCH `address_storage_enabled=false` без проверки stock | Админ может сломать адресный учёт без миграции | `tenant_settings_service.py:33-44` |
| DEC-010 / REQ-011: прогресс до confirm (операционная прозрачность) | Сводка/warning только на «Короба» при `confirmed` | До confirm оператор не видит «распределено X из Y» и предупреждение | `FfSuppliesShipmentsPage.tsx` (`mpCollectSummary`, `ff-mp-collect-warning`) |
| REQ-003 / GAP-003: без «общего подбора» | UI picking удалён | Описание страницы всё ещё «подбор по ячейкам» — вводит в заблуждение | `FfSuppliesShipmentsPage.tsx:1616` |
| DEC-012: ship при недопоставке с ack | Реализовано (422 → dialog → ack) | — | `marketplace_unload_pick_service.py`; `ff-mp-ship-discrepancy-dialog` |
| DEC-015: seller plan-only | Реализовано | — | `SellerMarketplaceUnloadDialog.tsx`; `_seller_plan_only` |

---

## 4. Сквозные проблемы

> Подтверждённые повторы в 2+ сценариях. `phase=final`.

1. **Вкладки «Упаковка» / «Короба» / «Финал» disabled до seller confirm** (S02, S04, S05, S08, S09) — backend уже создаёт упаковку и резервы по другим правилам; UI отстаёт от DEC-003 и скрывает следующий шаг оператора.
2. **Misleading copy «упаковка появится после подтверждения»** (S02, S04) — задача упаковки уже в БД с create; оператор думает, что упаковки нет.
3. **Устаревшее описание страницы «подбор по ячейкам»** (S02, S07) — после удаления общего подбора формулировка не соответствует REQ-003.
4. **Closed boxes как побочный эффект batch/copy** (S05, S08) — copy box и batch create закрывают короб; «Добавить товары» мёртва; copy-сценарий терпим, batch N≥2 — нет.
5. **Gate упаковки vs auto-done** (S04, S05) — UI/backend gate требует `packaging done`, но `_touch_task` может завершить упаковку неявно; оператор не понимает, завершил ли он этап осознанно.

---

## 5. Обязательные правки перед релизом

> Только блокеры. `phase=final`.

1. **Убрать авто-завершение упаковки в `_touch_task`** — где: `backend/app/services/packaging_task_service.py:142-143` — почему блокер: нарушает REQ-005 / DEC-014; оператор не нажимает «Завершить упаковку»; ЧЗ-gate на `complete_task` обходится; gate «сначала упаковка» теряет смысл как продуктовый контроль.
2. **Batch create коробов — открытые короба (без `closed_at`)** — где: `backend/app/services/marketplace_unload_box_service.py` (`create_boxes_batch`, ~167-179) + проверить UI `FfSuppliesShipmentsPage.tsx:1048` — почему блокер: REQ-007/008; основной WB-like сценарий «N коробов + модалка» не работает; e2e `ff-mp-box-add-modal` покрывает count=1/open path, не N≥2 batch.

**Критерий повторного прогона:** S04 → `partial`→`works` после fix #1 + pytest на complete/ЧЗ; S05 → `partial`→`works` после fix #2 + pytest/e2e на batch N≥2 с add через модалку.

---

## 6. Улучшения после релиза

> Некритичное. `phase=final`.

- **DEC-019:** guard при `address_storage_enabled=false` если на ячейках есть остаток (`tenant_settings_service.py`) + сообщение в `FfSettingsScreen`
- **UX draft:** показывать вкладку «Упаковка» (read-only или editable) на draft/submitted при наличии `linked_packaging_task`; убрать/исправить placeholder «после подтверждения»
- **Copy:** обновить описание `FfSuppliesShipmentsPage` (~1616) — убрать «подбор по ячейкам»
- **Seller:** подсказка после «Запланировано» — «дальше обработка на стороне фулфилмента» (`SellerMarketplaceUnloadDialog.tsx`)
- **Сводка прогресса:** счётчики план/распределено на черновике или на вкладке «Товары», не только после confirm
- **Legacy API:** `PUT .../pick-allocations` admin-only — документировать deprecated или удалить в отдельной задаче
- **Cancel inventory:** откат в sorting zone vs исходная ячейка — зафиксировать в docs/DATA_FLOW если осознанно
- **Тесты:** pytest `marking_not_done` на `POST .../complete`; e2e полный путь seller→FF→N коробов→ship
- **Alert на вкладке «Короба»** при packaging gate (сейчас только disabled-кнопки и текст в модалке)
