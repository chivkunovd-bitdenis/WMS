# Батч 06. Карта процесса FF-упаковки и заданий на упаковку

## Граница и исходное состояние

B06 проверяет только самостоятельную FF-упаковку на Railway staging: очередь `/app/ff/packaging`, ручное создание задания из складского места, карточку задания, ТЗ товара, маркировочный/печатный вход, прогресс, завершение, отмену и очередь «Осталось промаркировать». Связанная упаковка внутри отгрузки на МП инвентаризируется только как переход следующей роли и не исполняется: полный MP-процесс относится к B07. FBS, WB, реальные КМ, чужие tenants и credential operations не затрагиваются.

Перед первым кликом B06 принимает только как гипотезу переданный B05 fixture, который обязан быть перечитан глазами:

- seller `B01 UX Seller 960724`;
- warehouse `FBS WB 1155120`, storage-cell `A 1.1`, barcode `LOC-36F984B31C3D`;
- A: total/cells/available `3/3/3`, Sorting `0`, сохранённое ТЗ и признак ЧЗ;
- B: total/cells/available `2/2/2`, Sorting `0`, без подтверждённого требования ЧЗ;
- request №`000007` terminal `done`;
- неизвестно до живого экрана: open packaging queue, packed/unpacked split A/B, наличие доступных КМ и существующих packaging tasks.

Разрешены только изолированные synthetic mutations в том же tenant и storage-cell. Перед проводкой упаковки отдельно проверяются исходный split и отсутствие внешней связи. Cancel выполняется на отдельном новом manual task без прогресса. Завершение допускается только на малом количестве товара без ЧЗ, если UI однозначно показывает товар, место и последствия; после него обязательны reload/read-back задания, очереди и остатков. Необратимая смена `unpacked→packed` не маскируется как rollback: если обратного UI нет, финальный split явно передаётся B07.

## Физический смысл процесса

Задание на упаковку — не документ приёмки и не отгрузка. Оно говорит упаковщику: из какого физического места взять конкретный SKU, сколько единиц обработать, по какому ТЗ, нужна ли маркировка и что будет считаться завершённым. При выполнении товар остаётся в той же ячейке, но его состояние меняется с `не упаковано` на `упаковано`. Количество on-hand не должно изменяться.

Система должна поддержать поток, в котором сотрудник стоит у стола/ячейки с товаром и сканером, а не сидит за офисным компьютером. Каждый scan или ручное действие обязано давать немедленное и однозначное подтверждение: какой товар принят, сколько осталось, где находится физическая единица и что делать дальше.

## Роли и передачи работы

| Роль | Что знает на входе | Физическая задача | Нужный выход и следующая роль |
|---|---|---|---|
| Старший смены | seller, склад, место, приоритет, требуемое количество | Создать одно задание на доступный неупакованный остаток и назначить понятный объём | Упаковщик видит стабильный номер, место, SKU, количество, ТЗ и приоритет без устного объяснения |
| Упаковщик | Номер задания/очередь, физическое место, товар и упаковочные материалы | Взять товар, сверить SKU/ШК, выполнить ТЗ, при необходимости напечатать/нанести КМ, фиксировать каждую единицу | В строке виден доказуемый прогресс; товар остаётся в месте, но `unpacked↓`, `packed↑` |
| Контролёр/старший | Завершённое или проблемное задание | Проверить кто/что/сколько упаковал, обработать ошибку, повтор/брак и отмену | Durable task/document state и объяснимый остаток; для MP — разрешён следующий этап |
| Сотрудник отгрузки B07 | Связанная отгрузка и её packaging gate | Получить выполненное задание, точный прогресс и отсутствие незакрытых КМ | Может продолжить короб/подтверждение без повторного пересчёта и нового задания |

## AS-IS цепочка, которую нужно проверить

1. Открыть навигацию `Упаковка` и дождаться settled queue. Empty state доказывает только отсутствие открытых заданий.
2. Открыть `Создать задание`, выбрать warehouse и storage place. Система показывает только неупакованный остаток этого места.
3. Сверить seller/product identity, SKU/ШК, ТЗ, признак ЧЗ, `Неупаковано` и предлагаемое `В задание`.
4. Проверить выбор строк и количество: blank, zero, negative, decimal, overage, text, deselect/reselect и recovery. Неверное значение не должно молча округляться или исчезать.
5. Проверить Cancel/Close/reload/back до создания: никакого скрытого task/reservation.
6. Создать отдельное cancel-task с минимальным synthetic quantity; проверить double-click/идемпотентность, стабильный номер и появление в populated queue.
7. Открыть карточку: warehouse/place, seller, product, ТЗ, ЧЗ, всего/на полке/упаковать/готово и следующий физический шаг должны читаться без догадок.
8. Проверить `Отменить задание`: предупреждение с точным последствием, cancel recovery, повтор, reload, исчезновение из open queue и неизменность stock split.
9. Создать отдельное completion-task на минимальном количестве товара без ЧЗ. Проверить, что новый task не резервирует или не меняет packed/unpacked до фактической упаковки.
10. Выполнить одну строку, проверить feedback, partial status, reload/close/reopen, повторный click и conservation. Scanner/manual `+N` проверяются, если controls существуют; отсутствующие поверхности получают `FAIL_PROCESS/N/A`, а не вымышленные тесты.
11. Для строки с ЧЗ безопасно открыть preview/dialog и отменить до фактической печати. Unknown/empty pool, повтор, брак и очередь pending-marking проверяются только без создания реального/внешнего КМ.
12. Завершить валидное non-ЧЗ задание, проверить double-click, terminal read-only, отсутствие повторной проводки, queue removal и final stock/task/document read-back.
13. Проверить browser Back/Forward, reload, dirty/loaded recovery, keyboard focus и доступность row actions.
14. Передать B07 точный final split, task numbers/IDs, остаток и честный список того, что не доказано.

## Инвентарь экранов и действий

- `/app/ff/packaging`: loader/settled empty/populated queue, columns, row open, keyboard, create CTA, pending-marking badge/link, reload, back/forward, 1280 and wide.
- Create dialog: warehouse, location, sorting/system location, product rows, identity, print/TЗ affordance, selection, quantity variants, empty place, cancel/close, Create, double-click, backend errors.
- Task panel: number/status/link/context, line identity/location/TЗ, totals/progress/ЧЗ, confirm shelf, pack, complete, acknowledge, cancel, close, menu/reprint/defect where applicable, read-only terminal.
- `/app/ff/packaging/pending-marking`: empty/populated, selection, print/reprint affordance, back, reload and safe cancellation before physical print.
- `/app/ff/products`: only final exact A/B packed/unpacked/total read-back if visible; no unrelated catalog mutations.
- `/app/catalog`: only exact place identity/read-back if required; no cell mutation or physical print.

## Правила продуктового verdict

1. Наличие кнопки `Упаковать` не доказывает operator flow. Нужны product scan/manual fallback, количественный feedback и recoverable mistake path.
2. Task identity недостаточна без seller, warehouse, physical place, quantity and instruction. Устная передача этих данных — process failure.
3. `Выполнить` безопасно только после явной сверки последствий и при защите от повторной проводки. Busy-state сам по себе не доказывает серверную идемпотентность.
4. Decimal/blank/zero не могут молча floor/filter до другого business value. Ошибка должна остаться у поля и вернуть focus.
5. Печать считается проверенной только до видимого preview/диалога и безопасной отмены. Наличие CTA не доказывает physical printer, КМ reserve или фактическую этикетку.
6. Empty queue/pending state не доказывает populated workflow. Существующий или созданный synthetic task нужен для populated verdict.
7. После упаковки `total on hand` и place не меняются; только `unpacked↓`, `packed↑`. Без split read-back downstream handoff считается неполным.
8. Cancel без прогресса должен оставить stock неизменным. Cancel после прогресса не выполняется без доказанного rollback contract.
9. Отсутствующий scanner, manual quantity/undo/delete получает прямой verdict; source inventory не заменяет экран.
10. Каждый PNG лично открывается. Runtime viewport и физические размеры файла фиксируются отдельно; имя файла не является доказательством.

## Измеряемые operator flows

Для типового задания считаются clicks/taps, keyboard entries/Enter, scanner events, scroll gestures и attention shifts между экраном, товаром, упаковочным столом, мышью, клавиатурой и сканером:

- старший: `очередь → создать → место → товар/qty → задание`;
- упаковщик: `очередь → exact task → место/SKU/ТЗ → pack unit(s) → complete`;
- recovery: `не тот товар/количество → видимая ошибка → возврат к работе`;
- ЧЗ: `строка → preview/печать → нанесение → подтверждение/брак → complete`.

Минимальный простой поток в существующих сущностях: scan task/location → scan product по единице с крупным `готово/осталось` → автоматический focus назад в scan → один final confirm. Dropdown и ручное количество остаются fallback; новый workflow engine или тотальный редизайн не требуются.
