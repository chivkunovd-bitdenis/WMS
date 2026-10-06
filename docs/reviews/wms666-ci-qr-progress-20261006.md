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

## Независимое ревью форматирования тестов WMS-662/WMS-672

По поручению ведущего отдельная сессия Sol 6.1 проверила техническое
форматирование **5ddd09aac4df17e7ecdefaf1625462c05f8039ce** против контракта
**c466c65b850dd87481be5da88b99bcfaa4087414**.

PASS: `ast.dump(ast.parse(source), include_attributes=False)` полностью
одинаков до/после для обоих файлов. Отдельно сравнен каждый `ast.Assert`:
7 assertions в `test_wms662_live_delivery_substatuses.py` и 21 в
`test_wms672_box_label_scope.py`; ожидания и состав сохранены. Прочитанный diff
меняет отступы, переносы строк, пустую строку и перенос комментария.

SHA256 синтаксического дерева совпадают с сохранённым format-only proof:

- 662: `fb3439263ff402954392fd837f744c13f71c06572d3b124dd4128e9299a674e9`;
- 672: `63e90339badf547e09e586b7b03dd722ac98c8cbe1225b809d0ec85d5407c834`.

Это независимая проверка форматирования и неизменности контракта,
не полный продуктовый review, приёмка, CI или доказательство деплоя.
