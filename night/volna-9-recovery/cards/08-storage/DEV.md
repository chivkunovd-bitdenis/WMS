# Фича 1

# Фича 1

# DEV · 08-storage · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный вне изменённого слоя: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py`. Новые нарушения уже находятся в неразрешённых этим атомом файлах: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; базовая линия не обновлялась.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — 6 passed.
- Выполнена целевая команда: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-002 blocks a rate that rounds to zero before saving|S-11-TC-018 blocks Moscow-past start dates with a visible explanation'`. Запуск остановлен средой до выполнения тестов: запрещено bind `127.0.0.1:18000` для webServer.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --list --grep 'S-11-TC-002 blocks a rate that rounds to zero before saving|S-11-TC-018 blocks Moscow-past start dates with a visible explanation'` — найдены ровно два целевых сценария.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check`.
- Git не сохранён: `git add` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за запрета песочницы (`Operation not permitted`); commit SHA отсутствует, изменения остаются только в этой рабочей копии.

## Не реализовано

- Для атома 1 все пункты контракта реализованы буквально: обе фикстуры возвращают пустой список расчётов, до нажатия проверяется видимая кнопка «Задать тариф», после нажатия — видимый диалог «Тариф хранения», затем — недоступность «Сохранить» и объясняющая подсказка.
- Находки 1 и 3 из `REVIEW.md` не менялись: они относятся к следующим атомам 2 и 3 из `FEATURES.md`, а текущая задача явно ограничена атомом 1.

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

# Фича 2

# DEV · 08-storage · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — 6 passed.
- Красный вне слоя атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` сообщает новые нарушения только в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; базовая линия не обновлялась.
- Заблокировано средой до выполнения тестов: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep 'administrator keeps a previous month without a tariff after saving a later rate|S-11-TC-017 keeps the saved tariff dialog open until statement reading recovers'` не запустился, потому что webServer не получил право слушать `127.0.0.1:18000` (`Errno 1: operation not permitted`).
- Зелёный разбор целевых сценариев без webServer: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --list --grep 'administrator keeps a previous month without a tariff after saving a later rate|S-11-TC-017 keeps the saved tariff dialog open until statement reading recovers'` — найдены ровно 2 сценария.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check`.
- Git не сохранён: `git add` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за запрета песочницы (`Operation not permitted`); commit SHA отсутствует, изменения остаются в этой рабочей копии.

## Не реализовано

Нет для атома 2. Добавлен браузерный сценарий: он открывает прошлый месяц без тарифа, сохраняет ставку с датой после окончания этого месяца, ждёт успешный повторный `GET /api/operations/storage/statements`, проверяет в его ответе `tariff_configured=false` и пустой список, а после закрытия диалога — видимые «Тариф хранения ещё не задан» и «Задать тариф». Ответ POST намеренно содержит непустые строки, поэтому локальная подмена состояния вместо GET приводит к падению сценария.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production и живой кабинет Wildberries не открывались и не использовались.

# Фича 3

# DEV · 08-storage · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/tests/cases/S-11.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/CASES.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

`S-11-TC-021` — новый постоянный номер проверки прошлой московской даты в диалоге тарифа.
`S-11-TC-018` сохранён только за отрицательным восстановленным остатком, запретом фиксации
и отсутствием частичного ledger-начисления.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — 6 passed.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check`.
- Целевые Playwright-сценарии найдены: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --list --grep 'S-11-TC-002 blocks a rate that rounds to zero before saving|S-11-TC-021 blocks Moscow-past start dates with a visible explanation|administrator keeps a previous month without a tariff after saving a later rate'` — 3 теста.
- Запуск тех же трёх Playwright-сценариев заблокирован средой до выполнения тестов: webServer не получил право слушать `127.0.0.1:18000` (`Errno 1: operation not permitted`).
- Красный вне слоя атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` сообщает новые нарушения только в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- Git не сохранён: `git add` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за запрета песочницы (`Operation not permitted`); commit SHA отсутствует, изменения остаются в этой рабочей копии.

## Не реализовано

Нет. Все пункты атома реализованы буквально. Ранее отмеченные ревьюером живые сценарии
минимальной ставки и повторного чтения прошлого месяца уже присутствуют в `storage.spec.ts`;
их фикстуры открывают пустое состояние и они включены в целевой список регрессии.

## Находки

Секреты, ключи, токены, `.env`, персональные данные и кабинеты учётных данных не открывались
и не использовались.
