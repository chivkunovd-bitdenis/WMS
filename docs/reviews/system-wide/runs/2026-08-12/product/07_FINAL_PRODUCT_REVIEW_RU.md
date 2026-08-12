# Итоговое продуктовое ревью WMS

## Короткий вывод

На проверенном staging работают базовые оболочки FF и seller portal, создание складской структуры и жизненный цикл пустых черновиков. Но продукт нельзя считать проверенным как полноценную WMS: основной пункт `Инвентаризация` ведёт в заглушку, seller CTA акта расхождений обещает несуществующий результат, а физические процессы с товаром — приёмка, раскладка, упаковка, ЧЗ, отгрузка и полный FBS — не были пройдены в isolated dataset. Это не отрицательная оценка скрытой реализации; это честная граница evidence.

Runtime Browser относится к Railway revision `44fe72e`. Эталон static-аудита — `a39530c`; они не совпадают. Отдельный worker deployment отсутствует, schema revision напрямую не опубликована. Поэтому runtime findings и static candidates в отчёте не смешиваются.

## Как проводилась проверка

Оркестратор выполнил реальные клики в staging Browser по независимому продуктовому чек-листу. Я лично открыл через `view_image` каждый из 59 переданных screenshots и независимо оценил смысл действия, следующий физический шаг, пустые/ошибочные состояния, визуальный шум и тупики. Stable desktop batch подтверждён значениями `innerWidth=1920`, `innerHeight=1080`, `devicePixelRatio=1`; ключевые destinations также сняты в 1280×720. Transitional captures не использовались для layout verdict.

JSX, route inventory и API использовались только чтобы объяснить увиденное или сформировать `STATIC_CONTRACT_MISMATCH`. Экран без изображения остаётся `NOT_RUN`.

## Что реально работает по evidence

Самый полный workflow — справочник склада: isolated warehouse и две физические ячейки созданы через формы, затем после reload и повторного выбора склада обе ячейки, их barcodes и virtual `Сортировка` снова видны. Это настоящий durable result.

Черновики тоже ведут себя последовательно:

- FF создал пустую MP-отгрузку, открыл detail, после reload увидел её в списке, повторно открыл, а seller увидел тот же документ;
- seller сохранил inbound draft с датой и планом коробов, но без товаров, и увидел строку `Поставка / Черновик / 0` в Documents;
- manual product create с пустым обязательным seller корректно остановился на native validation, сохранил введённые поля в dialog и не создал ложный товар после reload.

Пустые черновики не объявлены дефектом: действующие сценарии прямо разрешают draft до добавления строк/склада WB; реальные guards должны оцениваться на submit/plan, которые не выполнялись.

FBS navigation соответствует утверждённой структуре на уровне пустых экранов: реально нажаты `Новые`, `В работе`, `В доставке`, `Завершённые`, `Отменённые`, затем `Остатки WB`; reload сохранил Stocks tab. Populated orders и supply stages отсутствовали, поэтому физическая сборка не засчитана.

## Подтверждённые проблемы

### P1 — основной складской процесс отсутствует

`Инвентаризация` присутствует в главном меню как рабочий раздел, но оба реальных desktop прохода открывают только `Раздел в разработке`. Оператор не может создать пересчёт, зафиксировать расхождение или провести результат. До реализации честный минимальный вариант — не выдавать заглушку за рабочий модуль и явно обозначить недоступность; для полноценной WMS сам процесс остаётся обязательным.

### P1 — акт расхождений seller является ложным CTA

Реальный клик по `Создать акт расхождений` возвращает error alert `будет реализован ... на следующем этапе`. Кнопка обещает бизнес-документ, но служит заглушкой. Минимальное решение: либо реализовать документ, либо убрать/disable CTA с честным пояснением до релиза. Ошибка после клика создаёт ложное ожидание и внешний ручной канал.

### P1 — выключение адресного хранения слишком опасно для одного checkbox

Settings показывает обычный checkbox. На baseline его выключение сразу переносит все ненулевые остатки из адресных ячеек в `Сортировку`, а обратное включение не восстанавливает прежнее размещение автоматически. Минимальное исправление — один confirmation dialog до PATCH: что именно будет перенесено и что автоматического возврата нет. Mutation в staging намеренно не выполнялась из-за массового воздействия.

### P1 security handoff — release keystore находится в Git

Mobile release signing artifact отслеживается Git как обычный readable file, а release build config на него ссылается. Ключ не использовался, не экспортировался и не исследовался. Это передано security review; конкретные secret operations не входят в продуктовый аудит.

### P2 — dashboard показывает внутренний `submitted`

В пользовательском тексте виден технический token `Статус «submitted»`. Он не отвечает оператору, что делать дальше. Достаточно отображать утверждённое русское бизнес-состояние; новый status model не нужен.

## Что сначала воспроизвести, а не чинить вслепую

На static baseline dashboard MP callback строит `/app/ff/ff/mp-shipments`, но synthetic dashboard не имел строки для клика, а staging revision другая. Это точный static candidate, не runtime finding. Аналогично дизайн ЧЗ обещает доступ FF-staff, тогда как baseline nav/API оставляют его admin; нужен реальный staff-role проход.

Короткие FBS packing labels, mobile `markLabelPrinted`, перегруженность populated catalog, общий FBS packing counter и отсутствие полного billing route также оставлены candidates. Ни один из них не повышен до визуального дефекта без нужного состояния.

## Что не проверено

Ни один физический товар в synthetic tenant не был принят, пересчитан, отсканирован, разложен, упакован, промаркирован или отгружен. Поэтому остаются `NOT_RUN`:

- inbound boxes/recount/discrepancy/posting и partial progress;
- sorting scan/manual placement и восстановление после ошибки;
- packaging task, print/reprint/defect, ЧЗ shortage и completion;
- MP products, plan, packaging, boxes, confirmation, ship/cancel;
- FBS selection/preflight, `Состав → Подбор → Упаковка и маркировка → Короба`, оба маршрута и deliver;
- Honest Sign upload/pools/ledger/reprints под FF и seller;
- notifications, legacy movements/transfers, billing/background status;
- весь mobile runtime на устройстве.

Live WB pull/export/bindings/stock sync, credential forms, shared-stock changes и fault injection без fixture имеют `BLOCKED`, а не `NOT_RUN`. Это сознательная защита внешних данных и секретов.

## Приоритет следующего прохода

1. Исправить четыре подтверждённых P1 с минимальным UX-объёмом: inventory honesty/flow, discrepancy CTA, address-storage confirmation, security handling keystore.
2. На isolated synthetic товаре пройти один сквозной seller inbound: draft → submit → FF boxes/recount → sorting → packaging → stock, включая failure и reload каждого irreversible шага.
3. На отдельном synthetic FBS order set пройти обе route variants и print/marking/box states без live WB side effects через fixture.
4. Добавить FF-staff credential и mobile device evidence; только после этого решать static role/mobile candidates.

## Состояние test data и ограничения handoff

В staging остались synthetic objects, показанные на screenshots: warehouse `Review Warehouse 687943`, две `REV-A` cells, один FF MP draft и один seller inbound draft. Отдельного cleanup screenshot/подтверждения не передано, поэтому cleanup не заявляется. Удалять их в рамках продуктового review без доказанного recovery не стали.

Полная детализация находится в `04_SCENARIO_MATRIX_RU.md`, `05_SCREENSHOT_MANIFEST_RU.md` и `06_FINDINGS_REGISTER_RU.md`.
