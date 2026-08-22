# DEV · 03-no-distribution-mode · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/api/fbs_supplies.py` — `POST /operations/fbs-supplies/{supply_id}/boxes-without-distribution` принимает `enabled`, вызывает сервис и возвращает обновлённый workspace; доменный конфликт назначенных заказов отображается как `409 boxes_already_distributed`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_workspace_service.py` — workspace получает `supply.boxes_without_distribution` из сохраняемого состояния поставки, в том числе без коробов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — исправлена серверная находка ревью: выключение режима сохраняет адресуемость legacy-ключа для повторного `POST /boxes`, поэтому повтор возвращает исходный короб и не создаёт дубль.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — покрыты API-возврат workspace, сохранение флага после повторного чтения, конфликт при назначенном заказе и регрессия идемпотентного повтора после выключения режима.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт backend-разработки.

## Миграции

- Нет: атом 3 использует добавляющие поля из атома 1 и не меняет схему.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — API-переключение на пустой поставке, устойчивость флага при пустом списке коробов, `409` при назначении и безопасный повтор создания после выключения режима.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_openapi_contract.py` — контракт OpenAPI для FBS API.

## Гейты

- `ruff check .` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend` — FAIL: 80 существующих ошибок в несвязанных файлах; файлов этого атома в диагностике нет.
- `mypy .` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend` — FAIL: 21 существующая ошибка в 6 несвязанных файлах; файлов этого атома в диагностике нет.
- `pytest -q tests/test_fbs_packing_box.py tests/test_fbs_openapi_contract.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend` — PASS: целевой запуск завершился без ошибок.
- `pytest` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend` — запуск начат, собраны 822 теста; исполнитель прекратил передачу вывода во время прогона, итоговая строка не получена.
- `python3 scripts/ci/back_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode` — NOT RUN: файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- `python3 scripts/ci/check_migrations.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode` — NOT RUN: файла `scripts/ci/check_migrations.py` в этой рабочей копии нет.

## Не реализовано

- Находка `REVIEW.md` о browser E2E относится к `frontend/tests-e2e/ff-fbs-supply.spec.ts` и экрану S-03; она вне разрешённой backend-роли и этого атома.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
