# WMS-409: production artifact proof

09.09.2026, 10:37:53–10:38:30 UTC: **PASS**. Независимо подтверждён production
HEAD `/opt/wms`: `a75ed98a03e0500e41a69e5b617a27587bed9792`.
Проверка только читала Git, файлы контейнеров и публичные HTTP-ответы.
Приёмки и другие объекты не создавались, повторный deployment не выполнялся.

Все **179 файлов** production frontend в `/srv` побайтово совпали с runtime
staging, на котором выполнена [проверка диалогов WMS-409](wms409-stage-20260909.md).
Нет отличающихся, отсутствующих или лишних файлов. Дерево frontend в Git
совпадает с проверенным staging source `3f6f02c77db6ee777518f6dc55922297df907d67`:
`879a2dc0616e82c74eb4336c307b2c007391c33f`.

Публичные GET с https://wms.sellerfocus.pro вернули HTTP 200. Для `index.html`,
основного `assets/ff-DFfJOXYQ.js` и `assets/FfInboundQueuePage-CmHWjBe5.js`
SHA-256 ответа совпал с соответствующим файлом production `/srv`.
В bundle очереди присутствует `ff-inbound-create-error`. `/api/health`
вернул HTTP 200 и `{"status":"ok"}`.

Исходники всего `backend/` идентичны предыдущему production
`8dfb216d4061b15789982b72f7c1b82c57e3e897`: Git tree в обоих коммитах
`2fee72d26bab3bf3f2e4a4e68ca026179f290c5b`. Дополнительно все **428 Python-файлов**
`app/` и `alembic/` активного API совпали по SHA-256 с файлами production Git.
Отсутствующих, отличающихся и лишних Python-файлов нет.

API и web работают, не находятся в состоянии restarting. Проверенные image ID:

- API: `sha256:b3e840424d1fcbccad9af8073497c2d39aa2a2508e4d96de29c131c07e84b6f7`.
- Web: `sha256:ea20035720feabdf6019a565ab4bdf2f548cca59c2a0955597f1e715128dc8ad`.

Полные контрольные суммы и результаты:
[wms409-production-artifacts-20260909.json](wms409-production-artifacts-20260909.json).
Этот результат подтверждает доставку проверенного frontend на production;
создание документа реальным production-пользователем здесь не проверялось.

Канонический статус должен учитывать production SHA выше. В собственной
ветке evidence канон старше WMS-409, поэтому его устаревший раздел не менялся;
результат передан root для обновления актуального канона без отката новых задач.
