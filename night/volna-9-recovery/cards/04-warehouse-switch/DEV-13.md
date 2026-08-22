## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/sellerInboundDocumentUi.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/seller-cabinet.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Экран теперь принимает смену склада черновика только когда ответ API возвращает именно
выбранный `warehouse_id`; иначе селектор возвращается к исходному состоянию и показывает
понятную ошибку. E2E-сценарий проверяет два доступных операционных склада, отсутствие их
технических кодов в выборе, сохранение выбранного склада при создании черновика и отсутствие
глобального переключателя в S-26.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный. Новые относительно его baseline нарушения:
  `src/components/WbProductPickerDialog.tsx` (0 → 646),
  `src/screens/v2/FfFbsOrdersScreen.tsx` (1587 → 1664),
  `src/screens/v2/FfFbsStockSyncScreen.tsx` (1083 → 1133),
  `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2605),
  `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1267). Baseline не обновлялся.
- `npm run test:unit` — красный: `sh: vitest: command not found`; зависимости этой рабочей
  копии не содержат исполняемый `vitest`.
- `npx playwright test tests-e2e/seller-cabinet.spec.ts --grep 'admin creates seller user; seller sees filtered catalog and inbound'` — зелёный.

## Не реализовано

- Контракт S-28 требует сохранять смену склада уже созданного черновика. Экран отправляет
  `warehouse_id` и теперь проверяет ответ, но текущая серверная схема PATCH не принимает это
  поле и молча возвращает прежний склад. Исправление схемы и сервисной операции относится к
  backend-слою и не входит в разрешённые файлы роли `screen-dev`; экран не выдаёт ложный успех.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.
