# WMS-663: одна галка на этапе коробов — прогресс реализации

Исходная общая версия: `585877bedf948faf7e38d14acc7e89acbf4feab3`.
Ветка: `codex/wms663-boxes-single-checkbox-20261006`.
Владелец runtime: `/root/priority_663`; контракт и тесты пишут отдельные исполнители. Свежие правила `origin/etalon:AGENTS.md` прочитаны; прямое уточнение владельца имеет приоритет над прежним UI-решением.

На первом шаге проведено только чтение. Runtime и замороженные тесты не изменены. Старый `OzonExemplarDocuments` расположен в строках упаковки и использует per-exemplar PUT. Для общей галки нельзя молча выполнять несколько таких PUT одного posting: каждый создаёт отдельный SET, а незавершённый первый запрос блокирует следующий.

Минимальный предложенный путь: оставить существующий durable сервис и строгий SET→STATUS/readback, добавить явный пакетный выбор отсутствия требуемых документов всех экземпляров одного posting. Точный набор экземпляров берётся из подтверждённого snapshot, проверяется по товарам и количествам заказа; другие сведения и marks сохраняются. Один posting получает один claim/version и один SET. Классификатор STATUS уже сравнивает все ключи `choices`, поэтому повторная отправка после unknown не требуется.

В интерфейсе остаётся одна галка «Без ГТД и РНПТ» в коробах текущей Ozon-поставки. Открытие экрана и обратный клик не отправляют отсутствие и не стирают документы. Ошибка, отказ и неизвестный результат показываются из прежнего состояния операции; не добавляются модалки, кнопки сохранения, печать, ship или изменения учёта. Новый код будет начат только после опубликованного test-before-code коммита и согласования точного API-контракта с тестировщиком.

Следующий шаг: получить новые тесты, реализовать узкую frontend/backend коррекцию, прогнать затронутые тесты, полный TypeScript check и build, затем передать отдельному ревьюеру точный опубликованный SHA. Production, staging и общая release-ветка не изменяются.

## Первый сохранённый runtime и проверки

`d4d1c658839d1cdbb8b9e50509f046a30bf5ffa3` — первичная663 операция/галка после test-before-code4c38. `6b6ff12c1` — отдельная666 коррекция общих мест колонок/возврата строк; `a853239214de613d1cadc9945092c98f7186f9a7` — отдельный662 возврат baseline ссылки Состава. Все опубликованы в собственной ветке.

На a853: 44/44 targeted frontend PASS (owner6637 +662C19 +666DOM17 +size19),48.68s; 74 backend PASS/1 ранее PG-only SKIP,20.23s во всех семи затронутых663 test files. Полный `npx tsc --noEmit -p tsconfig.app.json` и `npm run build` PASS. Ruff двух backend файлов PASS; mypy обоих PASS с `--cache-dir=/dev/null` (обычный cache получил disk I/O при127MiB свободного места, не ошибка типов). Compatible lockSHA2564ec9fd6b9291d52f2c3534bc3fb4ebbfd24a9d029f3d3d01127e43404c01984c, новых dependencies не установлено.

Старый OzonExemplarDocuments сохранён только ради исторических прямых тестов по отдельному разрешению ведущего. Production screens его не импортируют: единственное нетестовое упоминание — определение самого legacy export. Во всех142 собранных JS assets отсутствуют строки «Номер ГТД · SKU», «Номер РНПТ · SKU», «Сохранить ГТД / РНПТ · SKU», «Получить экземпляры». Workspace импортирует только новый Checkbox-only компонент. Существующие supply alerts используются для ошибки; новые панели/кнопки/статусные строки не добавлены.

Первый двухфайловый frontend запуск был ошибочно начат из корня checkout: owner6637 PASS, C19 collection failed по относительному fixture path. Повтор штатной команды из frontend прошёл в составе44 PASS. Это не продуктовый дефект и frozen fixture не менялась.

Независимое review ещё НЕ PASS: reviewer662 обнаружил два новых663 recovery defects. После прерванного batch preparing доSET остаётся marker намерения, не позволяющий явный первый SET после истечения lease; после accepted batch штатный marking claim заменяет текущий choice marker и falsely сбрасывает отображение intent. Отдельный тестировщик пишет узкие regression contracts до исправления. Следующий шаг — исправить только эти новые случаи и вернуть точный SHA тому же reviewer. Unknown после действительно отправленного SET сохраняет STATUS-only границу. Геометрический GREEN требует фактического browser DOM на новой общей версии, здесь не заявлен. Production/staging/main не изменялись.

## Узкая коррекция двух новых recovery defects

Отдельный тестировщик сохранил два фактических RED до исправления: `2afefa04e1b921ba94c40ba17887ee987a7c2589`, proof `f660fbe5f545c5519f7d81212c976d5f8c3d281d`. Реальный claim/checkpoint/restart доSET и настоящий accepted batch→KIZ воспроизвели ошибки; guards unknown-afterSET не ослаблены.

Исправление опубликовано в `d01e0b8885e85004dffac4d6c1e27e8d39bb8a90`, ровно один service файл. При fencing истёкшей preparing операции очищается только неотправленный batch intent; сохранённый snapshot не стирается. После маркировки checkbox intent вычисляется из прежней durable choices map и requirement flags всех экземпляров, а не только текущего operation marker. Save использует тот же predicate, поэтому отсутствию не нужен повторный SET после штатного КИЗ.

Сначала новые2+исходные5 batch cases — 7 PASS/1.28s. Поскольку изменены document_view и общий preparing fence, выполнены все затронутые663 backend checks:76 PASS/1 прежний PG-only SKIP/19.91s. Ruff PASS, mypy двух source files с cache-dir=/dev/null PASS. Frontend послеa853 не менялся, прежний full tsc/build и44 UI PASS сохраняют актуальность; не повторялись.

Независимый reviewer662 перепроверяет эти два конкретных defects. Дополнительно он обнаружил third UI case: полный достоверный posting без требуемых документов не должен мешать aggregate checkbox остальных required posting или получать повторный prepare. Пустой/неизвестный ответ нельзя автоматически объявлять не требующим документов. Отдельный tester пишет узкий test-before-fix; frontend изменение ещё не выполнено. Технический review и фактическая browser geometry пока не закрыты.

## F3: агрегирование только по полному известному составу

`45261220443cb1ffb0c2fd03522a96f23d1296ee` первоначально исключал nonempty no-required posting. Целевые1+7 frontend checks тогда дали8 PASS/10.15s, полный tsc/build PASS. Reviewer конкретно уточнил, что nonempty STATUS может содержать лишь один SKU из двух или один экземпляр вместо qty2; это не доказательство полноты. Поэтому intermediate452 не назван завершённым review.

Отдельный tester до новой runtime-дельты сохранил exact contracts: `a08c98f77d9f39d0ed7991bb8fd6f19f21ebef62` добавил только true completeness в fixture полного B (assertions прежние); `f938b2dba65c2d2f8605e78b087eb2076b5e8fda` — backend3 RED и frontend2 RED для false/missing completeness; proof `c28f3f54ce66e195774eba2620c941b4f28d85df`. Эти ancestry импортированы до исправления.

Исправление опубликовано: `1fe678d9abb4ed06afc79eba41461e3215978d5b`, ровно2 runtime files (+21/-2). Backend document_view вычисляет `requirements_complete` из уже прочитанных FbsOrderProduct positions и snapshot: exact SKU set, количество экземпляров, положительные уникальные ID. Нет дополнительного SQL/HTTP/state/store. Frontend пропускает не требующее документов отправление только при true completeness и обоих false required flags каждого реального экземпляра. Empty/partial/legacy missing-completeness не считаются доказательством отсутствия требований.

Фактические проверки exact runtime: backend3 completeness+2 recovery+5 batch —10 PASS/1.36s; Ruff PASS; mypy2source cacheless PASS. Frontendpositive completeB+false/missing negative —3 PASS/3.00s; полный `npx tsc --noEmit -p tsconfig.app.json` и `npm run build` PASS (Vite1.92s). Остальные44 UI и76 backend checks повторно не гонялись: прежняя666/662 геометрическая runtime-дельта и старые backend state/recovery branches здесь не менялись.

API export обновлён штатным scripts/export_fbs_openapi.py в `c7c079262fa39289554542e93d0134b103835746`: новый95-й route absent и OzonAbsentDocumentsBody; все94 прежних path objects и все старые schema objects идентичны. Existing OpenAPI contract4 PASS/5.81s. Дополнительные DTO поля не меняют OpenAPI return schema dict[str,Any].

Тот же независимый reviewer получил exact1fe678 для узкой перепроверки F3; PASS здесь пока не приписывается. Следующая граница — root integration, actual staging browser geometry по сохранённому RED contract и common CI. Production/main/675apply/внешние SET документов не выполнялись.
