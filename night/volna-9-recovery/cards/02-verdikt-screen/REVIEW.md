# Ревью · 02-verdikt-screen · повторная проверка ремонта

Вердикт: **CHANGES_REQUESTED**

ВЕРДИКТ: НАХОДКИ 1

## Находки

1. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_warehouse_sc.py:372-421` — предыдущая находка о недоказанной конкурентной границе не закрыта: `second_lock_boundary_entered.set()` вызывается **до** `await real_get_supply_for_update(...)`, поэтому ожидание на строке 417 доказывает только вход второго запроса в обёртку, но не выполнение и тем более блокировку на реальном `SELECT ... FOR UPDATE`. Конкретный сценарий: если вернуть преждевременный `commit()` в синхронизацию маркировки, второй task ставит событие, затем уступает управление на первом асинхронном вводе-выводе внутри `session.execute`; тестовый task сразу проходит проверки строк 418-419 и освобождает первый WB-вызов на строке 421. Первый запрос успевает завершить сдачу до продолжения второго, и финальные проверки одного WB-вызова и `supply_bad_status` остаются зелёными даже при возвращённой потере блокировки. Цена — тест, предназначенный защищать от двойной передачи в WB, не гарантированно краснеет при регрессии и оставляет повторную внешнюю операцию без надёжной автоматической защиты.

## Проверено и нормально

- Предыдущий `REVIEW.md` из коммита `be1bb4f0` использован как замороженный чек-лист; проверен только ремонтный продуктовый diff `be1bb4f0..2a3ced0e`. Изменения реализации ограничены разрешёнными файлами `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_autopoll_service.py` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_warehouse_sc.py`; изменения в `night/` являются стадийными артефактами.
- Первая прежняя находка закрыта: автополл на `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_autopoll_service.py:250-256` явно передаёт `persist_started_marker_outside_caller=False`, поэтому маркер записывается через `flush()` в уже удерживаемую транзакцию без конкурирующей `SessionLocal` и без преждевременного `commit()`.
- `ruff` для двух изменённых продуктовых файлов прошёл; полностью прошли `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_kiz.py` (`48 passed`) и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_warehouse_sc.py` (`12 passed`). Зелёный конкурентный тест не снимает находку выше, потому что его синхронизация не доказывает удержание блокировки.
- Формат API, остатки, резервы, складские движения и экранные правила ремонтный diff не меняет; новых операторских блокировок нет. Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.
