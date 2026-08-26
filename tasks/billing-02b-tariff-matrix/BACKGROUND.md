# Фон и решения: волна 2Б

## Текущее состояние

В checkout после принятой 2А уже есть immutable `OperationFact`, но он не
содержит денег. Старый денежный контур использует `BillingTariffVersion` с
дневным `valid_from`/`valid_to`, `BillingLedgerEntry` и неизменяемую
уникальность `uq_billing_ledger_source_event`. Он обслуживает legacy inbound,
marketplace outbound и storage; storage дополнительно зависит от склада и
настраивается на отдельном экране. Нельзя сделать вид, что этот контур уже
поддерживает часовые версии, product overrides и employee rates.

`FfSettingsScreen` — фактический owner S-19 (`/app/ff/settings`). В нём уже
есть header, warehouse panel и staff panel. `FfBillingScreen` уже умеет вести
пользователя к `settings?tab=tariffs`, но остаётся старым экраном начислений и
счетов; он не является частью 2Б. Реестр экранов назначает только S-19 на
`FfSettingsScreen`, следовательно добавление панели в эту зону не захватывает
чужой экран или route.

## Почему V2, а не правка legacy версии

Старые дневные unique indexes нужны существующему storage и уже выписанным
денежным строкам. Их изменение одновременно изменило бы meaning historical
links и позволило бы storage сменить цену посреди дня — это запрещено. Поэтому
V2 живёт рядом: non-storage получает timestamp intervals в UTC с Moscow input,
storage остаётся daily exception в `BillingTariffVersion`. Ledger хранит
nullable V2 link наряду со старой ссылкой, а не теряет историю.

Legacy non-storage copy — именно migration/backfill, не догадка: старый start
становится Moscow `00:00`, включительный old end — следующей исключающей
Moscow midnight. Если copy нельзя доказать без interval overlap/gap, migration
останавливается, а не делает частичный backfill.

## Области тарифов и приоритет

Seller matrix разделяет common scope, seller exception и product override.
Product price разрешена только для item unit; она выигрывает у seller/common.
Employee scope отделён от seller scope и допустим только для приёмки, подбора,
отгрузки, возврата. Упаковка сотрудника намеренно не дублируется: её factual
units/rate snapshot остаются в `PackagingTask` и
`staff_packaging_billing_service`.

Every scope is tenant-scoped. Service validates seller/product/user ownership
before it looks for an active version, locks one version stream while writing,
and treats `valid_to_at` as exclusive. Exact no-change retry is a no-op; a
changed matrix creates a new immutable version; any bad element rolls back the
whole payload. This makes a matrix save atomic rather than a sequence of
independent settings forms.

## Moscow time and money boundary

Administrator enters Moscow wall time; server resolves it with
`Europe/Moscow`, persists aware UTC timestamps, and rejects ambiguous/nonexistent
wall time if input cannot identify a single instant. Tests cover three-day,
month/year and timezone/DST-looking boundaries even though current Moscow zone
has no seasonal clock shift: the rule must not accidentally use browser-local
or UTC calendar dates. Amounts stay integer kopecks; overflow is rejected
before any write.

## UI boundary

At 1600px the new panel is a normal S-19 section after staff, not a second
Settings app. Existing UI-kit gives table density, fixed headers/columns,
overflow, skeleton loading, Russian error and empty states, status and actions.
The implementation may compose those pieces, but it must not add an in-screen
custom table, filter, dropdown, button or tab, nor modify `ui-kit/**`.
Separate ui-critic and live-browser judge verify the exact rendered state; unit
tests and Playwright do not replace that human browser check.
