# Фича 1

# DEV · 08-storage · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/docs/blockers/S-11.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный вне атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` сообщил новые нарушения в `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`. Эти файлы не входят в S-11; базовая линия не менялась.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — 7 passed.
- Блокировка среды: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:e2e -- tests-e2e/storage.spec.ts --grep 'S-11-TC-002 blocks a rate that rounds to zero before saving'` не стартовал, потому что песочница запретила API слушать `127.0.0.1:18000` (`Errno 1: operation not permitted`).
- Зелёный разбор целевого e2e без запуска web server: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-002 blocks a rate that rounds to zero before saving' --list` — найден 1 тест.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check`.
- Git не сохранён: `git add` не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за запрета песочницы (`Operation not permitted`), поэтому commit SHA отсутствует. Изменения лежат только в этой рабочей копии.

## Не реализовано

Нет. Атом 1 реализован буквально: общая и индивидуальная ставки `0,001` блокируются до POST с объяснением о минимально сохраняемых `0,01 ₽/л·день`; значение `0,005` остаётся допустимым, так как сервер сохраняет его как `0,01` по `ROUND_HALF_UP`. Находки ревью о повторном чтении после POST и экранных проверках других правил относятся к атомам 2–4 из `FEATURES.md` и намеренно не смешивались с этим атомом.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production и живой кабинет Wildberries не открывались и не использовались.

# Фича 2

# DEV · 08-storage · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — 7 passed.
- Заблокировано средой: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:e2e -- tests-e2e/storage.spec.ts --grep 'S-11-TC-017 (tariff repricing failure keeps the last successful summary|keeps the saved tariff dialog open until statement reading recovers)'` не запустился: песочница запретила API слушать `127.0.0.1:18000` (`Errno 1: operation not permitted`).
- Зелёный разбор целевых сценариев без запуска web server: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-017 (tariff repricing failure keeps the last successful summary|keeps the saved tariff dialog open until statement reading recovers)' --list` — найдены 2 сценария.
- Красный вне атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` сообщает новые нарушения только в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Они не входят в этот экран или атом; базовая линия не менялась.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check`.
- Git не сохранён: `git add` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за запрета песочницы (`Operation not permitted`); commit SHA отсутствует, изменения лежат только в этой рабочей копии.

## Не реализовано

Нет для атома 2. После успешного POST страница очищает неподтверждённую таблицу и ждёт повторный GET. При ошибке чтения диалог остаётся открытым с сообщением «Тариф сохранён, но расчёты не обновлены», POST заблокирован; «Повторить» выполняет только GET и закрывает диалог после успешного серверного ответа. Находки повторного ревью 1, 3 и 4 принадлежат атомам 1, 3 и 4 из `FEATURES.md` и не смешивались с этим атомом.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production и живой кабинет Wildberries не открывались и не использовались.

# Фича 4

# DEV · 08-storage · атом 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — 6 passed. Тест даты теперь проверяет только чистую функцию; чтение `FfStoragePage.tsx` как текста удалено.
- Заблокировано средой: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:e2e -- tests-e2e/storage.spec.ts --grep 'S-11-TC-018 blocks Moscow-past start dates with a visible explanation'` не смог запустить web server: песочница запрещает слушать `127.0.0.1:18000` (`Errno 1: operation not permitted`).
- Зелёный разбор целевого браузерного сценария: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-018 blocks Moscow-past start dates with a visible explanation' --list` — найден ровно один сценарий.
- Красный вне атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` сообщает новые нарушения в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Эти файлы не относятся к S-11 или текущему атому; базовая линия не менялась.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check`.
- Git не сохранён: `git add` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за запрета песочницы (`Operation not permitted`); commit SHA отсутствует, изменения остаются в этой рабочей копии.

## Не реализовано

Нет. Добавлен браузерный сценарий отрисованного диалога: для общей и индивидуальной ставок он выбирает вчерашнюю московскую дату, проверяет недоступность «Сохранить» и соответствующую видимую подсказку, а после выбора сегодняшней даты — снятие запрета. Запуск этого сценария требует среды, разрешающей локальный порт web server.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production и живой кабинет Wildberries не открывались и не использовались.
