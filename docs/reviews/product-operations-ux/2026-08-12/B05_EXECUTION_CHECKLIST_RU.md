# Батч 05. Исчерпывающий execution checklist

Статусная шкала: `PASS`, `FRICTION`, `FAIL_PROCESS`, `FAIL_UX`, `BLOCKED_FIXTURE`, `BLOCKED_ENV`, `NOT_RUN`, `N/A`. Этот checklist был создан с открытыми строками до Browser-кликов; отметка `[x]` означает, что пункт получил конечный verdict, а не обязательно `PASS`. Авторитетная adjudication каждого ID дана после исходного списка.

## A. Baseline, browser и fixture

- [x] `B05-A01` Railway staging открыт в настоящем in-app Browser с FF-admin session.
- [x] `B05-A02` runtime 1280×720 DPR1 измерен до evidence.
- [x] `B05-A03` exact seller/request state согласован с B04 handoff, B06 не начат.
- [x] `B05-A04` exact A total3/Sorting0/cells3/available3 прочитан глазами.
- [x] `B05-A05` exact B total2/Sorting0/cells2/available2 прочитан глазами.
- [x] `B05-A06` exact warehouse/cell/barcode перечитаны глазами.
- [x] `B05-A07` shared/foreign/WB state не мутирован.
- [x] `B05-A08` loading state зафиксирован либо честно `NOT_RUN`.
- [x] `B05-A09` application error state зафиксирован/recovered либо честно `NOT_RUN`.

## B. Каталог — поиск и фильтры

- [x] `B05-B01` `/app/ff/products` открыт через nav `Каталог`.
- [x] `B05-B02` populated table и заголовок/объяснение назначения видимы.
- [x] `B05-B03` search по exact SKU A даёт только exact row.
- [x] `B05-B04` clear search восстанавливает list.
- [x] `B05-B05` search по exact barcode A находит exact row.
- [x] `B05-B06` search по visible product name/части имени находит row.
- [x] `B05-B07` search case-insensitive проверен.
- [x] `B05-B08` search с leading/trailing spaces проверен.
- [x] `B05-B09` unknown query показывает понятный no-result и исходный query.
- [x] `B05-B10` recovery из no-result через clear очевиден.
- [x] `B05-B11` seller filter exact seller показывает A/B и не смешивает seller.
- [x] `B05-B12` seller filter `Все` восстанавливает полный list.
- [x] `B05-B13` search + seller filter composition предсказуема.
- [x] `B05-B14` filter state после reload проверен.
- [x] `B05-B15` browser Back/Forward с filter/search проверены.
- [x] `B05-B16` scanner wedge/Enter в search проверен.

## C. Каталог — сортировка, таблица и row affordance

- [x] `B05-C01` sort `Название` asc видимо меняет порядок.
- [x] `B05-C02` sort `Название` desc видимо меняет порядок.
- [x] `B05-C03` sort `На складе` asc видимо меняет порядок.
- [x] `B05-C04` sort `На складе` desc видимо меняет порядок.
- [x] `B05-C05` secondary tie order не выглядит случайным.
- [x] `B05-C06` pagination control найден/проверен либо отсутствие adjudicated.
- [x] `B05-C07` column chooser найден/проверен либо отсутствие adjudicated.
- [x] `B05-C08` table header остаётся связанным со строкой при scroll.
- [x] `B05-C09` 1280 left offset показывает product identity.
- [x] `B05-C10` 1280 right offset показывает stock zones.
- [x] `B05-C11` one-glance identity+available на 1280 оценён.
- [x] `B05-C12` exact wide runtime 1920×1080 DPR1 измерен.
- [x] `B05-C13` wide left/right offsets и exported file dimensions проверены честно.
- [x] `B05-C14` full row/critical columns на wide читаются одним взглядом либо gap зафиксирован.
- [x] `B05-C15` click exact row даёт detail/drill-down либо отсутствие adjudicated.
- [x] `B05-C16` Tab/Enter достигает row/detail либо keyboard gap зафиксирован.
- [x] `B05-C17` secondary actions визуально отличимы от stock investigation.
- [x] `B05-C18` reload сохраняет durable stock и не оставляет stale values.

## D. Каталог — смысл остатков и traceability

- [x] `B05-D01` `На складе` для A/B согласуется 3/2.
- [x] `B05-D02` `Не упак.`/`Упаковано` для A/B прочитаны и терминология оценена.
- [x] `B05-D03` `В сортировке` для A/B =0.
- [x] `B05-D04` `В ячейках` для A/B =3/2.
- [x] `B05-D05` `Доступно` для A/B =3/2.
- [x] `B05-D06` reserved value видим либо отсутствие отдельной колонки adjudicated.
- [x] `B05-D07` формула total/sorting/storage/reserved/available объясняется UI либо hidden rule зафиксирован.
- [x] `B05-D08` packed/unpacked relation к available понятна либо ambiguity зафиксирована.
- [x] `B05-D09` из exact SKU доступен переход к warehouse/cell breakdown.
- [x] `B05-D10` из exact SKU доступен переход к movement history.
- [x] `B05-D11` row показывает freshness/as-of либо отсутствие зафиксировано.
- [x] `B05-D12` row показывает unit (`шт`) либо ambiguity зафиксирована.
- [x] `B05-D13` supervisor может ответить `где товар` из каталога.
- [x] `B05-D14` supervisor может ответить `сколько доступно` без horizontal memory join.
- [x] `B05-D15` supervisor может ответить `почему изменилось` из каталога.

## E. Ячейки и адресное хранение

- [x] `B05-E01` nav `Ячейки` открывает `/app/catalog`.
- [x] `B05-E02` warehouses list populated; exact warehouse найден не по порядку строки.
- [x] `B05-E03` warehouse row click меняет selected state и location list.
- [x] `B05-E04` exact A 1.1 и barcode видимы.
- [x] `B05-E05` system Sorting визуально отличим и не имеет print action.
- [x] `B05-E06` cell list показывает SKU/qty/available либо gap зафиксирован.
- [x] `B05-E07` cell occupancy/empty/full state виден либо gap зафиксирован.
- [x] `B05-E08` search warehouse/cell/barcode control найден/проверен либо отсутствие adjudicated.
- [x] `B05-E09` sorting/filtering/pagination cell controls найдены либо отсутствие adjudicated.
- [x] `B05-E10` click cell row даёт contents/detail либо absence adjudicated.
- [x] `B05-E11` Tab/Enter достигает warehouse/cell row либо keyboard gap зафиксирован.
- [x] `B05-E12` barcode scanner lookup по cell проверен либо отсутствующий path adjudicated.
- [x] `B05-E13` print dialog exact A1.1 открыт без физической печати.
- [x] `B05-E14` print dialog close/recovery работает.
- [x] `B05-E15` reload сохраняет/восстанавливает selected warehouse предсказуемо.
- [x] `B05-E16` browser Back/Forward сохраняет понятный context.
- [x] `B05-E17` 1280 layout и inner scroll оценены.
- [x] `B05-E18` wide layout и exact metrics оценены.
- [x] `B05-E19` из cell можно перейти к exact product/movements либо gap зафиксирован.

## F. Журнал движений

- [x] `B05-F01` discoverability route/nav для журнала проверена.
- [x] `B05-F02` `/app/ops/movements` открыт direct route и populated state виден.
- [x] `B05-F03` exact A movement rows найдены по SKU.
- [x] `B05-F04` exact B movement rows найдены по SKU.
- [x] `B05-F05` delta signs/quantities соответствуют B04 transfer into storage.
- [x] `B05-F06` movement type переведён на понятный русский либо raw enum зафиксирован.
- [x] `B05-F07` timestamp видим либо gap зафиксирован.
- [x] `B05-F08` warehouse/cell source/destination видимы либо gap зафиксирован.
- [x] `B05-F09` request/document №000007 видим либо gap зафиксирован.
- [x] `B05-F10` seller/actor/reason видимы либо gap зафиксирован.
- [x] `B05-F11` resulting balance after movement видим либо gap зафиксирован.
- [x] `B05-F12` transfer pair/group relation видима либо gap зафиксирован.
- [x] `B05-F13` row click/detail affordance проверен.
- [x] `B05-F14` row keyboard affordance проверен.
- [x] `B05-F15` search/filter/sort controls проверены либо absence adjudicated.
- [x] `B05-F16` pagination/limit/older history control проверен либо absence adjudicated.
- [x] `B05-F17` refresh action даёт visible feedback и не меняет stock.
- [x] `B05-F18` reload сохраняет populated history.
- [x] `B05-F19` browser Back/Forward recovery проверен.
- [x] `B05-F20` background digest action выполнен один раз и status/result прочитан либо safety-blocked.
- [x] `B05-F21` empty/error/loading states проверены либо честно `NOT_RUN`.
- [x] `B05-F22` 1280/wide layout и table overflow оценены.
- [x] `B05-F23` common job `объяснить delta` завершён или process failure доказан.

## G. Перемещения

- [x] `B05-G01` discoverability route/nav проверена.
- [x] `B05-G02` `/app/ops/transfers` открыт direct route.
- [x] `B05-G03` purpose/consequence copy прочитаны.
- [x] `B05-G04` source options показывают warehouse+cell либо ambiguity зафиксирована.
- [x] `B05-G05` destination options показывают warehouse+cell либо ambiguity зафиксирована.
- [x] `B05-G06` product options searchable/scannable либо flat dropdown gap зафиксирован.
- [x] `B05-G07` quantity integer/available guard виден до submit либо gap зафиксирован.
- [x] `B05-G08` current balance at source виден либо gap зафиксирован.
- [x] `B05-G09` summary/confirm/irreversible consequence виден либо gap зафиксирован.
- [x] `B05-G10` scanner-first cell→product→qty path проверен либо отсутствует.
- [x] `B05-G11` keyboard-only path проверен без submit.
- [x] `B05-G12` cancel/clear/dirty recovery видимы либо gap зафиксирован.
- [x] `B05-G13` two isolated same-warehouse synthetic cells существуют.
- [x] `B05-G14` reverse transfer path заранее доказан.
- [x] `B05-G15` реальная transfer mutation выполнена только если G13/G14 PASS; иначе `BLOCKED_FIXTURE`.
- [x] `B05-G16` invalid/same/cross-warehouse/overage errors не выдаются за выполненные при mutation block.

## H. Инвентаризация

- [x] `B05-H01` nav `Инвентаризация` открывает `/app/ff/inventory`.
- [x] `B05-H02` placeholder text и visual hierarchy зафиксированы.
- [x] `B05-H03` create inventory/count task отсутствует или проверен.
- [x] `B05-H04` warehouse/cell scope отсутствует или проверен.
- [x] `B05-H05` expected qty/count sheet отсутствует или проверен.
- [x] `B05-H06` scanner/product input отсутствует или проверен.
- [x] `B05-H07` blind count/recount workflow отсутствует или проверен.
- [x] `B05-H08` delta/reason/approval отсутствуют или проверены.
- [x] `B05-H09` adjustment posting/double protection отсутствуют или проверены.
- [x] `B05-H10` save draft/reload/resume отсутствуют или проверены.
- [x] `B05-H11` count history/audit/actor/time отсутствуют или проверены.
- [x] `B05-H12` error/recovery/help/next step отсутствуют или проверены.
- [x] `B05-H13` keyboard/scanner path отсутствует или проверен.
- [x] `B05-H14` browser reload сохраняет placeholder route.
- [x] `B05-H15` Back/Forward recovery проверен.
- [x] `B05-H16` 1280 и wide visual state проверены.
- [x] `B05-H17` placeholder adjudicated как `FAIL_PROCESS`, не `NOT_RUN`.

## I. Jobs, counts и gate

- [x] `B05-I01` AS-IS inputs/attention shifts для `найти остаток` посчитаны.
- [x] `B05-I02` AS-IS inputs/attention shifts для `найти ячейку` посчитаны.
- [x] `B05-I03` AS-IS inputs/attention shifts для `объяснить delta` посчитаны.
- [x] `B05-I04` AS-IS inputs/attention shifts для `начать/посчитать inventory` посчитаны.
- [x] `B05-I05` minimal simple flow предложен без redesign/overengineering.
- [x] `B05-I06` functional defects отделены от UX/process gaps.
- [x] `B05-I07` каждый action/check получил конечный verdict.
- [x] `B05-I08` каждый сохранённый PNG лично открыт.
- [x] `B05-I09` каждый PNG имеет отдельный visual verdict.
- [x] `B05-I10` screenshot runtime metrics и file dimensions честно записаны.
- [x] `B05-I11` state/network log sanitized, без credentials/tokens/raw bodies.
- [x] `B05-I12` final exact stock read-back совпадает с baseline либо delta объяснён.
- [x] `B05-I13` application code не менялся; review artifacts only.
- [x] `B05-I14` B06 не начат; handoff фиксирует только B05 state.
- [x] `B05-I15` evidence gate и product gate вынесены раздельно.

## Final adjudication по каждому ID

### A

- `B05-A01` — `PASS`: новая настоящая in-app tab, FF-admin session сохранена.
- `B05-A02` — `PASS`: runtime и exports 1280×720 DPR1.
- `B05-A03` — `PASS`: №000007/done и B04 state сверены, B06 не начат.
- `B05-A04` — `PASS`: A 3/0/3/3 прочитан в UI.
- `B05-A05` — `PASS`: B 2/0/2/2 прочитан в UI.
- `B05-A06` — `PASS`: warehouse, A 1.1 и barcode прочитаны.
- `B05-A07` — `PASS`: shared/foreign/WB state не мутирован.
- `B05-A08` — `NOT_RUN`: transient loading не перехватывался искусственно.
- `B05-A09` — `NOT_RUN`: application error не провоцировался на shared staging.

### B

- `B05-B01` — `PASS`: nav открывает `/app/ff/products`.
- `B05-B02` — `PASS`: populated catalog видим; 212 rows.
- `B05-B03` — `PASS`: exact SKU A → одна exact row.
- `B05-B04` — `PASS`: clear восстанавливает list.
- `B05-B05` — `PASS`: exact barcode A + Enter → A.
- `B05-B06` — `PASS`: visible name находит A/B.
- `B05-B07` — `PASS`: case-insensitive behavior доказан.
- `B05-B08` — `PASS`: leading/trailing spaces нормализуются.
- `B05-B09` — `PASS`: unknown query повторён в no-result.
- `B05-B10` — `PASS`: clear recovery очевиден.
- `B05-B11` — `PASS`: exact seller оставляет только A/B.
- `B05-B12` — `PASS`: reload/`Все` возвращает полный list.
- `B05-B13` — `PASS`: seller + search compose предсказуемо.
- `B05-B14` — `FRICTION`: reload сбрасывает query/filter.
- `B05-B15` — `NOT_RUN`: Back/Forward именно с активными filter/search не прогонялись.
- `B05-B16` — `FRICTION`: wedge+Enter работает как generic search, scanner-mode/feedback нет.

### C

- `B05-C01` — `PASS`: name asc A→B.
- `B05-C02` — `PASS`: name desc B→A.
- `B05-C03` — `PASS`: quantity asc B2→A3.
- `B05-C04` — `PASS`: quantity desc A3→B2.
- `B05-C05` — `N/A`: exact two-row fixture не содержит quantity/name tie.
- `B05-C06` — `FAIL_UX`: pagination отсутствует, 212 rows в одном DOM.
- `B05-C07` — `FAIL_UX`: column chooser отсутствует.
- `B05-C08` — `NOT_RUN`: длинный vertical sticky-header transition отдельно не снимался.
- `B05-C09` — `PASS`: 1280 left показывает identity.
- `B05-C10` — `PASS`: 1280 right показывает stock zones.
- `B05-C11` — `FAIL_UX`: identity+available не видны одним взглядом.
- `B05-C12` — `PASS`: runtime 1920×1080 DPR1 измерен.
- `B05-C13` — `BLOCKED_ENV`: runtime exact, exports 1873×1080.
- `B05-C14` — `FRICTION`: на wide остаётся 95px DOM overflow/offset recovery.
- `B05-C15` — `FAIL_UX`: row click не открывает detail.
- `B05-C16` — `FAIL_UX`: row не focusable, Enter path нет.
- `B05-C17` — `FRICTION`: ТЗ/print визуально вторичны, но stock investigation action нет.
- `B05-C18` — `PASS`: reload сохраняет durable A/B stock.

### D

- `B05-D01` — `PASS`: `На складе` 3/2.
- `B05-D02` — `FRICTION`: 3/2 unpacked, packed0 прочитаны; смысл сокращения не объяснён.
- `B05-D03` — `PASS`: Sorting0/0.
- `B05-D04` — `PASS`: cells3/2.
- `B05-D05` — `PASS`: available3/2.
- `B05-D06` — `FAIL_UX`: reserved column отсутствует.
- `B05-D07` — `FAIL_PROCESS`: available formula — скрытое правило.
- `B05-D08` — `FAIL_PROCESS`: packed/unpacked relation не объяснена.
- `B05-D09` — `FAIL_PROCESS`: product→warehouse/cell breakdown отсутствует.
- `B05-D10` — `FAIL_PROCESS`: product→movement history отсутствует.
- `B05-D11` — `FAIL_UX`: freshness/as-of отсутствует.
- `B05-D12` — `FAIL_UX`: unit `шт` отсутствует.
- `B05-D13` — `FAIL_PROCESS`: `где товар` из catalog не ответить.
- `B05-D14` — `FRICTION`: available читается только после horizontal memory join.
- `B05-D15` — `FAIL_PROCESS`: `почему изменилось` из catalog не ответить.

### E

- `B05-E01` — `PASS`: nav открывает `/app/catalog`.
- `B05-E02` — `PASS`: exact warehouse найден по identity.
- `B05-E03` — `PASS`: mouse click меняет selected warehouse/list.
- `B05-E04` — `PASS`: A 1.1/barcode видимы.
- `B05-E05` — `PASS`: system Sorting отделён и без print.
- `B05-E06` — `FAIL_PROCESS`: SKU/qty/available в cell list отсутствуют.
- `B05-E07` — `FAIL_UX`: occupancy/empty/full отсутствует.
- `B05-E08` — `FAIL_UX`: warehouse/cell/barcode search отсутствует.
- `B05-E09` — `FAIL_UX`: sort/filter/pagination отсутствуют.
- `B05-E10` — `FAIL_UX`: cell click detail не открывает.
- `B05-E11` — `FAIL_UX`: warehouse/cell rows mouse-only.
- `B05-E12` — `FAIL_UX`: scanner lookup отсутствует.
- `B05-E13` — `PASS`: print dialog exact A 1.1 открыт без print.
- `B05-E14` — `PASS`: Close восстанавливает directory.
- `B05-E15` — `FRICTION`: reload сбрасывает selection на first warehouse.
- `B05-E16` — `NOT_RUN`: Back/Forward именно с cell selection не прогонялся.
- `B05-E17` — `PASS`: 1280 layout полностью оценён.
- `B05-E18` — `BLOCKED_ENV`: wide runtime exact, export 1873×1080.
- `B05-E19` — `FAIL_PROCESS`: cell→product/movements link отсутствует.

### F

- `B05-F01` — `FAIL_UX`: Movements route отсутствует в nav.
- `B05-F02` — `FRICTION`: direct route открыт, populated только после manual refresh.
- `B05-F03` — `PASS`: exact A rows найдены.
- `B05-F04` — `PASS`: exact B rows найдены.
- `B05-F05` — `FAIL_PROCESS`: signs видны, но B04 pair/№000007/from-to доказать нельзя.
- `B05-F06` — `FAIL_UX`: raw English enums.
- `B05-F07` — `FAIL_PROCESS`: timestamp отсутствует.
- `B05-F08` — `FAIL_PROCESS`: source/destination warehouse/cell отсутствуют.
- `B05-F09` — `FAIL_PROCESS`: request/document отсутствует.
- `B05-F10` — `FAIL_PROCESS`: seller/actor/reason отсутствуют.
- `B05-F11` — `FAIL_PROCESS`: resulting balance отсутствует.
- `B05-F12` — `FAIL_PROCESS`: transfer pair/group relation отсутствует.
- `B05-F13` — `FAIL_UX`: row detail/click отсутствует.
- `B05-F14` — `FAIL_UX`: row keyboard affordance отсутствует.
- `B05-F15` — `FAIL_UX`: search/filter/sort отсутствуют.
- `B05-F16` — `FAIL_UX`: 80-row limit без older/pagination control.
- `B05-F17` — `FRICTION`: refresh работает, visible success/loading feedback нет.
- `B05-F18` — `FAIL_PROCESS`: reload визуально теряет populated history до refresh.
- `B05-F19` — `NOT_RUN`: Back/Forward на movements отдельно не прогонялись.
- `B05-F20` — `PASS`: safe digest один раз, done/132.
- `B05-F21` — `NOT_RUN`: initial empty зафиксирован, application error/loading не провоцировались.
- `B05-F22` — `FAIL_UX`: near-black-on-dark на 1280/wide.
- `B05-F23` — `FAIL_PROCESS`: explain-delta job не завершается.

### G

- `B05-G01` — `FAIL_UX`: Transfers route отсутствует в nav.
- `B05-G02` — `PASS`: direct route открыт.
- `B05-G03` — `PASS`: purpose/consequence copy прочитано.
- `B05-G04` — `FAIL_UX`: source показывает cell без warehouse, raw Sorting.
- `B05-G05` — `FAIL_UX`: destination показывает cell без warehouse, raw Sorting.
- `B05-G06` — `FAIL_UX`: flat non-searchable dropdown 211 products.
- `B05-G07` — `FAIL_UX`: integer/positive/available guard до submit не виден.
- `B05-G08` — `FAIL_PROCESS`: current source balance отсутствует.
- `B05-G09` — `FAIL_PROCESS`: summary/confirm отсутствует.
- `B05-G10` — `FAIL_UX`: scanner-first path отсутствует.
- `B05-G11` — `FRICTION`: native selects keyboardable, но 211-product list непрактичен.
- `B05-G12` — `FAIL_UX`: cancel/clear/dirty warning отсутствуют.
- `B05-G13` — `BLOCKED_FIXTURE`: только одна exact storage-cell.
- `B05-G14` — `BLOCKED_FIXTURE`: safe reverse path не доказан.
- `B05-G15` — `BLOCKED_FIXTURE`: mutation не выполнялась по gate.
- `B05-G16` — `BLOCKED_FIXTURE`: server invalid/cross/overage не заявлены без safe mutation fixture.

### H

- `B05-H01` — `PASS`: nav открывает inventory.
- `B05-H02` — `PASS`: placeholder визуально зафиксирован.
- `B05-H03` — `FAIL_PROCESS`: create task отсутствует.
- `B05-H04` — `FAIL_PROCESS`: warehouse/cell scope отсутствует.
- `B05-H05` — `FAIL_PROCESS`: expected/count sheet отсутствует.
- `B05-H06` — `FAIL_PROCESS`: scanner/product input отсутствует.
- `B05-H07` — `FAIL_PROCESS`: blind count/recount отсутствует.
- `B05-H08` — `FAIL_PROCESS`: delta/reason/approval отсутствуют.
- `B05-H09` — `FAIL_PROCESS`: posting/double protection отсутствуют.
- `B05-H10` — `FAIL_PROCESS`: draft/reload/resume отсутствуют.
- `B05-H11` — `FAIL_PROCESS`: history/audit отсутствуют.
- `B05-H12` — `FAIL_PROCESS`: error/recovery/help/next отсутствуют.
- `B05-H13` — `FAIL_UX`: keyboard/scanner path отсутствует.
- `B05-H14` — `PASS`: reload сохраняет placeholder route.
- `B05-H15` — `PASS`: Back/Forward работают.
- `B05-H16` — `BLOCKED_ENV`: оба runtime проверены, exact 1920px export недоступен.
- `B05-H17` — `PASS`: adjudicated именно `FAIL_PROCESS`, не `NOT_RUN`.

### I

- `B05-I01` — `PASS`: find-stock = 4 inputs / 5 shifts.
- `B05-I02` — `PASS`: locate-product = 6 inputs / 8+ shifts, без завершения.
- `B05-I03` — `PASS`: explain-delta = hidden route + 2 controls / 6+ shifts, без ответа.
- `B05-I04` — `PASS`: inventory = 1 input / 2 shifts, затем stop.
- `B05-I05` — `PASS`: minimal linked catalog/movements/cell-first inventory flow описан.
- `B05-I06` — `PASS`: functional false-empty/guards отделены от UX/process gaps.
- `B05-I07` — `PASS`: 148/148 ID имеют final verdict.
- `B05-I08` — `PASS`: 54/54 PNG лично открыты.
- `B05-I09` — `PASS`: 54/54 PNG имеют отдельный verdict.
- `B05-I10` — `PASS`: runtime/file dimensions записаны отдельно.
- `B05-I11` — `PASS`: sanitized state/network log создан без secrets/raw bodies.
- `B05-I12` — `PASS`: final read-back A3/B2 совпал с baseline.
- `B05-I13` — `PASS`: application code не менялся.
- `B05-I14` — `PASS`: B06 не начат; handoff только B05.
- `B05-I15` — `PASS`: evidence `ACCEPTED`, product `STOP`.

## Exact counts

- Всего: **148/148 adjudicated**.
- Полностью исполнено: **133/148**.
- `PASS`: **65**.
- `FRICTION`: **10**.
- `FAIL_PROCESS`: **29**.
- `FAIL_UX`: **29**.
- `BLOCKED_FIXTURE`: **4**.
- `BLOCKED_ENV`: **3**.
- `NOT_RUN`: **7**.
- `N/A`: **1**.
