# WMS-675: независимое ревью read-only collector

06.10.2026. Отдельная сессия `gpt-6.1-sol`, не автор скрипта.
**PASS** для опубликованного `767f19fd2f4ba479f2034f915c0f16a1a4d962d4`,
дельта `df3e17614` → `767f19fd2`. Remote SHA проверен до запуска.

Прочитаны collect_ozon_bound.py, offline-проверки, seed plan и pending matrix,
RUN_BOUND_READER, штатные account/provider/factory/transport реализации.
Новых тестов/синхронизации/списаний/отгрузок ревьюер не запускал. Сохранённый
результат шести offline-проверок принадлежит разработчику; здесь выполнено чтение.

Collector сверяет точные tenant/seller/supply, 31 seed, состав и warehouse в
штатной PostgreSQL сессии `REPEATABLE READ, READ ONLY`; завершает snapshot
rollback до HTTP. Account service читает только seller-bound подключение
внутри приложения. Ключи/заголовки/конфигурация не переносятся и не выводятся.
Factory обязан быть live, host — точный api-seller.ozon.ru. Только read endpoint
`/v3/posting/fbs/get`: HTTP POST является чтением карточки, не отгрузкой.
Provider/transport делают один запрос без скрытого retry. Дополнительные
posting numbers приходят только из related/weight links Ozon; каждый номер
читается не более одного раза, предел 124. Контур не вызывает WMS sync/commit,
внешний ship/carriage/approve/create, печать или исправление остатков.

Записывается только allowlist полей карточки/состава/связей/отмены и безопасная
HTTP metadata; customer/addressee/financial/legal/marks/barcodes/raw errors и
headers исключены. Ошибки и неполные products/split остаются unknown. Manifest
сохраняется по каждой карточке, каталог результата должен быть новым.
Подтверждённых дефектов безопасности чтения не найдено. Reader не доказывает
расход или восстановление: граф/состав нужно сверить, live учёт перед мутацией
перечитать отдельно штатным процессом. Условия расхода не ослабляются.

SHA256 collector: `77f56f1100d27db0f369ff7edb436332c9fd91f295d4065c90bcb51e68e80011`.
SHA256 seed plan: `cccfb2d7c024f02309f23424a67473723cfcb6d7d85312f138f1b152e04bc00b`.
