# WMS-429 isolated Astra high review

Source:859fe08dc3fc6a20a2a16c91331f12b251756a2a; isolated thread01a08db5-fdff-7bb1-b235-e25fcf1a5c67. No prior reviewer output supplied. The three findings below were subsequently fixed in6185e3b7; targeted confirmation follows separately.

**В релизе `859fe08dc3fc6a20a2a16c91331f12b251756a2a` обнаружены три существенных дефекта формирования этикеток.** Выводы основаны на diff `dcac6251..859fe08d` и связанных исходниках. Предыдущие ревью и их артефакты не читал; тесты, сборки и браузер не запускал. `85d802b1` является предком базы и финального коммита; проверка границы не превращалась в повторное ревью принятого пакета.

1. **P2 — выбранный штрихкод не попадает в печатную ленту.**
   Место: [MarkingPrintDialog.tsx:939](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingPrintDialog.tsx:939), также формирование этикеток с ЧЗ на строке 913.

   **Условие:** у товара Ozon несколько штрихкодов, оператор открывает печать заказа и выбирает другой код в поле «Площадка и штрихкод». Выбор меняет `selectedProductLabel`, но сборщик FBS использует заранее созданные `order.productLabels` либо результат `productLabelForPrintedFbsCode`. В них остаётся первый штрихкод привязки.

   **Последствие:** фактическая этикетка содержит другой код, чем выбрал оператор; предпросмотр и печатный результат могут расходиться.

   **Минимальное исправление:** передавать выбранный штрихкод в этикетку соответствующей позиции и использовать этот объект при формировании ленты. Выбор для одной позиции не должен менять остальные позиции отправления.

2. **P2 — на этикетки разных позиций переносится размер одного товара.**
   Место: [FfFbsSupplyWorkspace.tsx:308](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx:308).

   **Условие:** отправление Ozon содержит товары разных размеров, а у общей карточки `order.product` заполнен размер. `productLabelFromPosition` берёт название, артикул и штрихкод конкретной позиции, но каждому объекту присваивает `wb_size: order.product.size`.

   **Последствие:** при включённой печати размера этикетка второй позиции получает её собственный штрихкод и чужую надпись «Размер». Это ошибка содержимого этикетки, а не оформления.

   **Минимальное исправление:** убрать подстановку размера из общей карточки. Передавать размер только из товара конкретной позиции; если такого значения в данных позиции нет, не печатать его.

3. **P2 — из смешанного отправления пропадают товарные этикетки позиций без ЧЗ.**
   Место: [MarkingPrintDialog.tsx:907](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingPrintDialog.tsx:907), альтернативная ветка на строке 938.

   **Условие:** в одном отправлении Ozon есть позиция с привязанным кодом ЧЗ и позиция без ЧЗ; оператор печатает или перепечатывает ленту с товарными штрихкодами. Сервер выставляет `requires_honest_sign` всему отправлению. Клиент после этого формирует этикетки только по `printed_codes`, а обход всех `productLabels` находится в противоположной ветке `else`.

   **Последствие:** позиция без ЧЗ вообще не получает товарную этикетку. При этом наличие этикеток первой позиции позволяет завершить сборку ленты без сообщения о пропущенной позиции.

   **Минимальное исправление:** формировать товарные этикетки по позициям и их количеству независимо от общего признака ЧЗ. Для позиций с ЧЗ сохранять сопоставление по `order_product_id`, не дублируя уже сформированные товарные этикетки.

Это **дефекты исходников**, не ограничения оборудования. Совместимость ОС, драйвера, очереди `lp` и физического принтера не проверялась; квитанция агента подтверждает только приём файла очередью ОС. В diff релиза Android-изменения представлены сохранённым файлом патча WMS-402, а не изменениями мобильных исходников. Состояние отдельного мобильного checkout и установленного APK11 этой проверкой не подтверждается.

**Рекомендация: не выпускать этот frozen commit как финальный релиз — сначала устранить три указанных дефекта печати.**

## Same-thread narrow confirmation

1. **Выбранный штрихкод Ozon доходит до позиционной этикетки, но не до её предпросмотра — не исправлено полностью.**

   В печати выбранный код накладывается только на выбранную пару «отправление + позиция» в [MarkingPrintDialog.tsx:130](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingPrintDialog.tsx:130), а затем именно этот объект используется при построении этикетки кода ЧЗ в [MarkingPrintDialog.tsx:952](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingPrintDialog.tsx:952) и [MarkingPrintDialog.tsx:976](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingPrintDialog.tsx:976). Физически сформированный лист получает выбранный штрихкод нужной позиции.

   Но «Реальный макет ленты» передаёт список Ozon-позиций в [MarkingPrintDialog.tsx:1930](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingPrintDialog.tsx:1930), а при наличии ЧЗ предпросмотр игнорирует `productLabels` и рисует один общий `order.productLabel` в [MarkingLabelPreview.tsx:294](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingLabelPreview.tsx:294)-[300](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingLabelPreview.tsx:300). Выбранный код меняет только `productLabels`, не это поле.

2. **Общий размер совместимой карточки больше не печатается на этикетке другой позиции Ozon — исправлено.**

   Позиционная этикетка теперь получает `wb_size: null` в [FfFbsSupplyWorkspace.tsx:305](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx:305)-[310](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx:310). Для кода ЧЗ печать выбирает `productLabel` по его `order_product_id` в [MarkingPrintDialog.tsx:174](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingPrintDialog.tsx:174)-[180](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingPrintDialog.tsx:180); обычные этикетки строятся из того же объекта позиции в [MarkingPrintDialog.tsx:1002](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingPrintDialog.tsx:1002)-[1014](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingPrintDialog.tsx:1014).

   В предпросмотре ЧЗ остаётся описанное ниже несоответствие: общий `productLabelFromOrder` всё ещё содержит `order.product.size` в [FfFbsSupplyWorkspace.tsx:343](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx:343). Это не попадает в сформированный печатный файл, но делает макет недостоверным.

3. **Смешанное отправление с маркируемой и немаркируемой позициями печатает этикетки каждой немаркируемой позиции — исправлено.**

   `remainingProductLabelsAfterPrintedCodes` считает напечатанные коды по `order_product_id` и оставляет позицию без ЧЗ с её полным количеством в [MarkingPrintDialog.tsx:154](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingPrintDialog.tsx:154)-[171](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingPrintDialog.tsx:171). Формирование ленты больше не находится в ветке `else`: после секций ЧЗ оно добавляет оставшиеся товарные этикетки в [MarkingPrintDialog.tsx:1002](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingPrintDialog.tsx:1002)-[1016](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingPrintDialog.tsx:1016). Поэтому позиция без ЧЗ не исчезает из печати.

Обнаружена одна регрессия узкой правки, совпадающая с неполностью исправленным первым пунктом.

- **P2 — предпросмотр маркируемого отправления Ozon показывает другой штрихкод и может показывать общий размер.**
  **Файл:** [MarkingLabelPreview.tsx:294](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingLabelPreview.tsx:294).
  **Триггер:** оператор открывает печать ЧЗ для Ozon, выбирает альтернативный штрихкод первой позиции и смотрит «Реальный макет ленты»; либо в отправлении есть другая позиция с иным размером.
  **Последствие:** печатный файл собирается из позиционного `productLabels`, а экран показывает общий `order.productLabel`, не содержащий выбранного штрихкода. Оператор подтверждает печать по недостоверному макету; в нём также может быть размер совместимой карточки другого товара.
  **Минимальная коррекция:** в ветке ЧЗ предпросмотра строить его из того же позиционного `productLabels`, что и реальная печать, с привязкой демонстрационного кода к конкретной позиции. Как минимум `withSelectedFbsTapeBarcode` должен заменять и отображаемый `productLabel` выбранной первой позиции, но полноценное исправление должно сохранять соответствие кода ЧЗ и `order_product_id`.

Изменения количества корректны для Ozon-отправлений без ЧЗ: число единиц суммируется по всем `productLabels` в [MarkingPrintDialog.tsx:718](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingPrintDialog.tsx:718)-[725](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/components/MarkingPrintDialog.tsx:725), а фактическая печать повторяет этикетку по количеству позиции. `MarketplaceChip` передаёт только `order.marketplace` в [FfFbsOrdersScreen.tsx:354](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-astra-review-20260911/frontend/src/screens/v2/FfFbsOrdersScreen.tsx:354) и не влияет на штрихкоды, количество или состав печати.

**Рекомендация по этому узкому подтверждению: не принимать `208775d` как окончательное исправление, пока предпросмотр Ozon с ЧЗ не будет собираться из тех же позиционных данных, что и реальная лента.**

## Root resolution after review, no further review cycle

Astra confirmed physical label selection/size/mixed quantity corrections and
identified a remaining preview mismatch.6c3393d6 now constructs Ozon ЧЗ sample
units from each position's own productLabels and copies, including the selected
barcode, with no compatibility-product fallback. Root read the complete diff
and additionally prevented preview from substituting SKU when an Ozon barcode
is absent. WB retains the former single-order branch. The sample CIS is still
an example layout, not a newly allocated real code. Final visual reread remains
blocked by the locked Mac; no claim of physical printing or live marketplace
handoff is made. No further Opus/Astra review cycle is requested.

Targeted frontend checks:28 passed (selected barcode exact order+position,
remaining mixed-posting quantities, unchanged WB behavior and existing picking
helpers). Final typecheck/build checked separately after last preview change.
CI859:2478 passed,134 skipped,1 xfailed,3 failures. Failures were two outdated
contract fixtures and an inherited Ozon generator mismatch, not reverted runtime
behavior; all three specific reruns passed (2 in2.16s, equality in0.04s).
