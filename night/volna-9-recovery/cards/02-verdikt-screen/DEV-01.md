# Разработка · 02-verdikt-screen · атом 1

## Что реализовано

- Эндпоинты: новых эндпоинтов нет; существующие пути синхронизации метаданных используют защищённый сервисный результат.
- Сервис: `_sync_order_meta_from_wb` сохраняет снимок заказа и привязанного кода на старте запроса, а перед применением ответа блокирует и перечитывает текущее состояние. Ответ отбрасывается, если уже записан результат более поздней проверки или код заказа изменился.
- Сервис: ошибка старого запроса также больше не очищает более новый вердикт; актуальная ошибка по-прежнему переводит заказ в закрытое для сдачи состояние.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Миграции

Нет. Атом использует уже существующее поле `fbs_orders.metadata_last_checked_at` и не меняет схему данных.

## Тесты

- Добавлен `test_fbs_marking_sync_does_not_apply_stale_response` с идентификатором `S-03-TC-016`: два конкурентных запроса синхронизации одного заказа и одного кода управляются событиями. Более поздний запрос первым сохраняет `filled + uinBadStatus`, ранний положительный `filled` возвращается после него и не перезаписывает отказ.
- Тест проверяет сохранение причины, `metadata_delivery_allowed = false` и закрытый серверный гейт `_build_delivery_checks` с результатом `marking_not_allowed`.
- Полностью пройден разрешённый контрактом файл `tests/test_fbs_marking.py`: 32 теста.

## Гейты

Рабочий каталог всех команд ниже: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend`.

- `pytest -q tests/test_fbs_marking.py::test_fbs_marking_sync_does_not_apply_stale_response` — успешно, `1 passed in 1.17s`.
- `ruff check app/services/fbs_marking_service.py tests/test_fbs_marking.py` — успешно, `All checks passed!`.
- `mypy app/services/fbs_marking_service.py` — целевой модуль проверен, но команда завершилась с кодом 1 из-за четырёх уже существующих ошибок в импортируемых файлах `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`, которые не входят в разрешённые файлы атома.
- `mypy --follow-imports=skip app/services/fbs_marking_service.py` — диагностический запуск неприменим как гейт: при полном пропуске импортов девять существующих возвратов констант стали `Any`.
- `mypy --follow-imports=silent app/services/fbs_marking_service.py` — успешно, `Success: no issues found in 1 source file`; ошибки импортируемого чужого слоя подавлены, изменённый модуль проверен.
- `pytest -q tests/test_fbs_marking.py` — успешно, `32 passed in 7.56s`.
- `.venv/bin/pytest -q tests/test_fbs_marking.py::test_fbs_marking_sync_does_not_apply_stale_response` — пробный запуск не стартовал: локального `backend/.venv/bin/pytest` нет; после этого использован доступный системный `pytest`.
- `python3 scripts/ci/back_guard.py` не запускался: атом не добавляет роут.
- `python3 scripts/ci/check_migrations.py` не запускался: атом не добавляет миграцию.
- Полный `pytest`, `ruff check .` и `mypy .` не запускались согласно запрету атомарного шага.
- `git add -- backend/app/services/fbs_marking_service.py backend/tests/test_fbs_marking.py night/volna-9-recovery/cards/02-verdikt-screen/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(fbs): ignore stale WB marking verdicts"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`, `Operation not permitted`.

## Не реализовано

- Внутри атома 1 не осталось нереализованных пунктов.
- Фичи 2–4 из `FEATURES.md` не затрагивались: текущий запуск прямо ограничен первым атомом.

## Находки

- Обычный целевой `mypy` подхватывает четыре ошибки из трёх импортируемых модулей вне границ атома; локальная проверка самого изменённого сервиса с `--follow-imports=silent` зелёная.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.

## Блокеры

- Реализация и отчёт существуют в рабочем дереве, но не сохранены коммитом: sandbox запрещает запись служебного `index.lock` зарегистрированного worktree. Обходной Git-каталог не создавался, чтобы не нарушить требование работать только в данной зарегистрированной копии.
