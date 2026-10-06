# Проверка старых frontend harness 06.10.2026

Основа — общий кандидат `5ddd09aac4df17e7ecdefaf1625462c05f8039ce`.
Работа тестировщика выполнена отдельно в `codex/wms-priority-legacy-test-harness-20261006`.
Продукт, workflow и ожидания frozen666 не изменялись.

Исходные пять файлов повторно проверены на Node 20: ровно прежние четыре группы ошибок CI37460067342/job112257135369 — size suite падает до assertions на отсутствующем workspace.supply.id; два WB681 кейса ищут короба в packing вместо boxes;514 ищет удалённый legacy JSX guard; два636 кейса ищут removed input/message. Результат:4 failed files/1passed,5failed tests/35passed, одна collection failure.

Коррекция `2c9b9ebf2b4af14f55f7c0d165a88c046aabaaee` меняет только четыре старых тестовых файла. Size получает идентификатор поставки для компонента663 и распознаёт адаптивный flex на desktop;19проверок размеров/порядка/прочерка/перепечатки сохранены. WB681 открывает вкладку коробов, сохраняя оба запрета подмены этикетки WB и отсутствие retry-qr.514 теперь проверяет существующую общую панель, наличие поля перед тремя прежними переключателями, их взаимное исключение, активность только открытой editable packing и выключенный legacy intake; другие11кейсов сохранены.636 использует реальное общее поле, дополнительно проверяет сохранённый focus и пустое поле после undo; один серверный вызов, отсутствие повторного выбора, удаление хвоста немедленно и disabled undo сохранены. Assembly636 оставлен byte-identical.

Команда изfrontend: `npm exec --yes --package=node@20 -- node node_modules/vitest/vitest.mjs run src/screens/v2/FfFbsSupplyWorkspace.size.test.ts src/screens/v2/FfFbsSupplyWorkspace.assembly.dom.test.tsx src/screens/v2/FfFbsSupplyWorkspace.wms514.test.ts src/screens/v2/FfFbsSupplyWorkspace.wms636.dom.test.tsx src/screens/v2/FfFbsSupplyAssembly.wms636.dom.test.tsx src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx --no-file-parallelism`.
Целевой результат:6files/76tests PASS; после дополнительной проверки real field/focus отдельно514+636:2files/19tests PASS. Локальные зависимости установлены штатным npmci в своём worktree (общие node_modules не содержалиpdf-lib).

Дополнительная изолированная коррекция fixture666 — `dc9b1578ab2a4a72439cd418e572cbccdd8f91e6`: толькоasset response.blob сохраняет browser Blob для jsdom FileReader на Node20. Все17cases/asserts/events сохранены byte-identical. Реальный независимый Sol6.1high PASS и17/17Node20 — `docs/evidence/WMS-666/ci-qr-fixture-review-20261006.md`, reportSHA `ec1ffacb77140c87b0daba341da58313a157750d`. Canonical ledger666 заменяет прежнийa29 cumulativeDOMref, сохраняя историческийAstraprovenance вproof.

Formatting-only662: isolated `5feca959614667eb95e56a85e7b94efa497feeff` меняет одну пустую строку; finalblob `cefb7d8ac635c3da443a6f623c2fef4a1ff75850` равен5ddd. Ancestry merge-sours в этой ветке не изменил дерево: до/после `87fed766334ff39bf37980b3de8d65c4993eed2b`. Actual Sol independent review — `4ebab12df01f255f446719c54ac0436e7163a645`, evidence вdocs/evidence/WMS-662. Canonical662ledger создан.

Modelguard652 regression contract — `2e94cf5f04a7863cf8abbe028126a6e48f8aee95`:70checks,67PASS и3RED доfix на actualSolhigh вlegacy/array/fixture. Unknownmodel,loweffort,missing/nonPASSreview,wrongSHA/blob/head,extra paths и изменениеassertions всё ещёreject. Исправлениеchecker `f263064f4c5735a477b91bd92bea982c9eeceaf5` принадлежит интегратору; в этой ветке checker не менялся. Старые четыре harness не требуют frozenledger; canonicalchecker замечает только666/662, для которыхledger записан с фактическимreview.

Следующий шаг: независимыйreview четырёх старых harness и общий CI после интеграции. Полный CI, deployment и физическая печать здесь не выполнялись.
