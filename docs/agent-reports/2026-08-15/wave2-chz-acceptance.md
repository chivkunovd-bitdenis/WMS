# ORDER 038 — live acceptance artifact по экрану «Честный знак» CZ-01..CZ-04

Дата: 2026-08-15 16:45 MSK.
Worktree: `/Users/deniscivkunov/Projects/WMS/.worktrees/integration-wave0-20260814`.
Ветка: `integration/wms-wave0-20260814`.

## Экран

Честный знак: карточка товара, лента расхода КМ, печать КМ из каталога и брак КМ из задания упаковки.

## Стадия

Post-merge product acceptance. Код экрана уже был влит в `integration/wms-wave0-20260814`; эта стадия закрывает найденную дыру в доказательствах живой приёмки.

## Статус

`PRODUCT_BROWSER_APPROVED`.

Прогон выполнен в настоящем внешнем видимом Google Chrome. Playwright/headless не использовались как приёмка. Backend API использовался только для подготовки данных и readback-проверки фактических статусов.

## Commit

Implementation до этого acceptance artifact: `d8ef8d11469fdc9462db691bb8a49b67927cd633` в `integration/wms-wave0-20260814`.

Artifact-only commit с этим отчётом и скриншотами фиксируется после сохранения файла и будет указан в финальном отчёте.

## Тесты реальные цифры

- Полный backend gate на текущей integration до artifact-only commit: `763 passed, 5 skipped, 6 warnings in 638.77s`.
- Дополнительно для live acceptance сделан backend readback после UI-действий:
  - продуктовые КМ: `printed=2`, `defective=1`, `available=9`;
  - лента `event_type=defective`: `total=1`;
  - очередь перепечатки: `1 pending` заявка по `…9512LIVE0002`.
- Targeted backend по ЧЗ после оформления артефакта: `17 passed in 15.47s`.

## Браузер

Браузер: внешний Google Chrome `Chrome/151.0.7922.138`, видимое окно OS.

Способ управления: Chrome DevTools Protocol на `127.0.0.1:9245`, реальные mouse/key events в видимую вкладку Chrome. Это не Playwright и не headless.

Сервисы live-прогона:
- Backend: `http://127.0.0.1:18950`.
- Frontend: `http://127.0.0.1:18951`.

Seed:
- user: `chz-live-1786811199512@example.com`;
- seller: `Live ChZ Seller`;
- product: `Live ChZ Product`, SKU `CHZ-LIVE-1786811199512`;
- pool: `Live ChZ Pool`, GTIN `04601234567890`;
- packaging task: `8e5ff606-a9c6-49f5-af9a-5b5ced2fcaab`.

## Проверка CZ-01..CZ-04

CZ-01:
- В каталоге выбран seller и товар с ЧЗ.
- Живым кликом открыта печать КМ из строки товара.
- Подтверждение печати открыло системный Chrome print preview.
- Backend readback показал расход ровно одного КМ: `…LIVE0001` перешёл в `printed`.
- Лента содержит полный `010460123456789021199512LIVE0001`, actor `chz-live-1786811199512@example.com`, source `Каталог`.

CZ-02:
- В карточке товара одновременно видны блоки `Коды` и `Лента`.
- В `Коды` видны КМ/CIS и статус.
- В `Лента` видны полный CIS, сотрудник, источник, время и документ.

CZ-03:
- В карточке товара отсутствует `ff-honest-sign-product-ledger-open-full`.
- Лента товара открыта прямо внутри карточки; фильтр printed показал напечатанный КМ.

CZ-04:
- В живом Chrome создано задание упаковки из сортировки.
- Из задания упаковки живым кликом напечатаны 2 КМ: `…LIVE0002` и `…LIVE0003`.
- Через меню строки открыт пункт `Брак`, выбран напечатанный `…LIVE0002`, заполнена причина `Порвана этикетка при live acceptance`, подтверждён брак.
- Backend readback показал статус `defective` у `010460123456789021199512LIVE0002`.
- Лента с фильтром `Брак` показывает полный CIS, документ `УПАК-26-08-15-1`, источник `Упаковка/FBS-печать`, пользователя.
- Очередь перепечатки показывает pending-заявку с той же причиной, документом и ссылками на задание/пул/историю.

## Скриншоты

- `assets/wave2-chz-live-00-os-visible-chrome.png` — видимое OS-окно Chrome.
- `assets/wave2-chz-live-01-page-open.png` — экран ЧЗ открыт.
- `assets/wave2-chz-live-02-seller-selected-product-row.png` — выбран seller, видна строка товара.
- `assets/wave2-chz-live-03-print-dialog.png` — диалог печати из строки товара.
- `assets/wave2-chz-live-04-after-print-row-updated.png` — строка после печати.
- `assets/wave2-chz-live-05-product-card-codes-and-ledger.png` — карточка товара: коды и лента одновременно.
- `assets/wave2-chz-live-06-product-card-printed-filter.png` — фильтр printed в карточке товара.
- `assets/wave2-chz-live-07-defective-ledger-filter.png` — лента с фильтром `Брак` до live defect.
- `assets/wave2-chz-live-08-pool-card-after-print.png` — карточка пула после печати и брака.
- `assets/wave2-chz-live-09-packaging-page.png` — экран упаковки.
- `assets/wave2-chz-live-10-packaging-create-dialog.png` — создание задания.
- `assets/wave2-chz-live-11-packaging-create-row.png` — выбор строки задания.
- `assets/wave2-chz-live-12-packaging-task-created.png` — задание создано.
- `assets/wave2-chz-live-13-packaging-print-dialog.png` — печать КМ из упаковки.
- `assets/wave2-chz-live-14-defect-menu.png` — меню строки с пунктом `Брак`.
- `assets/wave2-chz-live-15-defect-dialog.png` — диалог брака КМ.
- `assets/wave2-chz-live-16-defect-confirm-ready.png` — причина брака заполнена.
- `assets/wave2-chz-live-17-defect-confirmed.png` — диалог закрыт после подтверждения.
- `assets/wave2-chz-live-18-reprints-row.png` — pending-заявка на перепечать.
- `assets/wave2-chz-live-19-defective-ledger-after-defect.png` — лента после брака.
- `assets/wave2-chz-live-evidence.json` — машинный readback по браузеру/API.

## Находки Стоп-Тормоз-Хвост

Стоп: 0.

Тормоз: 0.

Хвост:
- 1: live acceptance выполнен на локальном стенде с sqlite и mock-данными, без внешнего кабинета Честного знака.

## Раунд

Раунд: post-merge acceptance, round 1.

## Блокеры

Нет блокеров для `PRODUCT_BROWSER_APPROVED` по CZ-01..CZ-04.

## 6а mapping по видимым элементам CZ-01..CZ-04

| Видимый элемент / поведение | ID задачи | Подтверждение |
|---|---:|---|
| Печать КМ из строки товара в каталоге | CZ-01 | `wave2-chz-live-03-print-dialog.png`, readback `…LIVE0001=printed` |
| Лента показывает полный CIS, сотрудника, источник, время | CZ-01 | `wave2-chz-live-05-product-card-codes-and-ledger.png`, `wave2-chz-live-evidence.json` |
| Коды и лента одновременно в карточке товара | CZ-02 | `wave2-chz-live-05-product-card-codes-and-ledger.png` |
| Статусы КМ в карточке товара и пуле | CZ-02 | `wave2-chz-live-06-product-card-printed-filter.png`, `wave2-chz-live-08-pool-card-after-print.png` |
| Нет отдельной кнопки `Вся лента товара` из карточки | CZ-03 | DOM/readback: `ff-honest-sign-product-ledger-open-full` отсутствует |
| Брак КМ из упаковки | CZ-04 | `wave2-chz-live-14-defect-menu.png` .. `wave2-chz-live-17-defect-confirmed.png` |
| Очередь перепечатки после брака | CZ-04 | `wave2-chz-live-18-reprints-row.png` |
| Лента `Брак` с полным CIS/документом/источником/пользователем | CZ-04 | `wave2-chz-live-19-defective-ledger-after-defect.png` |

## Примечания

UI и бизнес-код в этой стадии не менялись. Убрана прежняя формулировка `PRODUCT_BROWSER_BLOCKED`, потому что live external Chrome-прогон по ЧЗ теперь выполнен и зафиксирован.
