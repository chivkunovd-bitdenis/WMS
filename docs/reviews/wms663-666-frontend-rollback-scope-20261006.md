# WMS-663 / WMS-666: граница frontend rollback всего пакета, 06.10.2026

Текущий аналитик Sol6.1 сверил полный runtime frontend diff прежнего стенда
`727575a0fd47dec56f34b38b987925686626c2b9` → установленного кандидата
`585877bedf948faf7e38d14acc7e89acbf4feab3`. Git ancestry подтверждена.
База отката именно727, а не случайный старый screenshot или весь файл из etalon.
В Git diff45 frontend-путей:15 runtime, остальные30 tests/proofs и три673
вспомогательных test-файла, не импортируемых runtime. Сверка включает все15
runtime, а не только новый компонент663. Код/tests не менялись.

## Прямой контракт владельца имеет приоритет

Ведущий передал прямое поручение владельца: «откати ... фронт по всем остальным
процессам, ровно таким, какой он был, кроме строго ... описано в задачах»;
«одна галка GTD ... без неё и без чего там ещё ... на этапе коробов ...
нажимаешь и всё». Дополнительно владелец отклонил mixed screenshot:
«поехало форматирование», «ЧЗ уехали». Прежний C11 PASS отозван в `e9da2f9ea`.

Исходные слова проверены по документам662/663 (source153/154: обратная
синхронизация и «такую же галку»),666 (три входа, единый список, настройки,
Ozon без QR),517 (проданные WB КИЗ по sales),667 (фильтр фактического остатка),
669 (владелец «И то и то»: фильтры и группировка),672 (пачка коробов и быстрая
печать с сохранением защиты неизвестного исхода),673 («Нету столбца цвет»),
681 (нормальные QR WB без подмены внутренним кодом). 675 адресный аудит не даёт
разрешения менять frontend. Дополненные аналитиком R сами по себе не являются
разрешением на оформление, новые формы или чипы.

## Конкретные лишние изменения: вернуть/удалить

| Место в `585877bed` | Коррекция и основание |
| --- | --- |
| `FfFbsSupplyWorkspace.tsx`: import и mount `OzonExemplarDocuments` в packing rows; весь `OzonExemplarDocuments.tsx` как строковый UI | Убрать раскрытие «ГТД / РНПТ», поля номеров, отдельные absent-галки и действия Save/prepare/check. Прямой663 теперь разрешает одну общую галку только в Коробах. Backend durable-сервис сохраняется. Удаление/переиспользование файла решает разработчик без возвращения row UI. |
| `FfFbsSupplyWorkspace.tsx` around3708/3747: `useFlexGap={isOzonSupply}`, Ozon-only `flexWrap`, `flex: isOzonSupply ? ...` | Вернуть прежние sx из727: они добавлены для растущего блока документов, который владелец запрещает. Не переносить старое row-form оформление в другие процессы. |
| `FfFbsSupplyWorkspace.tsx` around3989: «упаковано» → «Обработано» | Вернуть исходное «упаковано». Исходный666 не поручал переименовывать показатель. |
| `FfFbsSupplyWorkspace.tsx` around5267: новый `FbsStatusChip` + дополнительный `Stack` в «Составе» | Вернуть прежнюю разметку ссылки/ячейки и убрать новый import. Это новое оформление пакета662; исходная обратная синхронизация не требует нового чипа. Errorhandling662 не откатывать. |
| Unified mixed packing rows: разные x колонок «Размер», «Стикер», «ЧЗ» у WB/Ozon | Минимально выровнять общие колонки, используя прежний вид WB-строк; это выполнение исходного666, а не новый дизайн. Приёмка требует фактической геометрии DOM/снимка, отсутствие overlap само по себе недостаточно. Не расширять на шапки, шрифты и все размеры экранов. |

**Запрещён неверный откат:** `FbsAssemblyTaskRows.tsx` не изменился между727 и585.
Его два чипа списка существовали до пакета; последний релевантный commit до базы
`7cd868cd854351789f0f4094ed62c30a01e5e986`, WMS-588 (30.09).
Их удаление не является возвратом нового frontend и не разрешено.

## Allowlist всех15 runtime-файлов

Разрешён только перечисленный смысл hunks. Попадание пути в таблицу не разрешает
косметику или подмену файла целиком: общий Workspace содержит несколько задач.

| Runtime-файл | Что сохранить и почему |
| --- | --- |
| `screens/ff/FfInboundRequestView.tsx` |672: одна лента штатных этикеток, запрет двойной передачи, durable attempt до print, восстановление technical marks и неизвестного исхода. Состав/размер этикетки и обычный успешный UI сохраняются. Подтверждение неизвестной предыдущей печати не считать бумагой. |
| `screens/ff/inboundDraftPersistence.ts` |672: exact HTML/paths/state в существующем recovery record, без новой UI-сущности. |
| `screens/v2/FbsPackingScanBar.tsx` |666: общая полоса/настройки всех входов, контекст FIFO и fencing принятых сканов, Ozon qrDisabled. Внешний стиль полосы остался baseline; новые размеры/содержимое вне запроса не разрешены. |
| `screens/v2/FbsScanPrintToggles.tsx` |666: QR видим, disabled/false для Ozon, предпочтение WB не стирается; остальные существующие настройки/копии/размеры сохранить. |
| `screens/v2/FfFbsOrdersScreen.tsx` |662: error Alert существующего действия добавления заказа показывает действительный отказ; это обработка ошибки, её сохранить. |
| `screens/v2/FfFbsSupplyAssembly.tsx` |666: убрать active/expanded ручной выбор рамки, общий scanner/list и QR marketplace-context; прежняя шапка/вкладки не переписываются. |
| `screens/v2/FfFbsSupplyWorkspace.tsx` |666: единая packing-поверхность и прозрачный start-work, Ozon позиционный lookup/assign `order_product_ids`, WB scan→immediate print, короб/fencing/recovery;673 marketplace в picking-print;681 только штатный WB boxQR, без local fallback.662 error wrapping сохранить. Лишние UI-hunks перечислены отдельно выше.663 заменить одной галкой в Коробах. |
| `screens/v2/FfProductsCatalogScreen.tsx` |667: только «С остатком» в существующих фильтрах и параметр/сброс страницы; источник тот же фактический остаток до пагинации. |
| `screens/v2/OzonExemplarDocuments.tsx` |Прежняя реализация строковой формы не разрешена. Допустим лишь внутренний перенос технического чтения/ошибок к общей галке663 без row UI; не оставлять component mount в packing. |
| `screens/v2/SellerKizWithdrawalScreen.tsx` |517: одна строка честно уточняет проданные WB FBS по sales; нового layout/пути подписи в delta727..585 нет. |
| `screens/v2/SellerProductsStockScreen.tsx` |669: запрошенные артикул/размер/«Только с остатком», группа категория→артикул→размер, поиск/пагинация и seller/request fence. Владелец явно потребовал оба поведения; эти групповые строки не считаются лишней косметикой666. |
| `screens/v2/fbsSequentialPacking.ts` |666: scoped FIFO/router match, сохранённые попытки и короб в момент скана; не задерживать immediate print внешним действием. |
| `screens/v2/fbsSupplyAssembly.ts` |673: передать существующий color в picking rows, без изменения экранной строки упаковки. |
| `screens/v2/fbsUx.ts` |673: отдельный «Цвет» в печатном листе/HTML, корректный posting идентификатор Ozon; прежняя семантика WMS610 и геометрия657 сохраняются. Не менять колонки упаковки под видом print-color. |
| `utils/printBarcodeLabel.ts` |672: awaitable handoff только для inbound batches, bounded image decode и восстановление; прежние scan callers без handoff сохраняют timing/контракт. Нет изменения label geometry/баркода в этом diff. |

Пути в таблице относительны `frontend/src/`. По прочитанному полному runtime diff
других неразрешённых изменений экранного оформления не выявлено; это аналитическая
граница будущей коррекции, не новый code-review или подтверждение всех сценариев.
Tests/E2E/fixtures от общего кандидата не откатываются как «лишние пиксели»:
они не пользовательский runtime, меняет их отдельный тестировщик по новому
прямому контракту, сохраняя защиту технических ошибок/повторов.

## Свежий663 контракт передан разработчику и тестировщику

Одна «Без ГТД и РНПТ» в Коробах текущей Ozon-поставки; явный true делает выбранное
отсутствие всех требуемых документов реальных экземпляров только в этом контексте.
Открытие/false не пишет. Checked отражает persisted absent-intent, не accepted;
обратный клик не стирает документы и не изображает отменённое persisted намерение.
Неполный результат нескольких posting и причина ошибки сохраняются различимыми.
Нет дополнительных кнопок/окон/форм. Ошибки идут только через существующий
feedback/errorchannel поставки: новое UI — одна галка, без новых панелей, чипов,
инструкций, списков posting и отдельной строки результата/статуса. Checked —
сохранённое намерение, не accepted; unknown/readback остаются внутри обработки
операции, не требуют новой строки UI.

Одна durable операция полного payload на точный posting сохраняет маркировки,
weight, чужие документы и bounded tenant/seller/product/exemplar IDs. Два клика
не дают второй SET. Pending/unknown проверяются чтением, HTTP200 не accepted.
Исполнитель663 установил: loop per-exemplar PUT небезопасен — первый SET меняет
posting state. Аналитик отозвал этот ранний технический вариант. Исполнитель и
тестировщик согласовали одну batch-операцию существующего durable-сервиса;
её URL/method не превращаются в отдельное требование бизнеса.

666: единый список/скан/настройки, Ozon без QR и WB immediate print сохраняются;
общая колонная геометрия проверяется в mixed, не косметическим переписыванием
всех процессов. C11 остаётся не принят до коррекции; C12 бумага OPEN.

## Состояние и следующий шаг

Новые исходные слова и граница записаны в requirements663/666 и их разделах
backlog. Продукт не изменён, rollback ещё не реализован/не проверен.
Разработчик663 и тестировщик `frontend_qr_finish` получили контракт напрямую,
ведущий получил точные лишние hunks и allowlist. Далее tests до кода → узкая
коррекция → независимое ревью только новой delta и её visual evidence.
Новые skills/Astra/CI ради документов не запускались. База/runtime/staging не
передвигались, физическая печать и внешние операции не выполнялись.

## Полный inventory frontend diff727..585

- `frontend/src/screens/ff/FfInboundRequestView.tsx` — runtime, смысл разрешения/отката выше
- `frontend/src/screens/ff/inboundDraftPersistence.ts` — runtime, смысл разрешения/отката выше
- `frontend/src/screens/v2/FbsPackingScanBar.tsx` — runtime, смысл разрешения/отката выше
- `frontend/src/screens/v2/FbsScanPrintToggles.tsx` — runtime, смысл разрешения/отката выше
- `frontend/src/screens/v2/FfFbsOrdersScreen.tsx` — runtime, смысл разрешения/отката выше
- `frontend/src/screens/v2/FfFbsSupplyAssembly.scanners.dom.test.tsx` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/FfFbsSupplyAssembly.tsx` — runtime, смысл разрешения/отката выше
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.assembly.dom.test.tsx` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.scan.dom.test.tsx` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.size.test.ts` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` — runtime, смысл разрешения/отката выше
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms514.test.ts` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms636.dom.test.tsx` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms662.c19.dom.test.tsx` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/FfProductsCatalogScreen.hasStock.wms667.dom.test.tsx` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/FfProductsCatalogScreen.tsx` — runtime, смысл разрешения/отката выше
- `frontend/src/screens/v2/OzonExemplarDocuments.tsx` — runtime, смысл разрешения/отката выше
- `frontend/src/screens/v2/OzonExemplarDocuments.wms663.developer.dom.test.tsx` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/OzonExemplarDocuments.wms663.residual.dom.test.tsx` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/SellerKizWithdrawalScreen.tsx` — runtime, смысл разрешения/отката выше
- `frontend/src/screens/v2/SellerProductsStockScreen.tsx` — runtime, смысл разрешения/отката выше
- `frontend/src/screens/v2/Wms669SellerCatalog.dom.test.tsx` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/fbsPickingColor.wms673.dom.test.tsx` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/fbsPickingColor.wms673.pdf.test.ts` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/fbsPickingListPrint.wms657.test.ts` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/fbsSequentialPacking.ts` — runtime, смысл разрешения/отката выше
- `frontend/src/screens/v2/fbsSupplyAssembly.ts` — runtime, смысл разрешения/отката выше
- `frontend/src/screens/v2/fbsUx.ts` — runtime, смысл разрешения/отката выше
- `frontend/src/screens/v2/wms666ChangeScope.test.ts` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/wms673MarketplaceProjection.json` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/wms673PrintFixtures.ts` — test/proof/helper, вне пользовательского runtime
- `frontend/src/screens/v2/wms673PrintRenderer.ts` — test/proof/helper, вне пользовательского runtime
- `frontend/src/utils/printBarcodeLabel.ts` — runtime, смысл разрешения/отката выше
- `frontend/tests-e2e/wms666-proof/index.html` — test/proof/helper, вне пользовательского runtime
- `frontend/tests-e2e/wms666-proof/main.tsx` — test/proof/helper, вне пользовательского runtime
- `frontend/tests-e2e/wms666-proof/vite.config.ts` — test/proof/helper, вне пользовательского runtime
- `frontend/tests-e2e/wms672-box-labels.test.mjs` — test/proof/helper, вне пользовательского runtime
- `frontend/tests-e2e/wms672-dom.config.ts` — test/proof/helper, вне пользовательского runtime
- `frontend/tests-e2e/wms672-dom.test.tsx` — test/proof/helper, вне пользовательского runtime
- `frontend/tests-e2e/wms672-harness.html` — test/proof/helper, вне пользовательского runtime
- `frontend/tests-e2e/wms672-harness.tsx` — test/proof/helper, вне пользовательского runtime
- `frontend/tests-e2e/wms672-remaining.test.mjs` — test/proof/helper, вне пользовательского runtime
- `frontend/tests-e2e/wms672-vite.config.ts` — test/proof/helper, вне пользовательского runtime

## Дополнительная сверка ранней части пакета с production baseline

Ведущий отдельно прочитал frontend diff `8f11d912351e8de7633b4abcf74d195badaeb254` → `727575a0fd47dec56f34b38b987925686626c2b9` и проверил его сохранённый результат в объединённой ветке после runtime `1fe678d9abb4ed06afc79eba41461e3215978d5b`. Это проверка кода, не заявление о текущей версии production или визуальная приёмка.

- WMS-653: треугольник ошибок, окно и группы заказов прямо названы владельцем в уточнении 05.10; соответствующие hunks Workspace и типы API относятся к этому требованию.
- WMS-657: удаление запрета переноса размера — ровно исправление «Универсальный» в существующей печатной колонке, без перестройки таблицы.
- WMS-659: поле количества и создание коробов в приёмке/возврате прямо поручены владельцем; исправление чтения draft не меняет оформление.
- WMS-670: удаление глобального переключателя обслуживания склада из товарного окна следует исходному уточнению «по конкретному товару, по конкретному складу … ни в коем случае не общая настройка». Товарный переключатель публикации остаётся, глобальное действие из товарного контекста убрано.
- Промежуточное удаление error Alert добавления в поставку уже восстановлено WMS-662: итоговый FfFbsOrdersScreen.tsx совпадает с production baseline.
- Промежуточная подмена настоящего WB boxQR внутренним кодом уже убрана WMS-681: соответствующих QR hunks между production baseline и итоговым Workspace нет.

FbsAssemblyTaskRows.tsx одинаков в baseline production,727 и585: blob `2df700a59b48831069f6f02b43339e505828acc4`. Два прежних чипа списка не добавлялись этим пакетом. Эта дополнительная сверка закрывает границу раннего пакета; окончательная визуальная проверка исправленной упаковки выполняется отдельно на стенде.
