# 09-billing · screen-dev · атом 5

Роль: `screen-dev`. Реализован только атом «Сократить подпись повторного формирования счёта» из `FEATURES.md` и относящаяся к нему находка R-32 из `DESIGN-REVIEW.md`.

Когда администратор выбирает селлера без действующих причин блокировки, пояснение «Причины устранены — повторите формирование» остаётся отдельным текстом панели, а `PrimaryAction` теперь имеет короткую подпись «Повторить формирование». Алгоритм запроса и отображение результата формирования не менялись.

В `billing-invoices.spec.ts` добавлен пользовательский сценарий `S-31-TC-006`: администратор выбирает селлера, видит отдельное пояснение и короткую подпись кнопки, запускает повторное формирование и после прежнего POST видит выставленный счёт в таблице. Тест отдельно подтверждает, что длинная фраза больше не является доступным именем кнопки и что запрос формирования отправлен один раз.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Гейты

- **Красный, существующий долг ветки** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` выполнена дважды, в том числе после финальной правки; код возврата 2. Финальный запуск повторил прежние ошибки типизации условного `DataTable`, старого `alignItems` в строках проблем, MUI-пропсов и `testId` у `DangerAction` в `FfBillingScreen.tsx`, а также прежние ошибки в `FfSettingsScreen.tsx`, `SellersScreen.tsx` и `PeriodPicker.tsx`. Добавленный в первой итерации `alignItems` у новой панели дал отдельную ошибку и был удалён до финального запуска; в финальном выводе этой новой ошибки больше нет.
- **Красный, существующий храповик ветки** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` выполнена дважды, в том числе после финальной правки; код возврата 1. Повторены четыре ранее зафиксированные записи: `WbProductPickerDialog.tsx` `0 → 646`, `FfSettingsScreen.tsx` `701 → 795`, `FfFbsSupplyWorkspace.tsx` `2493 → 2498`, `SellerInboundDraftScreen.tsx` `1111 → 1169`; `App.tsx` отмечен как улучшившийся `3492 → 3491`. `FfBillingScreen.tsx` не появился в списке новых отступлений, базовая линия не обновлялась.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_temp_dir=$(mktemp -d /private/tmp/wms-billing-unit.XXXXXX) && TMPDIR="$task_temp_dir" npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts --pool=threads --maxWorkers=1 --minWorkers=1` выполнена дважды, в том числе после финальной правки: 1 файл, 4 теста пройдены.
- **Красный по среде** — точная атомарная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_temp_dir=$(mktemp -d /private/tmp/wms-billing-e2e.XXXXXX) && TMPDIR="$task_temp_dir" npx playwright test tests-e2e/billing-invoices.spec.ts --grep "billing invoice retry uses a short action label and keeps the visible formation result"`, код возврата 1. Playwright создал тестовую схему, но локальный API не смог привязать `127.0.0.1:18000`: `operation not permitted`; браузерный кейс не стартовал. Конфигурация и порты ради обхода не менялись.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_temp_dir=$(mktemp -d /private/tmp/wms-billing-e2e.XXXXXX) && TMPDIR="$task_temp_dir" npx playwright test tests-e2e/billing-invoices.spec.ts --grep "billing invoice retry uses a short action label and keeps the visible formation result" --list` выполнена дважды, в том числе после финальной правки: найден ровно 1 кейс атома в 1 файле.
- **Зелёный** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check`: замечаний нет.
- **Красный по правам среды** — точная команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git add -- frontend/src/screens/ff/FfBillingScreen.tsx frontend/tests-e2e/billing-invoices.spec.ts night/volna-9-recovery/cards/09-billing/DEV.md && git diff --cached --name-status && git diff --cached --check && git commit -m "fix(billing): shorten invoice retry action"`, код возврата 128. Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock`: `Operation not permitted`. Ничего не попало в индекс; проверенного commit SHA нет. Чужое изменение `night/volna-9-recovery/JOURNAL.md` в команду не включалось.

Полный backend `pytest`, `pytest -q`, `ruff check .` и `mypy .` не запускались в соответствии с запретом атомарной проверки. Полный frontend E2E-регресс также не запускался.

## Не реализовано

Пунктов контракта атома 5, которые не легли буквально в код, нет. Живой Playwright-прогон не выполнен только из-за запрета среды на локальный порт; он не подменён правкой тестовой конфигурации.

Изменения локально реализованы и артефакт записан, но среда не позволила сохранить их в Git. До внешнего коммита результат остаётся уязвимым как незакоммиченный diff.

Находка R-30 про безопасное отображение неизвестных кодов относится к следующему атому 6 и намеренно не затрагивалась. Находки в `FfSettingsScreen.tsx` и сетках таблиц относятся к предшествующим атомам и также не входят в границы атома 5.

## Находки

`FfBillingScreen.tsx` и маршрут `/app/ff/billing` отсутствуют в `frontend/screens.registry.json`; существующий идентификатор `S-31` в реестре принадлежит другому экрану, хотя биллинговые тесты размечены `S-31-TC-*`. Реестр не входит в разрешённые файлы атома, поэтому не изменялся.

Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой кабинет Wildberries и боевой прод `194.87.96.144` не открывались и не затрагивались. Новых находок по данным, утечкам или персональным данным в границах атома нет.
