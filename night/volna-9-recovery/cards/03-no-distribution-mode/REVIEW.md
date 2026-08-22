ВЕРДИКТ: НАХОДКИ 1

# REVIEW · 03-no-distribution-mode · повторный проход

Вердикт: CHANGES_REQUESTED.

## Находки

1. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py:520-529`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py:345-402` — ремонт отказывается искать legacy-маркер для любого ключа длиннее 112 символов и сразу переходит к созданию. Сценарий: до деплоя запрос с 128-символьным `idempotency_key` создал физический короб, а старый код сохранил его ключ как `no-distribution:` плюс первые 112 символов; после деплоя клиент повторяет **тот же** запрос с тем же полным ключом. Точного raw-совпадения в БД нет, ветка `len(key) > 112` возвращает пустой список, и `create_boxes` создаёт ещё один короб и ещё одно грузоместо WB. Цена: повтор операции теряет идемпотентность (гарантию, что повтор не дублирует операцию), в учёте и физическом потоке появляется дубль короба. Новый тест проверяет только **другой** длинный ключ с теми же первыми 112 символами, поэтому он зелёный при поломке точного legacy-повтора.

## Проверено и нормально

- Предыдущая находка закрыта для заявленного сценария с двумя **разными** 128-символьными ключами: усечённый legacy-маркер больше не возвращает чужой короб.
- Ремонтный diff после прошлого вердикта прочитан целиком: продуктовые изменения ограничены `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py`; остальное — стадийные отчёты. Границы переданного списка соблюдены.
- Новых операторских блокировок в ремонтном diff нет; tenant и supply остались в условиях всех поисков, межарендный доступ не появился.
- `ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py` прошёл; `pytest -q tests/test_fbs_packing_box.py tests/test_fbs_openapi_contract.py` — `20 passed`. Назначенные `S-03-TC-001`, `S-03-TC-002`, `S-03-TC-003` и их e2e-привязки сверены; секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
