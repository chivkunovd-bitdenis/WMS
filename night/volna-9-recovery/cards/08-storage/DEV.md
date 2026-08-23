# Фича 1

# DEV · 08-storage · backend-dev · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py` — доменная ошибка `tariff_amount_must_be_positive` сопоставлена с HTTP 422; в схемах основная и индивидуальная ставки остаются строго положительными.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py` — `create_storage_tariff()` теперь сам отклоняет нулевую и отрицательную основную или индивидуальную ставку до создания ORM-объектов; проверка обеих дат относительно сегодняшнего дня по Москве сохранена в одном доменном сервисе.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_tariff_api.py` — проверки расширены на обе части атомарного запроса, доказывают отсутствие версий тарифа после 422 и используют динамические московские даты вместо скоро устаревающих констант 2026 года.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — артефакт backend-dev по текущему атому.

## Что реализовано

- Эндпоинт `POST /operations/storage/tariffs`: основная ставка и необязательное исключение селлера принимаются только со строго положительной ставкой и датой не раньше текущего дня по МСК; отказ возвращает 422 до любой записи.
- Сервис `create_storage_tariff()`: дублирует инвариант положительной ставки на доменном слое, чтобы не-HTTP вызов не мог обойти схему запроса.

## Миграции

Нет.

## Тесты

- `test_tariff_amount_must_be_positive`: нуль и отрицательная ставка отклоняются отдельно для склада и исключения селлера; проверены HTTP 422, точный путь ошибочного поля и нулевое число созданных версий.
- `test_tariff_valid_from_cannot_be_in_the_past`: вчерашняя дата по Москве отклоняется отдельно для основной ставки и исключения; проверены HTTP 422, `tariff_valid_from_in_past` и отсутствие версий.
- `test_admin_creates_warehouse_tariff` и `test_admin_creates_tariff_with_seller_exception`: основная ставка с датой «сегодня» и атомарная пара с будущими датами создаются с HTTP 201.
- Относящиеся к ручке регрессии атомарности и ролевого доступа также остались зелёными.

## Гейты

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/api/storage.py app/services/storage_statement_service.py tests/test_storage_tariff_api.py
```

Результат: `All checks passed!`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/api/storage.py app/services/storage_statement_service.py
```

Результат: целевые модули проверены, но команда завершилась с кодом 1 из-за четырёх уже существующих ошибок в трёх импортируемых, но не затронутых атомом файлах: `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23,291`. В двух целевых модулях ошибок не выведено.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy --follow-imports=silent app/api/storage.py app/services/storage_statement_service.py
```

Результат: `Success: no issues found in 2 source files`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_tariff_api.py
```

Финальный результат: `11 passed in 11.00s`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check -- backend/app/api/storage.py backend/app/services/storage_statement_service.py backend/tests/test_storage_tariff_api.py
```

Результат: exit 0, ошибок пробелов нет.

`python3 scripts/ci/back_guard.py` не запускался: в этом rework-атоме новый роут не добавлялся. `python3 scripts/ci/check_migrations.py` не запускался: миграций нет.

Первая диагностическая попытка `./.venv/bin/pytest -q tests/test_storage_tariff_api.py` не запустила тесты, потому что в `backend/` нет `.venv`; целевой прогон затем успешно выполнен доступным `pytest`.

## Не реализовано

- Атомы 2–6 из `FEATURES.md` не выполнялись.
- Находки 1, 3 и 5 из `REVIEW.md` относятся к следующим backend/frontend-атомам и не менялись в этом шаге.
- Frontend, миграции, внешние API, production и живой кабинет Wildberries не затрагивались.

## Находки

Нет. Секреты, ключи, токены, `.env`, кабинеты учётных данных и production не читались и не использовались.

## Блокеры

Нет на уровне backend-реализации и целевых тестов.

# Фича 2

# DEV · 08-storage · backend-dev · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_tariff_api.py` — тест границ тарифа расширен на чужой и отсутствующий склад, чужого и отсутствующего селлера, служебный склад, пустую транзакцию после каждого отказа и успешную пару своего операционного склада с селлером.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт backend-dev по атому 2.

## Что реализовано

- Эндпоинт `POST /operations/storage/tariffs`: целевой API-тест доказывает отказ `404 warehouse_not_found` для чужого или отсутствующего склада, `404 seller_not_found` для чужого или отсутствующего селлера и `422 warehouse_not_operational` для собственного служебного склада; ни один отказ не создаёт финансовую строку.
- Сервис `create_storage_tariff()`: в текущем коде уже выполняет обе проверки до создания `BillingTariffVersion` — загружает склад и селлера только вместе с `tenant_id` администратора и отдельно требует `Warehouse.is_operational`; дополнительная правка сервиса не понадобилась.

## Миграции

Нет.

## Тесты

- Расширен `test_tariff_scope_must_belong_to_tenant_and_operational_warehouse`: он создаёт два tenant, собственные операционный и служебный склады, чужой склад, собственного и чужого селлеров.
- Пять парных запросов проверяют чужой и отсутствующий склад, служебный склад, чужого и отсутствующего селлера. После каждого отказа число `BillingTariffVersion` текущего tenant остаётся нулевым.
- Завершающий запрос с собственными операционным складом и селлером получает `201` и сохраняет ровно две версии: общую ставку склада и исключение селлера на том же складе.

## Гейты

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/services/storage_statement_service.py tests/test_storage_tariff_api.py
```

Результат: `All checks passed!`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy --follow-imports=silent app/services/storage_statement_service.py tests/test_storage_tariff_api.py
```

Результат: `Success: no issues found in 2 source files`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_tariff_api.py
```

Результат: `11 passed in 9.79s`.

Предварительно отдельно проверен изменённый сценарий:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_tariff_api.py::test_tariff_scope_must_belong_to_tenant_and_operational_warehouse
```

Результат последнего одиночного прогона: `1 passed in 1.23s`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check -- backend/tests/test_storage_tariff_api.py night/volna-9-recovery/cards/08-storage/DEV.md
```

Результат: exit 0, ошибок пробелов нет.

`python3 scripts/ci/back_guard.py` не запускался: атом не добавляет маршрут. `python3 scripts/ci/check_migrations.py` не запускался: миграций нет.

Попытка сохранить атом отдельным коммитом:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add -- backend/tests/test_storage_tariff_api.py night/volna-9-recovery/cards/08-storage/DEV.md && git commit -m "test(storage): cover tariff tenant scope"
```

Результат: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`: `Operation not permitted`. Файлы не попали в индекс и остаются только локальным diff рабочей копии; `night/volna-9-recovery/JOURNAL.md` не затрагивался и не включался.

## Не реализовано

- Атомы 3–6 из `FEATURES.md` не выполнялись.
- Находки 1, 2, 4 и 5 из `REVIEW.md` не относятся к файлам и границам атома 2 и не менялись.
- Frontend, пересчёт черновиков, модели, миграции, внешние API, production и живой кабинет Wildberries не затрагивались.
- В `storage_statement_service.py` не внесён искусственный diff: требуемая проверка tenant и `is_operational` уже присутствует в текущем HEAD и полностью покрыта расширенным тестом.

## Находки

Нет. Секреты, ключи, токены, `.env`, кабинеты учётных данных и production не читались и не использовались.

## Блокеры

На уровне backend-кода и целевых тестов блокеров нет. Сохранение отдельного commit заблокировано правами текущей среды на общий Git-каталог за пределами разрешённой рабочей копии; commit SHA не создан.

# Фича 3

# DEV · 08-storage · backend-dev · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py` — ответ `POST /operations/storage/tariffs` дополнен списком `recalculated_statements` с пересчитанными открытыми черновиками и новыми суммами.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py` — сохранение тарифа теперь после успешного `flush` пересчитывает затронутые черновики выбранного склада и пересекающегося периода в той же транзакции; зафиксированные statements исключены из выборки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_tariff_api.py` — сценарий смены тарифа проверяет ответ POST, повторную загрузку, границы склада/даты, нулевой черновик, неизменность fixed-документа и финансовой строки, а также отказ сохранения до пересчёта.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт backend-dev по атому 3.

## Что реализовано

- Эндпоинт `POST /operations/storage/tariffs`: после атомарной записи тарифа возвращает только затронутые открытые черновики в `recalculated_statements`, уже с действующими ставками и суммами; fixed-документы в ответ не попадают.
- Сервис `reprice_open_storage_drafts()`: выбирает draft-statements текущего tenant только по выбранному складу и периодам, пересекающим дату новой общей или индивидуальной ставки, и рассчитывает серверный preview без публикации финансовых строк.
- Сервис `create_storage_tariff()`: выполняет INSERT-проверку через `flush`, затем пересчёт и только после этого `commit`; конфликт INSERT делает rollback до запуска пересчёта, ошибка пересчёта откатывает новые версии тарифа.

## Миграции

Нет.

## Тесты

- Расширен `test_new_tariff_reprices_open_draft_on_reload`: успешный POST возвращает два открытых черновика выбранного склада с новой суммой и ставкой, включая нулевой расчёт.
- Тот же тест доказывает, что черновик другого склада, открытый черновик периода до даты действия и fixed-statement не пересчитываются.
- Контрольная `BillingLedgerEntry` fixed-документа сохраняет прежние `rate=1.00` и `amount=1.00`; для draft-документов новые ledger-строки не создаются.
- Повторная запись тарифа на конфликтующую дату получает 409, не создаёт вторую версию и не меняет доступный расчёт.

## Гейты

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/api/storage.py app/services/storage_statement_service.py tests/test_storage_tariff_api.py
```

Результат: `All checks passed!`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy --follow-imports=silent app/api/storage.py app/services/storage_statement_service.py tests/test_storage_tariff_api.py
```

Результат: `Success: no issues found in 3 source files`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_tariff_api.py::test_new_tariff_reprices_open_draft_on_reload
```

Финальный результат целевого сценария: `1 passed in 1.00s`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_tariff_api.py
```

Финальный результат назначенного файла: `11 passed in 10.47s`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check -- backend/app/api/storage.py backend/app/services/storage_statement_service.py backend/tests/test_storage_tariff_api.py night/volna-9-recovery/cards/08-storage/DEV.md
```

Результат: exit 0, ошибок пробелов нет.

`python3 scripts/ci/back_guard.py` не запускался: атом не добавляет новый маршрут, а расширяет ответ существующего `POST /operations/storage/tariffs`.

`python3 scripts/ci/check_migrations.py` не запускался: миграций нет.

Полные `pytest`, `ruff check .` и `mypy .` не запускались: они прямо запрещены для этого атомарного шага.

Попытка сохранить атом отдельным коммитом:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add -- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_tariff_api.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md
```

Результат: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`: `Operation not permitted`. Файлы не попали в индекс; `night/volna-9-recovery/JOURNAL.md` не затрагивался и не включался.

## Не реализовано

- Атомы 4–6 из `FEATURES.md` не выполнялись.
- Frontend, сквозной Playwright-сценарий, модели, миграции, внешние API, production и живой кабинет Wildberries не затрагивались.
- Отдельные сохраняемые поля суммы или ставки в `StorageStatement` не добавлялись: по архитектурному контракту черновик остаётся вычисляемым preview, а неизменяемый денежный снимок существует только в `BillingLedgerEntry` после фиксации.

## Находки

Нет. Секреты, ключи, токены, `.env`, кабинеты учётных данных и production не читались и не использовались.

## Блокеры

Backend-реализация и целевые тесты завершены без блокеров. Сохранение отдельного commit заблокировано правами среды на общий Git-каталог за пределами разрешённой рабочей копии; commit SHA не создан, изменения остаются только в рабочем дереве.

# Фича 4

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

# Фича 5

# DEV · 08-storage · screen-dev · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx` — после успешного сохранения тарифа экран применяет `recalculated_statements` из того же ответа API к уже показанной таблице, не запускает отдельное формирование за месяц и не меняет строки, которых серверный пересчёт не коснулся. При ошибке исходная таблица остаётся в состоянии последней успешной загрузки, а в `ErrorNotice` диалога показано сообщение на языке оператора.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.test.ts` — добавлены точечные unit-тесты замены пересчитанного черновика, сохранения зафиксированной строки и сохранения последней таблицы при пустом результате пересчёта.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts` — скорректирована регрессия `S-11-TC-002`: смена тарифа больше не ожидает POST ручного rebuild; добавлены атомарные сценарии видимого обновления суммы и ставки сразу после закрытия диалога и сохранения прежней таблицы с `ErrorNotice` при ошибке (`S-11-TC-017`).
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт этого атома.

## Гейты

Точная команда TypeScript-гейта:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json
```

Результат: зелёный, exit 0, ошибок нет.

Точная команда UI-гейта:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py
```

Результат: красный, exit 1, только из-за существующих нарушений вне файлов и слоя этого атома:

```text
НОВОЕ НАРУШЕНИЕ  src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646
НОВОЕ НАРУШЕНИЕ  src/screens/v2/FfFbsSupplyWorkspace.tsx: экран-монолит 2493 → 2498
НОВОЕ НАРУШЕНИЕ  src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169
стало лучше  src/App.tsx: экран-монолит 3492 → 3491
```

`FfStoragePage.tsx`, его unit-тест и `storage.spec.ts` в выводе нарушений отсутствуют. Baseline не обновлялся, несвязанные файлы не исправлялись.

Точная команда unit-гейта затронутого экрана:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts
```

Результат: зелёный — `1 passed` test file, `4 passed` tests. Команда была повторена после финальной правки и оба раза завершилась с exit 0.

Точная команда проверки обнаружения только браузерных кейсов этого атома:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test storage.spec.ts --grep 'S-11-TC-002|tariff repricing failure' --list
```

Результат: зелёный — обнаружены ровно три теста в одном файле: существующий живой `S-11-TC-002`, новый UI-кейс мгновенного пересчёта `S-11-TC-002` и негативный `S-11-TC-017`.

Точная команда атомарного браузерного прогона:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test storage.spec.ts --grep 'S-11-TC-002|tariff repricing failure'
```

Результат: красный до исполнения трёх сценариев. Playwright поднял приложение до открытия сокета, затем песочница запретила локальному API привязаться к `127.0.0.1:18000`: `[Errno 1] ... operation not permitted`. Продуктовый код и утверждения тестов не исполнялись. Предварительный прогон только двух новых заголовков завершился на том же ограничении.

Точная команда проверки diff:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check -- frontend/src/screens/ff/FfStoragePage.tsx frontend/src/screens/ff/FfStoragePage.test.ts frontend/tests-e2e/storage.spec.ts
```

Результат: зелёный, exit 0.

Полный backend `pytest`, `pytest -q` без путей, `ruff check .`, `mypy .` и полный frontend-регресс не запускались: атомарная проверка ограничена файлами и кейсами этого атома.

## Не реализовано

- Пункты контракта в коде реализованы буквально: после успешного POST открытый черновик заменяется серверным пересчётом без ручного формирования, а ошибка не очищает последнюю таблицу и отображается через `ErrorNotice`.
- Живое исполнение двух новых браузерных сценариев не подтверждено из-за запрета среды на локальный socket. Это ограничение проверки, а не пропущенный пункт реализации.
- Находка 5 из `REVIEW.md` о полном сквозном тесте с подготовкой живых UUID относится к следующему атому 6 и здесь не расширялась; текущий атом меняет только ожидание отсутствия лишнего rebuild в уже существующем живом кейсе и добавляет изолированные UI-проверки своего поведения.
- Несвязанные нарушения `ui_guard.py` не исправлялись, потому что их файлы не входят в разрешённый слой атома.

## Находки

- Новых находок по данным, персональным данным или безопасности в файлах атома нет.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production и живой кабинет Wildberries не читались и не использовались.

## Блокеры

- Полностью зелёный набор гейтов недостижим в этой среде: `ui_guard.py` падает на трёх несвязанных файлах, а Playwright не может открыть локальный loopback-порт.
- Сохранить атом в Git из этой песочницы невозможно. Выполнена точная команда:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add -- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.test.ts /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md
```

Git завершился с exit 128: `Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock': Operation not permitted`. Файлы не попали в индекс, commit SHA не создан. Уже изменённый до атома `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/JOURNAL.md` в команду не включался и не менялся.

# Фича 6

# DEV · 08-storage · screen-dev · атом 6

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts` — `S-11-TC-002` переведён на реальный сквозной setup: через существующий тестовый API создаются tenant с авторизованным администратором, операционный склад, селлер, товар, приёмка с фактическим движением и открытый storage-черновик. Тест проверяет реальные UUID, запрет вчерашней даты в обоих полях, один атомарный POST ставки склада и исключения селлера, HTTP 201, закрытие диалога, отсутствие дополнительного rebuild и видимые сумму/ставку из серверного `recalculated_statements`. Дублирующий route-моканный `S-11-TC-002` удалён; route-моков `/operations/storage/tariffs` и `/operations/storage/statements` в оставшемся кейсе нет.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт текущего атома.

## Гейты

Точный финальный TypeScript-гейт:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json
```

Результат: зелёный, exit 0, ошибок нет. Команда выполнена после финальной правки.

Точный финальный UI-гейт:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py
```

Результат: красный, exit 1, только из-за уже существующих нарушений вне разрешённого файла и слоя атома:

```text
НОВОЕ НАРУШЕНИЕ  src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646
НОВОЕ НАРУШЕНИЕ  src/screens/v2/FfFbsSupplyWorkspace.tsx: экран-монолит 2493 → 2498
НОВОЕ НАРУШЕНИЕ  src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169
стало лучше  src/App.tsx: экран-монолит 3492 → 3491
```

`frontend/tests-e2e/storage.spec.ts` в нарушениях отсутствует. Baseline не обновлялся, несвязанные файлы не исправлялись.

Точный финальный unit-гейт затронутого экрана:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts
```

Результат: зелёный — `1 passed` test file, `4 passed` tests. Команда выполнена после финальной правки.

Первая диагностическая команда обнаружения браузерного кейса:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test storage.spec.ts --grep '^S-11-TC-002' --list
```

Результат: красный, exit 1, `No tests found`: якорь `^` не совпал с полным заголовком, который сопоставляет Playwright. Команда исправлена без якоря.

Точная финальная команда обнаружения назначенного браузерного кейса:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test storage.spec.ts --grep 'S-11-TC-002' --list
```

Результат: зелёный — найден ровно `1 test in 1 file`, `storage.spec.ts:64`.

Точный атомарный браузерный прогон:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test storage.spec.ts --grep 'S-11-TC-002'
```

Результат: красный до исполнения сценария. Backend создал тестовые таблицы и дошёл до открытия сокета, затем песочница запретила привязку API к `127.0.0.1:18000`: `[Errno 1] ... operation not permitted`. Тестовый код `S-11-TC-002` не исполнялся, поэтому продуктового падения сценария этот запуск не зафиксировал.

Точная относящаяся к атому backend-регрессия пересчёта:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_tariff_api.py::test_new_tariff_reprices_open_draft_on_reload
```

Результат: зелёный — `1 passed in 1.31s`.

Точная проверка пробелов:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check -- frontend/tests-e2e/storage.spec.ts
```

Результат: зелёный, exit 0.

Полный backend `pytest`, `pytest -q` без путей, `ruff check .`, `mypy .` и полный frontend-регресс не запускались: атомарная проверка ограничена `S-11-TC-002` и непосредственно относящимися к нему тестами.

## Не реализовано

- Живое исполнение `S-11-TC-002` не подтверждено в этой песочнице: локальному Playwright webServer запрещено открыть loopback-порт. Точную команду нужно повторить в среде, где разрешён bind `127.0.0.1:18000`.
- Пункты кода атома реализованы буквально: route-моки storage API и фиктивные идентификаторы убраны из `S-11-TC-002`; тест требует реальный 201, один POST, серверный пересчёт и видимый результат. Соседние атомы и продуктовые задачи не менялись.
- Несвязанные нарушения `ui_guard.py` не исправлялись и baseline не двигался, поскольку их файлы не входят в разрешённый слой атома.

## Находки

- Новых находок по данным, персональным данным или безопасности в разрешённом файле атома нет.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production и живой кабинет Wildberries не читались и не использовались.
