# Манифест выполнения системного ревью WMS

Дата среза: 2026-08-12 (Europe/Moscow).

## Базы и границы

- Статическая база основного репозитория: `etalon` / `a39530c5137deb31e189c2136b613d01093af87b`.
- Статическая база Android-клиента: `09aa479fd8e311a8155c92074ab2f4a6ec843da4`.
- Фактически развёрнутый Railway staging: frontend и API из `44fe72e3525332bb01fd76ba420f9cecbdaac6ba` по deployment metadata Railway. Это на два commit позади etalon; наблюдения staging не приписываются etalon без отдельного статического сравнения.
- В Railway присутствуют только `web`, `WMS` и `Postgres`. Отдельных worker/beat нет.
- Schema revision напрямую из `alembic_version` не читалась; по deployed tree и startup logs ожидается head `0075`, но это inference, а не прямой read-back. Etalon добавляет `0076`.
- Production и любые реальные действия в WB исключены. FBS runtime ограничен локальными read-only экранами staging, потому что synthetic WB emulator в deployed окружении не доказан.
- Физические ТСД, сканер и принтер не были подключены. Mobile runtime остаётся `NOT_RUN_DEVICE`.

## Кто что делал

Оркестратор выполнял Browser-действия в изолированном staging tenant и сохранял изображения. Product, architect и teamlead независимо открывали переданные PNG через визуальный просмотр и выносили собственные вердикты. Это явно обозначается как `execution=orchestrator, adjudication=<role>`; ни один агент не заявляет, что сам кликал экран.

Три роли независимо исследовали статический код и свои зоны: продуктовые сценарии, архитектуру/целостность, инженерное качество/отказоустойчивость. P0 отдельно воспроизведён архитектором дважды и тимлидом ещё дважды в других synthetic tenants.

## Browser-факты

- FF: реально прокликаны все 12 пунктов основного меню.
- Seller: реально прокликаны все 4 пункта меню, а также первый вход, заглушка акта расхождений и создание пустого inbound draft.
- FBS: реально прокликаны 5 групп заказов и вкладка остатков WB; WB-sync/publish/deliver/cancel не нажимались.
- Рабочие сценарии: создание склада; создание двух ячеек; reload и повторный выбор склада; создание FF MP draft, ожидание и reload; открытие detail; создание seller inbound draft; обязательная валидация товара без выбранного seller.
- Для desktop batch страница сама вернула `window.innerWidth=1920`, `innerHeight=1080`, `devicePixelRatio=1`; PNG имеют ширину 1920. Ранние переходные кадры с затемнением сохранены как диагностические, но не используются для layout verdict. Основные выводы опираются на файлы `stable-2s`, `stable-4s`, `reload` и исправленный `reload-reselect-visible`.
- Каталог evidence содержит 93 PNG (7.2 MiB) в каталоге `evidence/`.

## Изменения данных staging

Созданы только синтетические изолированные сущности: review tenants, test sellers, один склад, две ячейки, пустые MP/inbound drafts и данные для конкурентной проверки приёмки. WB и чужие tenants не изменялись. Аномальные P0-строки оставлены в своих synthetic tenants: безопасного tenant-delete/общей correction операции в проверенном публичном контракте нет.

## Что не считается доказанным

- Пять пустых FBS-вкладок не доказывают picking, packing, box QR, PVZ/SC delivery и stock publish.
- Пустые reception/sorting/packaging страницы не доказывают полный документный цикл.
- Наличие route и красивого empty state не является `PASS_WORKFLOW`.
- Health `200` не доказывает worker, beat, schema или совместимость mobile.
- Локальные тесты после ограничения пользователя не запускались; runtime-функциональность проверялась только на staging.
