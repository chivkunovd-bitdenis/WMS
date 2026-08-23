ФИЧ: 4

## Фичи

### 1. Не применять устаревший ответ WB поверх более нового вердикта

**Что меняется словами оператора.** Если одновременно идут две проверки кода и более поздняя уже получила отказ WB, поздно вернувшийся старый положительный ответ больше не сможет снова показать «WB: принято» и разрешить сдачу. Сервер сохраняет только актуальный результат проверки конкретного заказа и кода.

**Файлы.**

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`

**Зависит от.** Ни от одной предыдущей фичи.

**Как проверить.** В тесте `S-03-TC-016` искусственно запустить два синхронных запроса для одного заказа: поздний запрос записывает отказ с причиной, ранний возвращается после него с `filled`. После завершения обоих запросов в заказе остаются отказ и его причина, `metadata_delivery_allowed = false`; серверный гейт сдачи остаётся закрытым. Запустить `pytest backend/tests/test_fbs_marking.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend`.

### 2. Отдавать из сервера нейтральный вердикт ожидания WB

**Что меняется словами оператора.** Когда WB ещё проверяет код, сервер возвращает «WB: проверяет» с нейтральным тоном, а не с красным стоп-сигналом. Сдача при этом по-прежнему запрещена.

**Файлы.**

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`

**Зависит от.** Фича 1; обе меняют один серверный словарь вердиктов и его тесты, поэтому выполняются последовательно, чтобы не смешать правки и не создать конфликт.

**Как проверить.** Unit-тест вердикта для решения WB `pending` ожидает подпись `WB: проверяет`, тон `neutral` и `delivery_allowed = false`. Остальные запрещающие решения не меняют своих тонов. Запустить `pytest backend/tests/test_fbs_marking.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend`.

### 3. Показать для каждого блокирующего статуса следующее действие

**Что меняется словами оператора.** В рабочем месте поставки чип «WB: проверяет» остаётся нейтральным, а подсказка отключённой сдачи объясняет «WB ещё не подтвердил код». Для «WB: нужен код» оператор видит «Пришлите ЧЗ» и ту же понятную причину блокировки. Для «Нет ответа WB» остаётся строка «Сдача пока недоступна», а подсказка к сдаче говорит «Ждём ответа Wildberries». Причины отказа WB по-прежнему выводятся человеческим текстом, без технического кода.

**Файлы.**

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`

**Зависит от.** Фича 2: экран использует тот же контракт тона, который возвращает сервер для `pending`.

**Как проверить.** Unit-тесты словаря покрывают `pending`, `required`, отсутствие/неизвестный вердикт и отказ с причиной: тон и `disabledReason` совпадают с контрактом. В рабочем месте поставки вручную проверить три строки: ожидание WB — нейтральный чип и блокирующая подсказка «WB ещё не подтвердил код»; требуемый код — видимое «Пришлите ЧЗ»; отсутствие ответа — видимое «Сдача пока недоступна» и подсказка «Ждём ответа Wildberries». Запустить `npm run test:unit -- src/utils/metaStatus.test.ts` и `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend`.

### 4. Закрывать сдачу при ошибке фонового обновления рабочего места

**Что меняется словами оператора.** Если 15-секундное фоновое обновление поставки не получило свежий ответ, оператор видит складское сообщение об ошибке, прежний положительный вердикт больше не считается действительным, а кнопка «Передать в WB» блокируется. Пока следующее успешное обновление не пришло, строки показывают безопасное состояние «Нет ответа WB» и «Сдача пока недоступна».

**Файлы.**

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-supply.spec.ts`

**Зависит от.** Фича 3: использует её единые безопасные подписи и объяснения для состояния без свежего ответа WB.

**Как проверить.** Исполняемый сценарий `S-03-TC-018` открывает поставку с ранее принятым кодом, затем подменяет очередной запрос рабочего места ошибкой. Он проверяет видимый `Alert` без HTTP-кода, «Нет ответа WB», строку «Сдача пока недоступна» и неактивную кнопку «Передать в WB». Последующий успешный ответ снова снимает именно ошибку обновления и пересчитывает разрешение только по свежему серверному вердикту. Запустить `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-018'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend`.

## Порядок

Делать строго 1 → 2 → 3 → 4. Фичи 1 и 2 обе меняют один backend-сервис и его тестовый файл, поэтому параллельное выполнение создаст конфликт. Фичи 3 и 4 обе меняют рабочее место поставки, поэтому также идут последовательно. Между backend-цепочкой (1–2) и frontend-цепочкой нет отдельного исполняемого шага, но фича 3 намеренно ждёт фичу 2: так UI сразу закрепляет финальный контракт нейтрального ожидания.

## Что осталось за бортом

- Исправленный сценарий `S-03-TC-014` для нейтральной строки уже описан в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV-01.md`; повторно в разработку не включён.
- Сценарии `S-03-TC-015` и `S-03-TC-017` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/CASES.md` не являются самостоятельными незакрытыми замечаниями REVIEW.md. Их не расширяю в этой переделке; проверка фич 1–4 закрывает соответственно найденные регрессии `S-03-TC-016` и `S-03-TC-018` и словарь K8.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.
- Git-коммит артефакта не создан: среда запретила создание `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`. Файл существует только как локальное изменение рабочей копии, без восстанавливаемого SHA.
