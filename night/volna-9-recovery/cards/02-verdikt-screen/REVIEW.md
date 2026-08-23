# Ревью · 02-verdikt-screen · повторная проверка ремонта

Вердикт: **CHANGES_REQUESTED**

ВЕРДИКТ: НАХОДКИ 1

## Находки

1. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_warehouse_sc.py:379` — предыдущая находка о недоказанной конкурентной границе не закрыта: обработчик `before_cursor_execute` ставит событие **до** вызова DBAPI `cursor.execute`, а после пробуждения тест проверяет только, что весь HTTP-task ещё не завершился, и сразу освобождает первый WB-вызов на строке 419. Здесь нет наблюдения `after_cursor_execute` или другого барьера, который доказал бы, что второй `SELECT ... FOR UPDATE` действительно остался незавершённым до освобождения первого запроса. Более того, штатный контур файла работает на SQLite, где `FOR UPDATE` не создаёт строковую блокировку. Конкретная негативная проверка из `FEATURES.md` воспроизведена без правки рабочего дерева: `_record_wb_sync_started` в памяти процесса после штатного `flush()` делал преждевременный `await session.commit()`, освобождая транзакцию сдачи до `deliver_marketplace_supply`; изменённый тест остался зелёным три запуска из трёх (`1 passed` каждый). При таком сценарии событие успевает разбудить тест до завершения второго SQL-запроса, тест освобождает первый запрос, а итоговые проверки снова видят один WB-вызов и `supply_bad_status`, хотя защищаемая блокировка уже была снята. Цена — тест, предназначенный не допустить двойную передачу поставки в Wildberries, остаётся зелёным при возврате именно этой регрессии и не защищает внешнюю операцию от повтора.

## Проверено и нормально

- Предыдущий `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/REVIEW.md` из коммита `a84098d3` использован как замороженный чек-лист; проверен только ремонтный diff `a84098d3..5469012b`. Единственный продуктовый файл ремонта — разрешённый `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_warehouse_sc.py`; изменения в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/` являются стадийными артефактами и не считались выходом за границы.
- Полностью прочитаны ремонтный продуктовый diff, контракт, карта задевания, реестр S-03 и назначенные кейсы `S-03-TC-014`–`S-03-TC-018`, `S-14-TC-001`, `S-15-TC-001`. Ремонт не меняет экранный контракт, API, остатки, резервы, складские движения или формат данных и не вводит новых операторских блокировок.
- Обычный целевой сценарий прошёл (`1 passed`), весь `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_warehouse_sc.py` прошёл (`12 passed`), `ruff check --no-cache` для него также прошёл. Зелёные штатные прогоны не снимают находку, потому что обязательная негативная мутация остаётся зелёной.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.
