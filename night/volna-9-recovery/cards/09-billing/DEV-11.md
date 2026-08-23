# 09-billing — атом 11: пустой месяц без ложного повтора

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — кнопка «Повторить формирование» теперь появляется только для той пары «селлер + месяц», для которой экран ранее получил от сервера исправимую причину, а затем сервер подтвердил её отсутствие. Пустой месяц, активные фильтры и уже найденный счёт не создают ложного повтора; ответ формирования `empty` также убирает сохранённую возможность повтора.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts` — сценарий повторного формирования начинается с серверной причины `Нет тарифа`, проверяет недоступность действия до устранения, затем его появление после нового ответа сервера; добавлен сценарий пустого месяца без кнопки исправления и без POST-запроса.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — отчёт по атому 11.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный, код 0.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — красный из-за новых отступлений в чужих файлах: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/ff/FfSettingsScreen.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Файлы атома 11 в выводе отсутствуют; базовая линия не менялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts` — зелёный: `4 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:e2e -- billing-invoices.spec.ts --grep 'only after the server confirms|normal empty month'` — не стартовал: изолированная среда запретила Playwright webServer bind на `127.0.0.1:18000` (`Operation not permitted`), до выполнения тестовых утверждений.

## Не реализовано

Нет: пункты атома 11 реализованы в разрешённых фронтенд-файлах. Полный e2e-прогон технически заблокирован ограничением окружения на локальный порт; тестовые сценарии записаны, но не исполнялись.

## Находки

`ui_guard.py` обнаружил регрессии только вне файлов атома; они не исправлялись, чтобы не выходить за его границы.

## Блокеры

Изолированная среда запретила запись в git-метаданные checkout: `git add frontend/src/screens/ff/FfBillingScreen.tsx frontend/tests-e2e/billing-invoices.spec.ts night/volna-9-recovery/cards/09-billing/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`). Поэтому атом реализован локально, но отдельный Git-коммит и SHA создать не удалось.
