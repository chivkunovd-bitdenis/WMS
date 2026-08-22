# Screen Dev · 07-reporting · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx` — несовместимые с MUI 9 прямые свойства `alignItems`, `flexWrap` и `fontWeight` перенесены в `sx`; поведение и состав графика не менялись.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — записан обязательный отчёт роли.

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.test.tsx` уже соответствовали контракту и не потребовали правок. Названная ревьюером проблема обнаружения `.test.tsx` уже устранена в текущей ветке: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/vitest.config.ts` включает `src/**/*.test.tsx`; целевой тест действительно запустился.

## Гейты

- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend` выполнено `npx tsc --noEmit -p tsconfig.app.json`; код завершения 0, ошибок нет.
- Красный по изменениям вне атома: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting` выполнено `python3 scripts/ui/ui_guard.py`; код завершения 1. Храповик сообщил новые нарушения только в `src/App.tsx` (экран-монолит 3492 → 3511), `src/components/WbProductPickerDialog.tsx` (экран-монолит 0 → 646), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (экран-монолит 2493 → 2498) и `src/screens/v2/SellerInboundDraftScreen.tsx` (экран-монолит 1111 → 1169). Эти файлы не относятся к атому 5 и не входят в разрешённую область правок. Базовая линия не обновлялась.
- Зелёный: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend` выполнено `npm run test:unit -- src/ui-kit/MovementFlowChart.test.tsx`; 1 файл и 3 теста прошли.
- Красный по ограничению песочницы: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting` выполнено `git add -- frontend/src/ui-kit/MovementFlowChart.tsx night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(ui-kit): repair movement flow chart build"`; Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` (`Operation not permitted`). Отдельный commit SHA отсутствует.

## Не реализовано

В самом контракте атома 5 отступлений нет. Общий `ui_guard.py` не удалось сделать зелёным без запрещённых правок четырёх соседних файлов, перечисленных в разделе «Гейты». Изменения локально реализованы, но не сохранены отдельным Git-коммитом: песочница запрещает запись в общий Git-каталог зарегистрированного worktree.

## Находки

Находок о данных, персональных данных или секретах в пределах этого атома нет. Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
