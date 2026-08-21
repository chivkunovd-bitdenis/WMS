# Wave budget override

Wave: wave-a1b311d18f07
Recorded at: 2026-08-21T08:53:00+03:00
Recorded by: pipeline-orchestrator

PIPELINE_BUDGET_OVERRIDE: owner-approved

Reason:
The owner explicitly rejected treating the local Pipeline v2 budget stop as a reason to stop the
night wave after being told that `BUDGET_HARD_STOP` came from `pipeline/budget-policy.yml` and is a
control-plane spend guard, not a billing-system fact.

New limit:
Continue Pipeline v2 work for wave-a1b311d18f07 for this night run. Treat the previous
`BUDGET_HARD_STOP` holds as closed where budget was the only blocker, while still recording usage
receipts for every accepted stage.

Expires at:
2026-08-21T18:53:00+03:00

Boundaries unchanged:
- No live deploy.
- No production changes.
- No live WB/Ozon calls.
- No secrets, keys, or credential cabinets.
- No release for BLG-C01 or BLG-C02 without separate owner exact-SHA approval.
- No Dev before required BA/Product/Research/Architect receipts.
- One agent cannot accept its own work where Pipeline v2 requires an independent gate.
