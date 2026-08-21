# S09 UX_CONTRACT_AND_MOCKUPS - BLG-I08

## Source, screen, and operator outcome

`BLG-I08` removes the blind spot in which a warehouse operator cannot tell whether a failed WB action concerns the order, the local network, a temporary WB problem, or the seller's WB connection. The task is intentionally diagnostic: it does not create, view, replace, delete, rotate, test, or otherwise manage a credential.

The changed surface is `S-21` `WildberriesScreen`, route `/app/integrations/wb`. It receives one read-only status zone above its existing integration work area. Existing filters, tables, actions, dialogs, credential-management legacy controls, and all other screens remain unchanged. The zone is scoped to the currently authorised `tenant_id + seller_id`; it must never show a different seller's status.

The operator can see, for each WMS-used WB category (`Content`, `Поставки`, `Маркетплейс`), the current safe connection state, the last diagnostic attempt, the last confirmed success, and the next human action. This stops futile retries while preserving the distinction between a broken configuration and a temporary WB or network outage.

## Read-only data and behavioural boundary

The UI receives only the allowlisted diagnostic fields from S03: `capability`, `environment`, `configured`, normalized `state`, `checked_at`, `last_success_at`, `success_source`, `expires_at`, `retry_after_at`, and a safe `incident_ref` only if Product later permits its visibility. Timestamps are stored in UTC and shown in the operator's local format with timezone; an absent value is shown as `Нет подтверждённого успеха`, never as a fabricated date.

The identity of every row is `tenant_id + seller_id + capability + environment`. A success for another seller, category, or sandbox must not make the production row look healthy. A `200 /ping` confirms only the checked category; it is not a claim that all WB services or write operations are available. Where the server reports `write_access: unknown`, the table says `Право записи не подтверждено` as an explanatory text, not as a green or red connection state.

There is no operator action to refresh, retry, paste, reveal, mask, inspect, create, replace, delete, or rotate a key. A rate-limit wait is not overridden by a button. The sole instruction is to pass the named state, category, last attempt time, and (when approved) safe incident reference to `ответственному за интеграции / владельцу кабинета`; it must not direct an operator to a credential cabinet.

## UI-kit mapping and zone boundary

| Zone | Required component and use | Explicitly not added |
| --- | --- | --- |
| Existing S-21 frame | Keep its current shell and all legacy zones. This task does not migrate the screen wholesale. | No new page, filter, modal, form, or action panel. |
| New read-only connection-status zone | `ScreenSection` contains a `DataTable` with stable columns: `Категория WB`, `Состояние`, `Последняя попытка`, `Последний подтверждённый успех`, `Что делать`. `TextCell` truncates long instructions with a full-value tooltip. | No local card, raw table, custom colours, or credential field. |
| State | `StatusChip` only. `ok` is `Подключено`; `warn` is temporary or stale; `stop` is a configuration/auth/permission condition; `neutral` is informational. | A single global green status, because categories may disagree. |
| Blocking/forbidden retrieval result | `ErrorNotice` in the body immediately above the status table or empty zone. The message is warehouse language, not HTTP or upstream text. | Raw `detail`, HTTP code, endpoint, URL, stack trace, token diagnostic, or retry command. |
| Initial loading | `DataTable loading`, which uses `TableSkeletonBody` for the five fixed columns. | Empty white space, a full-screen spinner, or a success claim while data is loading. |
| No applicable WB categories | `EmptyState` with a concrete reason and instruction. | Treating an empty result as `Подключено` or as a secret failure. |

All named controls are exported by `frontend/src/ui-kit/index.ts` and cover this one new zone. There is no `DESIGN_SYSTEM_GAP` blocker. `ScreenSection` is the sole outlined work zone; it must not be nested in another card.

## State contract

The table has one row per applicable category. A failure updates `Последняя попытка` but preserves the previous `Последний подтверждённый успех` and its source. The latter is labelled as a past fact and must never be styled or worded as evidence that the current connection works. Only a new valid success changes it. `STALE` is derived from the Product-approved TTL and does not rewrite either timestamp.

| Normalized condition | Chip and exact operator text | Time treatment | Instruction |
| --- | --- | --- | --- |
| `CONNECTED` | `Подключено` (`ok`): `Подключение этой категории подтверждено.` | Both attempt and confirmed success show this success time; source is `Проверка подключения` or `Рабочая операция`. | `Действий не требуется.` |
| `NOT_CONFIGURED` | `Не настроено` (`stop`): `Подключение WB для этой категории не настроено.` | Attempt is local evaluation time. Previous success, if any, remains marked `Последний подтверждённый успех`; otherwise `Нет подтверждённого успеха`. | `Передайте ответственному за интеграции.` |
| `EXPIRED` | `Срок истёк` (`stop`): `Срок подключения WB истёк.` | Preserve past success; do not infer revocation. | `Передайте ответственному за интеграции.` |
| `AUTH_REJECTED` | `Не принято WB` (`stop`): `WB не принял подключение для этой категории. Повтор операции не поможет до проверки подключения.` | Preserve past success. | `Передайте категорию и время последней попытки ответственному за интеграции.` |
| `SERVICE_SECRET_MISMATCH` within safe `AUTH_REJECTED` classification | The same `Не принято WB` chip, with the narrower text `Подключение для этой категории не совпадает с используемым сервисом.` | Preserve past success. Neither the effective secret nor the base/slot name is shown. | `Передайте ответственному за интеграции название категории и время попытки.` |
| `INSUFFICIENT_ACCESS` | `Недостаточно прав` (`stop`): `Подключение работает, но для этой операции не хватает категории или права.` | Preserve past success. | `Передайте ответственному за интеграции.` |
| `CHECK_DELAYED` | `Проверка отложена` (`warn`): `WB временно ограничил проверку подключения.` | Preserve past success. If `retry_after_at` exists, render `Следующая проверка не раньше <local time>`; otherwise no invented interval. | `Дождитесь следующей проверки; не повторяйте операцию.` |
| `NETWORK_UNAVAILABLE` | `Нет связи с WB` (`warn`): `Не удалось связаться с WB. Это не подтверждает неисправность подключения.` | Preserve past success and show it as `Последний подтверждённый успех`. | `Попробуйте рабочую операцию позже. Если состояние не меняется, передайте его ответственному за интеграции.` |
| `WB_UNAVAILABLE` | `WB недоступен` (`warn`): `WB временно не отвечает корректно. Это не подтверждает неисправность подключения.` | Preserve past success. | `Попробуйте рабочую операцию позже; при сохранении состояния передайте его ответственному за интеграции.` |
| `STALE` | `Давно не проверялось` (`warn`): `Статус давно не проверялся.` | Keep the historical success and attempt timestamps unchanged; the stale age is not a new failed attempt. | `Передайте ответственному за интеграции время последнего подтверждённого успеха.` |
| `WRITE_ACCESS_UNKNOWN` alongside another state | No independent chip. Under the category instruction: `Право записи не подтверждено.` | It changes neither connection state nor timestamps. | `Не считать это разрешением на операции записи.` |

`EXPIRING_SOON` is deliberately not rendered in this stage: S04 leaves its time window to Product. S11 may add it only with an approved threshold, wording, and tone. Similarly, `incident_ref` stays hidden until S11 approves both its visibility and the permitted audience; no placeholder is shown in the meantime.

## Textual mockups

### A. Partial success is not a global success

```text
S-21 / existing screen header and existing legacy controls
ScreenSection: Подключение Wildberries
  DataTable
    Категория WB | Состояние        | Последняя попытка | Последний подтверждённый успех | Что делать
    Контент      | [Подключено]     | 21.08 10:14 MSK  | 21.08 10:14 MSK, проверка     | Действий не требуется.
    Поставки     | [Недостаточно прав] | 21.08 10:14 MSK | 20.08 16:40 MSK, рабочая операция | Передайте ответственному за интеграции.
    Маркетплейс  | [Проверка отложена] | 21.08 10:14 MSK | 20.08 16:40 MSK, проверка     | Следующая проверка не раньше 10:44 MSK. Не повторяйте операцию.
```

No status above the table says that all WB integration works. The `Поставки` and `Маркетплейс` rows retain their own historical success without hiding the present problem.

### B. Configuration/authentication fault, including service mismatch

```text
ErrorNotice
  "Для части категорий WB требуется проверка подключения. Оператор не может изменить его на этом экране."

DataTable
  Контент | [Не настроено] | 21.08 10:14 MSK | Нет подтверждённого успеха
           | Передайте ответственному за интеграции.
  Поставки | [Не принято WB] | 21.08 10:14 MSK | 20.08 16:40 MSK, проверка
            | Подключение для этой категории не совпадает с используемым сервисом.
            | Передайте ответственному за интеграции название категории и время попытки.
```

There is no input, reveal, edit, save, delete, rotate, or test command in this mockup. Neither a key value, mask, fingerprint, JWT claim, service slot, header, URL, nor raw WB response is present.

### C. Temporary WB/network condition with preserved history

```text
DataTable
  Маркетплейс | [WB недоступен] | 21.08 10:14 MSK | 20.08 16:40 MSK, рабочая операция
              | WB временно не отвечает корректно. Это не подтверждает неисправность подключения.
              | Попробуйте рабочую операцию позже; при сохранении состояния передайте его ответственному за интеграции.
```

`20.08 16:40 MSK` stays visibly historical. It must not turn the current `WB недоступен` row green or enable an operation that is otherwise blocked.

### D. Loading, empty, and forbidden

```text
Loading
  DataTable loading: five-column TableSkeletonBody
  No status claim and no action in the connection zone.

Empty, only when the selected seller has no applicable WB categories
  EmptyState: "Для выбранного селлера нет категорий WB."
  Hint: "Статус появится после настройки у ответственного за интеграции."

Forbidden
  ErrorNotice: "Нет доступа к состоянию подключения этого селлера. Обратитесь к руководителю смены."
  No table, no status, and no indication whether a secret exists.
```

An absent diagnostic payload for a seller that does have applicable WB categories is not an empty state; it is a retrieval failure shown with `ErrorNotice`. A long seller name, local timestamp, and instruction wrap inside their cell with no horizontal page scroll; the column headings and `StatusChip` labels do not wrap.

## Non-negotiable safety and evidence requirements

- The rendered DOM, client state, analytics, screenshot, support export, receipt, and test artifact may contain only the allowlisted fields above. They must exclude `Authorization`, `X-Client-Secret`, any token or mask/fingerprint, JWT/payload/identifiers, category bitmask, request or response headers/body/detail, upstream URL/query/path, stack trace, and any derived credential material.
- S15 must bind and execute the 16 existing `AUTH-EMU-001` through `AUTH-EMU-016` cases against an emulator only. It must assert every state in this contract, no immediate 429 retry, current-attempt versus historical-success preservation, recovery, sandbox/production isolation, and zero denied-material occurrences in API/UI/evidence sinks.
- S24 visual evidence must include connected, partial failure, a stop-class fault, rate-limited or outage state, loading, empty, and forbidden at the normal and narrow review viewport. Screenshots use sanitized fixtures only and are rejected if a prohibited value appears.
- S25 Product Browser acceptance must verify that an operator can identify the affected category and next responsible role without being offered any credential-management action, and that a historical success cannot be read as a current success.

## Required S10/S11 review focus

- S10 checks all matrix states, partial rows, long instruction/timestamp rendering, narrow viewport, error precedence, and the absence of a misleading global connection status. It also checks the canon: `ErrorNotice` for errors, short `StatusChip` labels, fixed table columns, no nested card, and no local UI implementation.
- S11 approves the `STALE` TTL, any `EXPIRING_SOON` window, the audience for `incident_ref`, and whether the generic responsible role needs an approved organisation-specific contact. Until then, the exact safe defaults in this document stand.

## S09 verdict

`UX_CONTRACT_READY`: S-21 receives a concrete, read-only and capability-specific diagnostic zone with loading, empty, forbidden, success, partial, configuration, permission, service-mismatch, rate-limit, network, WB-outage, stale, and recovery-safe presentation. It preserves `last_success_at`, gives the operator a responsible-person instruction, and exposes no credential-management path or secret material.
