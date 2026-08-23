# DEV · 04-warehouse-switch · атом 4 · переделка по REVIEW.md

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx` — `load()` переведён на единый механизм замены незавершённого запроса; при исчезновении складского контекста активный запрос также прерывается.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts` — добавлен тестируемый `runLatestFbsOrdersLoad`: новый запуск прерывает прежний `AbortController`, молча принимает `AbortError` и завершает индикатор только для актуального запроса. Ранее добавленные `signal` в `fetchFbsWorklist` и `fetchFbsSupplyWorklist` сохранены.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.test.ts` — добавлен регрессионный `S-03-TC-001`: медленная загрузка «Севера» прерывается сменой на «Юг», второй запрос стартует немедленно, ошибки в state нет, итоговый state содержит только данные «Юга».
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — отчёт этого атомарного прохода.

До начала прохода уже был изменён `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/JOURNAL.md`; это чужое изменение не редактировалось и в атом не входит.

## Гейты

- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend`; команда `npm run test:unit -- src/screens/v2/fbsApi.test.ts` — зелёная, код 0: `1 passed` файл, `10 passed` тестов.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend`; команда `npx tsc --noEmit -p tsconfig.app.json` — зелёная, код 0, ошибок нет.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch`; команда `python3 scripts/ui/ui_guard.py` — красная, код 1. Скрипт повторно сообщает о накопленных до этого прохода монолитах: `WbProductPickerDialog.tsx` (`0 → 646`), `FfFbsOrdersScreen.tsx` (`1587 → 1676`), `FfFbsStockSyncScreen.tsx` (`1083 → 1121`), `FfFbsSupplyWorkspace.tsx` (`2493 → 2605`) и `SellerInboundDraftScreen.tsx` (`1111 → 1267`). Baseline не изменялся. Текущий атом не ухудшил целевой экран: в `HEAD` было 1689 строк, после переделки — 1675 строк.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch`; команда `git diff --check` — зелёная, ошибок пробелов нет.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch`; команда `git add frontend/src/screens/v2/FfFbsOrdersScreen.tsx frontend/src/screens/v2/fbsApi.ts frontend/src/screens/v2/fbsApi.test.ts night/volna-9-recovery/cards/04-warehouse-switch/DEV.md && git diff --cached --check && git commit -m "fix(fbs): cancel stale warehouse worklist loads"` — красная до стадии индексации: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Чужой `JOURNAL.md` в команду не включался.
- Полные frontend/backend regression suites, полный `pytest`, `ruff check .` и `mypy .` не запускались: для этого атома прямо разрешены только его тестовый файл и относящиеся к вердикту проверки.

## Не реализовано

- Из требований атома 4 ничего не пропущено: прежний запрос прерывается, новый начинается без ожидания, все вызовы worklist внутри `load()` получают `signal`, `AbortError` не записывается в state, поллинг сохраняет семантику «последний тик побеждает», а гонка «Север → Юг» закреплена unit-тестом с проверкой итогового state.
- Находки 1 (S-14 frontend) и 2 (S-28 backend) из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/REVIEW.md` не трогались: пользователь назначил только атом 4 и запретил переходить к соседним задачам.
- `ui_guard.py` не удалось сделать зелёным буквально: он сравнивает всю ветку с baseline и видит пять накопленных монолитов, существовавших до текущего прохода. Разбиение этих экранов и обновление baseline запрещены границами роли и атома; новых отклонений в текущем diff нет.
- Живой браузерный проход не выполнялся: роль `screen-dev` ограничена реализацией и атомарными техническими проверками; продуктовая браузерная приёмка выполняется отдельной ролью после разработки.
- Отдельный commit и push не созданы: sandbox разрешает запись в worktree, но запрещает создание Git lock-файла в общем каталоге зарегистрированного worktree. Создавать второй checkout или временный клон запрещено правилами проекта, поэтому результат остаётся локально реализованным, но не сохранённым в новом Git-коммите.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не открывались и не изменялись.
