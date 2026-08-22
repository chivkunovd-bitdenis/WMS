## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Экранные файлы атома повторно проверены и не менялись. Уже реализованная frontend-логика
соответствует контракту: S-26 не содержит глобального складского переключателя; S-29 при двух
доступных операционных складах показывает только их имена, а при одном складе не показывает поле;
S-28 разрешает менять склад только в черновике и после передачи оставляет только текст документа.
Служебные `FBS WB *`, неоперационные склады и технические коды отфильтрованы. При ответе PATCH со
старым `warehouse_id` экран не показывает ложный успех, откатывает выбор и выводит понятную ошибку.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный, exit code 0.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && python3 scripts/ui/ui_guard.py` — красный, exit code 1. Храповик сообщил ранее накопленные превышения: `src/components/WbProductPickerDialog.tsx` 0 → 646, `src/screens/v2/FfFbsOrdersScreen.tsx` 1587 → 1679, `src/screens/v2/FfFbsStockSyncScreen.tsx` 1083 → 1121, `src/screens/v2/FfFbsSupplyWorkspace.tsx` 2493 → 2605 и `src/screens/v2/SellerInboundDraftScreen.tsx` 1111 → 1267. Baseline флагом `--update` не изменялся.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npm run test:unit -- --run src/screens/v2/sellerInboundDocumentUi.test.ts` — зелёный: 1 test file, 9 tests passed.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx playwright test tests-e2e/seller-cabinet.spec.ts --grep "admin creates seller user; seller sees filtered catalog and inbound"` — красный до старта браузера: тестовый API не смог привязать `127.0.0.1:18000`, среда вернула `[Errno 1] operation not permitted`; сценарий не исполнялся.

## Не реализовано

- Находка №4 из `REVIEW.md` не может быть исправлена буквально в роли `screen-dev`. Серверная схема `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/inbound_intake.py` не принимает `warehouse_id` в `InboundIntakeRequestPlannedPatch`, поэтому реальный API игнорирует отправленный экраном выбор. Исправление требует backend-файлов и backend-роли; они не входят в разрешённые файлы S-26/S-28/S-29 и не изменялись. Профильный E2E уже требует сохранения `warehouse_id` в ответе PATCH и после перезагрузки, поэтому не маскирует дефект.
- Живой браузерный сценарий не подтверждён из-за запрета среды на локальный порт. Условия одного и двух складов, фильтрация служебных/неоперационных складов, блокировка после передачи и проверка ответа PATCH покрыты зелёными unit-тестами.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не читались и не изменялись.
