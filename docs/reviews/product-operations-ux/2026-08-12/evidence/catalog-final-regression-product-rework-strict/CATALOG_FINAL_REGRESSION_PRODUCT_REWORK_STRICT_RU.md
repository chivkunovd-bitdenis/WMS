# CATALOG_FINAL_REGRESSION_PRODUCT_REWORK_STRICT_RU

Дата: 2026-08-14 MSK.

Роль: Catalog/F08-F11-F16-F22-F23 Live Product/UX Rework Spec Agent.

Repo: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.

HEAD: `d59959de70a8b9d447f200bdb703023c35b7b449`.

Verdict: `PRODUCT_REWORK_REQUIRED`.

Это не release-ready и не stage-ready verdict. Код, staging, production, Railway, secrets, commit и push не трогались.

## Browser Evidence

| Поле | Значение |
| --- | --- |
| browser_used | `yes` |
| browser | Chromium `headless=false` via Playwright |
| Browser plugin status | создание вкладки in-app browser было заблокировано в этом subagent thread; Chrome/extension/Edge backends были недоступны, поэтому использован живой локальный Chromium |
| viewport | `1280x720` |
| frontend | `http://127.0.0.1:15441/` |
| backend | `http://127.0.0.1:18441/` |
| route | `http://127.0.0.1:15441/seller/products` |
| DB | `/tmp/wms-catalog-rework-strict-20260814-1.sqlite` |
| seed evidence | `/tmp/wms-catalog-rework-strict-seed.json` |
| live evidence JSON | `/tmp/wms-catalog-rework-strict-live/live-playwright-evidence.json` |

Клики:

1. Открыл `/seller/products`.
2. Залогинился под seller и задал initial password.
3. Кликнул seller nav `Товары`.
4. Выбрал строку товара чекбоксом.
5. Кликнул `Изменить публикацию`.
6. Выбрал `Включить`.
7. Проверил confirmation dialog и отменил действие.
8. Кликнул row action `FBS` для распределения.
9. Создал FBS-направление `5 шт`.
10. Закрыл drawer распределения.
11. Кликнул сжатое row action `ТЗ`.

Screenshots:

- `/tmp/wms-catalog-rework-strict-live/01-seller-products-initial-1280.png`
- `/tmp/wms-catalog-rework-strict-live/02-selected-bulk-confirm-1280.png`
- `/tmp/wms-catalog-rework-strict-live/03-fbs-distribution-drawer-empty-1280.png`
- `/tmp/wms-catalog-rework-strict-live/04-fbs-direction-created-1280.png`
- `/tmp/wms-catalog-rework-strict-live/05-packaging-action-dialog-1280.png`

Фактические 1280 metrics:

- `documentScrollWidth=1280`, `bodyScrollWidth=1280`; page-level overflow is not the current blocker.
- Table width is `990px`; first row height is `91.5px`.
- Live headers: empty select column, `Товар`, `WB / ШК`, `Остаток`, `FBS-пул`, `Публикация WB`, `ТЗ / ЧЗ`, `Действия`.
- `Артикул WB` is absent from seller catalog body; `WB / ШК` is present.
- Before FBS direction, row showed stock as three naked numbers: `12 / 12 / 12`.
- After creating FBS direction `5 шт`, row showed `12 / 12 / 7`, `FBS 5 шт`, `резервы 0 шт`, `Проверяем WB`.
- Row action button `ТЗ` is `36px` wide inside a `59.4px` `Действия` column.
- FBS drawer itself is clearer than the table: it shows `FBS 5 шт`, `Резервы 0 шт`, `Свободный FBO 7 шт`.

## Product Conclusion

Экран функционально кликается, но всё ещё не проходит финальную продуктовую регрессию. Seller может открыть каталог, выбрать строку, открыть selected-only confirmation для публикации FBS, создать FBS-пул и открыть dialog ТЗ на упаковку. Этого недостаточно для product approval, потому что основная таблица всё ещё заставляет оператора расшифровывать сжатые складские данные.

Блокер не в горизонтальном overflow. Блокер в бизнес-читаемости на 1280px: `WB / ШК` прячет marketplace-смысл, колонка остатков складывает три числа без подписей в строке, FBS/FBO split по-настоящему читается только после открытия drawer, а отдельная колонка `Действия` тратит дефицитную ширину на одну кнопку `ТЗ`. Строка имеет высоту `91.5px`, выше прежнего compact-row target, но критические значения всё равно уходят в ellipsis.

## Minimal Rework Spec

Это минимальная доработка складской работы, не визуальный redesign. Каталог селлера остаётся одной таблицей с существующим selection flow, FBS drawer, F22 safe-sync rules и packaging dialog. Не добавлять декоративные chips, лишние cards, новые экраны или пояснительный developer text.

| UI element | Current live state | Required change | Product justification |
| --- | --- | --- | --- |
| Колонка `WB / ШК` | Header says `WB / ШК`; значение `424242` плюс barcode. | Переименовать header в `Артикул WB`. В ячейке WB article — primary line, barcode — secondary line с префиксом `ШК`, только если помещается; иначе barcode уходит в tooltip/details. | Seller и support говорят про артикул WB, а не про сокращённую техническую колонку. F16 acceptance требовал человеческое marketplace wording. |
| Колонка `Остаток` | Строка показывает `12`, `12`, `12` до FBS и `12`, `12`, `7` после FBS. | Оставить одну stock column, но подписать значения: primary `В ячейках 12`, secondary `На ФФ 12`, `Свободный FBO 7`. Никаких голых stacked numbers. | Пользователь должен знать, какое число можно использовать для FBO/MP planning, а какое является общим stock. Три голых числа — складская ловушка. |
| Колонка `FBS-пул` | Показывает `FBS 0 шт`, `резервы 0 шт` и маленькую кнопку `FBS`. | Оставить `FBS N шт` и `резервы N шт`; action переименовать в понятный compact control, например `Пул` или icon+tooltip `Настроить FBS-пул`. Drawer может остаться detailed source of truth. | Колонка уже называется FBS; вторая кнопка `FBS` не объясняет, что открывает настройки распределения. |
| Колонка `Публикация WB` | Short statuses работают: `Нет FBS`, `Проверяем WB`; switch compact. | Сохранить только короткие статусы: `Нет FBS`, `Пауза`, `Проверяем WB`, `WB: N шт`, `Ошибка WB`. Длинные причины и raw sync codes не показывать в строке; details — в drawer/popover. | F22 guardrail остаётся видимым, но таблица не превращается в error log. Unknown/missing FBS не должен выглядеть как safe zero или success. |
| Колонка `ТЗ / ЧЗ` | Показывает `Без ТЗ` и `ЧЗ нет`; отдельное action живёт в `Действия`. | Перенести edit action `ТЗ` в эту колонку как compact icon или fixed-width `ТЗ` button под статусом. | `ТЗ / ЧЗ` уже владеет смыслом packaging instruction state. Отдельная action column тратит ширину и выглядит clipped. |
| Колонка `Действия` | Header `Действия`; единственное visible row action — `ТЗ`, ширина `36px`. | Удалить колонку, если других row actions нет. Если колонка остаётся, в ней должно быть больше одного реального row action, и header/controls не должны клипаться на 1280px. | One-button action column не стоит своей ширины. Освободившаяся ширина нужна WB article и stock readability. |
| Верхние действия | Две большие bordered panels перед таблицей: API sync и FBS publication summary. | Не redesign страницы, но FBS selection toolbar должен быть достаточно compact, чтобы таблица начиналась выше и оставалась primary work surface. `Изменить публикацию` по-прежнему появляется только после selection. | Оператор пришёл читать и менять строки; toolbar не должен доминировать первый viewport. |
| Row geometry | Row height `91.5px`; long product/SKU values ellipsized, хотя строка всё равно высокая. | Target `64-72px` row height at 1280px с long name/SKU/barcode. Использовать fixed column widths, ellipsis и details/tooltip для overflow. | Текущая строка высокая и всё равно ambiguous; compactness должна улучшить clarity, а не прятать данные. |

## Что Оставить

- Selected-only bulk flow продуктово корректен: нет глобальных `Включить всем` / `Выключить всем`; confirmation говорит, что меняются только выбранные товары.
- FBS drawer подходит как detailed read-back: он ясно показывает `FBS`, `Резервы` и `Свободный FBO`.
- `Лимит` is not visible in the main table.
- Raw technical sync statuses не были видны в live row.
- Page-level horizontal overflow в этом прогоне не воспроизвёлся.

## Acceptance For Code Review

Code review обязан отклонить реализацию, если выполняется хотя бы одно:

- Seller `/seller/products` still contains header `WB / ШК` instead of `Артикул WB`.
- The stock cell still renders naked stacked numbers without row-level labels.
- The only row action remains isolated in a separate `Действия` column as `ТЗ`.
- The FBS pool action remains an unexplained duplicate `FBS` button with no clear affordance.
- Missing/unknown FBS availability can be published as `0` or shown as success.
- Regular states become chip noise or technical enum text.
- The layout fix relies only on hidden overflow while controls or headers are visually clipped.
- Long SKU/barcode/name pushes row height above `72px` at 1280px.
- Existing selected-only FBS bulk behavior regresses to all-products mutation or `product_ids: null`.

Обязательное code-review evidence:

- DOM/header assertion for `Артикул WB` on seller products.
- DOM/text assertion that stock values include labels `В ячейках`, `На ФФ`, and `Свободный FBO`.
- Assertion that no separate one-button `Действия` column remains, or that it has a justified non-clipped action set.
- Layout metric assertion at 1280px: `document.documentElement.scrollWidth <= window.innerWidth`, row height `<=72`, row action visible and clickable.
- F22 safe-sync regression proving no fallback publish `0` for missing FBS pool.

## Acceptance For Live Browser QA

Browser QA обязан использовать реальный browser и не имеет права approve по code/tests only.

Mandatory path:

1. Open `/seller/products` at `1280x720`.
2. Capture screenshot and DOM metrics for table headers, row height, document/body scroll width, and action button bounds.
3. Verify header `Артикул WB` is visible and `WB / ШК` is absent.
4. Verify stock cell reads as labeled business data, not `12 / 12 / 7`.
5. Select one row, open `Изменить публикацию`, choose `Включить`, and verify confirmation remains selected-only.
6. Open FBS pool control, create an FBS direction, and verify the main row and drawer both show FBS/FBO split clearly.
7. Open packaging instruction action from the `ТЗ / ЧЗ` area and verify it is still reachable without a separate clipped action column.
8. Verify no page-level horizontal overflow, no black strip, no clipped headers/actions, and row height `<=72px`.
9. Verify `Нет FBS`, `Проверяем WB`, and `WB: N шт` remain short row statuses; long reasons are in details only.
10. Verify F22 incident path: missing FBS pool does not send `0` to WB and does not display success.

Required QA verdict после rework:

- `BROWSER_PRODUCT_QA_PASSED` only if all mandatory checks pass in live browser.
- `BROWSER_PRODUCT_QA_FAILED` if the UI opens but any product/UX acceptance above fails.
- `BROWSER_PRODUCT_QA_BLOCKED` if the app, auth, route, fixture, or browser cannot run.

Final product verdict for this run: `PRODUCT_REWORK_REQUIRED`.
