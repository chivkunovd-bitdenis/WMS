# Wave 2 MPFBO packaging acceptance

Экран: MP/FBO отгрузка и упаковка  
Задачи: MPFBO-01, MPFBO-02, MPFBO-03, MPFBO-04, MPFBO-05  
Стадия: продуктовая приемка в живом браузере  
Статус: принято  
Раунд: 1  
Commit: `0f81362`

## Браузер

Открывал настоящий внешний Google Chrome `151.0.7922.138`, видимое окно ОС, управление через Chrome DevTools Protocol на порту `9235`.

Связка стенда:

- frontend: `http://127.0.0.1:18731`
- backend: `http://127.0.0.1:18730`
- база приемки: `/private/tmp/wms_mpfbo_live_1786805520.sqlite`

Chrome в конце прогона: `MPFBO_ACCEPTANCE_DONE OK live Chrome 9235`, URL `http://127.0.0.1:18731/app/ff/mp-shipments`.

## Проверенный сценарий

Setup данных был выполнен API-запросами из того же браузерного origin, затем UI проходился кликами в видимом Chrome.

1. Через форму входа в Chrome выполнен login FF-админа.
2. Клик по меню `Отгрузки на МП`.
3. Клик по строке MP/FBO-отгрузки.
4. Проверена вкладка `Товары`: вкладки ровно `Товары` и `Упаковка`, без отдельного шага коробов.
5. Проверена сводка: план `2`, в коробах/распределено `2`, осталось `0`, упаковано `2/2`.
6. Клик `Далее: Упаковка`.
7. Проверена упаковка: строка товара, SKU, WB-штрихкод `2045526738950`, иконка ТЗ, ЧЗ `не требуется`, статус ШК печати, прогресс `2/2`, кнопка печати.
8. Проверено отсутствие ручного процесса `+N`: нет `ff-packaging-pack-btn` и нет `ff-packaging-manual-qty-*`.
9. В сканер введен WB-штрихкод, результат UI: `Строка найдена: MPFBO Живой товар`.
10. Клик по печати строки: открылся диалог `Печать ШК ВБ`, есть `marking-print-wb-qty`, нет `marking-print-preset-pairs`, нет `marking-print-preview`.
11. Раскрыт блок `Короба`: виден короб `60_40_40`, товар `MPFBO Живой товар`, количество `2`.
12. Клик `Завершить упаковку`: упаковочное задание стало `done`.
13. Клик `Завершить`: отгрузка стала `shipped`.

Контроль backend после финального клика:

- документ: `ОТГР-26-08-15-1`, `status = shipped`
- `picked_qty = 2` из `quantity = 2`
- короб: `WHB-49D87EE146B2`, строка товара `2`
- linked packaging task: `status = done`, `qty_done = 2`, `qty_total = 2`, `is_complete = true`

Отдельно перед распределением в короб проверен стоппер упаковки: `POST /operations/packaging-tasks/{id}/complete` вернул `422 {"detail":"packaging_incomplete"}`.

## 6a audit

- Раздел MP/FBO-отгрузок, строка документа, открытие карточки, переходы между `Товары` и `Упаковка`: MPFBO-01.
- Проверка доступного товара и блокировка завершения до корректного распределения: MPFBO-02, MPFBO-05.
- Сканер в упаковке как поиск строки, без самостоятельного ручного `+1/+N`: MPFBO-03.
- Компактная строка упаковки с SKU, ШК, ТЗ, ЧЗ, статусом ШК и печатью: MPFBO-04.
- Короба внутри вкладки `Упаковка` под раскрывающимся блоком, без отдельной вкладки/шага `Короба`: MPFBO-05.

Лишних видимых элементов без задачи на проверенном MPFBO-пути не найдено.

## Скриншоты

- `docs/agent-reports/2026-08-15/assets/wave2-mpfbo-01-products-tab.png`
- `docs/agent-reports/2026-08-15/assets/wave2-mpfbo-02-packaging-tab.png`
- `docs/agent-reports/2026-08-15/assets/wave2-mpfbo-03-print-dialog.png`
- `docs/agent-reports/2026-08-15/assets/wave2-mpfbo-04-boxes-open.png`
- `docs/agent-reports/2026-08-15/assets/wave2-mpfbo-05-shipped.png`

## Находки

Стоп: 0  
Тормоз: 0  
Хвост: 0

## Тесты

- `pytest backend/tests/test_packaging_tasks.py backend/tests/test_marketplace_unload_and_discrepancy_acts.py backend/tests/test_inventory_balances_summary.py -q -p no:cacheprovider`: `38 passed in 183.31s`
- `pytest backend/tests/test_packaging_tasks.py::test_packaging_blocks_mp_ship_until_done -q -p no:cacheprovider`: `1 passed in 6.49s`
- `ruff check backend/app/services/packaging_task_service.py`: `All checks passed!`

