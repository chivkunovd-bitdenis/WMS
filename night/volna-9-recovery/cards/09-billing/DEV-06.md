# 09-billing · screen-dev · атом 6

Роль: `screen-dev`. Реализован только атом «Не выводить неизвестные коды биллинга в интерфейс» из `FEATURES.md` и относящаяся к нему находка R-30 из `DESIGN-REVIEW.md`.

Неизвестные `service_code` и `unit` теперь отображаются безопасным знаком «—» в строках начислений, режиме «По исполнителям», строках открытого счёта и печатном представлении того же счёта. Над журналом начислений и внутри диалога счёта появляется отдельный `ErrorNotice` с понятным оператору описанием ошибки; исходные технические значения в сообщения не подставляются.

E2E-заглушки возвращают неизвестные услугу и единицу отдельно для начисления и строки счёта. Сценарии проверяют обычный режим начислений, режим «По исполнителям», открытый счёт и печатный вид: в каждом месте видны «—», а исходные строки API отсутствуют в интерфейсе.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Гейты

- **Красный, существующий долг ветки** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json`, код возврата 2. В `FfBillingScreen.tsx` воспроизведены прежние ошибки типизации условного `DataTable`, старых MUI-пропсов и `testId` у `DangerAction`; также воспроизведены ранее зафиксированные ошибки в `FfSettingsScreen.tsx`, `SellersScreen.tsx` и `PeriodPicker.tsx`. На добавленных безопасных подстановках, вычислении признака неизвестных кодов и `ErrorNotice` отдельных новых ошибок TypeScript нет.
- **Красный, существующий храповик ветки** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py`, код возврата 1. Повторены четыре ранее зафиксированные записи: `WbProductPickerDialog.tsx` `0 → 646`, `FfSettingsScreen.tsx` `701 → 795`, `FfFbsSupplyWorkspace.tsx` `2493 → 2498`, `SellerInboundDraftScreen.tsx` `1111 → 1169`; `App.tsx` отмечен как улучшившийся `3492 → 3491`. `FfBillingScreen.tsx` не появился в списке новых отступлений, базовая линия не обновлялась.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_temp_dir=$(mktemp -d /private/tmp/wms-billing-unit.XXXXXX) && TMPDIR="$task_temp_dir" npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts --pool=threads --maxWorkers=1 --minWorkers=1`: 1 файл, 4 теста пройдены.
- **Зелёный** — точная команда обнаружения атомарных E2E и связанных регрессий `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_temp_dir=$(mktemp -d /private/tmp/wms-billing-e2e.XXXXXX) && TMPDIR="$task_temp_dir" npx playwright test tests-e2e/billing-ledger.spec.ts tests-e2e/billing-invoices.spec.ts --grep "billing (ledger (hides unknown service and unit codes in both modes|uses the canonical storage service code)|invoice (hides unknown service and unit codes|opens, reveals documents and starts print))" --list`: найдены ровно 4 кейса в 2 файлах — два сценария атома и две связанные регрессии канонического кода хранения и печати счёта.
- **Красный по среде** — та же атомарная Playwright-команда без `--list`, код возврата 1. Локальный API дошёл до запуска приложения, но не смог привязать `127.0.0.1:18000`: `operation not permitted`; браузерные шаги не стартовали. Конфигурация, порты и тестовые данные ради обхода не менялись.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check`: замечаний нет.
- **Красный по правам среды** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git add -- frontend/src/screens/ff/FfBillingScreen.tsx frontend/tests-e2e/billing-ledger.spec.ts frontend/tests-e2e/billing-invoices.spec.ts night/volna-9-recovery/cards/09-billing/DEV.md && git diff --cached --name-status && git diff --cached --check && git commit -m "fix(billing): hide unknown billing codes"`, код возврата 128. Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock`: `Operation not permitted`. Ничего не попало в индекс; проверенного commit SHA нет. Чужое изменение `night/volna-9-recovery/JOURNAL.md` в команду не включалось.

Полный backend `pytest`, `pytest -q`, `ruff check .` и `mypy .` не запускались в соответствии с запретом атомарной проверки. Полный frontend E2E-регресс также не запускался.

## Не реализовано

Пунктов контракта атома 6, которые не легли буквально в код, нет. Не выполнен только живой Playwright-прогон двух новых сценариев и двух связанных регрессий из-за запрета среды на локальный порт; это не подменено правкой конфигурации.

Обязательные общие `tsc` и `ui_guard.py` остаются красными на существующих отклонениях ветки, перечисленных выше. Исправление соседних ошибок и монолитов не входит в разрешённые файлы и границы атома 6.

Изменения локально реализованы и артефакт записан, но среда не позволила сохранить их в Git. До внешнего коммита результат остаётся уязвимым как незакоммиченный diff.

## Находки

`FfBillingScreen.tsx` и маршрут `/app/ff/billing` отсутствуют в `frontend/screens.registry.json`; существующий идентификатор `S-31` в реестре принадлежит другому экрану, хотя биллинговые тесты уже размечены `S-31-TC-*`. Реестр не входит в разрешённые файлы атома, поэтому не изменялся.

Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой кабинет Wildberries и боевой прод `194.87.96.144` не читались и не затрагивались. Новых находок по данным, утечкам или персональным данным в границах атома нет.
