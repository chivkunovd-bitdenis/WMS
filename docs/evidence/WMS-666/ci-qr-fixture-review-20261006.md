# WMS-666: расследование QR в frontend CI, 06.10.2026

Исполнитель Sol 6.1, отдельный постоянный worktree
`.worktrees/wms666-ci-qr-finish-20261006`, ветка
`codex/wms666-ci-qr-finish-20261006`, база `5ddd09aac` общей сборки.
Зона: два красных случая существующего замороженного DOM-контракта 666.
Требования 666/681/683 и применимые owner/failure cases прочитаны.

CI run `37460067342`, job `112257135369`, head `066a5e95c`:
mixed WB → Ozon → WB падает на отсутствии назначения Ozon после первого WB;
standalone с изменёнными галками ожидает три задания, получает ноль.
Frontend между этим SHA и базой расследования не менялся.

Первый локальный прогон на Node `24.13.1`: исходный файл без изменений,
**17/17 PASS**, 100.98с (96.59с импорт, 3.55с сами проверки).
Поэтому дефект продукта пока не подтверждён. CI использует Node 20;
подготовлен отдельный прогон на Node `20.20.2`.

Путь продукта: `makePackingScanDeps.preload` загружает `qr_asset`, читает
`Response.blob()` через браузерный `FileReader`, затем отправляет подготовленные
байты через `dispatchPreparedQrInKiosk` после атомарного claim.
Fixture возвращает `new Response(new Blob(['png']))`. В отдельном минимальном
Node/jsdom-пробнике Node Response сериализует jsdom Blob как `[object Blob]`,
возвращает Blob другого окружения; jsdom FileReader отклоняет его.
Точный прогон на Node `20.20.2` воспроизвёл **15 PASS / 2 FAIL** исходного файла:
те же mixed строка 459 и standalone строка 504, 11.36с.
Команда: `npm exec --yes --package=node@20 -- node node_modules/vitest/vitest.mjs run src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx --no-file-parallelism`.

Временная диагностическая копия этих двух тестов добавляла только журналирование
вызова `FileReader.readAsDataURL` и полученных HTTP-событий, затем была удалена.
В обоих случаях факт: `sameWindowBlob: false`, `constructor: 'Blob'`;
точная ошибка:

```text
TypeError: Failed to execute 'readAsDataURL' on 'FileReader': parameter 1 is not of type 'Blob'.
```

Последовательность обоих случаев: POST `scan-auto-print` с актуальными галками,
GET `/assets/wms666-wb.png`, ошибка FileReader; запроса `print-claim` и отправки
QR нет. После неё WB закономерно остаётся незавершённым и следующий Ozon-скан
не получает назначение в короб. Бизнес-код работает с браузерным Response/Blob;
ошибка возникла только из смешивания Node Response и jsdom FileReader в fixture.

Исправление только ответа asset передано отдельному тестировщику `priority_663`:
`blob()` тестового ответа должен вернуть Blob текущей браузерной среды.
Ожидания, состав 17 тестов, продукт и физическая печать не меняются.


Исходное доказательство опубликовано как `cfc67dca75261146ee81fbeaa71f2e62f057b7a9`.
Для общей сборки использовать этот конечный путь; прежний reviews-путь
не входит в разрешённую область scope-контракта 666. Исходная ветка
служит доказательством расследования; её ancestry в общую сборку не переносится.
