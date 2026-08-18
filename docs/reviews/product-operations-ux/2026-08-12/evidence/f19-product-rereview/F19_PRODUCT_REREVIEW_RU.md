# F19 Product / UX Rereview: возврат со сканированием и автопечатью ШК

Дата: 2026-08-13
Роль: isolated Product / UX Review Agent
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`

## Verdict

`PRODUCT_APPROVED_FOR_DEV`

Повторный Product / UX gate пройден. F19 можно передавать в atomic dev только в
узком контракте ниже: автопечать является маленьким режимом возврата рядом со
сканером, срабатывает только после успешного скана товара и печатает только WB
ШК из `wb_barcode`.

Это не означает, что фича done: после dev всё ещё обязательны code review и
живой browser product QA по протоколу.

## Что было проверено

Прочитаны:

- `AGENTS.md`;
- `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`;
- `docs/reviews/product-operations-ux/2026-08-12/ITERATION_FEATURE_CARDS_RU.md`;
- `docs/reviews/product-operations-ux/2026-08-12/evidence/f19-ba-ux-rework/F19_BA_UX_REWORK_RU.md`;
- текущий экран приёмки `frontend/src/screens/ff/FfInboundRequestView.tsx`;
- текущие helper-файлы `frontend/src/screens/ff/inboundReceivingHelpers.ts`,
  `frontend/src/utils/inboundOperationType.ts`,
  `frontend/src/utils/printBarcodeLabel.ts`.

Код не редактировался.

## Product / UX вывод

BA/UX rework исправил исходную продуктовую проблему: режим больше не выглядит
как общий печатный механизм приёмки. Он привязан к реальной складской работе
возврата: оператор держит поток физических единиц, сканирует товар, видит рост
факта на `+1` и при включённом режиме получает WB-этикетку без отдельной
печатной формы.

Для сотрудника fulfillment это рабочий процесс, а не новый экран и не второй
мастер возвратов. Возврат остаётся вариантом приёмки, но получает маленькое
ускорение именно там, где оператор уже работает руками, — рядом со scan input.
Обычная приёмка не должна видеть этот switch вообще, поэтому основной экран не
разрастается для тех, кто не принимает возвраты.

## Проверка по матрице F19

Строка `+1` по ШК: принято. Главный action остаётся scan action, а не ручной
picker. Успешный `/receiving/scan` должен увеличить фактическое количество
строки на одну единицу.

Автопечать после каждого скана: принято только при включённом режиме и только
после успешного scan response. Печать не должна запускаться от ручного
`Добавить факт`, ручного создания товара, загрузки по накладной, коробов,
переходов статуса или перерендера экрана.

Маленький switch рядом со сканером только для возврата: принято. Switch должен
оставаться в scan panel, быть компактным, по умолчанию выключенным и полностью
скрытым на обычной приёмке, а не disabled.

Перегрузка приёмки/возврата: в утверждённом виде перегрузки нет. Добавляется
один операторский control без новых колонок, вкладок, чипов, бейджей,
технического текста и отдельного возвратного flow. Единственный UX-риск —
панель приёмки уже содержит несколько действий; поэтому dev не должен добавлять
к F19 новые кнопки, поясняющие подписи или отдельные статусы.

## Жёсткие constraints для dev

- Не создавать отдельный экран, вкладку или мастер возврата.
- Не менять обычную приёмку, сортировку, короба, ЧЗ-печать и печать накладной.
- Не добавлять новые колонки, чипы, бейджи или технические подсказки.
- Switch `Печатать ШК при скане` показывать только при `operation_type = return`.
- Switch держать рядом со scan input / scan button, компактным и выключенным по
  умолчанию при открытии документа.
- Auto-print trigger: только successful `scanToReceiving`.
- `applyPicker`, manual product creation и любые non-scan действия не печатают
  автоматически.
- Источник печати: только `line.wb_barcode?.trim()`.
- `sku_code` запрещён как fallback для WB-этикетки.
- Если `wb_barcode` отсутствует, факт скана остаётся, но печать fail-closed:
  показать понятное сообщение `У товара нет ШК WB для печати.` и ничего не
  печатать.
- Auto-print flow не открывает `MarkingPrintDialog`.

## Constraints для browser QA

Browser Product QA должен пройти реальный UI в браузере и проверить видимый
результат, а не только API или unit tests:

- обычная приёмка открывается как `Поставка`, и `ff-inbound-return-autoprint`
  отсутствует;
- возврат открывается как `Возврат`, switch виден рядом со сканером;
- включённый switch + успешный scan увеличивает строку на `+1`;
- captured print payload содержит WB barcode и не содержит SKU, если
  `sku_code !== wb_barcode`;
- manual picker при включённом switch не меняет print payload;
- manual product creation при включённом switch не меняет print payload;
- missing `wb_barcode` показывает понятную ошибку и не печатает SKU;
- `marking-print-dialog` не появляется в auto-print scan flow;
- на desktop и mobile/узком viewport нет overlap: scan panel может переносить
  controls на новую строку, но клики должны оставаться стабильными, а таблица
  приёмки не должна получить новые колонки или расползание длинных SKU/ШК.

## Gate State

- local: product rereview выполнен локально по документам и текущему UI-коду;
- committed: artifact должен быть сохранён отдельным commit; SHA фиксируется в
  финальном ответе агента;
- pushed: not checked;
- deployed: not checked;
- browser-tested: not by this Product / UX gate;
- remaining risks: после dev обязателен отдельный code review и живой browser
  product QA; текущий approval не является browser acceptance.
