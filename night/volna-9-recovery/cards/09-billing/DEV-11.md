# 09-billing — screen-dev, переделка атома 11

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — печатный HTML счёта показывает полные снимки реквизитов с пользовательскими русскими подписями, строки и суммы в формате RUB; повторное подтверждение отмены заблокировано до завершения первого запроса.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.test.ts` — добавлена точечная unit-проверка печатного HTML: русские подписи, формат суммы, отсутствие технического `legal_name` и управляющих кнопок.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts` — усилены `S-31-TC-007` и `S-31-TC-008`: печатная сумма и отсутствие технического имени поля, блокировка повторной отмены во время незавершённого запроса и ровно один POST отмены.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — обязательный артефакт этапа.

## Гейты

- Красный по инфраструктуре: `npx --no-install tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend` не запустил компилятор: локального `frontend/node_modules/.bin/tsc` нет, затем `npx` завершился `ENOTFOUND registry.npmjs.org`.
- Красный только на чужих файлах: `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing` сообщил прежние новые нарушения в `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/ff/FfSettingsScreen.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Затронутый `FfBillingScreen.tsx` в отчёте отсутствует; базовая линия не менялась.
- Красный по инфраструктуре: `npm run test:unit -- --run src/screens/ff/FfBillingScreen.test.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend` завершился `sh: vitest: command not found`, потому что локальные frontend-зависимости отсутствуют.
- Красный по инфраструктуре: `npx --no-install playwright test tests-e2e/billing-invoices.spec.ts --grep 'billing invoice opens|billing invoice cancellation'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend` не запустил два назначенных сценария: локального Playwright нет, попытка `npx` обратиться к registry завершилась `ENOTFOUND`.
- Зелёный: `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing`.
- Красный по ограничениям рабочей копии: `git add -- frontend/src/screens/ff/FfBillingScreen.tsx frontend/src/screens/ff/FfBillingScreen.test.ts frontend/tests-e2e/billing-invoices.spec.ts night/volna-9-recovery/cards/09-billing/DEV.md && git diff --cached --check && git status --short && git commit -m 'night(09-billing): harden invoice print and cancellation'` не дошёл до индексации: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`). Чужой `JOURNAL.md` не индексировался.

## Не реализовано

- Буквальная реализация экранной части пунктов 6–7 контракта атома 11 выполнена в разрешённом слое. Доказать зелёными `tsc`, unit и e2e в этой рабочей копии не удалось из-за отсутствующих локальных npm-зависимостей и закрытого доступа к registry; поэтому результат нельзя считать прошедшим технические гейты.
- Находки 2, 4–7 из `REVIEW.md` относятся к backend API, сервисам, моделям и миграциям и не входят в роль `screen-dev` и разрешённые файлы атома 11; они не менялись.
- Часть находки 8 о тестировании живого backend read-model не может быть закрыта фронтенд-моком `billing-invoices.spec.ts`; для неё нужен отдельный backend/integration-атом. В этом атоме усилены только назначенные пользовательские сценарии `S-31-TC-007` и `S-31-TC-008`.
- Изменения и этот отчёт остались только в рабочем дереве: обязательный отдельный Git-коммит создать невозможно из-за запрета записи в служебный каталог worktree. Без снятия этого ограничения результат не сохранён в восстанавливаемом SHA.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не читались и не затрагивались.
