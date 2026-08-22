ФИЧ: 4

## Фичи

### 1. Сохранять режим «Без распределения» на поставке

Оператор включает режим для всей FBS-поставки, и его состояние не зависит от того, были ли удалены или заново созданы пустые короба. Для этого в поставке появляется нормальный сохраняемый признак с временем включения и пользователем, а не приписка к служебному ключу короба.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/alembic/versions/20260821_0094_fbs_supplies_boxes_without_distribution.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/models/fbs_supply.py`

Зависимости: нет.

Как проверить: применить миграцию, включить режим у поставки, удалить все её пустые короба и создать новые; запись `fbs_supplies` сохраняет признак режима и после повторного открытия поставки.

### 2. Переключать режим, пока в коробах нет назначенных заказов

Оператор может включать и выключать режим при любом числе пустых коробов. Сервис запрещает изменение только если в коробах этой поставки есть хотя бы одно назначение заказа; после удаления всех назначений переключение снова доступно. Старую приписку `no-distribution:` сервис читает только для совместимости существующих поставок, но новые переключения записывает в поле поставки.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py`

Зависимости: фича 1.

Как проверить: сервисным тестом и через сценарий данных включить режим после создания пустого короба, удалить и пересоздать короб, затем выключить режим. После назначения заказа в короб попытка сменить режим получает доменную ошибку; после удаления назначения смена снова проходит.

### 3. Отдавать режим и запрет переключения через FBS API

Клиент получает из workspace один источник истины `boxes_without_distribution` на поставке и меняет его отдельной операцией. API возвращает обновлённый workspace, а попытку включить режим при назначенных заказах переводит в понятный конфликтный ответ; построение workspace также учитывает сохранённый признак, даже когда список коробов пуст.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/api/fbs_supplies.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_workspace_service.py`

Зависимости: фичи 1 и 2.

Как проверить: `POST /operations/fbs-supplies/{supply_id}/boxes-without-distribution` с `enabled: true` на поставке с пустыми коробами возвращает workspace с `supply.boxes_without_distribution=true`. После удаления всех коробов `GET workspace` всё ещё возвращает `true`; при назначенном заказе POST получает конфликт, а не меняет состояние.

### 4. Показать оператору корректный режим на вкладке «Короба»

На вкладке «Короба» галка остаётся доступной после создания пустых коробов и становится недоступной только когда заказы уже назначены. При включённом режиме шапка показывает нейтральное состояние без ложного красного прогресса «Распределено 0 из N»; при выключенном возвращается обычный прогресс. Текст причины недоступности объясняет, что сначала нужно убрать назначения из коробов.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/openapi/fbs-operations.openapi.json`

Зависимости: фича 3.

Как проверить: в живом браузере открыть редактируемую поставку, создать пустой короб и включить режим — галка доступна, шапка не показывает «Распределено 0 из N». Удалить и вновь создать пустые короба — режим остаётся включённым. Назначить заказ при выключенном режиме — переключатель недоступен с объяснением; удалить назначение — снова доступен.

## Порядок

Делать строго 1 → 2 → 3 → 4: каждая следующая фича использует контракт и состояние предыдущей. Параллельных фич внутри этой карточки нет: сервис переключения зависит от схемы, API — от сервиса, а экран — от опубликованного API-контракта.

Карточку 03 следует влить раньше задач 04 и 06 волны: они меняют соответственно шапку и workspace экрана, а задача 06 также меняет `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_workspace_service.py`.

## Что осталось за бортом

- Массовая миграция старых поставок и окончательное удаление чтения `no-distribution:` не входят в контракт: остаётся только временная совместимость.
- Отдельный журнал переключений, настройка режима по селлеру и новые сценарии упаковки контрактом не запрошены.
- Обновление записи B-09 в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/docs/blockers/S-03.md` — сопроводительная документация, а не самостоятельная поставляемая фича; после реализации в ней нужно заменить правило «есть короб» на «есть назначение заказа».
