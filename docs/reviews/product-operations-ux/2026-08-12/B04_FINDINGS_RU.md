# Батч 04. Product findings сортировки и размещения

## Короткий вердикт

Складской результат технически корректен: exact пять единиц частично, затем полностью переместились из `Сортировки` в storage, стали доступны `3/2`, double-click не создал дублей, чужой склад и системная sorting-cell не попали в destination. Но текущий процесс **не годится как самостоятельное массовое рабочее место сортировщика**. Он построен как административная форма: мышью выбрать ячейку, мышью перейти в количество, набрать число, повторить для каждого SKU, разобраться в двух CTA и самому отличить черновик от уже проведённого товара.

Главная проблема — не число кнопок само по себе. Сотрудник постоянно переводит внимание между физическим товаром, dropdown, клавиатурой, обрезанными колонками, верхним remaining и нижними карточками. Scanner-flow для ячейки и товара отсутствует вообще. На 1280 даже самый простой one-cell путь требует внутреннего scroll вниз и обратно вверх.

## AS-IS input events и attention shifts

Считается одно осознанное действие сотрудника: click, выбор option, ввод значения или scroll-жест. Печатание одного целого количества считается одним input event, а не посимвольно.

### Fresh happy path на фактическом 1280×720

1. Click `Сортировка`.
2. Click exact row после визуальной сверки seller/2 lines/remaining/date.
3. Click destination A.
4. Click option A 1.1.
5. Click quantity A.
6. Ввести `3`.
7. Scroll к B.
8. Click destination B.
9. Click option A 1.1.
10. Click quantity B.
11. Ввести `2`.
12. Scroll обратно к верхним CTA.
13. Click `Применить раскладку`.

Итого: **13 input events**, из них **9 mouse clicks, 2 keyboard entries и 2 scroll gestures**. Scanner events: **0**, потому что scanner control отсутствует. По фиксированному правилу «сменился объект, за которым следит взгляд или рука» получается **10 attention shifts**: sidebar→queue, queue→detail identity, header→A cell, cell→A qty, A→scroll/B, B cell→B qty, B→scroll/header, header→CTA, CTA→result плюс возврат к физическому товару между A и B.

При runtime CSS viewport 1920×1080 обе product cards помещаются без scroll: **11 input events** и **8 attention shifts**. IAB wide export физически 1873×1080, поэтому это честный runtime UX-count, но не заявление о PNG шириной 1920px.

### Фактически пройденный partial + recovery путь

Проверочный путь был намеренно длиннее: Save draft, reload/reopen, dirty Close, Back/Forward/reload, partial Apply A=1, reload/stock read-back, затем A=2+B=2 и final Apply. Он доказывает recovery и conservation, но не выдаётся за happy path.

## Минимальный идеальный flow без redesign

Оставить те же queue/detail и тот же серверный transition. В detail нужен один постоянно активный scanner input:

1. Click `Сортировка`.
2. Click/Enter exact row, где видны № и warehouse.
3. Scan ячейки A 1.1 — она становится текущим destination.
4. Пять product scans: три A и два B; рядом растёт только фактически размещённый progress.
5. Один click `Завершить размещение` с summary `2/2 позиции · 5/5 ед. · A 1.1`.

Итого: **9 input events** и **6 attention shifts**. Руки не уходят на dropdown и ручной quantity, а текущий warehouse/cell остаётся в header. Для товара без штрихкода можно сохранить существующие dropdown+qty как fallback, а не строить новый wizard или сервис.

## UX findings — основной слой

### B04-F01 — рабочего scanner-flow нет

**Severity: P0 operational. Verdict: `FAIL_UX`.**

Destination выбирается только dropdown, количество вводится только number field. Нельзя отсканировать barcode ячейки, нельзя сканировать товар как `+1`, нет постоянно активной точки ввода. Реальный сортировщик держит товар/ТСД и вынужден положить его, взять мышь, затем клавиатуру, снова мышь. Это главный stop-gate для 10k+ пользователей.

Evidence: `b04-008`, `b04-014`, `b04-044`.

Минимальное исправление: scanner input в существующей панели; cell barcode задаёт destination, product barcode увеличивает соответствующий SKU на один. Dropdown и manual quantity остаются fallback.

### B04-F02 — queue/detail теряют identity задания

**Severity: P1. Verdict: `FAIL_UX`.**

Queue не показывает № документа и warehouse, выводит raw `sorting`; row mouse-only. После click исчезают seller и warehouse. Сотрудник должен удержать в памяти несколько признаков и надеяться, что A 1.1 относится к нужному складу.

Evidence: `b04-001`, `b04-005`, `b04-014`.

Минимальное исправление: добавить в существующие row/header №, warehouse, seller; перевести статус; дать `<tr>` keyboard focus и Enter.

### B04-F03 — `Разложено` смешивает draft и проведённый stock

**Severity: P1. Verdict: `FAIL_PROCESS`.**

Qty=1 без cell уже даёт `Разложено 1`. После partial Apply серверный remaining равен 4, а при подготовке финального draft A показывает `Разложено 3`: один уже проведён и два ещё только сохранены. Для сотрудника одно слово обозначает два разных состояния.

Evidence: `b04-015`, `b04-040`, `b04-045`, `b04-046`.

Минимальное исправление: разделить существующие подписи на `Уже размещено` и `В черновике`; remaining менять только после Apply. Не нужен отдельный progress-service.

### B04-F04 — Save и Apply выглядят как два равноправных способа закончить одно действие

**Severity: P1. Verdict: `FAIL_UX`.**

Save не сообщает успеха и не объясняет, что stock не двинулся. Apply не имеет confirmation/summary и сразу проводит partial movement. В момент ошибки сотрудник не понимает, нужно ли сначала Save, можно ли сразу Apply и что увидит следующая зона.

Evidence: `b04-005`, `b04-024`, `b04-028`, `b04-039`.

Минимальное исправление: один primary `Разместить`; secondary `Сохранить черновик` с saved-indicator и коротким пояснением. Перед Apply показывать компактный итог, а не новый экран.

### B04-F05 — ошибки ввода либо молчат, либо объясняются только красной рамкой

**Severity: P1. Verdict: `FAIL_UX / FAIL_PROCESS`.**

Positive qty без cell и zero silently исчезают после Save. `1.9` молча становится `1`. `-1` видим в number field без inline message. Overage4 блокируется правильно, но причина и допустимый максимум не написаны.

Evidence: `b04-015`–`b04-023`.

Минимальное исправление: разрешать только целые `>=1`; конкретная inline error рядом с той же row; неполную row не очищать; никогда не округлять молча.

### B04-F06 — recovery теряет работу без предупреждения

**Severity: P1. Verdict: `FAIL_UX`.**

Close и reload dirty draft без warning теряют `2` и возвращают saved `1`. Reload закрывает detail полностью. Back меняет underlying route, но dialog остаётся, что создаёт ложное ощущение сохранённого контекста.

Evidence: `b04-029`–`b04-036`.

Минимальное исправление: dirty guard для Close/Back/reload; deep-link/open request state; после Save явная метка `Черновик сохранён`.

### B04-F07 — частичное продолжение требует знания скрытой модели

**Severity: P1. Verdict: `FRICTION`.**

Partial Apply технически работает и durable. Но ранее проведённая A=1 остаётся визуально такой же row, как новый draft A=2. Продолжить можно только через `+ ячейка`, хотя ячейка та же; объяснения «1 уже проведена, осталось2» рядом с row нет.

Evidence: `b04-040`, `b04-043`, `b04-044`.

Минимальное исправление: lock/label posted rows и показывать остаток для нового ввода. Не создавать новый экран частичного размещения.

### B04-F08 — после завершения нельзя ответить «куда положили»

**Severity: P1. Verdict: `FAIL_UX`.**

Dashboard доказывает done и A3/B2, но не показывает destination. Cell directory показывает A 1.1 и barcode, но не SKU/баланс. Каталог показывает только aggregate `В ячейках` и `Доступно`, не per-cell breakdown. Supervisor не может визуально расследовать ошибку размещения.

Evidence: `b04-050`–`b04-054`.

Минимальное исправление: read-only distribution table в уже существующем completed detail либо cell detail с SKU/qty. Это audit read-back, не новый workflow.

### B04-F09 — 1280 перегружен шириной, wide всё равно требует horizontal recovery

**Severity: P2. Verdict: `FAIL_UX` на 1280, `FRICTION` на wide.**

На 1280 правый progress detail обрезан; stock требует переключать horizontal position между identity и zones. При runtime 1920 начальное левое положение всё ещё обрезает `Доступно`, но после одного horizontal shift одновременно видны meaningful identity от SKU/ШК/name и все zones; скрывается photo-column и подрезается page chrome. То есть wide уже пригоден для сверки, но не в исходном положении.

Evidence: `b04-005`, `b04-009`–`b04-012`, `b04-050`–`b04-052`.

Минимальное исправление: убрать вторичные артикулы в secondary line/tooltip, закрепить SKU и компактно сгруппировать zone numbers.

## Functional defects — отдельный слой

1. **Decimal floor, P1:** `1.9` сохраняется как `1` без ошибки (`b04-021`, `b04-022`). Это изменение физического факта, не косметика.
2. **Невалидный draft попадает в progress, P1:** positive qty без cell считается `Разложено`, хотя затем строка молча отбрасывается (`b04-015`, `b04-016`).
3. **Negative draft guard неполный, P1:** control показывает `-1` без inline error (`b04-017`). Серверное сохранение отрицательного значения в этом batch не выполнялось и не заявляется.
4. **Route/dialog рассинхронизация, P1:** Back/Forward меняют route при остающемся dialog и потере dirty-state (`b04-033`, `b04-034`; runtime observation).

## Что функционально работает

- Exact warehouse filtering: чужие cells и system Sorting не выбираются.
- Overage блокирует Save/Apply до server mutation.
- Save остаётся draft и не двигает stock.
- Partial Apply durable: A 3→Sorting2+cell1+available1; B остаётся Sorting2.
- Double-click Save/Apply не создал duplicate stock movement.
- Final Apply дал Sorting0, cells/available3/2, total5 сохранился.
- Completed документ исчез из Sorting до и после reload; final status read-back — `Оприходовано`.

## Fixture gap

В connected tenant нет warehouse с названием `Review Warehouse`. Exact request предлагает только storage cell `A 1.1` warehouse `FBS WB 1155120`; поэтому обязательный split по двум synthetic cells объективно заблокирован fixture. Чужие synthetic cells warehouse `Тестовый` не использовались. Финальная раскладка A3/B2 выполнена только в exact A 1.1.

## Product gate

Evidence batch: **`ACCEPTED`**. Product process: **`STOP` перед самостоятельным массовым пилотом** до появления scanner-first path, честных draft/posted semantics, безопасного recovery и completed per-cell read-back. Техническую транзакцию перерабатывать не требуется: stop-gates закрываются внутри существующих queue/detail/API-контрактов.
