# WMS-363 / WMS-401 / WMS-412 — публикация preview v10

10.09.2026. Опубликован отдельный неизменяемый APK
[WMS-TSD-0.1.9-cfe8b5adc1bb-debug.apk](https://github.com/chivkunovd-bitdenis/WMS/releases/download/tsd-preview/WMS-TSD-0.1.9-cfe8b5adc1bb-debug.apk).

Источник: main WMS d5d8f5a5cbfcb22756ebea1f137e0f2029c63e33, pushed;
Android beb2ba6dea046845e93c5c56c73963a7fb0ee117 сохранён локально, его
безопасный накопительный patch и metadata сохранены в основном Git.
83 целевых Android-теста прошли у автора; независимый reviewer принял точный
APK и самостоятельно проверил hash/размер/package/version/minSdk/signature.
Протокол: wms363-apk-final-independent-review-20260910.md.

Размер:45624909байт. SHA256:
cfe8b5adc1bbd62e728184b9a18a1e5a14a837b3028de865e493c6203bd36870.
ru.wms.tsd, versionCode10, versionName0.1.9-ozon-tsd, minSdk24.
Сертификат SHA256:e343ab0cccc6284b271a72da42a67b14a0f0893d92b9ca461f1cac3d0be1aeb6.

Порядок выпуска: совместимый API0771833b уже проверен на production; затем
загрузка APK asset554577899 (created_at08:17:30UTC); GitHub server digest
совпал с локальным; только затем заменён update.json. Manifestasset554581217
имеет digest34edfe7a67aa17b58bb9f9620d9f53073b88a248b89108271c9da794ccf01a41.
Координатор скачал manifest по обычному публичному URL со штатной TLS-проверкой;
содержимое совпало с candidate JSON и указывает наversion10/cfe8APK.
Предыдущие APK сохранены, перезаписан только manifest канала.

[Проверка server asset](artifacts/wms415-astra-takeover-20260910/resumed/published-v10/apk-asset-verification.json),
[проверка публикации](artifacts/wms415-astra-takeover-20260910/resumed/published-v10/publication-verification.json),
[опубликованный manifest](artifacts/wms415-astra-takeover-20260910/resumed/published-v10/update.json).

Приёмка канала продолжается: CLI PID12345, прежний mobilethread, эмулятор
оставлен наversion9. Задача — настоящие кнопки проверки/скачивания/установки,
затем сохранённый PIN/server и учебный незавершённый документ. Установкаv10
черезadb запрещена как замена этому доказательству. На момент этой записи
успешная установка через приложение ещё не подтверждена. Физический ATOL,
сканер и принтер этой публикацией не проверены.
