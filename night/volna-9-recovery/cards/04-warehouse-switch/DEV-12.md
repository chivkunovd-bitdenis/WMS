# DEV · 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts` — добавлен тип и клиентский вызов `GET /warehouses/resolve`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` — скан склада меняет контекст и сбрасывает ячейку, скан ячейки выбирает родительский склад, `ScannerLine` сообщает следующий шаг, успешный pick показывает единственную строку «Взято…».
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/ScannerLine.tsx` — проверен и использован без изменения.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts` — мок resolver и проверки текстов сканера/результата.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — красный: `npx` не нашёл локальный `tsc` и попытался обратиться к registry.npmjs.org; сеть недоступна (`ENOTFOUND`).
- `python3 scripts/ui/ui_guard.py` из корня — красный на baseline-нарушениях монолитности, включая `FfFbsSupplyWorkspace.tsx` (2493 → 2519 строк); базовая линия не обновлялась.
- `npm run test:unit` из `frontend/` — красный: `vitest: command not found`.

## Не реализовано

- `ScannerLine` не менялся: существующего ui-kit-примитива достаточно для контрактного поведения.
- Полноценный новый e2e-сценарий смены склада не добавлялся: текущий контрактный мок содержит один склад, а изменение ограничено разрешёнными файлами и существующим потоком workspace.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.
