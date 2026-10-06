# Очистка диска по прямому поручению владельца 06.10.2026

Владелец прямо поручил очистить диск: нехватка места мешает другому чату.
До очистки `df -h .`: 262 MiB свободно. После: 4.3 GiB;
точный последний `df -k`: Available 4,527,036 KiB.
Сумма предварительно измеренных удалённых каталогов: 4,196,516 KiB
(4.002 GiB). Параллельная работа может менять фактический свободный объём.

## Что удалено

Только следующие воспроизводимые результаты сборок и зависимости:

1. `.worktrees/wms595-tsd-inventory/android/app/build/`: `intermediates`,
   `tmp`, `kotlin` — 820,424 KiB.
2. `.worktrees/wms584-585-tsd-release/android/app/build/`: `intermediates`,
   `tmp`, `kotlin` — 530,000 KiB.
3. В `.worktrees/_artifacts-archive-20260925/` только `intermediates` и `tmp`
   под `mobile/android/app/build/` пяти сохранённых копий:
   `wms440-tsd-ui`, `wms441-tsd-ui`, `wms443-tsd-ui`, `wms445-tsd-ui`,
   `wms445-tsd-server-truth` — 1,177,820 KiB суммарно.
4. `/Users/deniscivkunov/.gradle/caches/8.11.1/`: `transforms`,
   `generated-gradle-jars`, `javaCompile` — 1,320,244 KiB.
   Скачанные библиотеки `modules-2`, Gradle и прочая конфигурация сохранены.
5. `.worktrees/support-task-7/prototypes/wms654-location-address/node_modules`
   — 348,028 KiB. Это не основной frontend/node_modules и не активный прототип.

До удаления проверены реальные каталоги (не symlink), `git ls-files`/игнорирование
для рабочих checkout, отсутствие открытых файлов через `lsof +D` и процессов
с соответствующим cwd. Процессов Java/Gradle/kotlinc не было. Удалены точные
абсолютные пути без glob и без принудительного `rm -f`.

## Что сохранено и как восстановить

Исходники, Git-ветки, изменения других чатов, базы, текущие PostgreSQL,
готовые APK в `build/outputs`, отчёты и результаты тестов сохранены.
Не тронуты действующие frontend-зависимости, среда Codex в `.cache/codex-runtimes`,
история чатов, Docker, пользовательские документы и Chrome.

Удалённые промежуточные файлы и кэш вновь создаёт штатная Android/Gradle-сборка.
Зависимости старого прототипа восстанавливаются `npm ci` в его каталоге.
`package-lock.json` до и после имеет SHA-256
`7962cce68009768143081751b00326a1dcf9833066ba00e0d10b0ab967097c8f`.
Отдельных архивов этих воспроизводимых кэшей не создавали.

Git status до/после: wms595 и support-task-7 чистые; в wms584 остаётся только
ранее существовавший `?? android/.kotlin/`. Чужой грязный fbs-unified-packing
не очищали. Рабочие деревья целиком не удалялись.

Эта очистка не означает выпуск WMS или прохождение продуктовых проверок.
