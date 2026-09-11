# WMS-429 final review contract

Perform one complete read-only review of the final frozen release SHA supplied by root. Development is already done; do not launch a second pipeline, tests, builds, browser automation, subagents, or deployments. Read actual files and Git diff; distinguish new defects from already accepted base code. Return exact file/line/trigger/consequence/minimal correction for actionable defects. Do not write code.

## Product boundaries

- User authorized production and APK publication; chat WMS-397/399 must remain outside production. Review its isolated branch separately only if root includes it explicitly.
- WB and Ozon FBS picking, packing, stickers, metadata and boxes are working surfaces. Do not add navigation/progress gates, move the operator backwards, or resurrect assembling->picking. The remaining checks must concern actual irreversible external operations, tenant access, duplicate execution or single stock write-off.
- Ozon never belongs to the Overdue worklist. Ozon identifiers/barcodes/labels and dialogs must use Ozon, including multi-product postings and marked positions. No silent WB or first-product substitution.
- Ozon assembly and final carriage approval are different external actions. Verify calls occur only on their intended explicit actions and failures do not become false local500 or duplicate shipments.
- Catalog filter means ENABLED STOCK PUBLICATION, and must compose with existing filters and mass edits.
- Use existing entities. No new business tables/counters/journals unless separately authorized. New print job types in the existing BackgroundJob are permitted; actual OS queue acceptance differs from physical printed output.
- Storage report is the explicitly requested simple seller->product report, metric cards matching Calculations, seller/category/date filters, liters/liter-days/rates/amount. No redesign of unrelated pages or invented monetary counters.
- CZ receiving must use existing seller TrueAPI authorization, preserve full code/position identity, report unavailable honestly, and keep receipt operation usable. DaData missing production key is an external setup dependency, not proof of live success.
- Do not open secret dashboards, inspect .env values, raw Claude/mobile logs, mobile PROGRESS, auth preferences, keystores, or production records. Do not mutate marketplace orders or operator documents.

## Review process

One Opus5 xhigh review -> bounded parallel corrections -> one isolated Astra high review. Do not demand duplicate complete test/review rounds. Root runs only necessary final technical checks and manual UI checks against an isolated fixture. Report actual material holes; do not invent protective blockers or new frontend requests.

## Already published APK

APK11 SHA2568435c3abcd240afbaadb95e157512d52a56c105fd73440e6991933741237a81f was uploaded and downloaded back for hash verification; public update.json was read back as versionCode11. The accepted recovery delta lives in the safe WMS patch record4b1a70c6. Physical TSD is explicitly not a pre-release gate, and network printing is not included in APK11.
