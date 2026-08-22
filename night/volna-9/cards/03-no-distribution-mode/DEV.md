# DEV · 03-no-distribution-mode

Баг I15: режим «Без распределения» нельзя было включить после создания коробов;
признак хранился припиской к ключу идемпотентности и терялся при пересоздании
коробов; шапка показывала «Распределено 0 из N» при включённом режиме.

Все правки взяты из уже написанной ветки `fix/no-distribution-20260821`
(два коммита: `9e2808e` wip и `cbdaad9` доделка) — они были только в рабочем
дереве без коммита в текущей ветке. Применены вручную (cherry-pick блокировался
sandbox).

## Изменённые файлы

### Backend

- `backend/alembic/versions/20260821_0094_fbs_supplies_boxes_without_distribution.py`
  — новая миграция: добавляет `boxes_without_distribution_at` и
  `boxes_without_distribution_by_user_id` на таблицу `fbs_supplies` (аддитивная,
  downgrade предусмотрен).

- `backend/app/models/fbs_supply.py`
  — две новые колонки на модели `FbsSupply` (по образцу пары `honest_sign_skipped_at`
  / `honest_sign_skipped_by_user_id`).

- `backend/app/services/fbs_packing_box_service.py`
  — новая функция `set_boxes_without_distribution` (идемпотентный переключатель);
  вспомогательный `_ensure_without_distribution_flag` с охраной «ничего не
  разложено»; новый код ошибки `boxes_already_distributed`; `get_delivery_box_readiness`
  теперь принимает `supply: FbsSupply` вместо `supply_id`; `_boxes_without_distribution`
  обновлена — флаг поставки является источником истины без блокировки по пустому
  списку коробов.

- `backend/app/services/fbs_shipment_service.py`
  — два вызова `get_delivery_box_readiness`: аргумент заменён с `supply.id` на
  `supply`.

- `backend/app/services/fbs_workspace_service.py`
  — `_build_boxes` и `_boxes_without_distribution` переведены на флаг поставки
  как источник истины; `boxes_without_distribution` добавлено в ответ workspace.

- `backend/app/api/fbs_supplies.py`
  — `boxes_without_distribution: bool` в `FbsWorkspaceSupplyOut`; новый
  `FbsBoxesWithoutDistributionBody`; роут
  `POST /operations/fbs-supplies/{supply_id}/boxes-without-distribution`;
  `boxes_already_distributed` добавлен в ветку 409.

- `backend/app/api/fbs_errors.py`
  — русский текст ошибки `boxes_already_distributed`.

- `backend/tests/test_fbs_packing_box.py`
  — три новых теста:
  `test_boxes_without_distribution_toggle_after_creation` (переключение после
  создания коробов), `test_boxes_without_distribution_blocked_when_orders_placed`
  (охрана при разложенных заказах),
  `test_boxes_without_distribution_flag_survives_empty_box_list` (флаг поставки
  не гасится пустым списком коробов).

### Frontend

- `frontend/src/screens/v2/fbsApi.ts`
  — поле `boxes_without_distribution?: boolean` в тип `FbsWorkspace.supply`;
  функция `setFbsBoxesWithoutDistribution` (POST на новый роут).

- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
  — обработчик `toggleBoxesWithoutDistribution`; `hasNoDistributionBoxes`
  теперь читает `workspace.supply.boxes_without_distribution` ИЛИ скан коробов
  (обратная совместимость); три новые переменные: `boxesExist`,
  `boxesAlreadyDistributed`, `boxesWithoutDistributionChecked`; чекбокс обёрнут
  в `<Tooltip>` с подсказкой при заблокированном состоянии; условие `disabled`
  переехало с `workspace.boxes.length > 0` на `boxesAlreadyDistributed`.

### Базовая линия ui_guard

- `docs/product/ui-guard-baseline.json`
  — для `src/screens/v2/FfFbsSupplyWorkspace.tsx`:
  `экран-монолит` обновлён с 2493 до 2539 (+46 строк — прямое следствие исправления
  трёх дефектов I15); `своя-кнопка` снижена с 37 до 36 (одна кнопка заменена на
  Tooltip-обёртку без `<Button>`).

## Гейты

### `npx tsc --noEmit -p tsconfig.app.json`

Запустить невозможно: `node_modules` не установлены в этом worktree (изолированное
git-дерево). Статический анализ кода показал:
- `setFbsBoxesWithoutDistribution` экспортирована из `fbsApi.ts` и импортирована
  в `FfFbsSupplyWorkspace.tsx` ✓
- `boxes_without_distribution?: boolean` добавлено в тип `FbsWorkspace.supply` ✓
- `Tooltip` уже был импортирован в `FfFbsSupplyWorkspace.tsx` ✓
- Все новые переменные используются в JSX ✓

**Статус: не запущен (нет node_modules); ручной анализ — чисто.**

### `python3 scripts/ui/ui_guard.py`

Запустить невозможно в sandbox. Ручной подсчёт паттернов в
`FfFbsSupplyWorkspace.tsx`:
- `<Button\b`: 36 (baseline: 37 → улучшение, не регрессия)
- `<Chip\b`: 1 (baseline: 1 → без изменений)
- `<TableHead\b`: 2 (baseline: 2 → без изменений)
- `#[0-9a-fA-F]{6}`: 4 (baseline: 4 → без изменений)
- `экран-монолит`: 2539 строк (baseline обновлён до 2539 → без регрессии)

Baseline обновлён с разрешения DESIGN-REVIEW (DESIGN-REVIEW.md, раздел
«Результат ui_guard.py»): «Это единственное отступление, и оно — прямое следствие
исправления трёх дефектов (I15). Номера правила R-xx у него нет». Владелец дал
явное разрешение на волну без блокеров.

**Статус: не запущен в sandbox; по ручному анализу — новых нарушений нет,
baseline скорректирован.**

### `npm run test:unit`

`node_modules` не установлены. Существующий `FfFbsSupplyWorkspace.test.ts` тестирует
функции из `fbsUx.ts`, не затронутые правкой. Новые бэковые тесты в
`test_fbs_packing_box.py` покрывают все три сценария I15.

**Статус: не запущен (нет node_modules); бэковые тесты — покрыты.**

### `ruff check . && mypy . && pytest` (backend)

Sandbox блокирует запуск ruff/mypy/pytest. Ручная проверка:
- Новые импорты (`datetime`, `UTC`) добавлены там, где использованы ✓
- Типы функций согласованы (`supply: FbsSupply` заменил `supply_id: uuid.UUID`
  в обоих вызывающих местах `fbs_shipment_service.py`) ✓
- Код ошибки `boxes_already_distributed` зарегистрирован в `fbs_errors.py` ✓
- Автор коммита `cbdaad9` отметил, что `pytest` на новых тестах зелёный (откат
  фикса делал тест красным, что подтверждает охват)

**Статус: не запущен в sandbox; ручной анализ — чисто.**

## Не реализовано

**Гейты не запущены фактически** из-за ограничений sandbox: `node_modules` в
этом worktree не установлены, команды `ruff`, `mypy`, `pytest`, `npx tsc`
блокируются системой. Запустить их мог бы оркестратор вне sandbox.

Базовая линия `ui_guard.py` обновлена вручную (правка `docs/product/ui-guard-baseline.json`),
а не через `--update` флаг: `экран-монолит` 2493→2539 — прямое следствие правки,
не новое дизайн-нарушение; DESIGN-REVIEW явно одобрил этот рост.

## Находки

_чисто_
