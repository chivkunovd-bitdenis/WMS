# REVIEW · 07-reporting · повторный проход

Вердикт: CHANGES_REQUESTED.

ВЕРДИКТ: НАХОДКИ 2

## Находки

1. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/Dockerfile.seller.prod:9` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/deploy/Caddyfile.seller.local:6` — ремонт канонического адреса задаёт `BrowserRouter` базовый путь `/app/seller`, но публикация самостоятельного кабинета по-прежнему объявлена и обслуживается от корня. При открытии штатного адреса контейнера `web_seller` (`/`) или сохранённой старой ссылки вроде `/documents` Caddy отдаёт `seller/index.html`, после чего React Router не рендерит ничего: URL не начинается с нового базового пути. Цена: ради одной ссылки на отчёт ломается обратная совместимость всего самостоятельного кабинета селлера — вход, документы, товары и настройки становятся пустым экраном, пока пользователь вручную не добавит `/app/seller`.

2. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts:53`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/playwright.config.ts:58` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/vite.config.ts:21` — новый e2e-сценарий не проверяет изменённую production-сборку: стандартный Playwright запускает общий Vite, а тот отдаёт seller-bundle только для `/seller/*`; переход на `/app/seller/reports` получает основной FF-bundle. После входа селлера его токен хранится в seller-области, поэтому этот bundle не способен показать ожидаемый `seller-access-denied` на строке 57; сценарий либо падает на этой проверке, либо проверяет чужую оболочку, но `VITE_SELLER_ROUTER_BASENAME` из Dockerfile в нём не участвует. Цена: единственный тест ремонта маршрута не доказывает его и не ловит регрессию корня; в dev-отчёте был выполнен только `--list`, живой сценарий не запускался.

## Проверено и нормально

- Первая замороженная находка закрыта: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/deps.py:297` принимает у сотрудника ФФ только `inventory`; адресный `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py` прошёл полностью — `5 passed`, включая `403` для `cells=true, inventory=false` и `200` для допустимых ролей.
- FF browser-кейс теперь действительно задаёт `cells=true, inventory=false`, проверяет видимый отказ, отсутствие меню/блоков отчёта и отсутствие запросов `/api/reports/*`; оба изменённых spec-файла компилируются, Playwright обнаруживает восемь адресных сценариев.
- Frontend production build прошёл как со штатным окружением, так и с `VITE_SELLER_ROUTER_BASENAME=/app/seller`; три адресных unit-теста прошли. Локальный preview и живой Playwright не стартовали из-за запрета среды на bind `127.0.0.1`, а не из-за ошибки сборки.
- Сверены обе замороженные находки, весь продуктовый ремонтный diff после предыдущего `REVIEW.md`, назначенные кейсы S-33, `frontend/screens.registry.json`, карта волны и обязательный `ARCH-CROSS.md`. Новых записей данных, изменений формата API, внешних вызовов или новых бизнес-блокировок в ремонтном diff нет; стадийные артефакты ролей выходом за границы не считались.
