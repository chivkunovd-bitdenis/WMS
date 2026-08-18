# Батч 04. Handoff оркестратору

## Короткий ответ

Сортировка №000007 **функционально завершена и прочитана обратно**, но UX процесса не готов к самостоятельной массовой работе сортировщика. Пять единиц сохранились без потерь: baseline Sorting3/2, partial A1, final Sorting0, cells/available3/2. Double-click не создал дублей, чужие warehouse cells и системная Sorting cell выбрать нельзя.

Основной стоп — экран требует мышь+клавиатуру и не имеет scanner-flow ни для ячейки, ни для товара. На 1280 simple happy path занимает 13 input events и 10 attention shifts; сотрудник должен помнить warehouse/seller, различать не объяснённые Save/Apply и угадывать, что слово `Разложено` одновременно считает черновик и уже проведённый stock.

## Что реально выполнено

- Настоящий in-app Browser на Railway staging; runtime viewports 1280×720 DPR1 и 1920×1080 DPR1. Wide exports физически 1873×1080, поэтому exact 1920px PNG не заявлен.
- Exact request доказан seller/remaining/date в queue, №000007 и A3/B2 в detail.
- До первой мутации доказаны baseline stock и exact destination isolation.
- Проверены cell directory, dropdown, отсутствие scanner/manual cell input, missing cell, zero, negative visual guard, decimal, overage, valid draft, Save/double-click, reload/reopen, dirty Close, Back/Forward, dirty reload, add/remove cell row.
- Проведён partial Apply A=1, затем reload/queue/stock read-back.
- Проведён final Apply A=2+B=2, double-click protection, terminal state, queue removal, reload, dashboard status, final stock и cell-directory traceability.
- Сохранено **54 PNG**, лично открыто `view_image`: **54/54**; у каждого есть отдельный visual verdict.
- Checklist: **102/102 adjudicated**, **91/102 полностью исполнены**. Неисполненные не скрыты: 3 `BLOCKED_FIXTURE`, 2 `BLOCKED_ENV`, 6 `N/A`.

## Checklist counts

- `PASS`: **53**.
- `FRICTION`: **10**.
- `FAIL_PROCESS`: **5**.
- `FAIL_UX`: **23**.
- `BLOCKED_FIXTURE`: **3**.
- `BLOCKED_ENV`: **2**.
- `N/A`: **6**.

## Главный UX verdict

Fresh one-cell path на 1280: **13 input events** = 9 clicks + 2 quantity entries + 2 scroll gestures; **10 attention shifts**; scanner events0. На 1920: **11 input events**, **8 attention shifts**. Технически путь короткий, операционно он рваный: queue→memory→dropdown→keyboard→scroll→dropdown→keyboard→scroll→CTA.

Минимальный идеальный путь в тех же экранах: click Sorting, click/Enter exact row, scan cell, пять product scans, один final click. Это **9 events** и **6 attention shifts**. Dropdown+qty остаются fallback; новый wizard, микросервис или тотальный redesign не нужны.

## Product stop-gates

1. Нет scanner-flow cell barcode→current destination и product barcode→+1.
2. Queue не показывает №/warehouse, использует raw status и mouse-only row; detail теряет seller/warehouse.
3. `Разложено` смешивает draft и posted; после partial сотрудник видит противоречащие друг другу progress numbers.
4. Save/Apply не объясняют последствия; Save без feedback, Apply без summary/confirm.
5. Missing cell и zero молча исчезают; decimal1.9 молча становится1; negative -1 не получает inline guard.
6. Close/Back/reload теряют dirty work без warning; reload закрывает документ.
7. Completed UI не показывает per-cell SKU/qty; supervisor не может ответить «куда положили».
8. Таблицы требуют horizontal/inner scroll даже на wide desktop.

## Что работает

- Exact warehouse filtering корректен: чужие cells и system Sorting не доступны.
- Overage блокирует mutation.
- Save не двигает stock и durable после reload.
- Partial Apply durable и сохраняет conservation.
- Double-click Save/partial Apply/final Apply не дал duplicate movement.
- Final state: Sorting0, cells/available A3/B2, total5 сохранён.
- Completed request убран из Sorting и после reload остаётся `Оприходовано` в Dashboard.

## Final staging state для следующего batch

- Request ID: `41823675-2b08-4714-97b6-8782486c4dda`.
- Документ: №`000007`, seller `B01 UX Seller 960724`.
- Status: `done`/UI `Оприходовано`.
- Sorting queue: exact row отсутствует до и после reload.
- Accepted/final stock: A=`3`, B=`2`.
- FF Sorting: A=`0`, B=`0`.
- FF cells: A=`3`, B=`2`.
- FF available: A=`3`, B=`2`.
- Destination использован: warehouse `FBS WB 1155120`, cell `A 1.1` (`LOC-36F984B31C3D`).
- Per-cell A/B balance из UI не читается; only aggregate cells/available доказан.
- Boxes не создавались.

## Fixture drift и граница B05

`Review Warehouse` в connected tenant отсутствует. В exact warehouse только одна storage cell A 1.1, поэтому two-cell split получил честный `BLOCKED_FIXTURE`; чужие cells warehouse `Тестовый` не использовались. B05 не запускался. Следующий reviewer не должен ожидать status `sorting`: exact request уже terminal done и stock available3/2.

## Gate

Формальный evidence gate B04: **`ACCEPTED`** — 102/102 ID adjudicated, 54/54 PNG лично просмотрены, exact mutations прочитаны обратно, fixture gaps, loading-кадры и IAB wide-export limitation не выданы за PASS.

Продуктовый gate: **`STOP` перед самостоятельным массовым пилотом**. Это не отменяет функционально корректный final stock; stop относится к scanner ergonomics, semantic clarity, recovery и traceability.

## Git boundary

B04 не менял application code, не выполнял commit/push и не откатывал чужие изменения. Созданы только review docs/evidence в общей review-ветке. По прямому поручению reviewer не коммитит; оркестратор должен включить эти материалы в итоговый scoped review commit.
