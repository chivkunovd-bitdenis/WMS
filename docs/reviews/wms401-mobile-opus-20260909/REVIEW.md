# WMS-401 — полный мобильный Opus Max review и независимая сверка

Дата: 09.09.2026. Frozen mobile SHA: `e2d43b5cc7817bf5be164b53ef9e2ef723c4f718`.
Результат CLI: **FAIL**, один обязательный finding F1.
После самостоятельного чтения кода подтверждён F1 и добавлен F2,
который Opus пропустил. Это отчёт о frozen версии до последующих исправлений,
а не разрешение на выпуск текущего APK.

## Область

Мобильный baseline `69caa22b3d2d0e715966776d0edb2cec92723696` → `e2d43b5cc7817bf5be164b53ef9e2ef723c4f718`:
полный новый WB FBS и узкая правка перехода «Войти по паролю».
В prompt переданы 12 явно перечисленных Kotlin production/test файлов.
Список и SHA256 diff: [scope.json](scope.json).
`bwip-js-min.js`, его лицензия и прежний review-документ не включены в diff prompt;
интеграция encoder проверялась по Kotlin. Полный mobile Git и история подписи
не публиковались и для review не читались.

Backend-контракты читались из `.worktrees/wms401-source-switch/backend/app`;
application code соответствует `aa7de3de8a965d1088ec44db1bb5f41a766d9dc5`.
Рабочее дерево mobile при запуске было чистым и HEAD проверен.
В конце работы другой агент начал следующую правку `FbsViewModel.kt`;
она не включена в frozen diff и не получила оценку Opus. По метаданным именно
этой CLI-сессии Read данного файла выполнен в 11:27:58 UTC, а mtime новой
правки — 11:45:15 UTC; Opus не перечитывал новую версию ViewModel.

WMS-402 (прямая сетевая печать) остаётся отдельной незавершённой задачей.
`PrintManager` открывает системный диалог Android; это не подтверждение
физической печати. APK/AVD проверял другой агент, этот review его не заменяет.

## Подтверждённые обязательные замечания frozen версии

### F1 · P2 · Вместо результата WB оператор видит «ok»

Подтверждён finding Opus. `FbsViewModel.kt:230–237` выбирает `result.message`
раньше шаблона с `metaStatus`. Backend `fbs_kiz_service.py:1435–1442`
на успешной обработке всегда возвращает `message="ok"`.
Поэтому для ответа `status=ok, message=ok, meta_status=pending` оператор видит
просто **«ok»** и не видит ожидание ответа WB. В raw review написано
«Ответ WB: ok» — это неточность: prefix в фактическом UI отсутствует.

Исправление должно показывать понятное состояние из `meta_status`, отдельно
от подтверждения сохранения/отправки. `pending`, `sending`, неизвестный статус
нельзя называть окончательным принятием WB. Нейтральное `message="ok"`
не должно вытеснять этот текст; содержательное сообщение об ошибке терять нельзя.
Изменять backend acceptance ради QA нельзя. Root сообщил, что у QA WB-эмулятора
`metaDetails=[]`; это внешний контекст проверки, а не найденная review ошибка production.

### F2 · P2 · Отсканированный технический QR заказа не находится в коробах

Это **дополнительный finding самостоятельной сверки**, Opus его не указал.
Frozen `FbsViewModel.kt:250–258` сравнивает вход со `sticker.code`, WB order id,
товарным barcode/SKU/article. `fbs_worklist_service.py:939–943` выдаёт
`sticker.code = order.sticker_code` — печатный номер.
Технический barcode QR хранится в другом поле `order.sticker_barcode`;
backend lookup явно различает их в `fbs_kiz_service.py:568–575`.
Мобильный workspace не содержит технического barcode и frozen `scanBox`
не вызывает серверный resolver.

Воспроизведение: открыть короб, отсканировать QR с technical barcode,
который отличается от печатного номера заказа и товарных кодов. Frozen клиент
выдаёт «Нет нераспределённого заказа с таким кодом» вместо распределения.
Основной агент независимо сообщил свежую DB-проверку собственного QA заказа
500046: technical barcode `*DU7aq2hE`, печатный номер `571157528424`
(в представлении с пробелами). Данные DB приведены с атрибуцией основному агенту;
автор этого отчёта не выполнял запрос к production/QA базе и не нажимал APK.
Кодовый разрыв проверен отдельно чтением файлов и frozen `git show`.

Нужна адресная резолюция такого скана в order id перед существующим assign API,
с сохранением проверки принадлежности поставке и защиты от повторного назначения.
Не следует ослаблять проверки WB или вводить складские движения.
Начатый после frozen SHA lookup fallback в рабочем дереве не считается
проверенным исправлением в этом отчёте.

## Границы и поправки к выводам Opus

Фраза Opus «client always sends order_id» неверна: `oldestMatchingOrder`
(`FbsViewModel.kt:22–25`) знает только отображаемые barcode/SKU/article;
`pickAction:166–169` передаёт nullable `order?.id`. Если валидный
`order.wb_barcode` отличается от полей карточки, backend распознаёт товар в
`fbs_picking_service.py:1685–1691`, затем при отсутствии `order_id` выбирает
заказ по `deadline_at` (`:1064–1065`), а не по моменту поступления.
Источник при этом сохраняется. Это конкретная кодовая граница гарантии FIFO;
различие результата на реальном APK с такими заказами здесь не проверено.
Общее утверждение reviewer об отсутствии mismatch нельзя принимать без этой оговорки.

Прочитанные picking/packing пути не добавляют второго списания склада;
упаковка записывает факт. Это вывод о рассмотренном WB application code,
а не универсальное доказательство отсутствия любого double-write при всех сбоях.
Существующие retry/idempotency ключи не заменялись в этом review.

Прочие ограничения raw review — последовательные QR-запросы на каждый заказ,
PNG-only печать WB, отсутствие возврата к списку сотрудников из password формы,
очередь сканов при неубранной ошибке — не превращены в дополнительные
блокеры без конкретного нарушения требования. `deliver`/tracking/preflight
API декларации не являются реализованным экраном передачи; такой экран
не добавлялся к согласованной области WMS-401 этим review.

## Доказательство запуска и расход

Установленный CLI Claude Code `2.1.123`, help проверен при первом запуске
после перезагрузки. Выполнен один полный мобильный review:

```sh
claude -p --model claude-opus-4-7 --effort max \
  --permission-mode plan --tools Read,Grep,Glob --allowedTools Read,Grep,Glob \
  --strict-mcp-config --mcp-config '{"mcpServers":{}}' \
  --add-dir /Users/deniscivkunov/Projects/WMS/.worktrees/wms397-mobile \
  --output-format json \
  < /Users/deniscivkunov/Projects/WMS/outputs/wms401-mobile-opus-20260909/opus-prompt.txt \
  > /Users/deniscivkunov/Projects/WMS/outputs/wms401-mobile-opus-20260909/opus-review.json \
  2> /Users/deniscivkunov/Projects/WMS/outputs/wms401-mobile-opus-20260909/opus-review.stderr
```

Exit code `0`, `subtype=success`, `terminal_reason=completed`, `is_error=false`,
`permission_denials=[]`, stderr пустой. FAIL — содержательный verdict review,
не ошибка CLI. Session `60392d3e-726e-4cb1-b52b-87016049c7c2`.
Длительность `1062896` ms (17 минут 43 секунды), `89` turns.
CLI сообщает `total_cost_usd=9.77926825`.
Usage верхнего уровня: input `92`, cache creation
`226875`, cache read `13570438`,
output `59320`. Cache read — повторно используемый контекст,
не объём написанного отчёта. `modelUsage` содержит основной Opus 4.7 и
вспомогательный Haiku; полные значения сохранены в JSON.

Всего автор этого отчёта выполнил после перезагрузки **два** CLI review:
source-switch (7 минут 43 секунды, CLI cost 1.49365025 USD) и этот mobile
(17 минут 43 секунды, CLI cost 9.77926825 USD). Сумма полей cost —
**11.27291850 USD**. Это оценка CLI, не реальная сумма списания подписки и
не процент лимита аккаунта. Прерванный до перезагрузки review запускал
предыдущий процесс; здесь он не посчитан как новый запуск.
После запроса пользователя о расходе новые/повторные Opus не запускались;
текущий процесс завершился без перезапуска. Дальнейшие изменения проверяются
основным заданием без повторения полного Opus review.

Неизменённый полный ответ: [result.json](result.json).
Точный prompt, поле `prompt`: [prompt.json](prompt.json).
SHA256 result: `fe33d69faa9507a17311c4067e1fb006156474e52c345db7b841f0774e5d8d38`.
SHA256 исходного текста prompt: `4bceb2b2b0a3636743cdf109dd6a9174d47bdc8d4e63468584017f7d689e9b1b`.
SHA256 whitelisted diff: `a5f686b919cc2e7e5a50b1068cea590ec2324dc08f40b123b7b4aa506eb31afb`.

В этой задаче не изменялся application code, не запускались дополнительные
тесты/серверы/AVD и не выполнялись внешние складские операции.
Статус WMS-401 и приёмку последующих исправлений ведёт основное задание.
