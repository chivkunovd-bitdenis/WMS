# Screen-dev · 07-reporting · атом 7 · rework

Исправлена находка №5 из повторного `REVIEW.md`: ограничение доступа к S-33
зафиксировано отдельной шестипольной записью, а оба ролевых отказа получили
адресные браузерные сценарии. Остальные четыре находки относятся к другим атомам
и файлам, поэтому в этом проходе не затрагивались.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts` — добавлен `S-33-TC-015`: сотрудник ФФ с правом приёмки, но без `inventory` и `cells`, открывает `/app/ff/reports` напрямую, видит «Нет доступа», не видит меню и блоки отчёта; запросы `/api/reports/*` не уходят.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts` — добавлен `S-33-TC-016`: сотрудник селлера с документами, но без `can_products`, открывает прямой маршрут отчёта, видит адресный отказ и не получает показатели, график или таблицу; запросы `/api/reports/*` не уходят.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/docs/blockers/S-33.md` — добавлена отдельная запись «Отчёт без права доступа» со всеми шестью обязательными полями: предмет блокировки, условие, место проверки, видимое состояние, разблокировка и бизнес-причина.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт текущего атома.

## Гейты

- **ЗЕЛЁНЫЙ:** рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`; команда `npx tsc --noEmit -p tsconfig.app.json` — код завершения 0.
- **КРАСНЫЙ ИЗ-ЗА НАКОПЛЕННОГО СОСТОЯНИЯ ВЕТКИ:** рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`; команда `python3 scripts/ui/ui_guard.py` — код завершения 1. Новых нарушений в файлах атома нет; сторож повторил прежние превышения baseline в `frontend/src/App.tsx` (`экран-монолит 3492 → 3511`), `frontend/src/components/WbProductPickerDialog.tsx` (`0 → 646`), `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` (`2493 → 2498`) и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx` (`1111 → 1169`). Для `FfReportsPage.tsx` сторож, наоборот, отметил улучшение по собственной кнопке и таблице. Baseline флагом `--update` не менялась.
- **ЗЕЛЁНЫЙ:** рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`; команда `npm run test:unit -- src/screens/ff/FfReportsPage.test.tsx src/apps/seller/SellerApp.test.tsx` — 2 файла, 3 теста, `3 passed`, код завершения 0.
- **КРАСНЫЙ ИЗ-ЗА ОГРАНИЧЕНИЯ СРЕДЫ:** рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`; команда `npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts --grep "staff without (inventory|products) access cannot open the direct reports route"` — Playwright не дошёл до браузерных сценариев, потому что тестовый API не смог открыть `127.0.0.1:18000` (`Errno 1: operation not permitted`), код завершения 1.
- **ЗЕЛЁНЫЙ, ОБНАРУЖЕНИЕ И КОМПИЛЯЦИЯ СЦЕНАРИЕВ:** рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`; команда `npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts --grep "staff without (inventory|products) access cannot open the direct reports route" --list` — найдены ровно 2 теста в 2 файлах, код завершения 0.
- **ЗЕЛЁНЫЙ:** рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`; команда `npx eslint tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts` — код завершения 0.
- **ЗЕЛЁНЫЙ:** рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`; команда `python3 -c "from pathlib import Path; text=Path('docs/blockers/S-33.md').read_text(); section=text.split('### Отчёт без права доступа',1)[1].split('### Выгрузка CSV',1)[0]; fields=['Что блокируется','Каким условием','Где живёт проверка','Что видит оператор','Как разблокировать','Зачем бизнесово']; missing=[field for field in fields if f'**{field}:**' not in section]; assert not missing, missing; print('S-33 access blocker: 6/6 fields present')"` — `6/6 fields present`, код завершения 0.
- **ЗЕЛЁНЫЙ:** рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`; команда `git diff --check` — ошибок формата diff нет, код завершения 0.
- **ЗЕЛЁНЫЙ:** в именованной ветке `night/volna-9-recovery/lane-1/07-reporting` команда `git commit -m "test(reports): cover denied report routes"` создала отдельный локальный коммит только из четырёх файлов атома; чужой `night/volna-9-recovery/JOURNAL.md` в него не вошёл.
- **КРАСНЫЙ ИЗ-ЗА ОГРАНИЧЕНИЯ СЕТИ:** команда `git push -u origin HEAD` не смогла разрешить имя `github.com` (`Could not resolve host`), код завершения 128. Ветка сохранена локально, но в remote не опубликована.
- Полный backend `pytest`, `ruff check .`, `mypy .`, полный Playwright и соседние атомы не запускались: атомарная проверка прямо ограничена двумя адресными сценариями и относящимися к экрану unit-тестами.

## Не реализовано

- Живое прохождение `S-33-TC-015` и `S-33-TC-016` в этой среде не подтверждено: локальный API нельзя привязать к порту из-за sandbox-ограничения. Оба сценария обнаруживаются и компилируются Playwright, но это не заменяет браузерный проход.
- Реестр называет маршрут селлера `/app/seller/reports`, а текущая локальная Playwright-сборка отдельного `SellerApp` использует basename `/seller`; поэтому `S-33-TC-016` открывает эквивалентный прямой путь `/seller/reports` через штатный `sellerPath('/reports')`. Буквальный URL `/app/seller/reports` этой конфигурацией не обслуживается отдельным seller-приложением.
- Локальная ветка не опубликована в `origin` из-за отсутствия DNS-доступа к GitHub. Деплой и production не выполнялись.

## Находки

- Новых находок по данным, персональным данным или видимому поведению за границами атома нет.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
