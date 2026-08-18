# Final Integration Review WMS-итерации 2026-08-12

Статус: passed для WMS-фичей F01-F19; F20 оставлен за рамками по требованию пользователя; F21 заблокирован отсутствием исходников/deploy target sellerfocus.pro в текущем WMS checkout.

Ветка: `iteration/wms-product-ux-features-20260812`.
Базовый SHA до этой волны: `56c8a67b99a063a77736c7bdcc52e51019a35b1b`.

## Проверка общей UX-целостности

Вердикт: passed.

Фичи не выглядят как набор несвязанных экранов:

- Приемка, возврат, добавление фактических строк, габариты, печать и карточка селлера остались в одной логике документа приемки.
- Отдельный процесс "Упаковка" в приемке не появился; коробочный учет используется только как способ посчитать факт.
- MP/FBO-отгрузка приведена к понятной пошаговой схеме, но FBS-специфика не скопирована: нет QR каждого FBS-заказа в FBO-документе.
- Резервы, FBS-пул и свободный FBO-остаток используют один словарь сущностей: "Распределение", "FBS-пул", "Свободно FBO", "Резерв/набор".
- `nmID` не выкинут как данные, но в UI назван по-русски как "Артикул WB".
- Управление сотрудниками селлера и ФФ использует роль/права, а не отдельные хаотичные экраны.
- Удаление ограничено черновиками, чтобы не ломать историю и остатки.

## Проверка на визуальный мусор

Вердикт: passed с одним низким остаточным риском.

Не обнаружены release-blocking признаки Frankenstein-UI:

- нет новых технических подсказок для разработчиков в пользовательском UI;
- нет отдельной упаковочной вкладки в приемке;
- нет дублирования главных кнопок в новых сценариях;
- направления товара вынесены из широкой таблицы в right Drawer, поэтому seller stock экран не перегружен;
- в FBS-sync тексте явно сказано, что WB получает только выделенный FBS-пул;
- печатные документы компактны и ориентированы на складскую работу.

Остаточный риск: в Playwright-логе есть предупреждение MUI про `Tooltip` вокруг disabled-кнопки в MP/FBO экране. Это не сломало сценарий и не является release-blocker, но стоит убрать отдельной косметической правкой.

## Конфликты между фичами

Вердикт: passed.

Проверенные потенциальные конфликты:

- F03/F04/F05/F06/F18/F19 трогают приемку. Они согласованы вокруг одной карточки: факт, расхождения, возврат, печать и ручной товар не создают отдельные конкурирующие процессы.
- F08/F09/F10/F12/F16 трогают остатки и каталог. Они согласованы вокруг stock directions: общий остаток, FBS-пул, резервы и свободный FBO-остаток считаются из одной модели.
- F13/F14 трогают доступы. Seller shop switching и staff permissions не расширяют видимость чужих товаров.
- F07/F17 трогают MP/FBO-отгрузку и печать. Новый пошаговый путь и единый печатный документ не тянут FBS order QR в FBO.

## Финальный browser regression

Команда:

```bash
cd /Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/frontend
npx playwright test tests-e2e/inbound-receiving-v2.spec.ts tests-e2e/ff-inbound-barcode-add.spec.ts tests-e2e/ff-inbound-print-waybill.spec.ts tests-e2e/ff-products.spec.ts tests-e2e/seller-cabinet.spec.ts tests-e2e/ff-staff-users.spec.ts tests-e2e/seller-staff-and-delete-drafts.spec.ts tests-e2e/seller-stock-directions.spec.ts tests-e2e/ff-mp-tabs.spec.ts tests-e2e/ff-mp-shipment-tz-print.spec.ts tests-e2e/ff-mp-print-waybill.spec.ts
```

Результат: 24 passed.

Покрытые реальные UI-процессы:

- приемка без отдельной вкладки "Упаковка";
- сканирование, ручная правка и завершение приемки с расхождением;
- приемка возврата с товаром из каталога селлера;
- ввод габаритов из карточки приемки;
- автопечать ШК при скане возврата;
- аварийное создание ручного товара из приемки;
- печать накладной приемки;
- фильтрация каталога ФФ;
- staff flow ФФ;
- staff flow селлера и удаление только черновиков;
- seller shop manager без видимости чужих товаров;
- направления остатка, FBS-пул, резервы и свободный FBO;
- MP/FBO пошаговый экран и компактная печать без FBS order QR.

## Backend и сборка

Результат: passed.

Проверки:

- `python3 -m pytest` в `backend/` -> 652 passed, 5 skipped.
- `python3 -m pytest backend/tests/test_fbs_stock_availability.py backend/tests/test_stock_directions.py backend/tests/test_catalog.py::test_catalog_flow backend/tests/test_inbound_intake.py::test_inbound_receiving_accepts_seller_catalog_product_as_discrepancy backend/tests/test_seller_staff_and_delete_drafts.py backend/tests/test_staff_users.py backend/tests/test_seller_shop_scope.py backend/tests/test_seller_shop_switch.py` -> 18 passed.
- `python3 -m ruff check .` в `backend/` -> passed.
- `python3 -m mypy .` в `backend/` -> passed.
- `python3 -m compileall -q app` в `backend/` -> passed.
- `python3 -m alembic heads` в `backend/` -> `20260812_0079 (head)`.
- `npm run build` в `frontend/` -> passed.
- `npm run test:unit` в `frontend/` -> 115 passed.

## Release gate

Passed для WMS-части при условиях:

- закоммитить итоговый diff в ветку итерации;
- запушить ветку;
- staging Railway обновлять только через staging branch;
- не трогать secrets, Railway variables и production.

F21 не входит в release gate текущей WMS-ветки, потому что правильный source/deploy target sellerfocus.pro не найден в этом checkout.
