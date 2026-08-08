# ARCHITECTURE.md — живая арх-карта WMS + реестр знаний

> Наполняется по [`LEARNING.md`](LEARNING.md): на гейтах задач (человек объясняет → сверка с кодом)
> и на добивках. Здесь фиксируется, **как система устроена на самом деле** (подтверждённо, с `file:line`),
> и что человек ещё не знает (реестр дыр). Ничего не пишем «по памяти модели» — только подтверждённое кодом.
>
> Пути в колонке «Где в коде» — **первичная прикидка**, статус у всех `не подтверждено`, пока не сверили
> на гейте. Уточняем и проставляем `file:line` при первом разборе соответствующей подсистемы.

## Подсистемы (статус понимания человеком)
Статусы: `ok` (объяснил, сверено с кодом) · `плаваю` (объяснял с ошибками) · `не подтверждено` (ещё не проверяли).

| Подсистема | Где в коде (прикидка, сверить на гейте) | Статус |
|---|---|---|
| Мультитенантность / изоляция данных | `backend/app/models/tenant.py`, `seller.py`, `deps.py` | не подтверждено |
| Аутентификация / роли / порталы | `backend/app/api/auth.py`, `services/auth_service.py` | не подтверждено |
| Приёмка (селлер → ФФ) | `backend/app/api/inbound_intake.py`, `services/inbound_intake_service.py` | не подтверждено |
| Отгрузка на МП (ФФ → маркетплейс) | `backend/app/models/marketplace_unload.py`, `services/marketplace_unload_*` | не подтверждено |
| Остатки / движения / резервы | `backend/app/models/inventory_*`, `services/inventory_service.py` | не подтверждено |
| Адресное хранение (ячейки/стеллажи/короба) | `backend/app/models/storage_location.py`, `warehouse_*`, `services/sorting_location_service.py` | не подтверждено |
| Упаковка (задания, биллинг) | `backend/app/models/packaging_task.py`, `services/packaging_task_service.py` | не подтверждено |
| Честный Знак (коды маркировки, печать) | `backend/app/models/marking_code.py`, `services/marking_*` | не подтверждено |
| Печать / конструктор шаблонов | `backend/app/models/print_template.py`, `services/print_template_service.py` | не подтверждено |
| Интеграция Wildberries (import-only) | `backend/app/services/wildberries_*`, `api/wildberries_integration.py` | не подтверждено |
| Фоновые задачи (Celery / BackgroundTasks) | `backend/app/tasks/`, `services/background_job_service.py` | не подтверждено |
| Фронтенд-портал ФФ (MUI) | `frontend/src`, эталон `FfProductsCatalogScreen.tsx` | не подтверждено |
| Мобильный ТСД (Android) | `mobile/`, состояние в `mobile/docs/PROGRESS.md` | не подтверждено |

## Реестр дыр (что подтянуть)
Порядок разбора — сверху вниз (сверху самое давнее/важное). Закрытая дыра → статус `закрыто`, тема в таблице выше → `ok`.

| # | Подсистема | Что именно неясно (со слов человека) | Заведено | Статус |
|---|---|---|---|---|
| _пусто_ | | заполняется на гейтах и добивках | | |

## Подтверждённые решения (арх-карта)
Сюда добавляются `02-arch-decision.md` из закрытых задач — как принятые архитектурные решения.
- _(пока пусто — первое решение появится после первой задачи через конвейер)_
