## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/sellerInboundDocumentUi.test.ts`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — команда завершилась без диагностик; оболочка не вернула числовой код.
- `python3 scripts/ui/ui_guard.py` — красный: обнаружены новые нарушения baseline в нескольких экранах, включая `SellerInboundDraftScreen.tsx` (`1111 → 1255`). Флаг `--update` не применялся.
- `npm run test:unit -- --run src/screens/v2/sellerInboundDocumentUi.test.ts` — красный: локальная зависимость `vitest` отсутствует (`vitest: command not found`, exit 127).

## Не реализовано

- Персистентная смена склада существующего черновика не может быть реализована буквально только в разрешённых screen-файлах: текущая серверная модель `InboundIntakeRequestPlannedPatch` не принимает `warehouse_id` и отвечает ошибкой валидации. UI теперь откатывает неподтверждённый выбор; изменение backend-схемы оставлено за пределами роли `screen-dev`.
- Живой browser E2E не запускался: локальная frontend-зависимость `vitest` отсутствует, а обязательный `ui_guard.py` уже красный.
