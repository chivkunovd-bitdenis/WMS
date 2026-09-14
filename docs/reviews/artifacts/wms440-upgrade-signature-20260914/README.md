# WMS-440 — checkpoint signature incident, 14.09.2026

**Причина физического отказа не установлена. Обновление не объявлено исправленным.**

Фото владельца `owner-photo.jpg` лично просмотрено аналитиком. Экран показывает установленную0.1.10-mobile-recovery, доступную0.1.11-tsd-package и «Подпись обновления не совпадает с установленным приложением». Название версии на экране не доказывает SHA файла, сертификат установленного APK или причину отказа. Текст обещания сохранить вход/адрес/данные также не является доказательством их фактического сохранения после этой попытки.

Terra read-only проверил публичные артефакты tsd-preview:

| Артефакт | SHA256 APK | Метаданные |
|---|---|---|
| [Публичный11](https://github.com/chivkunovd-bitdenis/WMS/releases/download/tsd-preview/WMS-TSD-0.1.10-8435c3abcd24-debug.apk) | 8435c3abcd240afbaadb95e157512d52a56c105fd73440e6991933741237a81f | code11,0.1.10-mobile-recovery,v2 valid |
| [Публичный12](https://github.com/chivkunovd-bitdenis/WMS/releases/download/tsd-preview/WMS-TSD-0.1.11-tsd-package-a776769fdb8e-debug.apk) | a776769fdb8e5352808f84528110e6e4ed07f8eeac4320e3b904122ed7df3003 | code12,0.1.11-tsd-package,v2 valid |

У обоих один certificate SHA256: `e343ab0cccc6284b271a72da42a67b14a0f0893d92b9ca461f1cac3d0be1aeb6`. Это подтверждает совпадение сертификатов публичной пары, **не** сертификат физически установленной программы. Возможные различия установленного артефакта и поведения проверки Android7 пока не различены. Пересборка/смена подписи/манифеста до установления причины не выполнялись и этим checkpoint не разрешаются.

Локальная проверка среды: активных adb устройств нет; sdkmanager --list_installed показывает только android-35 Google APIs/Playstore arm64-v8a. Каталог android-24/default пуст, размер0B. На диске9.4GiB свободно. Образ API24/25 не установлен. Образы не скачивались, новый AVD не создавался, прежние данные emulator5580 не изменялись. Прогон API35 не заменяет требуемое воспроизведение Android7.

Остаётся получить происхождение/факты установленной на устройстве0.1.10 и безопасно воспроизвести именно применимый путь. Приёмка исправления по440C16–C18: old public baseline как контроль → штатная кнопка обновления и Android подтверждение → сохранены собственный профиль/PIN/server/seller scope и незавершённая очередь/ID без дубля. Подпись не обходить, приложение не удалять, данные не стирать. Private key/кабинеты секретов не нужны для установления публичного сертификата APK. До новых данных проверки остановлены; дополнительных CI/больших прогонов нет.

## Кандидат 13 до переключения публичного manifest

Исходник кандидата сохранён отдельно в nested mobile Git: `9202edd513efed59f35f5e025d9c0a545f8c3ee8` (`fix(WMS-440): dual-sign Android 7 update candidate`). Он меняет только debug-конфигурацию подписи, `versionCode=13`/`versionName=0.1.12-android7-update` и адресный тест отказа несовпадающего сертификата на API24 и API35. Проверка сертификата в `UpdateRepository` не менялась: archive signer по-прежнему обязан совпасть с установленным signer.

Собранный `app-debug.apk` находится в `mobile/android/app/build/outputs/apk/debug/app-debug.apk`; это не публичная ссылка и переключения `update.json` ещё не было. Его SHA256 `f81d8be26298839720becb08341ee8152dd5754c3ccfec6e3af01c857a8164f0`, размер 45,576,192 B, package `ru.wms.tsd`, code13, name `0.1.12-android7-update`, minSdk24. Certificate SHA256 тот же, что у public11: `e343ab0cccc6284b271a72da42a67b14a0f0893d92b9ca461f1cac3d0be1aeb6`.

`apksigner verify --verbose --min-sdk-version 18 --max-sdk-version 23` для одного и того же APK показывает v1=true/v2=false; `apksigner verify --verbose --min-sdk-version 24 --max-sdk-version 35` показывает v1=false/v2=true. Это выбор сильнейшей применимой схемы проверяющим инструментом, а не отсутствие второй подписи: в APK есть `META-INF/CERT.SF` и `META-INF/CERT.RSA`, а `jarsigner -verify` завершается успешно. Таким образом APK содержит и проверяемую v1 JAR-подпись для старого диапазона, и v2 для API24–35. `./gradlew testDebugUnitTest lintDebug assembleDebug` завершился успешно; адресный тест сохраняет отказ при пустом или другом signer на API24 и API35.

Передача кандидата аналитику выполнена только по локальному пути. До его отдельной приёмки C20 не выполнены загрузка versioned asset, анонимная проверка, изменение manifest или попытка на физическом Android7.
