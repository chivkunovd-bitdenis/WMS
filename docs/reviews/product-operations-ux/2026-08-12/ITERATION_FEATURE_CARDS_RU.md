# Карточки WMS-итерации 2026-08-12

Источник: второй пул требований пользователя + завершённые блоки `MASTER_PRODUCT_UX_REVIEW_RU.md` до B05. B06 ещё наполняется внешними ревьюерами и не смешивается в реализацию до handoff.

Главный gate для каждой карточки: сотрудник fulfillment открывает реальный экран и понимает, что сделать дальше, без технического текста, лишних колонок, чипов, вкладок и дублирующих кнопок.

## F01. Приёмка без отдельного процесса упаковки

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: убрать из приёмки упаковочную воронку, оставить только рабочие печатные действия.
warehouse_user: оператор приёмки ФФ.
main_real_world_scenario: оператор принимает товар и при необходимости печатает обычные товарные/ЧЗ плашки без отдельной вкладки «Упаковка».
screens_touched: карточка приёмки ФФ.
required_visible_data: товар, план, факт, габариты, ЧЗ-признак через печать товара.
forbidden_ui_noise: отдельная упаковочная стадия, FBS QR заказа, технические подсказки.
business_assumptions: коробочная приёмка не считается упаковочным процессом; это способ считать факт.
ux_decision: печать остаётся в строке товара и в накладной, отдельный упаковочный tab не добавляется.
product_review_result: approved_by_assumption.
tests_run: `inbound-receiving-v2.spec.ts` проверяет отсутствие вкладки «Упаковка» в карточке приёмки.

## F02. Габариты товара прямо из приёмки

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: дать ФФ быстро зафиксировать длину/ширину/высоту по товару при фактической приёмке.
warehouse_user: оператор приёмки или старший смены.
main_real_world_scenario: в строке товара нажимают маленькую кнопку габаритов, вводят три размера, система сохраняет объём.
screens_touched: карточка приёмки ФФ, продуктовый API.
required_visible_data: длина, ширина, высота, рассчитанный объём в литрах.
forbidden_ui_noise: большая форма товара, отдельный справочник, декоративные бейджи.
business_assumptions: объём считается из миллиметров и хранится в `products.volume_liters`.
ux_decision: одна иконка-линейка в строке, компактная модалка.
dev_result: добавлен `PATCH /products/{id}/dimensions`, поле `volume_liters`, миграция `20260812_0079`.
tests_run: `test_catalog_flow`, `inbound-receiving-v2.spec.ts`.

## F03. Приёмка с расхождениями и любыми товарами селлера

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: принять фактически приехавший пересорт, недостачу или излишек без блокировки оператора.
warehouse_user: оператор приёмки ФФ.
main_real_world_scenario: заявлен один товар, приехал другой товар того же селлера; оператор сканирует его и получает строку с планом 0, фактом больше 0.
screens_touched: карточка приёмки ФФ, inbound API.
required_visible_data: план, факт, красная строка расхождения, признак «Добавлено ФФ».
forbidden_ui_noise: отдельная таблица проблем, технические коды расхождений на экране.
business_assumptions: скан может искать только в каталоге селлера заявки, не во всём tenant-каталоге.
ux_decision: пересорт остаётся в той же таблице приёмки.
dev_result: `receiving/scan` и `receiving/lines` добавляют фактическую строку товара селлера.
tests_run: `test_inbound_receiving_accepts_seller_catalog_product_as_discrepancy`, `inbound-receiving-v2.spec.ts`.

## F04. Создание нового товара из приёмки

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: аварийно принять товар, которого нет даже в каталоге селлера.
warehouse_user: оператор ФФ.
main_real_world_scenario: оператор нажимает маленький плюс, создаёт ручной товар и добавляет его в факт.
screens_touched: карточка приёмки ФФ, диалог создания товара.
required_visible_data: селлер, название, SKU, ШК, размер, габариты, ЧЗ.
forbidden_ui_noise: делать этот путь главным сценарием.
ux_decision: маленькая icon-кнопка рядом с добавлением товаров.
tests_run: `ff-inbound-barcode-add.spec.ts`.

## F05. Единая карточка приёмки для ФФ и селлера

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: ФФ и селлер видят одну фактическую карточку: заявлено, принято, добавлено ФФ, недостача/излишек.
warehouse_user: оператор ФФ, селлер.
main_real_world_scenario: после проведения селлер открывает документ и видит факт, а не упрощённый экран.
screens_touched: карточка приёмки ФФ, селлерская карточка заявки.
ux_decision: тип операции и расхождения выводятся в существующей карточке без нового dashboard; селлер в недraft-статусах видит заявлено, факт, расхождение и «Добавлено ФФ».
product_review_result: initially_rejected, approved_after_rework.
tests_run: `inbound-receiving-v2.spec.ts`.

## F06. Накладная из приёмки печатается по факту

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: после проведения печатать накладную с фактом и расхождениями.
warehouse_user: кладовщик, селлер.
main_real_world_scenario: печать документа после приёмки показывает фактически принятое количество.
screens_touched: карточка приёмки ФФ, print utility.
business_assumptions: карточка передаёт `actual_qty` в печатный документ.
tests_run: `ff-inbound-print-waybill.spec.ts`.

## F07. FBO/MP-отгрузка по шагам FBS-like

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: сделать MP/FBO отгрузку понятной пошаговой для оператора, сохранив подбор.
warehouse_user: оператор отгрузки ФФ.
main_real_world_scenario: оператор идёт по шагам план -> подбор -> упаковка/ЧЗ -> короба -> печать/финал.
forbidden_ui_noise: QR каждого FBS-заказа, перенос специфики FBS в FBO.
product_review_result: isolated product verdict chose hybrid flow, not full FBS copy.
dev_result: MP/FBO-агент, commit `e21a895`.
tests_run: MP Playwright/e2e and unit print tests by dev agent; rerun `ff-mp-tabs.spec.ts`, `ff-mp-print-waybill.spec.ts`, `ff-mp-shipment-tz-print.spec.ts`.

## F08. Резервы/направления внутри товара

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: дать селлеру разложить остаток товара по направлениям: FBS, наборы, прочие резервы.
warehouse_user: селлер, ФФ-менеджер.
main_real_world_scenario: внутри товара создаётся направление с названием, комментарием, количеством и галкой FBS.
ux_decision: в строке товара компактная ячейка «Распределение», управление направлениями вынесено в right Drawer.
product_review_result: initially_rejected, approved_after_rework.
tests_run: `test_stock_directions.py`, `seller-stock-directions.spec.ts`.

## F09. Свободный остаток для FBO

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: FBO отгружает только остаток после всех направлений.
main_real_world_scenario: было 1000, направления 500, к FBO доступно 500.
dev_result: inventory balance отдаёт `quantity_free_fbo`.
tests_run: `test_stock_directions.py`, `seller-stock-directions.spec.ts`.

## F10. FBS-синхронизация берёт только FBS-пул

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: в WB публикуется не весь остаток, а только выделенный FBS-пул.
main_real_world_scenario: принято 1000, FBS-пул 200, в WB уходит 200.
product_review_result: initially_rejected, approved_after_rework.
tests_run: `test_stock_directions.py`, `seller-stock-directions.spec.ts`.

## F11. Каталог ФФ упростить

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: убрать мусорные колонки и оставить полезные складские данные.
dev_result: предыдущий commit `56c8a67`.
tests_run: previous slice checks; rerun `ff-products.spec.ts`.

## F12. Месячный snapshot остатков

status: product_approved, backend_tests_passed, final_regression_passed
business_goal: фиксировать остатки на 1 число месяца с разбивкой общий/FBS/резервы/свободный FBO.
tests_run: `test_stock_directions.py`.

## F13. Точечный баг Виталика

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: пользователь с доступом к нескольким селлерам не видит товары чужих селлеров.
dev_result: access scope enforced for active seller.
tests_run: `test_seller_shop_scope.py` previous backend evidence; `seller-cabinet.spec.ts` browser scenario for allowed seller switch without forbidden products.

## F14. Сотрудники селлера и ФФ

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: управлять несколькими пользователями кабинета и правами.
main_real_world_scenario: владелец селлера создаёт сотрудника и назначает права на документы/товары/ЧЗ/настройки/сотрудников.
product_review_result: initially_rejected_without_ff_evidence, approved_after_browser_evidence.
tests_run: `test_seller_staff_and_delete_drafts.py`, `test_staff_users.py`, `ff-staff-users.spec.ts`, `seller-staff-and-delete-drafts.spec.ts`.

## F15. Удаление только черновиков

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: удалить можно только черновик, проведённые документы сохраняют историю и остатки.
tests_run: `test_seller_staff_and_delete_drafts.py`, `seller-staff-and-delete-drafts.spec.ts`.

## F16. nmID нормально назвать

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: оставить nmID как данные, но назвать колонку по-русски.
product_review_result: initially_rejected, approved_after_rework.
tests_run: `seller-stock-directions.spec.ts`, frontend build.

## F17. Единый документ печати: накладная + ТЗ

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: один компактный лист с шапкой, фото, товаром, ШК, количеством, инструкциями и пустой колонкой «Факт».
dev_result: MP/FBO-агент, commit `e21a895`.
tests_run: `printShipmentPackagingSheet.test.ts`, MP print e2e by dev agent; rerun `ff-mp-print-waybill.spec.ts`, `ff-mp-shipment-tz-print.spec.ts`.

## F18. Возвраты как вариант приёмки

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: возврат идёт через форму приёмки с типом операции.
dev_result: `operation_type=inbound|return` на заявке, селлер/ФФ видят тип.
tests_run: `test_inbound_receiving_accepts_seller_catalog_product_as_discrepancy`, `inbound-receiving-v2.spec.ts`.

## F19. Возврат со сканированием и автопечатью ШК

status: product_approved, browser_qa_passed, final_regression_passed
business_goal: оператор сканирует возврат, строка растёт на +1, при включенном режиме печатается ШК.
ux_decision: маленький switch рядом со сканером только для возврата.
tests_run: `inbound-receiving-v2.spec.ts`.

## F20. Счета клиентам

status: out_of_scope_by_user
business_goal: пока оставить за рамками.

## F21. Seller Focus Pro / лендинг WMS

status: blocked_missing_repo_target
business_goal: честно описать WMS на sellerfocus.pro как отдельное направление внутри домена.
blocking_issues: в текущем WMS checkout нет исходников Seller Focus Pro, раздела "Наши продукты" или deploy target sellerfocus.pro; секреты и внешние панели не трогаются без отдельного разрешения.
