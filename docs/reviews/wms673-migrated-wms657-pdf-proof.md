# WMS-673: фактический удалённый прогон мигрированного WMS-657

06.10.2026. Отдельный TESTER Sol 6.1 по прямому поручению владельца.
**PASS: точный замороженный файл WMS-657 выполнил все C1–C6,
6 passed / 0 failed / 0 skipped, exit 0.** C4–C6 действительно использовали
Google Chrome на GitHub Linux; C5/C6 создали настоящие PDF и прочитали их
через Poppler. Оба отрицательных контроля C5 выполнены внутри успешного теста.
Это закрывает назначенный удалённый тестовый этап, но не приёмку или выпуск.

## Источники, запуск и сохранённые доказательства

Прочитаны полный локальный AGENTS.md и обновлённый `origin/etalon:AGENTS.md`
из `954862b718f9f2f1faefb2f00ad2fef72a6e1929`, полный мигрированный файл,
[решение аналитика](wms673-wms657-authorized-contract-migration.md)
из `379f6f79cf24126cf4ef437831d504bd22b0f11a`,
[передача тестировщика](wms673-wms657-contract-migration-tester.md)
из `76f71776f403d0bdda07d521738281392e2b12ce` и полный
[отчёт Astra](wms673-astra-bc272386.md) из `ff559d760`.
Исторические 3 actual PDF PASS WMS-673 прочитаны, но не запускались повторно
и не подменяют новые результаты WMS-657.

Единственный новый workflow —
[wms657-673-contract-proof.yml](../../.github/workflows/wms657-673-contract-proof.yml).
Его push-trigger ограничен собственным путём и веткой
`codex/wms672-673-analyst-20261006`; workflow WMS-672 и его mjs не менялись.

- Источник всего продукта и тестов: **`76f71776f403d0bdda07d521738281392e2b12ce`**.
  Включает продукт bc272386, числовой fallback 6b272491d и миграцию WMS-657.
- Отдельный commit workflow runner: **`c86c9d1f14f78db5cc27eeac48d6ad5dd9f14e32`**.
- [GitHub run 37436845508](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37436845508):
  `completed / success`; job 112180644172; 08:33:01–08:34:07 UTC.
- [Исходный лог job](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37436845508/job/112180644172).
- [Артефакт 11399249395](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37436845508/artifacts/11399249395):
  `wms657-673-proof-c86c9d1f14f78db5cc27eeac48d6ad5dd9f14e32`, 421362 bytes;
  GitHub digest `sha256:f2d90eaeb28c8f4f8cb301aa4caf23c4ea5f0276c428e90a23a3686553a6bed9`.
  Проверен через API и скачан для независимой сверки. Срок хранения —
  до **20.10.2026 08:34:04 UTC**; ссылки могут требовать доступ к репозиторию.

Артефакт содержит оба PDF, пять исходных HTML (три geometry и два PDF),
три настоящих geometry JSON, raw DOM Chrome, два raw bbox XML Poppler,
команды процессов и stderr Chrome, `tests.log`, `results.json`, exit code,
версии среды, npm-ci.log, манифесты, контрольные суммы и точный workflow.
Локальная скачанная копия использована только для проверки; итоговый отчёт
и запускающий workflow сохраняются в Git, доказательства опубликованы в GitHub.

## Как запускался неизменённый файл

Среда: ubuntu-24.04 / Linux x86_64; Node **24.21.0**, npm **11.19.0**,
Google Chrome **154.0.8037.57**, Poppler pdftotext **24.02.0**, Vitest **3.2.6**.
`npm ci` выполнялся только на удалённом runner. Chrome — `/usr/bin/google-chrome`.

```sh
cd frontend
node node_modules/vitest/vitest.mjs run \
  src/screens/v2/fbsPickingListPrint.wms657.test.ts \
  --maxWorkers=1 --no-file-parallelism \
  --reporter=verbose --reporter=json --outputFile.json="$RUNNER_TEMP/wms657-proof/results.json"
```

Нет фильтра имён, исключённых тестов, новых skip или изменения timeout.
Использована исходная конфигурация с `environment: 'node'`. Сам файл,
assertions, входы, reader и параметры Chrome не менялись.
Внешний job-limit 10 минут не меняет timeout тестов 45/60 секунд.

Для сохранения файлов, которые тест удаляет в `finally`, workflow создаёт
собственный короткий `observe.cjs` вне source tree и подключает через
`NODE_OPTIONS=--require=...`. Он вызывает исходные `execFileSync`, `spawn`,
`rmSync`, сохраняет их настоящие результаты/логи и копирует HTML/PDF перед
исходным удалением. Возвращаемые значения, входы и исходная очистка сохранены;
Buffer, PDFDocument, координаты и проверки не подменяются. Исправление
совместимости reader не понадобилось. Сохранённая копия observer входит в артефакт.

До запуска runner переключается detached на точный source SHA. Скачанные
`source.manifest` и `checkout.manifest` побайтно совпали с локальным
`git ls-tree -r 76f71776f403d0bdda07d521738281392e2b12ce`: проверено всё дерево,
включая весь продукт и тесты, а не только один печатный файл. SHA256 манифеста:
`5eb01e698f310baa372e8fc680fa33e8b63d1a01093d417e33a8afdac59eecbc`.
До/после запуска `git diff --exit-code` не обнаружил tracked-изменений.
Контрольные суммы before/after совпали; независимо сверены с Git-объектами source:

| Файл | SHA256 |
|---|---|
| fbsPickingListPrint.wms657.test.ts | `382486dc2bc08cf8cb400c3e362e24ae313d90e0c61817ed6213ff2f69ad98c2` |
| fbsUx.ts | `974d37bfdb121fbdc43eb67ef9aae11ebd681d058ae17e92a1398104c5875730` |
| vitest.config.ts | `c5a189e0a84e5bd969515013fb33ecf6c5923f9e551fb9f4c4c5971247b30cda` |
| package-lock.json | `4ec9fd6b9291d52f2c3534bc3fb4ebbfd24a9d029f3d3d01127e43404c01984c` |

## Фактический результат

Сверены `tests.log`, `results.json` и `test-exit-code.txt`: 6 total, 6 passed,
0 failed, 0 pending, success=true, exit 0; duration **11.22 s**.

| Проверка | Результат | Подтверждённое поведение |
|---|---|---|
| C1 | PASS, 4 ms | Полный «Универсальный», размер 78 px, перенос разрешён, Цвет после Размера. |
| C2 | PASS, 3 ms | 11 колонок, все контрольные поля в собственных ячейках, одинаковый повторный HTML, вход не мутирует. |
| C3 | PASS, 2 ms | Короткий 46 и прочерк в размере, по 11 ячеек в двух строках. |
| C4 | PASS, 7934 ms | Настоящая геометрия длинной строки: 11 колонок, полное содержимое внутри границ, заголовки совпадают, соседние ячейки не перекрываются. Размер занимает 3 строки внутри своей ячейки. |
| C5 | PASS, 1441 ms | Настоящий одностраничный PDF A4 landscape; все поля в своих колонках/строке, включая цвет-прочерк. Оба отрицательных контроля сработали. |
| C6 | PASS, 1395 ms | 34 строки, настоящий PDF на 3 страницах A4 landscape, все значения принадлежат своей строке/странице, нет потерь и выхода за границы. |

C5 сохраняет две повреждённые копии прочитанного text report только в памяти:
удаление последнего фрагмента размера обязано вызвать `PDF потерял`,
а смещение `xMax` первого фрагмента на 2 pt за границу — `вышло за границу колонки`.
Оба `toThrow` находятся в неизменённом C5 после основных PDF assertions;
PASS полного C5 подтверждает их выполнение. Повреждённый PDF вместо
реального рендера не подавался. C6 проверяет каждую из 34 строк и три полных
«Универсальный»; геометрия короткого 46 и прочерка — одна строка.

Файлы в артефакте связаны сохранёнными командами Chrome/Poppler:

| Доказательство | Файл | SHA256 |
|---|---|---|
| C4 geometry | io-2919-1.geometry.json | `b048ef881d0e8d394981caa9f945bb81c59a1e942d3a1434a0a486355c514aa6` |
| C5 geometry | io-2919-2.geometry.json | `b048ef881d0e8d394981caa9f945bb81c59a1e942d3a1434a0a486355c514aa6` |
| C5 PDF, 40654 bytes | wms657-pdf-PtBF9H/picking-list.pdf | `1b36a8963c522d7a7a090818166d042762fd2553578587301a2154c5d64142ee` |
| C5 HTML | wms657-pdf-PtBF9H/picking-list.html | `35d861e35c580d46f193a170774e50666dd352956dc860ac9441709df7f4ab63` |
| C5 raw bbox, 1 страница | io-2919-4.raw.txt | `8e4b1c14170dc9fe3965bc278aa27ea2b3fa33b63bc744e44865d5a6630d8139` |
| C6 geometry | io-2919-5.geometry.json | `a7769563f444092b0ce0437118246c0afb60c94c48bb2a3c4573f3a1af09f3b2` |
| C6 PDF, 179052 bytes | wms657-pdf-fYXHhN/picking-list.pdf | `7247de7d245bea79b7613838c9e820f2d8dad2c664ba9b8378f4ead63cde87f6` |
| C6 HTML | wms657-pdf-fYXHhN/picking-list.html | `e22de7e4455a88b2c13e0a0669e94f36f3e7e0f84130c7b0890ff1925467eda6` |
| C6 raw bbox, 3 страницы | io-2919-7.raw.txt | `e0153f0fea4da79c7beca521cae933d69b4f7716142ac7f257e9e92553dc5c3a` |

Все три geometry report содержат true для tableWithinPage, allCellContentFits,
headersAligned, neighboringCellsDoNotOverlap, rowsDoNotOverlap. C4/C5 имеют
одинаковые геометрические метрики, но разные HTML и команды сохранены отдельно.
Raw лог содержит сообщения Chrome о недоступном D-Bus; реальный PDF,
координаты и все проверки завершились успешно, сообщений об отказе harness нет.

## Передача и границы заключения

Удалённые C1–C6 мигрированного WMS-657 приняты как тестовый PASS точного source.
Изменения этого исполнителя ограничены новым workflow и данным отчётом.
Продукт, frozen tests, чужие helper, WMS-672, требования и checker не менялись.
Навыки, агенты, локальный браузер, Playwright, live, физическая печать и деплой
не использовались; зависимости локально не устанавливались.

Известные препятствия документационной проверки — отсутствующий WMS-657.md
и 10 некорректных ссылок WMS-673 — оставлены аналитику, здесь не исправлялись
и не объявлены прошедшими. Приёмка аналитика, независимое ревью миграции/fallback
и полный CI итогового SHA остаются отдельными этапами. Этот workflow не запускает
широкий CI и не подтверждает выпуск. Main и стенд данным исполнителем не менялись.
