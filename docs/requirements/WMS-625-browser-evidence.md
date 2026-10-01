# WMS-625 — доказательства браузерной сохранности

## Текущая версия

Разработка завершена GPT-6.1 по новому прямому поручению владельца. Frontend
`7ecc4d99` подключает обычный WB товарный скан → QR к тому же durable native
транспорту и сохраняет обычную семантику упаковки и настройки QR/ЧЗ/перепечатки.
До POST сохраняется признак начала отправки; последующий GET404 не разрешает
автоматическую копию. Ответ v2 проверяется по схеме, контексту, точной PNG и
размеру, в том числе по реальному формату Swift/Python. Imported legacy запись
остаётся диагностикой; legacy helper без GET не получает повтор неизвестного
POST. Связанная допечатка требует `duplicateRiskAcknowledged === true`.

165 целевых тестов, проверка типов и production build прошли. Ведущий лично
прошёл обычное восстановление в Chrome; точные наблюдения записаны в
[его отчёте](WMS-625-review-lead.md). Astra независимо выполнила 78 адресных
frontend тестов и фактический обмен с заново скомпилированным Swift. Итоговый
вердикт находится в [отчёте ревью](WMS-625-review-final.md). На момент обновления
остаётся F4: повреждённый pending-журнал не должен блокировать обычный поиск
уже известного стикера. Исправление передано тому же разработчику.

## Исторический отчёт первоначальной реализации

Далее сохранены исходные доказательства для `26852c08`/`24c3cbf5`. Их формулировки
об объёме обычного пути и legacy POST относятся к этим версиям, а не к текущему
контракту выше. Исполнитель той стадии: отдельный Astra; фронт был разрешён
владельцем. Это отчёт реализации, не заключение приёмки и не физическая печать.

## Что сохранено

Массовая последовательная сборка до native-вызова сохраняет PNG целиком, исходные размеры, ключ, штрихкод, order/scan/supply/user/tenant и WB order ID в IndexedDB. Завершение записи ожидает commit транзакции с durability strict. Повтор того же ключа с другой картинкой/размером/контекстом не перезаписывает оригинал, включая конкурентную запись через другие вкладки. После получения результата native он сохраняется до серверного started/pack; история с PNG не удаляется при снятии pending-скана.

Отдельный существующий localStorage указатель на выбор заказа сохраняется до серверного скана. В массовом пути недоступное или повреждённое хранилище больше не превращается молча в отсутствие pending. После reload исходный штрихкод возвращается к прежнему request key, а другой штрихкод получает указание сначала восстановить незавершённый заказ. Серверная запись started больше не заменяет сверку native результата.

Обычный QR/ЧЗ и его флаги не переведены на новый транспорт. Изменение общей функции startClaimedAutomaticPrint — необязательная сверка только для нового массового пути. Бэкенд не менялся.

## Проверки

Команды из frontend: `npx tsc --noEmit -p tsconfig.app.json`; `npm run build`; `npx vitest run src/utils/durableDirectQr.test.ts src/screens/v2/fbsScanAutoPrint.durability.test.ts src/screens/v2/fbsSequentialPacking.test.ts src/screens/v2/fbsSequentialPacking.recovery.test.ts src/screens/v2/fbsSequentialPacking.binding.test.ts src/screens/v2/fbsKizAutoReprint.test.ts src/screens/v2/fbsScanAutoPrint.test.ts`.

Целевые 75 проверок прошли: сохранение до сети, quota/write/read/corrupt failures, исходный ключ после remount, потерянный POST response, async saved/submitting/accepted, canceled/aborted/stopped/held/unknown с receipt, проверенный presubmit retry, ошибка commit результата, несовпадение размеров/PNG/пользователя, legacy receipt, отсутствующий native job при серверном started, отдельные намерения двух одинаковых единиц, ЧЗ/привязка и исходный короб. Дополнительно проверены завершение исходной упаковки по связанной явной перепечатке, обязательная свежая сверка дочернего задания и отказ при неверных parentKey/hash/размере/пользователе/WB order ID, отсутствии квитанции либо неизвестном результате дочернего задания. Ошибка сохранения обновлённого результата не допускает pack.

## Реальный браузер

Перед изменением открыт рабочий существующий экран read-only: `https://wms.sellerfocus.pro/ff/fbs?supply_id=15f67cc7-e018-4b17-a0a8-56d6446ad00f`, Denmarcs, ноль заказов, вкладка «Упаковка и маркировка». Рабочие сканы и печать не выполнялись.

Изолированная fixture: `frontend/tests/browser/wms625-durable-qr.html`, Vite на 127.0.0.1:16255. Она исполняет настоящие makePackingScanDeps/createPackingScanController и IndexedDB Chrome, а WMS API/native — явно тестовые подстановки. В production build fixture не входит. В CUA 01.10.2026 получены такие состояния:

1. Native offline, первый скан: selectedOrders=1, printPosts=0, packed=[], active=order-1, savedKey=fixture-scan-1, savedSize=58×40, exactPng=true. Ошибка честно сообщает о сохранённой этикетке.
2. Настройка изменена на 70×120, выполнен reload: прежний key и PNG доступны, savedSize всё ещё 58×40.
3. Тестовая очередь приняла первое задание, HTTP-ответ потерян: selectedOrders=1, printPosts=1, packed=[], исходный order-1 остаётся активным.
4. Ещё один reload и исходный штрихкод: selectedOrders=1, printPosts=1, packed=[order-1], сохранённый result=accepted, error пуст. Второго POST нет.
5. Следующий одинаковый товар: новый fixture-scan-2, selectedOrders=2, printPosts=2, размер новой попытки 70×120; первая попытка остаётся 58×40.
6. Вторая очередь отменена после потерянного ответа; reload и повтор: selectedOrders=2, printPosts=2, packed только order-1, pending order-2, result=canceled, exactPng=true. Ошибка показывает WB №625002, штрихкод, исходный ключ и localhost-журнал. Ложной упаковки и новой копии нет. Получен скриншот CUA этого состояния.

7. После явной тестовой перепечатки fixture-scan-2 создан связанный fixture-scan-2:explicit-reprint; счётчик отправок вырос до 3 только от этой команды. Выполнены reload и исходный скан: selectedOrders=2, printPosts=3, packed=[order-1,order-2], original result=canceled, reprints=[accepted child с parent fixture-scan-2], exactPng=true. Ещё один reload сохранил всю эту историю. Браузер новой копии не отправлял.

## Границы

Нативный протокол согласован с runtime-разработчиком: protocolVersion:2 даёт async202 и polling; legacy helper без GET сохраняет совместимость через тот же POST key и настоящую receipt. Accepted/pending/processing/completed вместе с receipt означают приём очередью, не бумагу. Canceled/aborted/held/stopped/unknown не являются успехом.

Повтор скана адресно выполняет безопасный native retry только для saved/failed_before_submit. Для canceled/aborted/unknown он читает результат и сохраняет исходную попытку, не создавая скрытую копию. Явная перепечатка через native-журнал возвращается в исходную браузерную попытку через reprints[]: проверяются parentKey, hash исходных PNG+размера, размеры, полный контекст и отдельный ключ. Браузер выполняет POST child/reconcile, повторно читает исходное задание и сохраняет оригинал с reprints до pack. Только совпадающий дочерний результат с известным accepted/pending/processing/completed и настоящей квитанцией завершает исходный pending. Original status остаётся canceled/aborted/unknown в сохранённой истории. При наличии дочерней перепечатки браузер не вызывает retry оригинала, даже если оригинал failed_before_submit: иначе неизвестный исход дочернего задания мог бы породить скрытый дубликат.

Проверка физической этикетки, рабочего принтера и ночных 17 пропусков этим тестом не выполнена. Production deploy/merge не выполнялись.
