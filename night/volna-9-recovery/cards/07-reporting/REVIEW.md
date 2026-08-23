# REVIEW · 07-reporting · повторный проход

Вердикт: CHANGES_REQUESTED.

ВЕРДИКТ: НАХОДКИ 2

## Находки

1. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/docs/blockers/S-33.md:10`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx:3077` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/deps.py:297` — предыдущая находка 5 закрыта не полностью: новый шестипольный реестр объявляет блокировку сотрудника ФФ без `inventory`, меню и маршрут действительно требуют только `inventory`, но сервер разрешает все три отчётные ручки также при одном `cells=true`. При профиле `cells=true, inventory=false` оператор видит «Нет доступа» и не видит пункт «Отчёты», хотя прямой вызов `/reports/overview`, `/reports/inventory` или CSV проходит. Добавленный сценарий `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts:51` выставляет оба права в `false` и поэтому оставляет расхождение зелёным. Цена: самодельный запрет в UI расходится с серверной границей доступа, а защищённые складские данные доступны через API при видимом отказе; строка «Разошлись слои: Нет» в реестре недостоверна.

2. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts:55` — ремонт предыдущей находки 5 не проверяет заявленный прямой маршрут селлера: контракт и реестр называют `/app/seller/reports`, тест подменяет его dev-only адресом `/seller/reports`, а production-сборка из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/Dockerfile.seller.prod:9` монтирует `SellerApp` с basename `/` и фактическим маршрутом `/reports` на `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerApp.tsx:474`. Если сотрудник без `can_products` открывает сохранённую контрактную ссылку `/app/seller/reports` на самостоятельном кабинете селлера, wildcard на строке 529 перенаправляет его на первый доступный раздел вместо обещанного состояния «Нет доступа»; новый тест остаётся зелёным, потому что попадает в другой, существующий маршрут. Цена: обязательная блокировка прямой ссылки не доказана и не работает на URL из `S-33`, поэтому карточку нельзя принимать по заявленному маршруту.

## Проверено и нормально

- Предыдущие находки 1–4 закрыты: writer передаёт обязательный `warehouse_id`; адресный backend-набор прошёл `18 passed`, включая CSV неполной/полной transfer-пары, каталог складов и исходный отчёт движений; `ruff` и `mypy` зелёные.
- Отмена старой страницы теперь снимает отдельный `tableLoading`, не давая её `finally` затронуть новый контроллер; TypeScript, три frontend unit-теста и компиляция пяти адресных Playwright-сценариев прошли. Живой Playwright не стартовал только из-за запрета среды на bind `127.0.0.1:18000`.
- `is_operational` добавлен в list/create/rename ответы складов без удаления прежних полей; оба клиента фильтруют только по авторитетному признаку, переименование служебного склада больше не влияет на срез.
- Повторно сверены пять пунктов замороженного предыдущего вердикта, весь ремонтный diff после него, назначенные `S-33`-кейсы, карта волны, перекрёстное архитектурное решение и границы карточки; стадийные артефакты ролей и инфраструктура ночного конвейера выходом за границы не считались.
