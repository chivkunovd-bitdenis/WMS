# Architect findings index

| ID | Severity | Status | Short result |
|---|---:|---|---|
| `ARCH-P0-001` | P0 | Confirmed twice on staging; static same in etalon | Two parallel completions of one inbound operation both return 200 and turn actual quantity 1 into balance/movement delta 2 |
| `ARCH-P1-002` | P1 | Confirmed deployment gap | Staging has no worker or Beat scheduler, so periodic FBS/marking/WB tasks do not have a process that triggers them |
| `ARCH-P1-003` | P1 | Confirmed static contract mismatch; runtime not run | Mobile expects `PackagingTaskOut`, server returns `PackProgressOut` after committing the pack mutation |
| `ARCH-P2-004` | P2 | Confirmed static read-model divergence; overbooking not runtime reproduced | FBS, MP and inventory subtract different reservation-owner sets |
| `ARCH-P2-005` | P2 | Confirmed static policy debt; bypass not proved | Seller-shop manager capability is partly inferred from hard-coded email markers |

No other static concern was promoted to a confirmed defect. In particular, no live-WB timeout, partial-batch, external duplication, tenant escape, print failure or device deserialization failure was runtime reproduced.
