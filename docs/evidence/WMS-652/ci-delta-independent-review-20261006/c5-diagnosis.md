# WMS-672 C5: ограниченный диагноз actual CI37523087363

**Подтверждён продуктовый дефект потери причины настоящего decode отказа.
Первичная ошибка конкретного CI299 не установлена; выпуск остаётся красным.**
Нельзя назвать этот отказ доказанной ошибкой теста или инфраструктуры либо
считать его устранённым адресным локальным прогоном.

Идентичность: HEAD `f6066d68bd198794602a6e8916612d0d3b32460f`, tested merge
`2d1707cacdb9bbd2e92eee75115c9749ac969fcc`, run37523087363/attempt1,
print-regressions job112473176356, artifact11441536403. Реальный merge fetched
read-only. Замороженный тест, printBarcodeLabel и FfInboundRequestView
побайтно совпадают с локально проверяемыми файлами; три SHA256 записаны в
`c5-actual-ci-summary.json`. Исходные CI HTML/PNG/TAP сохранены ведущим в
`5b91c14681cce995d3690368df9996c891194406`,
`docs/evidence/WMS-652/common-ci-37523087363/`.

## Что точно наблюдалось в CI

Frozen C5 (`frontend/tests-e2e/wms672-box-labels.test.mjs:303`) сначала150,
затем299. Второе ожидание exact Alert `WMS672 decode failed at 299` завершилось
Timeout30000ms на308. Сохранённый fixture11 HTML имеет другой Alert:
«Не удалось напечатать этикетки.», iframe0, кнопка print-all включена.
Requests fixture11:147 GET, **0 non-GET**, поэтому mark-label-printed не было.
Неизвестный/пустой текст не выдан за успешную печать. Counter/native exception
identity, message, stack и индекс actual decode failure артефакт не сохраняет.
Source iframe после отказа уже удалён; невозможно восстановить его ошибка
объект из screenshot/HTML. Общий runner log не содержит browser pageerror:
эта ошибка обрабатывается продуктовым Promise catch и не является unhandled.

## Проверенная цепочка кода

`printBarcodeLabel.ts:170–212`: iframe load → native image.decode группами32 →
Promise.all → при любом rejection cleanup(image-error) удаляет iframe и
rejectTransfer передаёт **тот же исходный error**. До этой точки handoff и
технические отметки не выполняются. `FfInboundRequestView.tsx:1656` await этого
Promise; `:1684` ловит e и показывает e.message **только если e instanceof Error**,
иначе ставит общий текст. Finally снимает блокировку на1687–1688.

Тестовый load hook в `wms672-box-labels.test.mjs:80–97` создаёт функцию decode
в родительском page.evaluate контексте. Искусственное `new Error` на92 относится
к **родительскому** Error; объект native image.decode принадлежит iframe.
Поэтому сообщение искусственной299 ошибки само по себе не должно теряться.
Сохранённый общий Alert доказывает выбор fallback ветви при иной пойманной
ошибке. Наиболее вероятно native decode rejection выиграл до искусственного
отказа299; конкретное имя/индекс этой CI ошибки и причина native rejection
(повреждённое изображение, browser resource/decode budget, другая граница)
не доказаны. Генерация известных валидных пачек C1/C2 в этом run прошла;
это не исключает другой native отказ в позднем контексте.

## Две адресные локальные проверки без правки контракта/продукта

Запущен **только неизменный C5**, через `--test-name-pattern='^C5 '`, с
диагностическим adapter рядом с этим отчётом. Он сохраняет и повторно выбрасывает
тот же error; intercept printer transfer теста сохранён, сторонняя сеть запрещена,
Chrome --mute-audio. Vite работал только на127.0.0.1:16725 и штатно остановлен.
Chrome154.0.8037.98/darwin, Node24.13.1 отличаются от CI Chrome141.0.7390.37/linux,
Node24.21.0; это граница сопоставимости.

Обе intended errors150/299 в diagnostic1/2: Error, exact message, parentError=true;
нативных ошибок не записано. У150 corrected retry завершился. У299 exact Alert
также прошёл, corrected retry дал одну transfer, затем frozen C5 упал **на другой
точке**, allMarks248/321: RAF waitForFunction Timeout30000ms; parent printDisabled
true, Alert уже нет. Итог local C5 **FAIL**, не PASS. CI потеря exact299 этим
прогоном не воспроизведена. Эта соседняя локальная задержка отдельно не исследуется
и не используется для изменения C5 ожиданий или таймаутов.

Отдельно один заведомо плохой PNG (`data:image/png;base64,AAAA`) передан настоящему
неизменному printBarcodeLabels, без мокирования decode. Никакой печати/POST нет.
Подтверждены native **EncodingError**, message **The source image cannot be
decoded.**, parentInstanceofError=false. Exact screen catch выражение возвращает
**«Не удалось напечатать этикетки.»**, transfers0, iframe0. Результат
`c5-native-error-probe.json` воспроизводит именно потерю доступной причины на
соседней iframe→parent границе. Это реальный дефект R4 (причина в контексте действия),
но не доказательство, что тот же bad-PNG сценарий случился в CI.

## Что можно и чего нельзя заключать

Обработка настоящей cross-realm decode ошибки теряет её причину — подтверждено
реальным native probe, не теорией и не заменой ожидания. Безопасное прекращение
подготовки/отсутствие ранних отметок в сохранённом CI подтверждено отдельно.
Причина самой native ошибки в CI и её точный индекс остаются неизвестны. Нет
доказанного основания объявлять это чистым test-boundary/infra дефектом.

**Одной нормализации сообщения недостаточно обещать зелёный C5**: если иной native
отказ случается до299, экран покажет его реальную причину, а exact искусственный
fault299 всё равно не будет достигнут. Следующее необходимое доказательство —
bounded C5 в сопоставимом Linux/Chrome141 контуре с записью native/catch
name/message/index/counters до удаления iframe; без ослабления frozen assertions.
Код исправления, изменение fixed product reference и trusted SOURCE требуют
своих подтверждённых тестов, независимого review и утверждённой миграции.

Эта сессия сохраняет только диагноз/adapter/raw diagnostic data. Product,
frozen test, timeout, CI workflow, policy/SOURCE pin не менялись. Полный CI не
повторялся, main/GitHub/runtime не менялись, другие backend failures не исследованы.
