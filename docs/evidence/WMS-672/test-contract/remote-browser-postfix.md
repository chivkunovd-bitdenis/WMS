# WMS-672: удалённая проверка после исправления на точном продуктном SHA

06.10.2026. Проверка отдельного тестировщика Sol 6.1. Продукт, замороженные ожидания,
тестовые entrypoints и WMS-673 не изменялись. Это целевой браузерный контракт,
не независимое ревью, приёмка, полный CI, деплой или подтверждение бумаги.

## Точная версия и запуск

Продукт: `163259d412d2ef5ba2d49b831cd5c7da284245d9`.
Первый runner: `b88ea82bc2331202377143dad587102a9bb72b22`.
[Run 37434776468](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37434776468):
Ubuntu 24.04, Node 24, Playwright 1.56.1; реальный Chromium на GitHub runner,
синтетические HTTP-ответы, внешняя сеть браузера блокирована, print перехвачен.
Workflow/helper опубликованы до запуска существующим ограниченным push trigger.
Сравнение полных manifest `frontend/src` и `backend` и неизменности frozen файлов PASS.
Оба манифеста SHA256 `57f3a680e3b71cda007dee2f8f8dd068d82e393800b3ab5d15dbdb725589ff87`.
Контракт SHA256 `387555019c86e47b0875b83205715870f02c0c4396b24df3799216c62231ac53`;
harness `909d405c00427f98e5a8b71ce66e14f712d08cb39ee0c83a9a98bb5f77c0a2d0`.

Artifact `11399176105`, `wms-print-contract-b88ea82bc2331202377143dad587102a9bb72b22`,
14,289,454 bytes, retention 14 дней. Скачан, логи и JSON прочитаны, PDF проверены.
Содержит исходные PDF/PNG, HTML, requests/state/events, Vite/установочные логи,
source-pin, два продуктных манифеста и source-hashes. Бинарные файлы не добавлены в Git.

## Первый фактический результат

11 tests: **5 passed / 6 failed / 0 skipped / 0 cancelled**, 291180.475485 ms.
`672=1`, `673-renderer=skipped`, `673=skipped`; WMS-673 не запускалась.

| Случай | Вердикт | Достигнутая проверка и ограничение |
|---|---|---|
| C1/C2 приёмка 200 | PASS | Одна передача, 200 decode, весь порядок/текст, 200 PDF-страниц и три декодированных образца |
| C1/C2 возврат 200 | PASS | Те же проверки прошли полностью |
| C1/C2 приёмка/возврат 300 | FAIL: реальный отказ decode | 300 decode начаты, 225 завершены, 0 передач/отметок, iframe удалён, видимая ошибка подготовки; PDF не создан |
| C3 | PASS | Короткий/длинный CODE128, экранирование подписи, номер >99, сохранённый размер 60×80 |
| C4 | FAIL: timeout на 300 | 1/200 дошли до передачи, на 300 передачи нет; timing.json не записан, полный замер не доказан |
| C5 | Частичная защита PASS; весь тест FAIL | Все утверждения до corrected retry прошли: 0 лент, 0 отметок, Alert, действие доступно. После снятия fault повтор 300 не передан; timeout на строке 240 |
| C6 | PASS | Двойной callback, 200 decode, строго одна лента, без дублирования отметок |
| C7/C8 reload | FAIL: не достигнут recovery | На первой подготовке 300 нет передачи и отметок; потеря ответа и reload не достигнуты |
| C8 retry | FAIL: не достигнут retry | Та же первая подготовка не передана; потеря ответа/восстановление не достигнуты |
| C10 | PASS | Пустой/один короб, создание грузомест и открытие без печати |

Таймауты jsdom из developer handoff остаются TIMEOUT, не PASS. Первые remote
таймауты не объявлены бизнес-RED по одному ожиданию; диагностический повтор
ниже устанавливает первичный отказ. C9/backend, C11/операторский экран и
C12/физическая бумага этим поручением не проверялись.

## Проверка скачанных PDF без локального браузера

`pypdf` прочитал оба файла: по 200 страниц, **все страницы 57.827×39.878 мм**,
допуск frozen assertion <0.5 мм к 58×40 соблюдён. Текст страниц 1/101/200:
`Короб № 1 / INB-000000000001`, `Короб № 101 / INB-000000000101`,
`Короб № 200 / INB-000000000200`. Отдельный offline ZXing decode скачанных
PNG из pdftoppm подтвердил все шесть точных CODE128. Растры первой/средней/
последней страницы визуально просмотрены: заголовок, штрихкод и строка кода
помещаются целиком, обрезания нет. Соответствующие PNG приёмки/возврата
побайтно совпадают. PDF серий 300 отсутствуют; их размеры/decode не доказаны.

PDF SHA256:
* inbound-200: `2002da78fb0ab748a36119855e2e3743c4b7c4ffa5ca5f5c53a265cd31b36e3a`
* return-200: `db484cf853153fcc33801e398d4a9f5538a8ad0bb8a1f59ce268861cd9652cdb`

## Исходный вывод первого node:test

```text
Diagnostic capture: page.evaluate: SecurityError: Failed to read the 'localStorage' property from 'Window': Access is denied for this document.
    at UtilityScript.evaluate (<anonymous>:292:16)
    at UtilityScript.<anonymous> (<anonymous>:1:44)
✔ C1/C2 inbound 200: one complete ordered 58x40 tape, real PDF and readable samples (15106.000512ms)
✖ C1/C2 inbound 300: one complete ordered 58x40 tape, real PDF and readable samples (38573.0483ms)
Diagnostic capture: page.evaluate: SecurityError: Failed to read the 'localStorage' property from 'Window': Access is denied for this document.
    at UtilityScript.evaluate (<anonymous>:292:16)
    at UtilityScript.<anonymous> (<anonymous>:1:44)
✔ C1/C2 return 200: one complete ordered 58x40 tape, real PDF and readable samples (13196.835681ms)
✖ C1/C2 return 300: one complete ordered 58x40 tape, real PDF and readable samples (38073.682413ms)
Diagnostic capture: page.screenshot: Timeout 3000ms exceeded.
Call log:
  - taking page screenshot
  - waiting for fonts to load...
  - fonts loaded

Diagnostic capture: page.evaluate: SecurityError: Failed to read the 'localStorage' property from 'Window': Access is denied for this document.
    at UtilityScript.evaluate (<anonymous>:292:16)
    at UtilityScript.<anonymous> (<anonymous>:1:44)
Diagnostic capture: page.evaluate: SecurityError: Failed to read the 'localStorage' property from 'Window': Access is denied for this document.
    at UtilityScript.evaluate (<anonymous>:292:16)
    at UtilityScript.<anonymous> (<anonymous>:1:44)
✔ C3 renderer: short/long CODE128, >99 title, escaped special text and saved alternate size (5166.428648ms)
✖ C4 once: measure 1/200/300 preview preparation; decode delays overlap and UI responds (48022.600326ms)
✖ C5 decode failure at label 150: no transfer/early marks, visible error, explicit corrected retry (43168.197814ms)
✔ C6 fast double confirmation belongs to one attempt and transfers at most once (8121.059941ms)
✖ C7/C8 response lost after transfer: restore source/attempt across reload before another external action (38033.505818ms)
✖ C8 mark failure retry repairs original attempt without silently printing another tape (37754.949145ms)
Diagnostic capture: page.evaluate: SecurityError: Failed to read the 'localStorage' property from 'Window': Access is denied for this document.
    at UtilityScript.evaluate (<anonymous>:292:16)
    at UtilityScript.<anonymous> (<anonymous>:1:44)
✔ C10 controls: empty/one/cargo, creation dialog and opening never print (5235.563501ms)
ℹ tests 11
ℹ suites 0
ℹ pass 5
ℹ fail 6
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 291180.475485

✖ failing tests:

test at tests-e2e/wms672-box-labels.test.mjs:134:5
✖ C1/C2 inbound 300: one complete ordered 58x40 tape, real PDF and readable samples (38573.0483ms)
  page.waitForFunction: Timeout 30000ms exceeded.
      at transfer (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:109:16)
      at TestContext.<anonymous> (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:139:28) {
    name: 'TimeoutError'
  }

test at tests-e2e/wms672-box-labels.test.mjs:134:5
✖ C1/C2 return 300: one complete ordered 58x40 tape, real PDF and readable samples (38073.682413ms)
  page.waitForFunction: Timeout 30000ms exceeded.
      at transfer (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:109:16)
      at TestContext.<anonymous> (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:139:28) {
    name: 'TimeoutError'
  }

test at tests-e2e/wms672-box-labels.test.mjs:203:1
✖ C4 once: measure 1/200/300 preview preparation; decode delays overlap and UI responds (48022.600326ms)
  page.waitForFunction: Timeout 30000ms exceeded.
      at transfer (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:109:16)
      at TestContext.<anonymous> (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:216:13) {
    name: 'TimeoutError'
  }

test at tests-e2e/wms672-box-labels.test.mjs:227:1
✖ C5 decode failure at label 150: no transfer/early marks, visible error, explicit corrected retry (43168.197814ms)
  page.waitForFunction: Timeout 30000ms exceeded.
      at transfer (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:109:16)
      at TestContext.<anonymous> (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:240:25) {
    name: 'TimeoutError'
  }

test at tests-e2e/wms672-box-labels.test.mjs:261:1
✖ C7/C8 response lost after transfer: restore source/attempt across reload before another external action (38033.505818ms)
  page.waitForFunction: Timeout 30000ms exceeded.
      at transfer (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:109:16)
      at TestContext.<anonymous> (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:265:25) {
    name: 'TimeoutError'
  }

test at tests-e2e/wms672-box-labels.test.mjs:291:1
✖ C8 mark failure retry repairs original attempt without silently printing another tape (37754.949145ms)
  page.waitForFunction: Timeout 30000ms exceeded.
      at transfer (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:109:16)
      at TestContext.<anonymous> (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:295:11) {
    name: 'TimeoutError'
  }
```

## Состояния перед закрытием контекста

Данные только синтетического tenant/user/document. Число отметок взято из
фактического списка HTTP requests; полные storage HTML исключены из этой сводки.

```json
[
  {
    "fixture": "fixture-1",
    "decoded": 200,
    "decodeStarted": 200,
    "transfers": [
      {
        "decoded": 200,
        "htmlLength": 2097083
      }
    ],
    "fault": {},
    "local": [
      {
        "key": "wms440:/api/:672-tenant:672-user:672-document",
        "state": "transferred",
        "remainingPaths": 115,
        "htmlLength": 2097083
      }
    ],
    "session": [],
    "frames": [
      {
        "images": 200,
        "complete": 200
      }
    ],
    "alerts": [],
    "marks": 84
  },
  {
    "fixture": "fixture-2",
    "decoded": 225,
    "decodeStarted": 300,
    "transfers": [],
    "fault": {},
    "local": [],
    "session": [],
    "frames": [],
    "alerts": [
      "Не удалось напечатать этикетки."
    ],
    "marks": 0
  },
  {
    "fixture": "fixture-3",
    "decoded": 200,
    "decodeStarted": 200,
    "transfers": [
      {
        "decoded": 200,
        "htmlLength": 2097083
      }
    ],
    "fault": {},
    "local": [
      {
        "key": "wms440:/api/:672-tenant:672-user:672-document",
        "state": "transferred",
        "remainingPaths": 112,
        "htmlLength": 2097083
      }
    ],
    "session": [],
    "frames": [
      {
        "images": 200,
        "complete": 200
      }
    ],
    "alerts": [],
    "marks": 87
  },
  {
    "fixture": "fixture-4",
    "decoded": 225,
    "decodeStarted": 300,
    "transfers": [],
    "fault": {},
    "local": [],
    "session": [],
    "frames": [],
    "alerts": [
      "Не удалось напечатать этикетки."
    ],
    "marks": 0
  },
  {
    "fixture": "fixture-5",
    "decoded": 3,
    "decodeStarted": 3,
    "transfers": [
      {
        "decoded": 1,
        "htmlLength": 11799
      },
      {
        "decoded": 3,
        "htmlLength": 23589
      }
    ],
    "fault": {},
    "local": [
      {
        "key": "wms440:/api/:672-tenant:672-user:672-document",
        "state": "complete",
        "remainingPaths": 0,
        "htmlLength": 11799
      }
    ],
    "session": [],
    "frames": [
      {
        "images": 1,
        "complete": 1
      },
      {
        "images": 2,
        "complete": 2
      }
    ],
    "alerts": [],
    "marks": 1
  },
  {
    "fixture": "fixture-6",
    "decoded": 1,
    "decodeStarted": 1,
    "transfers": [
      {
        "decoded": 1,
        "htmlLength": 11799
      }
    ],
    "fault": {
      "hold": true,
      "delayMs": 20
    },
    "local": [
      {
        "key": "wms440:/api/:672-tenant:672-user:672-document",
        "state": "complete",
        "remainingPaths": 0,
        "htmlLength": 11799
      }
    ],
    "session": [],
    "frames": [
      {
        "images": 1,
        "complete": 1
      }
    ],
    "alerts": [],
    "marks": 1
  },
  {
    "fixture": "fixture-7",
    "decoded": 200,
    "decodeStarted": 200,
    "transfers": [
      {
        "decoded": 200,
        "htmlLength": 2097083
      }
    ],
    "fault": {
      "hold": true,
      "delayMs": 20
    },
    "local": [
      {
        "key": "wms440:/api/:672-tenant:672-user:672-document",
        "state": "transferred",
        "remainingPaths": 199,
        "htmlLength": 2097083
      }
    ],
    "session": [],
    "frames": [
      {
        "images": 200,
        "complete": 200
      }
    ],
    "alerts": [],
    "marks": 1
  },
  {
    "fixture": "fixture-8",
    "decoded": 225,
    "decodeStarted": 300,
    "transfers": [],
    "fault": {
      "hold": true,
      "delayMs": 20
    },
    "local": [],
    "session": [],
    "frames": [],
    "alerts": [
      "Не удалось напечатать этикетки."
    ],
    "marks": 0
  },
  {
    "fixture": "fixture-9",
    "decoded": 225,
    "decodeStarted": 600,
    "transfers": [],
    "fault": {
      "decodeAt": null
    },
    "local": [],
    "session": [],
    "frames": [],
    "alerts": [
      "Не удалось напечатать этикетки."
    ],
    "marks": 0
  },
  {
    "fixture": "fixture-10",
    "decoded": 200,
    "decodeStarted": 200,
    "transfers": [
      {
        "decoded": 200,
        "htmlLength": 2097083
      }
    ],
    "fault": {
      "hold": true
    },
    "local": [
      {
        "key": "wms440:/api/:672-tenant:672-user:672-document",
        "state": "transferred",
        "remainingPaths": 192,
        "htmlLength": 2097083
      }
    ],
    "session": [],
    "frames": [
      {
        "images": 200,
        "complete": 200
      }
    ],
    "alerts": [],
    "marks": 8
  },
  {
    "fixture": "fixture-11",
    "decoded": 225,
    "decodeStarted": 300,
    "transfers": [],
    "fault": {
      "markAt": 150
    },
    "local": [],
    "session": [],
    "frames": [],
    "alerts": [
      "Не удалось напечатать этикетки."
    ],
    "marks": 0
  },
  {
    "fixture": "fixture-12",
    "decoded": 225,
    "decodeStarted": 300,
    "transfers": [],
    "fault": {
      "markAt": 150
    },
    "local": [],
    "session": [],
    "frames": [],
    "alerts": [
      "Не удалось напечатать этикетки."
    ],
    "marks": 0
  },
  {
    "fixture": "fixture-13",
    "decoded": 0,
    "decodeStarted": 0,
    "transfers": [],
    "fault": {},
    "local": [],
    "session": [],
    "frames": [],
    "alerts": [],
    "marks": 0
  },
  {
    "fixture": "fixture-14",
    "decoded": 1,
    "decodeStarted": 1,
    "transfers": [
      {
        "decoded": 1,
        "htmlLength": 11799
      }
    ],
    "fault": {},
    "local": [
      {
        "key": "wms440:/api/:672-tenant:672-user:672-document",
        "state": "complete",
        "remainingPaths": 0,
        "htmlLength": 11799
      }
    ],
    "session": [],
    "frames": [
      {
        "images": 1,
        "complete": 1
      }
    ],
    "alerts": [],
    "marks": 1
  }
]
```

## Диагностический повтор

[Run 37435750876](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37435750876)
проверил продукт `163259d412d2ef5ba2d49b831cd5c7da284245d9` с runner
`e49ca24c6d0db9d325f2ecb11974314b3b703846`. Helper инструментирует native decode:
он записывает имя/сообщение/код ошибки и параметры изображения, затем пробрасывает
**ту же ошибку**. Native результат, fault, timeout и assertions не заменяются.
Запуск ограничен `inbound 300|C5 decode|C7/C8|C8 mark`; успешные серии 200,
C3/C6/C10, возврат 300 с уже зафиксированным тем же состоянием и WMS-673 не повторялись.
4 tests: **0 passed / 4 failed / 0 skipped / 0 cancelled**, 149248.254904 ms.
`672=1`, `673-renderer=skipped`, `673=skipped`.

Artifact `11399591837`, `wms-print-contract-e49ca24c6d0db9d325f2ecb11974314b3b703846`,
1,611,345 bytes, retention 14 дней: скачан и прочитан. Проверка source pin PASS;
SHA256 обоих manifest и frozen файлов совпадает с первым run.

Первичная native ошибка в **каждой из четырёх fixtures**, без искусственного
fault на 226-й этикетке (в C5 — после снятия decodeAt=150):

```json
{
  "name": "EncodingError",
  "message": "The source image cannot be decoded.",
  "code": 0,
  "srcLength": 10242,
  "complete": true,
  "width": 836,
  "height": 356,
  "barcode": "INB-000000000226"
}
```

На закрытии каждой fixture `decoded=225`, `transfers=[]`, `local=[]`,
`frames=[]`, Alert `Не удалось напечатать этикетки.`; decodeStarted=300
(600 у C5 с двумя подготовками). Фактических POST mark-label-printed **0**.
Нет зависшего mark callback: первой передачи и самой 150-й отметки не было.

Это подтверждённый **продуктовый отказ подготовки 300** в реальном remote
Chromium, R1/R3 не выполнены в данной среде. Последующий Timeout 30000ms в
`transfer()` — вторичное ожидание harness после уже произошедшей ошибки.
Продуктовый catch/cleanup скрывает DOMException за общим текстом, потому что
исключение не обязано быть `instanceof Error`; этот вывод основан на коде
`printBarcodeLabel.ts`/`FfInboundRequestView.tsx` и сохранённом native событии.
Это не доказательство проблемы самих данных CODE128 и не основание чинить
продукт в роли тестировщика. Есть правдоподобная, но **не доказанная** гипотеза
лимита памяти параллельного decode: 836×356×4×225=267854400 bytes,
а с 226-й картинкой 269044864 bytes, пересечение 256 MiB. Лимит Chromium,
PNG-валидность 226 и влияние deviceScaleFactor=4 отдельно не проверялись;
уверенно установлена только приведённая native причина и её последствия.

C5: защита **0 лент / 0 отметок / ошибка видна / ожидание снято** прошла;
полный C5 FAIL из-за отказа исправленной серии 300. C6 полностью PASS первого run.
C7 потеря ответа/resume, C8 reload/отсутствие автоматического дубликата и retry
**НЕ ПРОВЕРЕНЫ**: замороженные тесты остановились до первой передачи.
Сохранившуюся попытку на 200 нельзя выдавать за приёмку recovery 300.
PDF 300, его размеры и декодирование первой/средней/последней страницы не получены.

### Отдельный остановленный запуск

[Run 37435661995](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37435661995),
runner `ed9ed0273`, остановлен source manifest comparison до установки и тестов:
параллельный WMS-673 commit `6b272491d` изменил `frontend/src/screens/v2/fbsUx.ts`.
Это корректно сработавшая защита точного исходника, не продуктовый RED/PASS.
Последний workflow сохраняет helper runner, checkout делает **только на GitHub
runner** на точный immutable source, восстанавливает единственный helper,
проверяет product diff/tree и пишет отдельно runner/source. Общий checkout
и изменения другого исполнителя не откатывались.

### Точный вывод диагностического node:test

```text
✖ C1/C2 inbound 300: one complete ordered 58x40 tape, real PDF and readable samples (36731.556265ms)
✖ C5 decode failure at label 150: no transfer/early marks, visible error, explicit corrected retry (40107.01969ms)
✖ C7/C8 response lost after transfer: restore source/attempt across reload before another external action (35909.20444ms)
✖ C8 mark failure retry repairs original attempt without silently printing another tape (35913.187779ms)
ℹ tests 4
ℹ suites 0
ℹ pass 0
ℹ fail 4
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 149248.254904

✖ failing tests:

test at tests-e2e/wms672-box-labels.test.mjs:134:5
✖ C1/C2 inbound 300: one complete ordered 58x40 tape, real PDF and readable samples (36731.556265ms)
  page.waitForFunction: Timeout 30000ms exceeded.
      at transfer (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:109:16)
      at TestContext.<anonymous> (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:139:28) {
    name: 'TimeoutError'
  }

test at tests-e2e/wms672-box-labels.test.mjs:227:1
✖ C5 decode failure at label 150: no transfer/early marks, visible error, explicit corrected retry (40107.01969ms)
  page.waitForFunction: Timeout 30000ms exceeded.
      at transfer (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:109:16)
      at TestContext.<anonymous> (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:240:25) {
    name: 'TimeoutError'
  }

test at tests-e2e/wms672-box-labels.test.mjs:261:1
✖ C7/C8 response lost after transfer: restore source/attempt across reload before another external action (35909.20444ms)
  page.waitForFunction: Timeout 30000ms exceeded.
      at transfer (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:109:16)
      at TestContext.<anonymous> (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:265:25) {
    name: 'TimeoutError'
  }

test at tests-e2e/wms672-box-labels.test.mjs:291:1
✖ C8 mark failure retry repairs original attempt without silently printing another tape (35913.187779ms)
  page.waitForFunction: Timeout 30000ms exceeded.
      at transfer (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:109:16)
      at TestContext.<anonymous> (/home/runner/work/WMS/WMS/frontend/tests-e2e/wms672-box-labels.test.mjs:295:11) {
    name: 'TimeoutError'
  }
```

## Итог для ведущего

**WMS-672 не принята: серии 200 и C6 PASS, серия 300 имеет реальный decode FAIL;
C5 частично подтверждена, полный C5 FAIL; C7/C8 не достигнуты.** Продуктовый
SHA остаётся `163259d412d2ef5ba2d49b831cd5c7da284245d9` без правок тестировщика.
Разработчику передать native событие 226, точные runner/source SHA и оба artifact,
чтобы устранить первичный отказ до следующего целевого recovery/PDF прогона.
Самостоятельно продукт не исправлялся, frozen ожидания не ослаблялись.

Локальный Mac-браузер, кабинет секретов, live API, Telegram, физическая печать,
агенты и навыки не использовались. Полный CI/ревью/приёмка/merge/deploy не заявлены.
Ограниченные probe commits опубликованы до runs; этот proof report сохраняется
отдельным commit и push, его окончательный проверенный SHA передаётся в ответе.

