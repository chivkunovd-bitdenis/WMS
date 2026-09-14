# WMS-440 APK14 — повторный запуск финальной приёмки, 14.09.2026

После восстановления GitHub CLI авторизации прежние docs до02c1183c подтверждены в remote. Запущены только собственные fixture18086 и сохранённый AVD `wms440_upgrade13`/5582/API35/GPU host. PackageManager: code11/name0.1.10-mobile-recovery/minSdk24; auth_store checksum остался `fa6aa68d0294a49a4c19d84dbac183de9aa6a9753103a605e0375ee0d1f7562c`.

`baseline11.xml`: прежний synthetic профиль a@b.co виден в chooser. `baseline-home11.xml`: прежний PIN фактически открыл Home. Сохранённый server этого неизменного auth_store — http://10.0.2.2:18086/. Локальный fixture не представляет реального сотрудника/складскую очередь. После этого Terra получил READY на публикацию14; в приложении открыт экран обновления, проверка/загрузка14 не запускались.

**Блокер публикации:** Terra подтвердил asset14 в release API, но exact URL `https://github.com/chivkunovd-bitdenis/WMS/releases/download/tsd-preview/WMS-TSD-0.1.13-profile-migration-29327127f27a-debug.apk` анонимно вернул404 без redirect. Astra независимо выполнила один GET с уникальным cache-busting query:HTTP404,0bytes. Предположение CDN-задержки не считается доказанной причиной. Manifest оставлен13; до доступного14 C24 не начинается.

**Остановка среды:** Available2084708KiB =1.988GiB, ниже заранее заданного координатором порога2GiB. Собственный5582 штатно остановлен через emu kill; userdata сPUBLIC11/PIN сохранена, ничего не стиралось. Другие AVD/приложения не изменялись.

**Заключение:** baseline C24 подтверждён; native11→14, миграция ФИО/PIN на14 и конечный server reread остаются НЕ ПРОВЕРЕНЫ. Локальный artifact14/v1/v2/same cert и адресные tests остаются ранее подтверждёнными; это не заменяет приёмку опубликованного14. Продолжение требует доступной публичной ссылки и достаточного свободного диска. Новые широкие тесты не выполнялись.


## Прямая установка публичного org APK14 — FAIL миграции

После освобождения места и нового прямого поручения выполнен14 поверх сохранённого11 без data clear; использован локальный файл с SHA `29327127f27aee63bc10c6189ef74691978adb06c8518ea4d35835c195632945`, точное совпадение с публичным org APK подтверждено SHA. [Публичный APK14](https://github.com/oyster-labs-cy/wms-tsd-updates/releases/download/tsd-preview/WMS-TSD-0.1.13-profile-migration-29327127f27a-debug.apk) и [manifest](https://github.com/oyster-labs-cy/wms-tsd-updates/releases/download/tsd-preview/update.json) анонимно проверены координатором полным stream SHA.

`installed14.txt`: code14/name0.1.13-profile-migration. `prefs14-before-start.sha256`: прежний auth_store checksum до первого запуска14. `chooser14.xml`: фактически форма ФИО/пароля вместо профиля для PIN. **C24 FAIL.** AuthStore14 default organizationSlug="", но getLegacyStaffForMigration требует "legacy"; сохранённый реальный JSON11 без этого поля исключён. Исправление передано Terra вместе с требованием теста serialized JSON11. Локальный synthetic auth/me доступен и возвращает валидные id/FIO/org; продуктовый код аналитиком не менялся.

Эта прямая установка не объявляется combined button11→14: старый personal manifest host всё ещё404 (Support #4756099). Кнопка11→13 ранее доказана отдельными evidence. Следующий адресный кандидат15 должен устранить реальную миграцию и использовать org manifest как канонический URL.
