# Оркестраторский вердикт по WMS

## Короткий ответ

Система **не готова к безопасному складскому использованию без ограничений**. Причина не в количестве визуальных недочётов: на staging воспроизводится P0, который незаметно удваивает остаток при конкурентном завершении приёмки. Etalon содержит тот же критический код. До его исправления любые дальнейшие polishing-задачи вторичны.

Кроме P0, deployment не запускает periodic worker/beat, committed Android-клиент расходится с backend-контрактом упаковки, основной раздел инвентаризации является заглушкой, seller action акта расхождений является обещанием будущей функции, а release signing material хранится в Git. Staging также не равен etalon, поэтому зелёный staging не является release-certification etalon.

## Подтверждённые findings

### P0 — конкурентное завершение приёмки удваивает товар

Четыре воспроизведения в независимых synthetic tenants дали одинаковый результат: два параллельных завершения одной строки `expected=actual=1` оба возвращают 200; документ остаётся с одной принятой единицей, но баланс становится 2 и появляются два движения `+1`. Critical path byte-identical между staging `44fe72e…` и etalon `a39530c…`.

Минимальное исправление: однократный атомарный переход `receiving → sorting` в одной БД-транзакции (row lock или conditional update), движения создаёт только победивший запрос; уникальный бизнес-ключ движения как последний барьер; один конкурентный regression-test. Новая очередь, event sourcing и отдельный сервис для этого не нужны.

### P1 — periodic jobs объявлены, но не развёрнуты

В Railway нет worker и beat; API запускает только Alembic + Uvicorn. Ручная job может выполниться inline, но FBS polling/status/stock reconcile, marking low-stock и WB warehouse refresh сами не стартуют. Health API при этом остаётся зелёным.

Минимум: по одному worker и scheduler из того же SHA, liveness/last-success и release gate на API/worker/beat/schema identity.

### P1 — mobile pack contract несовместим с backend

Pinned Android-клиент ожидает `PackagingTaskOut`, а staging и etalon возвращают wrapper `PackProgressOut`. Сервер фиксирует изменение до формирования ответа; устройство может показать ошибку после успешной мутации, а повтор без стабильного idempotency key способен применить следующую единицу.

Минимум: regenerate mobile client из текущего OpenAPI, читать `packaging_task`, отправлять стабильный idempotency key, добавить contract + lost-response retry tests.

### P1 — инвентаризация отсутствует как продуктовый процесс

Полноценный пункт основного FF-меню открывает только `Раздел в разработке`. Нет задания, охвата, пересчёта, расхождения и проводки. Это не empty state, а отсутствующий обязательный складской процесс.

Минимум: сначала простой закрытый цикл count draft → counted quantities → discrepancy → single post с журналом; без dashboard, аналитики и универсального workflow engine.

### P1 — seller «Акт расхождений» является ложной активной кнопкой

Реальный клик показывает сообщение «будет реализован на следующем этапе», не создавая документ. Кнопка должна либо вести к минимальному рабочему акту, либо быть убрана из production navigation до готовности.

### P1 security — release signing material отслеживается Git

`mobile/android/wms-tsd-release.jks` — tracked release keystore, а release build config содержит signing configuration. Секретные значения в отчёт не включены. Нужно считать текущий signing material скомпрометированным, удалить из истории/репозитория и провести отдельную управляемую ротацию владельцем ключа. Это единственный finding, где исправление нельзя сводить к изменению UI.

### P1 release/process — staging не является etalon и не имеет полного identity gate

Frontend/API staging работают из `44fe72e…`, etalon — `a39530c…`; migration `0076` на staging не представлена. Worker отсутствует, schema напрямую не читается. Release-решение обязано проверять один SHA для web/API/worker и точную migration revision.

### P2 — разные контуры по-разному считают available/reserved

FBS, marketplace unload, outbound inventory и FF catalog вычитают разные наборы reservation owners. Runtime overbooking через live WB не воспроизводился, но статическое семантическое расхождение подтверждено.

Минимум: одна функция available per tenant/warehouse/product с явным исключением только редактируемого объекта и permutation tests для порядка резервов.

### P2 — UI показывает внутренний `submitted`

Dashboard объясняет оператору план отгрузки через внутреннее имя статуса. Оставить русское бизнес-состояние, технический token убрать.

### P2 — dashboard deep-link к MP формируется с двойным `/ff`

Статический callback строит `/app/ff/ff/mp-shipments`; такого route нет, wildcard возвращает на dashboard. На пустом synthetic dashboard кликабельной строки не было, поэтому runtime конкретной ссылки не доказан. Исправление простое: route helper/одна константа плюс navigation test.

## Что визуально работает разумно

Не всё плохо. Empty states FBS, reception, sorting, catalog и settings объясняют назначение без технического мусора. Склад и ячейки создаются через понятный диалог и сохраняются после reload. MP и seller inbound позволяют сохранить черновик и прочитать его обратно. Seller first-login с самостоятельной установкой пароля понятен. Stable desktop screens в целом используют один визуальный язык и не требуют редизайна.

Именно поэтому не нужен тотальный UI rewrite. Нужны точечные устранения дыр: P0/data integrity, background deployment, mobile contract, обязательные процессы и ложные кнопки.

## Незакрытые обязательные границы

- FBS picking/packing/boxes/PVZ/SC/stock publish: `BLOCKED_LIVE_WB_NO_SYNTHETIC_INJECTION`.
- Полный reception → sorting → cell placement Browser lifecycle: `NOT_RUN_POPULATED_UI`; P0 проверен через staging API/state, но не заменяет экранный цикл.
- Physical TSD/scanner/printer: `NOT_RUN_DEVICE`.
- Cross-tenant Browser denial: статически проверяется ролями, но отдельный end-to-end screenshot/readback в этом проходе не закрыт.
- Schema revision: `INFERRED_0075`, прямого read-back нет.

Эти строки нельзя превращать в зелёные выводы по коду или empty screens.

## Порядок исправления без оверинжиниринга

1. Заморозить promotion etalon и закрыть P0 с конкурентным тестом.
2. Развернуть worker/beat и добавить deployment identity/readiness.
3. Синхронизировать Android contract и idempotency; прогнать на реальном ТСД.
4. Закрыть две честные продуктовые дыры: inventory и discrepancy act.
5. Унифицировать availability calculation.
6. После появления synthetic WB emulator прогнать FBS populated Browser flow; до этого не трогать утверждённый FBS UI по вкусовым причинам.
7. Только затем убирать `submitted`, dead link и локальный визуальный шум.

Никаких микросервисов, универсальной state machine или редизайна всей системы в этом плане нет.
