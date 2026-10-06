# WMS-672/673: механическая интеграция готовой WMS-659

Интеграционный кандидат опубликован и прошёл целевые проверки. Полная приёмка нового кандидата не объявляется: независимое Astra high diff-review и заключение аналитика ещё требуются.

Ветка: `codex/wms672-673-prerequisite-integration`. Проверенный продуктовый SHA: **`f25e5a602b136052bb2bd4d3db008993378c6c17`**. База после fetch: `4b298efc95be7b4b6b7fe5665be9f3671f1fe747` (готовые WMS-659/657 и WMS-681). Ветка тестировщика `test/wms672-c7-c10-c11-20261006` сохранена на `afb2d5d3dfa989c43e8f979fe176f7c487fad4a4`; чужой analyst checkout не менялся. Старую историю продукта и checker не переносили.

## Сохранённый порядок и происхождение

Точные финальные reviewed тестовые blobs WMS-672 из 6b6a47e (включая 8afc05d), WMS-673 и разрешённую миграцию WMS-657 из 76f71776, новый отдельный C10 probe из afb2d5d3 сначала зафиксировали в **`c9f1df70cf22d45dee314741c4ed2700d13ee4c7`**. Это тестовый коммит до интеграционного кода; позднее эти файлы не менялись. Все 24 записи [test/source manifest](integration-contract-provenance.json) побайтно проверены после интеграции. WMS-659 DOM/backend/accepted correction ledger остались из etalon без diff. Миграция WMS-657 законна по 379f6f79 и последующей приёмке 2e49343a; historical F1 разрешён аналитиком, тесты здесь не переписывались.

Продукт перенесён только четырьмя scoped patches: 163259d4 + 0e6a7fb для WMS-672, bc272386 + 6b272491 для WMS-673. Текстовых конфликтов git apply --3way не было. [Исходные и итоговые blobs](integration-final-provenance.json), [точный product diff от базы](integration-product.diff) сохранены. Исторические Astra PASS 6c4c1253 / ff559d76 / e548d7b7 относятся к старым областям; новый кандидат ими не объявляется reviewed.

Новая компиляционная ошибка интеграции сохранена и **опубликована до исправления** в `7a11dee6b8c4e4c776826e79dab19bbf7fc7379e`: WMS-659 уже имела randomId import, старый patch WMS-672 добавил второй, получен TS2300. [Новый RED](integration-new-red.md), исходный tsc.log и [первичный product manifest](integration-product-provenance.json) сохранены. Следующий f25e5a602 удаляет только добавленный дубль, оставляя существующий import etalon. Ожидания тестов не ослаблялись.

## Реальная область продукта

Шесть файлов, 143 добавленных / 26 удалённых строк к свежему etalon:

- FfInboundRequestView: только ранее reviewed подготовка общей ленты, сохранение попытки и восстановление отметок. Массовое создание WMS-659, окно количества, mutation ID и разметка сохранены.
- inboundDraftPersistence: labelAttempt в существующем tenant/user/document recovery record; более новый read-only fallback etalon для non-JWT harness сохранён, строгие ключи записи не менялись.
- printBarcodeLabel: reviewed awaitable handoff и ограниченные параллельные группы только для inbound. Ветка без handoff сохраняет прежний void/Promise.all путь FBS scan-to-print; новая очередь/stock logic не вводится.
- FfFbsSupplyWorkspace: единственная новая строка — marketplace для print input. Вся более новая WMS-681 real WB QR/compensation логика сохранена.
- fbsSupplyAssembly: три добавления передачи/сохранения цвета своей группы.
- fbsUx: reviewed цвет, безопасный HTML, одиннадцать колонок и числовой Ozon fallback. Уже готовый перенос размера WMS-657 сохранён.

Backend production, bulk-create service, stock/reserve/location и printer worker не менялись. Все общие файлы переносились дельтами, а не старыми целыми workspace blobs. Semantic boundaries перечислены в provenance; единственная дополнительная интеграционная коррекция — duplicate import.

## Целевые проверки точного кандидата

[Remote run 37446838389](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37446838389) на exact **f25e5a602**, SUCCESS. Это отдельный integration workflow, не полный CI. [Pins, manifest, логи, hashes, снимки](integration-remote-37446838389/) сохранены в Git; продукт до/после выполнения не менялся.

Backend: **15 PASS / 1 штатный SKIP** в трёх существующих наборах WMS-659, WMS-672 scope и WMS-673 read-only mapping. Skip — `test_wms659_c7_same_mutation_is_concurrent_safe`: требует PostgreSQL locks, на disposable SQLite не выполняется. PostgreSQL concurrency не объявляется проверенной этим запуском. Новая локальная/общая БД не создавалась и не менялась; fixtures создавались только в одноразовом remote runner.

DOM: **95/95 PASS**, пять файлов. Включены все четыре frozen WMS-659 проверки (количество, API failure, lost-response mutation reuse, возврат, completed state), WMS-673 реальные одиночная/общая кнопки, старые assembly/fbsUx контракты, прежний числовой Ozon fallback. Оба WMS-681 guards отсутствия подмены реальных WB labels внутренним QR PASS. HTML-часть мигрированного WMS-657: **3 PASS**, C4–C6 исключены фильтром запуска; ранее пройденные неизменные PDF повторно не запускались.

Браузер на remote Linux Chrome: опубликованный отдельным тестировщиком C10 RED case теперь **2/2 PASS** (приёмка/возврат), прежний frozen C10 controls **1/1 PASS**. Нажатие «Создать короба» открывает готовое окно количества, non-GET = 0 и print = 0. Оба PNG лично прочитаны: окно количества присутствует. Это проверка интеграции, не новая visual C11/аналитическая приёмка. UI/API синтетические, сеть browser ограничена loopback, print перехвачен; реальные маркетплейсы/принтеры не вызывались.

Локально: `tsc --noEmit -p tsconfig.app.json` после удаления дубля PASS; Vite production build PASS с обычным предупреждением размера chunks, vendor integrity до/после PASS. npm clone/install не выполнялся: использованы существующие stable dependencies analyst checkout через symlink после cmp package-lock. Полный npm build script не запускался, чтобы не записывать общий incremental cache; отдельно выполнены compiler и Vite build. `git diff --check` продуктовых файлов PASS. Общий staged diff-check сообщает исходные пробелы/пустые строки raw logs и сохранённого patch; их байты не нормализованы ради сохранности доказательств. Checker документов от 4b298efc PASS; AGENTS/CLAUDE не менялись. Локальные DOM попытки прерваны без полного verdict; журнал сохранён честно, авторитетный полный targeted DOM — remote 95 PASS.

## Передача независимому ревьюеру и аналитику

Astra high должна независимо проверить **diff 4b298efc..f25e5a602**, шесть продуктовых файлов и test provenance, с фокусом на совмещение WMS-659 recovery с labelAttempt, сохранение WMS-681 QR, прежний FBS print путь и числовой Ozon fallback. Не требуется повтор полного ревью неизменных реализаций/PDF. Перед ревью прочитать текущие AGENTS и обе библиотеки owner-cases/failure-cases целиком. Разработчик не выставляет себе PASS ревью.

После независимого review аналитик должен оценить новый интегрированный SHA и C10 evidence вместе с ранее опубликованными C7/C11 tester proof. Требования/исторические вердикты перенесены без подмены новым self-PASS. Приёмка общего кандидата ещё не завершена. Далее по установленному порядку — PR и полный CI точного SHA; здесь они не запускались. Main/etalon, deployment и production не менялись, guard promotion не выполнялся. C12 — прежняя отдельная операторская проверка после выпуска и специального поручения. Субагенты, навыки, Mac browser и секретные кабинеты не использовались.
