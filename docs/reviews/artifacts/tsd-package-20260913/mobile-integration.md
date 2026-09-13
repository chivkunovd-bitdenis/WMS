# WMS-440 / WMS-441 / WMS-442 / WMS-443 / WMS-444 / WMS-445: совместный мобильный checkpoint

База patch — `af9693126d19d16918abd5cc7b7fbe99dfebc142`. Итоговая локальная история вложенного Android-репозитория — `4615af715213e328122d3798e2359b5e793d8968`; она не публикуется. Patch содержит только `android/app/src/main` и `android/app/src/test`. Его обратное применение к итоговому локальному SHA проверено командой `git apply --reverse --check`.

## Интегрированные изменения

Сохранены ранее принятые WMS-440, WMS-441 и WMS-443 (`7968aad`). В этот checkpoint добавлены исходные поставки и их локальные интеграционные коммиты:

- WMS-442: `217f31380f5f7b8af37329a99f7fad5365b80247` → `57ff68e`; компиляционная стыковка print/pack API — `222effa`.
- WMS-444: `eef6c0e1c0411b2b3280925b3e299b31ae238e09` → `344c956`, `3a3cf5dcf54c500ac4dbf5f6f22b75df2fc504fa` → `c260c63`, `5a564700898b9922aad24311f9083a451d98aaff` → `825b3b1`; из-за общего AuthStore добавлен минимальный интеграционный `cf756c6`.
- WMS-445: `ad945b29100db43bddb7b9da56855a119cb51d48` → `ea0175b`, `67dc64913d05a7b7933e529892ba9eed95f03e2f` → `92ddfd1`.
- Тестовое совмещение WMS-441 cargo recovery с WMS-442 durable print и актуальной identity-сессией: `4615af7`.

Конфликты были разрешены без изменения экранов или сценариев: сохранены identity/PIN, входящая приёмка, cargo recovery, compact print actions, восстановление упаковки и FBS work context.

## Проверка

Независимый финальный запуск после `4615af7` выполнил один объединённый Gradle-набор с лимитами `workers=2`, `Xmx1200m`, Kotlin in-process: `SortingViewModelTest`, `SortingSessionTest`, `SortingListRecoveryTest`, `OutboundAssemblyViewModelTest`, `OutboundPackAttemptTest`, `FbsViewModelTest`, `AuthManagerUrlPersistenceTest`, `AuthStoreCryptoConfigTest`, затем `:app:lintDebug` и `:app:assembleDebug`. Результат: `BUILD SUCCESSFUL`, 54 задачи.

Итоговый debug APK установлен на `emulator-5580`. Выполнены только четыре навигационные smoke-проверки: после обновления профиля в header показаны полные ФИО и должность `Анна Тестовая WMS / Администратор склада`; Sorting request `#15` открывается и показывает существующие компактные действия печати `Товар` и `Ячейка`; FBS открывается с экраном `FBS · Заказы` и выбором WB/Ozon; outbound `444001` показывает обычную упаковку и `Завершить упаковку`, без прежней кнопки полки FBO.

Физическая печать и внешние маркетплейсы в этой проверке не запускались. Это технический интеграционный checkpoint, а не независимое ревью, приёмка БА или деплой.
