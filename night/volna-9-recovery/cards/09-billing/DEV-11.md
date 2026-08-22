# 09-billing — screen-dev, переделка атома 11

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — заново записан обязательный отчёт переделки атома 11 с точными командами и результатами гейтов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — нового diff в этом проходе не потребовалось: относящаяся к экранному слою находка 1 из `REVIEW.md` уже исправлена и сохранена в текущей истории Git коммитом `11cd945941aad871d1d181420e2ad2e4729d81af`. Человекочитаемый номер приёмки открывает штатный диалог исходного документа, номер MP-отгрузки ведёт к существующей отгрузке, технический источник без пользовательского маршрута остаётся текстом.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts` — нового diff в этом проходе не потребовалось: текущие сценарии `S-31-TC-007` и `S-31-TC-008` уже проверяют раскрытие исходных документов, печатное HTML-представление без UI-управления, обязательное подтверждение отмены и блокировку повторного запроса отмены.

## Гейты

- **Красный по инфраструктуре:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm_config_offline=true npx tsc --noEmit -p tsconfig.app.json` — локального `tsc` нет; npm в режиме только локального кэша завершился с `ENOTCACHED`, не найдя пакет в кэше.
- **Красный только на чужих файлах:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — `FfBillingScreen.tsx` в отчёте отсутствует. Общий храповик остановился на ранее существующих новых нарушениях в `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/ff/FfSettingsScreen.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; `frontend/src/App.tsx` отмечен как улучшившийся. Базовая линия не менялась.
- **Красный по инфраструктуре:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- --run src/screens/ff/FfBillingScreen.test.ts` — адресный unit-тест экрана не стартовал: `vitest: command not found`, потому что `frontend/node_modules` отсутствует.
- **Красный по инфраструктуре:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm_config_offline=true npx playwright test tests-e2e/billing-invoices.spec.ts --grep 'billing invoice opens, reveals documents and starts print|billing invoice cancellation is confirmed and idempotent in UI'` — назначенные `S-31-TC-007` и `S-31-TC-008` не стартовали: локального Playwright нет, а npm завершился с `ENOTCACHED`.
- **Зелёный:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check`.
- **Красный по правам рабочей копии:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git add -- night/volna-9-recovery/cards/09-billing/DEV.md && git diff --cached --check && git status --short && git commit -m 'night(09-billing): document atom 11 screen rework'` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`). Несвязанное изменение `night/volna-9-recovery/JOURNAL.md` не индексировалось.
- Полные backend `pytest`, `ruff check .` и `mypy .` не запускались: атомарная проверка прямо запрещает их на этом шаге.

## Не реализовано

- Находки 2 и 3 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/REVIEW.md` относятся к backend-сервису жизненного цикла MP-отгрузки и backend-тесту неизменяемого закрытого счёта. Они не входят в роль `screen-dev`, экранный слой или два разрешённых файла атома 11, поэтому backend не изменялся.
- Буквально подтвердить зелёными `tsc`, `test:unit` и двумя e2e-сценариями не удалось из-за отсутствующих локальных npm-зависимостей и отсутствия нужных пакетов в npm-кэше. Экранный код и проверки находятся в Git, но технические гейты этого прохода остаются неподтверждёнными.
- Для `storage_measurement` и других технических источников ссылка не добавлялась: контракт не задаёт существующий пользовательский экран, а роль запрещает импровизировать маршрут.
- Обновлённый `DEV.md` остался в рабочем дереве: сохранить его отдельным Git-коммитом невозможно из-за запрета записи в служебный каталог зарегистрированного worktree. Экранное исправление восстанавливается из `11cd945941aad871d1d181420e2ad2e4729d81af`, но новый отчёт пока не имеет собственного SHA.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой кабинет Wildberries и боевой production `194.87.96.144` не читались и не затрагивались.
