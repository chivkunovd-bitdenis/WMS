# WMS-517: frozen контракт Mac-подготовки, 06.10.2026

Это checkpoint отдельного тестировщика до разработки по R26/R27 и SC17.
Основа требований: `8b3b45b10359711047a370f57fde528a0e57db1f`.
Исторический bundle: `c42f4d318c094253ce82ba6947c80a342cda57e0`.
Тестировщик не изменял helper, launcher, backend, frontend, CI или guard registry.
Chrome, Apple Events, реальные сертификаты/PIN, production и внешние операции не запускались.
SC18 остаётся ручной проверкой на Mac Виталика после реализации/ревью.

## Проверенный RED

`node scripts/ops/tests/wms517-replay-historical-mac-tests.cjs --r27`
исполняет новые тесты против точных исторических product blobs в временной
тестовой среде, затем удаляет её. Результат: **109 тестов, 78 PASS, 31 FAIL**, exit 1.
Это содержательный business RED, а не `MODULE_NOT_FOUND`:

- dry-run 81/84/305/501 получает `targetCount=80`, ожидается соответственно 81/84/305/501;
- default DOM adapter на 305 строках открывает диалог только для80, проверка получает `80 !== 305`;
- исчезнувший прежнийID останавливает подготовку, хотя сервер возвращает пригодные новые строки;
- formerID с возвратом/active claim/withdrawn/price error не позволяет подготовить оставшийся пригодный состав;
- launcher отвергает unsigned/unsent certificate dialog с положительным числом1/81/84/305;
- неполная конечная страница допускается старым reader вместо безопасного отказа.

API/DOM doubles проверяют полный точный состав всех страниц; GET-only preparation;
очистку двух дат, товара и поиска; только невыведенные; динамический N;0 без ready/dialog;
duplicate, partial pages, wrong origin/tenant/seller/role/permission, logout/session switch;
DOM count/dialog confirmation; отсутствие CIS/token в результате. Helper не читает
WB report и не вычисляет стоимость: API fixture представляет уже проверенный сервером
sales-backed реестр. Возврат здесь моделируется исчезновением строки из этого реестра,
а active claim — строкой в состоянии awaiting_crpt с operation_id.

## Сохранение исторических106

`node scripts/ops/tests/wms517-replay-historical-mac-tests.cjs`
восстанавливает все три исходных тестовых файла и нужные product/runbook blobs
только из pinned c42f4d3 во временной тестовой среде. **106/106 PASS**, exit0.
Оригинальные тесты не переписаны и не удалены из истории.
Это воспроизводимость прежнего согласованного контракта; она не принимает R27.

Текущий launcher contract сохраняет прежние проверки точного домена/tab identity,
Automation/probe failures, sanitization, bounded polling, отсутствия retry,
проверки embedded bytes, generator reproducibility, executable bit и JXA focus.
Его80 заменено на84 как один динамический пример. Прежние79/81 как запрещённые
counts заменены на0/-1/fraction/string/null/undefined/Infinity; отдельно1/80/81/84/305
теперь успешны. Прежний hardcoded80 allowlist и четырёх-CIS standalonehelper остаются
только в историческом replay, поскольку новая цель — серверный состав всех продаж.
В текущий выпуск старый product/history целиком не переносится.

## Интерфейс разработчику

Product-файлы должны появиться в `scripts/ops/` с прежними именами:
`avpack-sold-kiz-filter.js`, `avpack-macos-launcher.js`,
`build-avpack-macos-command.cjs`, `avpack-sold-kiz.command`.
Default command должен быть executable и содержать точные новые helper/launcher bytes.

Сохраняется `AvpackSoldKizFilter.createHelper({root,ui}).run({mode})` и CommonJS export
`createHelper`. `mode` — dry-run/execute; readonly dry-run не меняет UI/transport.
UI boundary: `inspectSelection()`, `clearFilters()` (execute до refresh),
`refreshSelectAllAndOpen(N, assertCurrentSession)`, `rollbackPreparation()`.
При обычном вызове без ui используется product DOM adapter; отдельный jsdom тест
проверяет реальные очищенные поля, массовый выбор страниц и открытие dialog.
Никакой обязательной архитектуры fetch interception контракт не навязывает;
ошибка требует отката своей подготовки, а свежие server IDs не заменяются снимком.
Уже выбранный чужой набор не расширяется молча.

Успех: ready в dry-run либо certificate_dialog_open в execute, положительное целое
`targetCount`, `noSend:true`, `signed:false`, `sent:false`, без secret/CIS.
Для0 допускается понятный отказ либо unsigned/unsent `status:empty`, `targetCount:0`;
ready/dialog не допускаются. Нет самостоятельных signatures/create/submit.
При новом составе между чтением/выбором нельзя сообщать stale success: отказ/refresh
допустим, но принятие старого набора при прежнем количестве запрещено. Серверный
fresh recheck перед созданием operation остаётся штатным WMS механизмом.

Launcher: прежний `Wms665MacLauncher.launch({chrome,helperSource,wait,maxPolls})`
и CommonJS `launch`, синхронный JXA; тот же run marker сохраняется для безопасного
повторного запуска. Только positive integer dialog count принимается как подготовка.
Сертификат выбирает и полную подпись подтверждает Виталик.

После реализации запуск из root checkout/worktree:

```
node --test scripts/ops/tests/wms517-sold-kiz-filter.test.cjs scripts/ops/tests/wms517-mac-launcher.test.cjs scripts/ops/tests/wms517-mac-dom.test.cjs
```

DOM test использует уже объявленный `frontend/package.json` jsdom26; требуется
установленный frontend/node_modules (допускается существующий общий root WMS).
`WMS517_MAC_SOURCE_DIR` — только test seam для historical/mutation проверки; обычная
команда выше читает актуальные product-файлы. Изменение frozen ожиданий разработчиком
запрещено; технические вопросы по интерфейсу возвращать тестировщику/ведущему.

Полный TAP RED и historical PASS сохранены рядом с этим документом. Никакой CI,
независимое ревью, приёмка, deployed SHA или реальный вывод этим checkpoint не объявляются.
