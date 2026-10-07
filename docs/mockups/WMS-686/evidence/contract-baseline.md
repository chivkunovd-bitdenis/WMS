# WMS-686 · фактический прогон контракта на базе (без продуктовой реализации)

Дата: 08.10.2026, облачная сессия `session_01WwBDWjkcHpts2CqPJApqJY` (модель
`claude-opus-5-5`). Код продукта — `origin/etalon` `a5df04f`; продуктовые файлы
(`backend/app`, `frontend/src` кроме новых `*.test.tsx`) не изменены.
Контракт — коммит `75c1bc6` («WMS-686: контракт тестов»).

## Команды

```sh
cd backend
pytest -n 0 -q tests/test_wms686_fbo_kiz_contract.py \
  "tests/test_wms632_fbo_reserve_model.py::test_pick_and_box_only_move_location_and_keep_reserve" \
  "tests/test_wms632_fbo_reserve_model.py::test_complete_writes_off_fact_once_and_releases_reserve" \
  "tests/test_wms679_wb_fbw_export_contract.py::test_c1_c2_c3_c4_c6_wb_export_is_exact_string_xlsx_from_existing_boxes" \
  --junitxml=backend.xml
ruff check tests/test_wms686_fbo_kiz_contract.py && mypy tests/test_wms686_fbo_kiz_contract.py
cd ../frontend
npx vitest run src/screens/ff/unload-pick/FfUnloadPickPage.wms686.dom.test.tsx \
  src/screens/ff/FfSuppliesShipmentsPage.wms686.dom.test.tsx --reporter=json --outputFile.json=frontend.json
npx tsc --noEmit -p tsconfig.app.json
cd ..
python3 docs/mockups/WMS-686/ci/contract_report.py --junit backend=backend.xml --vitest frontend.json \
  --expected docs/mockups/WMS-686/ci/expected_baseline.json --out summary.md
```

Итог: бэкенд контракт — 6 passed / 31 failed; существующие тесты C25/C30 — 3 passed;
фронт — 1 passed / 17 failed; `ruff`, `mypy`, `tsc` — без ошибок; сводка — exit 0
(нет BROKEN, все зелёные на базе тесты зелёные). C50/C51 помечены
`postgresql_concurrency`; на PostgreSQL их прогоняет целевой workflow
`.github/workflows/wms686-contract.yml` (локально — SQLite).

Доказательство назначения зелёных тестов (отдельные тестировщики, временная порча
продуктового кода с откатом): C1, C3, C6, C11, C13, C32, C51 — см. колонку «Факт
прогона на базе» в `docs/requirements/WMS-686.md`.

Найденный при прогоне дефект вне задачи: «Завершить» товара с ЧЗ без кодов даёт
500 вместо 422 (риск K24).

## Сводка `contract_report.py`

GREEN: 10 · RED (функции нет, падение на проверке): 48 · BROKEN: 0

| Тест | Результат | Причина |
| --- | --- | --- |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c03_each_product_scan_takes_one_unit_from_selected_box_to_sorting` | GREEN |  |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c06_product_without_honest_sign_ships_without_any_kiz` | GREEN |  |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c11_whole_mixed_warehouse_box_attaches_once_without_opening` | GREEN |  |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c13_one_box_is_split_between_two_shipments_and_overdraw_is_refused` | GREEN |  |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c32_seller_downloads_wb_xlsx_of_own_shipment` | GREEN |  |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c04_kiz_after_product_links_to_source_without_changing_quantity` | RED | AssertionError: КИЗ обработан как 'product': {'kind': 'product', 'storage_location_id': '760ac0ce-0f3e-43ad-ad46-904b7565b2d6', 'location_code': None, 'product_id': '29a4c5f0-997f-4bde-aa61-f647a673ade7', 'sku_code': 'SKU-dba2b7c3', 'product_name': 'Футболка 48', 'picked_qty': 2, 'allocation_quantit |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c07_repeated_kiz_is_already_linked_without_unit_or_second_link` | RED | AssertionError: КИЗ обработан как 'product': {'kind': 'product', 'storage_location_id': 'b9cd722c-5de0-4cc4-bdb8-58ba22aa1103', 'location_code': None, 'product_id': '6be8c03c-0464-47d4-b2bf-f09f8394ac22', 'sku_code': 'SKU-672a2bf6', 'product_name': 'Футболка 48', 'picked_qty': 2, 'allocation_quantit |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c08_kiz_beyond_picked_units_is_refused_without_quantity_change` | RED | AssertionError: КИЗ обработан как 'product': {'kind': 'product', 'storage_location_id': '801b3a36-d994-4f7e-aff4-c3bfca24790a', 'location_code': None, 'product_id': 'ad539719-f055-42cd-a760-a4f6a921373e', 'sku_code': 'SKU-94c65c78', 'product_name': 'Футболка 48', 'picked_qty': 2, 'allocation_quantit |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c09_kiz_of_another_shipment_is_refused_and_first_link_kept` | RED | AssertionError: КИЗ обработан как 'product': {'kind': 'product', 'storage_location_id': 'ea797807-21ce-418b-9fe3-3217a4b62036', 'location_code': None, 'product_id': '2093eada-9f1f-4257-a264-911e8cda182f', 'sku_code': 'SKU-cbaaf1f5', 'product_name': 'Футболка 48', 'picked_qty': 2, 'allocation_quantit |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c10_kiz_of_other_product_after_product_scan_is_refused` | RED | AssertionError: КИЗ товара B не отклонён: {"kind":"product","storage_location_id":"0f620a30-3331-4f70-b480-f0ea83c04687","location_code":null,"product_id":"fc298502-d85d-4459-942f-afca60c33ffb","sku_code":"SKU-97a69e01","product_name":"Футболка 48","picked_qty":2,"allocation_quantity":2,"container_k |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c14_decrease_returns_unmarked_unit_first_and_refuses_marked_one` | RED | AssertionError: КИЗ обработан как 'product': {'kind': 'product', 'storage_location_id': '7027cee5-8bef-4262-842d-bc7d54e7e749', 'location_code': None, 'product_id': '8bd283ee-e447-47b2-85e2-dc625c9bc0ce', 'sku_code': 'SKU-c4761f8c', 'product_name': 'Футболка 48', 'picked_qty': 2, 'allocation_quantit |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c15_removing_kiz_keeps_quantity_and_repeat_is_noop` | RED | AssertionError: КИЗ обработан как 'product': {'kind': 'product', 'storage_location_id': '3f114039-c6e0-4557-9d7d-16e07ab700fd', 'location_code': None, 'product_id': '8799eb8d-c6cb-4cb5-a9fa-ed42814468b9', 'sku_code': 'SKU-a6b45649', 'product_name': 'Футболка 48', 'picked_qty': 2, 'allocation_quantit |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c16_pick_scan_replay_with_same_key_takes_one_unit` | RED | AssertionError: повтор M1 снял вторую |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c19_packing_scan_boxes_only_picked_units_without_stock_moves` | RED | AssertionError: упаковка сняла товар со склада: {"kind":"product","container_kind":null,"container_id":null,"container_code":null,"storage_location_id":"4482f260-8ef5-4adf-ae58-4c96997c028f","location_code":null,"id":"a784e011-7565-48ed-85a5-07bece9c8e9e","product_id":"e342da0d-b72f-4363-8eaf-f16df3 |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c20_packing_kiz_links_to_current_box_and_repeat_is_idempotent` | RED | AssertionError: КИЗ не принят: 422 {"detail":"location_required"} |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c24_scanned_kiz_counts_as_marking_so_ship_passes_without_printing` | RED | AssertionError: КИЗ обработан как 'product': {'kind': 'product', 'storage_location_id': 'ccb449f2-3fb0-4c29-a9ce-ef4b9cb27f7e', 'location_code': None, 'product_id': 'b61fb1a6-b859-4103-a81c-4ed20b65142a', 'sku_code': 'SKU-78f51ab7', 'product_name': 'Футболка 48', 'picked_qty': 2, 'allocation_quantit |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c26_intake_kiz_shows_intake_number_external_kiz_shows_none` | RED | AssertionError: КИЗ обработан как 'product': {'kind': 'product', 'storage_location_id': '56c2828a-5c00-4ad1-aad3-3e252b9e0819', 'location_code': None, 'product_id': '9aa77bdc-bd88-4b7c-a0ae-393b1052d204', 'sku_code': 'SKU-50699804', 'product_name': 'Футболка 48', 'picked_qty': 2, 'allocation_quantit |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c27_ship_writes_shipped_event_and_cancel_releases_codes` | RED | AssertionError: КИЗ обработан как 'product': {'kind': 'product', 'storage_location_id': '60daefde-ad99-4a70-ad51-b936ed161496', 'location_code': None, 'product_id': '11e9bcb4-b249-47c6-80dd-6b65750ea553', 'sku_code': 'SKU-a9f06d51', 'product_name': 'Футболка 48', 'picked_qty': 2, 'allocation_quantit |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c28_honest_sign_history_csv_has_kiz_with_fbo_shipment_number` | RED | AssertionError: КИЗ не принят: 422 {"detail":"plan_limit_exceeded"} |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c29_attached_intake_box_keeps_its_barcode_in_shipment_and_xlsx` | RED | AssertionError: ШК короба приёмки потерян |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c31_pass_attach_download_replace_by_ff_and_seller_ship_without_pass` | RED | AssertionError: {"detail":"Not Found"} |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c37_remove_marked_unit_from_box_returns_it_to_its_source_once` | RED | AssertionError: КИЗ обработан как 'product': {'kind': 'product', 'storage_location_id': '2cc51fab-43e5-4805-a3c5-5fee797f2d3f', 'location_code': None, 'product_id': 'f87ad08b-541a-4203-8779-73b85fde2e91', 'sku_code': 'SKU-10f9af7c', 'product_name': 'Футболка 48', 'picked_qty': 2, 'allocation_quantit |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c38_remove_unmarked_unit_goes_to_its_source_then_all_marked_is_ambiguous` | RED | AssertionError: КИЗ обработан как 'product': {'kind': 'product', 'storage_location_id': 'b70f1734-bed5-47d1-a71a-7d5153d960b3', 'location_code': None, 'product_id': '7407f636-5ea8-42d9-a66b-8a130816eae8', 'sku_code': 'SKU-dc2260e5', 'product_name': 'Футболка 48', 'picked_qty': 2, 'allocation_quantit |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c40_kiz_goes_only_to_the_box_in_url_and_not_to_a_neighbour_box` | RED | AssertionError: КИЗ не принят: 422 {"detail":"barcode_unknown"} |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c41_kiz_of_earlier_product_after_other_product_scan_is_refused` | RED | AssertionError: assert 'plan_limit_exceeded' == 'marking_code_other_product' |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c42_picked_kiz_is_confirmed_in_box_without_new_unit_or_link` | RED | AssertionError: КИЗ обработан как 'product': {'kind': 'product', 'storage_location_id': '9acee8b8-eb7a-447e-b208-7f522fe19ef0', 'location_code': None, 'product_id': '284ccb30-a1f8-4873-99a9-1d7ea611e2e0', 'sku_code': 'SKU-6cc8b31d', 'product_name': 'Футболка 48', 'picked_qty': 2, 'allocation_quantit |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c43_print_marking_takes_one_pool_code_per_unit_and_respects_picked_codes` | RED | AssertionError: {"detail":"Not Found"} |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c46_exactly_known_code_is_shown_and_moves_with_whole_box` | RED | AssertionError: КИЗ обработан как 'product': {'kind': 'product', 'storage_location_id': '7e7945fd-e2de-4609-aa0e-b71ae9502804', 'location_code': None, 'product_id': 'fc28f17b-6134-4f13-aa03-77dd889db360', 'sku_code': 'SKU-62ee4f07', 'product_name': 'Футболка 48', 'picked_qty': 2, 'allocation_quantit |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c47_one_box_split_by_exact_codes_and_unknown_rest_is_not_invented` | RED | AssertionError: КИЗ обработан как 'product': {'kind': 'product', 'storage_location_id': '7c79f211-9057-42c5-92b6-ac6131131971', 'location_code': None, 'product_id': '285cbc06-b8c5-46df-9b9e-2e8dffb37a41', 'sku_code': 'SKU-c2b72776', 'product_name': 'Футболка 48', 'picked_qty': 2, 'allocation_quantit |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c49_other_organization_gets_404_on_shipment_kiz_links` | RED | AssertionError: {"detail":"Not Found"} |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c50_same_kiz_in_two_shipments_at_once_has_one_winner` | RED | AssertionError: ['{"kind":"product","storage_location_id":"7a02450f-1e47-4a6e-9770-d1dd24d8a0db","location_code":null,"product_id":"63..."Футболка 48","picked_qty":2,"allocation_quantity":2,"container_kind":null,"container_id":null,"container_code":null}'] |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c51_last_unit_of_source_taken_at_once_by_two_shipments_goes_to_one` | GREEN |  |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c54_check_context_links_kiz_to_counted_unit_without_new_unit` | RED | AssertionError: КИЗ не принят: 422 {"detail":"barcode_unknown"} |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c55_known_code_becomes_uncertain_after_unmarked_pick_and_stays_behind` | RED | AssertionError: КИЗ обработан как 'product': {'kind': 'product', 'storage_location_id': '16a3d166-0ba7-46d1-8590-19cea78ad283', 'location_code': None, 'product_id': 'e6065016-4d0c-4290-92e8-d2a97afb811b', 'sku_code': 'SKU-a4617fa1', 'product_name': 'Футболка 48', 'picked_qty': 2, 'allocation_quantit |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c56_box_code_with_unknown_source_needs_chosen_return_place` | RED | AssertionError: КИЗ не принят: 422 {"detail":"plan_limit_exceeded"} |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c57_atomic_return_makes_code_known_but_unlink_and_decrease_does_not` | RED | AssertionError: КИЗ обработан как 'product': {'kind': 'product', 'storage_location_id': '4becb128-bb4e-469f-a88b-4678239f0343', 'location_code': None, 'product_id': '384a0043-a642-4c33-ace1-48972bbaf31b', 'sku_code': 'SKU-20e8cb22', 'product_name': 'Футболка 48', 'picked_qty': 2, 'allocation_quantit |
| `backend/tests/test_wms686_fbo_kiz_contract.py::test_c58_scan_of_another_box_while_box_selected_switches_source` | RED | AssertionError: ШК короба K2 не распознан как тара: {"detail":"barcode_unknown"} |
| `backend/tests/test_wms632_fbo_reserve_model.py::test_pick_and_box_only_move_location_and_keep_reserve` | GREEN |  |
| `backend/tests/test_wms632_fbo_reserve_model.py::test_complete_writes_off_fact_once_and_releases_reserve` | GREEN |  |
| `backend/tests/test_wms679_wb_fbw_export_contract.py::test_c1_c2_c3_c4_c6_wb_export_is_exact_string_xlsx_from_existing_boxes` | GREEN |  |
| `frontend/src/screens/ff/FfSuppliesShipmentsPage.wms686.dom.test.tsx::c18 C18/R12: на «Упаковке» FBO есть поле скана и галки «Печатать ШК», «Печатать ЧЗ», «Перепечатывать ЧЗ», без «Печатать QR»` | RED | AssertionError: на вкладке «Упаковка» FBO есть поле скана [data-testid="fbo-pack-scan"]: expected null not to be null |
| `frontend/src/screens/ff/FfSuppliesShipmentsPage.wms686.dom.test.tsx::c21 C21/R13/R14: короб B1 — ШК → укладка в B1 без снятия со склада и +1; КИЗ → новая строка под товаром; второй ШК+КИЗ → вторая строка` | RED | AssertionError: ШК товара на «Упаковке» уходит в POST …/boxes/B1/scan: expected [] to have a length of 1 but got +0 |
| `frontend/src/screens/ff/FfSuppliesShipmentsPage.wms686.dom.test.tsx::c22 C22/R15: скан ШК короба этой отгрузки делает его текущим — следующий ШК уходит в него, присоединения нет` | RED | AssertionError: после скана короба B1 ШК товара уложен в B1: expected [] to have a length of 1 but got +0 |
| `frontend/src/screens/ff/FfSuppliesShipmentsPage.wms686.dom.test.tsx::c23 C23/R16: «Печатать ШК» — одно задание WMS Print на единицу с уникальным ключом; галка снята — печати нет` | RED | AssertionError: галка «Печатать ШК» на «Упаковке» FBO: expected null not to be null |
| `frontend/src/screens/ff/FfSuppliesShipmentsPage.wms686.dom.test.tsx::c39 C39/R28: в «Сборке» у строки товара закрытого короба «Убрать» — пункты «КИЗ … (источник известен)», «КИЗ … — источник неизвестен» с выбором места, «Без КИЗ»; запросы …/lines/{line}/remove с marking_code_id, для кода без источника — с return_to` | RED | AssertionError: «Убрать» у строки товара в карточке закрытого короба: expected null not to be null |
| `frontend/src/screens/ff/FfSuppliesShipmentsPage.wms686.dom.test.tsx::c44 C44/R16б,в,г: «Печатать ЧЗ» ×2 — код из пула и задания k, k:c2, строка КИЗ новая; «Перепечатывать ЧЗ» ×2 — два задания на скан КИЗ без запроса в пул` | RED | AssertionError: галка «Печатать ЧЗ» на «Упаковке» FBO: expected null not to be null |
| `frontend/src/screens/ff/FfSuppliesShipmentsPage.wms686.dom.test.tsx::c45 C45/R16г/R31 (WMS Print отвечает ошибкой): ошибка в поле скана, укладка не откатывается, «Повторить печать» — тот же idempotencyKey; после снятия галки повтора нет` | RED | AssertionError: галка «Печатать ШК» на «Упаковке» FBO: expected null not to be null |
| `frontend/src/screens/ff/FfSuppliesShipmentsPage.wms686.dom.test.tsx::c45 C45/R16г/R31 (обрыв ответа WMS Print): ошибка в поле скана, укладка не откатывается, «Повторить печать» — тот же idempotencyKey; после снятия галки повтора нет` | RED | AssertionError: галка «Печатать ШК» на «Упаковке» FBO: expected null not to be null |
| `frontend/src/screens/ff/FfSuppliesShipmentsPage.wms686.dom.test.tsx::c48 C48/R32: «Закрыть короб» в поле скана — POST …/boxes/B1/close, следующий ШК уходит в B2; скан ШК B1 — следующий ШК снова в B1` | RED | AssertionError: «Закрыть короб» в поле скана упаковки: expected null not to be null |
| `frontend/src/screens/ff/FfSuppliesShipmentsPage.wms686.dom.test.tsx::c54 C54/R6б/R14/D16 (упаковка): скан ШК короба B1 → КИЗ без ШК — укладка кода в B1 без product_id, строка КИЗ под товаром, «Упаковано» прежнее; неизвестный GTIN — «Сначала отсканируйте ШК товара»` | RED | AssertionError: КИЗ после скана ШК короба уходит в POST …/boxes/B1/scan: expected [] to have a length of 1 but got +0 |
| `frontend/src/screens/ff/unload-pick/FfUnloadPickPage.wms686.dom.test.tsx::c01 C1/R1: скан короба K1 держит источник для серии ШК; скан короба K2 меняет его` | GREEN |  |
| `frontend/src/screens/ff/unload-pick/FfUnloadPickPage.wms686.dom.test.tsx::c02 C2/R1: после ответа 500 на ручную правку «Снять» короб K1 остаётся источником, ШК уходит с K1, после перезагрузки — снова K1` | RED | AssertionError: после ошибки pick/set строка «Снимаем с:» всё ещё K1: expected '' to contain 'INB-000123' |
| `frontend/src/screens/ff/unload-pick/FfUnloadPickPage.wms686.dom.test.tsx::c05 C5/R3/R11: короб → ШК → КИЗ подряд: третий pick/scan несёт КИЗ, товар и короб; строка КИЗ новая; «осталось» не меняется от КИЗ` | RED | AssertionError: КИЗ уходит с product_id отсканированного товара: expected undefined to be 'p-a' // Object.is equality |
| `frontend/src/screens/ff/unload-pick/FfUnloadPickPage.wms686.dom.test.tsx::c12 C12/R7: после скана короба кнопка «Забрать целиком» отправляет присоединение этого короба` | RED | AssertionError: в строке «Снимаем с:» есть «Забрать целиком»: expected null not to be null |
| `frontend/src/screens/ff/unload-pick/FfUnloadPickPage.wms686.dom.test.tsx::c17 C17/R10: каждый скан ШК в pick/scan несёт свой mutation_id, у двух сканов ключи разные` | RED | AssertionError: запрос pick/scan несёт mutation_id: expected 'undefined' to be 'string' // Object.is equality |
| `frontend/src/screens/ff/unload-pick/FfUnloadPickPage.wms686.dom.test.tsx::c52 C52/R11/R33г: ответ на ШК задержан 300 мс — КИЗ, считанный раньше ответа, уходит после него и с product_id этого товара` | RED | AssertionError: КИЗ уходит с product_id товара, отсканированного перед ним: expected undefined to be 'p-a' // Object.is equality |
| `frontend/src/screens/ff/unload-pick/FfUnloadPickPage.wms686.dom.test.tsx::c53 C53/R9г: ШК → КИЗ → «Отменить последнее снятие» удаляет связь КИЗ, «осталось» прежнее` | RED | AssertionError: отмена последнего скана (КИЗ) отправляет DELETE …/marking-codes/{код}: expected [] to have a length of 1 but got +0 |
| `frontend/src/screens/ff/unload-pick/FfUnloadPickPage.wms686.dom.test.tsx::c54 C54/R6б/D16 (подбор): короб → КИЗ без ШК — pick/scan с КИЗ и коробом без product_id, привязка к уже снятой единице без +1; неизвестный GTIN — «Сначала отсканируйте ШК товара»` | RED | AssertionError: код привязан к уже снятой единице — строка КИЗ под источником: expected null not to be null |
