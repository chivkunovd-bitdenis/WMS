## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

В верхней части отчёта московские границы периода теперь уходят в API с явным `+03:00`, а декабрьский текущий месяц заканчивается исключающей границей `1 января` следующего года. Объекты `warnings` из backend переводятся в текст двух `WarningNotice`, неполная transfer-пара получает общий `ErrorNotice`, `StatusChip` «Ошибка» и тире для отсутствующей стороны. Повтор после независимого сбоя сводки запрашивает только overview: уже загруженные строки, группировка и страница не очищаются и не запрашиваются повторно.

В FF Playwright-spec добавлены сценарии атомарной загрузки со скелетами, синхронного обновления показателей и графика после смены периода, пустого периода, отсутствующей базы сравнения, объектных WB/legacy-предупреждений, независимого retry сводки, проблемной transfer-строки и декабрьской границы года. Существующий `/frontend/tests-e2e/seller-reports.spec.ts` уже проверяет отсутствие селлерского фильтра и технического предупреждения, поэтому файл не менялся.

## Гейты

- **КРАСНЫЙ вне разрешённых файлов:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json`. После устранения ошибок в `FfReportsPage.tsx` остались только три прежние TypeScript-ошибки в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx` на строках 39, 84 и 91: несовместимые с текущими MUI-типами props `alignItems`, `fontWeight` и `flexWrap`. Этот файл не входит в разрешённые файлы атома и прямо не назван ревьюером для правки.
- **КРАСНЫЙ вне разрешённых файлов:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py`. Храповик сообщает новые нарушения только в `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; по `FfReportsPage.tsx` он отдельно сообщает улучшение «своя-кнопка 1 → 0» и «своя-таблица 1 → 0». Базовая линия не менялась.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit` — 19 файлов, 138 тестов пройдены.
- **КРАСНЫЙ по ограничению песочницы:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts --reporter=line` — webServer не смог привязаться к `127.0.0.1:18000`, ошибка ОС `operation not permitted`; тестовые действия не начались.
- **ЗЕЛЁНЫЙ (разбор целевых тестов):** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts --list` — Playwright успешно разобрал 5 тестов в 2 разрешённых spec-файлах.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx eslint src/screens/ff/FfReportsPage.tsx tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts`.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && git diff --check`.

Перед проверками зависимости восстановлены без сети командой `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm ci --offline`: 285 пакетов установлены из локального кэша, аудит не нашёл уязвимостей.

## Не реализовано

- Находка review №1 не исправлена: фильтрация служебных складов должна быть сделана в `/frontend/src/App.tsx` и `/frontend/src/apps/seller/SellerApp.tsx`, но оба файла находятся вне трёх файлов текущего атома и вне разрешённой роли `screen-dev`. Сам экран по-прежнему может скрыть фильтр единственного склада только при условии, что родитель передал уже отфильтрованный список операционных складов.
- Находки review №4, 6, 9 и 10 относятся к `/backend/app/services/reporting_service.py`; backend не изменялся. В текущей рабочей копии в сервисе уже видны отдельные ремонты календарных нулевых дней, входящей WB-свежести, целостности transfer-типов и человекопонятных названий операций, но роль `screen-dev` не имеет права объявлять их проверенными этим атомом.
- Буквально подтвердить браузером целевые сценарии не удалось из-за системного запрета на локальный порт webServer. Spec-файлы синтаксически разобраны Playwright, но это не заменяет фактический прогон.
- Обязательные `tsc` и `ui_guard.py` нельзя сделать зелёными, не меняя файлы вне разрешённой границы. Эти внешние нарушения не маскировались обновлением baseline.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
