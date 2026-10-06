# WMS-595 / WMS-597 — независимое мобильное ревью

Изолированный Sol-review, 30.09.2026. Ревьюер не реализовывал код.

## Первичный вердикт

Предварительный вердикт: **WMS-595 — REJECT, WMS-597 — REJECT**. P1 не найдено; подтверждены два P2. Вердикт provisional, потому что проверенная реализация ещё не зафиксирована отдельным коммитом.

1. **P2, WMS-595 — HTTP 5xx после создания снимает защиту от дубля.**
   В [InventoryViewModel.kt:274](/Users/deniscivkunov/Projects/WMS/.worktrees/wms595-tsd-inventory/android/app/src/main/java/ru/wms/tsd/features/inventory/InventoryViewModel.kt:274) любой HTTP-ответ вне 2xx считается окончательным: на строках 275–277 удаляется сохранённая попытка и снова разрешается создание. Но `502/504` от прокси может означать, что backend уже создал документ, а ответ потерян. Следующий POST создаст второй документ, нарушая WMS-595 R4.

   Точный causal test: fake-server сохраняет документ, но возвращает `504`; после `create()` `pendingCreate` должен сохраниться, кнопка повторного POST — остаться заблокированной, а `reconcileCreate()` — найти созданный документ. Сейчас pending очищается. Guard: очищать попытку только при однозначном отказе; `5xx`, `408`, `429` оставлять для reconciliation.

2. **P2, WMS-597 — КИЗ многопозиционного Ozon-заказа печатаются с названием первого товара.**
   Backend `a68b4aea…` специально возвращает для каждого кода `order_product_id`: [fbs_supplies.py:351](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-urgent-product-tsd/backend/app/api/fbs_supplies.py:351), [fbs_supplies.py:2383](/Users/deniscivkunov/Projects/WMS/.worktrees/wms-urgent-product-tsd/backend/app/api/fbs_supplies.py:2383). Native DTO это поле целиком отбрасывает в [FbsModels.kt:469](/Users/deniscivkunov/Projects/WMS/.worktrees/wms595-tsd-inventory/android/app/src/main/java/ru/wms/tsd/core/api/fbs/FbsModels.kt:469), после чего [FbsViewModel.kt:1413](/Users/deniscivkunov/Projects/WMS/.worktrees/wms595-tsd-inventory/android/app/src/main/java/ru/wms/tsd/features/fbs/FbsViewModel.kt:1413) подписывает каждый Data Matrix как `order.product.name`. Для Ozon-заказа с товарами A и B обе этикетки получают название A, хотя сами КИЗ различны.

   Точный causal test: две позиции `A/B`, ответ tape содержит `CIS-A → position-A` и `CIS-B → position-B`; сгенерированный документ должен содержать соответствующие названия A и B. Сейчас оба кода подписываются A. Нужен разбор `printed_codes.order_product_id` и сопоставление с `order.positions.id`; legacy-fallback допустим только при отсутствии связи.

Остальные адресно проверенные пути — фильтры и постраничный каталог инвентаризации, выбранное место и `line_id`, ручной факт/пустое место/проведение, native-права, Ozon position IDs для коробов и current-primary товарные этикетки — новых P1/P2 не дали.

Проверенный снимок:

- Native HEAD/base: `41f0f336f11bb998486cc18e9f0a711831897a4a`.
- Backend-контракт: `a68b4aea116b55f9e2d3d84a68c4a6b92ca0c56c`.
- SHA-256 tracked patch: `0e31d8ff341dc43ada213e041c4ee20cd81c6e1a9ceba91d8483323448532253`.
- SHA-256 untracked source/test manifest, без generated `android/.kotlin`: `818732e76d693a488e4a1cba7374096ed6c8272fa1a077a5c7f6bfad5b71fc75`.
- Проверенные mtimes `+0400`: `FbsModels.kt` — `14:04:18`; `FbsViewModel.kt` — `14:46:36`; `InventoryApi.kt` — `15:08:20`; `InventoryScreens.kt` — `15:16:19`; `InventoryViewModel.kt` и `InventoryLogicTest.kt` — `15:35:39`. Снимок за время ревью не изменился.

Файлы не менял, тесты не перезапускал, push/merge/deploy не выполнял. Это только code review, не подтверждение QA эмулятора, физического сканера или принтера.



## Повторная проверка двух исправленных дефектов

**Provisional PASS по обеим исправленным дельтам.** Оба прежних P2 устранены; новых соседних P1/P2 не обнаружено.

- **WMS-595 PASS.** В [InventoryViewModel.kt:275](/Users/deniscivkunov/Projects/WMS/.worktrees/wms595-tsd-inventory/android/app/src/main/java/ru/wms/tsd/features/inventory/InventoryViewModel.kt:275) ответы `408`, `429` и `5xx` теперь сохраняют durable pending. Повторный `create()` блокируется, reconciliation находит созданный документ без второго POST. Однозначные ошибки по-прежнему очищают pending.
- **WMS-597 PASS.** [FbsModels.kt:469](/Users/deniscivkunov/Projects/WMS/.worktrees/wms595-tsd-inventory/android/app/src/main/java/ru/wms/tsd/core/api/fbs/FbsModels.kt:469) принимает `printed_codes.order_product_id`, а [FbsViewModel.kt:159](/Users/deniscivkunov/Projects/WMS/.worktrees/wms595-tsd-inventory/android/app/src/main/java/ru/wms/tsd/features/fbs/FbsViewModel.kt:159) сопоставляет каждый КИЗ с правильной Ozon-позицией. При старом ответе без `printed_codes` сохраняется прежний fallback через `codes`. Неверный известный position ID больше не маскируется названием первого товара.

Снимок пока без финального commit: HEAD `41f0f336f11bb998486cc18e9f0a711831897a4a`.

Финальные SHA-256 затронутых файлов:

- `InventoryViewModel.kt`: `c065a10ffa3377ffd918d40f453744c1efa01bcfa1d3b727e2e980cb159c9f98`
- `InventoryCreateViewModelTest.kt`: `24934bfa769f2e8e323967e4bcdeda7751f88ea9fa6931eaed260b63a5f6844b`
- `FbsModels.kt`: `2b3bd73b7bbe1cfa436ffa2ef9653d08a93f26de41be6c017bbeedd066e38204`
- `FbsViewModel.kt`: `8b960793c251d3483a98038cbc86d3d7073ec2c1df055e359d2fa3b917c27bef`
- `FbsFormattingTest.kt`: `2761f0635ea27639f15253989e72079f3edaa1a4a9347deff5a8c20f2e130433`

Во время ревью автор удалил один лишний import из inventory-теста; продуктовые файлы не изменились. Тесты и эмулятор не запускал, файлов не менял, push/merge/deploy не выполнял. Финальный PASS требует только сверки этих хешей с будущим commit SHA.

## Дополнительная адресная проверка

Ведущий отдельно выполнил `InventoryLogicTest` после последнего изменения распознавания алиаса в выбранном месте: 5 тестов, 0 failures, 0 errors; Gradle BUILD SUCCESSFUL за 3 секунды. Полный набор повторно не запускался.

## Финальная фиксация

30.09.2026: native-код сохранён отдельным коммитом `8f9f4b35a9eab3d52d9422ae15b1f58e1d7859c0` в ветке `codex/wms595-inventory`, рабочее дерево чистое. Ведущий прочитал каждый из пяти перечисленных файлов именно через `git show HEAD:<path>` и вычислил SHA-256: все пять совпали с заключением независимого ревьюера. Условие provisional-вердикта выполнено; итог независимого code review — **PASS**. Повторное ревью неизменённого кода не запускалось. Физический сканер/принтер и живые площадки этим выводом не подтверждаются; публикация остановлена владельцем.

Автор уточнил в своём единственном неопубликованном коммите только `docs/PROGRESS.md` после итоговой проверки; итоговый native SHA — `8f9f4b35a9eab3d52d9422ae15b1f58e1d7859c0`. Сравнение с ранее сверенным снимком показало изменения исключительно журнала, продуктовые файлы и пять проверенных хешей неизменны. Последний адресный прогон: InventoryCreateViewModelTest 1/1 и FbsFormattingTest 3/3, без failures/errors.
