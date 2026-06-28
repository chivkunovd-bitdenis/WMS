# TASKLOG

## TASK-051 — 2026-06-28 — BACKEND-01: deprecate scan-print / print-all / verify-pair

- What changed: `marking_codes.py` — `deprecated=True` + summary on `POST /scan-print`, `/verify-pair`, `/packaging-tasks/{id}/print-all`; comment BACKEND-01 / T-A6 (ORD-44).
- What did NOT change: endpoint behaviour, per-line print (`/packaging-lines/{line_id}/print`), service layer.
- Verification: `ruff check app/api/marking_codes.py`; `mypy app/api/marking_codes.py`; `pytest tests/ -q -k marking` — 50 passed; all three routes `deprecated=True` in OpenAPI. Commit `d82fe3c`.

## TASK-036 — 2026-06-28 — CZ-000 barrier: MP commit + feat/cz-ux-fixes + autopilot backlog

- What changed:
  - **CZ-000 done:** MP slice committed `304abf2` on `hotfix/alembic-marking-pools`; branch **`feat/cz-ux-fixes`** created.
  - **Autopilot:** `.cursor/hooks`, `wms-queue.mdc`, `docs/PARALLEL_AGENT_TASKS.md`, `CURSOR_QUEUE_LANES_RU.md`, CZ backlog docs.
  - **`PARALLEL_AGENT_TASKS.md`:** CZ-000 marked done; agents may start PACK/PRINT/… lanes.
- What did NOT change: lane tasks (PACK-01…); orchestrator lives in `~/.cursor/agents/orchestrator.md`.
- Verification: `git status` clean on `feat/cz-ux-fixes`.

## TASK-035 — 2026-06-28 — Queue lanes: files, depends_on, lane scheduling doc

- What changed:
  - **`docs/CURSOR_QUEUE_LANES_RU.md`** — справка для человека и orchestrator (атрибуты lane/files/depends_on, правила параллели, примеры, resume).
  - **`orchestrator.md`**, **`wms-queue.mdc`**, **`QUEUE.md`** — планирование по lanes; ссылка на справку (не alwaysApply).
  - **`.cursor/skills/queue-lanes/SKILL.md`** — короткий указатель на справку.
  - Orchestrator queue: **1 задача = 1 builder**, `parallel_workers` от владельца.
- What did NOT change: содержимое backlog (владелец вставит в QUEUE).
- Verification: docs-only.

## TASK-034 — 2026-06-28 — Backlog autopilot: orchestrator queue mode, QUEUE, stop hook

- What changed:
  - **`~/.cursor/agents/orchestrator.md`** — режим очереди: 4×3 parallel builder, builder→verifier→fix (max 3), ` done` только после verifier.
  - **`backlog-runner.md`** — stub → redirect на orchestrator queue mode.
  - **`.cursor/QUEUE.md`** — очередь (формат: `ID — описание` / `… done` / `… blocked`).
  - **`.cursor/SESSION_HANDOFF.md`** — handoff между пачками.
  - **`.cursor/rules/wms-queue.mdc`** — правила queue mode.
  - **`.cursor/hooks.json` + `continue-queue.sh`** — auto follow-up пока в QUEUE есть открытые задачи.
- What did NOT change: orchestrator (режим одной фичи); backlog tasks — владелец вставит в QUEUE.
- Verification: hook script exits `{}` on empty queue; `chmod +x` on continue-queue.sh.

## TASK-033 — 2026-06-28 — MP-032…034: parallel full-flow e2e, ship UI gate, canonical docs

- What changed:
  - **MP-032:** `ff-mp-full-flow.spec.ts` — TC-NEW-MP-FULL-001: boxes filled **before** packaging complete, then pack → ship from footer.
  - **MP-033:** `FfSuppliesShipmentsPage` — **«Отгружено»** disabled until `linked_packaging_task` done (`mpPackagingComplete`); guard in `requestShipMpUnload`.
  - **MP-034:** docs — superseded banners on `02`/`03`; `MVP_DECISIONS_RU` MP packaging; `DATA_FLOW.md` lifecycle; `01_normalized_process_spec` implementation status; `IMPLEMENTED_PRODUCT_SCENARIOS_*` §17 + updated S16 cases.
- What did NOT change: MP-024…031 (already in REV-FIX / prior tasks); `04_release_implementation_review.md` historical snapshot.
- Verification: e2e `ff-mp-full-flow`, `ff-mp-packaging-gate`, `ff-mp-tabs` — 5 passed; backend pytest batch/ship subset — 9 passed.

## TASK-032 — 2026-06-28 — MP-021…023: единый конструктор печати на упаковке MP

- What changed:
  - **MP-021:** иконка печати на вкладке «Упаковка» MP → `MarkingPrintDialog` (не `ProductBarcodePrintDialog`); печать убрана с вкладки «Товары».
  - **MP-022:** поле «Этикеток на каждый товар»; для товаров без ЧЗ — только пресеты этикеток, без блоков ЧЗ.
  - **MP-023:** `applyLabelsPerProductToLayout` / `countTapeBlocks` — lpp умножает только label-блоки (A-002); полная лента через `printMarkingCodeTape`.
- What did NOT change: MP-024…034 (settings, docs polish).
- Verification: `npm run test:unit -- markingPrintPresets` — 4 passed; e2e `ff-mp-packaging-print` — 1 passed; e2e `ff-mp-full-flow`, `ff-mp-tabs`, `ff-marking-print-constructor`, `ff-marking-packaging` — green; `npm run build` ok.

## TASK-031 — 2026-06-28 — MP-018 + MP-020: модалка pick/scan, главный scan только WHB

- What changed:
  - **MP-018:** модалка «Добавить товары» — dropdown ячейки, scan товара/ячейки/WHB; backend `collect_ready_box_into_open_box` + `kind: ready_box` в scan API; confirm/over-plan для WHB в модалке; убран `packagingGateActive`.
  - **MP-020:** главный scan на «Товарах» — только WHB/INB; товар/ячейка → сообщение «используйте Добавить товары»; e2e TC-NEW-MP-015.
- What did NOT change: MP-021…034 (печать, docs polish).
- Verification: `pytest tests/test_marketplace_unload_tsd_scan_contract.py` — 6 passed; e2e `ff-mp-box-add-modal` — 4 passed; e2e `ff-mp-tabs` — 3 passed; e2e `ff-mp-full-flow` — 1 passed; `npm run build` ok.

## TASK-030 — 2026-06-28 — MP-015…020: batch open boxes, e2e parallel, attach over-plan, WHB scan

- What changed:
  - **MP-015:** подтверждено — `create_boxes_batch` с `closed_at=NULL`; pytest batch green.
  - **MP-016:** e2e `ff-mp-box-add-modal` — 3 короба **без** complete packaging (параллельный flow).
  - **MP-017:** подтверждено — UI всегда `/boxes/batch`; pytest one-by-one + e2e TC-NEW-MP-022 green.
  - **MP-019:** `allow_over_plan` в collect/attach API; UI confirm «Весь короб» + «Больше плана»; pytest `test_marketplace_unload_attach_allow_over_plan`.
  - **MP-020:** главный scan на «Товарах» — только WHB attach; ячейка/товар → модалка короба; кнопка «Закрыть» на строке открытого короба.
- What did NOT change: MP-018 (WHB attach в модалке короба), MP-021…034, MP-020 dedicated e2e (product barcode на главном scan).
- Verification: `pytest -k "batch or attach_allow_over"` — 4 passed; `npm run build` ok; e2e `ff-mp-box-add-modal` + `ff-mp-packaging-gate` — 4 passed.

## TASK-029 — 2026-06-28 — MP-010/011/013: 2 вкладки, короба на «Товарах», footer ship

- What changed:
  - **MP-010:** убраны вкладки `ff-mp-tab-boxes` и `ff-mp-tab-final`; остались только «Товары» и «Упаковка».
  - **MP-011:** блок коробов (`ff-mp-boxes`), сводка распределения, scan/batch — на вкладке «Товары» после confirm.
  - **MP-013:** «Утвердить» / «Отгружено» / «Отменить» — в footer (`ff-mp-footer-bar`); дата/WB/печать на «Товарах».
- What did NOT change: MP-012 (full re-check), MP-015+.
- Verification: `npm run build` ok; e2e `ff-mp-tabs`, `ff-mp-full-flow`, `ff-mp-box-add-modal`, `ff-mp-print-waybill`, `ff-mp-packaging-gate`, `ff-dashboard` — green.

## TASK-029b — 2026-06-28 — MP-014: шапка документа (склад ФФ + дата + WB)

- What changed: `ff-mp-doc-header-fields` — дата (`ff-mp-planned-date`), склад ФФ (`ff-mp-ff-warehouse-name`), WB select/readonly; убрано дублирование с вкладки «Товары».
- Verification: e2e draft test asserts header testids; build green.

## TASK-028 — 2026-06-28 — MP-unload Phase A + frontend unblock (MP-001…009, MP-006…008, MP-012 partial)

- What changed:
  - **MP-001:** статус `collecting` («На сборке») — переход при первом коробе/collect/attach; ship из `collecting`; label в UI.
  - **MP-002/MP-009:** подтверждено — упаковка `done` только через `complete_task`; pytest marking_not_done green.
  - **MP-003:** `PackagingTask` только после confirm; draft без `linked_packaging_task`; GET by-unload → 404 без task.
  - **MP-004:** MP pack — счётчик `qty_packed` без `apply_packaging_convert`.
  - **MP-005:** снят gate упаковки с create/collect/batch коробов (остался на ship).
  - **MP-006/007/008:** UI — убран packaging gate; колонка «На полке упак.» скрыта для MP task; pack без ячейки.
  - **MP-012 (partial):** плашка прогресса не на draft; «Продолжить упаковку» только на вкладке «Упаковка».
- What did NOT change: MP-010…014 (2 вкладки, footer ship), MP-015…034, MP-021…023 (печать).
- Verification: backend `pytest tests/test_packaging_tasks.py` + MP sync/box tests — 12 passed; e2e `ff-mp-packaging-gate.spec.ts`, `ff-mp-tabs.spec.ts` (draft banner) — green; `npm run build` — ok.
- Commit: bdf297e (includes CZ P0/P1 marking fixes in same slice)

## TASK-027 — 2026-06-27 — CI mypy green for outbound-rework PR

- What changed: mypy fixes — optional `storage_location_id` в collect API/services; marking imports (`LAYOUT_BLOCK_CZ`, `STATUS_AVAILABLE`, `EVENT_PRINTED`); rename query param `code_status` (shadow `status`); typed seller scope in print-templates.
- What did NOT change: product behavior; e2e scenarios.
- Verification: `mypy .` — Success; `pytest -q` — 224 passed; PR #47 CI — backend + e2e + pr-quality + tc-coverage all pass.
- Commit: 39268c4

## TASK-026 — 2026-06-27 — REV-FIX-019, 020

- What changed:
  - **REV-FIX-019:** e2e `ff-mp-full-flow.spec.ts` (TC-NEW-MP-FULL-01): seller plan → FF confirm → packaging UI → batch 2 короба → fill → ship full plan; green.
  - **REV-FIX-020:** sanity docs — REQ-001 дополнен DEC-019 (миграция, не block); журнал батчей S03 в `04_release_manifest.md`; manifest S02/S04/S05 → works.
  - **CI fixes:** ruff (duplicate test rename, line length); `complete_task` billing order (finalize before skip guard); `test_staff_packaging_billing` — billing после explicit complete.
- What did NOT change: `04_release_implementation_review.md` (исторический снимок review).
- Verification: `npm run test:e2e -- ff-mp-full-flow.spec.ts` — 1 passed; grep DEC-019 в spec/MVP/manifest — канон «миграция на зону сортировки, toggle не блокируется».
- Commit: e6913ec

## TASK-025 — 2026-06-27 — REV-FIX-014 … 018 (P2)

- What changed:
  - **REV-FIX-014:** зафиксирован MVP — plan total на «Товары» (draft), collect summary/warning только после confirm на «Короба»; комментарии в UI; регрессия ff-mp-tabs green.
  - **REV-FIX-015:** docstring `copy_box` (closed by design); `docs/DATA_FLOW.md` — copy box; pytest `test_marketplace_unload_box_remove_copy_delete` green.
  - **REV-FIX-016:** `PUT .../pick-allocations` помечен `deprecated=True` + docstring admin-only; pytest green.
  - **REV-FIX-017:** cancel → sorting zone в `docs/DATA_FLOW.md`; pytest `-k cancel` green.
  - **REV-FIX-018:** Snackbar `ff-mp-box-add-success-snackbar` «Добавлено N шт» после add в короб; e2e ff-mp-box-add-modal green.
- What did NOT change: REV-FIX-019 (full-flow e2e), REV-FIX-020 (docs — уже в TASK-024).
- Verification: e2e ff-mp-tabs, ff-mp-box-add-modal; pytest copy + cancel + pick_allocations.
- Commit: e6913ec

## TASK-024 — 2026-06-27 — REV-FIX-004, 020, 011–013

- What changed:
  - **REV-FIX-004:** info Alert `ff-settings-address-storage-migration-info` при выключении адресного хранения; e2e green.
  - **REV-FIX-020:** DEC-019 → миграция на зону сортировки в `01_normalized_process_spec.md`, `MVP_DECISIONS_RU.md`, `04_release_manifest.md`.
  - **REV-FIX-011:** subtitle «Отгрузки на МП» без «подбор по ячейкам»; e2e assert.
  - **REV-FIX-012:** Alert `seller-mp-ff-handoff-hint` после «Запланировано»; e2e green.
  - **REV-FIX-013:** `ff-mp-plan-total` на вкладке «Товары» черновика; e2e assert.
- What did NOT change: REV-FIX-014+ (P2 docs/UX).
- Verification: e2e ff-address-storage-setting, ff-mp-tabs, seller-mp-unload green.
- Commit: e6913ec

## TASK-023 — 2026-06-27 — REV-FIX P1 (007–010, 009)

- What changed:
  - **REV-FIX-007:** убран misleading copy «появится после подтверждения»; empty/created states на вкладке упаковки; e2e assert.
  - **REV-FIX-008:** `ff-mp-packaging-progress` виден на draft при `linked_packaging_task`; e2e assert.
  - **REV-FIX-010:** Alert `ff-mp-packaging-gate-alert` на вкладке «Короба» при gate; e2e assert.
  - **REV-FIX-009:** batch API count≥1; UI всегда `/boxes/batch`; batch-create виден при открытых коробах; pytest one-by-one + e2e TC-NEW-MP-022.
- What did NOT change: REV-FIX-003+ (DEC-019 migration), P2 copy/docs.
- Verification: e2e ff-mp-tabs, ff-mp-packaging-gate, ff-mp-box-add-modal (two single-box); pytest create_boxes_batch*.
- Commit: e6913ec

## TASK-022 — 2026-06-27 — REV-FIX P0/P1 (001–006, 002a, 005)

- What changed:
  - **REV-FIX-001:** убран авто-`done` из `_touch_task`; gate `assert_unload_packaging_done` требует `status=done`; pytest explicit complete.
  - **REV-FIX-002:** batch-короба создаются открытыми (`closed_at=NULL`); pytest batch + manual-line.
  - **REV-FIX-002a:** UI — список всех открытых коробов; e2e TC-NEW-MP-021 batch 3 → add на 2-м коробе.
  - **REV-FIX-005:** pytest `marking_not_done` на `POST .../complete`.
  - **REV-FIX-006:** вкладка «Упаковка» enabled при `linked_packaging_task` (draft); e2e draft packaging tab.
- What did NOT change: REV-FIX-007+ (copy, progress на draft, DEC-019 migration).
- Verification: pytest packaging_tasks + batch; e2e ff-mp-box-add-modal + ff-mp-tabs green.
- Commit: e6913ec

## TASK-021 — 2026-06-27 — DEC-012 недопоставка + отмена на сортировку

- What changed: ship с `acknowledge_discrepancy` при распределено < план; UI диалог «Отгрузить неполную»; кнопка «Отменить отгрузку» на FF; cancel возвращает товар на **сортировку** (не на исходные ячейки); pytest partial ship + cancel/sorting.
- What did NOT change: DEC-019 (блок toggle) — по решению владельца не нужен; выключение адресного → перенос на виртуальную ячейку (отдельная задача).
- Verification: pytest ship ack + cancel sorting; build green.
- Commit: e6913ec

## TASK-020 — 2026-06-27 — Селлер plan-only (DEC-015)

- What changed: `_require_ff_execution` — seller 403 на короба/ship/confirm/cancel/pick; GET detail без boxes/pick_allocations/packaging для seller; `SellerMarketplaceUnloadDialog` — status cancelled, `seller-mp-plan-only`; pytest seller guards; e2e TC-NEW-MP-020.
- What did NOT change: FF вкладки; seller plan/unplan/lines draft.
- Verification: pytest seller test; e2e seller-mp-unload green; ruff.
- Commit: e6913ec

## TASK-019 — 2026-06-27 — Отмена отгрузки → откат инвентаря (DEC-016)

- What changed: `POST .../cancel`; `cancel_request` + `rollback_all_collected_for_cancel`; status `cancelled`; pytest partial distribution cancel restores stock and clears reserves/box lines.
- What did NOT change: UI кнопка отмены (FF); seller cancel (403 via TASK-020).
- Verification: pytest `test_marketplace_unload_cancel_partial_distribution_restores_inventory`; ruff.
- Commit: e6913ec

## TASK-018 — 2026-06-27 — API-контракт scan-потока для ТСД

- What changed: `POST .../boxes/{box_id}/scan` — единый flow location→product (`kind` в ответе); код ошибки `plan_limit_exceeded`; `pick/scan` deprecated; doc `docs/API_MP_UNLOAD_SCAN_TSD_RU.md`; pytest `test_marketplace_unload_tsd_scan_contract.py`; UI modal/box scan на один endpoint.
- What did NOT change: мобильный клиент; seller parity.
- Verification: pytest tsd contract + unload suite; e2e ff-mp-box-add-modal (after build).
- Commit: e6913ec

## TASK-017 — 2026-06-27 — E2E tests отгрузки на МП

- What changed: e2e `ff-mp-packaging-gate.spec.ts` (TC-NEW-MP-008) — UI/API gate до упаковки; комментарий TASK-017 в `ff-mp-ship-pick`; ship без ack body (TASK-015).
- What did NOT change: seller-mp-unload UI parity, ff-mp-print-waybill.
- Verification: e2e ff-mp-packaging-gate + ff-mp-ship-pick + ff-mp-tabs + ff-mp-box-add-modal green.
- Commit: e6913ec

## TASK-016 — 2026-06-27 — Backend tests marketplace unload

- What changed: pytest packaging gate before box/batch; ship rejects empty boxes (`distribution_incomplete`); seller test order упаковка→короба; batch test clarifies count=1 validation.
- What did NOT change: pick-allocations admin-only test (legacy admin path).
- Verification: pytest 32 passed (unload + address_storage + seller + packaging).
- Commit: e6913ec

## TASK-015 — 2026-06-27 — Рефактор ship_request после переноса списания

- What changed: `ship_request` без `acknowledge_discrepancy` и без pick_allocations; проверка `distribution_incomplete` по коробам (DEC-010); `wb_mp_warehouse_required` на ship; API ship без body; UI/e2e без ack body; pytest + packaging test через manual-line в короб.
- What did NOT change: seller parity, DEC-012 partial ship path.
- Verification: pytest 25 passed (unload + packaging); e2e ff-mp-ship-pick + ff-mp-tabs.
- Commit: e6913ec

## TASK-014 — 2026-06-27 — Финальная вкладка: печать ШК и gate ship

- What changed: кнопка «Печать всех ШК коробов» на вкладке «Финал»; ship блокируется при `remaining > 0` (UI + без confirm расхождения); pytest `test_marketplace_unload_ship_blocked_when_distribution_incomplete`; e2e ship disabled в `ff-mp-tabs`.
- What did NOT change: refactor ship_request pick_allocations (TASK-015), seller parity.
- Verification: pytest 1 passed; e2e ff-mp-tabs + ff-mp-ship-pick green; `npm run build`.
- Commit: e6913ec

## TASK-013 — 2026-06-27 — Счётчики плана, распределения и упаковки

- What changed: `mpCollectSummary` — план / распределено по коробам / остаток + статус упаковки; предупреждение `ff-mp-collect-warning` при неполном распределении; колонка «Распределено» вместо «Собрано»; e2e asserts в `ff-mp-tabs.spec.ts` (TC-NEW-MP-007).
- What did NOT change: ship validation (TASK-014), backend `picked_qty_by_product` (уже по коробам).
- Verification: `npm run build`; e2e ff-mp-tabs green.
- Commit: e6913ec

## TASK-012 — 2026-06-27 — Вкладочная структура документа отгрузки на МП

- What changed: MUI Tabs в `FfSuppliesShipmentsPage` — «Товары / Упаковка / Короба / Финальная отгрузка»; embed `FfPackagingTaskPanel` вместо `FfPackagingTaskDialog`; финал (дата, склад WB, печать, подтвердить/отгрузить) на вкладке «Финал»; e2e `ff-mp-tabs.spec.ts` (TC-NEW-MP-007).
- What did NOT change: счётчики DEC-010 (TASK-013), ship validation DEC-012 (TASK-014/015), seller parity (`SellerMarketplaceUnloadDialog`).
- Verification: `npm run build`; e2e ff-mp-tabs + ff-mp-box-add-modal + ff-address-storage-mp-ui + ff-mp-ship-pick green.
- Commit: e6913ec


- What changed: `FfMarketplaceUnloadBoxAddDialog` (фото, план/в коробах/доступно, scan ячейки+товара, ручной ввод); кнопка `ff-mp-box-add-products-{boxId}`; `plan_exceeded` в `collect_into_box` (BR-005); gate упаковки по `status === 'done'`; e2e `ff-mp-box-add-modal.spec.ts` (TC-NEW-MP-006).
- What did NOT change: вкладочная структура (TASK-012), счётчики DEC-010 (TASK-013).
- Verification: pytest 26 passed (unload + packaging + address_storage); `npm run build`; e2e `ff-mp-box-add-modal.spec.ts` green.
- Commit: e6913ec

## TASK-010 — 2026-06-27 — Действия короба: remove line, delete empty, copy, print ШК

- What changed: `remove_from_box` (откат on_hand/reserved/pick allocation, DEC-016); `delete_box` (DEC-007, только пустой); `copy_box` (новый короб + collect по allocations, лимит плана BR-005); API `POST .../copy`, `DELETE .../boxes/{id}`, `POST .../lines/{id}/remove`; UI меню короба + печать ШК + удаление строки; pytest `test_marketplace_unload_box_remove_copy_delete`.
- What did NOT change: модалка «Добавить товары» напротив короба (TASK-011), вкладочная структура (TASK-012).
- Verification: pytest 26 passed (unload + address_storage + packaging); `npm run build`.
- Commit: e6913ec

## TASK-009 — 2026-06-27 — Массовое создание N коробов

- What changed: `create_boxes_batch` в `marketplace_unload_box_service`; `POST .../boxes/batch` (count 2–50, закрытые пустые короба с ШК); UI — поле «Кол-во коробов» + кнопка «Создать короба» / «Открыть короб» (count=1); pytest batch.
- What did NOT change: per-box modal add (TASK-011), copy/delete короба (TASK-010).
- Verification: pytest `test_marketplace_unload_create_boxes_batch` + 25 unload tests passed; `npm run build`.
- Commit: e6913ec

## TASK-005 — 2026-06-27 — Удаление «Начать подбор» (legacy flow)

- What changed: убраны кнопка `ff-mp-start-picking`, модалка `ff-mp-picking-dialog`, блок `ff-mp-pick-saved`; `PUT .../pick-allocations` — только `FULFILLMENT_ADMIN`; pytest + e2e TC-NEW-MP-005.
- What did NOT change: сборка через скан в короб (`collect_into_box`); `GET pick-options` (без UI).
- Verification: pytest 24 passed (unload + address_storage + packaging); e2e `ff-address-storage-mp-ui`, `ff-mp-ship-pick` green; `npm run build`.
- Commit: e6913ec

## TASK-004 — 2026-06-27 — Списание остатков при добавлении в короб (DEC-006)

- What changed: `collect_into_box` вызывает `apply_marketplace_unload_pick` + `reduce_reservation_for_collect` в одной транзакции; `FOR UPDATE` на балансе и заявке; `ship_request` без повторного movement; `delete_empty_boxes_for_ship` (DEC-002); pytest + e2e `ff-mp-ship-pick` — остаток уменьшается после collect, не после ship.
- What did NOT change: откат при remove-from-box (TASK-010), отмена/abandon (TASK-019).
- Verification: `pytest tests/test_marketplace_unload_and_discrepancy_acts.py` + `test_marketplace_unload_address_storage.py` — 23 passed.
- Commit: e6913ec

## TASK-007 + TASK-008 — 2026-06-27 — Завершение упаковки и gate коробов

- What changed: `POST .../packaging-tasks/{id}/complete`; reopen task при смене плана отгрузки; блок `create_open_box`/`collect_into_box` до `packaging_not_done`; UI complete panel + disabled box scan; e2e `ff-mp-ship-pick`, `ff-address-storage-mp-ui` — упаковка перед коробами.
- What did NOT change: списание при collect (TASK-004), batch короба (TASK-009).
- Verification: `pytest tests/test_packaging_tasks.py` 8 passed; `test_marketplace_unload_address_storage.py` 2 passed; `npm run build`.
- Commit: e6913ec

## TASK-003 — 2026-06-27 — Скрытие UI ячеек при выкл. адресном хранении

- What changed: `addressStorageEnabled` prop в `FfSuppliesShipmentsPage`, `FfInboundRequestView`, `App.tsx`; скрыты chip ячейки, «Начать подбор», таблица pick_allocations, блок распределения приёмки; scan без шага ячейки; e2e `ff-address-storage-mp-ui.spec.ts`.
- What did NOT change: списание при collect (TASK-004), backend API (TASK-002 уже в `908029c`).
- Verification: `npm run build`; e2e `ff-address-storage-mp-ui.spec.ts` + `ff-address-storage-setting.spec.ts` green.
- Commit: `2cd8062`.

## TASK-001 — 2026-06-27 — Флаг «Адресное хранение» (UI)

- What changed: checkbox на `FfSettingsScreen`, поле `address_storage_enabled` в `Me`/`useAuth`, reload me после PATCH; e2e `ff-address-storage-setting.spec.ts`. Backend/API — в `908029c`.
- What did NOT change: скрытие UI ячеек (TASK-003).
- Verification: e2e settings + build green.
- Commit: `2cd8062` (UI; backend/API в `908029c`).

## TASK-002 — 2026-06-27 — Условная обязательность ячеек в collect/pick API

- What changed: `resolve_collect_storage_location` в `marketplace_unload_collect_service`; флаг `address_storage_enabled` через `tenant_settings_service` (TASK-001 dependency); optional `storage_location_id` в API scan/manual-line/pick-add; `pick_scan` — порядок ячейка→товар при вкл. флаге; pytest `test_marketplace_unload_address_storage.py`.
- What did NOT change: списание при collect (TASK-004), скрытие UI ячеек (TASK-003), inventory movement moment on ship.
- Verification: `ruff` + `mypy` on changed files green; pytest 2 new + `test_marketplace_unload_ship_deducts_stock_by_pick_and_scan` green.
- Commit: `908029c`.

## TASK-78 — 2026-06-26 — ЧЗ T4.1: хранилище кредов селлера

- What changed: таблица `seller_marking_credentials` (шифрованные токены ЧЗ/СУЗ/МП, МЧД, signing_method, edo_route, auto_introduce, auto_emit_limit); API `GET/PATCH /operations/marking-codes/self/credentials` и `/sellers/{id}/credentials`; блок настроек в `SellerSettingsScreen`; pytest + e2e `seller-marking-credentials.spec.ts`.
- What did NOT change: signing-service (T4.2), авто-ввод в оборот (T4.3).
- Verification: `pytest tests/test_marking_credentials_api.py` 4 passed; `npm run build`; e2e `seller-marking-credentials.spec.ts` green.
- Commit: `6840b15`.

## TASK-77 — 2026-06-26 — ЧЗ T3.3–T3.5: прогноз, low-stock, дашборд селлера, триггеры ФФ

- What changed: T3.3 расчёт `consumption_7d`/`forecast_days`, `PUT pools/{id}/threshold`, Celery `marking_low_stock`, KPI и пороги в UI; T3.4 карточки остатков селлера + e2e; T3.5 `notify_ff_portal` при создании приёмки/отгрузки МП.
- What did NOT change: фаза 4 (креды ЧЗ, подпись).
- Verification: pytest forecast+triggers; `npm run build`; e2e `seller-honest-sign-dashboard.spec.ts`.
- Commit: `51876d2`.

## TASK-76 — 2026-06-26 — ЧЗ T3.2: колокольчик и центр уведомлений

- What changed: `NotificationBell` в шапке FF и селлера, страница «Уведомления», API-клиент, e2e seed `/_e2e/seed`, Playwright `ff-notifications.spec.ts`.
- What did NOT change: пороги low-stock (T3.3), дашборд остатков селлера (T3.4), триггеры отгрузок (T3.5).
- Verification: `npm run build`; e2e `ff-notifications.spec.ts` green.
- Commit: `11c1ccd`.

## TASK-75 — 2026-06-26 — ЧЗ T3.1: шина уведомлений

- What changed: таблица `notifications`, сервис `notify`/`notify_ff_portal`, API `GET/POST /operations/notifications` (список, read, read-all), скоуп получателя user/seller/ff_portal.
- What did NOT change: UI колокольчик (T3.2), триггеры low-stock и отгрузок (T3.3–T3.5).
- Verification: `ruff`, `mypy`, `pytest tests/test_notifications.py` — 5 passed.
- Commit: `9c8a449`.

## TASK-74 — 2026-06-26 — ЧЗ T2.4–T2.5: verify-pair и ворклист pending

- What changed: T2.4 `POST verify-pair` (match → `applied` + событие), мини-станция на упаковке; T2.5 `GET pending-marking`, экран «Осталось промаркировать», бейдж на упаковке.
- What did NOT change: фаза 3 (уведомления T3.1).
- Verification: pytest verify_pair + pending; e2e ff-marking-verify-pair + ff-pending-marking.
- Commit: `15e290a`.

## TASK-73 — 2026-06-26 — ЧЗ T2.1–T2.3: shift_lead, брак, очередь перепечатки

- What changed: T2.1 `can_shift_lead`, `require_shift_lead`, nav «Перепечатки»; T2.2 `marking_reprint_requests`, `POST codes/{id}/defect`, кнопка «Брак» на упаковке; T2.3 approve/replace/reject API и кнопки на экране очереди.
- What did NOT change: T2.4 скан-пара «товар=пакет»; колокольчик уведомлений (Э7).
- Verification: pytest reprint_defect + shift_lead; `npm run build`; e2e ff-shift-lead + ff-marking-defect.
- Commits: `78881e7` (T2.1), `f6d78d1` (T2.2), `ff6f9f9` (T2.3).

## TASK-72 — 2026-06-26 — ЧЗ T1.6: рендер ленты по layout

- What changed: `expandLayoutTape` в `markingPrintPresets.ts`; `printMarkingCodeTape` / обновлённый `printMarkingCodeLabels` с блоками `cz` и `label` (58×40); экспорт `buildProductLabelSectionHtml`; вызовы из `MarkingPrintDialog`, `FfPackagingPage` (scan/print-all/строка); vitest `markingPrintPresets.test.ts`; e2e constructor — пресет «Этикетки + ЧЗ», счётчик этикеток в предпросмотре.
- What did NOT change: Фаза 2 (shift_lead, перепечатки).
- Verification: `npm run test:unit` 2 passed; `npm run build`; e2e constructor + print-all green.
- Commit: `a86def6`.

- What changed: `print_all_for_packaging_task` + `POST /operations/marking-codes/packaging-tasks/{id}/print-all` (dry_run, allow_partial); кнопка «Печать всех ЧЗ» и диалог сводки на панели упаковки; pytest `test_marking_print_all.py`; e2e `ff-marking-print-all.spec.ts` (TC-NEW-003).
- What did NOT change: рендер ленты по layout label-блокам (T1.6).
- Verification: pytest print_all 2 passed; `npm run build`; e2e print-all green.
- Commit: `7b33be6`.

## TASK-70 — 2026-06-26 — ЧЗ T1.4: скан-печать

- What changed: `units_to_print` в `print_codes_for_packaging_line` (инкремент `qty_marking_printed`); `scan_print_for_packaging_task` + `POST /operations/marking-codes/scan-print`; поле «Сканируйте товар» на панели упаковки; pytest `test_marking_scan_print.py`.
- What did NOT change: print-all (T1.5), layout-рендер label (T1.6).
- Verification: pytest scan + marking; `npm run build`.
- Commit: `b1e27b1`.

## TASK-69 — 2026-06-26 — ЧЗ T1.3: диалог-конструктор печати

- What changed: `MarkingPrintDialog` — шапка (товар/документ, нужно/доступно), баннер нехватки, «печатать доступные M», пресеты (Парами/Этикетки+ЧЗ/…/Свой), конструктор блоков, предпросмотр 3 единиц, сохранение шаблона, тост «Запросить у селлера»; кнопка «Печать ЧЗ» доступна при available≥1; e2e `ff-marking-print-constructor.spec.ts` (TC-NEW-002).
- What did NOT change: scan-print (T1.4), print-all (T1.5), рендер label-блоков (T1.6).
- Verification: `npm run build`; e2e constructor + packaging.
- Commit: `b1e27b1`.

## TASK-68 — 2026-06-26 — ЧЗ T1.2: печать из пула

- What changed: рефактор `print_codes_for_packaging_line` — коды из пула (`marking_pool_products`), reserve→printed, события с `document_number`, API `{layout_json, copies, allow_partial}`; ответ `{codes, layout, quantity, shortage}` вместо 422 при нехватке; фронт отправляет `layout_json` из шаблона; pytest `test_marking_print_pool.py`, обновлён `test_marking_insufficient_codes`.
- What did NOT change: конструктор ленты Э5 (T1.3), scan-print (T1.4), рендер по layout на фронте (T1.6).
- Verification: pytest marking print 9 passed; `npm run build`.
- Commit: not yet.

## TASK-67 — 2026-06-26 — ЧЗ T1.1: шаблоны печати

- What changed: таблица `print_templates`, модель `PrintTemplate`, сервис `print_template_service.py` (CRUD + резолвер product→seller→системный «Парами»); API `GET/POST/PUT/DELETE /operations/marking-codes/print-templates` и `GET …/print-templates/resolve`; фронт `printTemplate.ts`, диалог печати подтягивает шаблон по товару; pytest `test_print_templates.py`.
- What did NOT change: рефактор печати из пула (T1.2), конструктор ленты Э5 (T1.3), scan-print (T1.4).
- Verification: `ruff`/`mypy` green; pytest print_templates 3 passed; `npm run build`; e2e packaging — по возможности.
- Commit: not yet.

## TASK-66 — 2026-06-26 — ЧЗ T0.4: привязка пул↔товары

- What changed: `set_pool_products` / `add_pool_products` / `remove_pool_products` в `marking_code_service.py`; `PUT /operations/marking-codes/pools/{pool_id}/products` (422 `product_seller_mismatch`); диалог `MarkingPoolProductsDialog` + панель `MarkingPoolProductsPanel` (чипы товаров); e2e seed `POST …/_e2e/pools` при `WMS_AUTO_CREATE_SCHEMA=1`; pytest `test_marking_pool_products.py`, e2e `ff-pool-products-link.spec.ts` (TC-NEW-004).
- What did NOT change: список пулов Э1 (T0.7), импорт в пулы (T0.3), GET ленты/пулов (T0.6).
- Verification: `ruff`/`mypy` green; pytest marking 12 passed; `npm run build`; e2e `ff-pool-products-link.spec.ts` green.
- Commit: `82180c8`.

## TASK-65 — 2026-06-26 — ЧЗ T0.5: журнал marking_code_events

- What changed: таблица `marking_code_events`, модель `MarkingCodeEvent`, константы типов событий; `record_event()` в `marking_code_service.py`; события `imported` при импорте, `printed`/`reprinted` при печати; pytest `test_marking_code_events.py`.
- What did NOT change: API ленты (T0.6), привязка пул↔товары (T0.4), рефактор импорта в пулы (T0.3).
- Verification: `ruff`/`mypy` green; `pytest` 156 passed.
- Deploy: not yet.

## TASK-64 — 2026-06-26 — ЧЗ T0.2: модель пулов и расширение кодов

- What changed: таблицы `marking_pools`, `marking_pool_products`; расширение `marking_codes` (pool_id, serial, crypto_tail, reserved/applied/introduced/transferred/consumed, defective_reason, replaced_by_code_id); константы статусов; дата-миграция backfill пулов для существующих кодов; pytest `test_marking_pools.py`.
- What did NOT change: API, фронт, импорт в пулы (T0.3), события `marking_code_events` (T0.5).
- Verification: `ruff`/`mypy` green; `pytest` 154 passed.
- Deploy: not yet.

## TASK-63 — 2026-06-26 — ЧЗ T0.1: нумерация документов (УПАК/ПРИЕМ/ОТГР)

- What changed: таблица `document_sequences`, колонка `document_number` на `packaging_tasks`, `inbound_intake_requests`, `marketplace_unload_requests`; сервис `document_number_service.py` (атомарный счётчик по МСК); номер при создании упаковки/приёмки/отгрузки; API + UI (упаковка, приёмка, списки отгрузок); pytest + e2e TC-NEW-DOCNUM-01.
- What did NOT change: пулы ЧЗ, импорт кодов, события `marking_code_events` (T0.2+).
- Verification: `ruff`/`mypy` green; `pytest` 152 passed; `npm run build`; e2e `ff-packaging-page.spec.ts` (create from sorting).
- Deploy: not yet.

## TASK-62 — 2026-06-26 — FF каталог: поиск по артикулу и названию

- What changed: в разделе «Каталог» ФФ — строка поиска сверху; фильтрация по `sku_code`, `wb_vendor_code` (артикул продавца) и названию; пустое состояние «ничего не найдено»; e2e TC-NEW-002 в `ff-products.spec.ts`.
- What did NOT change: API `/products/ff-catalog`; фильтр по селлеру и сортировка.
- Verification: `npm run build`; e2e `ff-products.spec.ts` — filter/sort/search.
- Deploy: PR #46 → `main` `4e82c6b`; prod `194.87.96.144:8088` — `prod-update.sh`, HTTP 200.

## TASK-61 — 2026-06-24 — Фикс сброса даты отгрузки в WmsDateField

- What changed: `WmsDateField` не вызывает `onChange(null)` на пустом blur после выбора в календаре; регрессия в `seller-mp-unload.spec.ts` (TC-NEW-DATE-01).
- What did NOT change: API PATCH `planned_shipment_date`; логика сохранения в диалогах селлера и ФФ.
- Verification: `npm run build`; e2e `seller-mp-unload.spec.ts`, `ff-dashboard.spec.ts`.
- Deploy: PR #43 → `main` `fc1a32b`; prod `194.87.96.144:8088` — `prod-update.sh`, HTTP 200.

## TASK-60 — 2026-06-23 — FF навигация: «Каталог»→«Ячейки», «Товары»→«Каталог»

- What changed: подписи в сайдбаре ФФ и заголовки экранов — раздел складов/ячеек «Ячейки», раздел товаров селлеров «Каталог»; подсказки в приёмке/сортировке и текст ошибки ТЗ упаковки.
- What did NOT change: маршруты (`/app/catalog`, `/app/ff/products`), `data-testid`, кабинет селлера («Товары»).
- Verification: `npm run build`; e2e `admin-shell-layout.spec.ts`, `ff-products.spec.ts`.

## TASK-59 — 2026-06-23 — FF каталог: все товары селлеров, не только с движениями

- What changed: `GET /products/ff-catalog` возвращает все товары тенанта (как `linked-wb-catalog`), а не только с `InventoryMovement`; остатки в UI по-прежнему из `inventory-balances/summary` (0 для непринятых).
- What did NOT change: приватный WB-каталог селлера; эндпоинт `linked-wb-catalog` (оставлен для приёмки/хуков).
- Verification: `pytest tests/test_products_wb_catalog.py::test_ff_catalog_lists_all_tenant_products`; e2e `ff-products.spec.ts` — filter/sort passed.
- Deploy: PR #45 → `main` `7146d77`; prod `194.87.96.144:8088` — `prod-update.sh`, WB sync 8/8 sellers ok (~307 SKU updated).

## TASK-58 — 2026-06-18 — Печать ШК в каталоге товаров ФФ и после закрытия приёмки

- What changed: в разделе «Товары» ФФ — кнопка печати этикетки 58×40 (как на приёмке/упаковке); после «Завершить пересчёт» в разделе «Сортировка» таблица состава приёмки с печатью ШК остаётся видимой; общий компонент `ProductBarcodePrintButton`.
- What did NOT change: API печати; логика этикетки 58×40.
- Verification: `npm run build`; e2e `ff-reception-sorting.spec.ts`, `ff-product-barcode-print.spec.ts` — green.
- Deploy: PR #42 → `main` `a8a840a`; prod `194.87.96.144:8088` — `prod-update.sh`, все контейнеры Up, bundle `ff-ZMw0qrUp.js`.

## TASK-57 — 2026-06-16 — Селлер: изоляция каталога по магазину + деплой

- What changed: обычные селлеры всегда видят только свой `seller_id` (JWT-делегирование игнорируется); менеджеры — allowlist (`vitalik`/`vitaliy`/`виталий`, `denmark`/`denmarks`, `WMS_SHOP_MANAGER_EMAILS`, флаг БД); фронт перезагружает каталог при смене активного магазина; WB-импорт ищет баркод только в рамках селлера; pytest `test_seller_wb_catalog_isolation.py`, `test_seller_shop_allowlist.py`.
- What did NOT change: FF-каталог «все селлеры» для админа; логика переключения магазинов у менеджеров.
- Verification: pytest seller isolation 15 passed; PR #40 CI green; `npm run build`.
- Deploy: merge PR #40 → `main` `ee5095c`; prod `194.87.96.144:8088` — `prod-update.sh`, все контейнеры Up, seller/api HTTP 200. WB re-sync прерван (OOM); при необходимости вручную: `./scripts/deploy/sync-all-wb-products.sh`.

## TASK-56 — 2026-06-16 — Честный знак: импорт кодов и печать из упаковки

- What changed: модуль ЧЗ — `marking_codes` / `marking_code_imports` в БД; флаг `requires_honest_sign` у товара; загрузка CSV/PDF селлером или админом ФФ; остатки в разделах «Честный знак» (FF + seller); в задании на упаковке кнопка «Печать ЧЗ» на всё `qty_need_pack` строки, галочка «в 2 экземплярах», повторная печать без списания новых кодов; печать DataMatrix 58×40 (`bwip-js`); блок отгрузки на МП при `marking_not_done`; миграция `20260616_0041`; pytest `test_marking_codes.py`; e2e `ff-marking-packaging.spec.ts`.
- What did NOT change: отчётность в ГИС МТ / API ЧЗ; парсинг PDF-сетки на листе (только постраничный текст + CSV).
- Verification: `ruff check . && mypy . && pytest` (129 passed); `npm run build`; `npx playwright test tests-e2e/ff-marking-packaging.spec.ts`.

## TASK-55 — 2026-06-15 — Портал селлера: переключение между магазинами (Vitality)

- What changed: менеджер-магазинов (email с «vitalik», `WMS_SHOP_MANAGER_EMAILS` или `users.can_manage_seller_shops`) — в сайдбаре раздел «Магазины» с чекбоксами (все селлеры тенанта кроме своего и тестовых `@example.com` / `e2e-*`); после включения — переключатель «Активный магазин»; API `PUT /auth/seller-shops`, `POST /auth/switch-seller`; JWT `seller_id` = активный магазин; все seller API (отгрузки, приёмки, товары, WB) работают от лица выбранного магазина; миграция `20260615_0040`; pytest `test_seller_shop_switch.py`.
- What did NOT change: обычные селлеры без флага — только свой магазин; админ FF не затронут.
- Verification: `pytest tests/test_seller_shop_switch.py`; `npm run build`.

## TASK-54 — 2026-06-14 — Этикетка 58×40 и колонка ШК: баркод WB + размер

- What changed: на этикетке 58×40 в блоке деталей снова печатается «Размер: …»; под штрихкодом — только цифры ШК (баркод WB, не артикул/sku); в колонке «ШК» строк товаров (приёмка, упаковка, отгрузка) — баркод сверху, «Размер: …» снизу; e2e `ff-product-barcode-print.spec.ts` обновлён.
- What did NOT change: отдельная колонка «Размер» в каталоге товаров; логика импорта WB.
- Verification: `npm run build`; `npx playwright test tests-e2e/ff-product-barcode-print.spec.ts`.
- Deploy: commit `476d2aa`, prod `/opt/wms` — `git pull` + rebuild `web` only, `:8088` OK.

## TASK-53 — 2026-06-14 — WB: отдельный товар на каждый размер + фильтр ИП при отгрузке ФФ

- What changed: импорт WB — один `Product` на каждый баркод из `sizes[].skus` (`sku_code` вида `ART/S`, поля `wb_barcode`, `wb_chrt_id`, `wb_size`); при multi-size старый merged SKU → `OLD/…` + `[OLD]` в названии; миграция `20260614_0039`; post-deploy `./scripts/deploy/sync-all-wb-products.sh` (в `prod-update.sh`) — полная загрузка карточек по **всем** селлерам с content-токеном; UI «Товары» — колонка «Размер»; отгрузка на МП (ФФ) — выбор селлера (ИП) перед созданием.
- What did NOT change: строки `OLD/…` не удаляются (остатки/история на них); одна snapshot-карточка WB на nmID.
- Verification: `pytest tests/test_wildberries_legacy_old_mark.py tests/test_wildberries_product_import_sizes.py`; `npm run build`.
- Deploy: `prod-update.sh` → migrate + `python -m app.cli.sync_all_wb_products` в контейнере api.

## TASK-52 — 2026-06-14 — Дубликаты селлеров: очистка prod + атомарное создание

- What changed: prod — удалены 6 пустых дублей «ИП Герус Д.В.» (оставлен один с `gerus_denis@mail.ru`); бэкенд — `POST /sellers/with-account` (селлер + учётка в одной транзакции, откат при `email_taken`); UI `SellersScreen` — один запрос вместо двух; pytest `test_create_seller_with_account_*`; e2e sellers-create / auth-dual / auth-portal-mismatch.
- What did NOT change: отдельные `POST /sellers` и `POST /auth/seller-accounts` (для тестов/API); остальные селлеры (Denmarcs, Виталик и т.д.).
- Verification: `pytest tests/test_sellers.py` — 4 passed; `npm run build` — OK; prod SQL — 1 «ИП Герус Д.В.».
- Deploy: код ещё не на проде — нужен `git pull` + rebuild.

## TASK-51 — 2026-06-11 — Остатки селлера: остаток vs резерв vs отгрузка

- What changed: бэкенд — резерв МП/outbound только по ячейкам (не «Сортировка»); UI селлера — колонки «В ячейках», «Остаток» (На ФФ − резерв), «К отгрузке» (только ячейки); тест `test_available_matches_mp_reserve_only_after_putaway`, e2e `seller-available-stock`.
- What did NOT change: списание при ship/pick МП; экран товаров ФФ.
- Verification: `pytest tests/test_inventory_balances_summary.py`; `npm run build`.

## TASK-50 — 2026-06-11 — Биллинг сотрудников за упаковку

- What changed: ставка за ед. (₽) в настройках сотрудников; расчёт ЗП по завершённым заданиям (только `qty_packed_in_task`, снимок ставки при завершении); фильтр по месяцу (МСК); право «Упаковка» в матрице доступа; API `PATCH /auth/staff-accounts/{id}/packaging-rate`; миграция `0038`.
- What did NOT change: биллинг селлеров (литр‑день), выплаты/бухгалтерия.
- Verification: `ruff` / `mypy` / `pytest tests/test_staff_packaging_billing.py`; `npm run build`; e2e `ff-staff-packaging-billing.spec.ts`; PR #37 CI green; prod `194.87.96.144:8088` commit `b646463`.
- Commit: b646463 (squash PR #37).

## TASK-49 — 2026-06-11 — Упаковка: таблица создания задания как в приёмке

- What changed: диалог «Создать задание на упаковку» — ширина `min(1200px, 96vw)` как у `WbProductPickerDialog` в приёмке; те же отступы таблицы; фиксированные ширины колонок количества; `minWidth: 180` у «Наименование» в `FfProductLineCells` (не ломается посимвольно).
- What did NOT change: API упаковки, логика создания задания.
- Verification: `npm run build` — OK.
- Commit: 405025f.

## TASK-48 — 2026-06-11 — Отдельный favicon и марка для портала селлера

- What changed: `frontend/public/favicon-seller.svg` — бирюзовый «магазин» (отличается от фиолетовой «коробки» FF); `seller/index.html` → `/favicon-seller.svg`; `WmsBrandMark` с `portal="seller"` в шапке селлера и на экране входа; `deploy/Caddyfile.http` — исключение favicon-seller из no-cache SPA.
- What did NOT change: favicon FF (`/favicon.svg`), API, бизнес-логика.
- Verification: `npm run build` — OK.

## TASK-47 — 2026-06-11 — Брендинг WMS: favicon и марка в UI

- What changed: `frontend/public/favicon.svg` — вместо розовой молнии (оцифровка) иконка коробки в цвете темы; `WmsBrandMark` в шапке FF/селлера и на экране входа; заголовки вкладок `WMS · Фулфилмент` / `WMS · Селлер`.
- What did NOT change: API, бизнес-логика.
- Verification: `npm run build`; CI green PR #34; prod deploy `194.87.96.144:8088` commit `4caef80` — `curl /favicon.svg` → коробка `#5b21b6`.
- Commit: 4caef80 (squash PR #34).

## TASK-46 — 2026-06-11 — Seller SPA: no-cache на :8088 (Caddyfile.http)

- What changed: `deploy/Caddyfile.http` — `Cache-Control: no-cache` для seller/FF HTML (как в `frontend/deploy/Caddyfile`), чтобы после деплоя браузер не держал старый `seller-*.js`.
- What did NOT change: логика `SellerMarketplaceUnloadDialog` (на сервере уже `seller-mp-add-products`).
- Verification: после merge — `curl -I http://194.87.96.144:8088/seller/` → no-cache; hard refresh у селлера → кнопка «Добавить товары».

## TASK-45 — 2026-06-11 — WbProductPickerDialog: FF приёмка и отгрузка на МП

- What changed: `SellerWbProductPickerDialog` → ядро `WbProductPickerDialog` с `variant="ff"` (`FfProductLineCells`, печать ШК); подключено в `FfInboundRequestView` и `FfSuppliesShipmentsPage`. Пропсы `applyLabel`, `renderTrailingHeadCells` / `renderTrailingBodyCells` для будущих колонок FF.
- What did NOT change: API; логика сохранения строк остаётся в родительских экранах.
- Verification: `npm run build`; e2e ff-dashboard, ff-inbound-boxes, seller-mp-unload, seller-cabinet — 8 passed; prod `194.87.96.144:8088` commit `9094acf`.
- Commit: 9094acf.

## TASK-44 — 2026-06-11 — Общий picker каталога WB для селлера

- What changed: `SellerWbProductPickerDialog` — единая модалка выбора товаров (поиск, категория, фото, qty); подключена в `SellerInboundDraftScreen` и `SellerMarketplaceUnloadDialog`. Отгрузка на МП передаёт `showAvailableColumn`, `filterRow`, `getAvailable`.
- What did NOT change: портал ФФ — подключён в TASK-45.
- Verification: `npm run build`; e2e seller-mp-unload, seller-available-stock, seller-cabinet, ff-inbound-boxes.
- Commit: 4cb7c33 (в prod вместе с 9094acf).

## TASK-43 — 2026-06-11 — Селлер: отгрузка на МП — добавление товаров как в приёмке

- What changed: в `SellerMarketplaceUnloadDialog` убрана старая таблица всех остатков; кнопка «Добавить товары» + модалка каталога WB (поиск, категория, фото, ШК, колонка «Доступно») как в `SellerInboundDraftScreen`; строки заявки редактируются в таблице с удалением. E2e `seller-mp-unload`, `seller-available-stock` обновлены.
- What did NOT change: API отгрузки на МП; портал ФФ (уже на новом паттерне).
- Verification: `npm run build`; e2e `seller-mp-unload.spec.ts`, `seller-available-stock.spec.ts` — 2 passed.

## TASK-42 — 2026-06-11 — Отгрузка на МП: видимая панель добавления + деплой

- What changed: панель «Добавление товаров» (скан ШК + «Добавить товары») перенесена **под склад WB, до таблицы строк**; Caddy `no-cache` для `index.html`; e2e проверяет отсутствие старого Select на МП.
- What did NOT change: логика модалки каталога и API строк (c8db069); акты расхождений.
- Verification: PR #33 CI green; prod `194.87.96.144:8088` commit `d3a951e`, bundle `ff-CC085PGz.js`.
- Commit: d3a951e (squash merge PR #33).

## TASK-41 — 2026-06-11 — Отгрузка на МП: добавление товаров как в приёмке

- What changed: в черновике отгрузки на МП — скан ШК/артикула, кнопка «Добавить товары» и модалка каталога WB (фото, артикулы, ШК, поиск, категория, кол-во) как в `FfInboundRequestView`; строки таблицы по-прежнему через `FfProductLineCells`. Старый Select по остаткам убран для МП.
- What did NOT change: сборка в короба, подбор по ячейкам, акты расхождений (там старый Select).
- Verification: `npm run build`; e2e `ff-dashboard.spec.ts`, `ff-mp-ship-pick.spec.ts`.
- Commit: c8db069; CI run 27307241687 success; prod deploy `194.87.96.144:8088`.

## TASK-40 — 2026-06-11 — Этикетка ШК 58×40 по макету WB (штрихкод сверху)

- What changed: макет термоэтикетки как на WB — штрихкод и цифры сверху, имя селлера, название, артикул, цвет, бренд, «Пожалуйста оставьте отзыв»; убраны EAC и строка размера. API каталога отдаёт `wb_brand` из карточки WB.
- What did NOT change: печать коробов/ячеек; накладные A4; размер по-прежнему в каталоге, но не на этикетке.
- Verification: `npm run build`; pytest `test_wb_card_enrichment`, `test_seller_wb_catalog_enriched_from_imported_card`; e2e `ff-product-barcode-print.spec.ts`.
- Commit: b5e3eba; prod deploy `194.87.96.144:8088`.

## TASK-39 — 2026-06-10 — Приёмка без обязательного короба; этикетка: размер/цвет WB

- What changed: пересчёт приёмки — факт по строкам вручную даже при коробах; короб опционален. Этикетка 58×40 — убрано «Производитель: Россия», добавлены `wb_size`/`wb_color` из карточки WB в каталог и печать.
- What did NOT change: печать коробов/ячеек; синхронизация WB.
- Verification: pytest inbound_box + wb_catalog; e2e `ff-inbound-box-intake`, `ff-product-barcode-print`.
- Commit: 47ab877

## TASK-38 — 2026-06-10 — Этикетка товара 58×40 (EAC, артикул, количество)

- What changed: печать по образцу WB — 58×40 мм, название (обрезка), «Артикул», «Производитель: Россия», знак EAC, CODE128; диалог с превью и полем «Количество этикеток»; API `GET /products/linked-wb-catalog` — баркоды до первого движения по складу.
- What did NOT change: этикетки ячеек/коробов; накладные A4.
- Verification: pytest `test_linked_wb_catalog_before_stock_movement`; e2e `ff-product-barcode-print.spec.ts`.

## TASK-37 — 2026-06-10 — Печать ШК товара в модалках FF (приёмка, сортировка, отгрузка, упаковка)

- What changed: единый блок строки товара (фото, артикул, ШК WB, артикул продавца, nm, название) + кнопка «Печать ШК» (CODE128, 58×40) в модалках приёмки, сортировки, отгрузки на МП и упаковки; каталог WB подтягивается через `useWbProductCatalog`.
- What did NOT change: печать ШК ячеек/коробов; накладные A4; синхронизация карточек WB.
- Verification: `npm run build`; e2e `ff-product-barcode-print.spec.ts` (TC-NEW-PRINT-01).

## TASK-36 — 2026-06-03 — MP unload: без блокировки по ТЗ упаковки

- What changed: снята проверка `packaging_instructions_required` при `plan`/`confirm` отгрузки на МП; поле ТЗ на товаре остаётся опциональным.
- What did NOT change: блок `packaging_not_done` при «Отгружено», если есть незавершённое задание упаковки; UI редактирования ТЗ.
- Verification: pytest `test_seller_marketplace_unload`, `test_product_packaging_instructions`.
- Commit: df1934e

## TASK-35 — 2026-05-30 — Упаковка E7 slice 4 (FF каталог, ячейка, отмена, resync)

- What changed: FF-каталог — колонки «Не упак./Упаковано», редактирование ТЗ; создание задания из любой ячейки (не только сортировка); `POST /packaging-tasks/{id}/cancel` для ручных заданий; `pick_resync_warning` (миграция `0037`, sticky при смене подбора с прогрессом); e2e `ff-products` (ТЗ), `ff-packaging-page` (ячейка, отмена).
- What did NOT change: биллинг упаковки; ЧЗ; dismiss предупреждения resync в UI (alert пока открыто задание).
- Verification: `ruff`/`mypy`; pytest 110 passed; `npm run build`; e2e 49 passed; prod deploy `194.87.96.144:8088` (migrations 0036→0037).
- Commit: 6d8647d (main `5c9d115`)

## TASK-34 — 2026-05-30 — Упаковка E7 (этапы 1–3, PR feat/packaging-e7)

- What changed: `packaging_task` API + миграция split unpacked/packed; авто-задание при confirm MP unload; ship блок до `done`; ТЗ `packaging_instructions` (селлер UI + валидация plan/confirm); раздел FF «Упаковка»; create from sorting; прогресс в карточке отгрузки; e2e `ff-packaging-page`, regression MP ship/pick/seller; docs `PACKAGING_RU.md`, TC-NEW-PKG-*.
- What did NOT change: FF-редактирование ТЗ в каталоге; задание из произвольной ячейки; отмена задания; биллинг; ЧЗ.
- Verification: `ruff`/`mypy`; pytest 106 passed; `npm run build`; e2e `ff-packaging-page`, `ff-mp-ship-pick`.
- Commit: 642cba7

## TASK-33 — 2026-05-30 — Упаковка (этап 2: ТЗ селлера, сортировка, валидация MP)

- What changed: `PATCH /products/{id}/packaging-instructions` (селлер/админ); блок `plan`/`confirm` MP unload без ТЗ (`packaging_instructions_required`); `GET /warehouses/{id}/sorting-location`; создание задания без ячейки → зона «Сортировка»; UI селлера — редактирование ТЗ; FF — «Создать задание» на странице упаковки + кнопка «Упаковать» на сортировке; sync упаковки при подборе в короб; pytest `test_product_packaging_instructions.py`; e2e seller-mp-unload/seller-available-stock — ТЗ перед plan.
- What did NOT change: FF-редактирование ТЗ в каталоге; биллинг упаковки; ЧЗ.
- Verification: pytest (packaging + seller MP subset) locally via `.venv`.
- Commit: (pending)

## TASK-32 — 2026-05-30 — Задание на упаковку (этап 1: backend + UI)

- What changed: миграция `0036` — `quantity_unpacked`/`quantity_packed` на остатках; модели/API `packaging_tasks`; авто-задание при confirm отгрузки на МП; блок `ship` до выполнения задания; раздел «Упаковка» в меню ФФ; диалог упаковки из отгрузки на МП; pytest `test_packaging_tasks.py`; e2e `ff-mp-ship-pick` дополнен шагом упаковки. Спека: `docs/PACKAGING_RU.md`.
- What did NOT change: ТЗ на упаковку в карточке товара (поле `packaging_instructions` в БД есть, UI селлера — позже); кнопка «Упаковать» на сортировке; биллинг; ЧЗ.
- Commit: (pending)

## TASK-31 — 2026-05-30 — Пользователи ФФ: добавление и права доступа

- What changed: роль `fulfillment_staff`; таблица `ff_staff_permissions`; API `/auth/staff-accounts` (создание, список, PATCH прав); первый вход с пустым паролем как у селлера; экран «Настройки → Пользователи» с матрицей галочек (настройки, отгрузки МП, приёмка, ячейки, инвентаризация); фильтрация меню по правам; backend-guards на приёмку/отгрузки/ячейки.
- What did NOT change: управление селлерами (только админ); seller portal; полноценный раздел инвентаризации (заглушка).
- Verification: `ruff`/`mypy`; pytest `test_staff_users`; `npm run build`; e2e `ff-staff-users.spec.ts`, `admin-shell-layout`.
- Commit: eb73025

## TASK-30 — 2026-05-29 — Отгрузка на МП: обязательная дата + календарь

- What changed: `planned_shipment_date` обязательна для plan/confirm/ship; селлер не передаёт ФФ без даты; PATCH даты; общий `WmsDateField` (MUI DatePicker) на MP, приёмке селлера/ФФ.
- What did NOT change: создание черновика без даты; логика состава/коробов.
- Verification: `npm run build`; pytest `test_seller_marketplace_unload` (CI).
- Commit: (pending)

## TASK-29 — 2026-05-29 — Отгрузка на МП: единое поле скана (короб / ячейка / товар)

- What changed: убрана отдельная строка «Штрихкод существующего короба»; WHB-скан в общем поле → attach + закрытый короб внизу; ячейка и товар — как раньше в открытую тару.
- What did NOT change: API `/boxes/attach`, backend attach logic, закрытие короба кнопкой.
- Verification: `npm run build`.
- Commit: 88dfd8c

## TASK-28 — 2026-05-27 — Логин: видимая ошибка при неверном портале

- What changed: исправлен «тихий» сброс формы логина — при входе селлера на главный портал ФФ (или админа на `/seller/`) сообщение об ошибке больше не стирается; e2e `auth-portal-mismatch.spec.ts`.
- What did NOT change: правила разделения порталов (селлер → `/seller/`, ФФ → `/`); API auth.
- Verification: `npm run build`; e2e `auth-portal-mismatch`, `auth-core`.
- Commit: 1158a25


- What changed: операция `collect_into_box` — снятие с ячейки и количество в открытый короб в одной транзакции; **«Собрано»** = сумма по всем коробам; скан в короб требует `storage_location_id`; pick/scan товара только при открытом коробе; ручной подбор (модалка) добавляет в открытый короб; UI: сводка «Нужно / Собрано / Осталось», один блок «Сборка в короба», поле кол-ва.
- What did NOT change: создание/утверждение отгрузки селлером; проведение ship по pick allocations; attach inbound-короба (с box_lines).
- Verification: `npm run build` OK; pytest 99 passed (Docker py3.11); e2e — CI.
- Commit: 97c5289

## TASK-26 — 2026-05-27 — Отгрузка на МП: подбор по ячейкам, план/факт, короба WHB

- What changed: подбор **со списанием по ячейкам** — `POST .../pick/scan` (ячейка → товар), `POST .../pick/add`; факт = сумма pick allocations; строки API/UI **план / факт / Δ** (красный при расхождении); отгрузка `ship` с `acknowledge_discrepancy`; сквозные `warehouse_boxes` (ШК `WHB-…`) при создании короба; `POST .../boxes/attach` для существующего короба (разворот в pick); снят лимит «факт ≤ план» при скане; короба не обязательны для ship.
- What did NOT change: operational outbound; создание поставок в WB; seller UI (без подбора).
- Verification: миграция `0034`; pytest 96 passed; e2e 42 passed (`ff-mp-ship-pick`, inbound fixes); prod deploy `194.87.96.144:8088`.
- Commit: fb36cbf

## TASK-25 — 2026-05-27 — FF: отдельный раздел «Отгрузка» (документы на МП)

- What changed: в боковом меню ФФ пункт **«Отгрузка»** (`/app/ff/mp-shipments`) — только документы отгрузки на маркетплейс; из «Поставки и отгрузки» убраны отгрузки на МП и кнопка их создания; дашборд открывает плановую отгрузку в новом разделе.
- What did NOT change: API `marketplace-unload-requests`, логика модалки документа, бэкенд.
- Verification: `npm run build`; e2e `admin-shell-layout`, `ff-mp-ship-pick` (по возможности полный `test:e2e`).
- Commit: bf34625; prod deploy `194.87.96.144:8088`.

## TASK-24 — 2026-05-27 — Сортировка: агрегация по ячейкам

- What changed: блок «Уже в ячейках» — карточка на ячейку (чип + товары под ней); операция «весь короб» — строка «Короб №…» с составом; кнопка «Весь остаток короба сюда» под каждой ячейкой; убрана плоская таблица и колонка «По ячейкам».
- What did NOT change: API putaway.
- Verification: `npm run build`; e2e `ff-reception-sorting`.
- Commit: 4b6be9d

## TASK-23 — 2026-05-27 — Сортировка: история разкладки по ячейкам

- What changed: на карточке короба — блок «Уже в ячейках» (чипы + таблица); колонка «По ячейкам» у строк; fallback для строк без `box_id` при одном коробе; кнопка «Распределить по ячейкам» скрыта в workspace sorting.
- What did NOT change: API putaway и миграции; логика количеств.
- Verification: `npm run build`; e2e `ff-reception-sorting` (assert history chips).
- Commit: d122625

## TASK-22 — 2026-05-27 — Сортировка: разкладка по коробам (целиком и частично)

- What changed: `posted_qty` на строках короба; `box_id` в строках распределения; `POST .../boxes/{id}/putaway` (весь короб или частично); экран **Сортировка** — карточки коробов с составом, «Весь короб в ячейку», частичная разкладка по SKU; приёмка без изменений логики количества.
- What did NOT change: инвентаризация; резерв с зоны сортировки; полный экран «Поставки» (`workspace=full`) — старый черновик распределения с авто-`box_id` при одном коробе.
- Verification: `pytest` test_inbound_distribution + test_inbound_box_intake; `npm run build`; e2e `ff-reception-sorting`, `ff-inbound-distribution`.
- Commit: 2067093

## TASK-21 — 2026-05-27 — Приёмка / Сортировка: зона сортировки и остатки

- What changed: системная ячейка `__SORTING__`; остаток на `verify`; transfer в ячейки через `distribution-complete`; разделы FF **Приёмка** и **Сортировка**; колонки «В сортировке» / «В ячейках» в товарах; API `quantity_in_sorting`; e2e `ff-reception-sorting.spec.ts` (TC-S06-007).
- What did NOT change: инвентаризация для отката количества; резерв с зоны сортировки по-прежнему запрещён.
- Verification: `pytest` 95 passed; `npm run build`; e2e `ff-reception-sorting`, `ff-inbound-cell-hints`.
- Commit: 2de3092

## TASK-20 — 2026-05-25 — Поставка: пустое распределение не оприходует; reopen

- What changed: `complete_distribution` требует строки и полное покрытие принятого (`distribution_incomplete`); `POST .../distribution-reopen` если `posted_qty=0`; UI предупреждение + кнопка «Открыть распределение заново», блок «Завершить» при остатке «без ячейки»; подсказка в каталоге «Товары».
- What did NOT change: логика пересчёта/коробов; ff-catalog по-прежнему только с движениями.
- Verification: `pytest tests/test_inbound_distribution.py` (3 passed); prod deploy `194.87.96.144:8088`.
- Commit: 5998780

## TASK-19 — 2026-05-25 — Селлеры: MUI + email в одной форме

- What changed: `SellersScreen` на MUI (как «Товары»); форма название + email → `POST /sellers` + `POST /auth/seller-accounts` без пароля; `docs/UI_DESIGN_SYSTEM_RU.md`, онбординг в `MVP_DECISIONS_RU.md` + `AGENTS.md`; дашборд — ссылка в «Селлеры».
- What did NOT change: API не отдаёт временный пароль; логика `must_set_password` / первый вход с пустым паролем.
- Verification: `npm run build`; e2e `sellers-create-ui` (полный онбординг); prod deploy.
- Commit: dd1ab61

## TASK-18 — 2026-05-25 — Раздел «Селлеры» в портале FF

- What changed: экран `/app/ff/sellers` — список селлеров и форма «Добавить селлера» (`POST /sellers`); пункт навигации `nav-sellers`; e2e `sellers-create-ui.spec.ts` (TC-S04-001).
- What did NOT change: выдача аккаунта селлера — по-прежнему на дашборде (`POST /auth/seller-accounts`).
- Verification: `npm run build`; e2e `sellers-create-ui`, `admin-shell-layout`; prod deploy `194.87.96.144:8088`.
- Commit: b18340f

## TASK-17 — 2026-05-25 — Резерв без ячейки + накладные (MP + outbound) + deploy

- What changed: складской резерв на submit outbound без ячейки (миграция 0032); post по-прежнему требует ячейку; печать накладной на МП и operational outbound (`printShipmentWaybill.ts`); e2e `ff-mp-print-waybill`, `outbound-print-waybill`; `scripts/deploy/prod-update.sh`, `docker-compose.wms-host-8088.yml`, `docs/DEPLOY_SERVER_RU.md`.
- What did NOT change: seller box composition; consumables inbound; FIFO/FEFO (#14).
- Verification: `ruff`/`mypy`/`pytest` 93 passed; `npm run build`; e2e waybill specs passed.
- Commit: 3a15051

## TASK-16 — 2026-05-25 — Outbound submit: ячейка обязательна (#13)

- What changed: `submit` outbound возвращает `lines_missing_storage`, если у строки нет ячейки; решение в `MVP_DECISIONS_RU.md`; UI — обязательная ячейка при добавлении, форма в draft, блокировка кнопки submit; RU-сообщения в `readApiErrorMessage`; pytest + e2e `outbound-submit-storage.spec.ts`.
- What did NOT change: soft-reserve на уровне склада; seller submit outbound (по-прежнему только admin API).
- Verification: pytest `test_outbound_submit_storage.py`; e2e `outbound-submit-storage.spec.ts`; `npm run build`.
- Commit: 906bfd8

## TASK-15 — 2026-05-25 — Селлер: доступный остаток в UI (#15)

- What changed: экран «Товары» в портале селлера — колонки остаток, зарезерв., доступно и подсказка `(доступно N)` при резерве; e2e `seller-available-stock.spec.ts` (TC-S09-001); `TC_AUTOMATION_COVERAGE` / EN test-case note.
- What did NOT change: API `inventory-balances/summary`; MP-диалог (уже показывал «Доступно на ФФ»); operational outbound у селлера.
- Verification: `npm run build` ok; e2e `seller-available-stock.spec.ts` passed.
- Commit: c608196

## TASK-14 — 2026-05-25 — Хвосты MP unload + prod celery beat

- What changed: UI «Изменено ФФ» (`ff_modified`) в списке и карточке отгрузки на МП; `celery_beat` в `docker-compose.prod.yml` / `docker-compose.yml`; расписание `wms.wb_mp_warehouses_daily_sync` (03:00 UTC); плановая дата отгрузки на МП в общем списке FF.
- What did NOT change: operational outbound в кабинете селлера; деплой на сервер (вручную `git pull` + compose prod).
- Verification: `ruff`/`mypy` celery_app; `npm run build` ok.
- Commit: e31fd17

## TASK-13 — 2026-05-24 — Отгрузка на МП от селлера (TC-NEW-MP)

- What changed: отдельный документ `marketplace_unload` (не operational outbound): селлер — таблица остатков, plan/unplan, резерв; FF — confirm → короба/подбор/ship; дашборд ФФ по `submitted`; lazy-sync складов WB; миграция 0031, резервы; e2e `seller-mp-unload`, обновлены `ff-mp-ship-pick`, `ff-dashboard`.
- What did NOT change: индикатор `ff_modified` в UI; celery beat для daily WB sync; operational outbound в кабинете селлера.
- Verification: `pytest` 92 passed; `npm run build` ok; e2e seller-mp-unload, ff-mp-ship-pick, smoke passed; docker `compose build` + `up -d` (api, web, web_seller, celery_worker).
- Commit: 8c5a1c6

## TASK-12 — 2026-05-23 — Печать ШК ячейки и поиск по штрихкоду (US-C-03, US-C-06)

- What changed: кнопка печати ШК у выбранной ячейки в распределении FF; поле «Добавить по ШК» + Enter в picker; каталог FF = `/products` + WB-поля из `ff-catalog`; v2 inbound: поиск по ШК в `wb-catalog` merge, авто-выбор SKU; util `resolveProductByBarcode.ts`; e2e TC-NEW-C03/C06.
- What did NOT change: US-C-07 печать накладной приёмки.
- Verification: build ok; e2e barcode-add, distribution, inbound-intake passed.
- Commit: ac8f5ad

## TASK-11 — 2026-05-23 — Зелёные строки и «без ячейки» (US-C-04, US-C-05)

- What changed: строка товаров FF зелёная при `actual_qty === expected_qty` (`ff-inbound-line-row-match`); блок «Остаток без ячейки» — warning-фон и `data-pending=1` при нераспределённом остатке; e2e TC-NEW-C04/C05 в существующих spec.
- What did NOT change: v2 InboundScreen; глобальный список остатков (US-E-04).
- Verification: build ok; e2e box-intake + distribution 3 passed.
- Commit: 2aaae47

## TASK-9 — 2026-05-23 — Поштучная приёмка по скану короба INB (US-C-01)

- What changed: миграция `0029` (`inbound_intake_box_lines`, `intake_opened_at`/`intake_closed_at` на коробах); API `POST .../boxes/open`, `.../boxes/{id}/scan`, `.../close`; агрегация `actual_qty` по сканам; блок ручного PATCH actual при наличии коробов; UI на `FfInboundRequestView` и `InboundScreen`; pytest `test_inbound_box_intake.py` + хелпер `inbound_box_intake_helpers.py`; e2e `ff-inbound-box-intake.spec.ts` (TC-NEW-C01); обновлены регрессионные тесты/e2e под box-scan.
- What did NOT change: подсказки ячеек (US-C-02), зелёные строки, предварительные остатки только по коробам, состав короба от селлера.
- Verification: `pytest` 86 passed; `npm run build` ok; e2e 3 passed (`ff-inbound-box-intake`, `ff-inbound-distribution`).
- Commit: a9cebe6

## TASK-10 — 2026-05-23 — Подсказки ячеек при распределении (US-C-02)

- What changed: `GET /operations/inventory-balances/locations-by-product`; чипы «Уже лежит: A-01 (N)» в блоке распределения FF (`FfInboundRequestView`), клик подставляет ячейку; pytest `test_product_location_hints.py`; e2e `ff-inbound-cell-hints.spec.ts` (TC-NEW-C02).
- What did NOT change: подсказки при поштучном скане в короб (только этап распределения); v2 InboundScreen.
- Verification: pytest 87 passed; e2e cell-hints 1 passed; build ok.
- Commit: a453666

## TASK-8 — 2026-05-22 — Внутренние ШК на короба поставки (US-B-02)

- What changed: таблица `inbound_intake_boxes`, генерация N коробов с `INB-{hex}` при primary-accept; API `boxes` в заявке и `POST .../boxes/{id}/mark-label-printed`; UI панель «Короба и внутренние ШК» с печатью; миграция `0028`; pytest расширен; e2e TC-NEW-B02 в `ff-inbound-boxes.spec.ts`.
- What did NOT change: скан короба на поштучной приёмке (US-C-01), паллетирование, предварительное увеличение остатков только по коробам.
- Verification: `pytest tests/test_inbound_box_acceptance.py` (3 passed); `npm run test:e2e -- tests-e2e/ff-inbound-boxes.spec.ts` (5 passed, TC-NEW-B01/B02).
- Commit: pending

## TASK-7 — 2026-05-22 — Приёмка по коробам (US-B-01 / US-A-01)

- What changed: поля `planned_box_count` / `actual_box_count` / `boxes_discrepancy` на заявке поставки; селлер указывает план коробов в черновике; ФФ принимает факт на этапе «Принято по коробам»; предупреждение при расхождении; миграция `0027`; merge `0026`; pytest `test_inbound_box_acceptance.py`; e2e `ff-inbound-boxes.spec.ts` (TC-NEW-B01).
- What did NOT change: внутренние ШК на короба (US-B-02), предварительное увеличение остатков только по коробам, паллетирование >10 коробов.
- Verification: `pytest tests/test_inbound_box_acceptance.py`; `npm run build`; Docker `api`+`web` пересобраны.
- Commit: pending

## TASK-6 — 2026-05-22 — Отгрузка на МП: подбор по ячейкам и списание при «Отгружено»

- What changed: статус `shipped` и `POST .../ship` списывает остатки по сохранённому подбору (товар × ячейка); `PUT .../pick-allocations` сверяет сумму с фактом скана в коробах; UI — «Начать подбор», «Утвердить заявку» (без списания), «Отгружено»; миграция `0025`; e2e `ff-mp-ship-pick.spec.ts` (TC-NEW-MP-01).
- What did NOT change: ТЗ упаковки в карточке товара, статус «Начата сборка», расходники, откат отгрузки, приёмка по коробам.
- Verification: `pytest tests/test_marketplace_unload_and_discrepancy_acts.py`; `npm run build`; `npm run test:e2e -- ff-mp-ship-pick.spec.ts ff-dashboard.spec.ts`.
- Commit: pending

## TASK-5 — 2026-05-03 — Production Docker Compose HTTPS via Caddy

- What changed: production `docker-compose.prod.yml` now publishes `80/443` for Caddy, persists ACME state in Docker volumes, and passes `WMS_PUBLIC_DOMAIN` into the `web` container; production Caddy site blocks use the public domain for automatic HTTPS; added `deploy/env.prod.example` and updated README production instructions for DNS + HTTPS.
- What did NOT change: application code, database schema/migrations, Celery task definitions, and dev `docker-compose.yml` behavior were not changed in this task.
- Verification: `WMS_PUBLIC_DOMAIN=example.com POSTGRES_PASSWORD=postgres JWT_SECRET_KEY=dev-secret WMS_SECRETS_FERNET_KEY=dev-fernet DATABASE_URL='postgresql+psycopg_async://postgres:postgres@db:5432/wms' docker compose -f docker-compose.prod.yml config --quiet`; `ruff check . && mypy . && pytest` in `backend/`; `npm run build` in `frontend/`.
- Commit: 20b1aef

## TASK-3 — 2026-05-03 — Post accepted seller inbound distribution into FF stock

- What changed: completing FF inbound distribution now creates inventory movements and balances from distributed actual quantities, so accepted seller products appear in the FF warehouse catalog.
- What did NOT change: seller private WB catalog import, marketplace shipment flows, billing, migrations, and Docker infrastructure were not changed in this task.
- Verification: `ruff check app/services/inbound_intake_service.py tests/test_inbound_distribution.py && mypy app/services/inbound_intake_service.py`; `pytest tests/test_inbound_distribution.py tests/test_products_wb_catalog.py`.
- Commit: d5a954f

## TASK-2 — 2026-05-03 — Split seller and FF product catalogs

- What changed: renamed the FF products endpoint to `/products/ff-catalog` and changed FF catalog visibility to products with warehouse movements only; seller `/products/wb-catalog` remains private to the seller role.
- What did NOT change: seller WB import mechanics, marketplace shipment stock movements, adjustment acts, billing, and docker-compose infrastructure were not changed in this task.
- Verification: `ruff check app/api/products.py app/services/seller_wb_catalog_service.py tests/test_products_wb_catalog.py && mypy app/api/products.py app/services/seller_wb_catalog_service.py`; `pytest tests/test_products_wb_catalog.py`; `npm run build`; `npm run test:e2e -- ff-products.spec.ts`.
- Commit: 4089d7e

## TASK-1 — 2026-05-03 — FF products catalog

- What changed: added the fulfillment admin products catalog screen with seller filtering, sorting by product name/stock, WB photo/barcode enrichment, and backend/admin API coverage.
- What did NOT change: marketplace shipment stock movements, adjustment acts, billing, and docker-compose infrastructure were not changed in this task.
- Verification: `ruff check . && mypy . && pytest` in `backend/`; `npm run build` and `npm run test:e2e` in `frontend/`.
- Commit: 728e894
