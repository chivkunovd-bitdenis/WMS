# 09-billing · screen-dev · rework атома 9

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

В `FfBillingScreen` журнал начислений теперь запрашивает выбранный месяц через `period=YYYY-MM`, совпадающий с живым API. Хранение во всех трёх местах экрана — метка, фильтр и детализация счёта — использует единый межкарточный код `storage_liter_day`. Технический UUID расчёта хранения в детализации заменяется на «Расчёт хранения за {месяц}».

`AuthedAppLayout.tsx` и `App.tsx` проверены без правок: пунк «Расчёты» и маршрут `/app/ff/billing` уже ограничены `isFulfillmentAdmin`; селлер и складской сотрудник не видят пунк, а прямой маршрут возвращает экран отказа без финансовых данных. Общие UI-примитивы не добавлялись.

## Гейты

- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — локального `typescript` нет, `npx` попытался обратиться к `https://registry.npmjs.org/tsc` и завершился `ENOTFOUND`.
- Красный, но новых нарушений текущего атома нет: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py`. Храповик указал на уже существующий рост файлов `src/App.tsx` (3492 → 3503), `src/components/WbProductPickerDialog.tsx` (0 → 646), `src/screens/ff/FfSettingsScreen.tsx` (701 → 795), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2498), `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1169). Базовая линия не обновлялась.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts` — `vitest: command not found`, потому что в рабочей копии нет `node_modules`.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:e2e -- billing-ledger.spec.ts billing-invoices.spec.ts` — npm не нашёл локальный Playwright и вызвал одноимённый Python CLI, который завершился `error: unknown command 'test'`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check`.
- Красный: `git add <файлы атома> && git commit -m "night(09-billing): rework billing screen contract"` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock`: `Operation not permitted`. Изменения остались только в рабочем дереве и не сохранены в новом commit.

Полные backend `pytest`, `ruff check .` и `mypy .` не запускались: они прямо запрещены для этого атома.

## Не реализовано

- Backend-находки 2, 4, 5, 6 и 7 из `REVIEW.md` не изменялись: роль `screen-dev` и границы этого атома запрещают править API, сервисы биллинга и миграции.
- Живой frontend e2e с настоящим billing read-model из находки 8 не добавлялся: это интеграционная backend-проверка за границами экранного слоя. Фронтендные моки приведены к реальной форме `{ entries: [...] }` и параметру `period`.
- Предписанные frontend-гейты не подтверждены зелёными из-за отсутствующих локальных npm-зависимостей и недоступного npm registry.
- Результат локально реализован, но не сохранён в Git: служебный Git-каталог worktree недоступен для записи в этой среде.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не затрагивались.
