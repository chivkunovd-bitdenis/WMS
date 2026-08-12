# TL-F001 — Одновременное завершение одной приёмки удваивает складской остаток

## Паспорт

- Finding ID: `TL-F001`
- Title — пользовательский результат, а не предполагаемая причина: два оператора одновременно завершают один факт приёмки, после чего WMS показывает на складе вдвое больше товара
- Class: `BUG`
- Severity: P0
- Area / scenario ID: inbound receiving / inventory ledger / concurrent completion
- First reviewer / independent verifier: teamlead / second clean reproduction by teamlead; orchestrator cross-check pending
- Environment and SHA: staging API, deployed SHA represented by orchestrator as `44fe72e3525332bb01fd76ba420f9cecbdaac6ba`; critical inbound code is identical in etalon `a39530c5137deb31e189c2136b613d01093af87b`
- Role / tenant / seller test IDs: synthetic administrator; fresh isolated tenant `TL-P0-A`, fresh isolated tenant `TL-P0-B`; no seller
- WB mode: N/A

## Ожидаемое поведение

- Источник правды, точный раздел или официальная ссылка: inventory movement model documents a positive delta as one receipt (`backend/app/models/inventory_movement.py:29-55`); the inbound line fact is exactly one unit; the system-wide charter requires quantity conservation and safe retry/concurrency.
- Дата проверки внешнего источника: N/A
- Короткое ожидаемое поведение: completion must be single-effect. With a received fact of one, concurrent completion may return one success plus one conflict/idempotent read-back, but it must produce exactly one `+1` movement and a balance of one.

## Фактическое поведение и воспроизведение

- Предусловия и физический контекст склада: a fresh tenant, one warehouse, one synthetic product, one inbound request with one line `expected_qty=1`, and one scan establishing fact `1`; no WB or shared data.
- Шаги от чистого состояния: register isolated tenant → create warehouse/product/request/line → submit → scan once → verify document is `receiving` with fact `1` → concurrently send two `POST /operations/inbound-intake-requests/{id}/complete-receiving` calls from separate clients → read document, inventory summary and movements.
- Что видно пользователю: both callers receive `HTTP 200` and a `sorting` document; the inventory summary shows two units although the document still says one.
- Что произошло с данными, задачей, печатью или WB: WMS committed two `inbound_intake` movements of `+1` and an inventory balance of `2`; document fact remained `1`. No WB call occurred.
- Повторяемость: attempts / reproduced: `2 / 2`, each in a newly registered tenant.

## Доказательства

- `before` screenshot: N/A — API concurrency verification, no UI claim
- `action` screenshot: N/A — API concurrency verification, no UI claim
- `result` screenshot: N/A — API concurrency verification, no UI claim
- `reload` screenshot: N/A — server read-back is recorded below
- negative/failure screenshot: N/A
- sanitized request/response or trace ID: `evidence/TL-P0-double-complete-receiving.md`; in each attempt both responses were `200/sorting`
- DB/read-back proof with non-secret IDs: isolated product balance `2`; movements `[+1,+1]`; document `actual_qty=1`, `sorting_remaining_qty=1`, recorded in the evidence card
- relevant logs without secrets: not available from staging
- code path `file:line`: `backend/app/services/inbound_intake_service.py:612-652` reads an unlocked request, validates status, transitions it and applies the receipt; `backend/app/services/inventory_service.py:671-693` always appends/adjusts; `backend/app/models/inventory_movement.py:29-57` has no uniqueness guard for one inbound receipt per line
- existing automated test and its result: sequential completion tests exist in `backend/tests/test_inbound_intake_api_be03.py`; no concurrent double-complete test was found. Local functional tests were prohibited and were not run for this verification.

## Ущерб и граница

- Кто страдает и как часто: warehouses where two operator tabs/devices or a network retry complete the same reception concurrently; the race window is the full read/stock-update/commit transaction.
- Результат: неверные данные / тупик / двойная операция / утечка / лишний труд / UX noise: wrong stock and a double inventory operation. The phantom unit can later be reserved, picked, reported, or synchronized downstream.
- Workaround and its cost: operationally serialize completion of every inbound request and manually reconcile ledger/balance after suspected duplicate clicks; this is fragile and requires inventory correction.
- Почему это дефект, а не новая функция: the same immutable fact is posted twice and violates quantity conservation; no new workflow is requested.
- Что точно не входит в эту находку: sorting draft lost updates, WB delivery idempotency, and general button debouncing.

## Анализ причины

- Proven root cause / hypothesis / unknown: **proven root cause.** `complete_receiving` loads the request without a row lock or version compare. Both transactions observe a receiving state and each appends the same receipt effect before committing.
- Evidence separating cause from correlation: two isolated repetitions produce the same two successful responses, two movement rows and doubled balance. Static paths contain no request lock, completion idempotency record or movement uniqueness constraint. The relevant paths are identical in `44fe72e` and `a39530c`.
- Retry, concurrency and recovery implications: an ambiguous/lost response retried during the first in-flight completion can create the same double effect. A later document reload does not expose the duplication because its fact remains one; recovery needs ledger/balance reconciliation.
- Tenant/seller/security implications: the damage stays tenant-scoped in the reproduced case, but it corrupts authoritative tenant inventory and any seller allocation based on it.

## Критерий закрытия без проектирования решения

- Given: a receiving inbound request with one line whose accepted fact is one
- When: two clients concurrently complete that same request, or one client retries while the first call is still in flight
- Then — visible result: callers get one coherent completed state; no caller is told a second stock effect succeeded
- And — data/WB result: exactly one `inbound_intake +1` movement exists and the product balance is exactly one; no WB operation is involved
- Negative / retry / isolation requirement: repeat on PostgreSQL under true concurrency, including lost-response retry, and prove another tenant remains unchanged

## Проверка минимальности будущего исправления

- Можно ли восстановить инвариант существующими сущностями и экраном? Yes. The existing request status and movement reference provide the business identity of the completion.
- Какое минимальное изменение поведения требуется? Make transition-and-receipt a single guarded database effect and make repeat/concurrent completion return a stable result or conflict without another movement.
- Какая новая сущность/настройка предлагалась и почему она пока запрещена? None proposed; solution design is intentionally outside this finding.

## Вердикт оркестратора

- Accepted / evidence missing / duplicate / conflict / out of scope: pending orchestrator adjudication; complete teamlead evidence
- Duplicate of: none in teamlead ledger
- Second reproduction for P0/P1: complete — fresh `TL-P0-B`, same `200/200`, movement sum `+2`, balance `2`
- Queue status: proposed P0 stop-ship
