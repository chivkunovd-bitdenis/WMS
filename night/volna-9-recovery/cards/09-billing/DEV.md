# 09-billing · screen-dev · переделка атома 10

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — экранная часть находок 1 и 3 из `REVIEW.md` уже сохранена в текущем `HEAD`: журнал запрашивает живой API через `period=YYYY-MM`, читает `{ entries: [...] }`, не отправляет `seller_id=all`, а хранение использует единый код `storage_liter_day` в фильтре, строках и детализации счёта.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts` — экранная часть находки 8 уже сохранена в текущем `HEAD`: `S-31-TC-004`, `S-31-TC-005`, `S-31-TC-012`, очистка устаревших строк при ошибке и регресс канонического кода хранения проверяют реальную форму ответа и параметр `period`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — записан этот отчёт переделки.

Экран и e2e-файл не потребовали нового diff в этом проходе: относящиеся к ним исправления уже находятся в коммите `b9387460608031ec9267c5d606e42e9b78d5e313`, который является текущим `HEAD`. Чужое изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/JOURNAL.md` не менялось и не добавлялось в индекс.

## Гейты

- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — в рабочей копии нет локального `typescript`; `npx` не получил бинарник из недоступной сети и после 60 секунд без вывода был остановлен (`exit 130`).
- Красный, новых нарушений в файлах атома нет: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — храповик сообщил только о росте чужих файлов: `src/App.tsx` (3492 → 3503), `src/components/WbProductPickerDialog.tsx` (0 → 646), `src/screens/ff/FfSettingsScreen.tsx` (701 → 795), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2498), `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1169). Базовая линия не обновлялась.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts` — `sh: vitest: command not found`, потому что в рабочей копии нет `node_modules`.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx playwright test tests-e2e/billing-ledger.spec.ts --grep 'billing ledger preserves filters and month context|billing ledger performer mode hides money columns|billing ledger shows unpriced operation without blocking it|billing ledger clears stale rows on load error|billing ledger uses the canonical storage service code'` — в рабочей копии нет локального Playwright; `npx` не получил бинарник из недоступной сети и после 30 секунд без вывода был остановлен (`exit 130`).
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check`.
- Красный: `git add night/volna-9-recovery/cards/09-billing/DEV.md && git commit -m 'night(09-billing): document atom 10 rework'` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock`: `Operation not permitted`. Чужой `JOURNAL.md` в индекс не добавлялся.

Полные backend `pytest`, `ruff check .` и `mypy .` не запускались: они прямо запрещены для этого атома.

## Не реализовано

- Находки 2, 4, 5, 6 и 7 из `REVIEW.md` относятся к backend API, сервисам, миграциям и живому read-model. Роль `screen-dev` и список разрешённых файлов запрещают исправлять их в этом атоме.
- Клик по человекочитаемому номеру исходного документа нельзя реализовать буквально только в `FfBillingScreen.tsx`: текущий ledger API не возвращает маршрут или тип документа, а по замечанию 2 возвращает UUID вместо пользовательского номера. Выдумывать маршрут на экранном слое запрещено контрактом роли.
- Зелёные frontend-гейты подтвердить не удалось из-за отсутствующих локальных npm-зависимостей и недоступного npm registry. Кодовые исправления атома сохранены в Git-коммите `b9387460608031ec9267c5d606e42e9b78d5e313`, но новый отчёт `DEV.md` остался незакоммиченным из-за запрета записи в служебный Git-каталог worktree.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой кабинет Wildberries и боевой прод не открывались и не затрагивались.
