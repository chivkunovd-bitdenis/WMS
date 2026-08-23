# 08-storage · screen-dev · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

После успешного сохранения ставки S-11 больше не выставляет `tariff_configured` локально и безусловно. До ответа сервера он сохраняет только пересчитанные им строки, затем повторно загружает снимок открытого месяца. Поэтому для прошлого месяца, который новая ставка не покрывает, остаётся пустое состояние «Тариф хранения ещё не задан» и действие «Задать тариф». Для покрытого месяца сохраняются зафиксированные строки, а пересчитанный черновик заменяется только ответом сервера.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный, завершён с кодом `0`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — зелёный: `1 passed`, `6 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/scripts/ui/ui_guard.py` — красный из-за трёх чужих файлов вне S-11: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась; эти файлы не менялись в атоме.

## Не реализовано

Нет. Находка 2 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/REVIEW.md`, относящаяся к frontend-слою атома, исправлена. Находки 1 и 3 относятся соответственно к backend-валидации и реестру блокировок и в этот атом не входят.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных, production и живой кабинет Wildberries не открывались и не использовались.

## Сохранность

Реализация S-11 и unit-тесты уже находятся в commit `11637874ad8bea2ab6378280bcf6f343da2e0e7b`. Актуальный отчёт `DEV.md` записан в рабочей копии, но отдельный commit отчёта не создан: `git add` не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за `Operation not permitted`.
