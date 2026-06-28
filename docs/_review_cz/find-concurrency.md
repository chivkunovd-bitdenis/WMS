# Ревью: измерение «concurrency» (Честный Знак)

Диапазон: `4e82c6b..HEAD`. Скоуп: `marking_code_service.py`, `document_number_service.py`, `alembic/versions`.
Стек: FastAPI + SQLAlchemy async + Postgres. Изоляция БД — **дефолтная READ COMMITTED** (в `backend/app/db/session.py:14` `create_async_engine` без `isolation_level`), это важно для анализа `with_for_update`.

---

## 1. Выдача кодов из пула: `FOR UPDATE` + `LIMIT` без `SKIP LOCKED` → ложный дефицит под параллелью (НЕ двойная выдача)
**Severity: HIGH**
**Файл:** `backend/app/services/marking_code_service.py:1211-1223` (`print_codes_for_packaging_line`), тот же паттерн в `:2215-2227` (`replace_reprint_request`).

**Доказательство:**
```python
stmt = (
    select(MarkingCode)
    .where(... MarkingCode.status == STATUS_AVAILABLE, code_filter)
    .order_by(MarkingCode.created_at.asc())
    .limit(target_qty)
    .with_for_update()          # <-- нет .with_for_update(skip_locked=True)
)
```

**Почему важно:** под READ COMMITTED `FOR UPDATE` + `LIMIT` **без** `SKIP LOCKED` означает: два параллельных упаковщика (T1, T2) выбирают по `ORDER BY created_at LIMIT N` ОДНИ И ТЕ ЖЕ верхние строки. T2 блокируется на локах T1. После коммита T1 эти строки уже `STATUS_PRINTED`; Postgres под READ COMMITTED перечитывает предикат при захвате лока, строки отсеиваются — поэтому **двойной выдачи нет** (это плюс), НО T2 получает на руки **меньше N** строк, хотя в пуле есть другие доступные коды за пределами окна `LIMIT`. Итог: ложный `shortage` при `allow_partial=False` (`:1227` early-return с rollback) или недобор копий — упаковщик видит «нет кодов», хотя они есть. Чем больше параллельных упаковщиков на один пул, тем чаще ложный дефицит.

**Фикс:** добавить `skip_locked=True`: `.with_for_update(skip_locked=True)`. Тогда T2 пропускает залоченные строки T1 и сразу берёт следующие доступные. Это и есть штатный паттерн «очередь выдачи из пула». Учесть: при `SKIP LOCKED` число выбранных строк может быть < `target_qty` из-за конкурентных локов — текущая логика `shortage`/`allow_partial` это уже обрабатывает, но при `allow_partial=False` стоит делать повторную попытку (retry) перед тем как вернуть дефицит, чтобы не возвращать ложный shortage из-за временно залоченных строк.

---

## 2. `print_all_for_packaging_task` не атомарен: коммит на каждую строку
**Severity: HIGH**
**Файл:** `backend/app/services/marking_code_service.py:1536-1567` (цикл) + `:1278` (`session.commit()` внутри `print_codes_for_packaging_line`).

**Доказательство:** `print_all` в цикле по строкам вызывает `print_codes_for_packaging_line(...)`, а та в конце делает `await session.commit()` (`:1278`). Значит каждая строка коммитится отдельной транзакцией.

**Почему важно:** «напечатать всё для задания» подразумевается атомарной операцией. При параллельной выдаче (другой упаковщик/реплейс выгребает пул между строками) или при ошибке на N-й строке — первые строки уже закоммичены и коды списаны (`STATUS_PRINTED`, `qty_marking_printed++`), а на следующей строке прилетает `shortage`/исключение. Результат — частично отпечатанное задание без отката: коды израсходованы, но задание не завершено, повторный вызов упрётся в `already_printed_use_reprint` (`:1190`). Под параллелью окно между коммитами строк — окно для гонки за общий пул (если несколько SKU делят один пул по GTIN).

**Фикс:** вынести границу транзакции на уровень `print_all` (один commit в конце), а `print_codes_for_packaging_line` сделать без внутреннего commit (например, флаг `_autocommit=False` или использовать `begin_nested`/savepoint на строку). Тогда либо всё задание печатается, либо откатывается целиком.

---

## 3. Превью-проверка дефицита ≠ реальной выдаче: TOCTOU в `print_all` (non-partial)
**Severity: MEDIUM**
**Файл:** `backend/app/services/marking_code_service.py:1506-1531` (превью без локов) → `:1536-1567` (реальная выдача), счёт в `count_available_for_product` `:1091-1110`.

**Доказательство:** при `allow_partial=False` сначала идёт цикл `_preview_line_print` (использует `count_available_for_product`, БЕЗ локов), и если ни у кого нет shortage — переходим к реальной выдаче. Между превью и выдачей нет общей транзакционной защиты, а строки коммитятся по одной (см. находку 2).

Дополнительно расходятся фильтры: `count_available_for_product` считает по `or_(product_id==X, pool_id IN pools)` (`:1107`), а реальная выдача — только `pool_id.in_(pool_ids)` если пул есть, иначе только `product_id` (`:1205-1209`). Превью может посчитать БОЛЬШЕ кодов, чем реально выберет выдача → guard «нет дефицита» проходит, а реальная выдача упирается в shortage уже после частичного коммита строк.

Ещё: если несколько строк задания ссылаются на один пул (общий GTIN), `count_available_for_product` считает доступность для каждой строки **независимо** от того же пула — превью двух строк по 50 при 60 доступных кодах обе пройдут проверку (60≥50), а суммарно нужно 100.

**Почему важно:** ложное «всё ок» в превью с последующим частичным/неконсистентным результатом под параллелью и при общих пулах.

**Фикс:** считать доступность пула с учётом уже «забронированных» в этом же вызове строк (агрегировать потребность по пулам), и согласовать фильтр превью с фильтром выдачи. Идеально — выполнять превью и выдачу в одной транзакции с `FOR UPDATE SKIP LOCKED`.

---

## 4. `verify_pair_and_apply`: чтение без блокировки → двойное применение
**Severity: MEDIUM**
**Файл:** `backend/app/services/marking_code_service.py:2328-2360`.

**Доказательство:**
```python
code = (await session.execute(stmt)).scalar_one_or_none()  # без with_for_update
...
if code.status != STATUS_PRINTED:
    return VerifyPairResult(match=True, applied=False, code_id=code.id)
code.status = STATUS_APPLIED
code.applied_at = now
await record_event(... EVENT_APPLIED ...)
await session.commit()
```

**Почему важно:** два параллельных скана одной пары читают `status == PRINTED`, оба проходят проверку, оба пишут `STATUS_APPLIED` и **два** события `EVENT_APPLIED` в журнал. Идемпотентность применения нарушена — в журнале дубль applied, метрики/история кода задваиваются. Нет уникального ограничения на пару (code_id, event_type=applied), которое бы спасло на уровне БД.

**Фикс:** выбирать код с `.with_for_update()` и перепроверять `status == STATUS_PRINTED` под локом перед сменой статуса (классический lock-then-check). Альтернативно — условный UPDATE `... WHERE status='printed'` и проверять rowcount.

---

## 5. Идемпотентность импорта: SELECT-then-INSERT под уникальным ключом → срыв всей транзакции при гонке
**Severity: MEDIUM**
**Файл:** `backend/app/services/marking_code_service.py:910-937` (`import_marking_codes`); ограничение `uq_marking_codes_tenant_cis` есть (`models/marking_code.py:173`, миграция `20260616_0041_marking_codes.py:96`).

**Доказательство:** на каждый CIS — `SELECT id WHERE tenant_id, cis_code` (`:911-916`), если нет — `session.add(code); await session.flush()` (`:929-930`). Никакого `ON CONFLICT`.

**Почему важно:** два параллельных импорта одного и того же CIS (например, повторный/дублирующий аплоад одним кликом дважды, или ретрай) проходят SELECT оба, затем второй `flush()` ловит `IntegrityError` по `uq_marking_codes_tenant_cis`. Так как импорт идёт в одной транзакции на весь батч и savepoint'ов нет, ошибка **абортит весь батч** (включая уже добавленные коды, `MarkingCodeImport`, выданный `document_number`). Импорт не идемпотентен и не устойчив к параллельным дублям: вместо «пропустить дубликат» получаем падение всей загрузки.

**Фикс:** заменить check-then-act на `insert(...).on_conflict_do_nothing(index_elements=["tenant_id","cis_code"])` с `.returning(MarkingCode.id)` для подсчёта реально вставленных (как сделано идиоматично в `document_number_service.next_document_number`). Это убирает гонку и делает импорт идемпотентным на уровне БД.

---

## 6. `next_document_number`: атомарный upsert — ПОДТВЕРЖДЕНО корректно (контр-находка)
**Severity: NONE (подтверждение)**
**Файл:** `backend/app/services/document_number_service.py:59-76`.

**Доказательство:** счётчик инкрементируется одним стейтментом
`insert(...).on_conflict_do_update(index_elements=[tenant_id, doc_type, date], set_={counter: counter+1}).returning(counter)` поверх уникального ключа `uq_document_sequences_tenant_type_date` (миграция `20260626_0042:...UniqueConstraint(tenant_id, doc_type, date)`; модель мапит `document_date` на колонку `"date"`, `index_elements` ссылается на имя колонки `"date"` — согласовано).

**Почему важно:** это правильный паттерн — атомарный read-modify-write на стороне БД, без TOCTOU, два параллельных запроса получают разные счётчики, дублей номеров нет. Замечание (не баг): функция не коммитит сама — корректность зависит от того, что вызывающий код коммитит в той же транзакции, где номер присвоен сущности (`assign_document_number_if_missing` только проставляет атрибут). Стоит покрыть тестом «N параллельных next_document_number → N уникальных номеров».

---

## Сводка приоритетов
1. (HIGH) Нет `SKIP LOCKED` при выдаче из пула → ложный дефицит под параллелью — `:1221`, `:2225`.
2. (HIGH) `print_all` не атомарен (commit на строку) → частично отпечатанные задания — `:1278` + `:1536`.
3. (MEDIUM) TOCTOU превью↔выдача + расхождение фильтров/двойной счёт по общему пулу — `:1506`, `:1107` vs `:1207`.
4. (MEDIUM) `verify_pair_and_apply` без лока → двойное применение/дубль события — `:2328`.
5. (MEDIUM) Импорт SELECT-then-INSERT → срыв батча при параллельном дубле — `:911`.
6. (NONE) `next_document_number` — атомарный счётчик корректен.
