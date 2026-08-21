# BLG-D07 — S03 RESEARCH REWORK CLOSURE

## Паспорт

- Владелец rework: `pipeline-ba:codex-blg-d07-research-rework`.
- Дата повторной проверки: `2026-08-21T06:52:00+03:00`.
- Контур: публичная документация и локальные research artifacts; Marketplace API не вызывался.
- Исполненные sandbox/emulator proofs: `0`.
- Результат: S03 исправлен и готов к новому независимому S04; это не verdict `RESEARCH_PASSED`.

## Закрытие находок S04

### RC-01 — status enum

Текущая видимая английская страница
`https://dev.wildberries.ru/en/docs/openapi/orders-fbs`, endpoint heading
`Get Assembly Orders Statuses /api/v3/orders/status`, воспроизведена без авторизации.

- `supplierStatus`: `new`, `confirm`, `complete`, `cancel`, `cancel_carrier`.
- `wbStatus`: `waiting`, `sorted`, `sold`, `canceled`, `canceled_by_client`,
  `declined_by_client`, `defect`, `ready_for_pickup`, `postponed_delivery`,
  `accepted_by_carrier`, `sent_to_carrier`, `canceled_by_carrier`.
- `postponed_delivery` добавлен в обе S03-матрицы как нетерминальный статус.
- Carrier-cancel значения имеют текущий live-visible provenance. Их отсутствие в старом
  индексированном снимке записано как version skew, а не скрыто.
- Unknown values сохраняются raw и не разрешают необратимое локальное действие.

### RC-02 — multiplier и response matrix

У официального canonical URL зафиксированы две датированные формулировки:

1. индексированный snapshot, наблюдавшийся `2026-08-21` и помеченный crawler как `5 months ago`:
   **ответ `409` учитывается как 10 запросов**;
2. текущий live-visible DOM `2026-08-21T06:52:00+03:00`: **каждый `4XX` учитывается как 10
   запросов**.

Это реальный oracle drift. S03 теперь не приписывает старому правилу лишние коды и не выдаёт его за
текущую полноту: `409 x10` записан точно для старого снимка, текущий rate budget использует более
широкое `4XX x10`. Новый S04 обязан независимо воспроизвести страницу и рассудить drift.

Текущая таблица responses именно status endpoint: `200`, `400`, `401`, `402`, `403`, `429`.
`404` передан в S15 только как unexpected-response case и не назван документированным ответом этого
endpoint.

### RC-03 — sandbox и S15

Все `WB-FBS-STATUS-01..10` теперь явно имеют evidence state `documented_not_executed`. S03 не
использовал sandbox token и не создавал execution proof.

В S15 переданы 19 обязательных runnable local-emulator cases: полный, частичный и malformed `200`;
missing/duplicate/foreign ID; unknown, late и carrier statuses; `400`, `401`, `402`, `403`, unexpected
`404`, точный `409 x10`, текущий общий `4XX x10`, `429`, timeout/`5XX`; fallback cap;
restart/replay; starvation. Оракулы названы в `S03-DOMAIN-RESEARCH.md`, машинные IDs — в
`S03-capability-matrix.json`.

## Resume condition

- Полный status/error contract с датированным provenance: закрыт, включая явный version skew.
- `409 x10` указан точно: закрыт для снимка, на котором основана находка; текущая официальная версия
  дополнительно и явно расширяет правило до `4XX x10`.
- Documented sandbox design отделён от executed proof: закрыт.
- Explicit local-emulator coverage передан S15: закрыт.
- `unhandled_applicable_rows`: `0`; executed proof не подменён research closure.

Следующее допустимое действие контроллера: `resume` на `S04`, затем новый packet/dispatch
независимому `pipeline-reviewer`. Автор rework не выполняет `S04 advance`.
