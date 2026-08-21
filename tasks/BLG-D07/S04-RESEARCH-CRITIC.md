# BLG-D07 - S04 RESEARCH_CRITIC

## Паспорт повторного review

- Роль: `pipeline-reviewer`, независимый `research-critic`.
- Проверенный rework commit: `d091d645a15ddc6392847a339b8d78ee6a282e4c`.
- Модельный класс dispatch: `gpt-5.6-sol`, `expensive`.
- Дата повторной проверки: `2026-08-21`, Europe/Moscow.
- Вход: `S03-DOMAIN-RESEARCH.md`, `S03-capability-matrix.json`,
  `S03-RESEARCH-REWORK-CLOSURE.md`, предыдущий S04 verdict и controller packet.
- Независимая внешняя сверка: публичные страницы WB FBS OpenAPI и sandbox documentation открыты
  без авторизации; Marketplace production/sandbox API не вызывался.
- Секреты, кабинеты учётных данных, deploy и application code не затрагивались.
- Verdict: `RESEARCH_PASSED`.

## Итог

Rework закрывает все три блокирующие находки предыдущего S04. Текущий официальный FBS OpenAPI
воспроизводимо подтверждает полный status enum, включая `postponed_delivery`, `cancel_carrier` и
`canceled_by_carrier`, а также действующее правило `4XX x10`. Исследование больше не смешивает
документированные sandbox-переходы с исполненным proof и передаёт в S15 явный набор из 19 runnable
local-emulator cases без разрешения live-вызовов.

Research достаточен для перехода к Product-контракту S11. Он не утверждает terminal/reopen policy за
Product и не выдаёт будущую emulator execution за уже полученное доказательство.

## Независимая проверка blocker

### RC-01 - status enum и provenance: закрыто

На публичной странице `https://dev.wildberries.ru/en/docs/openapi/orders-fbs` в разделе
`Get Assembly Orders Statuses /api/v3/orders/status` независимо воспроизведены:

- `supplierStatus`: `new`, `confirm`, `complete`, `cancel`, `cancel_carrier`;
- `wbStatus`: `waiting`, `sorted`, `sold`, `canceled`, `canceled_by_client`,
  `declined_by_client`, `defect`, `ready_for_pickup`, `postponed_delivery`,
  `accepted_by_carrier`, `sent_to_carrier`, `canceled_by_carrier`.

S03 включает `postponed_delivery` как нетерминальный статус, даёт carrier-значениям точный URL,
endpoint heading и дату извлечения, а неизвестные значения сохраняет raw без необратимого действия.
Carrier-cancel provenance теперь воспроизводим и не зависит от предположения автора.

### RC-02 - rate-limit version skew: закрыто

Текущий видимый DOM того же endpoint содержит правило: `One request with 4XX response codes is
counted as 10 requests.` S03 явно отделяет его от старого indexed observation `409 x10` и выбирает
для текущего общего seller budget более широкое `4XX x10`.

Старый indexed snapshot не является immutable сохранённым артефактом этой карточки, поэтому на нём
нельзя строить текущую retry/rate policy. Это не blocker: текущий источник независимо воспроизведён,
а выбранное правило консервативно охватывает `409` и не трактует остальные `4XX` как бесплатные.
Response matrix также не смешана: `404` обозначен как unexpected emulator case, а не как
документированный ответ status endpoint.

### RC-03 - sandbox и S15 handoff: закрыто

Публичная sandbox documentation независимо подтверждает model rows от `waiting/new` до
`sorted/complete`, `ready_for_pickup/complete`, `sold/complete`,
`canceled_by_client/complete` и `defect/complete`. Carrier statuses и `postponed_delivery` в этой
sandbox status model не найдены, что совпадает с границей S03.

Все десять sandbox rows имеют единый evidence state `documented_not_executed`; счётчики исполненных
sandbox и local-emulator proofs равны нулю. В S15 переданы 19 machine-readable case IDs для полного,
частичного, malformed и неоднозначного `200`, unknown/late/carrier statuses, error/rate classes,
timeout/`5XX`, fallback cap, restart/replay и starvation. Это полноценный test design handoff, но не
execution proof.

## Closure matrix

| Область | Результат | Основание |
|---|---|---|
| `postponed_delivery` | pass | Есть в текущем `wbStatus` и в обеих S03-матрицах как non-terminal. |
| Carrier cancel values | pass | Независимо воспроизведены на текущем canonical FBS OpenAPI URL. |
| `409 x10` / `4XX x10` skew | pass | Версии разделены; current budget использует более широкий текущий oracle. |
| Error response matrix | pass | Текущие documented responses отделены от unexpected `404` case. |
| Sandbox evidence class | pass | Все rows помечены `documented_not_executed`; executed proof равен нулю. |
| S15 local emulator | pass | 19 явных runnable case IDs с безопасными oracle. |
| Unknown statuses | pass | Raw сохраняется, необратимые side effects запрещены до Product mapping. |
| Live calls / secrets | pass | Production и sandbox API, токены и кабинеты не использовались. |

## Остаточные обязательства следующих стадий

1. S11 должен утвердить terminal/reopen policy; S03 не подменяет Product-решение.
2. S13 должен задать общий seller rate budget, bounded retry/circuit breaker и restart semantics.
3. S15 должен материализовать все 19 переданных case IDs, а S19 - дать им runnable bindings.
4. Ни один из этих будущих пунктов не является пропущенной research capability row.

Предыдущий verdict `RESEARCH_REWORK` снят только после повторной независимой проверки rework commit.
Дополнительных S04 blocker нет.
