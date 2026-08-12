# Батч 02. Handoff оркестратору

## Короткий ответ

Нет, seller-процесс ещё нельзя назвать корректным и безопасным для плохо обученного сотрудника. Его техническое ядро жизнеспособно: seller видит свой товар, ТЗ сохраняется, valid inbound можно передать ровно один раз, stock до приёмки не возникает, submitted-data заблокированы. Но пользователь не управляет жизненным циклом черновика: вход/reload/Close создают и оставляют документы, а затем список не даёт отличить их друг от друга. Вместе со сломанной таблицей и молчаливой validation это создаёт прямой риск передать ФФ не тот физический состав.

## Scope и визуальное доказательство

- Проверены seller surfaces: Products, ТЗ упаковки, Inbound create/detail/submit, Documents, placeholder расхождений, seller-side MP draft при zero stock и Settings overview.
- Admin использовался только для двух isolated manual products; WB sync и чужие tenants не изменялись.
- Visual slices A–C ранее поштучно adjudicated **41/41 PNG**.
- Этот независимый synthesis лично повторно открыл через `view_image` ключевые **24/41 PNG**: `001`, `005`, `007`, `011`, `012`, `014`, `017`, `019`, `020`, `022`, `023`, `025`, `027`, `028`, `030`, `031`, `032`, `033`, `035`, `036`, `037`, `038`, `039`, `041`.
- `015`, `016`, `031`, `034`, `038`, `040` не используются как durable app truth. `031/038` подтверждают только false-empty/partial loading risk рядом с settled `032/041`.
- `008` не закрывает 1920×1080 DPR1: измеренный viewport оставался 1280×720, DPR2. Валидный layout gate есть только для нормализованного 1280 кадра `041`; несколько `028–040` имеют malformed/cropped geometry и используются только там, где конкретный текст/row всё же различим и подтверждён runtime.
- Credential dialogs не открывались; никаких secret values в evidence нет.

## Оставленное synthetic staging state

- Два manual seller-bound товара A/B; оба stock=0 во всех колонках после inbound submit.
- У товара A сохранено synthetic ТЗ упаковки и включён marking flag.
- В Documents осталось **6 документов**: один empty MP draft и пять inbound — один submitted с 2 lines, четыре drafts с line counts `0/0/2/0`.
- Submitted inbound содержит A=3, B=2 и boxes=2. Его точный seller-facing ID/номер не виден и не сохранён отдельным sanitized state log; поэтому этот батч **не передаёт B03 проверяемый exact ID**.
- MP populated planning не создан: available in-cell stock отсутствует, внешние/stock-changing действия не выполнялись.

## Ledger counts

- `PASS`: **9**.
- `FRICTION`: **15**.
- `FAIL_PROCESS`: **6**.
- `FAIL_UX`: **8**.
- `BLOCKED_FIXTURE`: **4**.
- `NOT_RUN`: **21**.
- Всего: **63/63 checklist IDs**.

## Stop-gates

1. Inbound `/new` и MP create мутируют данные до осознанного Save; reload/Close оставляют abandoned drafts.
2. Documents не показывает стабильный номер/ID и достаточный итог, поэтому документы одной даты нельзя надёжно различить.
3. Inbound table на 1280 не позволяет быстро сопоставить товар и quantity; названия идут вертикально.
4. Invalid qty/boxes обрабатываются молча; строка удаляется без confirm/undo.
5. «Создать акт расхождений» — рабочая на вид заглушка, реального recovery process нет.

До закрытия этих пунктов flow нельзя считать безопасным для склада или селлера с низкой цифровой грамотностью.

## FRICTION, не самостоятельный stop-gate

- ТЗ durable, но неясно, печатается текущая или сохранённая версия.
- Submitted detail сохраняет title «Новая заявка» и активный Save, не объясняет следующий физический шаг.
- Loading может временно показать false-empty/partial list.
- Нет компактного итога `позиции / единицы / короба` перед submit.
- Products и inbound таблицы требуют упрощения на 1280; отдельного валидного 1920 verdict нет.

## Непокрыто и fixtures

- Не проверены: product-create Cancel, duplicate barcode, date validation, duplicate inbound line с authoritative screenshot, Save double-click, browser back/forward, filters, MP row open/back, Settings safe non-secret mutations и print outcome.
- Sort заблокирован отсутствием второго безопасного document date.
- MP populated save/edit/reload и wrong qty заблокированы отсутствием isolated available in-cell stock.
- Confirm/ship/unplan/cancel, WB sync и credential operations сознательно не выполнялись по safety boundary.
- Отдельный sanitized state/network log отсутствует.

## Gate

Формальный результат: **`RETURN_FOR_COVERAGE`**.

Причина двойная: покрытие не закрывает обязательный 1920 viewport, state log и 21 action; одновременно уже подтверждены шесть `FAIL_PROCESS` и восемь `FAIL_UX`. B02 нельзя принимать как безопасный продуктовый процесс и нельзя передавать submitted inbound в B03 без exact ID. `B02_BROWSER_BLOCKER_RU.md` сохранить как исторический документ: он описывает раннюю недоступность Browser у первого изолированного агента, но superseded фактическим живым прогоном, slices A–C и этим ledger.

Следующий батч не начинать до adjudication оркестратора.
