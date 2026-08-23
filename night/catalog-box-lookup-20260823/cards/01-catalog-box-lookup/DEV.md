# Фича 1

# DEV · 01-catalog-box-lookup · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/screens.registry.json` — в список файлов `S-16` добавлен локальный владелец блока коробов: `src/screens/v2/FfCatalogInboundPackages.tsx`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md` — отчёт роли `screen-dev` для атома 1.

## Гейты

- Зелёный: `node --input-type=module -e "import fs from 'node:fs'; const registry = JSON.parse(fs.readFileSync('frontend/screens.registry.json', 'utf8')); const screen = registry.screens?.find((item) => item.id === 'S-16' && item.route === '/app/ff/products'); const expected = 'src/screens/v2/FfCatalogInboundPackages.tsx'; if (!screen || !screen.files?.includes(expected)) throw new Error('S-16 owner is missing'); console.log('registry JSON parsed; S-16 owns ' + expected);"` — JSON разбирается, `S-16` владеет требуемым файлом.
- Зелёный: `git diff --check -- frontend/screens.registry.json` — ошибок пробелов нет; diff содержит ровно одно добавление файла в `S-16`.
- Красный, ограничение окружения: `npx tsc --noEmit -p tsconfig.app.json` и `npx --no-install tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend` не выполнились: локальный `frontend/node_modules/.bin/tsc` отсутствует; `npm exec --offline` подтвердил отсутствие TypeScript в кэше (`ENOTCACHED`).
- Красный, вне границы атома: `python3 scripts/ui/ui_guard.py` сообщил новые нарушения в не затронутых этим атомом файлах `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/FfProductsCatalogScreen.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась, а эти файлы не правились, так как атом разрешает только реестр.
- Красный, ограничение окружения: `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend` завершился с `sh: vitest: command not found`; локальный `node_modules` отсутствует. Для декларативного изменения реестра отдельного unit-теста в репозитории нет.
- Не сохранено в Git: `git add frontend/screens.registry.json night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-catalog-box-lookup/index.lock` (`Operation not permitted`). Поэтому отдельный commit SHA получить в этом окружении нельзя.

## Не реализовано

- Все пункты контракта, относящиеся к UI и поведению, намеренно не изменялись: этот проход ограничен только атомом 1 из `FEATURES.md` — регистрацией владельца файла в `S-16`.
- Находки ревью 2–8 не относятся к файлу и слою атома 1; они остаются следующими отдельными атомами из `FEATURES.md` и в этом проходе не затрагивались.

## Находки

Нет находок о данных, секретах или персональных данных.

# Фича 2

# DEV · 01-catalog-box-lookup · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/app/services/inbound_package_catalog_service.py` — read-модель короба получила явный признак `fully_distributed`: он истинен только для короба с хотя бы одной строкой, у которого весь объём разложен (`quantity == posted_qty` для каждой строки), независимо от статуса приёмки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/app/api/inbound_package_catalog.py` — оба существующих GET-ответа каталога передают `fully_distributed`; для грузоместа признак всегда `false`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/tests/test_inbound_package_catalog.py` — тест закрепляет адресный поиск полностью разложенного короба в приёмке `sorting`, нулевой остаток, пустые текущие строки и исключение объекта из обычного списка.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md` — отчёт роли `backend-dev` по атому 2.

## Миграции

Нет: изменена только read-модель существующих API, схема БД не менялась.

## Тесты

- `backend/tests/test_inbound_package_catalog.py` — `GET /operations/inbound-packages/lookup` для `INB-CURRENT-DISTRIBUTED` в приёмке `sorting` возвращает `fully_distributed: true`, `remaining_qty: 0` и пустой состав; обычный `GET /operations/inbound-packages` этот короб не включает.

## Гейты

- Зелёный: `git diff --check` — ошибок пробелов нет.
- Зелёный: `ruff check app/services/inbound_package_catalog_service.py app/api/inbound_package_catalog.py ../backend/tests/test_inbound_package_catalog.py` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend`) — `All checks passed!`.
- Зелёный: `mypy app/services/inbound_package_catalog_service.py app/api/inbound_package_catalog.py` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend`) — `Success: no issues found in 2 source files`.
- Зелёный: `pytest -q tests/test_inbound_package_catalog.py` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend`) — `2 passed in 4.05s`.
- `python3 scripts/ci/back_guard.py` и `python3 scripts/ci/check_migrations.py` не запускались: атом не добавляет маршрут и не добавляет миграцию.
- Не сохранено в Git: `git add backend/app/services/inbound_package_catalog_service.py backend/app/api/inbound_package_catalog.py backend/tests/test_inbound_package_catalog.py night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-catalog-box-lookup/index.lock` (`Operation not permitted`), поэтому отдельный commit SHA получить в этом окружении нельзя.

## Не реализовано

- Находки ревью 1 и 3–8 не относятся к backend-слою этого атома или принадлежат следующим отдельным фичам из `FEATURES.md`; они намеренно не менялись.

## Находки

Нет находок о данных, секретах или персональных данных. Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались.

# Фича 3

# Backend dev · 01-catalog-box-lookup · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/app/services/inbound_package_catalog_service.py` — обычный список отбирает короба на уровне SQL: короб с положительным остатком либо пустой короб незавершённой приёмки; грузоместа завершённых приёмок исключаются до materialization (материализации результатов запроса).
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/tests/test_inbound_package_catalog.py` — добавлена проверка HTTP-состава и SQL-предикатов, включая отсутствие идентификаторов полностью разложенных и завершённых коробов в запросе строк короба.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md` — отчёт этого атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend && ruff check app/services/inbound_package_catalog_service.py tests/test_inbound_package_catalog.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend && mypy app/services/inbound_package_catalog_service.py` — `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend && pytest -q tests/test_inbound_package_catalog.py` — `3 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && git diff --check` — успешно.
- `python3 scripts/ci/back_guard.py` и `python3 scripts/ci/check_migrations.py` не запускались: атом не добавляет маршрут или миграцию.
- `git add … && git commit -m "fix: limit inbound package catalog queries"` — не выполнен: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-catalog-box-lookup/index.lock` (`Operation not permitted`). Изменения остаются локальными и незафиксированными.

## Не реализовано

Нет: выполнен только атом 3 из `FEATURES.md`. Соседние находки ревью, относящиеся к frontend и e2e, намеренно не затрагивались.

# Фича 4

# DEV · 01-catalog-box-lookup · атом 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/src/screens/v2/FfCatalogInboundPackages.tsx` — адресный результат сохраняется при обычной загрузке списка и остаётся видимым вместе со скелетоном, после ошибки и после «Повторить»; `fully_distributed` показывает состояние «Товар из короба уже разложен» независимо от статуса приёмки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/tests-e2e/catalog-box-lookup.spec.ts` — целевой сценарий `S-16-TC-015`: полностью разложенный короб остаётся раскрытым во время первой загрузки, после её ошибки и после успешного повтора.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md` — артефакт этого атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npx tsc --noEmit -p tsconfig.app.json` — команда завершилась с кодом `0` без вывода. Для исключения подмены одноимённой утилиты дополнительно выполнена `npx --yes --package typescript@~6.0.2 tsc --noEmit -p tsconfig.app.json`; также код `0`, без ошибок.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && python3 scripts/ui/ui_guard.py` — красный из-за новых нарушений вне этого атома: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/FfProductsCatalogScreen.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию не обновлял и чужие файлы не менял.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npm run test:unit -- FfCatalogInboundPackages` — красный: `sh: vitest: command not found`; в рабочей копии отсутствует `frontend/node_modules/.bin/vitest`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npm run test:e2e -- catalog-box-lookup.spec.ts` — красный: `playwright test` вызвал системный Python CLI и вернул `error: unknown command 'test'`; локальный `frontend/node_modules/.bin/playwright` отсутствует.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && git diff --check` — зелёный.
- `git add frontend/src/screens/v2/FfCatalogInboundPackages.tsx frontend/tests-e2e/catalog-box-lookup.spec.ts night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md && git commit -m "fix: preserve catalog box lookup result"` — не выполнен: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-catalog-box-lookup/index.lock` (`Operation not permitted`). Изменения сохранены в рабочей копии, но отдельный commit SHA в этом окружении получить нельзя.

## Не реализовано

Нет. Реализован только атом 4 из `FEATURES.md`. Находки ревью о фильтре селлера и гонках сканирования относятся к отдельным атомам 5 и 6 и намеренно не затрагивались.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались. Боевой сервер `194.87.96.144` не использовался.

# Фича 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/src/screens/v2/FfProductsCatalogScreen.tsx` — каталог для S-16 загружается без серверного `seller_id`; фильтр селлера по-прежнему применяется только к `filteredRows` основной таблицы. Поэтому адресно найденный короб сохраняет строки товара другого селлера.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npx tsc --noEmit -p tsconfig.app.json` — завершилась с кодом 0, диагностик нет.
- Красный, не относится к изменению атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && python3 scripts/ui/ui_guard.py` — новые нарушения базовой линии: `src/components/WbProductPickerDialog.tsx` (экран-монолит 0 → 646), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2498), `src/screens/v2/FfProductsCatalogScreen.tsx` (1414 → 1461), `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1169). Исправление этого атома заменило шесть строк на шесть и не увеличило размер S-16; три остальных файла вне разрешённой границы.
- Красный, ограничение окружения: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npm run test:unit -- frontend/src/screens/v2/FfProductsCatalogScreen.test.ts` — `sh: vitest: command not found`. Целевого unit-файла для этого экрана в репозитории нет; полный набор тестов атомарной проверкой не запускался.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && git diff --check`.
- Не сохранено коммитом: `git commit -m "fix(catalog): keep box composition independent of seller filter"` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-catalog-box-lookup/index.lock` (`Operation not permitted`). Рабочее дерево и артефакт сохранены, но проверенного SHA нет.

## Не реализовано

- В пределах атома 5 все требуемые изменения реализованы. Проверка пользовательского сценария Playwright не добавлялась: он относится к отдельной фиче 8 из `FEATURES.md`, а текущий атом разрешает менять только `FfProductsCatalogScreen.tsx`.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались.

# Фича 6

# Screen-dev · 01-catalog-box-lookup · атом 6

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/src/screens/v2/FfCatalogInboundPackages.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/src/screens/v2/FfProductsCatalogScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/tests-e2e/catalog-box-lookup.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend`) — не выполнен: локальный `tsc` отсутствует, а `npx` не смог загрузить пакет из-за `ENOTFOUND registry.npmjs.org`.
- `python3 scripts/ui/ui_guard.py` (из корня рабочей копии) — красный: храповик сообщает новые отступления в `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/FfProductsCatalogScreen.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не изменялась. Для S-16 причина — уже существующий размер экрана; данный атом добавляет одну защитную строку.
- `npm run test:unit` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend`) — не выполнен: `sh: vitest: command not found`.
- `npx playwright test tests-e2e/catalog-box-lookup.spec.ts --grep 'late failed scan'` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend`) — не выполнен: локальный Playwright отсутствует, а `npx` не смог загрузить пакет из-за `ENOTFOUND registry.npmjs.org`.
- `git diff --check` — зелёный.
- Сохранение Git — не выполнено: `git add … && git commit -m "fix(catalog): ignore stale inbound scan responses"` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-catalog-box-lookup/index.lock` (`Operation not permitted`). Поэтому проверенного commit SHA нет.

## Не реализовано

Нет. Поздний неуспешный lookup теперь возвращает `null`, если его номер запроса устарел; родитель не меняет ошибку, фокус или выделение для `null`. Добавлен сценарий S-16-TC-013/S-16-TC-016 с задержанным первым lookup, успешным вторым и начатым третьим вводом.

## Находки

Зависимости frontend не установлены в этой рабочей копии, а сеть до npm registry недоступна, поэтому TypeScript, Vitest и целевой Playwright-сценарий здесь не были исполнены. Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 7

# Screen-dev · 01-catalog-box-lookup · атом 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/src/screens/v2/FfCatalogInboundPackages.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend`) — не завершён: в рабочей копии отсутствует `frontend/node_modules/.bin/tsc`; `npx` ожидал загрузку пакета из сети и был остановлен после 60 секунд без вывода.
- `python3 scripts/ui/ui_guard.py` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup`) — красный по существующим отступлениям в `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/FfProductsCatalogScreen.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`. Этот атом не меняет ни один из них и базовая линия не обновлялась.
- `npm run test:unit -- --run frontend/src/screens/v2/FfCatalogInboundPackages.test.tsx` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend`) — не выполнен: `sh: vitest: command not found`. Отдельного unit-теста этого атома в контракте и реестре нет; следующий атом 8 владеет e2e-файлом.
- `git diff --check` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup`) — зелёный.

## Не реализовано

Нет. Если `request_display_number` уже содержит `№`, заголовок показывает номер без второго префикса; fallback на `request_id` добавляет ровно один `№`.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались. Локальные зависимости frontend отсутствуют, поэтому TypeScript и Vitest в этой рабочей копии не были выполнены.

# Фича 8

# Screen-dev · 01-catalog-box-lookup · атом 8

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/tests-e2e/catalog-box-lookup.spec.ts` — остаток проверяется через конкретную строку таблицы состава и её ячейку `QtyCell`, а не по произвольной цифре в accordion; добавлен сценарий `S-16-TC-017` для фильтра селлера A и адресного скана короба селлера B с проверками SKU, названия, ШК и остатка.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md` — отчёт атома 8.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npx tsc --noEmit -p tsconfig.app.json` — код возврата `0`, диагностик нет.
- Красный вне слоя атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && python3 scripts/ui/ui_guard.py` — новые отступления уже есть в чужих файлах `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/FfProductsCatalogScreen.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- Красный, ограничение окружения: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npm run test:unit -- catalog-box-lookup` — `sh: vitest: command not found`; локальный `vitest` отсутствует.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npx playwright test tests-e2e/catalog-box-lookup.spec.ts --grep 'catalog scan follows|catalog ignores'` — код возврата `0`; выполнены сценарии остатка/повтора списка/фильтра селлера и позднего отказа первого lookup.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && git diff --check` — ошибок пробелов нет.
- Не сохранено commit: `git add frontend/tests-e2e/catalog-box-lookup.spec.ts night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md && git commit -m "test: strengthen catalog box lookup e2e"` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-catalog-box-lookup/index.lock` (`Operation not permitted`). Поэтому проверенного SHA нет.

## Не реализовано

Нет. Реализован только атом 8 из `FEATURES.md`; продуктовые файлы и соседние задачи не менялись.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались. Боевой сервер `194.87.96.144` не использовался.
