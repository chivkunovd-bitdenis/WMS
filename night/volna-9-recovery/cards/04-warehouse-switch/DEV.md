## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/seller-cabinet.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Экранные файлы
`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/SellerDocumentsScreen.tsx`,
`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`
и профильный unit-тест были проверены, но в этом повторном проходе не менялись. В них уже есть
требуемые экранные ограничения: S-26 не показывает глобальный складской контекст, список складов
селлера отбрасывает служебные и неоперационные записи, поле склада показывается только для черновика
при двух и более вариантах, а после передачи остаётся текст документа. Ответ PATCH считается успешной
сменой только если вернул выбранный `warehouse_id`; ложный успех не показывается.

E2E-сценарий дополнен отсутствовавшей проверкой из находок 9 и 12: селлер создаёт черновик на «Юге»,
меняет склад на `WH`, проверяет `warehouse_id` в ответе PATCH, перезагружает карточку и убеждается, что
выбор сохранился. После передачи тест повторно открывает документ и проверяет отсутствие селектора и
видимый текст `Склад: WH`. Технические коды складов по-прежнему проверяются как отсутствующие в списке,
а на S-26 по-прежнему проверяется отсутствие глобального `warehouse-context-switch`.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный до проверки затронутого сценария: существующий
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx`
  не может импортировать отсутствующий `@testing-library/react`, после чего TypeScript также не знает
  DOM-матчеры `toBeInTheDocument`, `toBeDisabled`, `toHaveTextContent` и связанные методы. Этот файл и
  зависимости находятся вне разрешённых файлов атома.
- `python3 scripts/ui/ui_guard.py` — красный на ранее накопленных нарушениях baseline:
  `src/components/WbProductPickerDialog.tsx` (0 → 646),
  `src/screens/v2/FfFbsOrdersScreen.tsx` (1587 → 1664),
  `src/screens/v2/FfFbsStockSyncScreen.tsx` (1083 → 1121),
  `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2619),
  `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1267). Текущая правка меняет только E2E и не
  добавляет экранной вёрстки; baseline флагом `--update` не двигался.
- `npm run test:unit` — зелёный: 22 test files, 157 tests passed.
- `npm run test:unit -- --run src/screens/v2/sellerInboundDocumentUi.test.ts` — зелёный:
  1 test file, 9 tests passed.
- `npx playwright test tests-e2e/seller-cabinet.spec.ts --grep 'admin creates seller user; seller sees filtered catalog and inbound'`
  — красный до старта браузера: тестовый API не смог привязать `127.0.0.1:18000`, среда вернула
  `[Errno 1] operation not permitted`. Пользовательские шаги в этом запуске не выполнялись.

## Не реализовано

- Смена склада сохранённого черновика не может быть подтверждена буквально на живом API в рамках
  `screen-dev`: серверная схема
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/inbound_intake.py`
  всё ещё не принимает `warehouse_id` в `InboundIntakeRequestPlannedPatch`, а сервисный метод
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/inbound_intake_service.py`
  не меняет склад черновика. Эти backend-файлы не входят в реестр S-26/S-28/S-29 и не относятся к
  слою роли `screen-dev`; они не изменялись. Добавленный E2E теперь фиксирует требуемое поведение и
  станет зелёным только после исправления серверной зависимости.
- Браузерная проверка одного операционного склада не запускалась отдельно. Условие отсутствия поля
  покрыто зелёным unit-тестом `shouldShowSellerWarehouseSelector(1, 'draft') === false`; целевой E2E
  с двумя складами не стартовал из-за запрета локального порта.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не читались и не
  изменялись.
