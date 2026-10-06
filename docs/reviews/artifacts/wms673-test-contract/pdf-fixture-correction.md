# WMS-673: исправление чтения сохранённого PDF

06.10.2026. Узкий результат тестировщика: **3 фактических PDF-теста PASS**,
без повторного браузерного рендера. Это не продуктовая приёмка, полный CI или выпуск.

## Исправление и сохранность контракта

В `wms673PrintRenderer.ts::renderPdf` Node Buffer копируется через
`new Uint8Array(readFileSync(output))` перед настоящим `PDFDocument.load`.
Это устраняет несовместимость instanceof между Node и jsdom; содержимое PDF
не преобразуется в синтетические данные, геометрия и PDF assertions не меняются.

Исходный контракт: `5dab0dbaf0ca5184a116482da336f3dba8ef447b`.
Git blob PDF-теста до/после: `16149d68b47d2b41d595044872c21aa1235ec0f4`.
SHA256 теста до/после:
`77bb4d1b71efc40ad61eefbd35122d4ca8413d84fae77f5afe828b37c7ac797d`.
Все assertions, названия, параметры и skip conditions побайтно сохранены.
Blob helper до: `3ea7f4cd69ad22888d80c99f34fd989cb6cec7a2`;
после: `694b455fcb0647186b36a556a6141439a65c2b32`.
SHA256 helper до:
`8da03e1719becbcc0581a02250e8a5f9d2276b9d9d589bfd14e218f255f25454`;
после:
`5d9d1d7fa99a3f43aa102719190587a77269f07577b8fe57780047e612c7ac9d`.

## Источник и геометрия

Использованы уже скачанные реальные артефакты
[run 37431998239](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37431998239),
source SHA `3a2a0e16b850ce4336e5f3d48ee138a9f18f9ee2`,
с реализацией `bc2723866b4a0671c510124c39426058f201d2da`.
Artifact id `11396964277`, срок хранения 14 дней. Директория:
`/tmp/wms-print-contract-37431998239/wms-print-contract-3a2a0e16b850ce4336e5f3d48ee138a9f18f9ee2/673`.
Чтение каждого artifact проверяет побайтное совпадение его HTML с фактическим
`htmlFor(1)` или `htmlFor(34)` неизменённого контракта.

Ключ HTML контрольного/длинного ввода:
`e1d03d1dbe516cb437134a3853b1c166ba62d6d327780c8bf481c4f3bec21cfb`.
PDF SHA256:
`3929a6f46f1d120a0ca5b2ebd40a17cac5c8c1b703d8e4efe03b86ca1de8e0f9`.
Geometry SHA256:
`9dd6d11c32ca6405eb709845489720ed1defdb33ec13aa0309d59fe280125060`.

Ключ HTML 34 строк:
`923894384d3be770e8a560d2b2557d8dc22a27f8086630617c5c4ca37517adb1`.
PDF SHA256:
`7822751d441241d09e5be06599d83c63377111564ab6db9ca6bf75af381f8bc5`.
Geometry SHA256:
`5a0bb6d186204f11c81a8990ab4db3e0738913435d7499943a55f4d97a6cbf06`.

Оба исходных geometry JSON сохранены рядом с единственным добавлением конечного
переноса строки средствами apply_patch; значения и прочие байты совпадают.
SHA256 сохранённых копий для 1/34 строк соответственно:
`16bfc3d8f2bf32538d4eb2a65a0b712a046160f899bc9efd11453996e42cad62`,
`980a066fddb49211b4328b97ebdd9b2d52198dc2fc42e3ab0c6ee05b8f75fe14`.
Запуск использовал исходные remote JSON, а не эти копии. Они содержат
11 границ колонок, выравнивание заголовков, фиксированные ширины
28/54/116/62/62 px, размер 78 px/20 px, полные значения размера и цвета
для 1/34 строк, признаки отсутствия наложений и выхода за границы.
Неизменённые тесты дополнительно читают настоящие PDF через pdf-lib и
`pdftotext -bbox-layout`: проверяют A4 landscape, границы всех слов,
повтор заголовка «РАЗМЕР» на каждой странице и сохранность каждой строки,
цвета/размера/идентификатора/заказа/стикера на одной странице и в одной строке.
Прохождение этих assertions подтверждено запуском, а не придумано из JSON.

## Ограниченный запуск

Из frontend, один worker, без браузера и установки зависимостей:

```sh
WMS673_RENDERED_ARTIFACTS_DIR=/tmp/wms-print-contract-37431998239/wms-print-contract-3a2a0e16b850ce4336e5f3d48ee138a9f18f9ee2/673 NODE_OPTIONS=--max-old-space-size=768 ./node_modules/.bin/vitest run src/screens/v2/fbsPickingColor.wms673.pdf.test.ts --maxWorkers=1 --no-file-parallelism --reporter=verbose -t 'externally rendered actual PDF|real renderer keeps|multipage PDF'
```

Exit 0; 3 passed, 2 skipped по целевому фильтру (оба HTML-input теста не запускались).
Все три фактических PDF-теста выполнены, не skipped. Duration 1.08 s,
tests 242 ms. Контроль A4 172 ms, длинная строка 21 ms, многостраничность 48 ms.
До исправления в удалённом run те же три PDF-кейса падали на TypeError NaN
до бизнес-assertions; [исходный лог](../../../evidence/WMS-672/test-contract/remote-pdf-673.log).

## Передача ведущему

Независимому Astra high проверить только этот helper diff, неизменность
PDF-контракта относительно 5dab и происхождение приложенных доказательств.
Ревью здесь не выполнялось: прямое поручение запрещает запуск агентов.
Продукт, remote CI workflow, старые WMS-657 tests и чужие файлы не менялись.
Три старых семантических FAIL WMS-657 (авторизованные 11 колонок против старых 10)
остаются отдельной работой аналитика; их ожидания здесь не исправлялись.
Приёмка, новый remote CI, merge и деплой не заявляются.
