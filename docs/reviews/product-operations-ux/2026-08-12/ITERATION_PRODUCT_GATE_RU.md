# Product Gate WMS-итерации 2026-08-12

Роль: изолированный WB/Fulfillment Product Gate Agent.
Режим: read-only review, без коммитов, деплоя, секретов и Railway variables.

Критерий: экран должен быть понятен обычному сотруднику fulfillment/Wildberries/FBS без объяснений. Лишние чипы, технические подписи, дублирующие кнопки, лишние колонки и перегруженные таблицы являются причиной отказа.

## Первичный gate

| Фича | Verdict | Причина |
|---|---|---|
| F01 | needs_browser_evidence | Отдельной вкладки "Упаковка" в приемке не видно, но нужно глазами проверить, что короба не выглядят как новый упаковочный процесс. |
| F02 | needs_browser_evidence | Кнопка габаритов продуктово верная, но новая колонка требует визуальной проверки плотной таблицы. |
| F03 | needs_browser_evidence | Пересорт в одной таблице правильный, но нужен браузерный проход по план 0, факт больше 0, красная строка, "Добавлено ФФ". |
| F04 | needs_browser_evidence | Маленький плюс подходит как аварийный путь, но нужно проверить, что он не становится главным сценарием. |
| F05 | rejected | Селлерская карточка не показывала полноценный факт, "Добавлено ФФ", недостачи, излишки и пересорт. |
| F06 | needs_browser_evidence | Нужна проверка печати после проведения с фактом и расхождениями. |
| F07 | approved | Верное решение: вести MP/FBO к FBS-like шагам, но не копировать FBS-специфику. |
| F08 | rejected | Направления внутри широкой таблицы перегружали seller stock экран. |
| F09 | needs_browser_evidence | Формула верная, но нужно проверить, что пользователь не путает общий остаток, свободный FBO и FBS-пул. |
| F10 | rejected | Текст создавал ожидание, что в WB уходит весь остаток фулфилмента, а не только FBS-пул. |
| F11 | needs_browser_evidence | FF-каталог нужно смотреть в браузере на предмет новых микроподписей. |
| F12 | approved | Backend snapshot с разбивкой общий/FBS/резервы/свободный FBO продуктово ок. |
| F13 | needs_browser_evidence | Нужен browser/login сценарий доступа к разрешенным и чужим селлерам. |
| F14 | rejected | Требование включает сотрудников селлера и ФФ; на первом gate не было evidence по FF-сотрудникам. |
| F15 | needs_browser_evidence | Нужно браузером проверить, что удаление доступно только у черновиков. |
| F16 | rejected | В seller stock оставалось техническое название `nm`. |
| F17 | approved | Единый печатный лист продуктово правильный, без FBS order QR. |
| F18 | needs_browser_evidence | Возврат как тип приемки верен, нужен проход через UI. |
| F19 | needs_browser_evidence | Автопечать после скана требует browser/printer-flow evidence. |

## Вердикт по F07

Не оставлять старый MP/FBO процесс "как был". Делать гибридную пошаговую схему: план -> подбор -> ЧЗ/подготовка -> короба -> печать/финал. Не переносить QR каждого FBS-заказа и другую FBS-специфику. Сохранять возможность отката старой упаковочной логики.

## Повторный gate после доработок

| Фича | Verdict | Evidence |
|---|---|---|
| F05 | approved | Селлерская карточка в недraft-статусах показывает заявлено, факт, расхождение и "Добавлено ФФ". Browser e2e проверяет путь ФФ -> селлер. |
| F08 | approved | Направления вынесены из таблицы в right Drawer, таблица стала компактнее. Browser e2e проверяет создание направлений и распределение. |
| F10 | approved | Текст FBS-sync говорит, что WB получает только FBS-пул; нулевой FBS-пул явно показывает, что в WB уйдет 0 шт. |
| F14 | approved | Есть FF staff API/UI и seller staff API/UI. Browser e2e прошел по обеим сторонам. |
| F16 | approved | В целевых каталогах используется русское название "Артикул WB"; `nm` как заголовок убран. |

## Browser evidence на момент gate

- `npx playwright test tests-e2e/inbound-receiving-v2.spec.ts tests-e2e/ff-staff-users.spec.ts tests-e2e/seller-staff-and-delete-drafts.spec.ts tests-e2e/seller-stock-directions.spec.ts` -> 8 passed.
- `npx playwright test tests-e2e/ff-inbound-barcode-add.spec.ts` -> 2 passed.
- `npx playwright test tests-e2e/seller-cabinet.spec.ts` -> 2 passed.
- `npx playwright test tests-e2e/ff-inbound-print-waybill.spec.ts tests-e2e/ff-products.spec.ts tests-e2e/ff-mp-tabs.spec.ts tests-e2e/ff-mp-shipment-tz-print.spec.ts tests-e2e/ff-mp-print-waybill.spec.ts` -> 12 passed.
- `npx playwright test tests-e2e/inbound-receiving-v2.spec.ts` after F01/F19 strengthening -> 5 passed.
- `npm run build` -> passed.
- Backend targeted: catalog, inbound discrepancy, stock directions, seller staff/delete drafts, staff users -> 8 passed.

## Остаточный release gate

Этот product gate не заменяет общий final browser regression всей итерации. Перед staging/deploy обязательны общий integration review, общий browser regression и итоговый commit SHA.

## Финальный gate после общего browser regression

Вердикт: passed для WMS-фичей F01-F19.

Финальный браузерный прогон:

```bash
cd /Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/frontend
npx playwright test tests-e2e/inbound-receiving-v2.spec.ts tests-e2e/ff-inbound-barcode-add.spec.ts tests-e2e/ff-inbound-print-waybill.spec.ts tests-e2e/ff-products.spec.ts tests-e2e/seller-cabinet.spec.ts tests-e2e/ff-staff-users.spec.ts tests-e2e/seller-staff-and-delete-drafts.spec.ts tests-e2e/seller-stock-directions.spec.ts tests-e2e/ff-mp-tabs.spec.ts tests-e2e/ff-mp-shipment-tz-print.spec.ts tests-e2e/ff-mp-print-waybill.spec.ts
```

Результат: 24 passed.

Продуктовый вывод: фичи не конфликтуют между собой и не перегружают ключевые WMS-экраны. Приёмка остаётся приемкой, MP/FBO-отгрузка стала пошаговой без FBS-специфики, распределение остатка вынесено в отдельное компактное управление, FBS-sync явно работает от FBS-пула. F21 не утверждается в этой ветке, потому что исходники sellerfocus.pro не найдены в текущем WMS checkout.
