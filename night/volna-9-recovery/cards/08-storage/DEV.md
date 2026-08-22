# 08-storage · screen-dev rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

Экран S-11 теперь допускает только пользователя с правом `inventory`, а отдельное право
`cells` больше не открывает «Хранение». После запуска месячного расчёта экран опрашивает
`/operations/background-jobs/{id}` до статуса `done` и лишь затем перечитывает сводку;
`failed` и тайм-аут сохраняют последний успешный расчёт и показывают предусмотренную
контрактом ошибку. Вызовы `TextCell`, `ProductCell`, `StatusChip` и MUI-полей приведены к
фактическому API текущего UI-kit. Источники истории понимают как публичные значения API,
так и внутренние алиасы `wb` и `container_override`.

Playwright-проверка формирования теперь утверждает тело запроса с выбранными годом,
месяцем и складом, переход фоновой задачи `running` → `done` и загрузку изменившейся
сводки. Восстановлен буквальный `S-11-TC-008`: чистый черновик фиксируется и открывает
A4-предпросмотр с селлером, SKU и итогом. Добавлена проверка, что право `cells` без
`inventory` приводит на штатный экран «Нет доступа».

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend` — зелёный.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend` — зелёный: 20 файлов, 141 тест.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage` — красный только на существующих нарушениях вне файлов атома: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для `frontend/src/App.tsx` результат улучшен с 3492 до 3491 строки; новых нарушений S-11 нет. Базовая линия не обновлялась.
- `npx playwright test tests-e2e/storage.spec.ts --list` — зелёный: файл компилируется, найдено 17 тестов.
- `npx playwright test tests-e2e/storage.spec.ts --reporter=line` — инфраструктурно красный до запуска тестов: песочница запретила Playwright открыть локальный API-порт `127.0.0.1:18000` (`operation not permitted`), поэтому web-server завершился до старта браузерных сценариев.
- `git diff --check` — зелёный.

## Не реализовано

- Настройка тарифа буквально не реализована: в опубликованном API этой рабочей копии нет
  маршрута записи `BillingTariffVersion`. По обязательной границе `ARCH-CROSS.md` тарифом
  владеет финансовое ядро карточки 09; экран не создаёт второй контур и не изображает
  успешное сохранение локальным состоянием.
- Полный Playwright-прогон нельзя подтвердить в этой песочнице из-за запрета локального
  bind. Компиляция тестового файла подтверждена, но его 17 сценариев должны быть повторно
  запущены в CI или окружении, где разрешены локальные web-server порты.
- `S-11-TC-016`, `S-11-TC-018` и `S-11-TC-019` проверяют соответственно приоритет
  применённого события габаритов, целостность восстановленного остатка и идемпотентность
  финансовой фиксации. Это backend-конкурентные сценарии, которые нельзя доказать
  мокированным экранным Playwright без ложноположительного результата; в атоме
  `screen-dev` они не добавлялись.
- Сохранить изменения коммитом не удалось: Git не может создать
  `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за
  ограничений файловой песочницы (`Operation not permitted`). Изменения остаются только в
  постоянной рабочей копии и ещё не восстановимы по новому commit SHA.

## Находки

Секреты, ключи, токены, `.env`, персональные данные и кабинеты учётных данных не
открывались и не использовались.
