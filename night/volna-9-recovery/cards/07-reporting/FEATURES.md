ФИЧ: 2

## Фичи

### 1. Сохранить старые адреса самостоятельного кабинета селлера

Оператор, который открывает корень кабинета селлера (`/`) или сохранённую ссылку вроде `/documents`, попадёт в тот же seller-кабинет, а не на пустой экран; канонический адрес `/app/seller/reports` при этом остаётся рабочим. Production-сборка и Caddy должны согласованно направлять старые пути в базовый путь `BrowserRouter` `/app/seller`.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/Dockerfile.seller.prod`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/deploy/Caddyfile.seller.local`

Зависимости: нет.

Проверка: собрать самостоятельный seller-образ и открыть через его Caddy `/`, `/documents` и `/app/seller/reports`. Первые два адреса должны перенаправить либо отрендерить кабинет в корректном базовом пути без пустого экрана; канонический адрес должен отрендерить seller-бандл и маршрут отчёта.

### 2. Запускать e2e отчёта на seller-бандле с production basename

Тестировщик запускает сценарий прямого входа селлера без `can_products` на `/app/seller/reports`; Playwright подаёт именно seller-бандл с `VITE_SELLER_ROUTER_BASENAME=/app/seller`, поэтому сценарий проверяет изменённую production-маршрутизацию, видимый отказ и отсутствие запросов к `/api/reports/*`, а не FF-оболочку.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/playwright.config.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/vite.config.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts`

Зависимости: фича 1 — тест закрепляет итоговую совместимость адресов и канонический basename после исправления production-публикации.

Проверка: выполнить адресный Playwright-сценарий `seller staff without products access cannot open the direct reports route` в конфигурации, которая отдаёт seller-bundle на `/app/seller/*`. Проверить, что URL остаётся `/app/seller/reports`, показан `seller-access-denied`, FF-элементы отчёта отсутствуют и запросов к `/api/reports/*` нет. Дополнительно проверить сценарий на root/старой ссылке из фичи 1, чтобы он не регрессировал.

## Порядок

Сначала выполнить фичу 1: она восстанавливает рабочую публикацию всех старых адресов seller-кабинета и сохраняет канонический base path. Затем выполнить фичу 2, потому что её e2e-конфигурация должна проверять уже согласованную схему маршрутизации. Параллельное выполнение не рекомендуется: обе фичи меняют единый контракт путей самостоятельного seller-приложения.

## Что осталось за бортом

- Остальные части контракта S-33 и уже принятая проверка прав `inventory` не входят в перепланирование: повторный `REVIEW.md` признал их закрытыми.
- Новые ui-kit-компоненты `ReportMetricStrip`, `MovementFlowChart` и `WarningNotice` не добавляются: это не относится к двум незакрытым регрессиям маршрутизации.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой сервер `194.87.96.144` и запись в Wildberries не читались и не затрагивались.
