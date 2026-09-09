# WMS-401: реальный Android APK, 09.09.2026

Из исходников мобильной ветки `codex/wms397-mobile`, commit `dfcb7624216a6bb26bae1641357d4145764b85cf`, собран новый debug APK. Исходники приложения не менялись. Это результат сборки и установки, не подтверждение работы полного ФБС на складе.

## Артефакт и проверки

Файл: `/Users/deniscivkunov/Projects/WMS/outputs/wms401-android-20260909/WMS-TSD-FBS-dfcb762-debug.apk`.
Размер: 45 215 728 байт. SHA256: `1b5ab4498a451416873441a7afdae695f86f74166ae3093ba2a1ca0e2bbabb09`.
Пакет `ru.wms.tsd`, versionCode 5, versionName `0.1.4-atol7`, minSDK 24 (Android 7), target/compile SDK 35. В DEX проверено наличие новых `FbsScreensKt` и `FbsViewModel`. `apksigner verify --verbose` успешен, схема v2; использована существующая debug-подпись. Release-подпись, ключи и remote мобильного репозитория не менялись.

Gradle 8.11.1, Java 17, существующий Android SDK 35. Один процесс Gradle, максимум два worker, JVM 2 GiB. Выполнены только `:app:testDebugUnitTest` с фильтрами `ru.wms.tsd.features.fbs.FbsViewModelTest` и `ru.wms.tsd.features.fbs.FbsApiContractTest` (9+2 теста, 0 ошибок/падений/пропусков), затем `:app:assembleDebug`. Обе команды BUILD SUCCESSFUL. XML результатов и `build-proof.json` лежат рядом с APK. Полные Android тесты не запускались.

## Реальная установка и граница показа

Использован существующий AVD `wms_tsd` (Android 15/API 35, arm64), 2 GiB RAM/2 CPU. `adb install -r` вернул Success; MainActivity запущена. Userdata не стирали, приложение не удаляли. При холодном старте появилось системное окно System UI is not responding; нажата Wait, после чего экран приложения доступен.

На реальном экране входа сохранился пользователь review-user, активной сессии нет. Кнопка «Войти по паролю» нажата и не переключает экран. Подтверждение в `android/app/src/main/java/ru/wms/tsd/features/auth/LoginScreen.kt`: ветка savedStaff.isNotEmpty && !showPinDialog показывает список; обработчик onLoginWithPassword снова выставляет showPinDialog=false. Поэтому при сохранённом сотруднике обычный экран пароля и настройки сервера недостижимы этой кнопкой. На момент этого отчёта код не исправлялся; факт передан root.

Скриншоты реального эмулятора: `outputs/wms401-android-20260909/02-accounts.png` и `03-password-click.png` (в основном checkout). Секретов на снимках нет. В опубликованном Git находятся отчёт и доказательства сборки; APK хранится в постоянном ignored outputs и восстанавливается сборкой указанного мобильного SHA.

Существующий staging bearer проверен read-only: auth/me возвращает ожидаемый QA tenant `9c31f3f4-ce62-4c1f-891a-295b278f1e69`, роль fulfillment_admin. Сам bearer не выводился и не подставлялся вместо пароля. В проверенных конкретных проектных QA-документах и сценариях обычный пароль этого пользователя не найден. Сброс пароля, создание пользователя, обход входа и очистка данных не выполнялись.

Следовательно, список → поставка → подбор → упаковка/КИЗ → короба в этой сессии ещё не открыты; физических ТСД, сканирования и печати эта проверка не подтверждает. Debug API по умолчанию `http://10.0.2.2:18080/`; подключение нового APK к staging через обычный вход пока не выполнено. Это не production-сборка и не утверждение готовности ФБС к работе операторов.
