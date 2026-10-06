# WMS-680: инвентаризация печати и источников варианта · 06.10.2026

Исследователь: независимый аналитик-замена после ENOSPC (закончился диск у прежнего вызова).
Каталог: `/Users/deniscivkunov/Projects/WMS/.worktrees/night1007-679-680`.
Ветка: `codex/night1007-679-680`. Проверенная база:
`4b298efc95be7b4b6b7fe5665be9f3671f1fe747` = HEAD = обновлённый origin/etalon.
`git fetch origin etalon` выполнен; `git show origin/etalon:AGENTS.md` прочитан.
Документ подготовки взят из `3f8275d5133cd30fddcd712f41cabea7d377e4b0` и сохранён в начале
`docs/requirements/WMS-680.md`. Бэклог и чужие материалы не менялись. Git index не менялся.

Это чтение исходников и путей экрана, не подтверждение отображения в браузере, PDF или бумаги.

## Как устанавливался охват

Поиск `rg` выполнен по frontend/src, backend/app и затем по всему checkout для
`printWaybill`, `printShipmentWaybill`, его трёх обёрток, «накладн», builders/print методов
в utils и `window.print` / `.print(` / `printPdfBlob` в экранах. Тесты и служебные материалы
не считались продуктовыми входами. Функции с точным именем `printWaybill` нет; есть
`printShipmentWaybill` и две отдельные формы приёмки/упаковки. Поиск только точного имени
потерял бы оба реально действующих основных входа.

## Действующие формы и вызывающие места

| Форма | Источник и вызывающее место на базе | Фактический разрыв |
|---|---|---|
| Лист приёмки | `frontend/src/screens/ff/FfInboundRequestView.tsx:2551–2579`, `printInboundReceivingSheet.ts:3–54,56–175` | `InboundReceivingSheetItem` не содержит размер/цвет; map передаёт только название/артикулы/фото/ШК/expected_qty. `meta` уже содержит wb_size/wb_color при успешном каталоге |
| Лист отгрузки FBO | `frontend/src/screens/ff/FfPackagingPage.tsx:407–433,902–917`, `printShipmentPackagingSheet.ts:3–63,66–195` | `PackagingSheetItem` и map теряют оба поля displayMeta. Кнопка показана только `isMpUnloadTask` — задание отгрузки на маркетплейс; обычная несвязанная упаковка не получает новую кнопку |
| Накладная со склада | `frontend/src/screens/v2/OutboundScreen.tsx:21–42,212–257`, `printShipmentWaybill.ts:1–30,89–225` | В строке ответа/типа/map нет размера/цвета; общего каталога этот экран при печати не использует |
| FBS одиночный лист | `FfFbsSupplyWorkspace.tsx:2758–2801,4943–4944,4986–4987`; `fbsUx.ts:294–304,354–410,474–572` | В `FbsPickingListPrintRow` нет color; WB передаёт size, Ozon в `fbsBuildPickingRows` явно ставит `size: null` несмотря на поле позиции |
| FBS групповая сборка | `FfFbsSupplyAssembly.tsx:260–313,348–352`; `fbsSupplyAssembly.ts:320–390` | Используется та же HTML-функция; size WB/позиции Ozon передаётся, color не передаётся |
| Общая форма трёх видов | `printShipmentWaybill.ts:267–297` | Операционная обёртка имеет действующий вызов. Для marketplace_unload и inbound_intake прямых UI-вызовов не найдено; внутренние вызовы обёрток идут в общую форму. Поддержка полей должна быть общей, новых кнопок не требуется |

Маршруты подтверждены в `frontend/src/App.tsx`: outer `/app/*`; относительные
`ff/reception`, `ff/sorting`, `ff/mp-shipments`, `ff/packaging`, `ff/packaging/:taskId`,
`ff/fbs`, `ops/outbound`. Приёмка открывается через `openInboundDocument` в общий диалог
`FfInboundRequestView` (3818). Документ отгрузки со склада может открываться из dashboard
через `onOpenOutbound` (3051) в тот же `OutboundScreen`. Старые `ff/inbound` и
`ff/supplies-shipments` направляют в reception, `ff/outbound` — в ops/outbound.
Не использовать несуществующий `/app/ff/supplies` как доказательство экранного покрытия.

FBO-вход в `FfSuppliesShipmentsPage.tsx:1772–1801,2801–2827`: by-unload грузит PackagingTask,
вкладка «Упаковка» рендерит `FfPackagingTaskPanel`, тот печатает `printShipmentPackagingSheet`.
Самостоятельный `FfPackagingPage` использует ту же панель. Поиск только
`printMarketplaceUnloadWaybill` не покрывает FBO.

## Ответы сервера и локальные источники

| Путь данных | Проверенный код | Наблюдение |
|---|---|---|
| Документ приёмки | `backend/app/api/inbound_intake.py:309–333,632–666`; GET detail | `InboundIntakeLineOut` / `_line_out_from_orm` несут product_id, название, ШК, размеры габаритов, количества; размера варианта и цвета нет. Габариты length_mm и т.д. не являются размером одежды |
| Задание упаковки | `backend/app/api/packaging_tasks.py:87–112,151–185,220–280,419–456` | Обе выдачи по task ID/by-unload используют `_task_out`/`_line_out`; оба поля отсутствуют. Product уже доступен на строке |
| Отгрузка со склада | `backend/app/api/outbound_shipment.py:51–62,98–135,283–305` | В `OutboundShipmentLineOut` / `_line_out` оба поля отсутствуют; Product есть. Нужно передавать существующие характеристики на серверной границе |
| Строки документа FBO | `backend/app/api/marketplace_unload_requests.py:195–204,453–470` | Полей нет, но эти строки сейчас не являются источником действующей накладной: она идёт через packaging. Не расширять несвязанный ответ только ради симметрии |
| Общий каталог | `backend/app/api/products.py:169–197,838–850`; `seller_wb_catalog_service.py:125–168,439–534` | `linked-wb-catalog` отдаёт wb_size/wb_color. Строка каталога по Product.id, локальная WB-карточка по tenant+seller+nmID. Цвет вычисляется из raw_json, отдельной колонки Product.wb_color нет |
| Привязка каталога интерфейса | `frontend/src/types/wbProductCatalog.ts:49–90`; `hooks/useWbProductCatalog.ts` | При успешной загрузке оба поля доступны; без строки каталога обе характеристики становятся null. Кэш только product_id; нельзя допустить, чтобы он уничтожил характеристики, пришедшие в строке документа |
| FBS ответы | `frontend/src/screens/v2/fbsApi.ts:214–258`; `backend/app/services/fbs_worklist_service.py:1015–1040,1067–1074,1157–1160` | У product заказа есть size/color, у отдельных positions тоже; `_product_label_metadata` берёт характеристики точного WMS-product. Ozon должен использовать positions, WB — product. Одиночный frontend теряет Ozon size |

`Product` (`backend/app/models/product.py:60–79`) хранит tenant_id, seller_id, wb_nm_id,
wb_chrt_id, wb_barcode, wb_size. Один Product соответствует конкретному варианту:
`wildberries_product_import_service.py:303–399` создаёт/обновляет Product по chrtID;
`wildberries_product_link_service.py:158–160` сохраняет выбранный вариант и size_label.

`_size_for_product`: непустой Product.wb_size → иначе собственный barcode в карточке.
`size_from_card_for_barcode` (`wb_card_enrichment.py:255–274`) ищет размер с этим ШК; без
совпадения многовариантная карточка даёт None. Единственный размер допускается существующим
правилом. `color_from_card` (197–203) читает характеристику «Цвет» или известный ID цвета;
массив значений объединяется существующим парсером, не выбирается случайный соседний цвет.

Ozon raw/link сейчас даёт привязки/ШК/фото; общего импорта размера/цвета в печать в этой
задаче не добавляем. Существующая общая WMS-карточка может иметь wb_size и свои локальные
WB-характеристики даже при печати Ozon. Они относятся к этому Product; отсутствующие поля
печатаются прочерком. Не считать WB/Ozon-принадлежность разрешением подменять Product.

## Другие печатные формы: почему не являются накладной этой задачи

- `FfStoragePage`: кнопка PrintAction what="накладную" фактически показывает и печатает
  «Расчёт хранения» с литро-днями, ставкой, суммой и итогом. Товарная накладная приёмки/отгрузки
  из неё не получается. Это финансовый отчёт; подпись не расширяет WMS-680 на тарифные формы.
- `FfBillingInvoiceCreate`, `FfBillingInvoicesPanel`, invoice-print-preview: счета за услуги.
- `inventory/printInventorySheet`, `printContainerContents`: инвентаризация/содержимое тары.
- `printOzonReturnReconciliation`: сверка возвратов; `printPackagingInstructions`: отдельное ТЗ.
- QR, КИЗ, товарные/коробные/заказные стикеры и `printPdfBlob`: этикетки/печатные артефакты.
- `FfFbsPickList` используется только preview (`fbs-pick-list-preview.tsx`), его printImages
  печатает стикеры, а не товарный лист. Старый GET FBS picking-list не источник действующего
  общего HTML-листа и не требует нового маршрута печати.
- `BoxImportDialog` «Загрузить по накладной»: импорт, не печать.
- `backend/app/schemas/ozon_fbs_api.py` waybill: описания внешнего API, действующего вызова
  скачивания/печати накладной Ozon в checkout поиск не выявил.
- Акт приёмки, acceptance-act.xlsx и печать стикеров в `FfInboundRequestView` оставлены соседним
  WMS-684/586. Макет686 не читался как основание переноса дизайна.

## Риски и граница доказательств

Нужна проверка всех трёх ответов на фактической локальной сериализации, а не добавление типов
без данных. Особые риски: первый размер карточки; одинаковый nmID другого селлера; данные
корневого товара вместо позиции Ozon; второй вход в общую панель; отсутствие каталога;
размер габаритов вместо размера варианта; общий помощник влияет на этикетки соседних задач.
Контракт C680-01…14 записан в требованиях и следует библиотеке сбоев B03/B04/B07/B08/B12/B16/B20.

Браузерная проверка пока не выполнена. Команда Node require.resolve для playwright,
playwright-core и @playwright/test с paths ./frontend и ../night1007-684-586/frontend вернула
для всех unavailable; node_modules обоих worktree ведут на существующие общие frontend
зависимости. Ничего не устанавливалось. Новый браузер/принтер/production не запускался.
Это ограничение наблюдения, не доказательство дефекта макета. Следующему этапу нужен
существующий Playwright для проверки реальных экранов и PDF; физическая бумага проверяется
отдельно только после разрешения и не объявляется проверенной по HTML или PDF.
