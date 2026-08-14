# Батч 02. Blocker недоступности in-app Browser

## Точный checkpoint

- UTC timestamp: `2026-08-12T11:32:55.622Z`.
- Moscow time (UTC+03:00): `2026-08-12 14:32:55.622`.
- Выполнен свежий штатный setup browser runtime по Browser skill.
- Точный результат выбора обязательного backend: `agent.browsers.get("iab")` → `Browser is not available: iab`.
- После чтения обязательного `bootstrap-troubleshooting` выполнена одна разрешённая discovery-проверка.
- Точный discovery result: `await agent.browsers.list()` → `[]`.

In-app Browser отсутствует на уровне доступных browser backends. Это не доказательство сбоя staging, backend или authentication: до URL staging в этом ходе дойти было невозможно. Подмена Chrome, external browser, отдельным Playwright или source-code verdict не выполнялась.

## Состояние B02

Карта процесса и полный execution checklist сохранены в:

- `B02_INPUT_PROCESS_MAP_RU.md`;
- `B02_EXECUTION_CHECKLIST_RU.md`.

Isolated synthetic seller, созданный в B01, по последнему подтверждённому Browser-состоянию существует, но populated products/documents для B02 ещё не создавались. В этом ходе не выполнено ни одной staging mutation, не использованы WB, secrets, credential actions, shared-stock actions или внешняя отгрузка.

## Точный remaining ledger

Все **63** пункта `B02-C001`–`B02-C063` остаются `NOT_RUN_BROWSER_UNAVAILABLE`. Категории и количество:

| Диапазон | Область | Осталось | Статус |
|---|---|---:|---|
| `B02-C001`–`B02-C009` | Browser/session и isolated product fixtures | 9 | `NOT_RUN_BROWSER_UNAVAILABLE` |
| `B02-C010`–`B02-C018` | Seller products populated, ТЗ, размеры экрана | 9 | `NOT_RUN_BROWSER_UNAVAILABLE` |
| `B02-C019`–`B02-C035` | Inbound draft, validation, double-click, reload, submit handoff | 17 | `NOT_RUN_BROWSER_UNAVAILABLE` |
| `B02-C036`–`B02-C044` | Documents populated, filters/sort/row/back, discrepancy CTA | 9 | `NOT_RUN_BROWSER_UNAVAILABLE` |
| `B02-C045`–`B02-C051` | Seller-side MP draft only | 7 | `NOT_RUN_BROWSER_UNAVAILABLE` |
| `B02-C052`–`B02-C059` | Settings, credentialless state, safe non-secret save | 8 | `NOT_RUN_BROWSER_UNAVAILABLE` |
| `B02-C060`–`B02-C063` | Evidence, sanitized log, ledger, findings/handoff | 4 | `NOT_RUN_BROWSER_UNAVAILABLE` |
|  | **Итого** | **63** | `NOT_RUN_BROWSER_UNAVAILABLE` |

Подробное ожидаемое действие и безопасный outcome каждой строки уже перечислены в `B02_EXECUTION_CHECKLIST_RU.md`; ни одна строка не повышена до PASS, FAIL, FRICTION или `BLOCKED_FIXTURE` без визуального evidence.

## Что нужно для продолжения

Возобновить тем же Product Lead после появления backend `iab`. Начать с `B02-C001`, затем выполнить checklist по порядку и сохранить screenshot каждого route/dialog/CTA/error/reload в `evidence/b02/`. Только после живого прогона создавать `B02_SCREEN_ACTION_LEDGER_RU.md`, `B02_FINDINGS_RU.md` и `B02_HANDOFF_RU.md`.
