# Screen-dev · 07-reporting · атом 3 · повторная доработка

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/Dockerfile.seller.prod` — production-сборка самостоятельного кабинета селлера задаёт `VITE_SELLER_ROUTER_BASENAME=/app/seller`, поэтому канонический адрес `/app/seller/reports` сопоставляется с маршрутом `/reports` внутри `SellerApp`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts` — S-33-TC-016 открывает именно `/app/seller/reports`, сохраняет проверку неизменности URL, видимого отказа и отсутствия вызовов `/api/reports/*`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — артефакт этого атома.

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — код завершения 0.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/apps/seller/SellerApp.test.tsx` — `2 passed`, код завершения 0.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/seller-reports.spec.ts --grep 'seller staff without products access cannot open the direct reports route' --list` — один изменённый сценарий обнаружен и скомпилирован, код завершения 0.
- НЕ ЗАПУЩЕН ДО КОНЦА из-за ограничений среды: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/seller-reports.spec.ts --grep 'seller staff without products access cannot open the direct reports route'` — Playwright не начал сценарий: его API webServer не смог привязаться к `127.0.0.1:18000` (`operation not permitted`).
- НЕ ПРОВЕРЕНА СБОРКА: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && docker build -f frontend/Dockerfile.seller.prod -t wms-seller-reports-route-check .` — Docker socket недоступен (`permission denied while trying to connect to the docker API`), образ не создан.
- КРАСНЫЙ, вне разрешённых файлов атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` — новые нарушения в `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Они существовали до этой доработки и не относятся к двум разрешённым файлам; baseline не менялась.
- ЗЕЛЁНЫЙ: `git diff --check -- frontend/Dockerfile.seller.prod frontend/tests-e2e/seller-reports.spec.ts` — ошибок пробелов нет.
- Полный `npm run test:e2e`, полный backend `pytest`, `ruff check .` и `mypy .` не запускались: они запрещены границами атомарной проверки.

## Не реализовано

- Ни один пункт атома не оставлен нереализованным в коде: basename production-сборки и канонический маршрут e2e-сценария исправлены буквально.
- Доказательство через запущенный браузер и самостоятельный Docker-образ не получено только из-за ограничений среды на сетевой bind и Docker socket; это не исправляется в разрешённых файлах атома.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
