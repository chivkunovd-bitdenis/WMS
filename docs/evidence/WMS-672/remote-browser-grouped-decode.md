# WMS-672: реальный Chromium после группового decode, точный 0e6a7fb

06.10.2026. Отдельный тестировщик. Это результат целевого remote probe, не приёмка,
независимое ревью, полный CI, выпуск или доказательство бумаги. Продукт, требования,
frozen тесты/harness и workflow WMS-673 не изменялись.

## Источник и сохранность доказательств

Продукт `0e6a7fbc3eb11f951febf972b35c6e117c42678a`.
Runner `af5b648cb3e7feadc5c89c4694f0ea8251b77458`, именованная ветка
`codex/wms672-673-analyst-20261006`, commit опубликован до запуска.
[Run 37438707882](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37438707882)
завершён failure. Ubuntu 24.04, Node 24, Playwright 1.56.1, настоящий Chromium,
deviceScaleFactor=4. HTTP-ответы синтетические, внешняя сеть браузера блокируется,
print перехвачен; API production и физический принтер не вызываются.

Сначала выполнен существующий focused `inbound 300|C5 decode|C7/C8|C8 mark`,
затем отдельный delta `return 300|C4 once|C6 fast`. Не повторялись старые 200,
C3/C10, ревью или приёмка. WMS-673 skipped.

Artifact `11399699902`, `wms-print-contract-af5b648cb3e7feadc5c89c4694f0ea8251b77458`,
21,390,773 bytes, retention 14 дней. Скачан в постоянный рабочий checkout,
логи, JSON, HTML, исходные PNG прочитаны; бинарные доказательства доступны в artifact,
в Git сохраняется отчёт. PDF в artifact нет.
Оба product manifests имеют SHA256
`26a096a52bfe5a92e68a9844cf1679d5193d0690036e010dcf8262ccb4f5f5b6`.
Frozen browser contract SHA256
`387555019c86e47b0875b83205715870f02c0c4396b24df3799216c62231ac53`,
harness `909d405c00427f98e5a8b71ce66e14f712d08cb39ee0c83a9a98bb5f77c0a2d0`.

## Фактический результат

Focused: 4 tests, 2 PASS / 2 FAIL, 101045.95148 ms.
Delta: 3 tests, 0 PASS / 3 FAIL, 87733.430651 ms.
Exit: 672=1, 672-delta=1, 673-renderer=skipped, 673=skipped.

| Случай | Факт | Граница вердикта |
|---|---|---|
| Приёмка 300 | decodeStarted=300, decoded=300, одна передача, HTML 3146003 символа, Alert отсутствует | Frozen C1/C2 FAIL после передачи в renderTape(), строка 115: EncodingError при новом Promise.all всех 300. PDF не создан |
| Возврат 300 | Те же 300/300 и одна передача | Та же ошибка второго, тестового decode; PDF не создан |
| C5 error150 | decodeStarted=160, decoded=128 на snapshot, 0 передач/0 POST, Alert `WMS672 decode failed at 150`, persistence отсутствует | Frozen FAIL на строке 231, ожидание decodeStarted===300. Защита до передачи наблюдается; enabled и corrected retry не достигнуты, полного PASS нет |
| C4 | n=1 передан; при n=200 decodeStarted=32, decoded=0, 0 передач/POST, hold остаётся true | Frozen FAIL на строке 210 до снятия hold; n=300 и полный timing.json не достигнуты |
| C6 double | После двойного click decodeStarted=32, decoded=0, 0 передач/POST, hold=true | Frozen FAIL на строке 252 до снятия hold. Single-transfer assertion не достигнуто |
| C7/C8 lost response + reload | Frozen PASS; первая передача, ошибка POST №150, afterprint, storage, настоящая page.reload, сохранённая исходная попытка/HTML | Проверены точные assertions существующего теста; он не доказывает полный resume всех отметок или бумагу |
| C8 retry | Frozen PASS; 300 decode, одна передача; после lost response повтор не отправил вторую ленту | Snapshot ещё transferred, всего 157 POST на закрытии. Полное завершение 300 отметок этим тестом не доказано |

У C7 после reload в новом JS-контексте счётчики тестового window отсутствуют, но
labelAttempt ID `48190b3c-321b-4c7a-9866-9c03e3ea4397` и исходный HTML 3146003
символа сохранены; POST №150 действительно был прерван. Не подменять это
новой подготовкой/новым документом. У C8 сохраняется исходная попытка
`7c0f35dc-ce35-447a-b1c3-e84124c7ace0`, одна передача и тот же HTML.

## PNG 226 и точная причина нового FAIL

Runner наблюдает native decode, сохраняет исходный data URL до cleanup,
пробрасывает ту же ошибку. Результат native, fault, timeout и assertions не заменяются.
Для 226 дополнительно сохраняется источник даже при успешном продуктовом decode.
PNG присутствует в focused fixtures 1/3/4 и delta fixture 1, побайтно одинаков:
7663 bytes, SHA256 `eb5911b54d15b862db384960760b4fa5c8189d1d02bdcb192e20966e11a7d2aa`.
Файл `672/fixture-1/INB-000000000226.png` — именно PNG этого run, не реконструкция.
Offline PNG parser и ZXing CODE128 на существующих node_modules без браузера:
836×356, точный `INB-000000000226`. Отдельный native decode в изоляции не запускался;
продуктовый grouped native decode уже завершил все 300 до передачи.

Ошибки 226 и следующих возникают на новом tape page внутри `renderTape()`:
`EncodingError`, `The source image cannot be decoded.`, code=0,
srcLength=10242, complete=true, width=836, height=356, barcode=INB-000000000226.
Это второй concurrent decode, который frozen test выполняет независимо от
продуктового grouped decode. Старый продуктовый отказ до передачи на 163259d
на этом SHA не воспроизведён. Лимит памяти Chromium этим запуском не измерен.

## Точная передача аналитику: бизнес-требования и расписание оснастки

Ничего ниже не реализовано в frozen files, продукте или требованиях.
Все текущие ошибки остаются FAIL, молчаливого PASS/исключения тестов нет.
R3 запрещает поштучные пользовательские/внешние ожидания, но не задаёт
одновременный старт всех N native decode. Продукт запускает группы по 32.
Оснастка одновременно требует другое расписание и теперь блокирует достижение
проверок сбоев и PDF. Нужна отдельная явная корректировка тестового контракта
аналитиком/владельцем тестов, сохраняя все бизнес-утверждения:

1. `renderTape()`, строка 115: вспомогательная повторная загрузка HTML не должна
   запускать 300 native decode в одном Promise.all. Группы с границей кадра либо
   другое подтверждённое расписание подготовки PDF; обязательно дождаться всех N.
   Не менять DPR/PNG/HTML, N страниц, 58×40, порядок/текст и raster CODE128 asserts.
2. C4 строки 210–212: hold первой группы снять после подтверждения перекрытия
   нескольких decode, отзывчивости UI и нуля передач; затем проверить все N перед
   одной передачей и сохранить измерения 1/200/300. Отдельно проверять границы
   кадров, поздний отказ и fallback остановленных кадров. Утверждение allN-start
   до release не является самостоятельным бизнес-требованием R3.
3. C5 строка 231: дождаться фактического отказа №150/Alert и завершения busy вместо
   недостижимого decodeStarted===300 после отмены следующих групп. Сохранить
   утверждения 0 print/marks, доступность действия и corrected retry с полными 300.
4. C6 строка 252: hold первой группы снять после двойного подтверждения и проверки
   одной начатой подготовки; затем дождаться всех 200 и оставить неизменными
   asserts одной передачи и отсутствия дублирования отметок.

До этих решений полный C1/C2/C4/C5/C6 не закрыт. Уже выполненные C7/C8 не нужно
повторять без изменения или нового основания. C9/C11/C12 вне этого probe.
Мак/локальный Playwright, навыки, новые БД, локальный npm ci, секреты, live writes,
внешние списания/подписи/печать, merge/deploy не использовались.

## Неизменённый вывод node:test

### Focused

```text
✖ C1/C2 inbound 300: one complete ordered 58x40 tape, real PDF and readable samples (13627.62664ms)
✖ C5 decode failure at label 150: no transfer/early marks, visible error, explicit corrected retry (38605.584365ms)
✔ C7/C8 response lost after transfer: restore source/attempt across reload before another external action (25139.839429ms)
✔ C8 mark failure retry repairs original attempt without silently printing another tape (22903.669292ms)
ℹ tests 4
ℹ suites 0
ℹ pass 2
ℹ fail 2
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 101045.95148

✖ failing tests:

test at tests-e2e/wms672-box-labels.test.mjs:134:5
✖ C1/C2 inbound 300: one complete ordered 58x40 tape, real PDF and readable samples (13627.62664ms)
  locator.evaluateAll: EncodingError: The source image cannot be decoded.
      at renderTape (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:115:29)
      at async TestContext.<anonymous> (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:142:22)

test at tests-e2e/wms672-box-labels.test.mjs:227:1
✖ C5 decode failure at label 150: no transfer/early marks, visible error, explicit corrected retry (38605.584365ms)
  page.waitForFunction: Timeout 30000ms exceeded.
      at TestContext.<anonymous> (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:231:18) {
    name: 'TimeoutError'
  }

```

### Delta

```text
✖ C1/C2 return 300: one complete ordered 58x40 tape, real PDF and readable samples (12826.017006ms)
✖ C4 once: measure 1/200/300 preview preparation; decode delays overlap and UI responds (38374.138167ms)
✖ C6 fast double confirmation belongs to one attempt and transfers at most once (36017.052027ms)
ℹ tests 3
ℹ suites 0
ℹ pass 0
ℹ fail 3
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 87733.430651

✖ failing tests:

test at tests-e2e/wms672-box-labels.test.mjs:134:5
✖ C1/C2 return 300: one complete ordered 58x40 tape, real PDF and readable samples (12826.017006ms)
  locator.evaluateAll: EncodingError: The source image cannot be decoded.
      at renderTape (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:115:29)
      at async TestContext.<anonymous> (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:142:22)

test at tests-e2e/wms672-box-labels.test.mjs:203:1
✖ C4 once: measure 1/200/300 preview preparation; decode delays overlap and UI responds (38374.138167ms)
  page.waitForFunction: Timeout 30000ms exceeded.
      at TestContext.<anonymous> (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:210:20) {
    name: 'TimeoutError'
  }

test at tests-e2e/wms672-box-labels.test.mjs:245:1
✖ C6 fast double confirmation belongs to one attempt and transfers at most once (36017.052027ms)
  page.waitForFunction: Timeout 30000ms exceeded.
      at TestContext.<anonymous> (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:252:18) {
    name: 'TimeoutError'
  }

```
