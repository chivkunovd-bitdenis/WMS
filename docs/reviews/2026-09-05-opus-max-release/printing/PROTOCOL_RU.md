# WMS-371 — проверка цифрового документа печати

Дата: 06.09.2026. Проверены действующие генераторы товарной этикетки
`buildProductThermalLabelDocument` и ленты `buildMarkingTapeDocument`.
Каждому переданы три одинаковые этикетки стандартного размера 58×40 мм.
Исходные данные полностью синтетические: «Тестовый товар WMS-371», артикул
`TEST-WMS-371`, строка ШК `TEST371000001`, «Тестовый селлер». Изображение полос
также тестовое SVG: проверялась пагинация документа, а не считываемость баркода.
Полный воспроизводящий вход находится в `generate-print-evidence.ts`.

Команды выполнялись из корня WMS:

```sh
frontend/node_modules/.bin/esbuild docs/reviews/2026-09-05-opus-max-release/printing/generate-print-evidence.ts --bundle --platform=node --format=cjs --outfile=/tmp/wms371-document-check.cjs
node /tmp/wms371-document-check.cjs
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --disable-background-networking --no-first-run --user-data-dir=/tmp/wms371-chrome-evidence-product --no-pdf-header-footer --print-to-pdf=/tmp/wms371-product.pdf file:///tmp/wms371-product.html
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --disable-background-networking --no-first-run --user-data-dir=/tmp/wms371-chrome-evidence-tape --no-pdf-header-footer --print-to-pdf=/tmp/wms371-tape.pdf file:///tmp/wms371-tape.html
```

Оба PDF перечитаны PyMuPDF: каждый содержит ровно **3 страницы**, на каждой
найден текст тестового товара; пустых страниц нет. Размер страницы в записанном
Chrome PDF после округления — 57,83×39,88 мм, при CSS `@page size: 58mm 40mm`.
PDF и входные HTML сохранены рядом с этим протоколом. Изолированные процессы
Chrome после проверки завершены.

Пропуск этикетки в этих двух цифровых документах не воспроизведён. Физический
принтер, его модель, драйвер, размер фактической ленты и калибровка не проверялись.
Это доказательство ограничено указанными входами и генераторами; закрывать
WMS-371 или приписывать пропуск настройкам принтера на его основании нельзя.
Изменения CSS печати ради предположительной причины не выполнялись.
