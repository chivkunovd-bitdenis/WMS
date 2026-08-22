# 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/TransfersScreen.tsx`

Экран S-25 больше не показывает успешное «Перемещение» до ответа операции: результат
появляется только после окончания загрузки без ошибки. При серверном отказе строка
успешной операции не создаётся.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершился в доступное время через `npx`, вывода об ошибках нет; зелёным не считаю.
- `python3 scripts/ui/ui_guard.py` — красный: обнаружены новые нарушения в чужих для этого атома файлах `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Базовую линию не обновлял.
- `npm run test:unit` — не запущен: в окружении отсутствует исполняемый файл `vitest` (`vitest: command not found`).

## Не реализовано

- Полная фильтрация S-25 по глобальному складскому контексту и объединение серверной пары `transfer_group_id` требуют входных props/API-данных, которых текущий разрешённый файл экрана не получает; изменение `App.tsx` и backend выходит за границы реестра этого атома.
- Живой браузерный сценарий не запускался: локальные frontend-зависимости неполны (`vitest` отсутствует), а обязательные product-browser проверки выполняются отдельной ролью.
