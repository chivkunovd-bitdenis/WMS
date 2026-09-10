# WMS-363 — отдельный выпуск совместимого мобильного API

10.09.2026. PR [213](https://github.com/chivkunovd-bitdenis/WMS/pull/213)
слит в etalon с head3210e7d12cccc0e3c894590ea3881fc911da04bd.
Проверенный merge SHA: **0771833b7389260042f03a47abc7821e3a47fcb4**.
CI [34452470232](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/34452470232)
полностью прошёл: backend9m54s, frontend59s, backlog8s. Backend/frontend
mergeSHA побайтно совпадают с проверенным head PR.

Независимое backend review на644c656c не нашло нарушения новых контрактов;
пять backend файлов между этим SHA и3210e7d1 не менялись.
Документ: wms415-astra-independent-mobile-20260910.md.
Android-артефакты в ветке не означают принятого APK: e2685e7772fc отклонён
последним review восстановления очереди при устаревшем списке коробов.
Этот дефект не входит в исполняемый backend.

Сервер /opt/wms перед выполнением имел чистый tracked checkout0229831f.
Команды проверили принадлежность точного0771833b веткеorigin/etalon, прежний
HEAD и отсутствие изменений миграций/frontend/compose/deploy относительно
прошлого production. Затем checkout точного SHA, последовательная сборка
api/celery_worker/celery_beat и up --no-deps только этих трёх сервисов.
Использован существующий Compose projectwms_prod и оба его прежних configfiles.
Миграции не запускались, web/старый seller listener не перезапускались.
Скрипт завершился0; это отдельный mobile выпуск без общего338DDL,111/112,418.

После запуска координатор повторно прочитал серверныйGitHEAD и SHA256 пяти
файлов внутри wms_prod-api-1: api/fbs_kiz.py, api/fbs_orders.py,
api/fbs_supplies.py, services/fbs_worklist_service.py,
services/wb_marketplace_orders_service.py. Все совпали с Git0771833b.

Публичный HTTPS проверен curl со штатной проверкой сертификата:
/api/health200, /200, /seller/200, /api/openapi.json200. В публичной схеме
marketplace необязателен, wb|ozon; worklist поддерживает sort deadline|oldest.
Первый urllib-запрос завершился локальной ошибкой CA Python; проверка TLS не
отключалась, повтор штатным curl успешен. Это проверка HTTP/схемы, не ручной
проход оператора по клиентским заказам.

Доказательство: [verification JSON](artifacts/wms415-astra-takeover-20260910/resumed/mobile-backend-release-0771833b-verification.json).
Скрипт точного выпуска сохранён рядом; raw build log не публикуется.
Публичный manifest остаётсяversionCode9. APK, реальная кнопка9→10,
сохранённый PIN/server/незавершённый документ и физический ATOL/принтер
остаются отдельными этапами. Ни одно клиентское складское действие ради
теста не выполнялось, секреты и квота не менялись.
