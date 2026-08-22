ВЕРДИКТ: НАХОДКИ 1

# REVIEW · 03-no-distribution-mode · повторный проход

Вердикт: CHANGES_REQUESTED.

## Находки

1. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py:520-531`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py:294-342` — fallback для legacy-повтора безусловно обрезает любой новый API-ключ до 112 символов и ищет старый `no-distribution:` / `retired-no-dist:` маркер. Сценарий: до деплоя был создан короб с 128-символьным ключом `"x" * 112 + "A" * 16`, который старый код необратимо сохранил как `no-distribution:` + `"x" * 112`; после деплоя клиент впервые отправляет другой валидный ключ `"x" * 112 + "B" * 16`. Точного raw-совпадения нет, но fallback находит усечённый старый маркер и возвращает прежний короб вместо создания нового. Цена: легитимная операция тихо теряется, а оператор получает чужой физический короб как результат новой команды. Добавленный тест использует только короткий ключ `legacy-compatible-box`, поэтому он зелёный при этой поломке.

## Проверено и нормально

- Единственная находка прошлого `REVIEW.md` закрыта для коротких legacy-ключей: повтор находит как активный `no-distribution:`, так и погашенный `retired-no-dist:` ключ и не создаёт дубль.
- Ремонтный дифф после прошлого вердикта прочитан целиком: изменены только `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` плюс стадийные артефакты; границы переданного списка соблюдены.
- Точный поиск нового raw-ключа выполняется до legacy-fallback, tenant и supply остались в условиях обоих запросов; доступ к коробам другого tenant или другой поставки не появился.
- `ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py` прошёл; `pytest -q tests/test_fbs_packing_box.py tests/test_fbs_openapi_contract.py` — `18 passed`. Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
