# Вердикт: BLOCKED

В diff нет реализации карточки: изменены только описания тест-кейсов, а обязательное
продуктовое правило для локального кода, отсутствующего у Wildberries, и судьба уже
потраченного кода пула владельцем не определены. Поэтому содержательно принять карточку
до появления решения владельца и отдельной backend-реализации нельзя.

## Находки

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-1-01/backend/app/services/fbs_marking_service.py:507` — локальная маркировка, для которой Wildberries не вернул `metaDetails`, остаётся в прежнем `meta_status`; затем на строке 526 готовность снова считается по этому старому состоянию — если клиент удалил код у WB, а локально он ранее был `accepted`, оператор по-прежнему получает ложную готовность к передаче. Цена: заказ с неподтверждённой маркировкой может уйти дальше складского процесса; основной дефект карточки не исправлен.

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-1-01/backend/app/services/fbs_marking_service.py:138` — таблица решений WB не содержит `optional`, хотя контракт карточки признаёт `filled` и `optional` допустимыми — при ответе `metaDetails.decision = "optional"` статус превращается в `unknown`, и корректный заказ блокируется вместо допуска. Цена: оператор не сможет передать заказ, который Wildberries разрешил передавать.

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-1-01/backend/app/services/fbs_marking_service.py:492` — пакетный метод всегда вызывается с массивом из одного `wb_order_id`; других production-вызовов `fetch_marketplace_orders_meta_batch` нет — при сверке поставки из 25 или 100 заданий система не делает требуемую пачку, а вынуждена обращаться к WB по одному заказу. Цена: лишние внешние запросы, риск лимита WB и незавершённой сверки части поставки.

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-1-01/backend/tests/test_fbs_marking.py:128` — единственный тест синхронизации проверяет устаревший объект `meta` и статус `checking`, но не рабочий `metaDetails`, решение `optional`, отсутствие локального кода в ответе WB и судьбу потраченного кода пула — все три описанных выше дефекта останутся зелёными. Цена: тестовый набор не защищает контракт карточки и создаёт ложное подтверждение исправления.

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-1-01/tests/cases/S-05.md:13` — файл изменён вне границ S-05: поле `files` в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-1-01/frontend/screens.registry.json` разрешает для этого экрана только `frontend/src/screens/ff/FfHonestSignPage.tsx` плюс `frontend/src/ui-kit/` — при ночном слиянии карточка заносит несогласованный файл общей базы кейсов. Цена: карточка нарушает изоляцию наряда и может столкнуться с параллельной волной.

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-1-01/tests/cases/S-14.md:13` — файл изменён вне границ S-14, у которого поле `files` в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-1-01/frontend/screens.registry.json` пусто — при ночном слиянии карточка меняет неразрешённый общий файл. Цена: тот же риск пересечения работ и нарушение механизма экранной изоляции.

## Проверено и нормально

- Полностью прочитан рабочий diff: кроме двух файлов `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-1-01/tests/cases/S-05.md` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-1-01/tests/cases/S-14.md` изменений реализации нет; посторонние правки приложения в карточку не попали.
- Сценарии `filled`, отсутствующего ответа WB и запрета ложного зелёного статуса в самих описаниях кейсов сформулированы предметно и не закрепляют неутверждённое имя состояния расхождения.
- Ошибка внешнего API в существующем потоке не преобразуется в успешный результат: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-1-01/backend/app/services/fbs_marking_service.py:639` переводит ошибку WB в доменную ошибку для вызывающего слоя.
- Нового операторского запрета в коде или UI diff не добавлено, поэтому новый файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-1-01/docs/blockers/S-05.md` или `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/zadachi-2026-08-21-20260821-r04/lane-1-01/docs/blockers/S-14.md` в рамках этого diff не требуется.
