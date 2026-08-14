# Батч 05. Product findings: остатки, ячейки, движения и инвентаризация

## Короткий вердикт

Фактический остаток после B04 сохранился без потерь: товар A = `3`, товар B = `2`, `В сортировке=0`, `В ячейках=3/2`, `Доступно=3/2`. Но четыре обычных вопроса склада не образуют один рабочий процесс. «Сколько доступно» можно узнать после горизонтального сдвига таблицы; «где товар» и «почему изменилось» интерфейс доказательно не отвечает; инвентаризация целиком заменена сообщением `Раздел в разработке`.

Это не запрос на новый большой WMS-модуль. Минимальный продуктовый контур уже можно собрать на существующих сущностях: связать строку каталога с location breakdown и движениями, сделать журнал читаемым и доступным из навигации, а инвентаризацию начать с короткого cell-first count flow с черновиком и подтверждением расхождений.

## AS-IS: inputs и attention shifts

Считается одно осознанное действие: click, scan/text+Enter или scroll-жест. Attention shift — перенос взгляда/руки на другой объект или зону экрана.

### Найти остаток и ответить «сколько доступно»

На 1280 из другого раздела: click `Каталог`, click search, scan/ввод SKU+Enter, horizontal scroll к `Доступно`. Итого **4 input events**: 2 clicks, 1 scan/keyboard event, 1 scroll; **5 attention shifts**: sidebar → search → физическая этикетка/ввод → identity слева → stock справа. Ответ получить можно, но SKU и число не видны одним взглядом. На runtime 1920 остаётся малый горизонтальный overflow; физический wide-export IAB имеет 1873px, поэтому exact 1920px PNG не заявляется.

### Найти ячейку товара

Каталог → search → scan SKU → horizontal scroll → `Ячейки` → выбор склада: **6 input events** и минимум **8 attention shifts**. После этого процесс останавливается: каталог показывает только aggregate `В ячейках`, а directory ячеек — только адрес и barcode без SKU/qty. Завершённого пути до доказанного `A 1.1 · 3/2` нет.

### Объяснить изменение остатка

Из продуктовой навигации путь отсутствует: route журнала скрыт. При заранее известном direct URL нужны navigate и `Обновить`, затем ручной просмотр до 80 строк — **2 управляющих события + неограниченный визуальный поиск**, минимум **6 attention shifts**, и ответа всё равно нет. В строках отсутствуют время, документ №000007, from/to cell, actor/reason, resulting balance и связь двух половин transfer.

### Начать и провести инвентаризацию

Click `Инвентаризация` — **1 input event**, **2 attention shifts**, затем процесс полностью останавливается на `Раздел в разработке`. Ни начать задание, ни отсканировать ячейку/товар, ни сохранить факт, ни согласовать расхождение нельзя.

### Перемещение как дополнительный common job

Route скрыт. Даже с direct URL оператор выбирает source, destination, товар из flat list 211 позиций и количество: ориентировочно **8 input events** и **7+ attention shifts**, scanner events 0. Баланс source не показан, warehouse не подписан, `__SORTING__` выведен как обычная option. Реальная мутация не выполнялась: в exact warehouse только одна storage-cell, а системная Sorting не является безопасной второй тестовой ячейкой.

## Минимальный простой flow без переизобретения системы

1. В существующей строке каталога закрепить SKU/name и `Доступно`; рядом показать `Где: A 1.1 · 3` как ссылку на уже существующий location balance и action `История`.
2. Открывать журнал из строки с prefilled SKU. Одна человеческая строка движения: время, операция по-русски, документ, `откуда → куда`, delta и остаток после операции. Две части transfer визуально объединять.
3. Сделать routes `Движения` и `Перемещения` видимыми в навигации по правам, а не требовать знания URL.
4. В текущей форме transfer заменить flat product select на search/scan, показать доступно в source, исключить same source/destination и объяснить системную Sorting. Перед submit — короткий итог, не новый wizard.
5. Первый inventory flow: `Новая инвентаризация` → scan ячейки → scan товаров/ввод факта → расхождения → сохранить черновик → подтверждение/проведение. Нужны resume и audit; отдельный дизайнерский конструктор или новый сервис не требуются.

## UX/process findings

### B05-F01 — инвентаризации как процесса нет

**Severity: P0 operational. Verdict: `FAIL_PROCESS`.**

Экран содержит только `Раздел в разработке`. Нет scope по складу/ячейке, expected/fact, scanner input, blind count/recount, причин, approval, posting, draft/resume, истории и восстановления. Для 10k+ пользователей это полный process stop, а не пустое состояние.

Evidence: `b05-031`–`b05-035`.

### B05-F02 — каталог и ячейки не отвечают «где товар»

**Severity: P1. Verdict: `FAIL_PROCESS`.**

Каталог показывает aggregate `В ячейках`, но не адреса. Directory показывает A 1.1 и barcode, но не содержимое, количество, доступность или occupancy. Row click с обеих сторон не открывает detail; связующего перехода нет.

Evidence: `b05-001`, `b05-012`, `b05-028`, `b05-052`–`b05-054`.

### B05-F03 — журнал не объясняет причину изменения

**Severity: P1. Verdict: `FAIL_PROCESS / FAIL_UX`.**

Маршрута нет в nav. После ручного refresh видны только SKU, Δ и raw enum (`stock_transfer_in`, `inbound_intake`). Нет времени, документа, склада/ячеек, seller/actor/reason, результата и парности transfer. Exact A/B присутствуют, но их нельзя доказательно связать с №000007 или конкретным A 1.1.

Evidence: `b05-036`–`b05-042`.

### B05-F04 — движения после прямого входа/reload выглядят ложно пустыми

**Severity: P1. Verdict: `FAIL_PROCESS`; functional defect отдельным слоем ниже.**

Direct route и reload показывают `Пока пусто.` до ручного `Обновить`, хотя на сервере есть 80 последних строк. Пользователь получает ложный нулевой state и должен знать скрытое recovery-действие.

Evidence: `b05-036`, `b05-037`, `b05-040`, `b05-041`.

### B05-F05 — критические stock-поля разделены горизонтальным scroll

**Severity: P1. Verdict: `FAIL_UX`.**

При 1280 identity находится слева, `Доступно` — справа. Таблица имеет scrollWidth 2641px; 212 строк отрисованы без pagination/column chooser. Оператор должен запомнить SKU, сдвинуться и читать неподписанное число без единицы и freshness. На runtime 1920 scrollWidth остаётся 2015px.

Evidence: `b05-001`, `b05-012`–`b05-014`, `b05-028`–`b05-030`.

### B05-F06 — смысл `Доступно` держится на скрытых правилах

**Severity: P1. Verdict: `FAIL_PROCESS`.**

UI не показывает reserved, не объясняет формулу total/sorting/cells/reserved/available и связь packed/unpacked с доступностью. Нет `шт` и времени актуальности. Числа A=3, B=2 совпадают с baseline, но пользователь не может проверить, почему они именно такие.

Evidence: `b05-012`, `b05-013`, `b05-052`–`b05-054`.

### B05-F07 — transfer выглядит как административная форма, а не операция склада

**Severity: P1. Verdict: `FAIL_UX / FAIL_PROCESS`.**

Route скрыт; source/destination не показывают warehouse, системный `__SORTING__` не переведён, product list из 211 позиций не searchable, scanner-flow отсутствует, source balance не виден. UI допускает видимые 1.9, -1, 0 и same-cell combination при активной CTA; браузерная/server validation не объясняется заранее. Draft теряется после reload без предупреждения.

Evidence: `b05-043`–`b05-051`.

### B05-F08 — directory ячеек пригоден только как справочник адресов

**Severity: P2. Verdict: `FAIL_UX`.**

Нет поиска по warehouse/cell/barcode, фильтра/сортировки, occupancy, contents или detail. Warehouse и cell rows mouse-only. Print dialog безопасно работает, но не помогает найти остаток.

Evidence: `b05-028`–`b05-030`.

### B05-F09 — movements/transfers визуально трудно читать

**Severity: P1 accessibility. Verdict: `FAIL_UX`.**

Текст legacy cards и таблицы почти чёрный на тёмно-сером фоне при 1280 и wide; заголовок белый, данные теряются. Расширение viewport не исправляет контраст.

Evidence: `b05-036`–`b05-051`.

### B05-F10 — рабочий контекст поиска не восстанавливается

**Severity: P2. Verdict: `FRICTION`.**

Seller filter и query после reload сбрасываются. В movement summary status `done` после reload снова `—`; в transfer несохранённый draft очищается. Durable stock не страдает, но расследование приходится собирать заново.

Evidence: `b05-011`, `b05-039`, `b05-040`, `b05-050`.

## Functional defects — отдельный слой

1. **Movement list false-empty после mount/reload, P1:** данные существуют и появляются после `Обновить`, но initial/reload state сообщает `Пока пусто.` (`b05-036`, `b05-037`, `b05-040`).
2. **Client-side transfer guards неполны, P1 UX/data-risk:** same source/destination, decimal, negative и zero визуально допустимы при активной CTA (`b05-045`–`b05-049`). Submit не выполнялся; server mutation или конкретная server error не заявляются.
3. **Wide export limitation — не app defect:** Browser runtime честно измерен как 1920×1080 DPR1, но сохранённые wide PNG имеют 1873×1080. Это `BLOCKED_ENV`, не дефект WMS.
4. **Закрытие Browser tab — не app defect:** новая in-app tab восстановлена по разрешению пользователя, auth/session и state сохранились.

## Что доказанно работает

- Exact SKU, barcode, name, case/spaces и unknown-query search дают предсказуемый результат.
- Seller filter и search composition работают; name/quantity sorting asc/desc меняет порядок.
- A/B stock после B04 и после финального reload неизменен: 3/2, Sorting0, cells/available3/2.
- Exact warehouse/cell/barcode видимы; print dialog открывается и закрывается без физической печати.
- Manual movement refresh показывает 80 rows; read-only digest завершился `done`, result `Всего движений: 132`.
- Inventory route, reload и Back/Forward стабильны, но стабильно ведут только к placeholder.
- Ни одной stock mutation в B05 не было.

## Product gate

Evidence batch: **`ACCEPTED` с прозрачным `BLOCKED_ENV` exact-wide export**. Product process: **`STOP` перед самостоятельным массовым пилотом**. Главные stop-gates: отсутствующая инвентаризация, отсутствие product↔cell trace, необъясняющий журнал, false-empty movements и небезопасный/scanner-less transfer form.
