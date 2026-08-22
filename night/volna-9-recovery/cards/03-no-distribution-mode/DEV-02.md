# DEV · 03-no-distribution-mode · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — при явном выключении режима legacy-ключ переведён в нейтральный ключ совместимости; отложенный повтор исходного `create_boxes(..., without_distribution=true)` по прежнему ключу находит тот же короб, не создаёт дубль и не включает режим повторно.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — регрессия последовательности «создать короб без распределения → выключить режим → повторить исходное создание»: проверяет один и тот же короб, выключенный режим и сохранённую возможность идемпотентного поиска.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — этот отчёт.

## Гейты

- `ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py` — PASS.
- `ruff check .` — FAIL: 80 ранее существовавших ошибок в несвязанных файлах; изменённые файлы в выводе отсутствуют.
- `mypy .` — FAIL: 21 ранее существовавшая ошибка в 6 несвязанных файлах; изменённые файлы атома в выводе отсутствуют.
- `pytest -q tests/test_fbs_packing_box.py -k 'toggle_preserves_legacy_key_for_create_retry'` — PASS: `1 passed, 10 deselected`.
- `pytest` — запущен: собрал 822 теста, но исполнитель завершил вывод без итоговой строки после начала прогона; результат полного прогона не подтверждён. Целевой регрессионный тест завершился успешно.
- `python3 scripts/ci/back_guard.py` — NOT RUN: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/back_guard.py` нет.
- `python3 scripts/ci/check_migrations.py` — NOT RUN: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/check_migrations.py` нет.

## Не реализовано

- Находка `REVIEW.md` о browser E2E относится к фронтенд-слою и этому backend-атому не принадлежит.
- Миграций нет: изменение использует существующее поле поставки и только сохраняет идемпотентность legacy-ключа.

## Находки

- Секреты, ключи, токены и `.env` не читались.
- Git commit не создан: Git не смог открыть lock-файл `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock` (`Operation not permitted`). Изменения существуют только в локальном незакоммиченном рабочем дереве.
