# WMS-652: Ozon posting date CI fixture correction

Date: 07.10.2026.

## Observed failure and classification

GitHub Actions run `37553998053` failed only
`test_posting_barcode_price_and_creation_date_come_from_the_real_fields` after
2287 passing tests. The persisted `created_at_wb` value had the expected wall
time `2026-09-01 10:30`, but SQLite returned it without `tzinfo`, so it did not
compare equal to `2026-09-01 10:30+00:00`.

The product path parses the Ozon `in_process_at` value ending in `Z` as UTC and
the `FbsOrder.created_at_wb` column is declared `DateTime(timezone=True)`. A
same-session query can retain the just-created ORM object and conceal SQLite's
representation difference. After an explicit `refresh`, the old strict test
reproduced the CI failure exactly: same date and time, naive SQLite value versus
the UTC-aware expected value.

This is a SQLite test-fixture representation defect, not a production time
shift: the product code and migration were not changed.

## Corrected contract

Commit `bdfea8e006c9dd7a15341b9aef27abeaaefa3b02` makes the test read the stored
row after the round-trip. It verifies the column's timezone-aware declaration.
Only for SQLite, whose datetime storage omits offset metadata, the returned wall
time is explicitly interpreted as UTC. Other dialects must return an aware
datetime. The assertions still require the exact UTC instants for both
`in_process_at` and `shipment_date`; a wrong source hour does not pass.

## Verification

The targeted SQLite test was red before normalization and passed afterwards.
`ruff check tests/test_ozon_posting_contract.py` passed, and the complete target
file passed: 44 tests.

For an independent dialect check, the same target scenario passed against a
fresh test-only PostgreSQL database on an owned loopback cluster at port 55467.
That branch requires the returned timestamp to be timezone-aware. Its raw JUnit
XML and log remain in the ignored `.agent-runs/night-20261006-01a112a8/f6-local-pg`
directory:

- `ozon-date-roundtrip.xml`, SHA-256
  `389f8b6b9f8a2df41a996c9e3c3fb4f88ee84daaca38102cc10b8cac47068e4a`;
- `ozon-date-roundtrip.log`, SHA-256
  `262eb7593124b35872166f12cbc341109c3acd1b0337453b2aadd798c88e8860`.

The owned cluster was stopped afterwards and port 55467 confirmed free. The
existing PostgreSQL service on port 5432 was not used. This evidence does not
replace independent review or CI of the integration SHA.
