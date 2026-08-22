# Backend-dev · 02-verdikt-screen · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_workspace_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Что реализовано

- Сервис workspace: `_metadata_ready` теперь принимает сохранённый `metadata_delivery_allowed` как единый серверный вердикт, включая явный `False`; fallback к прежним статусам применяется только для старых записей без этого признака.
- Тест: S-03-TC-003 подтверждает, что `filled + reason=uinBadStatus` с техническим `accepted` не повышает готовность workspace; legacy-запись без серверного признака сохраняет прежний fallback.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`: добавлена регрессия server-verdict → workspace progress для S-03-TC-003.

## Гейты

- `ruff check app/services/fbs_marking_service.py app/services/fbs_workspace_service.py tests/test_fbs_marking.py` — PASS.
- `ruff check .` — FAIL: 81 предсуществующая ошибка вне изменённых файлов.
- `mypy .` — FAIL: 21 предсуществующая ошибка в 6 файлах вне изменённых файлов.
- `pytest -q tests/test_fbs_marking.py` — PASS: 27 passed.
- `pytest` — FAIL/прерван после первого падения: `tests/test_fbs_kiz.py::test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row`, 167 passed, 3 skipped. Фикстура ожидает разрешение при WB `decision=accepted`, которое не является допустимым положительным decision контракта этого атома; изменённый workspace-сервис в traceback не участвует.
- `python3 scripts/ci/back_guard.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Frontend-находки 1 и 3 из REVIEW.md не входят в роль backend-dev и не менялись.
- Полные repo-гейты не зелёные по указанным предсуществующим проблемам вне атома.

## Блокеры

Нет.
