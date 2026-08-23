# 08-storage · screen-dev · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`

У поля «Месяц» добавлено видимое объяснение «Будущие месяцы недоступны: расчёт ещё не начался». Атрибут `max` сохранён. Новый сценарий открывает S-11 как сотрудник ФФ, проверяет этот текст и `max="2026-08"` при зафиксированной московской дате.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — 1 файл, 6 тестов.
- Красный вне атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py`. Сторож сообщил три новых отступления в чужих экранах: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для S-11 новых отступлений нет; базовую линию не обновлял.
- Не запущен до результата: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep "staff sees why future storage months are unavailable"`. Playwright начал запуск, но его API web server не смог привязать `127.0.0.1:18000`: `operation not permitted`.
- Не сохранено коммитом: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add frontend/src/screens/ff/FfStoragePage.tsx frontend/tests-e2e/storage.spec.ts night/volna-9-recovery/cards/08-storage/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`: `Operation not permitted`. Commit SHA отсутствует.

## Не реализовано

Все пункты первого атома из `FEATURES.md` реализованы буквально. Находки о ширинах истории габаритов и печатной таблице намеренно не трогались: это второй и третий атомы, запрещённые текущим заданием.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не использовались. Ограничение среды не позволило запустить локальный API Playwright на порту 18000.
