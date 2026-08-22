ВЕРДИКТ: НАХОДКИ 1

# REVIEW · 03-no-distribution-mode · повторный проход

Вердикт: CHANGES_REQUESTED.

## Находки

1. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py:107-108`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py:511-524` — ремонт перестал узнавать идемпотентный повтор старой операции `without_distribution=true`: новый код ищет только сырой API-ключ, тогда как уже существующие короба хранят его как `no-distribution:<key>`, а после выключения legacy-режима — как `retired-no-dist:<key>`. Сценарий: до деплоя клиент успешно создал короб с ключом `legacy-compatible-box`, но не получил ответ; после деплоя он повторяет тот же `POST`, сервис не находит запись `no-distribution:legacy-compatible-box` и создаёт ещё один короб. Цена: повторная доставка запроса удваивает физические короба и грузоместа WB вместо безопасного возврата первого результата; это нарушает обещанное в контракте чтение старого формата для совместимости. Тест `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py:264-291` проверяет только запрет назначения заказа, но не повтор создания, поэтому весь целевой набор остаётся зелёным при этой поломке.

## Проверено и нормально

- Все три пункта прошлого `REVIEW.md` проверены как замороженный чек-лист: новые короба больше не получают `no-distribution:`, два разных 128-символьных ключа не склеиваются, поздний GET больше не откатывает успешную мутацию workspace.
- Ремонтный diff после прежнего вердикта прочитан полностью: два файла backend, два файла frontend и стадийные отчёты. Продуктовые файлы остались в переданных границах; фронтовый экран и `fbsApi.ts` соответствуют S-03 в `frontend/screens.registry.json`.
- Тест гонки действительно фиксирует снимок `false` до POST, освобождает его после ответа `true` и проверяет видимую галку с нейтральной шапкой; TypeScript, ESLint и оба целевых Playwright-сценария компилируются и обнаруживаются.
- `ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py` прошёл; `pytest -q tests/test_fbs_packing_box.py tests/test_fbs_openapi_contract.py` — `16 passed`. Добавляющая миграция, tenant-фильтры, серверная блокировка `boxes_already_distributed` и её экранное объяснение не регрессировали.
