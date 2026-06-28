# Ревью инвариантов доменной логики «Честный Знак» (диапазон 4e82c6b..HEAD)

## Резюме
Найдено 6 находок: 2 CRITICAL, 2 HIGH, 2 MEDIUM. Самое страшное — прямое нарушение
инварианта **И2** (автопривязка товара к коду по GTIN в `relink_unlinked_marking_codes`,
вызывается молча из `list_inventory`) и баг с теневым перекрытием имени `status` в
`marking_codes.py:721`, из-за которого вместо HTTP 404 падает `AttributeError`.
Дополнительно: прогноз/расход считает 2× из-за `copies` (нарушение духа И4), и при пометке
кода браком в `replace_reprint_request` старый код остаётся в статусе `defective`, а не
`replaced` (нарушение машины статусов из DESIGN §5).

---

## [CRITICAL] Автопривязка товара к коду по GTIN — нарушение инварианта И2

- **Где:** `backend/app/services/marking_code_service.py:667-698` (`relink_unlinked_marking_codes`),
  вызывается из `list_inventory` на `marking_code_service.py:981-982`; использует
  `_resolve_product_for_row` (`marking_code_service.py:452-483`).
- **Доказательство:**
```python
async def relink_unlinked_marking_codes(session, tenant_id, seller_id) -> int:
    """Try to attach imported codes (product_id=NULL) to catalog products by GTIN."""
    stmt = select(MarkingCode).where(
        MarkingCode.tenant_id == tenant_id,
        MarkingCode.seller_id == seller_id,
        MarkingCode.product_id.is_(None),
        MarkingCode.pool_id.is_(None),
        MarkingCode.status == STATUS_AVAILABLE,
    )
    codes = list((await session.execute(stmt)).scalars().all())
    linked = 0
    for code in codes:
        gtin = (code.gtin or "").strip() or extract_gtin_from_cis(code.cis_code)
        if not gtin:
            continue
        product = await _resolve_product_for_row(session, tenant_id, seller_id, gtin=gtin, sku="")
        if product is not None:
            code.product_id = product.id      # <-- автопривязка product по GTIN
            linked += 1
```
И вызов без явного действия пользователя:
```python
async def list_inventory(session, tenant_id, *, seller_id):
    if seller_id is not None:
        await relink_unlinked_marking_codes(session, tenant_id, seller_id)  # молча при чтении
```
- **Проблема:** Инвариант **И2** (TASKS строки 23-24): «Связь "пул ↔ товары" — только ручная
  (`marking_pool_products`, M2M). Никогда не угадывать товар по GTIN/названию автоматически.»
  Здесь код по GTIN автоматически находит `product` (`_resolve_product_for_row` ищет по
  `wb_barcode`/GTIN) и проставляет `code.product_id`. Это происходит **молча при обычном
  чтении инвентаря** (`list_inventory`), без явного действия, и даже коммитит изменение в БД
  (`if linked: await session.commit()`). Прямое нарушение И2 — связь товар↔код должна быть
  только следствием ручной привязки пула или фактической печати, а не угадывания по GTIN.
- **Фикс:** Удалить `relink_unlinked_marking_codes` и его вызов из `list_inventory`. Остаток на
  товар следует выводить через ручную M2M-связь `marking_pool_products` (как уже делает
  `list_inventory` ниже в блоке `pool_links_stmt`). Если нужен показ «непривязанных» —
  оставить их в `unlinked_available_count`, но НЕ проставлять `product_id`.

---

## [CRITICAL] `status` query-param затирает модуль FastAPI `status` → AttributeError вместо 404

- **Где:** `backend/app/api/marking_codes.py:715` (параметр) и `:721` (использование).
- **Доказательство:**
```python
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status  # :9

async def list_marking_pool_codes(
    pool_id: uuid.UUID,
    ...
    status: Annotated[str | None, Query()] = None,          # :715  затеняет модуль `status`
) -> list[PoolCodeOut]:
    from app.models.marking_code import MarkingPool
    pool = await session.get(MarkingPool, pool_id)
    if pool is None or pool.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pool_not_found")  # :721
```
- **Проблема:** Локальный параметр `status` (типа `str | None`) перекрывает импортированный
  модуль `fastapi.status` внутри всей функции. На строке 721 при ненайденном пуле обращение
  `status.HTTP_404_NOT_FOUND` идёт к параметру, а не к модулю: при `status=None` →
  `AttributeError: 'NoneType' object has no attribute 'HTTP_404_NOT_FOUND'`; при переданном
  `?status=printed` → `AttributeError: 'str' object has no attribute ...`. То есть запрос
  кодов несуществующего/чужого пула вместо корректного 404 падает с 500. Это тот самый класс
  бага, что упомянут в гейтах. Дополнительно — это маскирует мультитенантную проверку (И5):
  ветка «чужой tenant → 404» не отрабатывает штатно.
- **Фикс:** Переименовать query-параметр, например `status_filter: Annotated[str | None,
  Query(alias="status")] = None`, и пробросить его в `list_pool_codes(..., status=status_filter)`.
  Тогда строка 721 снова ссылается на модуль `status`. (Альтернатива — `from starlette import
  status as http_status`, но переименование параметра проще и локальнее.)

---

## [HIGH] Прогноз/расход (consumption_7d) считает копии, а не единицы — нарушение духа И4

- **Где:** `backend/app/services/marking_code_service.py:1652-1677` (`_pool_consumption_7d_batch`),
  совместно с записью события печати на `:1267-1275` (`copies=event_copies`, где
  `event_copies = cz_copies_from_layout(...)`, обычно 2).
- **Доказательство:**
```python
# запись события печати: одно событие на КОД, но с copies=2 (label+cz)
event_copies = cz_copies_from_layout(print_layout)   # :1126  -> обычно 2
...
await record_event(..., event_type=EVENT_PRINTED, copies=event_copies)  # :1267-1275

# расход за 7 дней суммирует именно copies:
stmt = (
    select(MarkingCodeEvent.pool_id, func.coalesce(func.sum(MarkingCodeEvent.copies), 0))
    .where(
        MarkingCodeEvent.event_type.in_(tuple(CONSUMPTION_EVENT_TYPES)),  # printed/shipped
        MarkingCodeEvent.created_at >= cutoff,
    )
    .group_by(MarkingCodeEvent.pool_id)
)
```
- **Проблема:** Инвариант **И4** (TASKS 26-27): «Один КМ расходуется один раз. Печать N копий
  одного кода — это параметр печати, остаток уменьшается на 1 за единицу товара, **не за
  копию**.» Расход `consumption_7d` суммирует `copies`, поэтому при печати N кодов с layout
  `copies=2` он покажет 2N израсходованных кодов вместо N. Это идёт в `compute_forecast_days`
  (`available / (consumption_7d/7)`) → прогноз дней занижается вдвое, и в low-stock алёрты
  (`marking_low_stock_service.py:75,82-83`) → ложные срабатывания «мало кодов». Сам остаток
  (`available` по статусам) считается верно — расходуется один код. Проблема именно в метрике
  расхода/прогноза.
- **Фикс:** В `_pool_consumption_7d_batch` считать число событий/кодов, а не сумму копий:
  заменить `func.sum(MarkingCodeEvent.copies)` на `func.count(func.distinct(MarkingCodeEvent.code_id))`
  (расход = число уникальных израсходованных кодов за период).

---

## [HIGH] Брак→замена: старый код остаётся `defective`, не доходит до `replaced` (машина статусов)

- **Где:** `backend/app/services/marking_code_service.py:2231-2259` (`replace_reprint_request`).
- **Доказательство:**
```python
old_code.status = STATUS_DEFECTIVE
old_code.defective_reason = req.reason
await record_event(..., code=old_code, event_type=EVENT_DEFECTIVE, ...)   # статус остаётся defective

new_code.status = STATUS_PRINTED
...
old_code.replaced_by_code_id = new_code.id
await record_event(..., code=old_code, event_type=EVENT_REPLACED, ...)    # событие replaced, но статус НЕ меняется
await record_event(..., code=new_code, event_type=EVENT_PRINTED, ...)
```
- **Проблема:** DESIGN §5 (строки 105-119): машина статусов `... defective → replaced (новый
  код)`; «`replaced` — заменён новым (старый погашен)». Здесь пишется событие `EVENT_REPLACED`,
  но `old_code.status` так и остаётся `STATUS_DEFECTIVE` — переход в `STATUS_REPLACED` не
  выполняется. В результате: (1) статус кода не соответствует терминальному состоянию «погашен/
  заменён»; (2) агрегат `defective` в карточке пула (`PoolDetailRow.defective`,
  `marking_code_service.py:1810`) завышается — заменённые коды навсегда числятся «браком»,
  хотя по дизайну `defective` и `replaced` — разные конечные состояния. Событие `replaced`
  есть, а статусного перехода нет — рассинхрон журнала и состояния.
- **Фикс:** После записи `EVENT_REPLACED` выставить `old_code.status = STATUS_REPLACED`
  (импортировать `STATUS_REPLACED`). Тогда счётчик «Брак» в пуле не будет включать
  заменённые коды, а терминальный статус совпадёт с журналом.

---

## [MEDIUM] Печать/перепечатка не проверяет статус упаковочного задания (печать на закрытом/отгруженном)

- **Где:** `backend/app/services/marking_code_service.py:1113-1289` (`print_codes_for_packaging_line`),
  `:1156-1188` (ветка reprint). Нет проверки `task.status`.
- **Доказательство:** В функции загружается `task = line.task`, проверяется только
  `task.tenant_id`, далее печать/резерв идут без проверки статуса задания:
```python
task = line.task
if task.tenant_id != tenant_id:
    raise MarkingCodeServiceError("line_not_found")
...   # никакой проверки task.status (draft/in_progress/done/...)
```
  Для сравнения, `list_pending_marking_lines` явно ограничивает
  `PackagingTask.status.in_(("draft", "in_progress"))` (`:2397`).
- **Проблема:** Можно напечатать/зарезервировать коды (перевести `available→reserved→printed`)
  для строки задания, которое уже завершено/отгружено, и тем самым израсходовать коды из пула
  «в никуда», исказив остаток (И3) и расход. DESIGN §5 предполагает печать на активном
  документе упаковки. Требует подтверждения acceptance по конкретному списку допустимых
  статусов задания, но отсутствие любой проверки `task.status` — явный пробел, особенно для
  reprint (повторная запись событий на закрытом документе).
- **Фикс:** Добавить guard в начале `print_codes_for_packaging_line` (и в reprint-ветке):
  `if task.status not in ("draft", "in_progress"): raise MarkingCodeServiceError("task_not_active")`.
  Список статусов согласовать с моделью `PackagingTask`.

---

## [MEDIUM] `approve_reprint_request` пишет `reprinted` без проверки статуса кода — событие на коде, который мог уйти в брак/отгрузку

- **Где:** `backend/app/services/marking_code_service.py:2141-2180` (`approve_reprint_request`).
- **Доказательство:**
```python
req = await _get_pending_reprint_request(session, tenant_id, request_id)
code = await session.get(MarkingCode, req.code_id)
if code is None or code.tenant_id != tenant_id:
    raise MarkingCodeServiceError("code_not_found")
...   # НЕТ проверки code.status (в отличие от replace_reprint_request, где есть STATUS_PRINTED)
await record_event(..., event_type=EVENT_REPRINTED, ...)
```
- **Проблема:** В «замене» (`replace_reprint_request:2195`) есть страж
  `if old_code.status != STATUS_PRINTED: raise ... "code_not_printed"`, а в «подтвердить и
  печатать тот же код» (`approve_reprint_request`) такого стража нет. Между созданием
  pending-заявки и её аппрувом код мог сменить статус (например, быть применён `applied`,
  отгружен `shipped` или помечен `defective` другим процессом). Тогда мы пишем событие
  `reprinted` (перепечать «того же валидного кода» по DESIGN §6 строка 323 — «если ещё валиден»)
  для кода, который уже невалиден. Журнал получает событие, противоречащее состоянию кода.
  Severity MEDIUM, т.к. статус кода тут не меняется (печатается тот же `printed`-код), но
  условие «если ещё валиден» из дизайна не проверяется.
- **Фикс:** Добавить проверку перед `record_event`:
  `if code.status != STATUS_PRINTED: raise MarkingCodeServiceError("code_not_printed")` —
  симметрично `replace_reprint_request`.

---

## Что проверено и признано корректным
- **И1 / И3 (остаток на пул, не на товар):** агрегаты статусов считаются по `pool_id`
  (`_pool_status_counts:1602-1624`, `list_pools`, `get_pool_detail`); вывод остатка на товар
  идёт через ручную M2M `marking_pool_products` (`list_inventory:1025-1041`). Сам остаток —
  на пул. Корректно (кроме автопривязки product_id, см. CRITICAL #1).
- **И4 (нет двойного списания КМ при N копиях):** в `print_codes_for_packaging_line` один код
  переводится `available→reserved→printed` ровно один раз, `copies` идёт только в событие/
  layout, `line.qty_marking_printed += quantity` (число кодов, не копий). Двойного списания
  самого кода нет. (Проблема только в метрике расхода — см. HIGH #1.)
- **И6 (событие на каждый переход):** проверены все смены статуса — `import`(imported),
  `print`(printed), `reprint`(reprinted), `apply`(applied via verify_pair), `defective`,
  `replaced`, `printed` новой замены — везде рядом есть `record_event`. Пропусков события при
  смене статуса не обнаружено.
- **`count_available_for_product` OR-фильтр (`:1100-1108`):** `or_(product_id==X, pool_id IN
  pools)` в рамках одного `WHERE` (не join) не даёт двойного счёта одной строки. ОК.
