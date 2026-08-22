## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.
- `python3 scripts/ui/ui_guard.py` из корня — красный: обнаружены новые/накопленные нарушения монолитности, включая `FfSettingsScreen.tsx: 701 → 795`; baseline не обновлялся.
- `npm run test:unit -- --runInBand` из `frontend/` — не запущен: в окружении отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- Полная продуктовая browser-проверка сценариев S-31-TC-002, S-31-TC-003, S-31-TC-010, S-31-TC-011 и S-19-TC-001 не выполнена: в среде нет установленного test runner/dependency setup.
- Ревью-находки, относящиеся к backend и другим экранам, не менялись: контракт этого атома разрешает только `FfSettingsScreen.tsx` и его E2E-файл.
