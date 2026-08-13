# F22 BA/UX: Safe sync остатков WMS -> WB / ЛК селлера

Дата: 2026-08-13, Europe/Moscow.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: isolated Business Analyst / UX Agent.
Статус: `BA_UX_READY`.

Код не редактировался. Этот документ является BA/UX-артефактом для отдельной P0-защитной задачи поверх F08/F10: WMS не имеет права превратить ошибку, неизвестный расчет или отсутствие явного FBS-пула в публикацию `0` в WB/ЛК селлера.

## Короткий продуктовый вывод

Инцидент пользователя: в ЛК WB у товара было `20`, включили синхронизацию, после попытки стало `0`, плюс пользователь увидел ошибку. Для бизнеса это критический сценарий: WMS не просто показала сбой, а могла испортить внешний продающий остаток в WB.

Правильное поведение safe sync: если WMS не может безопасно доказать количество к публикации, она ничего не отправляет в WB. Ошибка, неизвестный ответ WB, пустой расчет, отсутствующая привязка склада или невыделенный FBS-пул не являются нулем. Это стоп-состояния, где пользователь должен увидеть человеческое `не отправлено`, а последний подтвержденный WB-остаток должен остаться последним известным безопасным состоянием.

`0` можно отправить только в отдельном явно утвержденном продуктом сценарии, где WMS доказала, что для этого товара и WB-склада FBS-пул действительно равен нулю, пользователь понимает последствия, WB принял запись, а WMS затем получила readback - повторное чтение из WB, подтверждающее, что WB видит именно отправленное значение.

## Что делаем

Описываем защитный бизнес-контракт для синхронизации FBS-остатков из WMS в WB:

1. Включение sync не должно сразу публиковать `0`, если у WMS нет безопасной основы для числа.
2. Публикуемым источником остается только явный FBS-пул, а не общий остаток ФФ, не свободный FBO-остаток и не технический fallback.
3. Любая ошибка расчета, токена, WB API, сети, readback или warehouse mapping должна завершаться без внешней записи в WB либо без пометки успеха, если внешняя запись не подтверждена.
4. UI должен компактно показать человеку, что именно будет отправлено, почему отправка заблокирована или что WB уже подтвердил.
5. Таблицу товаров нельзя раздувать защитной механикой: это не повод вернуть колонку `Лимит`, насыпать технические чипы или вынести отладочные коды в основной экран.

## Зачем это бизнесу

Селлер воспринимает ЛК WB как место, где продается товар. Если там было `20`, а после действия WMS стало `0`, товар перестает продаваться, хотя физически он мог оставаться доступным. Это прямая потеря продаж и доверия к WMS.

WMS должна быть более осторожной, чем обычная форма редактирования числа. Она работает между складским учетом и внешним маркетплейсом, поэтому не имеет права заменять неопределенность нулем. Лучше остановить синхронизацию и попросить пользователя выделить FBS-пул или повторить попытку, чем молча занулить витрину WB.

## Пользователь и складской процесс

Основной пользователь: селлер или FF-менеджер, который управляет публикацией FBS-остатков в WB.

Он открывает seller catalog / экран товаров и остатков, потому что хочет включить или повторить синхронизацию FBS-остатка. Его складская работа проста: понять, сколько товара реально разрешено продавать по FBS через конкретный WB-склад, и отправить именно это количество в WB.

Рядом с этим процессом существуют F08 и F10:

- F08 задает распределение остатка, включая явный FBS-пул;
- F10 говорит, что в WB уходит только FBS-пул;
- F22 добавляет P0-защиту: если FBS-пул не доказан или sync не подтвердился, WMS не публикует `0` как безопасный результат.

Это не новый складской workflow. Это защитный слой над действием публикации, чтобы оператор не получил опасный внешний эффект от неполного внутреннего состояния.

## Основной сценарий

Дано: в ЛК WB у товара сейчас `20`.

Когда пользователь включает sync в WMS, система сначала должна определить:

- seller scope - какой селлер и какой WB-токен используются;
- WB warehouse - какой виртуальный FBS-склад WB является целью;
- WMS warehouse / pool - какой физический склад и какой FBS-пул являются источником;
- product key - какой `chrtId`/вариант товара публикуется;
- qty to publish - какое количество WMS безопасно считает FBS-пулом для этой пары seller + WB warehouse + product.

Если WMS не имеет явного FBS-пула, не может связать WB-склад с WMS-складом, получает ошибку WB или не может выполнить readback, then `0` не отправляется. UI показывает: `Не отправлено: не удалось безопасно рассчитать FBS-пул` или более конкретную человеческую причину.

Если FBS-пул есть и равен, например, `7`, then WMS отправляет `7`, после ответа WB делает readback и только после подтверждения показывает успех: `WB подтвердил 7 шт`.

Если FBS-пул действительно равен `0`, then это все равно не должно быть автоматическим fallback. Нужен отдельный продуктово утвержденный сценарий: явный FBS-пул `0`, понятное предупреждение/подтверждение в UX, запись в WB и readback `0`. До такого approval F22 считает публикацию нуля запрещенной.

## Инварианты safe sync

1. Ошибка не равна нулю.
2. Неизвестное состояние не равно нулю.
3. Пустой расчет не равен нулю.
4. Отсутствие FBS-пула не равно нулю.
5. Отсутствие привязки seller + WB warehouse + WMS warehouse не равно нулю.
6. Истекший, неверный или недоступный WB-токен не равен нулю.
7. Таймаут, 5xx, сетевой сбой или неполный ответ WB не равны нулю.
8. Успешный `PUT` без readback не является финальным успехом для пользователя.
9. Последний подтвержденный sync result нельзя перезаписывать расчетом, который не дошел до подтвержденного WB readback.
10. `0` можно отправить только после отдельного Product OK для явного нулевого FBS-пула, а не как аварийный fallback.
11. Обычная публикация остатков не использует destructive DELETE для зануления; ноль - это бизнес-значение, а не способ "очистить ошибку".
12. Внешняя цель синхронизации всегда seller-scoped и warehouse-scoped: один селлер, один WB-склад, один товарный вариант.

## UX-решение

### В таблице товаров

Основная таблица должна остаться компактной. Нужны только те данные, которые помогают человеку принять решение:

- общий остаток WMS;
- FBS-пул;
- к отправке в WB;
- последний подтвержденный WB sync;
- короткий статус последней попытки.

Не возвращать отдельную колонку `Лимит` как перегружающую сущность. Если лимит или ограничение нужен для расчета, он должен жить в деталях распределения или внутри объяснения причины, а не как еще один постоянный столбец в таблице.

Кнопки должны быть короткими и рабочими:

- `Включить sync`;
- `Повторить`;
- `Открыть FBS-пул` / `Настроить FBS-пул`.

Не добавлять отдельные большие CTA для каждого под-состояния. Один компактный статус и одно основное действие достаточно.

### В строке / compact status

Рекомендуемые человекочитаемые статусы:

- `Не настроен FBS-пул`;
- `Не отправлено`;
- `Ошибка WB`;
- `Ожидает подтверждения WB`;
- `WB подтвердил N шт`;
- `Sync выключен`.

Запрещенный основной текст:

- `null`;
- `undefined`;
- `stock_sync_failed`;
- `warehouse_mapping_missing`;
- raw HTTP body;
- stack trace;
- длинные JSON-контексты;
- технические названия полей как основной UX.

Технические детали можно хранить в логах и code review evidence, но не делать их основным экраном для селлера.

### В деталях распределения

Если FBS-пул не задан, пользователь должен попасть в понятное место настройки распределения. Текст должен объяснять складскую причину:

`FBS-пул не выделен. WB не получает остаток, пока вы не зададите количество для FBS.`

Не надо писать, что система "рассчитала 0", если на самом деле она не нашла безопасный источник.

### Подтверждение опасного нуля

До отдельного Product OK сценарий публикации `0` заблокирован. Если Product Agent утвердит его позже, UX должен требовать явного подтверждения смысла:

- видно, что FBS-пул именно `0`;
- видно, какой WB-склад и какой товар будут изменены;
- текст говорит, что в WB будет отправлено `0 шт`;
- после действия WMS показывает успех только после WB readback.

Без этого сценария dev не должен реализовывать автоматическую публикацию нуля.

## Обязательные данные

- seller id / active seller scope;
- WB token availability state без показа секрета;
- WB warehouse id и человекочитаемое имя склада;
- WMS warehouse id и связь с WB warehouse;
- product id и WB variant key, предпочтительно `chrtId` для stock sync;
- общий остаток WMS;
- явный FBS-пул;
- quantity to publish;
- sync enabled/disabled;
- last attempted at;
- last confirmed quantity;
- last confirmed readback at;
- last failure reason в человекочитаемом виде;
- состояние `pending_confirmation`, если WB-запись могла произойти, но readback не подтвердил итог.

## Лишние данные и UI-шум

Не добавлять:

- колонку `Лимит`;
- отдельную широкую колонку с JSON/error payload;
- новые цветные чипы на каждую внутреннюю причину;
- технические статусы `pending_confirmation`, `mapping_missing`, `transport_error` как пользовательский текст;
- кнопку destructive zero / clear WB stock без отдельного Product OK;
- настройку секретов, токенов или кабинеты ключей в рамках этой задачи;
- отдельный экран "WB debug" для обычного селлера.

## Состояния

### Empty state

Если FBS-пул не выделен, UI показывает:

`FBS-пул не настроен. В WB ничего не отправляем.`

Основное действие: `Настроить FBS-пул`.

Ожидаемый внешний эффект: никаких записей в WB, никакого `0`, статус sync не считается успешным.

### Error state

Если WB вернул ошибку, токен недоступен, readback не прошел или WMS не смогла связать склады, UI показывает:

`Не отправлено: не удалось подтвердить остаток WB.`

Если причина понятна, ее можно дать коротко:

- `Не найден FBS-склад WB`;
- `Не задан FBS-пул`;
- `WB временно недоступен`;
- `WB не подтвердил изменение`;
- `Нет доступа к WB-синхронизации`.

Ожидаемый внешний эффект: последний подтвержденный WB/WMS sync result не перезаписан ошибочным `0`; пользователь видит, что нужна настройка или повтор.

### Pending/uncertain state

Если WMS отправила запрос, но не получила надежный readback, UI не должен писать `Успешно`.

Текст:

`Проверяем подтверждение WB. Не повторяйте как новую отправку, пока система не сверит остаток.`

Для dev это означает durable state - сохраненное промежуточное состояние операции, чтобы повтор не создал двойной или противоречивый внешний эффект.

### Success state

Успех виден только после WB readback:

`WB подтвердил 7 шт`

В success state нужно сохранить:

- отправленное количество;
- подтвержденное WB количество;
- время подтверждения;
- товар и WB-склад.

Если отправили `7`, но readback вернул не `7`, это не success, а error/reconcile state.

## Почему именно так

Безопасная синхронизация должна быть fail-closed: при сомнении система останавливается, а не делает опасное внешнее изменение. В stock sync `0` является полноценным бизнес-значением: оно убирает товар из продажи. Поэтому нельзя использовать `0` как default для пустого массива, ошибки API, отсутствующей привязки или незаданного FBS-пула.

Отдельный большой экран для safe sync не нужен: пользователь уже работает с товарами и распределением остатка. Защита должна жить рядом с текущим действием синхронизации и показывать короткий ответ: сколько уйдет в WB, подтверждено ли это WB и почему сейчас не отправляем.

## Product questions / decision points

Следующий изолированный Product Agent должен дать явный verdict по этим вопросам:

1. Разрешаем ли вообще сценарий публикации `0` в WB из WMS в этой итерации?
2. Если да, какой UX считается достаточным подтверждением опасного нуля: inline confirm, modal confirm, отдельное право роли или только ручной admin action?
3. Должен ли `Включить sync` только включать флаг и ждать следующей безопасной публикации, или сразу выполнять sync attempt после preflight?
4. Где показываем последний подтвержденный WB readback: в строке таблицы, в drawer распределения или в compact details popover?
5. Какая формулировка лучше для пользователя при отсутствии FBS-пула: `Не настроен FBS-пул` или `В WB не отправляем без FBS-пула`?
6. Нужен ли отдельный role/permission gate для публикации `0`, даже если FBS-пул явно равен нулю?
7. Какой SLA повтора после uncertain state: автоматическая reconcile-задача, ручная кнопка `Проверить WB`, или оба варианта?
8. Что показывать, если readback вернул число, отличающееся от отправленного: блокировать sync, показать конфликт или предложить повтор?

До ответов Product Agent dev не должен реализовывать опасный нулевой сценарий.

## Acceptance criteria

### AC-F22-01 Enable Sync Does Not Zero On Missing FBS Pool

Given в WB ЛК у товара `20`, а в WMS для seller + WB warehouse + product нет явного FBS-пула,
When пользователь включает sync,
Then WMS не отправляет `0` в WB, показывает `FBS-пул не настроен. В WB ничего не отправляем.`, оставляет success state пустым или старым подтвержденным, и предлагает `Настроить FBS-пул`.

### AC-F22-02 Calculation Error Is Not Zero

Given WMS не может безопасно рассчитать FBS-пул из-за ошибки данных, склада, товара или резерва,
When sync attempt запускается вручную или автоматически,
Then внешняя запись в WB не выполняется, `quantity_to_publish=0` не используется как fallback, UI показывает `Не отправлено`, а ошибка сохраняется как failure reason.

### AC-F22-03 WB Error Does Not Mark Success

Given WMS рассчитала FBS-пул, но WB вернул ошибку или transport failure,
When sync attempt завершается,
Then UI не показывает success, last confirmed quantity не меняется, пользователь видит человеческую причину, а повтор доступен только как повтор той же безопасной операции.

### AC-F22-04 Success Requires WB Readback

Given WMS отправила количество `N` в WB,
When WB вернул технический успех записи,
Then WMS делает readback и показывает `WB подтвердил N шт` только если readback вернул тот же `N` для той же пары seller + WB warehouse + product.

### AC-F22-05 Zero Requires Explicit Product-Approved Scenario

Given FBS-пул равен `0`,
When Product Agent еще не утвердил опасный нулевой сценарий,
Then dev не реализует автоматическую отправку `0`; UI показывает, что публикация нуля требует отдельного подтвержденного сценария, без destructive action.

### AC-F22-06 Compact UX

Given seller products table отображает товары и stock sync,
When есть success/error/empty state,
Then таблица остается компактной: нет колонки `Лимит`, нет технических JSON/кодовых статусов, нет лишних чипов, а кнопки имеют короткие рабочие названия.

### AC-F22-07 Seller/Warehouse Scope Is Mandatory

Given у селлера есть несколько складов или товаров,
When sync считает quantity to publish,
Then расчет и readback scoped по seller + WB warehouse + product variant; нельзя брать общий остаток, FBO-свободный остаток или чужой склад как fallback.

### AC-F22-08 Browser QA Must Prove No External Zero In Incident Path

Given test/emulator содержит WB остаток `20`,
When browser QA включает sync при отсутствующем FBS-пуле или forced WB error,
Then QA доказывает readback/emulator state: WB осталось `20`, UI показывает error/empty state, и на экране нет технического мусора.

## Рекомендуемое test coverage для dev PR

| TC-ID | Title | Applies | Notes |
|-------|-------|---------|-------|
| TC-NEW-F22-001 | Missing FBS pool does not publish zero | Y | Given WB stock is 20 and FBS pool is absent, When user enables sync, Then WB/emulator readback remains 20; expected UI says not sent; negative: no PUT 0 fallback. |
| TC-NEW-F22-002 | WB error/readback failure is not success | Y | Given safe FBS quantity exists, When WB write or readback fails, Then last confirmed sync is unchanged and UI shows human error; restriction: no success without readback. |
| TC-NEW-F22-003 | Explicit FBS pool publishes only after readback | Y | Given FBS pool N exists, When user repeats sync, Then WMS sends N for seller + WB warehouse + chrtId and shows success only after readback N. |
| TC-NEW-F22-004 | Zero publication is blocked pending Product OK | Y | Given FBS pool equals 0, When Product zero scenario is not approved, Then UI does not auto-send 0; negative: no destructive clear/delete action. |
| TC-NEW-F22-005 | Compact seller stock UX | Y | Given empty/error/success sync states, When seller products table renders, Then core columns stay compact and no `Лимит`, raw JSON, technical status codes, or extra chips appear. |

## Acceptance checklist for dev / code review / browser QA

Dev checklist:

- Backend preflight distinguishes missing/unknown/error from numeric zero.
- Sync source is explicit FBS-pool only.
- Seller + WB warehouse + product variant scope is mandatory.
- WB write success is followed by readback before user-visible success.
- Pending/uncertain state is durable enough for safe retry/reconcile.
- No secret/token panels or credential mutations are introduced.
- UI uses compact labels and does not add `Лимит` as a table column.
- Zero publication is blocked unless Product Agent explicitly approves the UX and business rule.

Code review checklist:

- No path converts `None`, empty list, exception, mapping miss or API failure into `0`.
- No ordinary sync path uses destructive DELETE to clear WB stock.
- Last confirmed sync result is not overwritten before readback.
- Tests cover missing FBS-pool, WB error, readback mismatch, explicit nonzero success and blocked zero.
- Error messages are human-readable at UI boundary and technical details stay in logs.
- Changes remain scoped to F22 and do not redesign seller catalog / stock directions.

Browser QA checklist:

- Open real seller stock/catalog UI.
- Prove the incident path: WB/emulator starts with `20`, sync with missing FBS-pool or forced error does not change WB to `0`.
- Prove visible empty/error state with no technical codes.
- Prove nonzero happy path only if dev implemented it and WB/readback confirms the same number.
- Check table width and buttons at normal desktop viewport: no `Лимит` column, no raw JSON, no chip explosion.
- If zero scenario is not product-approved, verify there is no UI path that sends `0`.

## BA/UX handoff to next gate

F22 receives `BA_UX_READY`.

This is not `PRODUCT_APPROVED_FOR_DEV`. The next required gate is isolated Product / UX Review. Product Agent must decide the explicit zero-publication policy and approve the compact UX before any Atomic Dev Agent starts implementation.
