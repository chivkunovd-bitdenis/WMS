# Карточки WMS-итерации 2026-08-12

Источник: второй пул требований пользователя + завершённые блоки `MASTER_PRODUCT_UX_REVIEW_RU.md` до B05. B06 ещё наполняется внешними ревьюерами и не смешивается в реализацию до handoff.

Главный gate для каждой карточки: сотрудник fulfillment открывает реальный экран и понимает, что сделать дальше, без технического текста, лишних колонок, чипов, вкладок и дублирующих кнопок.

Важно: предыдущие пометки `browser_qa_passed` были признаны недостоверными для текущего строгого протокола. Ниже фиксируется фактическое состояние gates на текущую итерацию; фича считается завершенной только после отдельного Product/UX verdict, Code Review и живого Browser Product QA.

## Сводная матрица gate-статусов

Эта таблица явно отделяет первичный или повторный Product/UX gate от разработки,
code review и живого browser QA. `Product/UX passed` означает, что фичу можно
было отдавать в разработку; это не заменяет code review и browser QA.

| Фича | BA | Product/UX gate | Dev | Code review | Browser QA | Текущий итог |
|---|---|---|---|---|---|---|
| F01 Приёмка без упаковки | BA_READY | PRODUCT_APPROVED_FOR_DEV | DEV_DONE | CODE_REVIEW_PASSED | BROWSER_PRODUCT_QA_PASSED | integration_pending |
| F02 Габариты из приёмки | BA_READY | PRODUCT_APPROVED_FOR_DEV | DEV_DONE | CODE_REVIEW_PASSED | pending | нужен live browser QA |
| F03 Расхождения и товары селлера | BA_READY | PRODUCT_APPROVED_FOR_DEV | DEV_REWORK_DONE | CODE_REVIEW_PASSED | failed_before_fix, rerun_pending | нужен повторный live browser QA |
| F04 Ручной товар из приёмки | BA_READY | PRODUCT_APPROVED_FOR_DEV | DEV_REWORK_DONE | CODE_REVIEW_PASSED | BROWSER_PRODUCT_QA_PASSED | integration_pending |
| F05 Единая карточка ФФ/селлер | BA_READY | PRODUCT_APPROVED_AFTER_REWORK | DEV_REWORK_DONE | CODE_REVIEW_FAILED | blocked_by_code_review | нужен rework raw MP-статусов |
| F06 Накладная по факту | BA_READY | PRODUCT_APPROVED_AFTER_REWORK | DEV_DONE | CODE_REVIEW_PASSED | BROWSER_PRODUCT_QA_PASSED | integration_pending |
| F07 FBO/MP отгрузка по шагам | BA_READY | PRODUCT_APPROVED_HYBRID_FLOW | DEV_DONE | CODE_REVIEW_PASSED | BROWSER_PRODUCT_QA_PASSED | integration_pending |
| F08 Направления остатков/FBS-пул | BA_UX_REWORK_READY | PRODUCT_APPROVED_AFTER_REWORK | DEV_REWORK_DONE | CODE_REVIEW_PASSED | BROWSER_PRODUCT_QA_PASSED | integration_pending |
| F09 Свободный FBO | BA_READY | blocked_until_F08_product_passes | blocked | blocked | blocked | зависит от F08 |
| F10 FBS sync берёт FBS-пул | BA_READY | blocked_until_F08_product_passes | blocked | blocked | blocked | зависит от F08 |
| F11 Упрощённый FF каталог | BA_READY | PRODUCT_APPROVED_FOR_DEV | DEV_DONE | CODE_REVIEW_PASSED | BROWSER_PRODUCT_QA_PASSED | integration_pending |
| F12 Monthly snapshot | BA_READY | PRODUCT_APPROVED_FOR_MINIMAL_UI | DEV_DONE | CODE_REVIEW_PASSED | BROWSER_PRODUCT_QA_PASSED | integration_pending |
| F13 Доступ Виталика | BA_READY | PRODUCT_APPROVED_EXISTING_IMPL | DEV_REWORK_DONE | CODE_REVIEW_PASSED | BROWSER_PRODUCT_QA_PASSED | integration_pending |
| F14 Сотрудники и права | BA_REWORK_READY | PRODUCT_REWORK_REQUIRED | blocked | blocked | blocked | не пускать в dev/stage |
| F15 Удаление только черновиков | BA_READY | PRODUCT_APPROVED_FOR_DEV | DEV_DONE | CODE_REVIEW_PASSED | BROWSER_PRODUCT_QA_PASSED | integration_pending |
| F16 nmID по-русски | BA_READY | PRODUCT_APPROVED_AFTER_REWORK | DEV_DONE | CODE_REVIEW_PASSED | BROWSER_PRODUCT_QA_PASSED | integration_pending |
| F17 Единый печатный документ | BA_READY | PRODUCT_APPROVED_EXISTING_IMPL | DEV_DONE | CODE_REVIEW_PASSED | BROWSER_PRODUCT_QA_PASSED | integration_pending |
| F18 Возврат как вариант приёмки | BA_UX_REWORK_READY | PRODUCT_APPROVED_FOR_DEV | DEV_REWORK_DONE | CODE_REVIEW_PASSED | BROWSER_PRODUCT_QA_PASSED | integration_pending |
| F19 Возврат со сканом/autoprint | BA_UX_REWORK_READY | PRODUCT_REREVIEW_PENDING | blocked | blocked | blocked | нужен повторный Product/UX |
| F22 Safe sync остатков WMS->WB | BA_UX_READY | PRODUCT_APPROVED_FOR_DEV | DEV_DONE | CODE_REVIEW_PASSED | browser_qa_pending | нужен live browser QA |
| F23 Каталог товаров селлера cleanup | BA_UX_REWORK_READY | PRODUCT_DESIGN_APPROVED_FOR_DEV | dev_pending | blocked | blocked | можно отдавать atomic dev |
| F20 Счета клиентам | out_of_scope | out_of_scope | out_of_scope | out_of_scope | out_of_scope | вне релиза |
| F21 Seller Focus Pro | blocked_missing_repo | blocked_missing_target | blocked | blocked | blocked | нужен repo/target |

## F01. Приёмка без отдельного процесса упаковки

status: ba_ready, product_approved_for_dev, dev_done, code_review_passed, browser_qa_passed, integration_pending
business_goal: убрать из приёмки упаковочную воронку, оставить только рабочие печатные действия.
warehouse_user: оператор приёмки ФФ.
main_real_world_scenario: оператор принимает товар и при необходимости печатает обычные товарные/ЧЗ плашки без отдельной вкладки «Упаковка».
screens_touched: карточка приёмки ФФ.
required_visible_data: товар, план, факт, габариты, ЧЗ-признак через печать товара.
forbidden_ui_noise: отдельная упаковочная стадия, FBS QR заказа, технические подсказки.
business_assumptions: коробочная приёмка не считается упаковочным процессом; это способ считать факт.
ux_decision: печать остаётся в строке товара и в накладной, отдельный упаковочный tab не добавляется.
product_review_result: PRODUCT_APPROVED_FOR_DEV; отдельный упаковочный процесс не нужен, печатная плашка остаётся в приёмке.
tests_run: `inbound-receiving-v2.spec.ts` проверяет отсутствие вкладки «Упаковка» в карточке приёмки.

## F02. Габариты товара прямо из приёмки

status: ba_ready, product_approved_for_dev, dev_done, code_review_passed, browser_qa_pending
business_goal: дать ФФ быстро зафиксировать длину/ширину/высоту по товару при фактической приёмке.
warehouse_user: оператор приёмки или старший смены.
main_real_world_scenario: в строке товара нажимают маленькую кнопку габаритов, вводят три размера, система сохраняет объём.
screens_touched: карточка приёмки ФФ, продуктовый API.
required_visible_data: длина, ширина, высота, рассчитанный объём в литрах.
forbidden_ui_noise: большая форма товара, отдельный справочник, декоративные бейджи.
business_assumptions: объём считается из миллиметров и хранится в `products.volume_liters`.
ux_decision: одна иконка-линейка в строке, компактная модалка.
product_review_result: PRODUCT_APPROVED_FOR_DEV; маленькая кнопка габаритов в строке не перегружает приёмку.
dev_result: добавлен `PATCH /products/{id}/dimensions`, поле `volume_liters`, миграция `20260812_0079`.
tests_run: `test_catalog_flow`, `inbound-receiving-v2.spec.ts`.

## F03. Приёмка с расхождениями и любыми товарами селлера

status: ba_ready, product_approved_for_dev, dev_rework_done, code_review_passed, browser_qa_failed_before_fix, browser_qa_rerun_pending
business_goal: принять фактически приехавший пересорт, недостачу или излишек без блокировки оператора.
warehouse_user: оператор приёмки ФФ.
main_real_world_scenario: заявлен один товар, приехал другой товар того же селлера; оператор сканирует его и получает строку с планом 0, фактом больше 0.
screens_touched: карточка приёмки ФФ, inbound API.
required_visible_data: план, факт, красная строка расхождения, признак «Добавлено ФФ».
forbidden_ui_noise: отдельная таблица проблем, технические коды расхождений на экране.
business_assumptions: скан может искать только в каталоге селлера заявки, не во всём tenant-каталоге.
ux_decision: пересорт остаётся в той же таблице приёмки.
product_review_result: PRODUCT_APPROVED_FOR_DEV; расхождения должны быть в одной таблице факта, без отдельного экрана проблем.
dev_result: `receiving/scan` и `receiving/lines` добавляют фактическую строку товара селлера.
tests_run: `test_inbound_receiving_accepts_seller_catalog_product_as_discrepancy`, `inbound-receiving-v2.spec.ts`.

## F04. Создание нового товара из приёмки

status: ba_ready, product_approved_for_dev, dev_rework_done, code_review_passed, browser_qa_passed, integration_pending
business_goal: аварийно принять товар, которого нет даже в каталоге селлера.
warehouse_user: оператор ФФ.
main_real_world_scenario: оператор нажимает маленький плюс, создаёт ручной товар и добавляет его в факт.
screens_touched: карточка приёмки ФФ, диалог создания товара.
required_visible_data: селлер, название, SKU, ШК, размер, габариты, ЧЗ.
forbidden_ui_noise: делать этот путь главным сценарием.
ux_decision: маленькая icon-кнопка рядом с добавлением товаров.
product_review_result: PRODUCT_APPROVED_FOR_DEV; аварийный плюс допустим только как вторичный путь.
tests_run: `ff-inbound-barcode-add.spec.ts`.

## F05. Единая карточка приёмки для ФФ и селлера

status: ba_ready, product_approved_after_rework, dev_rework_done, code_review_failed, browser_qa_blocked
business_goal: ФФ и селлер видят одну фактическую карточку: заявлено, принято, добавлено ФФ, недостача/излишек.
warehouse_user: оператор ФФ, селлер.
main_real_world_scenario: после проведения селлер открывает документ и видит факт, а не упрощённый экран.
screens_touched: карточка приёмки ФФ, селлерская карточка заявки.
ux_decision: тип операции и расхождения выводятся в существующей карточке без нового dashboard; селлер в недraft-статусах видит заявлено, факт, расхождение и «Добавлено ФФ».
product_review_result: initially_rejected, PRODUCT_APPROVED_AFTER_REWORK.
tests_run: `inbound-receiving-v2.spec.ts`.

## F06. Накладная из приёмки печатается по факту

status: ba_ready, product_approved_after_rework, dev_done, code_review_passed, browser_qa_passed, integration_pending
business_goal: после проведения печатать накладную с фактом и расхождениями.
warehouse_user: кладовщик, селлер.
main_real_world_scenario: печать документа после приёмки показывает фактически принятое количество.
screens_touched: карточка приёмки ФФ, print utility.
business_assumptions: карточка передаёт `actual_qty` в печатный документ.
product_review_result: PRODUCT_APPROVED_AFTER_REWORK; печать должна идти по факту и показывать расхождения.
tests_run: `ff-inbound-print-waybill.spec.ts`.

## F07. FBO/MP-отгрузка по шагам FBS-like

status: product_approved_existing_impl, dev_rework_done, code_review_passed, browser_qa_passed, integration_pending
business_goal: сделать MP/FBO отгрузку понятной пошаговой для оператора, сохранив подбор.
warehouse_user: оператор отгрузки ФФ.
main_real_world_scenario: оператор идёт по шагам план -> подбор -> упаковка/ЧЗ -> короба -> печать/финал.
forbidden_ui_noise: QR каждого FBS-заказа, перенос специфики FBS в FBO.
product_review_result: isolated product verdict chose hybrid flow, not full FBS copy.
dev_result: MP/FBO-агент, commit `e21a895`.
tests_run: MP Playwright/e2e and unit print tests by dev agent; rerun `ff-mp-tabs.spec.ts`, `ff-mp-print-waybill.spec.ts`, `ff-mp-shipment-tz-print.spec.ts`.

## F08. Резервы/направления внутри товара

status: ba_ux_rework_ready, product_approved_after_rework, dev_rework_done, code_review_passed, browser_qa_passed, integration_pending
business_goal: дать селлеру разложить остаток товара по направлениям: FBS, наборы, прочие резервы.
warehouse_user: селлер, ФФ-менеджер.
main_real_world_scenario: внутри товара создаётся направление с названием, комментарием, количеством и галкой FBS.
ux_decision: в строке товара компактная ячейка «Распределение», управление направлениями вынесено в right Drawer.
product_review_result: initially PRODUCT_REWORK_REQUIRED; after rework PRODUCT_APPROVED_AFTER_REWORK.
dev_result: compact drawer CRUD directions, human error for excess quantity, no `Лимит`, no bulk enable/disable, geometry fix for seller table and FF distribution popover.
code_review_result: CODE_REVIEW_PASSED; artifact `evidence/f08-code-review-after-geometry/F08_CODE_REVIEW_RU.md`.
browser_qa_result: BROWSER_PRODUCT_QA_PASSED; artifact `evidence/f08-browser-product-qa-final/F08_BROWSER_PRODUCT_QA_FINAL_RU.md`.
tests_run: `test_stock_directions.py`, `seller-stock-directions.spec.ts`, headed browser QA on 1280px.

## F09. Свободный остаток для FBO

status: ba_artifact_exists, blocked_until_F08_passes_product_and_dev, strict_product_gate_pending, dev_pending, code_review_pending, browser_qa_pending
business_goal: FBO отгружает только остаток после всех направлений.
main_real_world_scenario: было 1000, направления 500, к FBO доступно 500.
dev_result: inventory balance отдаёт `quantity_free_fbo`.
tests_run: `test_stock_directions.py`, `seller-stock-directions.spec.ts`.

## F10. FBS-синхронизация берёт только FBS-пул

status: ba_artifact_exists, blocked_until_F08_passes_product_and_dev, strict_product_gate_pending, dev_pending, code_review_pending, browser_qa_pending
business_goal: в WB публикуется не весь остаток, а только выделенный FBS-пул.
main_real_world_scenario: принято 1000, FBS-пул 200, в WB уходит 200.
product_review_result: blocked_until_F08_product_passes.
tests_run: `test_stock_directions.py`, `seller-stock-directions.spec.ts`.

## F11. Каталог ФФ упростить

status: product_approved_for_dev, dev_done, code_review_passed, browser_qa_passed, integration_pending
business_goal: убрать мусорные колонки и оставить полезные складские данные.
dev_result: предыдущий commit `56c8a67`.
tests_run: previous slice checks; rerun `ff-products.spec.ts`.

## F12. Месячный snapshot остатков

status: product_approved_for_minimal_ui, dev_done, code_review_passed, browser_qa_passed, integration_pending
business_goal: фиксировать остатки на 1 число месяца с разбивкой общий/FBS/резервы/свободный FBO.
product_review_result: PRODUCT_APPROVED_FOR_MINIMAL_UI; отдельный минимальный экран FF inventory допустим без перегруза.
tests_run: `test_stock_directions.py`.

## F13. Точечный баг Виталика

status: product_approved_existing_impl, dev_rework_done, code_review_passed, browser_qa_passed, integration_pending
business_goal: пользователь с доступом к нескольким селлерам не видит товары чужих селлеров.
product_review_result: PRODUCT_APPROVED_EXISTING_IMPL; чинится фильтрация доступа, не UI-редизайн.
dev_result: access scope enforced for active seller.
tests_run: `test_seller_shop_scope.py` previous backend evidence; `seller-cabinet.spec.ts` browser scenario for allowed seller switch without forbidden products.

## F14. Сотрудники селлера и ФФ

status: ba_rework_ready, product_rejected_rework_required, dev_pending, code_review_pending, browser_qa_pending
business_goal: управлять несколькими пользователями кабинета и правами.
main_real_world_scenario: владелец селлера создаёт сотрудника и назначает права на документы/товары/ЧЗ/настройки/сотрудников.
product_review_result: PRODUCT_REWORK_REQUIRED; строгий gate не пройден, dev/stage запрещены.
tests_run: `test_seller_staff_and_delete_drafts.py`, `test_staff_users.py`, `ff-staff-users.spec.ts`, `seller-staff-and-delete-drafts.spec.ts`.

## F15. Удаление только черновиков

status: product_approved_for_dev, dev_done, code_review_passed, browser_qa_passed, integration_pending
business_goal: удалить можно только черновик, проведённые документы сохраняют историю и остатки.
tests_run: `test_seller_staff_and_delete_drafts.py`, `seller-staff-and-delete-drafts.spec.ts`.

## F16. nmID нормально назвать

status: ba_ready, product_approved_after_rework, dev_done, code_review_passed, browser_qa_passed, integration_pending
business_goal: оставить nmID как данные, но назвать колонку по-русски.
product_review_result: initially_rejected, PRODUCT_APPROVED_AFTER_REWORK.
tests_run: `seller-stock-directions.spec.ts`, frontend build.

## F17. Единый документ печати: накладная + ТЗ

status: product_approved_for_dev_existing_impl, code_review_passed, browser_qa_passed, integration_pending
business_goal: один компактный лист с шапкой, фото, товаром, ШК, количеством, инструкциями и пустой колонкой «Факт».
dev_result: MP/FBO-агент, commit `e21a895`.
tests_run: `printShipmentPackagingSheet.test.ts`, MP print e2e by dev agent; rerun `ff-mp-print-waybill.spec.ts`, `ff-mp-shipment-tz-print.spec.ts`.

## F18. Возвраты как вариант приёмки

status: ba_ux_rework_ready, product_approved_for_dev, dev_rework_done, code_review_passed, browser_qa_passed, integration_pending
business_goal: возврат идёт через форму приёмки с типом операции.
product_review_result: initially_rejected, PRODUCT_APPROVED_FOR_DEV_AFTER_BA_UX_REWORK.
dev_result: `operation_type=inbound|return` на заявке, селлер/ФФ видят тип.
code_review_result: CODE_REVIEW_PASSED after containment rework.
browser_qa_result: BROWSER_PRODUCT_QA_PASSED; artifact `evidence/f18-browser-product-qa-final/QA_RESULT_RU.md`.
tests_run: `test_inbound_receiving_accepts_seller_catalog_product_as_discrepancy`, `inbound-receiving-v2.spec.ts`, `seller-inbound-operation-type.spec.ts`.

## F19. Возврат со сканированием и автопечатью ШК

status: ba_ux_rework_ready, product_rereview_pending, dev_blocked, code_review_blocked, browser_qa_blocked
business_goal: оператор сканирует возврат, строка растёт на +1, при включенном режиме печатается ШК.
ux_decision: маленький switch рядом со сканером только для возврата.
product_review_result: initially_rejected; BA/UX rework ready, repeat Product/UX gate still pending.
tests_run: `inbound-receiving-v2.spec.ts`.

## F22. Safe sync остатков WMS -> WB / ЛК селлера

status: ba_ux_ready, product_approved_for_dev, dev_done, code_review_passed, browser_qa_pending
business_goal: не допустить зануления или неверной публикации остатков в WB/ЛК селлера при включении синхронизации, ошибке API, пустом расчете или отсутствии явного FBS-пула.
warehouse_user: селлер или ФФ-менеджер, который включает синхронизацию FBS-остатков и ожидает, что WMS не испортит реальные остатки в WB.
main_real_world_scenario: в ЛК WB у товара 20 шт; пользователь включает sync в WMS; если WMS не может безопасно посчитать явный FBS-пул или получает ошибку WB, система не отправляет 0, не помечает успех и показывает человеку понятную ошибку/причину без технического мусора.
screens_touched: кабинет селлера с товарами/направлениями, статус синхронизации FBS, backend-сервис публикации остатков WB.
required_visible_data: общий остаток WMS, выделенный FBS-пул, количество к отправке, последний подтвержденный WB/WMS sync result, понятная ошибка последней попытки.
forbidden_ui_noise: технические коды ошибок как основной текст, цветные лишние чипы, колонка "Лимит" как отдельная перегружающая сущность, автопубликация нуля без явного безопасного основания.
primary_actions: включить sync только после понятного расчета; повторить sync; открыть распределение FBS-пула.
secondary_actions: посмотреть причину ошибки и последний подтвержденный остаток.
empty_state: FBS-пул не выделен, поэтому в WB ничего не отправляем.
error_state: ошибка WB/токена/расчета не меняет WB-остаток и видна человеку как "не отправлено".
success_state: WB подтвердил именно рассчитанное количество, и это количество сохранено как последний подтвержденный результат.
business_assumptions: публикация 0 допустима только если есть явный, проверенный и продуктово утвержденный сценарий нулевого FBS-пула; ошибка, неизвестное состояние или отсутствие FBS-пула не равны нулю.
ux_decision: статус sync должен быть компактным и человеческим, без раздутых колонок и кнопок; основной ответ экрана - сколько реально уйдет в WB и почему.
product_review_result: PRODUCT_APPROVED_FOR_DEV; artifact `evidence/f22-product-review/F22_PRODUCT_VERDICT_SAFE_STOCK_SYNC_RU.md`.
dev_result: backend fail-closed before WB PUT; missing FBS pool / missing safe availability / `fbs_stock_limit=0` no longer becomes unsafe `amount=0`; stale sync items no longer auto-zero.
code_review_result: CODE_REVIEW_PASSED; artifact `evidence/f22-code-review/F22_CODE_REVIEW_RU.md`.
browser_qa_result: pending live seller UI proof, especially WB/emulator `20 -> 20` without FBS pool.
changed_files: `backend/app/services/fbs_stock_sync_service.py`, `backend/tests/test_fbs_stock_sync.py`, `backend/tests/test_fbs_stock_emulator_integration.py`.
tests_run: backend targeted sync tests, ruff, mypy, full backend pytest by dev; code review reran targeted `23 passed`.
commit_or_patch_ref: dev commit `f62e592c8bec7a0b8c7586fc0fc865b02f15b5e2`, review commit `f1fbb100131d880008652bd6274340bae065bbe2`.
blocking_issues: нужно проверить текущий `fbs_stock_sync_service`, включение `stock_sync_enabled`, zeroed targets и поведение при ошибке WB/readback.

## F23. Каталог товаров селлера cleanup

status: ba_ux_rework_ready, product_design_approved_for_dev, dev_done, code_review_pending, browser_qa_blocked
business_goal: привести каталог товаров селлера к рабочему виду без визуального мусора, перегруза FBS-sync и сломанной геометрии.
warehouse_user: селлер/ФФ-менеджер, который смотрит остатки, распределение и FBS-публикацию по товарам.
main_real_world_scenario: пользователь открывает каталог, видит товары и остатки, выделяет нужные строки и выполняет одно действие; таблица не раздувается чипами, полями и дублирующими кнопками.
screens_touched: seller products/catalog stock screen, возможно общий FF catalog только если источник black-strip/overflow общий.
required_visible_data: SKU/ШК, русский артикул WB, название, складские остатки, распределение, компактный статус FBS-публикации.
forbidden_ui_noise: чиповый хаос, постоянная колонка/поле `Лимит`, две массовые кнопки включить/выключить вместо выбора строк и одного действия, raw technical labels, black strip/page overflow, дублирующие действия.
primary_actions: выбрать товары, выполнить одно массовое действие; открыть распределение; настроить FBS-пул.
secondary_actions: повторить sync или открыть компактные детали статуса.
empty_state: нет товаров или нет FBS-пула без опасной публикации нуля.
error_state: человеческая ошибка без технического кода и без раздувания строки.
success_state: таблица укладывается в 1280px, основные действия видны, FBS-публикация понятна без лишних controls.
business_assumptions: текущий скрин пользователя является достаточным evidence для отдельного Product/Design gate; dev запрещён до verdict обоих ревьюеров.
ux_decision: initial DESIGN_REWORK_REQUIRED; rework spec ready in `evidence/f23-ba-ux-rework/F23_BA_UX_REWORK_SPEC_RU.md`; repeat Product+Design gate approved.
product_review_result: initially PRODUCT_REWORK_REQUIRED; repeat verdict PRODUCT_DESIGN_APPROVED_FOR_DEV in `evidence/f23-product-design-rereview/F23_PRODUCT_DESIGN_REREVIEW_RU.md`.
dev_result: selected-row bulk publication flow; removed permanent "всем" actions and main-table `Лимит`; compact FBS statuses; 1280px overflow guard; F08 directions drawer CRUD preserved by targeted e2e.
code_review_result: pending_after_dev.
browser_qa_result: blocked_until_dev.
changed_files: `frontend/src/screens/v2/SellerProductsStockScreen.tsx`, `frontend/tests-e2e/seller-stock-directions.spec.ts`.
tests_run: `npm run build`; `npx playwright test frontend/tests-e2e/seller-stock-directions.spec.ts`.
commit_or_patch_ref: pending_commit.
blocking_issues: code review и browser product QA ещё не пройдены; commit зависит от чистого выделения F23 diff из уже грязных F08/F22 файлов.

## F20. Счета клиентам

status: out_of_scope_by_user
business_goal: пока оставить за рамками.

## F21. Seller Focus Pro / лендинг WMS

status: blocked_missing_repo_target
business_goal: честно описать WMS на sellerfocus.pro как отдельное направление внутри домена.
blocking_issues: в текущем WMS checkout нет исходников Seller Focus Pro, раздела "Наши продукты" или deploy target sellerfocus.pro; секреты и внешние панели не трогаются без отдельного разрешения.
