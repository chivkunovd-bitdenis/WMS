## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellersScreen.tsx` — строка селлера открывает существующий диалог; в нём добавлен раскрываемый блок «Реквизиты для счетов» с сохранением через billing API, подтверждением и понятной ошибкой над полями.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-seller-profile.spec.ts` — добавлены сценарии `S-31-TC-001` и заготовка `S-31-TC-009`.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершился в рабочее время без вывода; процесс остановлен, итог не подтверждён.
- `python3 scripts/ui/ui_guard.py` — красный из-за существующих нарушений в `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; новых нарушений для `SellersScreen.tsx` после исправления кнопки нет.
- `npm run test:unit` — не запустился: в рабочей копии отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- Полное чтение ранее сохранённого профиля при новом открытии диалога не реализовано буквально: доступный контракт backend предоставляет только `PUT`, без GET. Значения сохраняются и остаются видимыми в текущем открытом экране; ошибка валидации не меняет сохранённое локальное состояние.
- `S-31-TC-009` оставлен как пропущенный тестовый сценарий до появления общей фикстуры чтения профиля; UI-ошибка контрольного числа реализована через ответ API.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не затрагивались.
- Несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/JOURNAL.md` не включалось в работу.
