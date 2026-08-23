# DEV · 08-storage · screen-dev · атом 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx` — общая проверка даты начала вынесена в тестируемую функцию; обе даты тарифа продолжают сравниваться с сегодняшним днём по Москве, а поле индивидуальной ставки получило стабильный `data-testid` для отдельной проверки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.test.ts` — точечные unit-тесты: вчера запрещено, сегодня и будущая дата разрешены.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts` — `S-11-TC-002` проверяет московское `min` и значение «сегодня» в обоих полях, недоступность сохранения и отсутствие POST для вчерашней даты отдельно у общей ставки и исключения селлера, повторное разрешение сохранения на сегодняшней дате и успешную отправку будущей даты.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт текущего атома.

## Гейты

Точный обязательный TypeScript-гейт:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json
```

Результат: зелёный, exit 0, ошибок нет.

Точный обязательный UI-гейт:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py
```

Результат: красный, exit 1, только из-за уже существующих нарушений вне файлов и слоя атома:

```text
НОВОЕ НАРУШЕНИЕ  src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646
НОВОЕ НАРУШЕНИЕ  src/screens/v2/FfFbsSupplyWorkspace.tsx: экран-монолит 2493 → 2498
НОВОЕ НАРУШЕНИЕ  src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169
стало лучше  src/App.tsx: экран-монолит 3492 → 3491
```

`FfStoragePage.tsx` и новый тест в выводе нарушений отсутствуют. Baseline не обновлялся; несвязанные экраны не исправлялись, потому что роль `screen-dev` запрещает выходить за файлы атома.

Точный финальный unit-гейт экрана и относящейся к нему московской даты:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts src/utils/moscowDate.test.ts
```

Результат: зелёный — `2 passed` test files, `6 passed` tests.

Первая диагностическая попытка unit-гейта до исправления расширения тестового файла:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.tsx src/utils/moscowDate.test.ts
```

Результат: команда выполнила только `moscowDate.test.ts` (`4 passed`), потому что `vitest.config.ts` включает только `src/**/*.test.ts`. Тест экрана переименован в `.test.ts`, после чего финальный прогон выше выполнил оба файла.

Проверка обнаружения ровно назначенного браузерного кейса:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test storage.spec.ts --grep 'S-11-TC-002' --list
```

Результат: зелёный — найден ровно `1 test in 1 file`.

Точный атомарный браузерный прогон:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test storage.spec.ts --grep 'S-11-TC-002'
```

Результат: красный до старта браузерного сценария. Playwright поднял приложение до этапа открытия сокета, после чего песочница запретила локальному API привязаться к `127.0.0.1:18000`: `[Errno 1] ... operation not permitted`. Код кейса не исполнялся, продуктового падения тест не зафиксировал.

Предварительная попытка с путём относительно корня testDir:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep '^S-11-TC-002'
```

Результат: тот же запрет привязки `127.0.0.1:18000`; финальная команда выше приведена в правильном формате относительно `testDir`.

Проверка пробелов:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check -- frontend/src/screens/ff/FfStoragePage.tsx frontend/src/screens/ff/FfStoragePage.test.ts frontend/tests-e2e/storage.spec.ts
```

Результат: зелёный, exit 0.

Полные frontend/backend-регрессии, полный `pytest`, `ruff check .` и `mypy .` не запускались: для атома разрешены только назначенный кейс и относящиеся к нему точечные тесты.

## Не реализовано

- Живой браузерный проход `S-11-TC-002` не выполнен из-за запрета среды на локальный socket; требуется повторить точную команду в среде, где разрешён bind на loopback-порт.
- Находки 1, 3 и 4 из `REVIEW.md` закрывались предыдущими backend-атомами и в этом экранном шаге не менялись. Находка 5 про сквозной живой API учтена в существующем `S-11-TC-002`; соседние продуктовые задачи и атомы 5–6 не выполнялись.
- Несвязанные нарушения `ui_guard.py` не исправлялись и baseline не двигался: их файлы отсутствуют в разрешённом списке этого атома.

## Находки

- Новых находок по файлам атома нет.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production и живой кабинет Wildberries не читались и не использовались.

## Блокеры

- Полностью зелёный набор обязательных гейтов недостижим в этой рабочей копии: `ui_guard.py` падает на трёх несвязанных файлах, а Playwright не может открыть локальный порт из-за ограничений песочницы.
