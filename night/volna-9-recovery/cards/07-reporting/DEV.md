# DEV · 07-reporting · атом 9 · переделка по review

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx` — в обеих совместимых точках маршрутизации S-33 в отчёт передаются только операционные склады. Явный `is_operational` имеет приоритет; до интеграции расширенного `/warehouses` служебные склады `FBS WB …` исключаются по тому же правилу, которым миграция заполняет этот флаг.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerApp.tsx` — основной seller-маршрут использует ту же фильтрацию и не открывает селлеру ложную область служебного склада.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerApp.test.tsx` — добавлены точечные unit-кейсы для явного `is_operational=false` и совместимости со старым ответом API без флага.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts` — добавлен `S-33-TC-003/S-33-TC-014`: один физический склад вместе с `FBS WB Архив` не создаёт селектор ложного склада в портале ФФ.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts` — seller-сценарий дополнен проверкой URL, отсутствия чужого селлера и отсутствия селектора при служебном складе с `is_operational=false`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт этого ремонтного прохода.

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/layouts/AuthedAppLayout.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/screens.registry.json` не менялись: пункт меню, ролевое условие ФФ и регистрация S-33 с двумя маршрутами уже присутствуют; относящихся к ним находок в текущем `REVIEW.md` нет.

## Гейты

- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`: `npm_config_offline=true npx tsc --noEmit -p tsconfig.app.json` — красный до компиляции: локального `tsc` и записи пакета в npm-кэше нет (`ENOTCACHED`).
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`: `python3 scripts/ui/ui_guard.py` — красный по уже существующим превышениям baseline: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Ремонт уменьшил `App.tsx` относительно `HEAD` с 3512 до 3510 строк; baseline не менялась.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`: `npm run test:unit -- src/apps/seller/SellerApp.test.tsx` — красный до запуска кейсов: `vitest: command not found`.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`: `npm_config_offline=true npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts` — красный до запуска браузера: локального Playwright и записи пакета в npm-кэше нет (`ENOTCACHED`).
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`: `git diff --check` — зелёный.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`: `python3 -m json.tool frontend/screens.registry.json >/dev/null` — зелёный.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`: `git add -- frontend/src/App.tsx frontend/src/apps/seller/SellerApp.tsx frontend/src/apps/seller/SellerApp.test.tsx frontend/tests-e2e/ff-reports.spec.ts frontend/tests-e2e/seller-reports.spec.ts night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(reports): hide service warehouse scopes"` — красный на `git add`: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock`, `Operation not permitted`. Чужой `JOURNAL.md` в индекс не добавлялся.

## Не реализовано

- Пункты контракта этого атома и относящаяся к его frontend-маршрутизации находка 1 из `REVIEW.md` реализованы буквально. Автоматическое подтверждение tsc/unit/Playwright отсутствует только из-за отсутствующих frontend-зависимостей и закрытого npm-кэша.
- Находки 2–10 из `REVIEW.md` относятся к `FfReportsPage.tsx`, reporting backend и другим атомам. В рамках роли `screen-dev` и атома 9 эти файлы не менялись.
- Результат локально реализован, но не сохранён отдельным Git-коммитом: sandbox запрещает запись в общий Git-каталог зарегистрированного worktree.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
