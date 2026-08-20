# Единая очередь backlog

Машинный источник очереди — docs/product/backlog-queue.json. Он собирает незакрытые и частично закрытые пункты из docs/BACKLOG-2026-08-19-CHAT-RU.md, включая разделы D, F, I, K и клиентские входящие. Закрытый или подтверждённый как ошибка разбора пункт в очередь не переносится.

Каждый элемент имеет стабильный id вида BLG-*. source_section сохраняет трассировку к исходному разделу, type описывает характер работы, status — текущую судьбу пункта, а readiness — ближайший допустимый вход в конвейер. dependencies содержит только IDs этой очереди: сначала закрываются указанные предпосылки, затем задача может получить собственную карточку.

suggested_roles и suggested_stages — начальная маршрутизация, а не разрешение на запуск. Значения needs_product_*, needs_architecture_*, needs_product_discovery, waiting_owner_* и waiting_dependency означают, что до Dev нужны соответствующие Product/BA/Architect артефакты, receipt или закрытие зависимости.

Очередь не является autopilot: owner-approved wave, Product receipt и обычные гейты pipeline остаются обязательными. Изменение JSON должно сопровождаться python3 scripts/ci/check_backlog_queue.py; скрипт проверяет JSON, обязательные поля, уникальность IDs и ссылки зависимостей.
