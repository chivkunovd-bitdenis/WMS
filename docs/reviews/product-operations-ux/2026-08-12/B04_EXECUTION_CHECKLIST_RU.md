# Батч 04. Итоговый exhaustive checklist сортировки и размещения

Статусы здесь относятся к полноте проверки. `PASS` не означает, что весь продуктовый процесс хорош: UX- и process-дефекты вынесены в `B04_FINDINGS_RU.md`. Evidence на каждый выполненный пункт сведён в action ledger и visual adjudication.

## A. Среда, safety и входной state

- [x] `B04-A01` `PASS` — настоящий in-app Browser, существующая FF admin staging-session.
- [x] `B04-A02` `PASS` — 1280×720 DPR1 и CSS viewport 1920×1080 DPR1 измерены runtime; exported wide bytes отдельно не переоценены.
- [x] `B04-A03` `PASS` — baseline `/app/ff/sorting` снят до мутации.
- [x] `B04-A04` `PASS` — exact row доказана seller/lines/remaining/date, не порядком.
- [x] `B04-A05` `PASS` — detail №000007, A=3/B=2; no-box факт унаследован из B03 и подтверждён составом.
- [x] `B04-A06` `PASS` — stock baseline Sorting-only 3/2, cells0, available0.
- [x] `B04-A07` `FRICTION` — `Review Warehouse` в tenant отсутствует; exact target доказан как synthetic `FBS WB 1155120` по единственной доступной A 1.1.
- [x] `B04-A08` `BLOCKED_FIXTURE` — в exact warehouse только одна storage cell A 1.1; две целевые ячейки отсутствуют.
- [x] `B04-A09` `PASS` — до мутации доказано: чужие cells и Sorting buffer в dropdown отсутствуют.

## B. Очередь «Сортировка» и ориентация

- [x] `B04-B01` `PASS` — populated queue и density проверены на 1280.
- [x] `B04-B02` `FAIL_UX` — human number в queue отсутствует.
- [x] `B04-B03` `FAIL_UX` — warehouse в queue отсутствует.
- [x] `B04-B04` `PASS` — seller, lines, remaining, plan/created dates читаются.
- [x] `B04-B05` `FAIL_UX` — raw `sorting`, операторского перевода нет.
- [x] `B04-B06` `FAIL_UX` — row не получает Tab-focus.
- [x] `B04-B07` `FAIL_UX` — Enter/Space row не открывают.
- [x] `B04-B08` `PASS` — один click exact row открыл соответствующий detail.
- [x] `B04-B09` `PASS` — до partial queue reload сохранял remaining5, после partial — remaining4.
- [x] `B04-B10` `N/A` — после финала queue оставалась populated чужими rows; false empty-state не заявлен.

## C. Detail и визуальная модель задания

- [x] `B04-C01` `PASS` — процесс и №000007 видны.
- [x] `B04-C02` `FAIL_UX` — seller после открытия теряется.
- [x] `B04-C03` `FAIL_UX` — warehouse name/code после открытия теряются.
- [x] `B04-C04` `FRICTION` — accepted3/2 и total5 видны, но compact A/B progress нет.
- [x] `B04-C05` `FAIL_UX` — на 1280 product cards обрезают правые progress columns и требуют внутреннего scroll.
- [x] `B04-C06` `FAIL_PROCESS` — draft уже входит в `Разложено`, тогда как серверный remaining ещё не изменился.
- [x] `B04-C07` `PASS` — source `Россыпь` явно подписан.
- [x] `B04-C08` `FRICTION` — следующий шаг достижим, но Save и Apply конкурируют как CTA.
- [x] `B04-C09` `FAIL_UX` — смысл и последствия Save/Apply не объяснены.
- [x] `B04-C10` `BLOCKED_ENV` — runtime CSS viewport был 1920×1080 DPR1, но IAB export физически 1873×1080; wide comparison выполнен, exact 1920px PNG не заявлен.

## D. Cell directory и выбор назначения

- [x] `B04-D01` `FRICTION` — «Ячейки» есть в sidebar, но sorting не ведёт туда по контекстной ссылке.
- [x] `B04-D02` `PASS` — exact warehouse доказан в cell directory.
- [x] `B04-D03` `PASS` — A 1.1 и barcode LOC-36F984B31C3D видны.
- [x] `B04-D04` `FRICTION` — `Сортировка` отличима отсутствием barcode, но не маркирована как системная/запрещённая.
- [x] `B04-D05` `PASS` — dropdown содержит только exact A 1.1.
- [x] `B04-D06` `PASS` — cells warehouse `Тестовый` отсутствуют.
- [x] `B04-D07` `PASS` — Sorting buffer отсутствует как destination.
- [x] `B04-D08` `FAIL_UX` — manual cell code/barcode input отсутствует.
- [x] `B04-D09` `FAIL_UX` — scanner cell flow отсутствует.
- [x] `B04-D10` `N/A` — unknown cell невозможно ввести через UI; mutation невозможна по дизайну control.
- [x] `B04-D11` `N/A` — wrong-warehouse cell невозможно ввести/выбрать; dropdown уже ограничен.
- [x] `B04-D12` `PASS` — выбор A 1.1 остаётся внутри правильной product card.
- [x] `B04-D13` `BLOCKED_FIXTURE` — второй target отсутствует; повторный поиск товара отдельно не проверяем.

## E. Quantity и draft validation

- [x] `B04-E01` `FAIL_UX` — blank/неполная row молча очищается Save.
- [x] `B04-E02` `FAIL_UX` — zero молча игнорируется/очищается без feedback.
- [x] `B04-E03` `FAIL_PROCESS` — поле визуально принимает -1 без inline guard; server-save отрицательного значения отдельно не выдаётся за выполненный.
- [x] `B04-E04` `FAIL_PROCESS` — 1.9 молча превращается в 1 и сохраняется.
- [x] `B04-E05` `FRICTION` — overage4 блокирует обе CTA красным control, но не объясняет максимум/причину текстом.
- [x] `B04-E06` `FAIL_PROCESS` — positive qty без cell входит в summary, затем silently discarded.
- [x] `B04-E07` `PASS` — valid A=1 accepted/durable в draft.
- [x] `B04-E08` `FAIL_UX` — product barcode scan/+1 flow отсутствует.
- [x] `B04-E09` `N/A` — unknown product scan невозможен: scanner control нет.
- [x] `B04-E10` `N/A` — repeat scan semantics отсутствуют вместе со scanner flow.
- [x] `B04-E11` `PASS` — add-cell создаёт одну дополнительную row.
- [x] `B04-E12` `PASS` — double-click видимо оставил ровно одну дополнительную row.
- [x] `B04-E13` `FRICTION` — remove recovery работает, но маленький `×` без подписи/Undo.

## F. Save draft, cancel/back/reload

- [x] `B04-F01` `FAIL_UX` — Save не даёт success/dirty-saved indicator.
- [x] `B04-F02` `PASS` — Save не двигает stock из Sorting.
- [x] `B04-F03` `PASS` — reopen после reload восстанавливает saved A1.1=1.
- [x] `B04-F04` `FAIL_UX` — Close dirty без warning теряет 2 и возвращает saved1.
- [x] `B04-F05` `PASS` — reopen показывает saved, не unsaved state.
- [x] `B04-F06` `FAIL_UX` — Back меняет underlying route, оставляет dialog и теряет dirty-state.
- [x] `B04-F07` `FAIL_UX` — Forward снова меняет route при визуально том же dialog.
- [x] `B04-F08` `FAIL_UX` — reload dirty без warning закрывает detail; нужен повторный поиск.
- [x] `B04-F09` `PASS` — Save double-click не дал duplicate draft row/version в read-back.

## G. Частичное применение и stock conservation

- [x] `B04-G01` `PASS` — безопасный partial A=1 в exact A 1.1.
- [x] `B04-G02` `FAIL_UX` — Apply не подтверждает consequence и сразу двигает stock.
- [x] `B04-G03` `PASS` — detail: total remaining4, A distributed1.
- [x] `B04-G04` `PASS` — double-click Apply провёл одну единицу.
- [x] `B04-G05` `PASS` — reopen сохраняет partial progress.
- [x] `B04-G06` `PASS` — queue reload показывает remaining4.
- [x] `B04-G07` `PASS` — A: total3, Sorting2, cells1, available1.
- [x] `B04-G08` `PASS` — B: total2, Sorting2, cells0, available0.
- [x] `B04-G09` `FRICTION` — continuation доступен через `+ ячейка`, но posted и new rows визуально не различены.
- [x] `B04-G10` `FRICTION` — duplicate stock не возник, однако защита понятна только после read-back, не из row semantics.

## H. Split и полное размещение

- [x] `B04-H01` `BLOCKED_FIXTURE` — remaining A=2 размещён в той же A 1.1; split по второй cell невозможен.
- [x] `B04-H02` `PASS` — B=2 размещён в доказанную A 1.1.
- [x] `B04-H03` `FAIL_PROCESS` — draft summary A=3 при серверном total remaining4 смешивает posted и draft.
- [x] `B04-H04` `FRICTION` — final Apply один primary action, но нет confirm/итогового A+B preview.
- [x] `B04-H05` `PASS` — final double-click не создал duplicate movement.
- [x] `B04-H06` `PASS` — terminal success, remaining0, `Оприходовано`.
- [x] `B04-H07` `PASS` — Apply исчез/controls locked после completion.
- [x] `B04-H08` `PASS` — final done durable через Dashboard reload/read-back.
- [x] `B04-H09` `PASS` — Close возвращает populated Sorting queue.
- [x] `B04-H10` `PASS` — exact seller absent до/после queue reload.
- [x] `B04-H11` `N/A` — другие rows остались, true empty state не возник.

## I. Финальный read-back и handoff

- [x] `B04-I01` `PASS` — A total3, Sorting0, cells3, available3.
- [x] `B04-I02` `PASS` — B total2, Sorting0, cells2, available2.
- [x] `B04-I03` `FAIL_UX` — cell directory не показывает SKU/балансы; per-cell exact read-back недоступен.
- [x] `B04-I04` `PASS` — conservation total5 до/после доказана.
- [x] `B04-I05` `FAIL_UX` — 1280 stock требует horizontal attention shift identity↔zones.
- [x] `B04-I06` `BLOCKED_ENV` — final numeric wide read-back выполнен при runtime 1920×1080 DPR1, но exported bytes 1873×1080.
- [x] `B04-I07` `FAIL_UX` — terminal UI не объясняет следующий физический шаг/роль и не даёт cell trace.
- [x] `B04-I08` `PASS` — application code не менялся; B05 не начат.

## J. Evidence и gate

- [x] `B04-J01` `PASS` — 54 PNG покрывают baseline, mutation, partial/final и reload/read-back.
- [x] `B04-J02` `PASS` — 54/54 PNG лично открыты через `view_image`.
- [x] `B04-J03` `PASS` — у 54/54 PNG есть отдельный visual verdict.
- [x] `B04-J04` `PASS` — AS-IS input/attention counts зафиксированы.
- [x] `B04-J05` `PASS` — минимальный scanner-first ideal flow сформулирован без нового workflow.
- [x] `B04-J06` `PASS` — UX findings отделены от functional defects и fixture gaps.
- [x] `B04-J07` `PASS` — 102/102 строк имеют конечный статус.
- [x] `B04-J08` `PASS` — final done/stock state передан без запуска B05.
- [x] `B04-J09` `PASS` — evidence gate `ACCEPTED`; product pilot verdict отдельно `STOP`.

## Счётчик

Счётчик ниже сгенерирован после финальной сверки всех 102 ID; `BLOCKED_FIXTURE` и `N/A` не выданы за выполненный позитивный результат.

- Всего строк: `102`.
- Adjudicated: `102/102`.
- `PASS`: `53`.
- `FRICTION`: `10`.
- `FAIL_PROCESS`: `5`.
- `FAIL_UX`: `23`.
- `BLOCKED_FIXTURE`: `3`.
- `BLOCKED_ENV`: `2`.
- `N/A`: `6`.
- PNG сохранено/лично просмотрено: `54/54`.
- Evidence gate: `ACCEPTED`.
- Product gate: `STOP` перед самостоятельным массовым пилотом.
