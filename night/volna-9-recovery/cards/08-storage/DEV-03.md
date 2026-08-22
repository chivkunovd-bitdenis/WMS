# 08-storage · screen-dev · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

В диалоге тарифа обе даты ограничены сегодняшним московским днём, а прошедшая дата дополнительно блокируется логикой формы. После единственного `POST /operations/storage/tariffs` экран запускает существующий пересчёт выбранного месяца и только после завершения обновляет видимый расчёт. Тело одного POST содержит `seller_exception`, когда индивидуальная ставка раскрыта и заполнена.

`S-11-TC-002` переведён с подменённых storage-ответов на живой API: сценарий регистрирует администратора, создаёт операционный склад и селлера, подготавливает черновик, проверяет московскую дату по умолчанию, запрет прошедшей даты, единственный объединённый POST и следующий за ним rebuild.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json` — exit 0.
- Красный вне файлов атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` — exit 1. Храповик сообщил только уже присутствующие изменения в `src/components/WbProductPickerDialog.tsx` (`0 → 646`), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (`2493 → 2498`) и `src/screens/v2/SellerInboundDraftScreen.tsx` (`1111 → 1169`). `FfStoragePage.tsx` в новых нарушениях отсутствует; baseline не обновлялся.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/utils/moscowDate.test.ts` — 1 файл, 4 теста пройдены.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx eslint src/screens/ff/FfStoragePage.tsx tests-e2e/storage.spec.ts` — exit 0.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep "S-11-TC-002" --list` — найден ровно один назначенный тест, файл компилируется.
- Красный из-за ограничения среды до исполнения кейса: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep "S-11-TC-002"` — Playwright-managed backend не смог открыть `127.0.0.1:18000`, ошибка `[Errno 1] operation not permitted`; тестовые шаги не начались.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check` — ошибок пробелов нет.
- Красный из-за ограничения среды: `git add frontend/src/screens/ff/FfStoragePage.tsx frontend/tests-e2e/storage.spec.ts night/volna-9-recovery/cards/08-storage/DEV.md && git commit -m "fix(storage): repair tariff dialog retry flow"` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`, ошибка `Operation not permitted`. Коммит не создан.

## Не реализовано

Пункты контракта этого экранного атома реализованы буквально. Живой браузерный прогон `S-11-TC-002` не подтверждён: sandbox запретил локальному тестовому серверу открыть порт 18000 до запуска сценария. Поэтому этот артефакт не утверждает `PRODUCT_BROWSER_APPROVED`.

Изменения локально реализованы, но не сохранены в новом Git-коммите: sandbox запрещает запись в служебный каталог текущего зарегистрированного worktree. Для завершения сохранности оркестратору нужно закоммитить три файла из секции «Изменённые файлы» в этой же ветке.

Backend-находки ревью о tenant/операционном складе и положительной ставке не менялись ролью `screen-dev`: они вне файла и слоя атома. В текущей рабочей копии соответствующие серверные проверки уже присутствуют в `create_storage_tariff()` и Pydantic-модели запроса.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и production не открывались и не использовались. Боевой адрес `194.87.96.144` не затрагивался.
