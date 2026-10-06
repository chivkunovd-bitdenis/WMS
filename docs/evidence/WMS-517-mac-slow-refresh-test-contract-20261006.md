# WMS-517: контракт задержанного обновления Mac helper до исправления

Отдельный тестировщик продолжил SC17 после независимого P1 ревью.
Product bytes проверены против `5376d15cf9be7489fb1ac28a3c5723589724c05c`;
helper SHA256 `79fba6821a43900f5a1ff1de25c9a40cd6d17a4cbac08293fd688f740d3ac19c`.
Независимое настоящее React/MUI воспроизведение опубликовано в
`d49f2319330c537ac376a8a9444a06a9bdb779bb`,
`docs/evidence/WMS-517-mac-review.test.tsx` и
`docs/evidence/WMS-517-mac-real-screen-review-20261006.txt`:
без задержки PASS; успешный GET с700ms задержкой оставляет Refresh disabled
после fixed400ms ожидания clearFilters, и helper преждевременно отказывает.

## Новый frozen тест

`scripts/ops/tests/wms517-mac-dom.test.cjs::SC17 default DOM adapter waits for successful 700ms filter refresh before selecting and opening certificate dialog`

Тест использует настоящий product DOM adapter и прежний jsdom screen fixture.
Управляемая граница эмулирует уже существующий автоматический React refresh:
input changes запускают успешные GET, кнопка Refresh disabled до завершения
этих GET. Все ответы корректные; нет malformed source, session switch,
ошибки API или отсутствующего module. Ожидается штатная подготовка всех305
точных IDs и ровно один certificate dialog,0signature/create/submit.
Нельзя добавлять новый продуктовый запрет или требовать повторного запуска;
достаточно ограниченно дождаться завершения обычного обновления.

Первоначальный109 набор сохранён: его assertions/expectations не изменены.
DOM fixture выделена в общую функцию, прежний zero-latency test по-прежнему
вызывает её с нулевой задержкой. Новый case использует700ms и сохраняет настоящий
таймер ожидания помощника. Искусственного изменения product для RED не нужно.
Ожидания null/Infinity/undefined unsafe launcher cases прежние; к именам добавлен
уникальный scenario index, потому что JSON.stringify давал одинаковые имена.

## Выполненная проверка до исправления

```
WMS517_MAC_SOURCE_DIR=/Users/deniscivkunov/Projects/WMS/.worktrees/wms517-dynamicmac-independent-review/scripts/ops node --test --test-reporter=tap scripts/ops/tests/wms517-sold-kiz-filter.test.cjs scripts/ops/tests/wms517-mac-launcher.test.cjs scripts/ops/tests/wms517-mac-dom.test.cjs
```

Результат **110 tests:109 PASS,1 FAIL**, exit1. Падает только новый700ms case:
`SoldKizFilterError: Штатная кнопка обновления реестра недоступна.`
Контроль прежних109 GREEN; строго проверены110 уникальных TAP names.
Полный журнал: `WMS-517-mac-slow-refresh-test-red-20261006.tap` рядом.

После исправления стандартная Node-команда без WMS517_MAC_SOURCE_DIR должна
дать110 PASS. `frontend` jsdom26 установлен в существующих root dependencies;
новый checkout/node_modules/temp bundle не создавался. Product, frontend,
CI/guard registry не изменены тестировщиком. Реальные браузеры, сертификаты,
ключи/PIN, production и внешние операции не запускались. Деплой/приёмка этим
контрактом не объявляются и не требуют ожидания физической подписи Виталика.
