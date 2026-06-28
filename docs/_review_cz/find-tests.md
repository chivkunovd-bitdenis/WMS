# Ревью тестов (ЧЗ / Честный Знак) — измерение ТЕСТЫ

## Резюме
Покрытие в целом ХОРОШЕЕ: нехватка, частичная печать, tenancy, shift-lead-гейт, события, раскладка-пары — есть. Найдено **6 находок**: 1 HIGH (нет теста на конкурентную/параллельную выдачу кодов из пула — ключевой инвариант И4), 2 MEDIUM (слабый ассерт в `replace`-тесте — не проверяет defective/printed/остаток; нет негативного теста на shift-lead-гейт для `replace`/`approve`-действий) и 3 LOW (тавтологичные/неполные ассерты порядка и `unread_count`). Критичные сценарии «нехватка», «брак→замена (служебный код)», «tenancy» функционально покрыты, но пробел по «гонкам» — реальный.

---

## [HIGH] Нет теста на конкурентную (параллельную) выдачу кодов из пула — И4 / acceptance T1.2 не проверен

- **Где:** `backend/tests/test_marking_print_pool.py:143` (`test_sequential_print_does_not_reuse_codes`) — единственный «не пересекаются» тест; `backend/app/services/marking_code_service.py` использует `with_for_update` при выборке кодов.
- **Доказательство:**
```python
# test_marking_print_pool.py — печать строк выполняется СТРОГО последовательно (await за await):
    codes_a = await _print_line(line_a)
    codes_b = await _print_line(line_b)
    all_codes = codes_a + codes_b
    assert len(all_codes) == len(set(all_codes))
```
Никакого `asyncio.gather` — две печати никогда не идут одновременно. Для сравнения, конкурентность ЕСТЬ в `test_document_number_service.py:104` (`await asyncio.gather(*[one() for _ in range(12)])`), то есть паттерн в проекте известен, но к выдаче кодов из пула не применён.
- **Проблема:** Acceptance T1.2 прямо требует: «параллельные печати не пересекаются (reserve/`with_for_update`)». Инвариант И4 «Один КМ расходуется один раз». Последовательный тест НЕ проверяет блокировку `with_for_update`: даже если её убрать, последовательный тест пройдёт (т.к. между запросами есть commit). Регрессия «двойная выдача одного кода при гонке» останется незамеченной.
- **Фикс:** Добавить тест с `asyncio.gather` двух печатей по разным строкам одного пула при ограниченном остатке (например 3 кода, две строки по 2) и проверить, что объединённый набор `codes` не содержит дубликатов и суммарно выдано ≤ остатка. По аналогии с `test_next_document_number_concurrent_no_duplicates`.

---

## [MEDIUM] `test_replace_reprint_request_clears_queue` не проверяет результат замены (defective / printed / остаток −1)

- **Где:** `backend/tests/test_marking_reprint_defect.py:181`–207 (`test_replace_reprint_request_clears_queue`).
- **Доказательство:**
```python
    body = replaced.json()
    assert body["status"] == "approved"
    assert body["replacement_code_id"] is not None
    ...
    assert queue.json()["requests"] == []
```
Сервис `replace_reprint_request` (`marking_code_service.py:2232`–2249) делает: `old_code.status = STATUS_DEFECTIVE`, `old_code.replaced_by_code_id = new_code.id`, `new_code.status = STATUS_PRINTED`, плюс события `defective`/`replaced`/`printed`. Ничего из этого тест не ассертит.
- **Проблема:** Acceptance T1.3 буквально: «старый код `defective`, выдан новый `printed`, остаток пула −1 (за новый), события записаны». Тест проверяет только статус запроса и опустевшую очередь — это «факт записи», а не USER-VISIBLE исход. Если регрессия не переведёт старый код в `defective`, не привяжет `replaced_by_code_id`, не спишет код из пула или не запишет события — тест останется зелёным.
- **Фикс:** Дочитать из БД `old_code` (== `STATUS_DEFECTIVE`, `replaced_by_code_id == replacement_code_id`), `new_code` (== `STATUS_PRINTED`, привязан к `packaging_task_line_id`), проверить наличие событий `defective`, `replaced`, `printed`, и что `available_count` пула уменьшился на 1 (был 1 свободный из 2 импортированных).

---

## [MEDIUM] Нет негативного теста shift-lead-гейта на действиях `replace` / `approve` / `reject`

- **Где:** `backend/tests/test_shift_lead.py:71` покрывает только `GET /reprint-requests`; `test_marking_reprint_defect.py:139` (`test_defect_requires_packaging_access`) покрывает только `defect`.
- **Доказательство:** В `test_shift_lead.py` единственный негативный кейс:
```python
    forbidden = await async_client.get(
        "/operations/marking-codes/reprint-requests",
        headers=no_perm,
    )
    assert forbidden.status_code == 403
```
Мутирующие действия очереди — `POST …/reprint-requests/{id}/replace` (и, судя по `approve_reprint_request`/reject в сервисе, `…/approve`, `…/reject`) — НЕ имеют ни одного теста на 403 без права `shift_lead`.
- **Проблема:** TASKS T2.1: «Тест: pytest: без права — 403 на действиях перепечатки». Гейт проверен на чтении очереди, но самые опасные операции (выдать новый код, списать в брак под чужим именем) негативным кейсом не закрыты. Если на `replace`/`approve` забыли навесить `require_shift_lead`, тесты этого не поймают.
- **Фикс:** Добавить тест: упаковщик без `shift_lead` создаёт `defect` (он имеет `packaging`), затем под не-shift-lead аккаунтом дёргает `…/replace` и `…/approve` и `…/reject` → ожидать 403 на каждом.

---

## [LOW] `test_print_all_aggregates_lines_in_order` — тавтологичная проверка «в порядке», нет проверки раскладки/пары

- **Где:** `backend/tests/test_marking_print_all.py:124`–126.
- **Доказательство:**
```python
    assert body["lines"][0]["quantity"] == 2
    assert body["lines"][1]["quantity"] == 3
```
Строки задачи создавались с qty 2 и 3 в этом же порядке, поэтому ассерт лишь повторяет вход. Имя теста — «in_order», но никакой связи `lines[i]` ↔ конкретный `line_id` (порядок строк именно как в задаче) не проверяется, как и поле `layout` в ответе print-all.
- **Проблема:** «in_order» де-факто не проверяется (агрегат мог бы отдать строки в любом порядке и тест бы прошёл при совпадении qty). Раскладка (`layout.units`, последовательность блоков, пара внутри единицы) на уровне backend для print-all не ассертится — покрыта только e2e (`ff-marking-print-constructor.spec.ts:118`–125), что хрупко.
- **Фикс:** Сопоставить `body["lines"][i]["packaging_task_line_id"]` с исходными `line_ids[i]`; задать строки с разным qty в обратном порядке, чтобы порядок был содержательным; добавить ассерт структуры `layout`/`units` в ответе.

---

## [LOW] `test_low_stock_job_notifies_seller`: проверяет `unread_count == 0` под админом — слабый сигнал получателя

- **Где:** `backend/tests/test_marking_forecast.py:138`–149.
- **Доказательство:**
```python
    notes = await async_client.get("/operations/notifications", headers=h)  # h = админ
    assert notes.json()["unread_count"] == 0
    ...
    note = (... Notification.type == "marking_low_stock" ...).scalar_one()
    assert note.recipient_id == seller_id
```
- **Проблема:** Ассерт `unread_count == 0` под админом доказывает лишь, что админу уведомление НЕ пришло. Что селлер реально ВИДИТ уведомление через API (`GET /operations/notifications` под `seller_headers`) — не проверяется; берётся напрямую из БД. USER-VISIBLE исход для целевого получателя (селлера) не подтверждён через эндпоинт.
- **Фикс:** Залогиниться селлером (паттерн `_create_seller` есть в `test_notifications.py`) и проверить, что `GET /operations/notifications` под селлером отдаёт это уведомление с `unread_count == 1` и `severity == "critical"`.

---

## [LOW] `test_print_records_printed_and_reprint_records_reprinted`: условный ассерт document_number может «проглотить» отсутствие номера

- **Где:** `backend/tests/test_marking_code_events.py:142`,162–163.
- **Доказательство:**
```python
    doc_number = task.json().get("document_number")
    ...
        if doc_number:
            assert all(e.document_number == doc_number for e in printed_events)
```
- **Проблема:** Acceptance T1.5/T1.2 требует `document_number=УПАК-…` в событии `printed`. Если задача по какой-то причине вернёт `document_number == None` (регрессия присвоения номера), `if doc_number:` пропустит проверку целиком — тест останется зелёным при реальной поломке нумерации. Это маскирующий условный ассерт.
- **Фикс:** Получать `document_number` после печати из задачи (он присваивается при печати, см. `test_marking_print_pool.py:139` где он `is not None`) и ассертить без `if`: `assert doc_number is not None` и `all(e.document_number == doc_number ...)`.

---

## Матрица покрытия acceptance-сценариев

| Сценарий | Покрыт? | Тест / Пробел |
|---|---|---|
| Нехватка кодов (печать > остатка) | ДА | `test_marking_codes.py:141` (`shortage==2`, `codes==[]`, `quantity==0`); `test_marking_print_all.py:145` |
| Частичная печать (`allow_partial`) | ДА | `test_marking_codes.py:205` (`quantity==1`, `len(codes)==1`); `test_marking_print_all.py:181` |
| Гонки / конкурентная выдача из пула | **НЕТ (ПРОБЕЛ)** | Только последовательный `test_marking_print_pool.py:143`. Конкурентность есть лишь у document_number. → **HIGH** |
| Брак → замена (старый defective, новый printed, −1) | ЧАСТИЧНО | `test_marking_reprint_defect.py:181` проверяет только status/queue; не проверяет defective/printed/остаток → **MEDIUM** |
| Брак → создание pending-запроса + дедуп | ДА | `test_marking_reprint_defect.py:106` (pending, дубликат → 422 `reprint_already_pending`) |
| Tenancy / изоляция (user/seller/ff-role) | ДА | `test_notifications.py:78,106,131,220`; `test_marking_pool_products.py:128` (`product_seller_mismatch`); `test_marking_credentials_api.py` (no secrets in response, 403 non-admin) |
| shift_lead-гейт перепечатки | ЧАСТИЧНО | `test_shift_lead.py:71` (GET 403) + `defect` 403. Нет негатива на `replace`/`approve`/`reject` → **MEDIUM** |
| Раскладка печати (пара внутри единицы, код одинаковый) | ДА (e2e), частично backend | e2e `ff-marking-print-constructor.spec.ts:118-125` (chip-1-0/1-1 = ЧЗ/ЧЗ, Этикетка/ЧЗ); backend `test_marking_print_pool.py:116` проверяет echo `layout.units`. print-all backend `layout` не ассертит → LOW |
| scan-print: 1 единица за скан, разные коды, complete | ДА | `test_marking_scan_print.py:12` (qty==1, `codes[0]!=codes[1]`, 3-й → `marking_complete`) |
| verify-pair: match→applied, mismatch, идемпотентность | ДА | `test_marking_verify_pair.py:88,116,140` (статус `applied`, событие `applied`, повтор `applied==False`) |
| pending-marking worklist | ДА | `test_marking_pending.py:12` (total 1→0 после печати, `qty_remaining`) |
| Импорт: пул по GTIN, дедуп, document_number, события | ДА | `test_marking_import_pools.py` (accepted/skipped, `duplicate`, ЗАГРКМ-, события imported) |
| Forecast / low-stock | ДА (с LOW-замечанием) | `test_marking_forecast.py` (`consumption_7d`, `forecast_days`, нотификация селлеру) |
| События при печати/перепечатке (И6) | ДА | `test_marking_code_events.py:76` (printed×2 copies==2, reprinted copies==1) |

**Пробелы по критичным сценариям:** гонки (HIGH), полнота проверки брак→замена (MEDIUM), shift-lead-гейт на мутациях очереди (MEDIUM).
