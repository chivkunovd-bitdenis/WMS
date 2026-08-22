ВЕРДИКТ: НАХОДКИ 2

# REVIEW · 03-no-distribution-mode

Вердикт: CHANGES_REQUESTED.

## Находки

1. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py:376-381,561-590` — при явном выключении режима новый префикс увеличивает служебный ключ за предел колонки. Сценарий: `POST /boxes` принимает разрешённый API ключ длиной 128 символов; `_stored_creation_key` урезает его до 112 и записывает 128-символьное `no-distribution:<key>`, а `_retire_legacy_without_distribution_markers` заменяет 16-символьный префикс на 25-символьный и получает 137 символов для `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/models/fbs_packing_box.py:48` (`String(128)`). PostgreSQL отклонит `UPDATE` с `value too long for type character varying(128)`, и оператор не сможет выключить режим. Цена: штатная смена режима падает 500-й ошибкой на валидном входе; SQLite-тест с коротким ключом этого не ловит.

2. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx:329-342,388-394,2029-2035` — фоновое обновление workspace меняет `workspace`, но не синхронизирует локальный `boxesWithoutDistribution`, из которого рисуется `checked`. Сценарий: два оператора открыли одну поставку с выключенным режимом; первый включает его, через 15 секунд второй получает `supply.boxes_without_distribution=true`; шапка уже показывает «Без распределения», а чекбокс остаётся снятым. Обратный переход даёт зеркальное расхождение. Цена: оператор видит два противоречащих состояния одного режима и может принять неверное решение о раскладке; E2E проверяет только изменения из той же вкладки через `run()` и остаётся зелёным при сломанной фоновой синхронизации.

## Проверено и нормально

- Итоговый продуктовый дифф по заданному списку файлов прочитан целиком; фронтовые файлы входят в S-03 по `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/screens.registry.json`, а прочие файлы вне заданного списка считались стадийными артефактами.
- Серверная блокировка согласована с экраном: переключение запрещено только при назначенных заказах, прямой и конкурентный запрос защищены блокировкой строки поставки и ответом `409 boxes_already_distributed`. B-09 описан шестью полями в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/docs/blockers/S-03.md`.
- Сохраняемый флаг поставки переживает удаление всех коробов; legacy-префикс продолжает блокировать раскладку, а повтор старого POST после выключения режима возвращает прежний короб и не включает режим снова.
- `pytest -q tests/test_fbs_packing_box.py tests/test_fbs_openapi_contract.py` завершился успешно: `15 passed in 38.04s`. Playwright не запускался: в рабочей копии нет локального `frontend/node_modules/.bin/playwright`.
