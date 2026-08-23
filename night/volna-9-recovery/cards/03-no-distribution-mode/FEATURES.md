ФИЧ: 4

## Фичи

### 1. Сохранить режим «Без распределения» на поставке

Оператор включает и выключает существующую галку, а состояние живёт на самой
FBS-поставке, а не в ключе создания короба. Поэтому удаление и повторное создание
пустой тары не сбрасывает режим; старый префикс короба читается только для
совместимости с уже существующими поставками. Переключение разрешено лишь пока во
всей поставке нет назначений заказов.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/models/fbs_supply.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/alembic/versions/20260821_0094_fbs_supplies_boxes_without_distribution.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py`

Зависимости: нет.

Проверка: на чистой тестовой БД миграция выполняется до `head`; включённый сервисом
режим сохраняет поле поставки после удаления последнего пустого короба и создания
нового, а наличие хотя бы одного `FbsPackingBoxItem` запрещает смену состояния.

### 2. Отдать и проверить сохранённое состояние через workspace FBS

Оператор получает после переключения свежий workspace с признаком поставки;
серверный маршрут принимает существующее действие включения/выключения и не даёт
сменить его при уже назначенном заказе. Готовность передачи продолжает получать
`without_distribution` из существующей готовности коробов, поэтому снимается только
проверка распределения, а остальные проверки не меняются.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/api/fbs_supplies.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/api/fbs_errors.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_workspace_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py`

Зависимости: 1.

Проверка: `test_fbs_packing_box.py` через `POST
/operations/fbs-supplies/{supply_id}/boxes-without-distribution` проверяет включение,
удаление и повторное создание пустых коробов, повторную загрузку workspace, возврат
к выключенному режиму и отказ при назначенном заказе. Отдельно существующий тест
передачи подтверждает, что режим не отменяет другие её проверки.

### 3. Связать клиент FBS с существующим маршрутом режима

Клиентская функция отправляет только `enabled` в существующий маршрут и принимает
канонический workspace из ответа. Это даёт экрану один серверный источник истины,
без локального флага, не привязанного к поставке.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/fbsApi.test.ts`

Зависимости: 2.

Проверка: unit-тест клиента фиксирует `POST` на маршрут поставки, тело
`{ enabled }` и обновлённый `FbsWorkspace` с
`supply.boxes_without_distribution`.

### 4. Показать сохранённое состояние существующей галкой и убрать лишний UX

На вкладке «Короба» S-03 галка доступна при любом числе пустых коробов и блокируется
только при назначенных заказах. Экран читает состояние из ответа workspace, поэтому
после закрытия поставки, удаления коробов и повторного открытия оно не сбрасывается.
Из текущего кандидата удаляется только незапрошенный тултип; существующая строка
шапки «Без распределения · коробов N» сохраняется без изменений;
доступность QR, печати, меню, раскрытия и «Добавить товары» не меняется карточкой.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/tests-e2e/ff-fbs-supply.spec.ts`

Зависимости: 3.

Проверка: Playwright-сценарии `S-03-TC-001`--`S-03-TC-008` прокликивают создание
пустых коробов, включение и выключение галки, удаление/повторное создание и повторное
открытие workspace; подтверждают блокировку только при назначении, отсутствие
незапрошенного тултипа, неизменность существующей строки шапки, а также прежний gate передачи без регрессии
листа подбора и ленты (`S-06-TC-001`).

## Порядок

Выполнять строго последовательно: 1 → 2 → 3 → 4. Фича 1 создаёт сохраняемое
состояние, фича 2 делает его доступным через API и workspace, фича 3 даёт экрану
типизированный клиент, а фича 4 меняет только существующую галку и пользовательские
проверки. Параллельных атомов внутри карточки нет: все они используют одно состояние
поставки и один сценарий S-03.

## Что осталось за бортом

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_shipment_service.py` уже получает `without_distribution` через готовность коробов; контракт не требует его правки.
- Переписывание B-09 в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/docs/blockers/S-03.md` — документационный хвост карты волны, не часть принятого UX-контракта этой атомарной карточки.
- Любые изменения существующего текста шапки, новый тултип, новый серверный текст ошибки, UI-kit, соседние FBS-экраны, QR, печать, лист подбора и лента исключены границей владельца.
