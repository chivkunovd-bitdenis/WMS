# WMS-675 · узкий import manifest для интегратора

Этот список предназначен для переноса поверх уже принятого WMS-675 requirements
интегратора. Он не является cherry-pick всего `937adf` и не переносит product
code. Сначала сопоставить содержимое, затем добавить только перечисленные
файлы в отдельном интеграционном commit.

## Перенести

1. `docs/reviews/wms675-fresh-snapshot-20261007/PRODUCTION_LIVE_READ_20261007.md`
   — вывод свежего production read: 31/31 Ozon HTTP 200, 26 доказанных,
   local conducted=0 и current missing delta=26. Это read-only снимок, не
   acceptance и не deploy proof.
2. `docs/reviews/wms675-fresh-snapshot-20261007/OPERATIONAL_REPAIR_RUNBOOK_20261007.md`
   — условия после verified deploy, принятый WMS-662 entrypoint, locks,
   idempotency, readback и разграничение prepare/actual repair.
3. `docs/reviews/wms675-fresh-snapshot-20261007/marketplace-production-read-20261007-attempt2/remote-read-sanitized.json`
   — очищенный внешний proof; SHA-256
   `82fe8696ac64b56461013ef9bfbaac3d0b1bd3328ed70eb745a68995b7465bab`.
4. Весь каталог
   `docs/reviews/wms675-fresh-snapshot-20261007/accounting-post-marketplace-20261007-attempt2/accounting-refresh-20261006-attempt1/`
   без изменения имён и байтов: 11 результатных `*.csv`, соответствующие
   `*.sql` и `manifest.json`. Manifest SHA-256
   `8b56eb9a2871465c66d2ba68a81b6a1c7051d1e81dfca02b3925434ef0643b77`;
   он фиксирует bounded SELECT, `writes=0`, `external_calls=0`, время и hashes.
5. В `docs/requirements/WMS-675.md` — только короткую ссылку на пункты 1–2 и
   их статус: current proof 937adf read-only; R6/actual repair не выполнен.
   Не заменять принятый у интегратора основной текст требований его ранней
   копией из этой ветки.

## Намеренно не переносить

- `backend/tests/test_wms675_recovery_evidence_contract.py`, его commit-историю
  `85d3d84d3`/`e0df56829` и любой новый meta-contract: это не защита учёта, а
  независимое review обнаружило F1–F3. История остаётся в исходной ветке,
  тихого удаления нет.
- Любой `backend/app` product code, WMS-662 tests, новый runner, UI, сущности,
  SQL migration или копию accepted product package. Они уже принадлежат общему
  кандидату и проверяются там.
- Ранний `marketplace-read-20261007-attempt1/manifest.json`: он описывает
  локальный `live_transport_disabled`, который заменён свежим production proof.
- Ранние local accounting snapshots, `collect_*.py`, top-level SQL и
  `FRESH_READ_HANDOFF.md`: они полезны как история исследования, но не нужны
  интегратору для воспроизводимости актуальной current delta. Historical frozen
  bundle уже остаётся на принятой стороне requirements.

После переноса интегратор не заявляет, что repair выполнен, пока verified
deployed SHA, fresh preflight, штатное проведение и независимый readback не
доказаны отдельными новыми evidence.
