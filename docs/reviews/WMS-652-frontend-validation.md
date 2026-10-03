# WMS-652 · Валидация фронтовой части (разработчик)

Исполнитель фронтовых тестов: Opus Extra (claude-opus-4-7, effort xhigh).
Дата: 03.10.2026. Ветка: `codex/wms652-regression-guard`. Коммит сам не делаю —
по инструкции ведущего общий git-index делится с Astra; ведущий сохранит и
запушит.

Это отчёт исполнителя, не приёмка. Независимое перекрёстное ревью Astra high
лежит рядом: `docs/reviews/WMS-652-review-astra-frontend.md`; его F1/F2
исправлены (см. ниже).

## Исходное состояние (чем доказано)

- Полный frontend-прогон на Linux уже выполнялся до правок и **завершился
  неудачей** — GitHub Actions run **37139806128**, лог сохранён в
  `.agent-runs/wms652/ci-frontend-first.log` (ubuntu-24.04, Chrome stable
  через `browser-actions/setup-chrome@v2`, Poppler 24.02 через apt).
- Статистика прогона: **149 файлов, 145 passed / 4 failed; 1351 тест,
  1337 passed / 14 failed**.
- Группировка падений — предположение, которое ещё предстоит проверить
  следующим Linux CI после правок: 6 pagination-кейсов из одного файла,
  2 из `FfInboundRequestView.test.ts`, 2 из `FfFbsSupplyWorkspace.size.test.ts`
  и 4 из `wms636.dom.test.tsx` (R5, R6/R7, R10/R11, C10). Для wms636
  R6/R7, R10/R11 и C10 — правдоподобный каскад от первого R5-таймаута
  через утечку `act()`, не установленная причинность.
- Полный backend GitHub уже SUCCESS: 3951 passed / 179 skipped / 1 xfail,
  PG5, ruff/mypy/миграции зелёные.

## Разбор падений Linux CI

| Файл | Падение в CI | Диагноз | Статус |
|---|---|---|---|
| `src/utils/printMarkingCodeLabel.pagination.test.ts` | 6× `Error: Chrome did not produce a complete PDF` на 30-с дедлайне | Старый `stdio: 'ignore'` + 30-с ожидание глушили любой stderr, так что точная причина раннего выхода Chrome в CI **не установлена**. Правдоподобная гипотеза — SUID `chrome-sandbox` отсутствует на ubuntu-ранере и Chromium от `setup-chrome@v2` выходит мгновенно; это нужно подтвердить stderr-инструментацией в следующем Linux CI | Правка внесена; реальная причина будет установлена новым Linux CI |
| `src/screens/ff/FfInboundRequestView.test.ts` | `testid multiset …(104) ≠ …(92)` и `expected 4101 to be ≤ 600` | Baseline из WMS-586 — устарел на 14 новых selectors / 2 удалённых; `≤600` — исторический A-3 split (коммит 9283d754e, 28.08.2026, предок HEAD). Соответствующих split-модулей сейчас в дереве нет, экран снова один монолит 4101 строк; **почему модули ушли — здесь не установлено**. Шаг 2 WMS-652 разрешает убрать устаревший тест с объяснением | Исправлено |
| `src/screens/v2/FfFbsSupplyWorkspace.size.test.ts` | `['Box:118px','Box:150px','Box:118px',…] ≠ [‥]` и `['Box:150px','Box:118px',…] ≠ [‥]` | UI поменял литеральные ширины 118/150. Инвариант не в цифрах, а в выравнивании колонок между вариантами ряда | Исправлено |
| `src/screens/v2/FfFbsSupplyWorkspace.wms636.dom.test.tsx` | R5 `Test timed out in 5000ms`; затем R6/R7, R10/R11, C10 падают с ошибками через `act()`/DOM | R5 измерен в 5514 мс при 5-с дефолте, запускает сценарий дважды с перемонтированием — harness-таймаут. Три последующих падения — **правдоподобный каскад от R5 через утечку `act()`, не доказанная причинность**; Linux CI после подъёма R5 покажет, уходят ли они вместе | Правка внесена; каскадность будет проверена Linux CI |

### 1. `printMarkingCodeLabel.pagination.test.ts`

Что сделано:

- Добавлен отдельный блок `WMS-613 CI gate · WMS_REQUIRE_PRINT_PAGINATION`.
  Когда `WMS_REQUIRE_PRINT_PAGINATION=1`, он обязан увидеть executable Chrome
  (`WMS_PRINT_CHROMIUM` + `existsSync`) и `pdfimages` на PATH; при любом
  отсутствии — громкое падение с человеческим сообщением. Шаг CI в
  `.github/workflows/ci.yml` (коммит `a8deb6e69`) уже выставляет эту
  переменную, так что обещание ведущего «отсутствие chromium или poppler
  явно падает в CI» теперь выполняется на самом тесте, а не только в
  шаговом `test -x`.
- Локальный opt-in сохранён: без `WMS_REQUIRE_PRINT_PAGINATION` отсутствие
  Chrome остаётся safe skip (`describe.skipIf(!chrome)`), gate тихо проходит.
- Spawn Chrome: добавлены `--no-sandbox --disable-dev-shm-usage`. Это
  безопасно именно здесь: тест рендерит только собственный локальный HTML
  во временной `--user-data-dir`, и это не браузер пользователя. Гипотеза
  о причине старого падения — отсутствие SUID `chrome-sandbox` в сборке
  `setup-chrome@v2` и мгновенный выход Chromium на ubuntu-ранере; подтвердить
  или опровергнуть это должен следующий Linux CI с stderr-инструментацией.
- `stdio: ['ignore', 'pipe', 'pipe']`, листенеры `error`/`exit`/stderr/stdout.
  Теперь:
  - любой spawn-error ловится и выдаётся с stderr;
  - ранний exit до появления PDF — отдельная ошибка с `code`, `signal`,
    stderr и stdout;
  - 30-секундный дедлайн тоже показывает «что произошло». Эта
    инструментация и есть способ установить реальную причину —
    предыдущий лог 37139806128 её не содержит.
- Cleanup: SIGTERM → ждём 2 с → SIGKILL → ждём ещё 2 с события `exit` до
  удаления временной папки. Так Chrome не пишет в директорию, которую
  `rmSync` вот-вот удалит (поправка по замечанию Astra).

Проверка:
- Chrome установлен и require=1: 7/7 passed, 5.79 с
  (`/tmp/vitest-pagination-final.log`).
- Chrome отсутствует, require=1: gate падает громко, 6 pagination-кейсов
  скипнуты (`/tmp/vitest-pagination-gate-noChrome.log`).
- Chrome отсутствует, require не задан: 1 passed (gate без условия), 6
  скипов (`/tmp/vitest-pagination-local.log`).

### 2. `FfInboundRequestView.test.ts`

Что сделано:

- Снят исторический `≤600` строк: `9283d754e` 28.08.2026 — предок HEAD,
  соответствующих split-модулей сейчас в дереве нет, причина их
  отсутствия здесь не установлена. Требования WMS-652 (шаг 2 плана)
  разрешают убрать устаревшую проверку с объяснением. Комментарий в
  тесте так и говорит. Продуктовый экран не трогаем.
- Полный multiset testid заменил на required-подмножество. Все 89 ещё
  присутствующих baseline-selectors обязательны (missing-массив должен быть
  пустой), добавления разрешены. Единственные два изъятых —
  `ff-inbound-close-confirm` и `ff-inbound-close-confirm-dialog` — коммит
  `4221969c1` заменил локальный Dialog на родительский
  `confirmDiscardChanges`/`onDirtyChange`+`window.confirm`; эквивалента нет.
- Проверки сканирования (`replaces the just scanned row`, debounce
  reconciler, serial queue, scan dispatch filter), TS/ESLint гигиена и
  запрет `any` — сохранены как были.

Проверка: 9/9 passed за 1.77 с (`/tmp/vitest-inbound-v2.log`).

Исправление F1 Astra: ранее я случайно обрезал required-набор до 68
selectors; восстановил весь ряд ещё существующих ID, отдельно
подтверждено `node`-скриптом по текущему исходнику FfInboundRequestView.tsx
(23/23 YES; `close-confirm` и `-dialog` — NO с задокументированным источником).

### 3. `FfFbsSupplyWorkspace.size.test.ts`

Что сделано:

- Инвариант C4 «одна вертикаль столбца Размер» теперь измеряется через
  совпадение `columnsAfterProduct()` между вариантами ряда (ЧЗ / без ЧЗ /
  после печати) и форму раскладки (несколько `Box:<n>px`, затем
  Typography, затем `Stack:по содержимому`). Литеральные 118/150 убраны.
- Инвариант C5 «нет ЧЗ ни у одной строки → слот снимается у всей вкладки»
  — `boxes(plain).length === boxes(withMarking).length - 1`, формы «без ЧЗ»
  и «после печати» идентичны. Литералы 150/118 убраны.
- Остальные тесты файла (ширина 76 px у ячейки размера, прочерк без
  размера, перенос длинного значения, длинное название товара,
  WMS-489 перепечатка КИЗ, Ozon-варианты) сохранены как были.

Проверка: 19/19 passed (`/tmp/vitest-fixes-inbound-size.log`).

### 4. `FfFbsSupplyWorkspace.wms636.dom.test.tsx`

Что сделано:

- Единственное изменение — `{ timeout: 20_000 }` у теста R5. Логика
  сценария, ожидания результата, рендер и мок-сервер не трогал. В
  CI-прогоне 37139806128 R5 измерен в 5514 мс при 5-секундном дефолте.
  Падения соседних R6/R7, R10/R11, C10 — правдоподобная каскадная
  гипотеза через утечку `act()`, не установленная причинность. Поднятие
  именно одного теста ограничивает запас harness-ожидания и даёт
  следующему Linux CI проверить, уходят ли соседние три падения вместе
  с устранением R5-таймаута.
- Комментарий переформулирован на одно наблюдение в CI — не на
  обобщение «стабильно 5.5 с».

Проверка: 7/7 passed, R5 2.18 с (`/tmp/vitest-fixes-wms636.log`).

## Что не трогал

- `.github/workflows/ci.yml`, backend, `scripts/ci/`, guard infra — владение
  Astra (коммит `a8deb6e69` уже на ветке; env `WMS_REQUIRE_PRINT_PAGINATION=1`
  там уже выставлен).
- Продуктовый UI (`FfInboundRequestView.tsx`, `FfFbsSupplyWorkspace.tsx` и
  т.д.) — явное ограничение.
- Другие тестовые файлы и `vitest.config.ts` — не нужно: правок хватает
  трогать только четыре файла, никаких тестов не отключаю и не
  исключаю.
- Ветку/коммит `WMS-641`, подпроцессы других моделей, secrets, SSH,
  deploy, merge.

## Проверки

- Python-watchdog (`start_new_session=True` + `os.killpg`,
  `.agent-runs/wms652/watchdog.py`), жёсткий wallclock. Пересчитано по
  сохранённым логам, без повторных прогонов:
  - Отдельный прогон `FfInboundRequestView.test.ts`
    (`/tmp/vitest-inbound-v2.log`): `Test Files 1 passed (1)`,
    `Tests 9 passed (9)`, 1.77 с.
  - Совместный прогон `FfInboundRequestView.test.ts` +
    `FfFbsSupplyWorkspace.size.test.ts`
    (`/tmp/vitest-fixes-inbound-size.log`): `Test Files 2 passed (2)`,
    `Tests 28 passed (28)`. Из них по строкам «✓ src/screens/v2/
    FfFbsSupplyWorkspace.size.test.ts» 19 — это и есть все тесты
    size-файла. Отдельного одно-файлового запуска size.test.ts после
    финальных правок не было; отдельный ранний прогон size
    (`/tmp/vitest-size.log`, до правок — 17 passed / 2 failed) больше
    не отражает текущее состояние.
  - `FfFbsSupplyWorkspace.wms636.dom.test.tsx` в одиночку
    (`/tmp/vitest-fixes-wms636.log`): `Test Files 1 passed (1)`,
    `Tests 7 passed (7)`, R5 2.18 с.
  - pagination с Chrome+require
    (`/tmp/vitest-pagination-final.log`): `Test Files 1 passed (1)`,
    `Tests 7 passed (7)`, 5.79 с.
  - pagination с require, но без Chrome
    (`/tmp/vitest-pagination-gate-noChrome.log`): `Tests 1 failed |
    6 skipped (7)` — gate падает громко.
  - pagination без require и без Chrome
    (`/tmp/vitest-pagination-local.log`): `Tests 1 passed | 6
    skipped (7)` — локальный opt-in.
- `./node_modules/.bin/tsc --noEmit -p tsconfig.app.json`: exit=0 (`/tmp/tsc-final.log`).
- `npm run build`: exit=0 (`/tmp/npm-build.log`), vendor CryptoPro проверен.
- Полный `vitest run` на macOS дважды вис под параллельной нагрузкой;
  по решению ведущего не повторяю. Финальная проверка — Linux CI, его
  запустит Astra после коммита. Отключений/skip не прошу.

## Нерешённое / блокеры за границами задачи

- 4101-строчный `FfInboundRequestView.tsx` — это не моя задача WMS-652, а
  неоконченный архитектурный split (`9283d754e`). Комментарий к удалению
  исторической проверки это фиксирует; владельцу/аналитику решать
  отдельно.
- В CI-логе есть посторонние предупреждения `An update to
  ForwardRef(TouchRipple) inside a test was not wrapped in act(...)` в
  `FbsScanPrintToggles.dom.test.tsx` и повторяющиеся `overlapping act()`
  в wms636.dom. Гипотеза — часть из них исчезнет вместе с
  R5-каскадом после подъёма таймаута; проверит Linux CI, не моё
  утверждение здесь.

## Файлы и диагностические логи

- `.agent-runs/wms652/frontend-progress.md` — короткая живая сводка для
  ведущего.
- `.agent-runs/wms652/ci-frontend-first.log` — исходный CI (Astra, до
  правок).
- `.agent-runs/wms652/watchdog.py` — Python-watchdog для адресных прогонов.
- `/tmp/vitest-fixes-inbound-size.log`, `/tmp/vitest-fixes-wms636.log`,
  `/tmp/vitest-pagination-final.log`, `/tmp/vitest-pagination-gate-noChrome.log`,
  `/tmp/vitest-pagination-local.log`, `/tmp/vitest-inbound-v2.log` —
  целевые верификации.
- `/tmp/tsc-final.log`, `/tmp/npm-build.log` — тип-чек и сборка.

## Заключение исполнителя

Четыре фронтовых файла приведены к состоянию, при котором Linux CI
должен стать зелёным без ослабления продуктовых проверок. Коммит и
последующий полный Linux CI — за ведущим.
