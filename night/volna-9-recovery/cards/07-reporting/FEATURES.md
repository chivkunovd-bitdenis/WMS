ФИЧ: 2

## Фичи

### 1. Включить Caddy-конфигурацию seller-портала в воспроизводимую сборку

Оператор, открывший старую ссылку `/` или `/documents` на самостоятельном seller-хосте, попадает на канонический `/app/seller`; это поведение собирается из чистого checkout, а не зависит от локального игнорируемого файла разработчика.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/deploy/Caddyfile.seller`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/Dockerfile.seller.prod`

Зависимости: нет.

Проверка: в чистом checkout оба файла присутствуют в Git; `docker build -f frontend/Dockerfile.seller.prod .` завершается успешно. В собранном контейнере запросы `/` и `/documents` получают постоянный редирект под `/app/seller`, а `/app/seller/reports` отдаёт seller-bundle, не FF-bundle.

### 2. Передать production-префикс seller-портала в Playwright worker

Разработчик, запуская штатный `npm run test:e2e`, проверяет seller-сценарии по `/app/seller/*`: тот же префикс доступен и Vite-серверу, и Playwright worker, поэтому прямой маршрут отчётов не уходит в FF-bundle.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/playwright.config.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/inbound-boxes-helpers.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts`

Зависимости: нет.

Проверка: `npm run test:e2e -- seller-reports.spec.ts` выполняет, а не только перечисляет, адресный сценарий. Его `sellerPath('/reports')` равен `/app/seller/reports`, браузер остаётся на этом пути, показывает seller-состояние доступа и не рендерит `ff-reports-*`.

## Порядок

Фичи 1 и 2 независимы и могут выполняться параллельно разными frontend-исполнителями. После их объединения нужно повторно проверить чистую сборку seller-образа и адресный E2E-сценарий: первая фича подтверждает production-артефакт, вторая — что тесты действительно проходят его маршрут.

## Что осталось за бортом

- Ничего нового: повторное планирование ограничено двумя незакрытыми находками из `REVIEW.md`; уже принятые API, экран отчёта и ui-kit намеренно не возвращены в разработку.
