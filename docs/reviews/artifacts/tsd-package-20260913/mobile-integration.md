# WMS-440 / WMS-441 / WMS-442 / WMS-443 / WMS-444 / WMS-445: совместный мобильный checkpoint

База patch — `af9693126d19d16918abd5cc7b7fbe99dfebc142`. Итоговая локальная история вложенного Android-репозитория — `45676eee0225d895a21d2d41030a652172411e6d`; она не публикуется. Patch содержит только `android/app/src/main` и `android/app/src/test`. Его обратное применение к итоговому локальному SHA повторно проверено командой `git apply --reverse --check`.

## Интегрированные изменения

Сохранены ранее принятые WMS-440, WMS-441 и WMS-443 (`7968aad`). В этот checkpoint добавлены исходные поставки и их локальные интеграционные коммиты:

- WMS-442: `217f31380f5f7b8af37329a99f7fad5365b80247` → `57ff68e`; компиляционная стыковка print/pack API — `222effa`.
- WMS-444: `eef6c0e1c0411b2b3280925b3e299b31ae238e09` → `344c956`, `3a3cf5dcf54c500ac4dbf5f6f22b75df2fc504fa` → `c260c63`, `5a564700898b9922aad24311f9083a451d98aaff` → `825b3b1`; из-за общего AuthStore добавлен минимальный интеграционный `cf756c6`.
- WMS-445: `ad945b29100db43bddb7b9da56855a119cb51d48` → `ea0175b`, `67dc64913d05a7b7933e529892ba9eed95f03e2f` → `92ddfd1`.
- Тестовое совмещение WMS-441 cargo recovery с WMS-442 durable print и актуальной identity-сессией: `4615af7`.

Конфликты были разрешены без изменения экранов или сценариев: сохранены identity/PIN, входящая приёмка, cargo recovery, compact print actions, восстановление упаковки и FBS work context.

## Финальная дельта WMS-441…445

Коммит `c60c236` закрывает findings финального Astra-review: FBS create/add receipt привязан к server/tenant/employee/session (F1); name/password login передаёт известный либо введённый код организации (F2); preview печати связан со сканированным кодом и складом (F3); у pending/unknown печати есть отдельное штатное `Проверить` без повторного POST (F4); сохранённая незавершённая печать остаётся доступна в текущем списке после автозавершения и перезапуска (F5); cargo recovery не открывает автоматически только что возвращённый документ повторно, оставляя его доступным для явного выбора (F6).

Коммит `45676ee` закрывает delta findings WMS-442: durable receipt читается до публикации done-документа (D5); running/pending job показывает отдельные `Проверить` и `Печать ещё раз`, а второе действие требует существующий confirm sheet и создаёт новый UUID только после явного подтверждения (D4).

## Проверка

Независимый финальный запуск после `4615af7` выполнил один объединённый Gradle-набор с лимитами `workers=2`, `Xmx1200m`, Kotlin in-process: `SortingViewModelTest`, `SortingSessionTest`, `SortingListRecoveryTest`, `OutboundAssemblyViewModelTest`, `OutboundPackAttemptTest`, `FbsViewModelTest`, `AuthManagerUrlPersistenceTest`, `AuthStoreCryptoConfigTest`, затем `:app:lintDebug` и `:app:assembleDebug`. Результат: `BUILD SUCCESSFUL`, 54 задачи.

После финальной дельты выполнен целевой объединённый Gradle-запуск: `FbsPendingScopeTest`, `AuthManagerUrlPersistenceTest`, `FbsViewModelTest`, `SortingViewModelTest`, `SortingListRecoveryTest`, затем `:app:lintDebug` и `:app:assembleDebug`. Результат: `BUILD SUCCESSFUL` (54 задачи); lint сформировал HTML-отчёт без ошибок.

После delta D4/D5 выполнен один объединённый запуск `SortingViewModelTest`, `SortingListRecoveryTest`, `:app:lintDebug`, `:app:assembleDebug`. Результат: `BUILD SUCCESSFUL`; 18 и 2 targeted unit tests прошли без failures/errors.

Итоговый debug APK установлен на `emulator-5580`. Выполнены только четыре навигационные smoke-проверки: после обновления профиля в header показаны полные ФИО и должность `Анна Тестовая WMS / Администратор склада`; Sorting request `#15` открывается и показывает существующие компактные действия печати `Товар` и `Ячейка`; FBS открывается с экраном `FBS · Заказы` и выбором WB/Ozon; outbound `444001` показывает обычную упаковку и `Завершить упаковку`, без прежней кнопки полки FBO.

Физическая печать и внешние маркетплейсы в этой проверке не запускались. Это технический интеграционный checkpoint, а не независимое ревью, приёмка БА или деплой.
