# 09-billing — screen-dev, переделка атома 10

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — относящаяся к экранному слою находка 1 из `REVIEW.md` уже исправлена и сохранена в текущем `HEAD` (`11cd945941aad871d1d181420e2ad2e4729d81af`): человекочитаемый номер приёмки открывает штатный диалог исходного документа, номер MP-отгрузки ведёт к существующей отгрузке, а технические источники без пользовательского маршрута остаются обычным текстом. Нового diff в этом проходе не потребовалось.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts` — сценарий `S-31-TC-004` в текущем `HEAD` нажимает номер приёмки, проверяет открытие штатного диалога и сохранение маршрута `/app/ff/billing`; `S-31-TC-005` и `S-31-TC-012` проверяют режим по исполнителям и начисление без тарифа. Нового diff в этом проходе не потребовалось.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — записан обязательный отчёт этого прохода.

## Гейты

- **Красный по инфраструктуре:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm_config_offline=true npx tsc --noEmit -p tsconfig.app.json` — компилятор не запустился: локального пакета `tsc` нет, а npm в режиме только локального кэша завершился с `ENOTCACHED`.
- **Красный в целом, но без нового нарушения в файле атома:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — `FfBillingScreen.tsx` в отчёте отсутствует; общий храповик остановился на чужих `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/ff/FfSettingsScreen.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. `frontend/src/App.tsx` отмечен как улучшившийся с 3492 до 3491 строки. Базовая линия не менялась.
- **Красный по инфраструктуре:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts` — адресный unit-тест не стартовал: `vitest: command not found`, потому что `frontend/node_modules` отсутствует.
- **Красный по инфраструктуре:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm_config_offline=true npx playwright test tests-e2e/billing-ledger.spec.ts --grep 'billing ledger preserves filters and month context|billing ledger performer mode hides money columns|billing ledger shows unpriced operation without blocking it|billing ledger clears stale rows on load error|billing ledger uses the canonical storage service code'` — назначенные сценарии не стартовали: локального Playwright нет, npm завершился с `ENOTCACHED`.
- **Зелёный:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check`.
- **Красный из-за прав рабочей копии:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git add -- night/volna-9-recovery/cards/09-billing/DEV.md && git diff --cached --check && git status --short && git commit -m 'night(09-billing): document atom 10 screen rework'` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`). Несвязанное изменение `night/volna-9-recovery/JOURNAL.md` не индексировалось.
- Полные backend `pytest`, `ruff check .` и `mypy .` не запускались: для атома 10 они прямо запрещены.

## Не реализовано

- Находки 2 и 3 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/REVIEW.md` относятся к backend-сервису жизненного цикла MP-отгрузки и backend-тесту неизменяемого счёта. Они не входят в роль `screen-dev`, слой экрана или два разрешённых файла атома и поэтому не изменялись.
- Буквально подтвердить зелёными `tsc`, unit и e2e не удалось из-за отсутствующих локальных npm-зависимостей. Экранная находка исправлена в Git, но технические гейты этого прохода остаются неподтверждёнными.
- Для `storage_measurement` и `billing_reversal` ссылка не добавлялась: контракт не задаёт существующий пользовательский экран для этих технических источников, поэтому выдумывать маршрут на экранном слое нельзя.
- Новый отчёт `DEV.md` записан в требуемый абсолютный путь, но сохранить его отдельным Git-коммитом невозможно из-за запрета записи в служебный каталог зарегистрированного worktree. Экранный результат восстанавливается из `11cd945941aad871d1d181420e2ad2e4729d81af`; обновлённый отчёт пока остаётся только в рабочем дереве.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой кабинет Wildberries и боевой production не читались и не затрагивались.
