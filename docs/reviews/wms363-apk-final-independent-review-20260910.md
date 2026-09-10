**ACCEPTED для разрешённой preview publication: прежний stale-box P2 закрыт в Android `beb2ba6dea046845e93c5c56c73963a7fb0ee117`. В проверенном узком исправлении оставшихся P1/P2 не обнаружил.** Вердикт относится к APK с SHA-256 `cfe8b5adc1bbd62e728184b9a18a1e5a14a837b3028de865e493c6203bd36870`.

Полный follow-up прочитан. Safe delta из двух файлов **побайтно совпала** с diff неизменяемых Android-коммитов `c9d27e16 → beb2ba6d`.

По фактическому коду подтверждено:

- **Старый ожидающий товар больше не уходит в A.** При обнаружении неизвестного короба удаляются ожидающие сканы режима `boxes` только этой поставки. Проверка отмены выполняется после ожидания `busy/error`, поэтому охватывает и элемент, уже извлечённый из канала. Одинаковые физические сканы остаются отдельными объектами и учитываются отдельно. См. [FbsViewModel.kt:97](/Users/deniscivkunov/Projects/WMS/.worktrees/wms397-mobile/android/app/src/main/java/ru/wms/tsd/features/fbs/FbsViewModel.kt:97) и [строку 107](/Users/deniscivkunov/Projects/WMS/.worktrees/wms397-mobile/android/app/src/main/java/ru/wms/tsd/features/fbs/FbsViewModel.kt:107).
- **Восстановление явно описано оператору:** выбранный адресат очищается, сообщение сообщает точное число отменённых ожидающих сканов и требует повторить короб и товары. Другие режимы и поставки исключены из этой отмены. См. [строку 413](/Users/deniscivkunov/Projects/WMS/.worktrees/wms397-mobile/android/app/src/main/java/ru/wms/tsd/features/fbs/FbsViewModel.kt:413).
- **Retry больше не воспроизводит отвергнутый скан и не отменяет свежие сканы.** После первого отказа действие завершается через `rejectedStaleBox`; свежая пара «B → товар», поставленная до закрытия сообщения или retry, сохраняется. См. [строку 403](/Users/deniscivkunov/Projects/WMS/.worktrees/wms397-mobile/android/app/src/main/java/ru/wms/tsd/features/fbs/FbsViewModel.kt:403).
- **Предыдущие исправления сохранены:** известный B выбирается до постановки товара в очередь; поздний ручной выбор не перенаправляет этот товар. При потерянном ответе назначения сохраняются адресат и тело запроса, а уже выполненное назначение определяется повторным чтением без второй записи. См. [строку 272](/Users/deniscivkunov/Projects/WMS/.worktrees/wms397-mobile/android/app/src/main/java/ru/wms/tsd/features/fbs/FbsViewModel.kt:272) и [строку 439](/Users/deniscivkunov/Projects/WMS/.worktrees/wms397-mobile/android/app/src/main/java/ru/wms/tsd/features/fbs/FbsViewModel.kt:439).

Новые девять тестов прочитаны: матрица покрывает WB/Ozon, A/`null`, обнаружение сразу либо на retry и четыре способа восстановления. **83 scoped PASS — результат автора; собственный прогон я не выполнял.**

APK самостоятельно проверил через SHA-256, размер, `aapt` и `apksigner`:

- **45 624 909 байт**, хеш полностью совпал с указанным выше и candidate JSON.
- `ru.wms.tsd`, versionCode **10**, versionName **0.1.9-ozon-tsd**, minSdk **24**, targetSdk **35**, debug.
- Подпись v2 действительна, один подписант. Сертификат прежний: `e343ab0cccc6284b271a72da42a67b14a0f0893d92b9ca461f1cac3d0be1aeb6`.

**Этот review снимает мой оставшийся блокер публикации данного APK.** Реальное обновление кнопкой **9→10**, PIN и продолжение незавершённого документа остаются следующим отдельным этапом. UI не проверял, APK не устанавливал, сохранённый эмулятор v9 не трогал. Физический ATOL предварительным условием preview не выставляю. Файлы и данные не изменял.