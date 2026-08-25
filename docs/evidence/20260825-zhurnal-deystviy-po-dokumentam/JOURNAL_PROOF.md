# API-доказательство журнала документов

Дата прогона: 25.08.2026.

Проверка выполнена через настоящий ASGI HTTP-контур приложения на отдельной SQLite-базе:
создан администратор ФФ, склад, товар и документ приёмки, после чего документ проведён только
HTTP-запросами от `draft` до `done`. Затем тем же токеном вызван
`GET /operations/document-events?document_type=inbound_intake&document_id=...`.

## Проведение документа

Документ: `66b9f9e9-cc5c-4427-93d9-366bd696ea92`.

```json
[
  {"step":"planned","status_code":200,"document_status":"draft"},
  {"step":"submitted","status_code":200,"document_status":"submitted"},
  {"step":"receiving","status_code":200,"document_status":"receiving"},
  {"step":"actual_5","status_code":200,"actual_qty":5},
  {"step":"sorting","status_code":200,"document_status":"sorting"},
  {"step":"done","status_code":200,"document_status":"done"}
]
```

## Фактический ответ журнала

HTTP status: `200`.
Ниже без сокращений сохранено буквальное тело HTTP-ответа.

```json
[{"id":"67ae1f62-b35b-4766-a02f-ab044e2822c0","document_type":"inbound_intake","document_id":"66b9f9e9-cc5c-4427-93d9-366bd696ea92","event_type":"status_changed","actor":{"id":"46adb48b-0c97-4754-ba9a-87cb4f216cd6","name":"journal-1787689511177170000@example.com"},"source":"user","occurred_at":"2026-08-25T20:25:13.022469","qty":5,"product":null,"payload":{"from":"sorting","to":"done"}},{"id":"0203c385-c5ba-4571-b81c-bccc236deef0","document_type":"inbound_intake","document_id":"66b9f9e9-cc5c-4427-93d9-366bd696ea92","event_type":"status_changed","actor":{"id":"46adb48b-0c97-4754-ba9a-87cb4f216cd6","name":"journal-1787689511177170000@example.com"},"source":"user","occurred_at":"2026-08-25T20:25:12.789057","qty":5,"product":null,"payload":{"from":"receiving","to":"sorting"}},{"id":"c3fc2851-7dec-4a43-bd01-65488c1c6d23","document_type":"inbound_intake","document_id":"66b9f9e9-cc5c-4427-93d9-366bd696ea92","event_type":"line_qty_changed","actor":{"id":"46adb48b-0c97-4754-ba9a-87cb4f216cd6","name":"journal-1787689511177170000@example.com"},"source":"user","occurred_at":"2026-08-25T20:25:12.701760","qty":5,"product":{"id":"adc95e62-7030-4349-b020-135f60591d20","name":"Journal product"},"payload":{"qty_before":0,"qty_after":5}},{"id":"5d3ed20e-1929-4863-ba74-936151a268a4","document_type":"inbound_intake","document_id":"66b9f9e9-cc5c-4427-93d9-366bd696ea92","event_type":"status_changed","actor":{"id":"46adb48b-0c97-4754-ba9a-87cb4f216cd6","name":"journal-1787689511177170000@example.com"},"source":"user","occurred_at":"2026-08-25T20:25:12.609537","qty":0,"product":null,"payload":{"from":"submitted","to":"receiving"}},{"id":"db82e4e9-e517-4d2e-83e4-54fca9609497","document_type":"inbound_intake","document_id":"66b9f9e9-cc5c-4427-93d9-366bd696ea92","event_type":"status_changed","actor":{"id":"46adb48b-0c97-4754-ba9a-87cb4f216cd6","name":"journal-1787689511177170000@example.com"},"source":"user","occurred_at":"2026-08-25T20:25:12.530178","qty":0,"product":null,"payload":{"from":"draft","to":"submitted"}},{"id":"fff6b58b-0360-42f6-ae03-32440db690af","document_type":"inbound_intake","document_id":"66b9f9e9-cc5c-4427-93d9-366bd696ea92","event_type":"planned_date_changed","actor":{"id":"46adb48b-0c97-4754-ba9a-87cb4f216cd6","name":"journal-1787689511177170000@example.com"},"source":"user","occurred_at":"2026-08-25T20:25:12.454639","qty":null,"product":null,"payload":{"field":"planned_delivery_date","value_before":null,"value_after":"2026-08-26"}},{"id":"0ef7c04f-912c-4f16-a26a-eeb85e833700","document_type":"inbound_intake","document_id":"66b9f9e9-cc5c-4427-93d9-366bd696ea92","event_type":"line_added","actor":{"id":"46adb48b-0c97-4754-ba9a-87cb4f216cd6","name":"journal-1787689511177170000@example.com"},"source":"user","occurred_at":"2026-08-25T20:25:12.389677","qty":5,"product":{"id":"adc95e62-7030-4349-b020-135f60591d20","name":"Journal product"},"payload":{"qty_before":0,"qty_after":5}}]
```

Ответ отсортирован от нового события к старому. В нём видны все четыре перехода основной цепочки,
один и тот же фактический автор, количество `5` после приёмки товара и отдельные изменения строки.
