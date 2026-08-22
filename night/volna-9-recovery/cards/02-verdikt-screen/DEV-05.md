# DEV · 02-verdikt-screen · переделка атома 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

Рабочее место уже читало готовность строки и доступность действия только из
серверного `metadata.verdict.delivery_allowed`. В переделке сохранено это
поведение и убрано новое превышение храповика размера целевого экрана без
изменения разметки или интерфейса.

Тестовый ответ workspace теперь считает серверный `progress.metadata_ready`
по тому же `verdict.delivery_allowed`, а сценарии S-03-TC-004, S-03-TC-005 и
S-03-TC-007 дополнительно проверяют, что `pending`, `required` и один
отклонённый заказ не сосуществуют с оптимистичным полным прогрессом готовности.
S-03-TC-007 по-прежнему проверяет видимую русскую причину, отсутствие зелёной
галочки для заблокированного заказа и `disabledReason` с номером заказа.

Обе находки `REVIEW.md` уже исправлены в зависимом серверном слое текущего
`HEAD`: реальный API сохраняет `metadata.verdict`, а свежий пустой или ошибочный
ответ WB сбрасывает прежний зелёный вердикт. Их регрессии повторно проверены.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.
- `npm run test:unit` из `frontend/` — зелёный: 20 файлов, 149 тестов прошли.
- `python3 scripts/ui/ui_guard.py` из корня — общий гейт красный только на
  соседних файлах `frontend/src/components/WbProductPickerDialog.tsx` и
  `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Целевой
  `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` больше не нарушает
  храповик и улучшил счётчики: `экран-монолит 2493 → 2492`, `своя-кнопка 37 → 36`.
  Базовая линия не обновлялась.
- Playwright S-03-TC-004, S-03-TC-005 и S-03-TC-007 — исполнение заблокировано
  до браузерного шага: webServer не может занять `127.0.0.1:18000`, среда
  возвращает `[Errno 1] operation not permitted`. `playwright --list` зелёный и
  обнаруживает все три целевых теста.
- Серверные регрессии находок ревью — зелёные: 4 теста прошли, 6 отфильтрованы.
- `git diff --check` — зелёный.

## Не реализовано

- Буквально не выполнен живой прогон трёх Playwright-сценариев: запуск
  останавливает запрет среды на локальный HTTP-порт до открытия браузера.
- Общий `ui_guard.py` нельзя сделать зелёным в границах атома: два оставшихся
  нарушения находятся в соседних файлах, которые роль `screen-dev` и контракт
  запрещают менять.
- Результат локально реализован, но не сохранён Git-коммитом: песочница не даёт
  создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`
  (`Operation not permitted`). Оркестратору с доступом на запись к общему
  git-dir нужно закоммитить три файла из секции «Изменённые файлы».

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и
  production `194.87.96.144` не читались и не затрагивались.
