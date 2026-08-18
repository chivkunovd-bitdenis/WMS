# Wave 2 Final Integration Live Acceptance

ORDER: 035

Экран / процесс: сквозной сценарий `приёмка → сортировка → упаковка → отгрузка`.

Стадия: final integration browser acceptance after Wave 2 merge.

Статус: `PRODUCT_BROWSER_APPROVED`.

Браузер: настоящий внешний видимый Google Chrome `151.0.7922.138`.
Управление: CDP mouse/key events в видимом окне ОС, не Playwright и не headless.
Использовались окна CDP `9240` и `9241`: первое окно дошло до системной печати, второе видимое окно завершило упаковку и отгрузку по сохраненному состоянию backend.

Стенд:
- frontend: `http://127.0.0.1:18831`
- backend: `http://127.0.0.1:18830`
- database: `/private/tmp/wms_final_integration_live_1786805850.sqlite`

Данные setup:
- admin: `final-live-1786805911640@example.com`
- seller: `Final Live Seller`
- warehouse: `Final Live WH`
- product: `Final Live Product`, SKU `FINAL-911640`, barcode `XINT-911640`
- inbound: `d477beed-9acc-4291-a3d5-9dea87508705`
- marketplace unload: `b820aba4-7349-446f-92f4-e7cf22939bf6`
- packaging task: `ff427df8-aacd-40b8-a10a-c318bd431175`

Проверенный путь:
- Внешний Chrome: вход под FF admin.
- Приёмка: открыт документ, начата приёмка, создан короб, принято `4/4`, документ переведен в статус `sorting`.
- Сортировка: открыт экран сортировки, строка принятого товара видна с остатком в зоне сортировки.
- MP-отгрузка: документ `№000001` открыт из таблицы, план `2`, распределено `0`, осталось `2`.
- Упаковка: создан короб через UI-кнопку, товар `XINT-911640` дважды отсканирован в видимом диалоге наполнения короба.
- Печать: товарные ШК зафиксированы как `напечатано 2/2`.
- Завершение упаковки: UI-кнопка `Завершить упаковку`, история содержит событие `Задание выполнено`.
- Отгрузка: UI-кнопка `Завершить`, таблица показывает статус `Отгружено`.

Итоговая backend-сверка:
- inbound `status=sorting`, `actual_qty=4`, `sorting_remaining_qty=4`
- MP unload `status=shipped`, line `quantity=2`, `picked_qty=2`, `has_discrepancy=false`
- MP box `WHB-241FD76D7CA8`, line `FINAL-911640`, `quantity=2`
- linked packaging task `status=done`, `qty_done=2`, `qty_total=2`, `is_complete=true`
- packaging task line: `qty_product_label_printed=2`, `qty_packed_in_task=2`, `is_complete=true`

Тесты:
- `backend/tests/test_packaging_tasks.py backend/tests/test_marketplace_unload_and_discrepancy_acts.py backend/tests/test_inventory_balances_summary.py`: `38 passed in 66.09s`
- `frontend npm run build`: passed; Vite chunk-size warning only
- Calendar acceptance branch before merge: `pytest tests/test_fbs_supply_from_orders.py::test_fbs_cutoff_autoplans_supply_manual_date_and_calendar` passed, `npm run build` passed

Кодовая правка, найденная финальным прогоном:
- Для MP-упаковки заменен legacy-текст предупреждения `Подбор по ячейкам изменился...` на `Состав коробов изменился...`.
- Файл: `frontend/src/screens/ff/FfPackagingPage.tsx`
- Причина: в MP/FBO UI не должен всплывать старый термин отдельного этапа подбора по ячейкам.

Скриншоты:
- `assets/wave2-final-01-reception-to-sorting.png`
- `assets/wave2-final-02-sorting-visible.png`
- `assets/wave2-final-05-mp-box-filled-dialog.png`
- `assets/wave2-final-07-print-dialog.png`
- `assets/wave2-final-10-before-complete-packaging.png`
- `assets/wave2-final-11-packaging-complete.png`
- `assets/wave2-final-12-shipped.png`
- `assets/wave2-final-13-shipped-row.png`

Диагностический скриншот, не acceptance-доказательство:
- `assets/wave2-final-08-print-dialog-diagnostic-wrong-qty.png`

Находки:
- Stop: 0
- Тормоз: 0
- Хвост: 1

Хвост:
- Во время диагностики после первого сбоя ожидания был создан пустой короб через browser-fetch. Финальная отгрузка ушла с одним коробом `WHB-241FD76D7CA8` и двумя единицами товара; итоговый API не содержит пустой короб в shipped-документе.

Раунд: 1.

Блокеры: нет.
