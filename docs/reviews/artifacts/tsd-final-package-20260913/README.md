# Артефакты единого финального Astra-review, 13.09.2026

`mobile-final-delta.patch` дополняет сохранённый `../tsd-package-20260913/mobile-integration.patch`:
первый patch восстанавливает mobile af9693126d19d16918abd5cc7b7fbe99dfebc142 →
45676eee0225d895a21d2d41030a652172411e6d; этот patch —
45676eee0225d895a21d2d41030a652172411e6d → f3c7f23abc33680a3f4a127634c753b73924e63d.
Patch сохранён с нулевым контекстом; применять через `git apply --unidiff-zero mobile-final-delta.patch`.
Последняя дельта затрагивает только FbsViewModel.kt и FbsViewModelTest.kt.
Она сохраняется в remote основного репозитория; отдельный push nested mobile этим review не выполнен.

Установленный emulator-5580 APK и локальный app-debug.apk имели одинаковый SHA256:
`64df8c6af6de1eb057368e7549d5ddf750055e53e6afbacafdf8f54f4e7fb5d0`.
Это проверка равенства APK, а не повторная сборка из Git в данном проходе.

`seed_native.py` и `native-fixture.json` — только подготовка нового synthetic контура
в локальной БД wms_tsd_20260913. Скрипт получает пароль из WMS_FINAL_PASSWORD, не хранит его.
Приёмка 936cc6a4-60e8-4916-acc3-6356b8a396a1 создана сервисом и оставлена в sorting.
Нативный проход остановлен по timebox владельца на экране входа. Размещение и начисление
через Android не совершены, current queue на новом контуре не наблюдалась.
Ожидаемые 3 единицы / 3000 копеек в manifest не являются фактическим начислением.
Эти файлы не используются как доказательство PASS WMS-444 или C21 WMS-445.
