# WMS-441…445: исправления финального Astra-review

Исправлены шесть подтверждённых findings из `wms441-445-final-astra-review.md` минимальными изменениями в существующих web и ТСД-контекстах. Новый пользовательский экран, режим, сущность или backend-контракт не добавлялись.

| Finding | Исправление и регрессия |
| --- | --- |
| F1 | `FbsPendingScope` связывает сохранённую попытку FBS create/add с нормализованным server, tenant, employee и session. Чужая смена identity не читает, не отправляет и не удаляет receipt. `FbsPendingScopeTest` проверяет A → B → A. |
| F2 | Существующие web и Android name/password формы передают необязательный `organization`: web — введённый код, ТСД — известный единственный сохранённый код либо введённый. Email и выбор организации не добавлены. `useAuth.test.ts` и `AuthManagerUrlPersistenceTest` проверяют payload. |
| F3 | Web preview принтера хранит code и warehouse, отменяет устаревший ответ и подтверждает ровно previewed pair. `WarehousePrinterDialog.test.ts` покрывает замену A на B. |
| F4 | Для известной pending/running sorting-печати в текущем диалоге есть `Проверить`, вызывающее reconcile существующего request id. Повторная печать остаётся отдельным действием только после terminal result. `SortingViewModelTest` проверяет завершение recovery без второго create. |
| F5 | Автовыход из завершённой сортировки ждёт окончания print recovery; сохранённые print receipts выводятся существующими карточками очереди и после перезапуска остаются вручную восстанавливаемыми. `SortingViewModelTest` и `SortingListRecoveryTest` это проверяют. |
| F6 | Один и тот же cargo receipt автооткрывается лишь один раз за время текущего списка. После возврата он остаётся карточкой для явного повторного входа, а другой recovery-документ остаётся выбираемым. `SortingListRecoveryTest` покрывает consume и ручную доступность. |

## Проверка

Во frontend прошли `npx vitest run src/hooks/useAuth.test.ts src/screens/ff/warehouse-map/WarehousePrinterDialog.test.ts` (2 файла, 3 теста), `npx tsc --noEmit -p tsconfig.app.json` и `npm run build`. Vite вывел только существующее предупреждение о размере chunk.

Во вложенном `mobile` прошёл один экономный запуск `:app:testDebugUnitTest` с пятью целевыми test classes, `:app:lintDebug` и `:app:assembleDebug`: `BUILD SUCCESSFUL`, 54 задачи. Lint сформировал HTML-отчёт без ошибок; остаются только предупреждения deprecated Android security API и прежнее test warning.

Мобильный commit `c60c236ca8cc6eba51d4cd529bfd62bf95f0f9a9` локальный и не публиковался. `mobile-integration.patch` заново собран из `af9693126d19d16918abd5cc7b7fbe99dfebc142..c60c236ca8cc6eba51d4cd529bfd62bf95f0f9a9` только по `android/app/src/main` и `android/app/src/test`; `git -C mobile apply --reverse --check ../docs/reviews/artifacts/tsd-package-20260913/mobile-integration.patch` прошёл.

## RELEASE

Готово для одного финального Astra delta-review изменений F1–F6. Это техническая проверка исходников; стенд, реальные marketplace, физическая печать и приёмка аналитика не запускались.
