# WMS-681: независимое ревью PostgreSQL race, 07.10.2026

**PASS**, product SHA `5eb18bc0ca54c2005ef551c2877c5dd3943ec01e`, родитель RED `f034e3b08c76f4e9ace933c84ef3fe1de4703b18`. Можно передать исходному аналитику `01a1133a`; это не приёмка и не разрешение выпуска.

Полный новый diff меняет только `fbs_print_asset_service.py`. Обязательные правила, требования и обе библиотеки случаев полностью прочитаны в предыдущем независимом ревью; контекст сохранён.

[Сервис](../../backend/app/services/fbs_print_asset_service.py#L628) блокирует **только FbsTrbx**, ограниченный trbx/supply/tenant/seller; join не захватывает чужую поставку или её marketplace. [Повторное чтение](../../backend/app/services/fbs_print_asset_service.py#L510) с `populate_existing` обновляет ORM-снимок. Готовый проверенный файл переиспользуется с прежним ID, без перезаписи metadata/байтов. Иначе прежнее сохранение записи и файла выполняется под блокировкой до commit.

[Единственный вызывающий путь](../../backend/app/services/fbs_shipment_pvz_service.py#L500) обрабатывает одно грузоместо и делает commit перед следующим: новые блокировки нескольких грузомест не накапливаются, обратного порядка в изменённом пути не найдено. Внешнее чтение предшествует новой блокировке; blind create, повтор неизвестной внешней операции и rollback чужих pending writes не добавлены. Durable A1/R6, cached ready, Ozon-путь и физические короба сохранены. Всеобщая свобода от deadlock не заявляется.

Независимо разобран сохранённый [GREEN JUnit](../evidence/WMS-681/postgres-c6/green-junit.xml), сопоставленный с [RED](../evidence/WMS-681/postgres-c6/red-junit.xml) и [реальным тестом](../../backend/tests/test_wms681_postgres_recovery.py#L161): RED `23505/uq_fbs_print_assets_ready_cargo_qr`; GREEN **1 passed/0 skipped**, OS `6494/6513`, PG `6509/6522`, блокирование второго первым, QR overlap, `[200,200]`, create `[5]`, одинаковые пять asset IDs. Физические связи/другая группа проверяются frozen assertions.

Receipt скопирован побайтно; SHA256 `bae01efd39cfa2f97871c0bdfee17abd61b08bae3f35528c6045768d497ad658`. XML предшествует commit; связь с итоговым кодом подтверждает developer handoff, сам XML Git SHA не удостоверяет. Здесь тест не перезапускался; новых оснований для отрицательного сценария не найдено. Предоставленные 17 recovery/23 asset/29 DOM, ruff/mypy PASS не выдаются за мои повторные запуски.

Ограничения: старое P3 registry остаётся; миграционный production-schema proof, физическая печать, deploy и полный CI не выполнены. Аналитическую приёмку заполняет исходный аналитик; CI проверяет окончательный candidate SHA.
