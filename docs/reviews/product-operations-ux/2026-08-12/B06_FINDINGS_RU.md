# Батч 06. Подтверждённые продуктовые проблемы FF-упаковки

## Жёсткий продуктовый verdict

Техническое ядро упаковки работает: manual task создаётся ровно один раз, create сам не меняет stock, pack переводит одну единицу `unpacked→packed` в той же ячейке, reload сохраняет progress, complete double-click не дублирует движение, а total/cell/available сохраняются. Но как самостоятельное рабочее место реального упаковщика процесс **не готов к массовому складу**. Очередь не говорит, чью и где лежащую работу взять; create автоматически включает все товары ячейки разных seller; сохранённое ТЗ до упаковщика не доходит; scanner/unit flow отсутствует; выполненный документ после reload исчезает из доступного UI.

## B06-F01 — очередь не позволяет выбрать физически правильное задание

**Процесс:** старший смены назначает работу, упаковщик берёт следующее задание. **Severity:** P0/P1. **Verdict:** `FAIL_PROCESS`.

В populated queue из 11 задач видны только номер, статус, число строк и признак связи с отгрузкой `Да/—`. Seller, warehouse, cell, товар, единицы, progress и возраст задания отсутствуют. Строки mouse-only (`tabIndex=-1`). Несколько черновиков на 1–2 строки выглядят одинаково; сотрудник должен открывать их по очереди и держать контекст в памяти.

Evidence: `b06-004`, `b06-020`, `b06-023`; runtime accessibility read.

**Почему это важно и ценность изменения:** на поточном участке неправильный task означает, что сотрудник подходит не к той ячейке, обрабатывает не того seller или тормозит линию устными уточнениями. Исправление уменьшает хождение, повторные открытия и риск смешения владельцев.

**Минимальное изменение:** в одной строке queue показать `seller · warehouse/cell · 1–2 SKU · готово/всего`; номер сделать настоящей keyboard-accessible ссылкой. Добавить simple search по номеру/SKU/ШК, без нового dispatcher или redesign.

## B06-F02 — create автоматически выбирает все товары места и может смешать разных seller

**Процесс:** старший создаёт задание из конкретной ячейки. **Severity:** P0. **Verdict:** `FAIL_PROCESS`.

В exact cell A1.1 оказались synthetic A/B seller `B01 UX Seller 960724` и третий shared SKU. Create dialog не показывает seller, но сразу checked **все три строки** и ставит maximum `В задание`. Primary Create активен. Чтобы безопасно создать B1, reviewer должен был помнить владельца вне формы, вручную снять A/shared и изменить qty.

Evidence: `b06-010`; no-selection recovery `b06-011`.

**Почему это важно и ценность изменения:** один пропущенный checkbox создаёт смешанное задание и физически связывает товар разных клиентов одной работой. Для фулфилмента это прямой риск претензии, неверного тарифа и пересорта.

**Минимальное изменение:** стартовать с `unchecked`; показать seller на каждой строке и summary `выбрано N SKU / M единиц / K seller`. Если mixed-seller task не является утверждённым контрактом — блокировать его с конкретным сообщением. Если допустим — требовать отдельное осознанное подтверждение.

## B06-F03 — сохранённое seller-ТЗ не доставлено на рабочее место упаковщика

**Процесс:** упаковщик сверяет пакет/комплектность/этикетку/ЧЗ перед физической операцией. **Severity:** P0. **Verdict:** `FAIL_PROCESS`.

У A в каталоге виден persisted status `Заполнено`; B02 доказал текст ТЗ и marking flag. Но create rows и task panel не показывают ни текст инструкции, ни короткий preview/expand. В task A виден лишь orange state и счётчик ЧЗ, в B — тире. Warehouse и seller также отсутствуют; из физического контекста остаётся только `A 1.1` внутри product label.

Evidence: catalog `b06-002`; task A `b06-012`; task B `b06-019`, `b06-026`.

**Почему это важно и ценность изменения:** система фиксирует факт «упаковано», не проверяя, что работа выполнена по заданию селлера. Результат — неверный пакет, согнутая этикетка, пропущенная комплектность или маркировка, то есть возврат/штраф уже после дорогой downstream-операции.

**Минимальное изменение:** в каждой task line всегда показывать заметный блок `ТЗ: ...` с полным expand/print; рядом `Seller`, `warehouse`, `cell`. Нельзя прятать инструкцию за отдельный переход.

## B06-F04 — рабочего scanner/unit-flow нет; `Упаковать` проводит весь остаток строки

**Процесс:** упаковщик стоит у товара и фиксирует фактические единицы. **Severity:** P0/P1. **Verdict:** `FAIL_PROCESS`.

Task panel не имеет input для task barcode, cell barcode или product barcode; scanner events0. Нет manual `+N`, decrement, undo или исправления. Единственная кнопка `Упаковать` отправляет весь remainder строки. Для B1 это сработало, но для A3 та же кнопка означала бы сразу +3 без поштучного подтверждения. Unknown/repeat/zero/decimal product scan невозможно проверить не потому, что защита хороша, а потому, что поверхности нет.

Evidence: task A `b06-012`; task B before/after `b06-019`, `b06-022`; control inventory runtime.

**Почему это важно и ценность изменения:** интерфейс просит подтвердить плановое количество вместо физического факта. В шуме и при прерывании сотрудник может провести три единицы, обработав две, и у него нет recovery. Scanner-first уменьшает ручные решения и делает факт аудируемым.

**Минимальное изменение:** auto-focused `Сканируйте ШК товара`, каждый valid scan `+1` с крупным `Готово / Осталось`, sound/color feedback, repeat считается следующей физической единицей; unknown/overage блокируются. Рядом оставить `+N` и `Отменить последнее` как fallback, без отдельного wizard.

## B06-F05 — quantity validation меняет business value молча и не возвращает пользователя к ошибке

**Процесс:** старший задаёт объём задания. **Severity:** P1. **Verdict:** `FAIL_UX`.

Qty `1.9` (визуально locale `1,9`) был принят и создал task №000020 с qty1: значение молча floored. Zero, negative и blank не создают task, но Create остаётся active, а один общий banner наверху говорит выбрать «хотя бы один товар» вместо подсветки exact row. Только overage получил содержательную server error.

Evidence: zero `b06-014`, negative `b06-015`, blank `b06-016`, overage `b06-017`, decimal before/after `b06-018`, `b06-019`.

**Почему это важно и ценность изменения:** сотрудник уверен, что передал 1,9/2 единицы или не понимает, почему Create ничего не сделал. Молчаливое изменение количества приводит к неполному заданию и ручной сверке позже.

**Минимальное изменение:** step1 integer input; reject decimal before POST; inline `Введите целое число от 1 до 2` у row, focus туда же; disable Create, пока selected rows invalid. Не фильтровать и не floor молча.

## B06-F06 — на 1280 task нельзя прочитать identity и действие одним взглядом

**Процесс:** упаковщик сверяет SKU/ШК/место, затем фиксирует progress. **Severity:** P1. **Verdict:** `FAIL_UX`.

Task table шире рабочего viewport. В left position видны number, SKU/ШК/name, но progress/action уходят вправо (`b06-026`). В right position видны `Упаковать/Готово/ЧЗ/Действия`, но number, SKU и часть name исчезают (`b06-012`, `b06-019`, `b06-022`). Сотрудник совершает горизонтальный memory join перед необратимой проводкой.

Evidence: `b06-012`, `b06-019`, `b06-022`, `b06-026`; standard 1280×720 DPR1.

**Почему это важно и ценность изменения:** действие выполняется уже без видимой identity товара. Это повышает шанс нажать кнопку в соседней строке и замедляет каждую единицу.

**Минимальное изменение:** для operator workspace оставить fixed `photo + SKU/ШК + short name + place + ready/remaining + main CTA`; vendor/WB identifiers и secondary quantities убрать в expand. Не нужен общий redesign таблиц.

## B06-F07 — завершённый и отменённый task исчезает без доступной истории

**Процесс:** старший проверяет работу, разбирает расхождение и передаёт результат B07. **Severity:** P1. **Verdict:** `FAIL_PROCESS`.

№000020 достиг visible `Выполнено`; terminal panel правильно убрал pack/cancel/complete. Но reload того же route потерял selected document и показал open-only queue, где №000020 отсутствует. Filter/history/direct detail link нет. Technical task ID не виден. Аналогично №000019 после cancel-path отсутствует, поэтому точный результат cancel нельзя открыть повторно.

Evidence: terminal `b06-027`; reload queue `b06-028`; queue before `b06-020`.

**Почему это важно и ценность изменения:** невозможно ответить «кто, когда и сколько упаковал», доказать выполнение seller или восстановиться после случайного Close. B07 не получает durable UI-link на упаковку.

**Минимальное изменение:** tabs `Открытые / Выполненные / Отменённые`, search по №/SKU; stable route `/app/ff/packaging/:id`; terminal card показывает completed time/operator и движения unpacked→packed. Open queue может остаться default.

## B06-F08 — marking queue показывает проблему, но не даёт recovery при pool0

**Процесс:** упаковщик должен напечатать КМ или передать blocker ответственному. **Severity:** P1. **Verdict:** `FAIL_PROCESS`/`FAIL_UX`.

Pending route populated13 и хорошо показывает document/product/place/remain/pool. Но 11 строк с pool0 имеют disabled selection/Print без причины и без next step. Exact A task показывает `дост.0 в пуле`; Create task уже увеличивал badge13→14, но сотрудник не может запросить/импортировать КМ или хотя бы понять владельца blocker. Route также выводит internal `__SORTING__`, тогда как остальной UI говорит `Сортировка`.

Evidence: `b06-005`, selection `b06-006`, safe preview `b06-007`, exact A `b06-012`.

**Почему это важно и ценность изменения:** task зависает между физической упаковкой и complete, а упаковщик вынужден искать руководителя. Видимый blocker без recovery создаёт очередь «вечных» заданий.

**Минимальное изменение:** у pool0 написать `Нет КМ — запросить у seller/ответственного` с owner/CTA в разрешённый existing process; normalise `Сортировка`; link pending row назад в exact task. Не автоматизировать внешний ЧЗ без отдельного product contract.

## B06-F09 — CTA lifecycle конкурируют и не объясняют последствия

**Процесс:** оператор должен отличить факт упаковки от административного завершения. **Severity:** P1. **Verdict:** `FAIL_UX`.

До работы на одной панели одновременно видны `Упаковать`, checkbox `Весь товар уже упакован` и широкая primary-looking `Завершить упаковку`. Premature Complete выдаёт понятную error, но checkbox не объясняет, что может массово признать физическую работу выполненной. Save/Apply нет; progress автоматически проводит stock. Это особенно опасно рядом с all-remainder `Упаковать`.

Evidence: `b06-019`, premature completion `b06-013`, progress `b06-022`.

**Почему это важно и ценность изменения:** низкообученный сотрудник выбирает визуально сильную кнопку вместо физически правильного шага. Система защищает incomplete completion, но предлагает shortcut без пояснения.

**Минимальное изменение:** пока есть remaining, главный CTA только scanner/`Упаковать`; Complete становится enabled после ready; `Весь товар уже упакован` переименовать в `Подтвердить уже упакованный остаток с полки` и показывать exact consequence/quantity.

## Что функционально выдержало проверку

- Create task сам не изменил stock: B remained2 unpacked before pack (`b06-021`).
- Decimal bug aside, double-click Create produced one №000020 (`b06-020`).
- Pack double-click produced one unit, status `В работе`, split B2/0→1/1 in same cell (`b06-022`–`025`).
- Progress survived close, navigation, reload and reopen (`b06-026`).
- Premature complete was blocked with readable error (`b06-013`).
- Complete double-click produced one `Выполнено`, terminal controls became read-only (`b06-027`).
- Final conservation: A total3/unpacked3/packed0; B total2/unpacked1/packed1; Sorting0/0, cells/available3/2 (`b06-029`).
- Marking preview clearly showed exact print formula and was safely closed without print (`b06-007`, `b06-008`).

## Stop-gate

Перед самостоятельным массовым пилотом обязательны F01–F07: correct task selection, seller-safe create, visible ТЗ, scanner/unit fact, strict integer validation, one-glance task and durable history. F08–F09 обязательны до процесса с ЧЗ и плохо обученными упаковщиками.

Неподтверждённая гипотеза о false-empty/loading вынесена из findings: immediate и settled captures оба были populated, а empty fixture отсутствовал. Её нельзя считать продуктовым дефектом без собственного visual outcome.

Ни один finding не требует микросервиса, workflow engine или тотального redesign.
