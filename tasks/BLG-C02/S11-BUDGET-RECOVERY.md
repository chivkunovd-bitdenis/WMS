# BLG-C02 S11 budget recovery packet

- `wave_id`: `wave-a1b311d18f07`
- `card_id`: `BLG-C02`
- `stage`: `S11 PRODUCT_CONTRACT_APPROVAL`
- `tier`: `expensive`
- `limit`: wave maximum `35.000 USD` and `12,000,000` tokens
- `observed_or_projected_usage`: current wave `34.813 USD` and `4,390,870`
  tokens; submitted S11 usage `0.250 USD` and `37,200` tokens; projected wave
  `35.063 USD` and `4,428,070` tokens
- `next_action`: owner records a reasoned `PIPELINE_BUDGET_OVERRIDE:
  owner-approved` with a new wave limit above the projected total, then resumes
  `BLG-C02` at S11 through the controller. The submitted usage must not be
  reduced merely to fit the remaining budget.

Controller result: `WAITING`, blocker type `OWNER_INPUT`, reason code
`BUDGET_HARD_STOP`, resume stage `S11`. No S11 approval receipt, S12 packet, or
S12 dispatch exists. The Product contract is written but is not controller-
accepted until a permitted resumed `advance` succeeds.
